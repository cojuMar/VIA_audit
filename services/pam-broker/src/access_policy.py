from __future__ import annotations

from .models import ResourceType

# Roles that are permitted to request each resource type
_PERMITTED_ROLES: dict[ResourceType, set[str]] = {
    ResourceType.DATABASE_READONLY: {"auditor", "admin", "firm_partner", "readonly"},
    ResourceType.DATABASE_INFRA: {"admin", "firm_partner"},
    ResourceType.API_READONLY: {"auditor", "admin", "firm_partner", "readonly"},
    ResourceType.BREAK_GLASS: {"admin", "firm_partner"},
}


class AccessPolicy:
    TTL_RULES: dict[ResourceType, dict] = {
        ResourceType.DATABASE_READONLY: {
            "default": 14400,   # 4h
            "max": 28800,       # 8h
            "vault_role": "auditor-db-role",
            "pki_role": "auditor-role",
        },
        ResourceType.DATABASE_INFRA: {
            "default": 300,     # 5m
            "max": 900,         # 15m
            "vault_role": "infra-db-role",
            "pki_role": "infra-role",
        },
        ResourceType.API_READONLY: {
            "default": 14400,
            "max": 28800,
            "vault_role": None,  # JWT-scoped, no DB credential
            "pki_role": None,
        },
        ResourceType.BREAK_GLASS: {
            "default": 900,
            "max": 900,
            "vault_role": "infra-db-role",
            "pki_role": "infra-role",
        },
    }

    def validate_and_cap_ttl(
        self,
        resource_type: ResourceType,
        requested_seconds: int,
        user_role: str,
    ) -> int:
        permitted = _PERMITTED_ROLES.get(resource_type, set())
        if user_role not in permitted:
            raise PermissionError(
                f"Role '{user_role}' is not permitted to request resource type '{resource_type}'"
            )

        rule = self.TTL_RULES[resource_type]
        max_ttl: int = rule["max"]
        return min(requested_seconds, max_ttl)

    def is_break_glass_permitted(self, requester_role: str) -> bool:
        return requester_role in {"admin", "firm_partner"}

    def requires_dual_approval(self, resource_type: ResourceType) -> bool:
        return resource_type == ResourceType.BREAK_GLASS

    def get_vault_roles(
        self, resource_type: ResourceType
    ) -> tuple[str | None, str | None]:
        rule = self.TTL_RULES[resource_type]
        return rule["vault_role"], rule["pki_role"]
