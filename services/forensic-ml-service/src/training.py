"""
Per-tenant model training pipeline.

Training cadence: weekly (Sunday 2am UTC) via APScheduler cron job.
Each tenant gets independently trained models — no shared parameters.

Training data source: evidence_records table (via RLS, per-tenant).
Feature enrichment: vendor_profiles + jurisdiction_risk_scores.

The full pipeline for one tenant:
  1. Load 6 months of normalized evidence records
  2. Enrich with vendor age, jurisdictional risk
  3. Extract 12-dim feature vectors
  4. Train VAE (50 epochs, KL annealing)
  5. Train Isolation Forest (n_estimators=200, max_samples=256)
  6. Compute anomaly threshold (95th percentile)
  7. Log models to MLflow with tenant_id tag
  8. Update ml_model_registry in DB (is_active = TRUE, retire previous)
  9. If labeled anomaly data exists (from HITL reviews): train meta-classifier
"""

import asyncpg
import numpy as np
import structlog
from uuid import UUID

from .config import settings
from .features import extract_features, build_feature_context_from_canonical
from .vae import VAETrainer, VAEConfig
from .isolation_forest import train_isolation_forest
from .ensemble import DRIEnsemble, DRIWeights, EnsembleInput
from .model_store import ModelStore
from .benford import BenfordEngine

logger = structlog.get_logger()


