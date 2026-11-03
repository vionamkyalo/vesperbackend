from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_alembic_ini_uses_runtime_database_url():
    alembic_ini = (ROOT / "alembic.ini").read_text()
    assert "sqlalchemy.url = DATABASE_URL" in alembic_ini


def test_alembic_env_uses_sqlalchemy_metadata():
    env_text = (ROOT / "alembic" / "env.py").read_text()

    assert "from sqlalchemy.orm import declarative_base" in env_text
    assert "Base = declarative_base()" in env_text
    assert "target_metadata=Base.metadata" in env_text


def test_project_declares_alembic_and_psycopg_dependencies():
    pyproject_text = (ROOT / "pyproject.toml").read_text()
    pyproject = tomllib.loads(pyproject_text)

    dependencies = pyproject["project"]["dependencies"]
    dep_names = [
        dep.split(">=")[0].split("[")[0].split("==")[0] for dep in dependencies
    ]

    assert "alembic" in dep_names
    assert "psycopg" in dep_names
