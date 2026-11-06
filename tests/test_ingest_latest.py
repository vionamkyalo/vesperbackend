import urllib.error
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models.zone_baseline import MoonBand
from models.zone_light_reading import IngestionStatus, ZoneLightReading
from scripts import ingest_latest
from services.ingestion import ingestion_service
from services.zone_baseline import moon_band_for, zone_baseline_service

TODAY = date(2026, 11, 4)


def fake_result(alerts=0, skipped=False):
    return SimpleNamespace(
        skipped=skipped,
        detection=SimpleNamespace(alerts=[object()] * alerts),
    )


def add_reading(db_session, zone, night):
    db_session.add(
        ZoneLightReading(
            zone_id=zone.zone_id,
            observation_date=night,
            ingestion_status=IngestionStatus.RECEIVED,
        )
    )
    db_session.commit()


@pytest.fixture
def baseline_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        zone_baseline_service,
        "recalculate",
        lambda db, user, data: (
            calls.append(data) or SimpleNamespace(updated=[], skipped=[])
        ),
    )
    return calls


def test_default_lookback_is_30_nights():
    assert ingest_latest.LOOKBACK_DAYS == 30


def test_fetches_missing_nights_oldest_first(
    db_session, sample_coordinator, sample_zone, monkeypatch, baseline_calls
):
    add_reading(db_session, sample_zone, date(2026, 11, 1))
    calls = []
    monkeypatch.setattr(
        ingestion_service,
        "run_for_night",
        lambda db, user, night: calls.append(night) or fake_result(),
    )

    ingest_latest.run(db_session, TODAY)

    assert calls == sorted(calls)
    assert calls[0] >= date(2026, 10, 5)
    assert calls[-1] == date(2026, 11, 3)
    assert date(2026, 11, 1) not in calls
    assert TODAY not in calls
    assert all(moon_band_for(night) != MoonBand.BRIGHT for night in calls)


def test_unpublished_night_does_not_stop_the_run(
    db_session, sample_coordinator, sample_zone, monkeypatch, baseline_calls
):
    def fake_run(db, user, night):
        if night == date(2026, 11, 3):
            raise urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        if night == date(2026, 11, 2):
            raise HTTPException(status_code=404, detail="no file")
        return fake_result(alerts=2)

    monkeypatch.setattr(ingestion_service, "run_for_night", fake_run)

    results = ingest_latest.run(db_session, TODAY)

    assert results[date(2026, 11, 3)] == "not published yet"
    assert results[date(2026, 11, 2)] == "not published yet"
    assert results[date(2026, 11, 1)] == "2 alerts"


def test_one_failing_night_does_not_stop_the_run(
    db_session, sample_coordinator, sample_zone, monkeypatch, baseline_calls
):
    def fake_run(db, user, night):
        if night == date(2026, 11, 1):
            raise ValueError("too many points")
        return fake_result(skipped=night == date(2026, 11, 2))

    monkeypatch.setattr(ingestion_service, "run_for_night", fake_run)

    results = ingest_latest.run(db_session, TODAY)

    assert results[date(2026, 11, 1)] == "failed"
    assert results[date(2026, 11, 2)] == "skipped (too cloudy)"
    assert results[date(2026, 11, 3)] == "0 alerts"


def test_new_nights_refresh_the_baselines(
    db_session, sample_coordinator, sample_zone, monkeypatch, baseline_calls
):
    monkeypatch.setattr(
        ingestion_service, "run_for_night", lambda db, user, night: fake_result()
    )

    ingest_latest.run(db_session, TODAY)

    assert len(baseline_calls) == 1
    assert baseline_calls[0].lookback_days == 30
    assert baseline_calls[0].min_nights == ingest_latest.BASELINE_MIN_NIGHTS


def test_no_new_nights_leaves_baselines_alone(
    db_session, sample_coordinator, sample_zone, monkeypatch, baseline_calls
):
    def not_published(db, user, night):
        raise HTTPException(status_code=404, detail="no file")

    monkeypatch.setattr(ingestion_service, "run_for_night", not_published)

    ingest_latest.run(db_session, TODAY)

    assert baseline_calls == []


def test_runs_as_the_coordinator(
    db_session,
    sample_coordinator,
    sample_officer,
    sample_zone,
    monkeypatch,
    baseline_calls,
):
    users = []
    monkeypatch.setattr(
        ingestion_service,
        "run_for_night",
        lambda db, user, night: users.append(user) or fake_result(),
    )

    ingest_latest.run(db_session, TODAY)

    assert {user.user_id for user in users} == {sample_coordinator.user_id}


def test_no_coordinator_does_nothing(db_session, sample_officer, monkeypatch):
    calls = []
    monkeypatch.setattr(
        ingestion_service,
        "run_for_night",
        lambda db, user, night: calls.append(night),
    )

    assert ingest_latest.run(db_session, TODAY) == {}
    assert calls == []
