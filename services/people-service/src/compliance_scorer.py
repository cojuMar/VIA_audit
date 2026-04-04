from __future__ import annotations

import asyncpg

from .background_check_manager import BackgroundCheckManager
from .models import EmployeeComplianceScore
from .policy_manager import PolicyManager
from .training_manager import TrainingManager


class ComplianceScorer:
    def __init__(self) -> None:
        self._policy_mgr = PolicyManager()
        self._training_mgr = TrainingManager()
        self._bgcheck_mgr = BackgroundCheckManager()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _status_from_score(score: float) -> str:
        if score >= 90:
            return "compliant"
        if score >= 70:
            return "at_risk"
        return "non_compliant"

    # ------------------------------------------------------------------
    # Core scoring
    # ------------------------------------------------------------------

    async def score_employee(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        employee: dict,
    ) -> EmployeeComplianceScore:
        emp_id = employee["employee_id"]

        # --- Policy score (40%) ---
        ack_statuses = await self._policy_mgr.get_employee_ack_status(
            pool, tenant_id, emp_id
        )
        required_policies = [s for s in ack_statuses if s["required"]]
        acked_policies = [s for s in required_policies if s["acknowledged"] and not s["is_overdue"]]
        if required_policies:
            policy_score = len(acked_policies) / len(required_policies) * 100
        else:
            policy_score = 100.0

        # --- Training score (40%) ---
        training_statuses = await self._training_mgr.get_employee_training_status(
            pool, tenant_id, emp_id
        )
        total_assignments = len(training_statuses)
        completed_non_overdue = sum(
            1
            for t in training_statuses
            if t["status"] == "completed" and not t.get("is_overdue", False)
        )
        if total_assignments:
            training_score = completed_non_overdue / total_assignments * 100
        else:
            training_score = 100.0

        # --- Background check score (20%) ---
        bg_status = await self._bgcheck_mgr.get_compliance_status(
            pool, tenant_id, emp_id
        )
        bg_score = bg_status["score_contribution"] * 100

        # --- Overall ---
        overall = policy_score * 0.4 + training_score * 0.4 + bg_score * 0.2
        overall = round(overall, 1)

        # --- Open items ---
        open_items = (
            sum(1 for s in required_policies if s["is_overdue"] or not s["acknowledged"])
            + sum(1 for t in training_statuses if t["status"] in ("assigned", "in_progress", "overdue"))
            + (0 if bg_status["has_valid_check"] else 1)
        )

        details = {
            "policy": {
                "required": len(required_policies),
                "acknowledged": len(acked_policies),
                "overdue": [s["policy_id"] for s in required_policies if s["is_overdue"]],
            },
            "training": {
                "total_assignments": total_assignments,
                "completed": completed_non_overdue,
                "overdue_assignments": [
                    t["assignment_id"]
                    for t in training_statuses
                    if t.get("is_overdue") or t["status"] == "overdue"
                ],
            },
            "background_check": {
                "has_valid_check": bg_status["has_valid_check"],
                "score_contribution": bg_status["score_contribution"],
            },
        }

        return EmployeeComplianceScore(
            employee_id=emp_id,
            full_name=employee["full_name"],
            overall_score=overall,
            policy_score=round(policy_score, 1),
            training_score=round(training_score, 1),
            background_check_score=round(bg_score, 1),
            status=self._status_from_score(overall),
            open_items=open_items,
            details=details,
        )

    async def score_all_employees(
        self, pool: asyncpg.Pool, tenant_id: str
    ) -> list[EmployeeComplianceScore]:
        from .employee_manager import EmployeeManager

        emp_mgr = EmployeeManager()
        employees = await emp_mgr.list_active(pool, tenant_id)
        scores = []
        for emp in employees:
            score = await self.score_employee(pool, tenant_id, emp)
            scores.append(score)
        return scores

    async def get_org_compliance_summary(
        self, pool: asyncpg.Pool, tenant_id: str
    ) -> dict:
        scores = await self.score_all_employees(pool, tenant_id)
        if not scores:
            return {
                "overall_score": 0.0,
                "compliant_count": 0,
                "at_risk_count": 0,
                "non_compliant_count": 0,
                "total_employees": 0,
                "compliance_rate_pct": 0.0,
                "by_department": [],
                "top_issues": [],
            }

        overall_score = round(sum(s.overall_score for s in scores) / len(scores), 1)
        compliant = sum(1 for s in scores if s.status == "compliant")
        at_risk = sum(1 for s in scores if s.status == "at_risk")
        non_compliant = sum(1 for s in scores if s.status == "non_compliant")
        compliance_rate = round(compliant / len(scores) * 100, 1)

        # By department — we need to fetch department data
        from .employee_manager import EmployeeManager

        emp_mgr = EmployeeManager()
        employees = await emp_mgr.list_active(pool, tenant_id)
        emp_dept_map = {e["employee_id"]: e.get("department") for e in employees}

        dept_buckets: dict[str, list[float]] = {}
        for score in scores:
            dept = emp_dept_map.get(score.employee_id) or "Unknown"
            dept_buckets.setdefault(dept, []).append(score.overall_score)

        by_department = [
            {
                "dept": dept,
                "score": round(sum(v) / len(v), 1),
                "employee_count": len(v),
            }
            for dept, v in sorted(dept_buckets.items())
        ]

        # Top issues
        overdue_policies = sum(
            len(s.details["policy"]["overdue"]) for s in scores
        )
        overdue_training = sum(
            len(s.details["training"]["overdue_assignments"]) for s in scores
        )
        no_bg_check = sum(
            1 for s in scores if not s.details["background_check"]["has_valid_check"]
        )

        top_issues = sorted(
            [
                {
                    "issue_type": "overdue_policy_acknowledgment",
                    "count": overdue_policies,
                    "description": "Employees with overdue policy acknowledgments",
                },
                {
                    "issue_type": "overdue_training",
                    "count": overdue_training,
                    "description": "Overdue training assignments",
                },
                {
                    "issue_type": "missing_background_check",
                    "count": no_bg_check,
                    "description": "Employees without a valid background check",
                },
            ],
            key=lambda x: x["count"],
            reverse=True,
        )

        return {
            "overall_score": overall_score,
            "compliant_count": compliant,
            "at_risk_count": at_risk,
            "non_compliant_count": non_compliant,
            "total_employees": len(scores),
            "compliance_rate_pct": compliance_rate,
            "by_department": by_department,
            "top_issues": top_issues,
        }
