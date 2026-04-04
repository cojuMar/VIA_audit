from collections import defaultdict

import numpy as np
from scipy import stats

from .models import MonitoringFinding, PayrollRecord

# Benford's Law expected first-digit frequencies
BENFORD_EXPECTED = {
    1: 0.301,
    2: 0.176,
    3: 0.125,
    4: 0.097,
    5: 0.079,
    6: 0.067,
    7: 0.058,
    8: 0.051,
    9: 0.046,
}


class PayrollAnalyzer:
    def __init__(self, settings):
        self.zscore_threshold = settings.payroll_outlier_zscore_threshold
        self.iqr_multiplier = settings.payroll_outlier_iqr_multiplier

    def analyze(self, records: list[PayrollRecord]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []
        findings.extend(self._detect_statistical_outliers(records))
        findings.extend(self._detect_benford_deviation(records))
        findings.extend(self._detect_ghost_employees(records))
        return findings

    # ------------------------------------------------------------------
    # Statistical outlier detection (z-score + IQR)
    # ------------------------------------------------------------------

    def _detect_statistical_outliers(self, records: list[PayrollRecord]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []

        # Group records by department; use sentinel key "" for records with no dept
        groups: dict[str, list[PayrollRecord]] = defaultdict(list)
        for rec in records:
            key = rec.department or ""
            groups[key].append(rec)

        for dept, group in groups.items():
            if len(group) < 2:
                continue

            amounts = np.array([r.amount for r in group], dtype=float)
            mean = float(np.mean(amounts))
            std = float(np.std(amounts, ddof=1)) if len(amounts) > 1 else 0.0

            if std == 0:
                continue

            q1 = float(np.percentile(amounts, 25))
            q3 = float(np.percentile(amounts, 75))
            iqr = q3 - q1
            iqr_lower = q1 - self.iqr_multiplier * iqr
            iqr_upper = q3 + self.iqr_multiplier * iqr

            for rec in group:
                z = (rec.amount - mean) / std
                abs_z = abs(z)

                is_z_outlier = abs_z > self.zscore_threshold
                is_iqr_outlier = (rec.amount < iqr_lower or rec.amount > iqr_upper) and iqr > 0

                if not (is_z_outlier or is_iqr_outlier):
                    continue

                # Determine severity
                if abs_z > 4.0 or (is_iqr_outlier and abs_z > self.zscore_threshold):
                    severity = "critical"
                    risk_score = 9.0
                elif abs_z > 3.5:
                    severity = "high"
                    risk_score = 7.5
                else:
                    severity = "medium"
                    risk_score = 5.5

                name = rec.employee_name or rec.employee_id
                title = f"Payroll Outlier: {name} - ${rec.amount:.2f} ({z:+.1f}\u03c3)"
                description = (
                    f"Employee {name} received ${rec.amount:.2f} in period {rec.period}, "
                    f"which is {abs_z:.1f} standard deviations from the department mean "
                    f"of ${mean:.2f} (std=${std:.2f})."
                )

                findings.append(
                    MonitoringFinding(
                        finding_type="payroll_outlier",
                        severity=severity,
                        title=title,
                        description=description,
                        entity_type="employee",
                        entity_id=rec.employee_id,
                        entity_name=rec.employee_name,
                        evidence={
                            "z_score": round(z, 4),
                            "mean": round(mean, 2),
                            "std_dev": round(std, 2),
                            "amount": rec.amount,
                            "department": dept or None,
                            "period": rec.period,
                            "iqr_outlier": is_iqr_outlier,
                            "iqr_lower": round(iqr_lower, 2),
                            "iqr_upper": round(iqr_upper, 2),
                        },
                        risk_score=risk_score,
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # Benford's Law deviation detection
    # ------------------------------------------------------------------

    def _detect_benford_deviation(self, records: list[PayrollRecord]) -> list[MonitoringFinding]:
        if len(records) < 50:
            return []

        # Extract first significant digit for each positive amount
        observed_counts: dict[int, int] = {d: 0 for d in range(1, 10)}
        valid = 0
        for rec in records:
            if rec.amount <= 0:
                continue
            first_digit = int(str(abs(rec.amount)).lstrip("0").replace(".", "")[0])
            if first_digit in observed_counts:
                observed_counts[first_digit] += 1
                valid += 1

        if valid < 50:
            return []

        observed_freq = {d: observed_counts[d] / valid for d in range(1, 10)}
        observed_arr = np.array([observed_counts[d] for d in range(1, 10)], dtype=float)
        expected_arr = np.array([BENFORD_EXPECTED[d] * valid for d in range(1, 10)], dtype=float)

        chi2, p_value = stats.chisquare(observed_arr, f_exp=expected_arr)

        if p_value >= 0.05:
            return []

        if p_value < 0.001:
            severity = "high"
            risk_score = 8.0
        elif p_value < 0.01:
            severity = "medium"
            risk_score = 6.0
        else:
            severity = "low"
            risk_score = 3.0

        title = f"Benford's Law Deviation in Payroll Data (\u03c7\u00b2={chi2:.2f}, p={p_value:.4f})"
        description = (
            f"The distribution of first digits in {valid} payroll amounts significantly deviates "
            f"from Benford's Law (chi-square={chi2:.2f}, p-value={p_value:.4f}). "
            "This may indicate data manipulation or systematic irregularities."
        )

        return [
            MonitoringFinding(
                finding_type="benford_deviation",
                severity=severity,
                title=title,
                description=description,
                entity_type="dataset",
                entity_id=None,
                entity_name="Payroll Dataset",
                evidence={
                    "chi_square": round(float(chi2), 4),
                    "p_value": round(float(p_value), 6),
                    "observed_frequencies": {str(d): round(observed_freq[d], 4) for d in range(1, 10)},
                    "expected_frequencies": {str(d): round(BENFORD_EXPECTED[d], 4) for d in range(1, 10)},
                    "sample_size": valid,
                },
                risk_score=risk_score,
            )
        ]

    # ------------------------------------------------------------------
    # Ghost employee detection
    # ------------------------------------------------------------------

    def _detect_ghost_employees(self, records: list[PayrollRecord]) -> list[MonitoringFinding]:
        findings: list[MonitoringFinding] = []

        # Gather periods and total amounts per employee_id
        emp_periods: dict[str, set[str]] = defaultdict(set)
        emp_amounts: dict[str, list[float]] = defaultdict(list)
        emp_names: dict[str, str | None] = {}

        for rec in records:
            emp_periods[rec.employee_id].add(rec.period)
            emp_amounts[rec.employee_id].append(rec.amount)
            if rec.employee_name:
                emp_names[rec.employee_id] = rec.employee_name

        # Build name -> list[employee_id] map for duplicate name detection
        name_to_ids: dict[str, list[str]] = defaultdict(list)
        for eid, name in emp_names.items():
            if name:
                name_to_ids[name.strip().lower()].append(eid)

        # Flag duplicate names with different IDs
        flagged_as_duplicate: set[str] = set()
        for name, ids in name_to_ids.items():
            if len(ids) > 1:
                for eid in ids:
                    flagged_as_duplicate.add(eid)
                findings.append(
                    MonitoringFinding(
                        finding_type="ghost_employee_duplicate",
                        severity="critical",
                        title=f"Duplicate Employee Name Detected: {emp_names.get(ids[0], name)}",
                        description=(
                            f"Multiple employee IDs share the name '{emp_names.get(ids[0], name)}': "
                            + ", ".join(ids)
                            + ". This may indicate a ghost employee or data entry error."
                        ),
                        entity_type="employee",
                        entity_id=ids[0],
                        entity_name=emp_names.get(ids[0]),
                        evidence={
                            "matching_names": name,
                            "employee_ids": ids,
                            "is_potential_duplicate": True,
                            "periods_paid": {eid: sorted(emp_periods[eid]) for eid in ids},
                        },
                        risk_score=9.5,
                    )
                )

        # Flag single-period employees with high amounts (not already flagged as duplicate)
        all_amounts = [a for amounts in emp_amounts.values() for a in amounts]
        if all_amounts:
            overall_mean = float(np.mean(all_amounts))
            high_threshold = overall_mean * 1.5
        else:
            high_threshold = float("inf")

        for eid, periods in emp_periods.items():
            if eid in flagged_as_duplicate:
                continue
            if len(periods) == 1:
                total = sum(emp_amounts[eid])
                is_high = total > high_threshold

                severity = "medium" if is_high else "low"
                risk_score = 5.5 if is_high else 2.0
                name = emp_names.get(eid)

                findings.append(
                    MonitoringFinding(
                        finding_type="ghost_employee_single_period",
                        severity=severity,
                        title=f"Single-Period Employee: {name or eid} - ${total:.2f}",
                        description=(
                            f"Employee {name or eid} appears in only one payroll period "
                            f"({next(iter(periods))}) with a total payment of ${total:.2f}."
                        ),
                        entity_type="employee",
                        entity_id=eid,
                        entity_name=name,
                        evidence={
                            "periods_paid": sorted(periods),
                            "total_amount": round(total, 2),
                            "is_high_amount": is_high,
                            "is_potential_duplicate": False,
                            "matching_names": [],
                        },
                        risk_score=risk_score,
                    )
                )

        return findings
