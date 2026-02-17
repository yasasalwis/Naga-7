
import asyncio
import httpx
import pytest
from n7_core.api_gateway.service import app
from n7_core.config import settings
from n7_core.database.session import async_session_maker
from n7_core.models.user import User
from sqlalchemy import delete

# Use TestClient for synchronous testing of FastAPI app, 
# or httpx.AsyncClient for async testing.
from httpx import AsyncClient, ASGITransport

BASE_URL = "http://test"

@pytest.mark.asyncio
async def test_auth_flow():
    # 0. Setup: Ensure clean state for test user
    test_username = "auth_test_user"
    test_password = "password123"
    test_email = "auth_test@example.com"
    
    async with async_session_maker() as session:
        await session.execute(delete(User).where(User.username == test_username))
        await session.commit()
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
        
        # 1. Access protected endpoint without token (Expect 401)
        # /api/agents is protected
        resp = await client.get("/agents/")
        print(f"[1] No Token Access: {resp.status_code}")
        assert resp.status_code == 401
        
        # 2. Register User (if public registration is enabled or use seed)
        # We'll use the /users/ endpoint
        user_data = {
            "username": test_username,
            "email": test_email,
            "password": test_password,
            "role": "analyst"
        }
        resp = await client.post("/users/", json=user_data)
        print(f"[2] Register User: {resp.status_code}")
        # It might be 200 or 400 if already exists (but we deleted it)
        assert resp.status_code == 200
        
        # 3. Login to get Token
        login_data = {
            "username": test_username,
            "password": test_password
        }
        resp = await client.post("/auth/token", data=login_data)
        print(f"[3] Login: {resp.status_code}")
        assert resp.status_code == 200
        token_data = resp.json()
        access_token = token_data["access_token"]
        assert access_token is not None
        
        # 4. Access protected endpoint with token (Expect 200)
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = await client.get("/agents/", headers=headers)
        print(f"[4] With Token Access: {resp.status_code}")
        assert resp.status_code == 200
        
        print("Auth Flow Verified Successfully")

if __name__ == "__main__":
    # Allow running directly or via pytest
    try:
        asyncio.run(test_auth_flow())
    except Exception as e:
        print(e)
        import sys
        sys.exit(1)
