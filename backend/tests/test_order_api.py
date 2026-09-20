"""API integration tests for /api/orders endpoints.

Tests the full HTTP workflow: create order -> allocate -> validate.
Requires PostgreSQL at head.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from datetime import date

from app.main import app

pytestmark = pytest.mark.db

TEST_DATE = "2099-01-01"
DOCUMENTED_CSV = (
    "slot,demandMW,generationMW,importsMW,marginMW\n"
    "19:00-19:30,4350,3800,200,50\n"
)

@pytest.fixture(autouse=True)
def _cleanup(engine):
    def wipe():
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM shed_order WHERE plan_id IN (SELECT id FROM deficit_plan WHERE date = :d)"), {"d": TEST_DATE})
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

async def _setup_validated_plan(client, auth) -> int:
    r = await client.post("/api/deficit/plans", json={"date": TEST_DATE, "mode": "J-1"}, headers=auth)
    plan_id = r.json()["id"]
    await client.post(
        f"/api/deficit/plans/{plan_id}/import-csv", headers=auth,
        files={"file": ("demo.csv", DOCUMENTED_CSV, "text/csv")},
    )
    await client.post(f"/api/deficit/plans/{plan_id}/validate", headers=auth)
    return plan_id

async def test_create_order_api(client):
    auth = await _login(client)
    plan_id = await _setup_validated_plan(client, auth)
    
    r = await client.post("/api/orders", json={"plan_id": plan_id}, headers=auth)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "DRAFT"

async def test_create_order_unauthorized(client):
    r = await client.post("/api/orders", json={"plan_id": 1})
    assert r.status_code == 401

async def test_create_order_wrong_role(client):
    # 'sana' is an operator and shouldn't be able to create orders if role requires DISPATCHER
    auth = await _login(client, username="sana")
    r = await client.post("/api/orders", json={"plan_id": 1}, headers=auth)
    assert r.status_code in [403, 404] # Depending on if plan exists or role is checked first

async def test_list_orders_api(client):
    auth = await _login(client)
    plan_id = await _setup_validated_plan(client, auth)
    await client.post("/api/orders", json={"plan_id": plan_id}, headers=auth)
    
    r = await client.get("/api/orders", headers=auth)
    assert r.status_code == 200
    orders = r.json()
    assert isinstance(orders, list)
    assert len(orders) >= 1

async def test_get_order_api(client):
    auth = await _login(client)
    plan_id = await _setup_validated_plan(client, auth)
    order_res = await client.post("/api/orders", json={"plan_id": plan_id}, headers=auth)
    order_id = order_res.json()["id"]
    
    r = await client.get(f"/api/orders/{order_id}", headers=auth)
    assert r.status_code == 200
    assert r.json()["id"] == order_id

async def test_allocate_order_api(client):
    auth = await _login(client)
    plan_id = await _setup_validated_plan(client, auth)
    order_res = await client.post("/api/orders", json={"plan_id": plan_id}, headers=auth)
    order_id = order_res.json()["id"]
    
    r = await client.post(f"/api/orders/{order_id}/allocate", headers=auth)
    assert r.status_code == 200
    assert r.json()["status"] == "ALLOCATED"

async def test_validate_order_api(client):
    auth = await _login(client)
    plan_id = await _setup_validated_plan(client, auth)
    order_res = await client.post("/api/orders", json={"plan_id": plan_id}, headers=auth)
    order_id = order_res.json()["id"]
    
    await client.post(f"/api/orders/{order_id}/allocate", headers=auth)
    r = await client.post(f"/api/orders/{order_id}/validate", headers=auth)
    assert r.status_code == 200
    assert r.json()["status"] == "VALIDATED"

async def test_cancel_order_api(client):
    auth = await _login(client)
    plan_id = await _setup_validated_plan(client, auth)
    order_res = await client.post("/api/orders", json={"plan_id": plan_id}, headers=auth)
    order_id = order_res.json()["id"]
    
    r = await client.post(f"/api/orders/{order_id}/cancel", json={"reason": "Testing cancellation"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["status"] == "CANCELLED"
