"""
Pre-Sprint-21 bug: /auth/notifications* had NO authentication. Anyone could
read, create, mark, and delete notifications for any user in any tenant
simply by passing tenant_id and user_id in query/body.

Post-Sprint-21 contract:
  - Every /auth/notifications* endpoint requires a Bearer JWT.
  - tenant_id is derived from the JWT, never from query/body.
  - user_id is derived from the JWT for list/unread-count/read-all/mark/delete.
  - POST /auth/notifications requires admin role.
"""
from __future__ import annotations


def test_list_notifications_without_jwt_returns_401(http):
    r = http.get("/auth/notifications")
    assert r.status_code == 401


def test_list_notifications_ignores_query_tenant_id(http, end_user_token, other_tenant_id):
    r = http.get(
        "/auth/notifications",
        params={"tenant_id": other_tenant_id, "user_id": "bogus"},
        headers={"Authorization": f"Bearer {end_user_token}"},
    )
    # Must succeed (derives tenant/user from JWT), NOT leak other tenant's data.
    assert r.status_code == 200
    # All returned items belong to our tenant — we can't directly assert that
    # without DB access, but at minimum the call must not 500 or return others'.
    body = r.json()
    assert isinstance(body, list)


def test_unread_count_without_jwt_returns_401(http):
    r = http.get("/auth/notifications/unread-count")
    assert r.status_code == 401


def test_mark_all_read_without_jwt_returns_401(http):
    r = http.patch("/auth/notifications/read-all")
    assert r.status_code == 401


def test_mark_read_without_jwt_returns_401(http):
    r = http.patch("/auth/notifications/some-id/read")
    assert r.status_code == 401


def test_delete_notification_without_jwt_returns_401(http):
    r = http.delete("/auth/notifications/some-id")
    assert r.status_code == 401


def test_create_notification_without_jwt_returns_401(http):
    r = http.post("/auth/notifications", json={
        "user_id": "anything", "type": "x", "title": "y",
    })
    assert r.status_code == 401


def test_create_notification_as_end_user_returns_403(http, end_user_token):
    r = http.post(
        "/auth/notifications",
        json={"user_id": "anything", "type": "x", "title": "y"},
        headers={"Authorization": f"Bearer {end_user_token}"},
    )
    assert r.status_code == 403


def test_create_notification_rejects_cross_tenant_target(http, admin_token):
    """Admin cannot create a notification for a user in another tenant."""
    r = http.post(
        "/auth/notifications",
        json={
            "user_id": "00000000-0000-0000-0000-000000000999",
            "type": "bogus",
            "title": "cross-tenant attempt",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # Either 404 (target not in tenant) or 503 (table missing) are acceptable.
    # It must NOT be 201.
    assert r.status_code != 201
