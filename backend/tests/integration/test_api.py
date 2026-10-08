"""API contract tests: authentication, ownership isolation and validation."""

from __future__ import annotations

from httpx import AsyncClient


class TestHealthAndCatalogue:
    async def test_health_reports_dependencies(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["database"] == "connected"

    async def test_catalogue_is_public_and_complete(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/catalog")

        assert response.status_code == 200
        body = response.json()
        assert len(body["frontend"]) == 3
        assert len(body["backend"]) == 3
        assert [option["key"] for option in body["database"]] == ["mongodb", "sqlite"]
        assert len(body["agents"]) == 12

    async def test_root_advertises_the_api(self, client: AsyncClient) -> None:
        response = await client.get("/")
        assert response.status_code == 200
        assert response.json()["name"] == "Aegis AI"


class TestAuthentication:
    async def test_register_returns_user_and_tokens(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "new@aegisai.dev",
                "full_name": "New User",
                "password": "Str0ngPassphrase!",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["user"]["email"] == "new@aegisai.dev"
        assert body["tokens"]["token_type"] == "bearer"
        assert "password" not in body["user"]
        assert "password_hash" not in body["user"]

    async def test_duplicate_email_is_rejected(self, client: AsyncClient) -> None:
        payload = {
            "email": "dup@aegisai.dev",
            "full_name": "First",
            "password": "Str0ngPassphrase!",
        }
        assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201

        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 409
        assert response.json()["error"] == "conflict"

    async def test_weak_password_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "weak@aegisai.dev", "full_name": "Weak", "password": "short"},
        )
        assert response.status_code == 422

    async def test_login_round_trip(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "login@aegisai.dev",
                "full_name": "Login User",
                "password": "Str0ngPassphrase!",
            },
        )

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@aegisai.dev", "password": "Str0ngPassphrase!"},
        )
        assert response.status_code == 200
        assert response.json()["user"]["email"] == "login@aegisai.dev"

    async def test_wrong_password_is_rejected(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "wrong@aegisai.dev",
                "full_name": "User",
                "password": "Str0ngPassphrase!",
            },
        )

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "wrong@aegisai.dev", "password": "NotThePassword!"},
        )
        assert response.status_code == 401

    async def test_unknown_email_gives_the_same_error(self, client: AsyncClient) -> None:
        """The response must not reveal whether an address is registered."""
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@aegisai.dev", "password": "Str0ngPassphrase!"},
        )
        assert response.status_code == 401
        assert response.json()["message"] == "Incorrect email address or password."

    async def test_refresh_issues_a_new_pair(self, client: AsyncClient) -> None:
        registered = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "refresh@aegisai.dev",
                "full_name": "User",
                "password": "Str0ngPassphrase!",
            },
        )
        refresh_token = registered.json()["tokens"]["refresh_token"]

        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert response.status_code == 200
        assert response.json()["access_token"]

    async def test_access_token_cannot_be_used_as_a_refresh_token(
        self, client: AsyncClient
    ) -> None:
        registered = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "swap@aegisai.dev",
                "full_name": "User",
                "password": "Str0ngPassphrase!",
            },
        )
        access_token = registered.json()["tokens"]["access_token"]

        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": access_token}
        )
        assert response.status_code == 401

    async def test_protected_route_requires_a_token(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/auth/me")).status_code == 401
        assert (await client.get("/api/v1/projects")).status_code == 401

    async def test_malformed_token_is_rejected(self, client: AsyncClient) -> None:
        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert response.status_code == 401


class TestProjects:
    async def test_create_derives_a_name_and_slug(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(
            "/api/v1/projects",
            json={"idea": "A hospital management system for appointments and records"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"]
        assert body["slug"]
        assert "/" not in body["slug"]

    async def test_short_idea_is_rejected(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post("/api/v1/projects", json={"idea": "app"})
        assert response.status_code == 422

    async def test_list_paginates(self, authed_client: AsyncClient) -> None:
        for index in range(3):
            await authed_client.post(
                "/api/v1/projects",
                json={"idea": f"Project number {index} for inventory management"},
            )

        response = await authed_client.get("/api/v1/projects?limit=2&offset=0")
        body = response.json()

        assert response.status_code == 200
        assert body["total"] == 3
        assert len(body["items"]) == 2

    async def test_search_filters_results(self, authed_client: AsyncClient) -> None:
        await authed_client.post(
            "/api/v1/projects", json={"idea": "A hospital appointment booking system"}
        )
        await authed_client.post(
            "/api/v1/projects", json={"idea": "A restaurant ordering platform"}
        )

        response = await authed_client.get("/api/v1/projects?search=hospital")
        assert response.json()["total"] == 1

    async def test_update_and_delete(self, authed_client: AsyncClient) -> None:
        created = await authed_client.post(
            "/api/v1/projects", json={"idea": "An inventory management system"}
        )
        project_id = created.json()["id"]

        updated = await authed_client.patch(
            f"/api/v1/projects/{project_id}",
            json={"name": "Renamed", "tags": ["inventory"]},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Renamed"

        assert (await authed_client.delete(f"/api/v1/projects/{project_id}")).status_code == 200
        assert (await authed_client.get(f"/api/v1/projects/{project_id}")).status_code == 404

    async def test_stats_reflect_created_projects(self, authed_client: AsyncClient) -> None:
        await authed_client.post(
            "/api/v1/projects", json={"idea": "A customer relationship manager"}
        )

        response = await authed_client.get("/api/v1/projects/stats")
        assert response.status_code == 200
        assert response.json()["total_projects"] == 1


class TestOwnershipIsolation:
    async def test_a_user_cannot_read_another_users_project(
        self, client: AsyncClient
    ) -> None:
        """Ownership is enforced in the query, not merely by obscurity."""
        first = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "owner@aegisai.dev",
                "full_name": "Owner",
                "password": "Str0ngPassphrase!",
            },
        )
        owner_token = first.json()["tokens"]["access_token"]

        created = await client.post(
            "/api/v1/projects",
            json={"idea": "A private financial planning application"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        project_id = created.json()["id"]

        second = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "intruder@aegisai.dev",
                "full_name": "Intruder",
                "password": "Str0ngPassphrase!",
            },
        )
        intruder_headers = {
            "Authorization": f"Bearer {second.json()['tokens']['access_token']}"
        }

        assert (
            await client.get(f"/api/v1/projects/{project_id}", headers=intruder_headers)
        ).status_code == 404
        assert (
            await client.delete(f"/api/v1/projects/{project_id}", headers=intruder_headers)
        ).status_code == 404
        assert (
            await client.get("/api/v1/projects", headers=intruder_headers)
        ).json()["total"] == 0


class TestRunGuards:
    async def test_generation_requires_analysis_first(
        self, authed_client: AsyncClient
    ) -> None:
        created = await authed_client.post(
            "/api/v1/projects", json={"idea": "A task management application"}
        )
        project_id = created.json()["id"]

        response = await authed_client.post(f"/api/v1/projects/{project_id}/runs", json={})

        assert response.status_code == 422
        assert "analyse" in response.json()["message"].lower()

    async def test_unknown_run_is_not_found(self, authed_client: AsyncClient) -> None:
        assert (await authed_client.get("/api/v1/runs/doesnotexist")).status_code == 404

    async def test_download_requires_a_package(self, authed_client: AsyncClient) -> None:
        assert (
            await authed_client.get("/api/v1/runs/doesnotexist/download")
        ).status_code == 404
