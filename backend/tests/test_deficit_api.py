"""HTTP-level tests for M3, through the real FastAPI app (not just the
service layer) — this is what actually catches response-serialization bugs
like a lazy-load attempt outside the async greenlet context, which
test_deficit_db.py's direct service calls cannot see since they never go
through Pydantic's response_model serialization.

Uses a sentinel date far from real usage so it never collides with a real
plan, and cleans up afterward with a real (committed) delete — HTTP
requests commit their own transactions independently of any test-owned one,
so the `db`/`adb` rolled-back-transaction fixtures don't apply here.
"""
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.main import app

pytestmark = pytest.mark.db

TEST_DATE = "2099-01-01"

DOCUMENTED_CSV = (
    "slot,demandMW,generationMW,importsMW,marginMW\n"
    "19:00-19:30,4350,3800,200,50\n"
    "19:30-20:00,4400,3800,200,50\n"
    "20:00-20:30,4300,3800,200,50\n"
    "20:30-21:00,4150,3800,200,50\n"
    "21:00-21:30,4000,3800,200,50\n"
)


@pytest.fixture(autouse=True)
def _cleanup(engine):
    """Delete any leftover sentinel-date plan before AND after, using a real
    committed connection (cascade deletes slots/revisions)."""
    def wipe():
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM deficit_plan WHERE date = :d"), {"d": TEST_DATE})
    wipe()
    yield
    wipe()


@pytest.fixture()
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _login(client, username="ahmed", password="delestage123") -> dict:
    r = await client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_full_deficit_flow_over_http(client):
    auth = await _login(client)

    r = await client.post("/api/deficit/plans", json={"date": TEST_DATE, "mode": "J-1"}, headers=auth)
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["status"] == "DRAFT"
    assert plan["slots"] == []  # the exact assertion that used to crash the server
    plan_id = plan["id"]

    r = await client.post(
        f"/api/deficit/plans/{plan_id}/import-csv", headers=auth,
        files={"file": ("demo.csv", DOCUMENTED_CSV, "text/csv")},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["created"] == 5
    assert result["updated"] == 0
    assert [s["deficit_mw"] for s in result["slots"]] == [300, 350, 250, 100, 0]

    r = await client.get(f"/api/deficit/plans/{plan_id}", headers=auth)
    assert r.status_code == 200, r.text
    assert len(r.json()["slots"]) == 5

    slot_id = result["slots"][0]["id"]
    r = await client.patch(
        f"/api/deficit/plans/{plan_id}/slots/{slot_id}", headers=auth, json={"imports_mw": 150},
    )
    assert r.status_code == 200, r.text
    assert r.json()["deficit_mw"] == 350

    r = await client.get(f"/api/deficit/plans/{plan_id}/slots/{slot_id}/revisions", headers=auth)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1

    r = await client.post(f"/api/deficit/plans/{plan_id}/validate", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "VALIDATED"


async def test_bcc_operator_gets_403(client):
    auth = await _login(client, username="sana")
    r = await client.post("/api/deficit/plans", json={"date": TEST_DATE, "mode": "J-1"}, headers=auth)
    assert r.status_code == 403


async def test_unauthenticated_gets_401():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/deficit/plans")
        assert r.status_code == 401
