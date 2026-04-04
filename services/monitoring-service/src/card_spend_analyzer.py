from collections import defaultdict
from datetime import datetime

from .models import CardTransaction, MonitoringFinding


def _parse_transaction_date(date_str: str) -> datetime | None:
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


class CardSpendAnalyzer:
    def analyze(self, transactions: list[CardTransaction]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        findings.extend(self._detect_weekend_spend(transactions))
        findings.extend(self._detect_policy_violations(transactions))
        findings.extend(self._detect_round_amounts(transactions))
        findings.extend(self._detect_high_frequency(transactions))
        return findings

    # ------------------------------------------------------------------
    # Weekend spend detection
    # ------------------------------------------------------------------

    def _detect_weekend_spend(self, transactions: list[CardTransaction]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        for txn in transactions:
            dt = _parse_transaction_date(txn.transaction_date)
            if dt is None:
                continue
            # weekday(): Monday=0, Saturday=5, Sunday=6
            if dt.weekday() not in (5, 6):
                continue

            day_name = "Saturday" if dt.weekday() == 5 else "Sunday"
            name = txn.employee_name or txn.employee_id
            findings.append(
                MonitoringFinding(
                    finding_type="weekend_card_spend",
                    severity="medium",
                    title=f"Weekend Transaction: {name} - ${txn.amount:.2f} on {day_name}",
                    description=(
                        f"Employee {name} made a ${txn.amount:.2f} transaction at "
                        f"'{txn.merchant_name}' on a {day_name} ({txn.transaction_date})."
                    ),
                    entity_type="employee",
                    entity_id=txn.employee_id,
                    entity_name=txn.employee_name,
                    evidence={
                        "transaction_id": txn.transaction_id,
                        "merchant_name": txn.merchant_name,
                        "amount": txn.amount,
                        "transaction_date": txn.transaction_date,
                        "day_of_week": day_name,
                        "merchant_category": txn.merchant_category,
                    },
                    risk_score=5.0,
                )
            )
        return findings

    # ------------------------------------------------------------------
    # Policy violation detection (daily spend limit)
    # ------------------------------------------------------------------

    def _detect_policy_violations(self, transactions: list[CardTransaction]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []

        # Group by (employee_id, date_string)
        daily_totals: dict[tuple[str, str], list[CardTransaction]] = defaultdict(list)
        for txn in transactions:
            if txn.policy_limit_daily is None:
                continue
            dt = _parse_transaction_date(txn.transaction_date)
            date_key = dt.strftime("%Y-%m-%d") if dt else txn.transaction_date[:10]
            daily_totals[(txn.employee_id, date_key)].append(txn)

        for (employee_id, date_key), day_txns in daily_totals.items():
            total = sum(t.amount for t in day_txns)
            limit = day_txns[0].policy_limit_daily
            if limit is None or total <= limit:
                continue

            name = day_txns[0].employee_name or employee_id
            overage = total - limit
            findings.append(
                MonitoringFinding(
                    finding_type="card_policy_violation",
                    severity="high",
                    title=f"Daily Spend Limit Exceeded: {name} - ${total:.2f} on {date_key}",
                    description=(
                        f"Employee {name} spent ${total:.2f} on {date_key}, exceeding the "
                        f"daily policy limit of ${limit:.2f} by ${overage:.2f}."
                    ),
                    entity_type="employee",
                    entity_id=employee_id,
                    entity_name=day_txns[0].employee_name,
                    evidence={
                        "date": date_key,
                        "total_spend": round(total, 2),
                        "policy_limit": limit,
                        "overage": round(overage, 2),
                        "transaction_count": len(day_txns),
                        "transaction_ids": [t.transaction_id for t in day_txns],
                    },
                    risk_score=7.5,
                )
            )

        return findings

    # ------------------------------------------------------------------
    # Round amount detection
    # ------------------------------------------------------------------

    def _detect_round_amounts(self, transactions: list[CardTransaction]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        for txn in transactions:
            if txn.amount <= 200:
                continue
            for divisor in [100, 50]:
                if txn.amount % divisor == 0:
                    name = txn.employee_name or txn.employee_id
                    findings.append(
                        MonitoringFinding(
                            finding_type="round_amount_card",
                            severity="low",
                            title=f"Round Amount Transaction: {name} - ${txn.amount:.2f}",
                            description=(
                                f"Employee {name} made a round-amount transaction of ${txn.amount:.2f} "
                                f"at '{txn.merchant_name}' (exact multiple of ${divisor})."
                            ),
                            entity_type="employee",
                            entity_id=txn.employee_id,
                            entity_name=txn.employee_name,
                            evidence={
                                "transaction_id": txn.transaction_id,
                                "amount": txn.amount,
                                "divisor": divisor,
                                "merchant_name": txn.merchant_name,
                                "transaction_date": txn.transaction_date,
                            },
                            risk_score=2.0,
                        )
                    )
                    break  # Report only the largest matching divisor

        return findings

    # ------------------------------------------------------------------
    # High frequency detection (more than 5 transactions in one day)
    # ------------------------------------------------------------------

    def _detect_high_frequency(self, transactions: list[CardTransaction]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []

        daily_txns: dict[tuple[str, str], list[CardTransaction]] = defaultdict(list)
        for txn in transactions:
            dt = _parse_transaction_date(txn.transaction_date)
            date_key = dt.strftime("%Y-%m-%d") if dt else txn.transaction_date[:10]
            daily_txns[(txn.employee_id, date_key)].append(txn)

        for (employee_id, date_key), day_txns in daily_txns.items():
            if len(day_txns) <= 5:
                continue

            name = day_txns[0].employee_name or employee_id
            total = sum(t.amount for t in day_txns)
            findings.append(
                MonitoringFinding(
                    finding_type="high_frequency_card",
                    severity="medium",
                    title=f"High-Frequency Card Use: {name} - {len(day_txns)} transactions on {date_key}",
                    description=(
                        f"Employee {name} made {len(day_txns)} card transactions on {date_key}, "
                        f"totalling ${total:.2f}. More than 5 transactions in a single day may "
                        "indicate misuse or policy violation."
                    ),
                    entity_type="employee",
                    entity_id=employee_id,
                    entity_name=day_txns[0].employee_name,
                    evidence={
                        "date": date_key,
                        "transaction_count": len(day_txns),
                        "total_amount": round(total, 2),
                        "transaction_ids": [t.transaction_id for t in day_txns],
                        "merchants": list({t.merchant_name for t in day_txns}),
                    },
                    risk_score=5.5,
                )
            )

        return findings
