"""Wiki authorization API tests."""

from pathlib import Path

import pytest
from httpx import AsyncClient


async def _login_admin(client: AsyncClient) -> None:
    response = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert response.status_code == 200, response.text


async def _create_member(client: AsyncClient, username: str) -> str:
    response = await client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret1"},
    )
    assert response.status_code == 200, response.text
    user_id = response.json()["subject_id"]
    await client.post("/api/auth/logout")
    return str(user_id)


async def _create_feature(client: AsyncClient, slug: str) -> tuple[int, int]:
    await _login_admin(client)
    response = await client.post("/api/features", json={"name": slug, "slug": slug})
    assert response.status_code == 201, response.text
    await client.post("/api/auth/logout")

    tree = await client.get("/api/wiki/tree", params={"feature_id": int(response.json()["id"])})
    assert tree.status_code == 200, tree.text
    return int(response.json()["id"]), int(tree.json()["space"]["id"])


@pytest.mark.asyncio
async def test_anonymous_can_read_wiki_tree_but_cannot_create_nodes(
    client: AsyncClient,
) -> None:
    _feature_id, space_id = await _create_feature(client, "wiki-authz-read")

    tree = await client.get("/api/wiki/tree")
    assert tree.status_code == 200

    created = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Denied"},
    )
    assert created.status_code == 403


@pytest.mark.asyncio
async def test_feature_admin_can_write_only_assigned_feature(client: AsyncClient) -> None:
    feature_id, space_id = await _create_feature(client, "wiki-authz-assigned")
    _other_feature_id, other_space_id = await _create_feature(client, "wiki-authz-other")
    user_id = await _create_member(client, "wiki-feature-admin")

    member_login = await client.post(
        "/api/auth/login",
        json={"username": "wiki-feature-admin", "password": "secret1"},
    )
    assert member_login.status_code == 200, member_login.text
    denied_before_grant = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Denied"},
    )
    assert denied_before_grant.status_code == 403
    await client.post("/api/auth/logout")

    await _login_admin(client)
    granted = await client.post(f"/api/features/{feature_id}/admins", json={"user_id": user_id})
    assert granted.status_code == 201, granted.text
    await client.post("/api/auth/logout")

    login = await client.post(
        "/api/auth/login",
        json={"username": "wiki-feature-admin", "password": "secret1"},
    )
    assert login.status_code == 200, login.text

    allowed = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Allowed"},
    )
    assert allowed.status_code == 201, allowed.text

    denied_other = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": other_space_id,
            "parent_id": None,
            "type": "folder",
            "name": "Other denied",
        },
    )
    assert denied_other.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_write_any_wiki_feature(client: AsyncClient) -> None:
    _feature_id, space_id = await _create_feature(client, "wiki-authz-admin")

    await _login_admin(client)
    response = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": "Admin"},
    )
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_legacy_document_upload_requires_feature_manager(
    client: AsyncClient,
    tmp_path: Path,
) -> None:
    feature_id, _space_id = await _create_feature(client, "wiki-authz-legacy-doc")
    markdown_path = tmp_path / "authz.md"
    markdown_path.write_text("# Authz\n\nLegacy document upload.", encoding="utf-8")

    with markdown_path.open("rb") as file:
        denied = await client.post(
            "/api/documents",
            data={"feature_id": str(feature_id)},
            files={"file": ("authz.md", file, "text/markdown")},
        )
    assert denied.status_code == 403

    user_id = await _create_member(client, "legacy-doc-admin")
    await _login_admin(client)
    granted = await client.post(f"/api/features/{feature_id}/admins", json={"user_id": user_id})
    assert granted.status_code == 201, granted.text
    await client.post("/api/auth/logout")

    member_login = await client.post(
        "/api/auth/login",
        json={"username": "legacy-doc-admin", "password": "secret1"},
    )
    assert member_login.status_code == 200, member_login.text
    with markdown_path.open("rb") as file:
        allowed = await client.post(
            "/api/documents",
            data={"feature_id": str(feature_id)},
            files={"file": ("authz.md", file, "text/markdown")},
        )
    assert allowed.status_code == 201, allowed.text


@pytest.mark.asyncio
async def test_report_mutation_requires_feature_manager(client: AsyncClient) -> None:
    feature_id, _space_id = await _create_feature(client, "wiki-authz-report")

    denied = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "Denied report",
            "body_markdown": "body",
            "metadata": {},
        },
    )
    assert denied.status_code == 403

    user_id = await _create_member(client, "report-feature-admin")
    await _login_admin(client)
    granted = await client.post(f"/api/features/{feature_id}/admins", json={"user_id": user_id})
    assert granted.status_code == 201, granted.text
    await client.post("/api/auth/logout")

    member_login = await client.post(
        "/api/auth/login",
        json={"username": "report-feature-admin", "password": "secret1"},
    )
    assert member_login.status_code == 200, member_login.text
    allowed = await client.post(
        "/api/reports",
        json={
            "feature_id": feature_id,
            "title": "Allowed report",
            "body_markdown": "body",
            "metadata": {},
        },
    )
    assert allowed.status_code == 201, allowed.text


@pytest.mark.asyncio
async def test_feature_skill_mutation_requires_feature_manager(client: AsyncClient) -> None:
    feature_id, _space_id = await _create_feature(client, "wiki-authz-skill")

    denied = await client.post(
        "/api/skills",
        json={
            "name": "denied-feature-skill",
            "scope": "feature",
            "feature_id": feature_id,
            "prompt_template": "Denied.",
        },
    )
    assert denied.status_code == 403

    user_id = await _create_member(client, "skill-feature-admin")
    await _login_admin(client)
    granted = await client.post(f"/api/features/{feature_id}/admins", json={"user_id": user_id})
    assert granted.status_code == 201, granted.text
    await client.post("/api/auth/logout")

    member_login = await client.post(
        "/api/auth/login",
        json={"username": "skill-feature-admin", "password": "secret1"},
    )
    assert member_login.status_code == 200, member_login.text
    created = await client.post(
        "/api/skills",
        json={
            "name": "allowed-feature-skill",
            "scope": "feature",
            "feature_id": feature_id,
            "prompt_template": "Allowed.",
        },
    )
    assert created.status_code == 201, created.text

    updated = await client.patch(
        f"/api/skills/{created.json()['id']}",
        json={"enabled": False},
    )
    assert updated.status_code == 200, updated.text

    deleted = await client.delete(f"/api/skills/{created.json()['id']}")
    assert deleted.status_code == 204, deleted.text
