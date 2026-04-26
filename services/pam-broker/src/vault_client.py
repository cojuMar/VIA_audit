from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

import hvac
import structlog

logger = structlog.get_logger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


class VaultClient:
    def __init__(self, vault_addr: str, vault_token: str) -> None:
        self._client = hvac.Client(url=vault_addr, token=vault_token)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_sync(self, func, *args, **kwargs) -> Any:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, partial(func, *args, **kwargs))

    def _issue_db_credential_sync(self, vault_role: str, ttl_seconds: int) -> dict:
        response = self._client.secrets.database.generate_credentials(name=vault_role)
        data = response["data"]
        lease_id = response.get("lease_id", "")
        lease_duration = response.get("lease_duration", ttl_seconds)
        return {
            "username": data["username"],
            "password": data["password"],
            "lease_id": lease_id,
            "lease_duration": lease_duration,
        }

    def _issue_pki_certificate_sync(
        self, pki_role: str, common_name: str, ttl_seconds: int
    ) -> dict:
        response = self._client.secrets.pki.generate_certificate(
            name=pki_role,
            common_name=common_name,
            extra_params={"ttl": f"{ttl_seconds}s"},
        )
        data = response["data"]
        return {
            "certificate": data["certificate"],
            "issuing_ca": data["issuing_ca"],
            "serial_number": data["serial_number"],
            "expiration": data["expiration"],
        }

    def _revoke_lease_sync(self, lease_id: str) -> None:
        self._client.sys.revoke_lease(lease_id=lease_id)

    def _check_health_sync(self) -> bool:
        try:
            health = self._client.sys.read_health_status(method="GET")
            # Vault returns 200 when initialized, unsealed, and active
            return health.get("initialized", False) and not health.get("sealed", True)
        except Exception as exc:
            # Health probe — never propagate, but always log the cause so
            # an operator can distinguish "vault unreachable" from "vault sealed".
            logger.warning(
                "vault_health_probe_failed", error=str(exc), exc_info=True
            )
            return False

    # ------------------------------------------------------------------
    # Public async interface
    # ------------------------------------------------------------------

    async def issue_auditor_credential(
        self, tenant_id: str, user_id: str, ttl_seconds: int
    ) -> dict:
        logger.info(
            "issuing_auditor_credential",
            tenant_id=tenant_id,
            user_id=user_id,
            ttl_seconds=ttl_seconds,
        )
        return await self._run_sync(
            self._issue_db_credential_sync, "auditor-db-role", ttl_seconds
        )

    async def issue_infra_credential(
        self, tenant_id: str, user_id: str, ttl_seconds: int
    ) -> dict:
        logger.info(
            "issuing_infra_credential",
            tenant_id=tenant_id,
            user_id=user_id,
            ttl_seconds=ttl_seconds,
        )
        return await self._run_sync(
            self._issue_db_credential_sync, "infra-db-role", ttl_seconds
        )

    async def issue_auditor_certificate(
        self, user_email: str, ttl_seconds: int
    ) -> dict:
        logger.info(
            "issuing_auditor_certificate",
            user_email=user_email,
            ttl_seconds=ttl_seconds,
        )
        return await self._run_sync(
            self._issue_pki_certificate_sync, "auditor-role", user_email, ttl_seconds
        )

    async def issue_infra_certificate(
        self, service_name: str, ttl_seconds: int
    ) -> dict:
        logger.info(
            "issuing_infra_certificate",
            service_name=service_name,
            ttl_seconds=ttl_seconds,
        )
        return await self._run_sync(
            self._issue_pki_certificate_sync, "infra-role", service_name, ttl_seconds
        )

    async def revoke_lease(self, lease_id: str) -> None:
        logger.info("revoking_vault_lease", lease_id=lease_id)
        await self._run_sync(self._revoke_lease_sync, lease_id)

    async def check_health(self) -> bool:
        return await self._run_sync(self._check_health_sync)
