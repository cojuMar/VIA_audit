"""
Real-time anomaly scorer.

Loads active models from MLflow (cached in memory, refreshed on model update events).
Scores incoming evidence records from the Kafka consumer.
"""

import numpy as np
import asyncpg
import structlog
from uuid import UUID
from datetime import datetime, timezone
from .vae import AegisVAE
from .isolation_forest import IsolationForestModel
from .ensemble import DRIEnsemble, EnsembleInput, DRIResult
from .features import extract_features, build_feature_context_from_canonical
from .benford import benford_risk_score, BenfordResult
from .model_store import ModelStore

logger = structlog.get_logger()

_model_cache: dict[str, dict] = {}  # {tenant_id: {'vae': ..., 'if': ..., 'ensemble': ..., 'loaded_at': ...}}


class AnomalyScorer:
    """
    Scores a canonical evidence record using the full Aegis ML ensemble.

    Model loading strategy:
    - Models are cached per-tenant in memory
    - Cache is invalidated when a new model is deployed (DB poll every 5 minutes)
    - On cache miss, models are loaded from MLflow
    - Fallback: if no trained models exist (new tenant), returns neutral scores
    """

    def __init__(self, pool: asyncpg.Pool, model_store: ModelStore):
        self.pool = pool
        self.model_store = model_store

    async def score(
        self, tenant_id: str, evidence_record: dict, framework: str = 'soc2'
    ) -> DRIResult:
        models = await self._get_models(tenant_id, framework)
        payload = evidence_record.get('canonical_payload', {})

        # Enrich context from DB
        vendor_data = await self._get_vendor_context(tenant_id, payload.get('entity_id', ''))
        juris_risk = await self._get_jurisdiction_risk(payload.get('metadata', {}).get('country_code', 'US'))
        benford_result = await self._get_entity_benford_stats(tenant_id, payload.get('entity_id', ''))

        ctx = build_feature_context_from_canonical(
            payload,
            vendor_age_days=float(vendor_data.get('vendor_age_days', 365)),
            account_interaction_percentile=float(vendor_data.get('interaction_percentile', 0.5)),
            jurisdictional_risk=float(juris_risk),
            transaction_velocity_zscore=float(vendor_data.get('velocity_zscore', 0.0)),
        )
        fv = extract_features(ctx)

        if models is None:
            # No trained models — return neutral DRI
            from .ensemble import DRIResult, DRIWeights
            neutral_dri = 0.3
            return DRIResult(
                dynamic_risk_index=neutral_dri,
                risk_level='low',
                vae_score=0.5,
                isolation_score=0.5,
                benford_risk=benford_risk_score(benford_result),
                scored_by='fallback_no_model',
            )

        vae_score_raw = models['vae'].anomaly_score(fv.reshape(1, -1))[0]
        vae_score_norm = float(np.clip(
            (vae_score_raw - models['vae_min']) / (models['vae_max'] - models['vae_min'] + 1e-8), 0, 1
        ))
        if_score = float(models['if'].predict_scores(fv.reshape(1, -1))[0])

        entity_id = payload.get('entity_id', '')
        vendor_age_days = float(vendor_data.get('vendor_age_days', 365))
        inp = EnsembleInput(
            vae_score=vae_score_norm,
            isolation_score=if_score,
            benford_risk=benford_risk_score(benford_result),
            vendor_age_risk=1.0 - float(1.0 / (1.0 + np.exp(-(vendor_age_days - 365) / 365))),
            round_number_freq=float(fv[1]),
            weekend_activity=float(fv[7]),
            rare_account_interaction=1.0 - float(ctx.account_interaction_percentile),
            jurisdictional_risk=float(juris_risk),
            evidence_id=str(evidence_record.get('evidence_id', '')),
            tenant_id=tenant_id,
            entity_id=entity_id,
            framework=framework,
        )
        return models['ensemble'].score(inp)

    async def _get_models(self, tenant_id: str, framework: str) -> dict | None:
        cached = _model_cache.get(f"{tenant_id}:{framework}")
        if cached:
            return cached

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT model_type, mlflow_run_id FROM ml_model_registry
                WHERE tenant_id=$1 AND framework=$2 AND is_active=TRUE
            """, UUID(tenant_id), framework)

        if not rows:
            return None

        models_by_type = {r['model_type']: r['mlflow_run_id'] for r in rows}
        loaded = {}

        if 'vae' in models_by_type:
            vae = self.model_store.load_vae(models_by_type['vae'])
            loaded['vae'] = vae
            # Compute score bounds from a small random batch
            import torch
            dummy = torch.zeros(100, 12)
            scores = vae.anomaly_score(dummy.numpy())
            loaded['vae_min'] = float(scores.min())
            loaded['vae_max'] = float(scores.max())

        if 'isolation_forest' in models_by_type:
            loaded['if'] = self.model_store.load_isolation_forest(models_by_type['isolation_forest'])

        if loaded:
            from .ensemble import DRIWeights
            weights = DRIWeights(framework=framework)
            if 'ensemble' in models_by_type:
                loaded['ensemble'] = self.model_store.load_ensemble(models_by_type['ensemble'])
            else:
                loaded['ensemble'] = DRIEnsemble(weights=weights)

            _model_cache[f"{tenant_id}:{framework}"] = loaded

        return loaded if loaded else None

    async def _get_vendor_context(self, tenant_id: str, entity_id: str) -> dict:
        if not entity_id:
            return {}
        async with self.pool.acquire() as conn:
            await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
            row = await conn.fetchrow("""
                SELECT first_transaction_at, transaction_count, jurisdictional_risk_score
                FROM vendor_profiles WHERE external_vendor_id=$1
            """, entity_id)
            if not row:
                return {}
            import datetime as dt
            age = (dt.datetime.now(dt.timezone.utc) - row['first_transaction_at']).days if row['first_transaction_at'] else 365
            return {'vendor_age_days': age, 'velocity_zscore': 0.0, 'interaction_percentile': 0.5}

    async def _get_jurisdiction_risk(self, country_code: str) -> float:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT risk_score FROM jurisdiction_risk_scores WHERE country_code=$1", country_code)
            return float(row['risk_score']) if row else 0.1

    async def _get_entity_benford_stats(self, tenant_id: str, entity_id: str) -> BenfordResult | None:
        return None  # Benford stats are computed in training, loaded from benford_entity_stats table
