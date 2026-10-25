"""
Regression test: the server starts with no configuration at all.

WHY: `docker compose up` must work out of the box. Settings used to require
GOOGLE_API_KEY, CORS_ORIGINS, a JWT secret, AWS and MLflow variables, so a fresh
install crashed at import time.
"""

import os
import subprocess
import sys
import textwrap


def test_server_starts_and_serves_with_an_empty_environment(tmp_path):
    script = textwrap.dedent(
        """
        from fastapi.testclient import TestClient
        from llmwatch.main import app

        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            r = client.post(
                "/auth/register",
                json={
                    "email": "first@example.com",
                    "password": "correct-horse-battery",
                    "workspace_name": "Acme",
                },
            )
            assert r.status_code == 201, r.text
        print("OK")
        """
    )
    # Only what a bare container has, plus paths kept inside tmp_path.
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
    }
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,  # no .env file here
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert "OK" in result.stdout
    # Defaults put the database and the generated secret under ./data
    assert (tmp_path / "data" / "llmwatch.db").exists()
    assert (tmp_path / "data" / "secret_key").exists()
