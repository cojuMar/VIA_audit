import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/tprm-service'))

import pytest
from src.models import VendorIntakeRequest, VendorType
from src.vendor_intake import VendorIntake


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_intake(**kwargs):
    defaults = {
        'name': 'Test Vendor',
        'vendor_type': VendorType.OTHER,
        'integrations_depth': 'none',
        'data_types_processed': [],
        'processes_pii': False,
        'processes_phi': False,
        'processes_pci': False,
        'uses_ai': False,
        'sub_processors': [],
        'website': None,
        'description': None,
        'primary_contact_name': None,
        'primary_contact_email': None,
    }
    defaults.update(kwargs)
    return VendorIntakeRequest(**defaults)


def _score(intake: VendorIntakeRequest) -> float:
    intake_svc = VendorIntake(db_pool=None)
    return intake_svc.score_vendor(intake).inherent_score


def _rubric(intake: VendorIntakeRequest):
    intake_svc = VendorIntake(db_pool=None)
    return intake_svc.score_vendor(intake)


# ---------------------------------------------------------------------------
# TestRiskRubricScoring
# ---------------------------------------------------------------------------

class TestRiskRubricScoring:
    def test_phi_processing_adds_3_points(self):
        base = _score(make_intake())
        result = _score(make_intake(processes_phi=True))
        assert result - base == pytest.approx(3.0, abs=0.01)

    def test_pci_processing_adds_2_5_points(self):
        base = _score(make_intake())
        result = _score(make_intake(processes_pci=True))
        assert result - base == pytest.approx(2.5, abs=0.01)

    def test_pii_processing_adds_2_points(self):
        base = _score(make_intake())
        result = _score(make_intake(processes_pii=True))
        assert result - base == pytest.approx(2.0, abs=0.01)

    def test_core_infrastructure_depth_adds_4_points(self):
        base = _score(make_intake(integrations_depth='none'))
        result = _score(make_intake(integrations_depth='core_infrastructure'))
        assert result - base == pytest.approx(4.0, abs=0.01)

    def test_ai_usage_adds_0_5_points(self):
        base = _score(make_intake())
        result = _score(make_intake(uses_ai=True))
        assert result - base == pytest.approx(0.5, abs=0.01)

    def test_sub_processors_capped_at_1_5(self):
        # 8 sub-processors × 0.3 = 2.4, capped at 1.5
        intake = make_intake(sub_processors=['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'])
        rubric = _rubric(intake)
        assert rubric.score_factors['sub_processors'] == pytest.approx(1.5, abs=0.01)

    def test_max_score_capped_at_10(self):
        intake = make_intake(
            vendor_type=VendorType.DATA_PROCESSOR,
            integrations_depth='core_infrastructure',
            processes_pii=True,
            processes_phi=True,
            processes_pci=True,
            uses_ai=True,
            sub_processors=['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'],
            data_types_processed=['pii', 'phi', 'pci', 'financial', 'health', 'biometric'],
        )
        result = _score(intake)
        assert result <= 10.0

    def test_zero_risk_vendor(self):
        intake = make_intake(
            vendor_type=VendorType.OTHER,
            integrations_depth='none',
            processes_pii=False,
            processes_phi=False,
            processes_pci=False,
            uses_ai=False,
            sub_processors=[],
            data_types_processed=[],
        )
        result = _score(intake)
        assert result < 2.0


# ---------------------------------------------------------------------------
# TestRiskTierThresholds
# ---------------------------------------------------------------------------

class TestRiskTierThresholds:
    def _make_at_score(self, target_score: float):
        """
        Build an intake that produces exactly target_score by using
        integrations_depth='none', vendor_type=OTHER (0.2), and adjusting PII/PHI.
        We rely on known rubric weights.  For fine-grained control, use a score
        that is achievable with the available factors.
        """
        intake_svc = VendorIntake(db_pool=None)
        # Try different combos until we bracket the target
        # Use PHI (3.0) + core_infrastructure (4.0) as our big levers
        # For target 7.0: core_infrastructure (4.0) + PHI (3.0) = 7.0, vendor_type=OTHER (+0.2) → 7.2
        # We'll build the intake to confirm tier classification directly
        return intake_svc

    def test_score_7_or_above_is_critical(self):
        # core_infrastructure(4.0) + PHI(3.0) + OTHER(0.2) = 7.2 → critical
        intake = make_intake(
            integrations_depth='core_infrastructure',
            processes_phi=True,
        )
        rubric = _rubric(intake)
        assert rubric.inherent_score >= 7.0
        assert rubric.risk_tier.value == 'critical'

    def test_score_5_to_7_is_high(self):
        # admin(2.5) + PCI(2.5) + OTHER(0.2) = 5.2 → high
        intake = make_intake(
            integrations_depth='admin',
            processes_pci=True,
        )
        rubric = _rubric(intake)
        assert 5.0 <= rubric.inherent_score < 7.0
        assert rubric.risk_tier.value == 'high'

    def test_score_3_to_5_is_medium(self):
        # read_write(1.5) + PII(2.0) + OTHER(0.2) = 3.7 → medium
        intake = make_intake(
            integrations_depth='read_write',
            processes_pii=True,
        )
        rubric = _rubric(intake)
        assert 3.0 <= rubric.inherent_score < 5.0
        assert rubric.risk_tier.value == 'medium'

    def test_score_below_3_is_low(self):
        # read_only(0.5) + OTHER(0.2) = 0.7 → low
        intake = make_intake(
            integrations_depth='read_only',
        )
        rubric = _rubric(intake)
        assert rubric.inherent_score < 3.0
        assert rubric.risk_tier.value == 'low'


# ---------------------------------------------------------------------------
# TestQuestionnaireRecommendation
# ---------------------------------------------------------------------------

class TestQuestionnaireRecommendation:
    def test_critical_vendor_gets_sig_lite(self):
        # score >= 7.0 → critical → sig-lite
        intake = make_intake(
            integrations_depth='core_infrastructure',
            processes_phi=True,
        )
        rubric = _rubric(intake)
        assert rubric.risk_tier.value == 'critical'
        assert rubric.recommended_questionnaire == 'sig-lite'

    def test_high_vendor_gets_sig_lite(self):
        # admin(2.5) + PCI(2.5) + OTHER(0.2) = 5.2 → high → sig-lite
        intake = make_intake(
            integrations_depth='admin',
            processes_pci=True,
        )
        rubric = _rubric(intake)
        assert rubric.risk_tier.value == 'high'
        assert rubric.recommended_questionnaire == 'sig-lite'

    def test_medium_saas_gets_caiq(self):
        # read_write(1.5) + PII(2.0) + SAAS(0.5) = 4.0 → medium + cloud → caiq-v4
        intake = make_intake(
            vendor_type=VendorType.SAAS,
            integrations_depth='read_write',
            processes_pii=True,
        )
        rubric = _rubric(intake)
        assert rubric.risk_tier.value == 'medium'
        assert rubric.recommended_questionnaire == 'caiq-v4'

    def test_low_vendor_gets_custom_base(self):
        # read_only(0.5) + OTHER(0.2) = 0.7 → low → custom-base
        intake = make_intake(
            integrations_depth='read_only',
        )
        rubric = _rubric(intake)
        assert rubric.risk_tier.value == 'low'
        assert rubric.recommended_questionnaire == 'custom-base'
