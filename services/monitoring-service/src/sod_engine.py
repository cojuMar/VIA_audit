import logging
from collections import defaultdict

import asyncpg

from .models import MonitoringFinding, UserAccessRecord

logger = logging.getLogger(__name__)

# Base risk scores by severity band
_SEVERITY_BASE: dict[str, float] = {
    "critical": 9.5,
    "high": 8.0,
    "medium": 6.0,
    "low": 3.0,
}


def _severity_to_risk(severity: str, extra: int = 0) -> float:
    base = _SEVERITY_BASE.get(severity, 5.0)
    return min(10.0, base + extra * 0.5)


def _role_matches(user_roles: list[str], rule_role: str) -> bool:
    """Case-insensitive substring match: rule_role contained in user role OR vice versa."""
    rule_lower = rule_role.lower()
    for role in user_roles:
        role_lower = role.lower()
        if rule_lower in role_lower or role_lower in rule_lower:
            return True
    return False


class SoDEngine:
    async def analyze(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        users: list[UserAccessRecord],
    ) -> list[dict]:
        # Load all active SoD rules (platform-level, no tenant filter)
        async with pool.acquire() as conn:
            rules = await conn.fetch(
                """
                SELECT id, rule_key, role_a, role_b, description, severity
                FROM sod_rules
                WHERE is_active = TRUE
                """
            )

        if not rules:
            return []

        # Count violations per user for stacking risk score
        user_violation_counts: dict[str, int] = defaultdict(int)
        violations: list[dict] = []

        for user in users:
            combined_roles = list(user.roles) + list(user.permissions)
            user_violations: list[dict] = []

            for rule in rules:
                has_role_a = _role_matches(combined_roles, rule["role_a"])
                has_role_b = _role_matches(combined_roles, rule["role_b"])

                if not (has_role_a and has_role_b):
                    continue

                user_violations.append(
                    {
                        "rule_id": str(rule["id"]),
                        "rule_key": rule["rule_key"],
                        "role_a": rule["role_a"],
                        "role_b": rule["role_b"],
                        "description": rule["description"],
                        "severity": rule["severity"],
                    }
                )

            # Stack risk: each additional violation adds 0.5
            for idx, v in enumerate(user_violations):
                risk_score = _severity_to_risk(v["severity"], idx)
                v["risk_score"] = round(risk_score, 1)

            for v in user_violations:
                violation_record = {
                    "tenant_id": tenant_id,
                    "user_id": user.user_id,
                    "user_name": user.user_name,
                    "user_email": user.user_email,
                    "department": user.department,
                    "rule_id": v["rule_id"],
                    "rule_key": v["rule_key"],
                    "role_a": v["role_a"],
                    "role_b": v["role_b"],
                    "severity": v["severity"],
                    "risk_score": v["risk_score"],
                    "description": v["description"],
                    "user_roles": combined_roles,
                }
                violations.append(violation_record)

        # INSERT all violations (immutable)
        if violations:
            async with pool.acquire() as conn:
                for v in violations:
                    try:
                        await conn.execute(
                            """
                            INSERT INTO sod_violations
                                (tenant_id, user_id, user_name, user_email, department,
                                 rule_id, rule_key, role_a, role_b,
                                 severity, risk_score, description, user_roles)
                            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                            """,
                            v["tenant_id"],
                            v["user_id"],
                            v["user_name"],
                            v["user_email"],
                            v["department"],
                            v["rule_id"],
                            v["rule_key"],
                            v["role_a"],
                            v["role_b"],
                            v["severity"],
                            v["risk_score"],
                            v["description"],
                            v["user_roles"],
                        )
                    except Exception as exc:
                        logger.error("Failed to insert SoD violation: %s", exc)

        return violations

    # ------------------------------------------------------------------
    # Finding conversion helper (for the main endpoint response)
    # ------------------------------------------------------------------

    def violations_to_findings(self, violations: list[dict]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        for v in violations:
            name = v.get("user_name") or v.get("user_id", "unknown")
            findings.append(
                MonitoringFinding(
                    finding_type="sod_violation",
                    severity=v["severity"],
                    title=f"SoD Violation: {name} — {v['role_a']} + {v['role_b']}",
                    description=(
                        f"User {name} holds conflicting roles '{v['role_a']}' and '{v['role_b']}'. "
                        + (v.get("description") or "")
                    ),
                    entity_type="user",
                    entity_id=v.get("user_id"),
                    entity_name=v.get("user_name"),
                    evidence={
                        "rule_key": v["rule_key"],
                        "role_a": v["role_a"],
                        "role_b": v["role_b"],
                        "user_roles": v.get("user_roles", []),
                        "department": v.get("department"),
                    },
                    risk_score=v.get("risk_score"),
                )
            )
        return findings
