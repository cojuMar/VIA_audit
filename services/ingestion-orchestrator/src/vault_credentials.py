"""
Vault credential loader for connectors.

Loads connector credentials at runtime from HashiCorp Vault KV v2.
Credentials are never cached in memory beyond the duration of a single poll —
each fetch_incremental call receives freshly loaded credentials.

Vault path convention:
  secret/aegis/connectors/{tenant_id}/{connector_id}

Required Vault secret keys (subset used per connector type):
  api_key, oauth_access_token, oauth_refresh_token,
  client_id, client_secret, extra (JSON object)
"""

import asyncio
import json
import logging

import hvac

from .config import settings
from .connector_base import ConnectorCredentials

logger = logging.getLogger(__name__)


class ConnectorVaultLoader:
    """
    Thin async wrapper around the hvac synchronous client.

    All hvac calls are dispatched to the default thread-pool executor so they
    do not block the asyncio event loop.
    """

    def __init__(self):
        self._client = hvac.Client(
            url=settings.vault_addr,
            token=settings.vault_token,
        )

    async def load_credentials(self, vault_path: str) -> ConnectorCredentials:
        """
        Loads connector credentials from Vault KV v2.

        Parameters
        ----------
        vault_path:
            Path within the 'secret' mount point, e.g.
            'aegis/connectors/{tenant_id}/{connector_id}'.

        Returns
        -------
        ConnectorCredentials populated from the Vault secret data.
        """
        loop = asyncio.get_event_loop()

        def _read():
            return self._client.secrets.kv.v2.read_secret_version(
                path=vault_path,
                mount_point="secret",
            )

        secret = await loop.run_in_executor(None, _read)
        data: dict = secret["data"]["data"]

        extra = data.get("extra", {})
        if isinstance(extra, str):
            # Vault may store the extra blob as a JSON string
            try:
                extra = json.loads(extra)
            except json.JSONDecodeError:
                logger.warning(
                    "vault_credentials: 'extra' field is not valid JSON for path %s",
                    vault_path,
                )
                extra = {}

        return ConnectorCredentials(
            api_key=data.get("api_key"),
            oauth_access_token=data.get("oauth_access_token"),
            oauth_refresh_token=data.get("oauth_refresh_token"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            extra=extra,
        )

    async def update_tokens(
        self,
        vault_path: str,
        access_token: str,
        refresh_token: str,
    ) -> None:
        """
        Persists refreshed OAuth2 tokens back to Vault using KV v2 patch
        (only the specified keys are updated; other keys are preserved).

        Called after a successful token refresh so the next poll uses the
        new tokens.
        """
        loop = asyncio.get_event_loop()

        def _write():
            return self._client.secrets.kv.v2.patch(
                path=vault_path,
                secret={
                    "oauth_access_token": access_token,
                    "oauth_refresh_token": refresh_token,
                },
                mount_point="secret",
            )

        await loop.run_in_executor(None, _write)
        logger.debug("vault_credentials: updated tokens at %s", vault_path)
