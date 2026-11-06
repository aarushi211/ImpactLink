"""Verify a running backend using a temporary Firebase user and test records.

Requires local Firebase admin credentials and the frontend Firebase API key.
No existing user is impersonated. Test data and the temporary user are removed.
"""

import argparse
from pathlib import Path
import uuid

from dotenv import dotenv_values
import firebase_admin
from firebase_admin import auth, credentials
import psycopg
from psycopg import sql
import requests


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "impactlink-backend"


def verify(base_url):
    config = dotenv_values(BACKEND / ".env")
    frontend = dotenv_values(ROOT / "impactlink-frontend/.env")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(str(BACKEND / "firebase-service-account.json")))
    uid = "migration-check-" + uuid.uuid4().hex
    session_id = None
    work_id = None
    http = requests.Session()

    def call(method, path, **kwargs):
        response = http.request(method, base_url.rstrip("/") + path, timeout=180, **kwargs)
        if not response.ok:
            raise RuntimeError(f"{method} {path} returned HTTP {response.status_code}")
        return response.json() if "application/json" in response.headers.get("Content-Type", "") else response.text

    try:
        custom_token = auth.create_custom_token(uid).decode()
        response = requests.post(
            "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken",
            params={"key": frontend["REACT_APP_FIREBASE_API_KEY"]},
            json={"token": custom_token, "returnSecureToken": True},
            headers={"Referer": "https://impactlink-cbfc5.web.app/", "Origin": "https://impactlink-cbfc5.web.app"},
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"Temporary Firebase sign-in returned HTTP {response.status_code}")
        http.headers["Authorization"] = "Bearer " + response.json()["idToken"]
        print("PASS temporary Firebase sign-in", flush=True)

        call("GET", "/")
        print("PASS application health", flush=True)
        results = call("POST", "/api/grants/search", json={"query": "urban forestry community resilience", "top_k": 3})
        if not results.get("grants"):
            raise RuntimeError("Grant search returned no results")
        print(f"PASS grant search: {len(results['grants'])} results", flush=True)

        created = call("POST", "/api/work/drafts", json={"title": "Temporary Neon verification", "content": "migration check"})
        work_id = created["id"]
        listed = call("GET", "/api/work/drafts/me")
        if not any(row["id"] == work_id for row in listed["drafts"]):
            raise RuntimeError("Saved draft was not returned by the list endpoint")
        call("PATCH", f"/api/work/drafts/{work_id}", json={"title": "Verified Neon update"})
        listed = call("GET", "/api/work/drafts/me")
        if next(row for row in listed["drafts"] if row["id"] == work_id)["title"] != "Verified Neon update":
            raise RuntimeError("Saved draft update was not persisted")
        call("DELETE", f"/api/work/drafts/{work_id}")
        if call("GET", "/api/work/drafts/me")["drafts"]:
            raise RuntimeError("Temporary draft was not deleted")
        print("PASS authenticated draft create/read/update/delete", flush=True)

        # No description: slot initialization reaches its first interrupt without
        # asking an LLM to generate a proposal, keeping the check small.
        created = call("POST", "/api/session", json={
            "flow": "scratch", "grant": {"grant_id": "migration-check", "title": "Temporary database verification"},
        })
        session_id = created["session_id"]
        restored = call("GET", f"/api/session/{session_id}")
        if restored.get("gate") != created.get("gate"):
            raise RuntimeError("Persisted proposal gate differs from the initial response")
        # Confirm that this running server actually wrote to the intended Neon DB.
        with psycopg.connect(config["DATABASE_URL_UNPOOLED"], connect_timeout=15) as connection:
            count = connection.execute("SELECT count(*) FROM public.checkpoints WHERE thread_id=%s", (session_id,)).fetchone()[0]
            if not count:
                raise RuntimeError("Server checkpoints were not found in the configured Neon database")
        print("PASS proposal checkpoint write/read in Neon", flush=True)
    finally:
        # Clean by the dedicated test UID/thread only, even if an HTTP check fails.
        with psycopg.connect(config["DATABASE_URL_UNPOOLED"], connect_timeout=15) as connection:
            connection.execute("DELETE FROM public.user_work WHERE user_id=%s", (uid,))
            if session_id:
                for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                    connection.execute(sql.SQL("DELETE FROM public.{} WHERE thread_id=%s").format(sql.Identifier(table)), (session_id,))
        try:
            auth.delete_user(uid)
        except auth.UserNotFoundError:
            pass
        http.close()
        print("Temporary verification user and database records removed", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    verify(args.base_url)
