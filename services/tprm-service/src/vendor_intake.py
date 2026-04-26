"""
Vendor Intake & Risk Tiering

The intake rubric automatically scores vendors 0–10 based on:
  - Data sensitivity: PII (+2.0), PHI (+3.0), PCI (+2.5)
  - Integration depth: none(0), read_only(+0.5), read_write(+1.5), admin(+2.5), core_infrastructure(+4.0)
  - Vendor type: infrastructure(+1.0), data_processor(+1.5), financial(+1.0)
  - AI usage: +0.5
  - Sub-processors: +0.3 per sub-processor (max +1.5)
  - Data types count: +0.2 per type (max +1.0)

Risk tier thresholds:
  score >= 7.0 → critical
  score >= 5.0 → high
  score >= 3.0 → medium
  score <  3.0 → low

Recommended questionnaire:
  critical/high → 'sig-lite'
  medium with cloud services → 'caiq-v4'
  low → 'custom-base'
"""
import logging
from uuid import UUID
from .models import VendorIntakeRequest, RiskRubricScore, RiskTier, VendorType

logger = logging.getLogger(__name__)


class VendorIntake:
    def __init__(self, db_pool):
        self._pool = db_pool

    def score_vendor(self, intake: VendorIntakeRequest) -> RiskRubricScore:
        """
        Compute inherent risk score from intake form data.
        Returns RiskRubricScore with breakdown.
        No DB call — pure computation.
        """
        score = 0.0
        factors = {}

        # Data sensitivity
        if intake.processes_phi:
            score += 3.0
            factors['phi_processing'] = 3.0
        if intake.processes_pci:
            score += 2.5
            factors['pci_processing'] = 2.5
        if intake.processes_pii:
            score += 2.0
            factors['pii_processing'] = 2.0

        # Integration depth
        depth_scores = {
            'none': 0.0, 'read_only': 0.5, 'read_write': 1.5,
            'admin': 2.5, 'core_infrastructure': 4.0
        }
        depth_score = depth_scores.get(intake.integrations_depth, 0.0)
        score += depth_score
        factors['integration_depth'] = depth_score

        # Vendor type
        type_scores = {
            'infrastructure': 1.0, 'data_processor': 1.5, 'financial': 1.0,
            'saas': 0.5, 'professional_services': 0.3, 'hardware': 0.5, 'other': 0.2
        }
        type_score = type_scores.get(intake.vendor_type.value, 0.0)
        score += type_score
        factors['vendor_type'] = type_score

        # AI usage
        if intake.uses_ai:
            score += 0.5
            factors['uses_ai'] = 0.5

        # Sub-processors
        sub_score = min(len(intake.sub_processors) * 0.3, 1.5)
        score += sub_score
        factors['sub_processors'] = sub_score

        # Data types breadth
        data_score = min(len(intake.data_types_processed) * 0.2, 1.0)
        score += data_score
        factors['data_types_count'] = data_score

        # Cap at 10.0
        score = min(round(score, 2), 10.0)

        # Determine tier
        if score >= 7.0:
            tier = RiskTier.CRITICAL
        elif score >= 5.0:
            tier = RiskTier.HIGH
        elif score >= 3.0:
            tier = RiskTier.MEDIUM
        else:
            tier = RiskTier.LOW

        # Recommend questionnaire
        is_cloud = intake.vendor_type in (VendorType.SAAS, VendorType.INFRASTRUCTURE)
        if tier in (RiskTier.CRITICAL, RiskTier.HIGH):
            questionnaire = 'sig-lite'
        elif tier == RiskTier.MEDIUM and is_cloud:
            questionnaire = 'caiq-v4'
        else:
            questionnaire = 'custom-base'

        return RiskRubricScore(
            vendor_id=None,  # set after DB insert
            inherent_score=score,
            risk_tier=tier,
            score_factors=factors,
            recommended_questionnaire=questionnaire
        )

    async def create_vendor(self, tenant_id: UUID, intake: VendorIntakeRequest) -> dict:
        """
        Score vendor, insert into DB, persist risk score snapshot.
        Returns the created vendor record as dict.
        """
        rubric = self.score_vendor(intake)

        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            async with conn.transaction():
                vendor_id = await conn.fetchval("""
                    INSERT INTO vendors (
                        tenant_id, name, website, description, vendor_type,
                        risk_tier, primary_contact_name, primary_contact_email,
                        data_types_processed, integrations_depth,
                        processes_pii, processes_phi, processes_pci, uses_ai,
                        sub_processors, inherent_risk_score, next_review_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                              NOW() + INTERVAL '90 days')
                    RETURNING id
                """,
                    tenant_id, intake.name, intake.website, intake.description,
                    intake.vendor_type.value, rubric.risk_tier.value,
                    intake.primary_contact_name, intake.primary_contact_email,
                    intake.data_types_processed, intake.integrations_depth,
                    intake.processes_pii, intake.processes_phi, intake.processes_pci,
                    intake.uses_ai, intake.sub_processors, rubric.inherent_score
                )

                # Persist immutable risk score snapshot
                import json
                await conn.execute("""
                    INSERT INTO vendor_risk_scores (tenant_id, vendor_id, inherent_score, score_factors)
                    VALUES ($1, $2, $3, $4::jsonb)
                """, tenant_id, vendor_id, rubric.inherent_score, json.dumps(rubric.score_factors))

                rubric.vendor_id = vendor_id
                logger.info(f"Vendor created: {intake.name} tier={rubric.risk_tier.value} score={rubric.inherent_score}")

                return {
                    "vendor_id": str(vendor_id),
                    "name": intake.name,
                    "risk_tier": rubric.risk_tier.value,
                    "inherent_risk_score": rubric.inherent_score,
                    "score_factors": rubric.score_factors,
                    "recommended_questionnaire": rubric.recommended_questionnaire
                }
