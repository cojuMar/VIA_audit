import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/monitoring-service"))

from unittest.mock import MagicMock

from src.payroll_analyzer import PayrollAnalyzer
from src.models import PayrollRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_settings():
    s = MagicMock()
    s.payroll_outlier_zscore_threshold = 3.0
    s.payroll_outlier_iqr_multiplier = 3.0
    return s


def make_record(employee_id, amount, period="2024-01", department="Engineering", name=None):
    return PayrollRecord(
        employee_id=employee_id,
        employee_name=name or f"Employee {employee_id}",
        department=department,
        amount=amount,
        period=period,
        payment_date=None,
    )


# ---------------------------------------------------------------------------
# TestPayrollAnalyzer
# ---------------------------------------------------------------------------

class TestPayrollAnalyzer:

    def test_no_outliers_in_uniform_data(self):
        """20 records all with amount=5000.0 → 0 statistical outlier findings."""
        analyzer = PayrollAnalyzer(make_settings())
        records = [make_record(f"E{i}", 5000.0) for i in range(20)]
        findings = analyzer._detect_statistical_outliers(records)
        assert len(findings) == 0

    def test_detects_obvious_outlier(self):
        """19 records at 5000.0, one at 150000.0 → finds at least 1 outlier for the 150k record."""
        analyzer = PayrollAnalyzer(make_settings())
        records = [make_record(f"E{i}", 5000.0) for i in range(19)]
        records.append(make_record("E_outlier", 150000.0))
        findings = analyzer._detect_statistical_outliers(records)
        assert len(findings) >= 1
        outlier_ids = [f.entity_id for f in findings]
        assert "E_outlier" in outlier_ids

    def test_outlier_includes_zscore_in_evidence(self):
        """The outlier finding has evidence['z_score'] key."""
        analyzer = PayrollAnalyzer(make_settings())
        records = [make_record(f"E{i}", 5000.0) for i in range(19)]
        records.append(make_record("E_outlier", 150000.0))
        findings = analyzer._detect_statistical_outliers(records)
        assert any(findings), "Expected at least one outlier finding"
        for f in findings:
            if f.entity_id == "E_outlier":
                assert "z_score" in f.evidence, "evidence must contain 'z_score'"
                break

    def test_outlier_severity_critical_for_extreme(self):
        """Amount 10x mean → severity == 'critical' or 'high'."""
        analyzer = PayrollAnalyzer(make_settings())
        # 19 records at 5000, one at 50000 (10x mean ≈ very high z-score)
        records = [make_record(f"E{i}", 5000.0) for i in range(19)]
        records.append(make_record("E_extreme", 100000.0))
        findings = analyzer._detect_statistical_outliers(records)
        extreme_findings = [f for f in findings if f.entity_id == "E_extreme"]
        assert extreme_findings, "Expected a finding for the extreme outlier"
        assert extreme_findings[0].severity in ("critical", "high")

    def test_outlier_groups_by_department(self):
        """Two departments with different mean salaries; outlier detection is per-department."""
        analyzer = PayrollAnalyzer(make_settings())
        # Engineering: mean ~5000, HR: mean ~50000
        eng_records = [make_record(f"ENG{i}", 5000.0, department="Engineering") for i in range(10)]
        hr_records = [make_record(f"HR{i}", 50000.0, department="HR") for i in range(10)]
        # Add a genuine outlier only in Engineering
        eng_records.append(make_record("ENG_out", 100000.0, department="Engineering"))

        all_records = eng_records + hr_records
        findings = analyzer._detect_statistical_outliers(all_records)

        outlier_ids = {f.entity_id for f in findings}
        # ENG_out should be flagged
        assert "ENG_out" in outlier_ids
        # HR records with 50000 should not be flagged (their dept mean is 50000)
        hr_flagged = [f for f in findings if f.entity_id and f.entity_id.startswith("HR")]
        assert len(hr_flagged) == 0, "HR records should not be flagged within their own department"

    def test_benford_skips_small_samples(self):
        """Fewer than 50 records → no benford finding."""
        analyzer = PayrollAnalyzer(make_settings())
        records = [make_record(f"E{i}", 5000.0 + i) for i in range(49)]
        findings = analyzer._detect_benford_deviation(records)
        assert findings == []

    def test_benford_runs_on_large_sample(self):
        """100 records with highly skewed first digits (all starting with 9) → finds benford deviation."""
        analyzer = PayrollAnalyzer(make_settings())
        # All amounts start with digit 9 — strongly violates Benford's Law
        records = [make_record(f"E{i}", 9000.0 + i) for i in range(100)]
        findings = analyzer._detect_benford_deviation(records)
        assert len(findings) >= 1
        assert findings[0].finding_type == "benford_deviation"

    def test_benford_evidence_has_chi_square(self):
        """Benford finding evidence has 'chi_square' and 'p_value' keys."""
        analyzer = PayrollAnalyzer(make_settings())
        records = [make_record(f"E{i}", 9000.0 + i) for i in range(100)]
        findings = analyzer._detect_benford_deviation(records)
        assert findings, "Expected at least one Benford finding"
        evidence = findings[0].evidence
        assert "chi_square" in evidence, "evidence must contain 'chi_square'"
        assert "p_value" in evidence, "evidence must contain 'p_value'"

    def test_ghost_employee_single_period(self):
        """One employee appears only in one of 12 periods → ghost employee finding."""
        analyzer = PayrollAnalyzer(make_settings())
        # 5 regular employees appear in all 12 periods
        records = []
        for month in range(1, 13):
            period = f"2024-{month:02d}"
            for emp in ["E001", "E002", "E003", "E004", "E005"]:
                records.append(make_record(emp, 5000.0, period=period))
        # Ghost employee appears only in period 2024-06
        records.append(make_record("GHOST", 5000.0, period="2024-06"))

        findings = analyzer._detect_ghost_employees(records)
        ghost_findings = [f for f in findings if f.entity_id == "GHOST"]
        assert ghost_findings, "Expected a ghost employee finding for single-period employee"
        assert ghost_findings[0].finding_type == "ghost_employee_single_period"

    def test_ghost_employee_duplicate_name(self):
        """Two records with same name but different employee_id → duplicate finding."""
        analyzer = PayrollAnalyzer(make_settings())
        records = [
            make_record("E001", 5000.0, name="John Smith"),
            make_record("E999", 5000.0, name="John Smith"),
        ]
        findings = analyzer._detect_ghost_employees(records)
        dup_findings = [f for f in findings if f.finding_type == "ghost_employee_duplicate"]
        assert dup_findings, "Expected a duplicate name finding"

    def test_empty_records_returns_empty(self):
        """[] → []."""
        analyzer = PayrollAnalyzer(make_settings())
        findings = analyzer.analyze([])
        assert findings == []

    def test_single_record_no_outlier(self):
        """[one record] → no statistical outlier (can't compute std from 1 sample)."""
        analyzer = PayrollAnalyzer(make_settings())
        records = [make_record("E001", 5000.0)]
        findings = analyzer._detect_statistical_outliers(records)
        assert findings == []

    def test_analyze_returns_all_finding_types(self):
        """Call analyze() with data that triggers all 3 detectors."""
        analyzer = PayrollAnalyzer(make_settings())

        # Statistical outlier: 19 at 5000, one extreme
        records = [make_record(f"E{i}", 5000.0) for i in range(19)]
        records.append(make_record("E_outlier", 150000.0))

        # Benford deviation: 80 more records all starting with 9
        for i in range(80):
            records.append(make_record(f"B{i}", 9000.0 + i, period="2024-02"))

        # Ghost employee / duplicate name
        records.append(make_record("DUP1", 4000.0, name="Ghost User"))
        records.append(make_record("DUP2", 4000.0, name="Ghost User"))

        findings = analyzer.analyze(records)
        types_found = {f.finding_type for f in findings}

        assert "payroll_outlier" in types_found, "Expected payroll_outlier finding"
        assert "benford_deviation" in types_found, "Expected benford_deviation finding"
        assert "ghost_employee_duplicate" in types_found, "Expected ghost_employee_duplicate finding"

    def test_finding_has_required_fields(self):
        """Every finding has: finding_type, severity, title, description, evidence."""
        analyzer = PayrollAnalyzer(make_settings())
        records = [make_record(f"E{i}", 5000.0) for i in range(19)]
        records.append(make_record("E_outlier", 150000.0))
        findings = analyzer.analyze(records)
        assert findings, "Expected at least one finding"
        for f in findings:
            assert f.finding_type, "finding_type must be set"
            assert f.severity, "severity must be set"
            assert f.title, "title must be set"
            assert f.description, "description must be set"
            assert isinstance(f.evidence, dict), "evidence must be a dict"
