"""Deployment regression tests; isolated processes never read .env or production data."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def run_python(self, code, **settings):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("DB_") and key not in
               {"DATABASE_URL", "APP_ENV", "CORS_ORIGINS"}}
        env.update(APP_ENV="development", DATABASE_URL="sqlite:///:memory:",
                   PYTHONDONTWRITEBYTECODE="1")
        env.update(settings)
        return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=20)

    def test_production_rejects_sqlite(self):
        result = self.run_python("import backend.database", APP_ENV="production")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("正式環境不可使用 SQLite", result.stderr)

    def test_invalid_database_type_fails_instead_of_falling_back(self):
        result = self.run_python("import backend.database", DB_TYPE="postgress")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DB_TYPE 必須是", result.stderr)

    def test_postgres_configuration_preserves_password_and_ssl(self):
        result = self.run_python(
            "from backend.database import engine; "
            "assert engine.url.password == 'test@:/?#'; "
            "assert engine.url.query['sslmode'] == 'require'; "
            "assert engine.url.get_backend_name() == 'postgresql'",
            APP_ENV="production", DB_TYPE="postgres", DB_HOST="invalid.example",
            DB_PASSWORD="test@:/?#")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_database_url_override_does_not_pass_sqlite_arguments_to_postgres(self):
        result = self.run_python(
            "from unittest.mock import patch; "
            "from sqlalchemy import create_engine; "
            "mock = patch('sqlalchemy.create_engine', wraps=create_engine).start(); "
            "import backend.database; "
            "assert 'check_same_thread' not in mock.call_args.kwargs['connect_args']",
            APP_ENV="production", DATABASE_URL="postgresql+psycopg2://user:test@invalid.example/db")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_health_static_files_and_database_failure(self):
        # Exercise HTTP responses without opening a port or installing a test client.
        result = self.run_python('''
import asyncio
import json
from unittest.mock import patch
from sqlalchemy.exc import OperationalError
from backend.main import app, engine

async def get(path):
    messages = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(message):
        messages.append(message)
    await app({"type": "http", "asgi": {"version": "3.0"},
               "http_version": "1.1", "method": "GET", "scheme": "http",
               "path": path, "raw_path": path.encode(), "query_string": b"",
               "root_path": "", "headers": [], "server": ("localhost", 8000),
               "client": ("127.0.0.1", 1234)}, receive, send)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, body

async def check():
    for path in ("/", "/css/style.css", "/js/app.js", "/docs", "/api/health", "/api/ready"):
        status, body = await get(path)
        assert status == 200 and body, (path, status)
    with patch.object(engine, "connect", side_effect=OperationalError("SELECT 1", {}, Exception("private-details"))):
        status, body = await get("/api/ready")
        assert status == 503
        assert json.loads(body) == {"status": "unavailable"}
        assert (await get("/api/health"))[0] == 200

asyncio.run(check())
''')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
