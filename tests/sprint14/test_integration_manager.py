"""Sprint 14 — IntegrationManager unit tests."""
import sys
import os
import json

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "../../services/integration-service"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pool_conn():
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool, mock_conn


def make_encryption():
    from src.encryption import TokenEncryption
    return TokenEncryption("test-key-for-tests")


TENANT = "00000000-0000-0000-0000-000000000014"
INTEGRATION_ID = "aaaa1400-0000-0000-0000-000000000001"
CONNECTOR_ID = "bbbb1400-0000-0000-0000-000000000001"


def _make_connector_row(auth_type="api_key"):
    row = MagicMock()
    row.__getitem__ = lambda self, key: (
        CONNECTOR_ID if key == "id" else auth_type
    )
    return row


def _make_integration_row(**kwargs):
    """Return a MagicMock that looks like an asyncpg Record."""
    defaults = {
        "id": INTEGRATION_ID,
        "tenant_id": TENANT,
        "connector_id": CONNECTOR_ID,
        "integration_name": "Test Integration",
        "auth_config": json.dumps({}),
        "field_mappings": json.dumps({}),
        "sync_schedule": "0 */6 * * *",
        "webhook_secret": None,
        "status": "pending",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    defaults.update(kwargs)
    row = MagicMock()
    row.__iter__ = lambda self: iter(defaults.items())
    row.keys = MagicMock(return_value=list(defaults.keys()))
    row.__getitem__ = lambda self, key: defaults[key]
    # dict(row) behaviour — asyncpg Records support this via mapping protocol
    row._data = defaults
    return row


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestIntegrationManager:

    @pytest.mark.asyncio
    async def test_create_integration_looks_up_connector(self):
        """create() must call fetchrow to look up the connector by key."""
        from src.integration_manager import IntegrationManager
        from src.models import IntegrationCreate

        pool, conn = make_pool_conn()
        enc = make_encryption()

        connector_row = _make_connector_row(auth_type="api_key")
        conn.fetchrow = AsyncMock(side_effect=[
            connector_row,                          # connector lookup
            _make_integration_row(),                # INSERT RETURNING
        ])

        mgr = IntegrationManager()
        data = IntegrationCreate(
            connector_key="workday",
            integration_name="Workday HR",
        )

        with patch("src.integration_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)
            await mgr.create(pool, TENANT, data, enc)

        # The first fetchrow call must include connector_key lookup
        first_call_args = conn.fetchrow.call_args_list[0]
        assert "connector_definitions" in first_call_args[0][0]

    @pytest.mark.asyncio
    async def test_create_encrypts_api_key_in_auth_config(self):
        """api_key in auth_config must be stored encrypted, not plaintext."""
        from src.integration_manager import IntegrationManager
        from src.models import IntegrationCreate

        pool, conn = make_pool_conn()
        enc = make_encryption()
        plaintext_key = "sk-secret"

        connector_row = _make_connector_row(auth_type="api_key")
        captured = {}

        async def fake_fetchrow(sql, *args):
            if "connector_definitions" in sql:
                return connector_row
            # Capture the auth_config argument (4th positional arg after tenant, connector_id, name)
            # INSERT call: $4 = auth_config (json string)
            for i, arg in enumerate(args):
                if isinstance(arg, str) and "api_key" in arg:
                    captured["stored_auth"] = json.loads(arg)
            return _make_integration_row()

        conn.fetchrow = fake_fetchrow

        mgr = IntegrationManager()
        data = IntegrationCreate(
            connector_key="workday",
            integration_name="Workday HR",
            auth_config={"api_key": plaintext_key},
        )

        with patch("src.integration_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)
            await mgr.create(pool, TENANT, data, enc)

        stored = captured.get("stored_auth", {})
        assert stored.get("api_key") != plaintext_key, (
            "api_key must be stored encrypted, not as plaintext"
        )

    @pytest.mark.asyncio
    async def test_create_encrypts_token_field(self):
        """access_token in auth_config must be stored encrypted."""
        from src.integration_manager import IntegrationManager
        from src.models import IntegrationCreate

        pool, conn = make_pool_conn()
        enc = make_encryption()
        plaintext_token = "tok-xyz"

        connector_row = _make_connector_row(auth_type="oauth2")
        captured = {}

        async def fake_fetchrow(sql, *args):
            if "connector_definitions" in sql:
                return connector_row
            for arg in args:
                if isinstance(arg, str) and "access_token" in arg:
                    captured["stored_auth"] = json.loads(arg)
            return _make_integration_row()

        conn.fetchrow = fake_fetchrow

        mgr = IntegrationManager()
        data = IntegrationCreate(
            connector_key="salesforce",
            integration_name="Salesforce",
            auth_config={"access_token": plaintext_token},
        )

        with patch("src.integration_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)
            await mgr.create(pool, TENANT, data, enc)

        stored = captured.get("stored_auth", {})
        assert stored.get("access_token") != plaintext_token

    @pytest.mark.asyncio
    async def test_create_does_not_encrypt_non_sensitive_fields(self):
        """base_url (non-sensitive) must be stored as-is, unencrypted."""
        from src.integration_manager import IntegrationManager
        from src.models import IntegrationCreate

        pool, conn = make_pool_conn()
        enc = make_encryption()
        base_url = "https://api.example.com"

        connector_row = _make_connector_row(auth_type="api_key")
        captured = {}

        async def fake_fetchrow(sql, *args):
            if "connector_definitions" in sql:
                return connector_row
            for arg in args:
                if isinstance(arg, str) and "base_url" in arg:
                    captured["stored_auth"] = json.loads(arg)
            return _make_integration_row()

        conn.fetchrow = fake_fetchrow

        mgr = IntegrationManager()
        data = IntegrationCreate(
            connector_key="workday",
            integration_name="Workday",
            auth_config={"base_url": base_url},
        )

        with patch("src.integration_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)
            await mgr.create(pool, TENANT, data, enc)

        stored = captured.get("stored_auth", {})
        assert stored.get("base_url") == base_url, (
            "Non-sensitive field base_url must not be encrypted"
        )

    @pytest.mark.asyncio
    async def test_create_generates_webhook_secret_for_webhook_auth(self):
        """When connector auth_type='webhook', webhook_secret must be populated."""
        from src.integration_manager import IntegrationManager
        from src.models import IntegrationCreate

        pool, conn = make_pool_conn()
        enc = make_encryption()

        connector_row = _make_connector_row(auth_type="webhook")
        captured_secret = {}

        async def fake_fetchrow(sql, *args):
            if "connector_definitions" in sql:
                return connector_row
            # webhook_secret is 7th positional arg ($7 in INSERT)
            if len(args) >= 7:
                captured_secret["value"] = args[6]
            return _make_integration_row(webhook_secret="some-secret")

        conn.fetchrow = fake_fetchrow

        mgr = IntegrationManager()
        data = IntegrationCreate(
            connector_key="github",
            integration_name="GitHub Webhook",
        )

        with patch("src.integration_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)
            await mgr.create(pool, TENANT, data, enc)

        assert captured_secret.get("value") is not None, (
            "webhook_secret must be populated for webhook auth_type"
        )

    @pytest.mark.asyncio
    async def test_list_integrations_returns_list(self):
        """list() must return a Python list, even for multiple rows."""
        from src.integration_manager import IntegrationManager

        pool, conn = make_pool_conn()

        row1 = dict(
            id="id-1", tenant_id=TENANT, connector_id=CONNECTOR_ID,
            integration_name="Int A", auth_config=json.dumps({}),
            field_mappings=json.dumps({}), sync_schedule="0 */6 * * *",
            webhook_secret=None, status="active",
            connector_key="workday", display_name="Workday",
            category="hris", auth_type="api_key",
            created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
        )
        row2 = dict(
            id="id-2", tenant_id=TENANT, connector_id=CONNECTOR_ID,
            integration_name="Int B", auth_config=json.dumps({"api_key": "enc-val"}),
            field_mappings=json.dumps({}), sync_schedule="0 0 * * *",
            webhook_secret=None, status="active",
            connector_key="salesforce", display_name="Salesforce",
            category="crm", auth_type="oauth2",
            created_at="2026-01-02T00:00:00Z", updated_at="2026-01-02T00:00:00Z",
        )
        conn.fetch = AsyncMock(return_value=[row1, row2])

        mgr = IntegrationManager()

        with patch("src.integration_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await mgr.list(pool, TENANT)

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_integration_returns_none_for_missing(self):
        """get() must return None when fetchrow returns None."""
        from src.integration_manager import IntegrationManager

        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=None)

        mgr = IntegrationManager()

        with patch("src.integration_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await mgr.get(pool, TENANT, "nonexistent-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_pause_updates_status(self):
        """pause() must issue UPDATE with status='paused'."""
        from src.integration_manager import IntegrationManager

        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=_make_integration_row(
            status="paused", auth_config=json.dumps({}), field_mappings=json.dumps({})
        ))

        mgr = IntegrationManager()

        with patch("src.integration_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)
            await mgr.pause(pool, TENANT, INTEGRATION_ID)

        sql_used = conn.fetchrow.call_args[0][0]
        assert "UPDATE" in sql_used
        assert "paused" in conn.fetchrow.call_args[0]

    @pytest.mark.asyncio
    async def test_resume_updates_status(self):
        """resume() must issue UPDATE with status='active'."""
        from src.integration_manager import IntegrationManager

        pool, conn = make_pool_conn()
        conn.fetchrow = AsyncMock(return_value=_make_integration_row(
            status="active", auth_config=json.dumps({}), field_mappings=json.dumps({})
        ))

        mgr = IntegrationManager()

        with patch("src.integration_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)
            await mgr.resume(pool, TENANT, INTEGRATION_ID)

        sql_used = conn.fetchrow.call_args[0][0]
        assert "UPDATE" in sql_used
        assert "active" in conn.fetchrow.call_args[0]

    @pytest.mark.asyncio
    async def test_store_oauth_token_encrypts_access_token(self):
        """store_oauth_token() must store an encrypted, not plaintext, access token."""
        from src.integration_manager import IntegrationManager
        from src.models import OAuthTokenCreate

        pool, conn = make_pool_conn()
        enc = make_encryption()
        plaintext_access = "ya29.a0AfH6SM"

        integration_id_row = MagicMock()
        integration_id_row.__bool__ = lambda self: True
        integration_id_row.__str__ = lambda self: INTEGRATION_ID

        conn.fetchval = AsyncMock(return_value=INTEGRATION_ID)
        conn.execute = AsyncMock()

        captured_args = {}

        async def fake_fetchrow(sql, *args):
            # Capture what is being stored for access_token_enc
            if "oauth_tokens" in sql:
                captured_args["args"] = args
                result = MagicMock()
                result.__iter__ = lambda self: iter({
                    "id": "tok-id",
                    "integration_id": INTEGRATION_ID,
                    "tenant_id": TENANT,
                    "access_token_enc": args[2] if len(args) > 2 else "",
                    "refresh_token_enc": None,
                    "token_type": "Bearer",
                    "expires_at": None,
                    "scope": None,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }.items())
                return result
            return None

        conn.fetchrow = fake_fetchrow

        mgr = IntegrationManager()
        token = OAuthTokenCreate(
            access_token=plaintext_access,
            token_type="Bearer",
        )

        with patch("src.integration_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)
            await mgr.store_oauth_token(pool, TENANT, INTEGRATION_ID, token, enc)

        stored_access = captured_args["args"][2]
        assert stored_access != plaintext_access, (
            "access_token must be stored encrypted, not as plaintext"
        )
        # Must be decryptable
        assert enc.decrypt(stored_access) == plaintext_access

    @pytest.mark.asyncio
    async def test_store_oauth_token_upserts(self):
        """store_oauth_token() SQL must contain ON CONFLICT clause for upsert."""
        from src.integration_manager import IntegrationManager
        from src.models import OAuthTokenCreate

        pool, conn = make_pool_conn()
        enc = make_encryption()

        conn.fetchval = AsyncMock(return_value=INTEGRATION_ID)
        conn.execute = AsyncMock()

        captured_sql = {}

        async def fake_fetchrow(sql, *args):
            if "oauth_tokens" in sql:
                captured_sql["sql"] = sql
                result = MagicMock()
                result.__iter__ = lambda self: iter({
                    "id": "tok-id",
                    "integration_id": INTEGRATION_ID,
                    "tenant_id": TENANT,
                    "access_token_enc": "enc-val",
                    "refresh_token_enc": None,
                    "token_type": "Bearer",
                    "expires_at": None,
                    "scope": None,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }.items())
                return result
            return None

        conn.fetchrow = fake_fetchrow

        mgr = IntegrationManager()
        token = OAuthTokenCreate(access_token="tok-abc")

        with patch("src.integration_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)
            await mgr.store_oauth_token(pool, TENANT, INTEGRATION_ID, token, enc)

        sql = captured_sql.get("sql", "")
        assert "ON CONFLICT" in sql, (
            "store_oauth_token SQL must use ON CONFLICT for upsert semantics"
        )

    @pytest.mark.asyncio
    async def test_get_integration_summary_structure(self):
        """get_integration_summary() must return dict with required keys."""
        from src.integration_manager import IntegrationManager

        pool, conn = make_pool_conn()

        conn.fetchval = AsyncMock(side_effect=[
            5,   # total integrations
            3,   # last_sync_errors
        ])
        conn.fetch = AsyncMock(side_effect=[
            [{"status": "active", "cnt": 3}, {"status": "paused", "cnt": 2}],  # by_status
            [{"category": "hris", "cnt": 2}, {"category": "crm", "cnt": 3}],   # by_category
        ])

        mgr = IntegrationManager()

        with patch("src.integration_manager.tenant_conn") as mock_tc:
            mock_tc.return_value.__aenter__ = AsyncMock(return_value=conn)
            mock_tc.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await mgr.get_integration_summary(pool, TENANT)

        assert "total" in result
        assert "by_status" in result
        assert "by_category" in result
        assert "last_sync_errors" in result
        assert isinstance(result["by_status"], dict)
        assert isinstance(result["by_category"], dict)
