import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_user_registration_and_login_flow(client: AsyncClient):
    """Test full registration, authentication, and profile retrieval cycle with Bar Council ID."""
    email = "lawyer@example.com"
    password = "SuperSecretPassword123"
    full_name = "Jane Doe, Esq."
    bar_council_id = "D/1234/2020"

    # 1. Register
    register_res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
            "bar_council_id": bar_council_id,
        },
    )
    assert register_res.status_code == 201
    user_data = register_res.json()
    assert user_data["email"] == email
    assert user_data["full_name"] == full_name
    assert user_data["bar_council_id"] == bar_council_id
    assert "password_hash" not in user_data
    assert "id" in user_data

    # 2. Duplicate registration should fail with 400
    dup_res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert dup_res.status_code == 400
    assert "already exists" in dup_res.json()["detail"]

    # 3. Login with incorrect password should fail with 401
    bad_login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "wrongpassword"},
    )
    assert bad_login_res.status_code == 401

    # 4. Login with correct password should succeed with JWT
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    token = token_data["access_token"]

    # 5. Access protected /me without token should fail with 401
    unauth_me = await client.get("/api/v1/auth/me")
    assert unauth_me.status_code == 401

    # 6. Access protected /me with Bearer token
    auth_headers = {"Authorization": f"Bearer {token}"}
    me_res = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_res.status_code == 200
    profile = me_res.json()
    assert profile["email"] == email
    assert profile["full_name"] == full_name
    assert profile["bar_council_id"] == bar_council_id

    # 7. Update profile
    update_res = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers,
        json={"full_name": "Jane Senior Partner", "bar_council_id": "D/5678/2021"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["full_name"] == "Jane Senior Partner"
    assert update_res.json()["bar_council_id"] == "D/5678/2021"


@pytest.mark.asyncio
async def test_oauth2_form_login(client: AsyncClient):
    """Test OAuth2 form login used by Swagger UI."""
    email = "paralegal@example.com"
    password = "AnotherSecurePassword123"
    full_name = "Alex Senior Paralegal"

    # Register
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )

    # Form login
    form_res = await client.post(
        "/api/v1/auth/login/oauth",
        data={"username": email, "password": password},
    )
    assert form_res.status_code == 200
    data = form_res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
