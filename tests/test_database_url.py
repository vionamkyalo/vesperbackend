import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_database_engine_uses_normalized_heroku_url():

    env = {
        **os.environ,
        "DATABASE_URL": "postgres://user:pass@localhost:5432/vesper",
        "JWT_SECRET": "test-secret-that-is-long-enough-1234567890",
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import database; print(database.engine.url.drivername)",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    driver = result.stdout.strip()
    assert driver.startswith("postgresql"), driver
    assert driver != "postgres"