class TenantTrainingPipeline:
    def __init__(self, pool: asyncpg.Pool, model_store: ModelStore):
        self.pool = pool
        self.model_store = model_store
        self.benford_engine = BenfordEngine()

    async def train_tenant(self, tenant_id: str, framework: str = 'soc2') -> dict:
        """
        Full training pipeline for a single tenant.
        Returns summary of training results.
        """
        logger.info("Starting training pipeline", tenant_id=tenant_id, framework=framework)
        results = {}

        # 1. Load evidence records (trailing 6 months)
        records = await self._load_evidence_records(tenant_id, days=180)
        if len(records) < settings.ml_min_samples_for_training:
            logger.warning(
                "Insufficient training data",
                tenant_id=tenant_id,
                count=len(records),
                minimum=settings.ml_min_samples_for_training,
            )
            return {'status': 'skipped', 'reason': 'insufficient_data', 'count': len(records)}

        # 2. Load enrichment data
        vendor_data = await self._load_vendor_data(tenant_id)
        jurisdiction_data = await self._load_jurisdiction_data()
        framework_weights = await self._load_framework_weights(framework)

        # 3. Extract feature vectors
        features, metadata = self._extract_feature_matrix(records, vendor_data, jurisdiction_data)
        logger.info("Features extracted", tenant_id=tenant_id, shape=features.shape)

        # 4. Train VAE
        vae_config = VAEConfig(
            feature_dim=settings.ml_feature_dim,
            latent_dim=settings.ml_latent_dim,
            encoder_dims=settings.ml_encoder_dims,
            learning_rate=settings.ml_learning_rate,
            kl_annealing_epochs=10,
        )
        trainer = VAETrainer(vae_config)
        vae_metrics = trainer.train(features, epochs=settings.ml_vae_epochs, batch_size=settings.ml_batch_size)
        vae_scores = trainer.model.anomaly_score(features)
        vae_threshold = trainer.compute_threshold(features, settings.ml_anomaly_percentile)
        vae_run_id = self.model_store.save_vae(trainer.model, vae_config, tenant_id, {
            'final_loss': vae_metrics['final_loss'],
            'vae_threshold': vae_threshold,
        }, framework)
        results['vae'] = {'run_id': vae_run_id, 'threshold': vae_threshold}
        logger.info("VAE trained", tenant_id=tenant_id, run_id=vae_run_id)

        # 5. Train Isolation Forest
        if_model = train_isolation_forest(features, tenant_id=tenant_id, framework=framework)
        if_scores = if_model.predict_scores(features)
        if_run_id = self.model_store.save_isolation_forest(if_model, tenant_id, {
            'training_sample_count': float(if_model.training_sample_count),
        }, framework)
        results['isolation_forest'] = {'run_id': if_run_id}
        logger.info("Isolation Forest trained", tenant_id=tenant_id, run_id=if_run_id)

        # 6. Compute Benford stats per entity
        amounts_by_entity = self._group_amounts_by_entity(records)
        benford_results = self.benford_engine.analyze_batch(amounts_by_entity)
        await self._save_benford_stats(tenant_id, benford_results)

        # 7. Build ensemble inputs for meta-classifier training
        dri_weights = DRIWeights.from_db_row(framework_weights) if framework_weights else DRIWeights(framework=framework)
        ensemble = DRIEnsemble(weights=dri_weights)

        # 8. Load labeled anomaly data (from HITL reviews in anomaly_scores table)
        labeled_data = await self._load_labeled_anomalies(tenant_id)
        if labeled_data and len(labeled_data) >= 50:
            ensemble_inputs = [item['input'] for item in labeled_data]
            labels = [item['label'] for item in labeled_data]
            meta_metrics = ensemble.train_meta_classifier(ensemble_inputs, labels)
            results['meta_classifier'] = meta_metrics
            ensemble_run_id = self.model_store.save_ensemble(ensemble, tenant_id, meta_metrics, framework)
            results['ensemble'] = {'run_id': ensemble_run_id}
        else:
            logger.info("Insufficient labeled data for meta-classifier", tenant_id=tenant_id,
                        labeled_count=len(labeled_data) if labeled_data else 0)

        # 9. Update DB model registry
        await self._update_model_registry(tenant_id, framework, results)

        logger.info("Training pipeline complete", tenant_id=tenant_id, results=results)
        return {'status': 'success', 'records_used': len(records), 'results': results}

    async def _load_evidence_records(self, tenant_id: str, days: int = 180) -> list[dict]:
        async with self.pool.acquire() as conn:
            await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
            rows = await conn.fetch("""
                SELECT evidence_id, source_system, collected_at_utc,
                       canonical_payload, chain_sequence
                FROM evidence_records
                WHERE collected_at_utc > NOW() - INTERVAL '{days} days'
                  AND freshness_status = 'fresh'
                ORDER BY collected_at_utc
            """.replace('{days}', str(days)))
            return [dict(r) for r in rows]

    async def _load_vendor_data(self, tenant_id: str) -> dict[str, dict]:
        async with self.pool.acquire() as conn:
            await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
            rows = await conn.fetch("""
                SELECT external_vendor_id, vendor_name, first_transaction_at,
                       transaction_count, jurisdictional_risk_score
                FROM vendor_profiles
            """)
            return {r['external_vendor_id']: dict(r) for r in rows}

    async def _load_jurisdiction_data(self) -> dict[str, float]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT country_code, risk_score FROM jurisdiction_risk_scores")
            return {r['country_code']: r['risk_score'] for r in rows}

    async def _load_framework_weights(self, framework: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM dri_framework_weights WHERE framework = $1", framework
            )
            return dict(row) if row else None

    def _extract_feature_matrix(
        self, records: list[dict], vendor_data: dict, jurisdiction_data: dict
    ) -> tuple[np.ndarray, list[dict]]:
        features, metadata = [], []
        for rec in records:
            payload = rec.get('canonical_payload', {})
            entity_id = payload.get('entity_id', '')
            vendor = vendor_data.get(entity_id, {})

            # Compute vendor age
            first_txn = vendor.get('first_transaction_at')
            if first_txn:
                import datetime as dt
                vendor_age_days = (dt.datetime.now(dt.timezone.utc) - first_txn).days
            else:
                vendor_age_days = 365  # Default to 1 year if unknown

            country_code = payload.get('metadata', {}).get('country_code', 'US')
            juris_risk = jurisdiction_data.get(country_code, 0.1)

            ctx = build_feature_context_from_canonical(
                payload,
                vendor_age_days=float(vendor_age_days),
                jurisdictional_risk=juris_risk,
            )
            fv = extract_features(ctx)
            features.append(fv)
            metadata.append({'evidence_id': str(rec['evidence_id']), 'entity_id': entity_id})

        return np.stack(features), metadata

    def _group_amounts_by_entity(self, records: list[dict]) -> dict[str, list[float]]:
        result: dict[str, list[float]] = {}
        for rec in records:
            payload = rec.get('canonical_payload', {})
            entity_id = payload.get('entity_id', 'unknown')
            amount = float(payload.get('metadata', {}).get('amount', 0.0))
            if amount > 0:
                result.setdefault(entity_id, []).append(amount)
        return result

    async def _save_benford_stats(self, tenant_id: str, benford_results: dict) -> None:
        import json
        from datetime import datetime, timezone, timedelta
        async with self.pool.acquire() as conn:
            await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
            for entity_id, result in benford_results.items():
                if result is None:
                    continue
                await conn.execute("""
                    INSERT INTO benford_entity_stats
                        (tenant_id, entity_id, entity_type, transaction_count,
                         first_digit_distribution, expected_distribution,
                         mad, chi2_statistic, chi2_pvalue, conforming,
                         window_start, window_end)
                    VALUES ($1,$2,'vendor',$3,$4,$5,$6,$7,$8,$9,$10,$11)
                    ON CONFLICT (tenant_id, entity_id, entity_type, window_start) DO UPDATE
                    SET mad=$6, conforming=$9, computed_at=NOW()
                """,
                    UUID(tenant_id), entity_id, result.transaction_count,
                    json.dumps(result.digit_counts), json.dumps(result.expected_probs),
                    result.mad, result.chi2_statistic, result.chi2_pvalue, result.conforming,
                    datetime.now(timezone.utc) - timedelta(days=90),
                    datetime.now(timezone.utc),
                )

    async def _load_labeled_anomalies(self, tenant_id: str) -> list[dict] | None:
        """Load HITL-reviewed anomaly scores to use as meta-classifier training data."""
        async with self.pool.acquire() as conn:
            await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
            rows = await conn.fetch("""
                SELECT vae_score, isolation_score, benford_mad,
                       dynamic_risk_index, false_positive, feature_vector
                FROM anomaly_scores
                WHERE reviewed = TRUE AND false_positive IS NOT NULL
                ORDER BY reviewed_at DESC
                LIMIT 5000
            """)
            if not rows:
                return None
            result = []
            for row in rows:
                import json
                fv = row['feature_vector']
                if isinstance(fv, str):
                    fv = json.loads(fv)
                inp = EnsembleInput(
                    vae_score=float(row['vae_score'] or 0.5),
                    isolation_score=float(row['isolation_score'] or 0.5),
                    benford_risk=0.5,
                    vendor_age_risk=float(fv.get('8', 0.5)) if fv else 0.5,
                    round_number_freq=float(fv.get('1', 0.0)) if fv else 0.0,
                    weekend_activity=float(fv.get('7', 0.0)) if fv else 0.0,
                    rare_account_interaction=float(1 - fv.get('9', 0.5)) if fv else 0.5,
                    jurisdictional_risk=float(fv.get('10', 0.1)) if fv else 0.1,
                    tenant_id=tenant_id,
                )
                label = 0 if row['false_positive'] else 1
                result.append({'input': inp, 'label': label})
            return result

    async def _update_model_registry(self, tenant_id: str, framework: str, results: dict) -> None:
        """Update ml_model_registry: mark new models active, retire old ones."""
        async with self.pool.acquire() as conn:
            await conn.execute(f"SET LOCAL app.tenant_id = '{tenant_id}'")
            for model_type, data in results.items():
                if 'run_id' not in data:
                    continue
                # Retire existing active model
                await conn.execute("""
                    UPDATE ml_model_registry SET is_active=FALSE, retired_at=NOW()
                    WHERE tenant_id=$1 AND model_type=$2 AND framework=$3 AND is_active=TRUE
                """, UUID(tenant_id), model_type, framework)
                # Register new model
                await conn.execute("""
                    INSERT INTO ml_model_registry
                        (tenant_id, model_type, framework, version, mlflow_run_id,
                         training_started_at, training_completed_at, is_active, deployed_at)
                    VALUES ($1,$2,$3,'1.0.0',$4,NOW(),NOW(),TRUE,NOW())
                """, UUID(tenant_id), model_type, framework, data['run_id'])
