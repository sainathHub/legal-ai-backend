import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cases_and_threads_lifecycle(client: AsyncClient):
    """Test creating projects (cases), adding threads (chat sessions), retrieving, updating, and cascade deleting."""
    # 1. Register lawyer user
    email = "advocate.sharma@example.com"
    password = "StrongPassword999"
    full_name = "Advocate R. K. Sharma"

    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name, "bar_council_id": "MAH/999/2018"},
    )
    login_res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Project (Case)
    project_payload = {
        "title": "State vs. Reliance (138 NI Act)",
        "description": "Negotiable Instruments Act case regarding cheque dishonor and evidence submission.",
    }
    create_proj_res = await client.post("/api/v1/projects/", json=project_payload, headers=headers)
    assert create_proj_res.status_code == 201
    project = create_proj_res.json()
    project_id = project["id"]
    assert project["title"] == project_payload["title"]
    assert project["description"] == project_payload["description"]

    # 3. List user's projects
    list_res = await client.get("/api/v1/projects/", headers=headers)
    assert list_res.status_code == 200
    projects = list_res.json()
    assert len(projects) == 1
    assert projects[0]["id"] == project_id

    # 4. Create Threads under the Case Project
    thread1_payload = {"title": "Drafting Bail Application"}
    thread2_payload = {"title": "Cross-Examination Prep"}

    t1_res = await client.post(f"/api/v1/projects/{project_id}/threads", json=thread1_payload, headers=headers)
    assert t1_res.status_code == 201
    t1 = t1_res.json()
    assert t1["title"] == "Drafting Bail Application"
    thread1_id = t1["id"]

    t2_res = await client.post(f"/api/v1/projects/{project_id}/threads", json=thread2_payload, headers=headers)
    assert t2_res.status_code == 201
    assert t2_res.json()["title"] == "Cross-Examination Prep"

    # 5. List Threads for the Project
    threads_res = await client.get(f"/api/v1/projects/{project_id}/threads", headers=headers)
    assert threads_res.status_code == 200
    threads = threads_res.json()
    assert len(threads) == 2

    # 6. Retrieve Project Detail (includes threads list)
    detail_res = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == project_id
    assert len(detail["threads"]) == 2

    # 7. Update Thread title
    update_thread_res = await client.patch(
        f"/api/v1/threads/{thread1_id}",
        json={"title": "Anticipatory Bail Application Draft Final"},
        headers=headers,
    )
    assert update_thread_res.status_code == 200
    assert update_thread_res.json()["title"] == "Anticipatory Bail Application Draft Final"

    # 8. Delete Single Thread
    del_t1 = await client.delete(f"/api/v1/threads/{thread1_id}", headers=headers)
    assert del_t1.status_code == 204

    # Verify 1 thread remains
    threads_res_after = await client.get(f"/api/v1/projects/{project_id}/threads", headers=headers)
    assert len(threads_res_after.json()) == 1

    # 9. Delete Case Project (Cascade deletes remaining threads)
    del_proj = await client.delete(f"/api/v1/projects/{project_id}", headers=headers)
    assert del_proj.status_code == 204

    # Verify project is gone
    get_del_proj = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert get_del_proj.status_code == 404


@pytest.mark.asyncio
async def test_project_isolation_between_users(client: AsyncClient):
    """Ensure user A cannot access or modify user B's cases and threads."""
    # User A
    await client.post(
        "/api/v1/auth/register",
        json={"email": "usera@example.com", "password": "Password123!", "full_name": "Lawyer A"},
    )
    login_a = await client.post("/api/v1/auth/login", json={"email": "usera@example.com", "password": "Password123!"})
    headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}

    # User B
    await client.post(
        "/api/v1/auth/register",
        json={"email": "userb@example.com", "password": "Password123!", "full_name": "Lawyer B"},
    )
    login_b = await client.post("/api/v1/auth/login", json={"email": "userb@example.com", "password": "Password123!"})
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    # User A creates a case
    proj_a = await client.post(
        "/api/v1/projects/",
        json={"title": "Confidential Corporate Case"},
        headers=headers_a,
    )
    proj_a_id = proj_a.json()["id"]

    # User B attempts to access User A's case
    b_access = await client.get(f"/api/v1/projects/{proj_a_id}", headers=headers_b)
    assert b_access.status_code == 404

    # User B attempts to create thread in User A's case
    b_thread = await client.post(
        f"/api/v1/projects/{proj_a_id}/threads",
        json={"title": "Unauthorized Thread"},
        headers=headers_b,
    )
    assert b_thread.status_code == 404
