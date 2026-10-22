import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

NOW = datetime.now(timezone.utc)

COORDINATOR = {
    "user_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "rudo")),
    "first_name": "Rudo",
    "last_name": "Chikwanha",
    "full_name": "Rudo Chikwanha",
    "email": "rudo@example.org",
    "role": "patrol_coordinator",
    "is_active": True,
}
SECOND_COORDINATOR = {
    "user_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "farai")),
    "first_name": "Farai",
    "last_name": "Ncube",
    "full_name": "Farai Ncube",
    "email": "farai@example.org",
    "role": "patrol_coordinator",
    "is_active": True,
}
OFFICER = {
    "user_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "tendai")),
    "first_name": "Tendai",
    "last_name": "Moyo",
    "full_name": "Tendai Moyo",
    "email": "tendai@example.org",
    "role": "patrol_officer",
    "is_active": True,
}
USERS = [COORDINATOR, SECOND_COORDINATOR, OFFICER]

ZONE_BASINS = [
    ("Zone 1", "Sanyati"),
    ("Zone 2", "Sanyati"),
    ("Zone 3", "Bumi"),
    ("Zone 4", "Bumi"),
    ("Zone 5", "Sengwa"),
    ("Zone 6", "Sengwa"),
    ("Zone 7", "Binga"),
    ("Zone 8", "Mlibizi"),
]
ZONES = [
    {
        "zone_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, name)),
        "name": name,
        "basin": basin,
        "zone_type": "fishing_zone",
        "is_active": True,
        "radiance_threshold": 10.0,
        "cluster_radius_m": 1500.0,
        "min_cluster_points": 3,
        "confidence_threshold": 0.5,
    }
    for name, basin in ZONE_BASINS
]

CHANGES = [
    (0, COORDINATOR, 96, 8.0, 1200, 3, 0.3),
    (0, COORDINATOR, 72, 10.0, 1500, 3, 0.4),
    (0, SECOND_COORDINATOR, 48, 12.5, 1500, 4, 0.5),
    (2, COORDINATOR, 40, 9.0, 1000, 3, 0.45),
    (2, SECOND_COORDINATOR, 20, 11.0, 1100, 3, 0.5),
    (4, COORDINATOR, 30, 14.0, 2000, 5, 0.55),
    (6, SECOND_COORDINATOR, 12, 7.5, 900, 3, 0.35),
    (7, COORDINATOR, 3, 6.0, 800, 2, 0.3),
]
HISTORY = [
    {
        "history_id": str(uuid.uuid4()),
        "zone_id": ZONES[index]["zone_id"],
        "radiance_threshold": radiance,
        "cluster_radius_m": radius,
        "min_cluster_points": points,
        "confidence_threshold": confidence,
        "changed_by": user["user_id"],
        "changed_at": (NOW - timedelta(hours=hours)).isoformat(),
    }
    for index, user, hours, radiance, radius, points, confidence in CHANGES
]

app = FastAPI(title="Vesper - zone history local testing")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.100.224:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


def page(rows, limit, offset):
    return rows[offset : offset + limit]


@app.get("/vesper/zone-setting-history")
def list_history(limit: int = 200, offset: int = 0):
    return page(HISTORY, limit, offset)


@app.get("/vesper/zones")
def list_zones(limit: int = 200, offset: int = 0):
    return page(ZONES, limit, offset)


@app.get("/vesper/users")
def list_users(limit: int = 200, offset: int = 0):
    return page(USERS, limit, offset)


@app.get("/vesper/users/me")
def current_user():
    return COORDINATOR
