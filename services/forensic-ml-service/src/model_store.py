"""
Model registry using MLflow for experiment tracking and artifact storage.

Per-tenant model lifecycle:
  1. Training triggered (weekly cron or manual API call)
  2. MLflow run created with tenant_id tag
  3. Models (VAE weights, IF pickle, meta-classifier pickle) saved as artifacts
  4. Validation metrics logged
  5. If metrics pass threshold → model promoted to 'active' in DB
  6. Previous active model retired

Per-tenant isolation is enforced by tagging all MLflow runs with tenant_id.
MLflow experiments are named 'aegis-{model_type}-{tenant_id_prefix}'.
"""

import mlflow
import mlflow.pytorch
import structlog
from .vae import AegisVAE, VAEConfig
from .isolation_forest import IsolationForestModel, serialize_model, deserialize_model
from .ensemble import DRIEnsemble

logger = structlog.get_logger()


class ModelStore:
    def __init__(self, tracking_uri: str, artifact_bucket: str = "aegis-ml-artifacts"):
        mlflow.set_tracking_uri(tracking_uri)
        self.artifact_bucket = artifact_bucket

    def _experiment_name(self, model_type: str, tenant_id: str) -> str:
        return f"aegis-{model_type}-{tenant_id[:8]}"

    def save_vae(
        self, vae: AegisVAE, config: VAEConfig, tenant_id: str,
        metrics: dict, framework: str = 'soc2',
    ) -> str:
        """Save VAE to MLflow. Returns mlflow_run_id."""
        exp_name = self._experiment_name('vae', tenant_id)
        mlflow.set_experiment(exp_name)

        with mlflow.start_run(tags={'tenant_id': tenant_id, 'framework': framework}) as run:
            mlflow.log_params({
                'feature_dim': config.feature_dim,
                'latent_dim': config.latent_dim,
                'encoder_dims': str(config.encoder_dims),
            })
            mlflow.log_metrics(metrics)
            mlflow.pytorch.log_model(vae, artifact_path='vae_model')
            return run.info.run_id

    def load_vae(self, mlflow_run_id: str) -> AegisVAE:
        model_uri = f"runs:/{mlflow_run_id}/vae_model"
        return mlflow.pytorch.load_model(model_uri)

    def save_isolation_forest(
        self, model: IsolationForestModel, tenant_id: str,
        metrics: dict, framework: str = 'soc2',
    ) -> str:
        exp_name = self._experiment_name('isolation_forest', tenant_id)
        mlflow.set_experiment(exp_name)

        with mlflow.start_run(tags={'tenant_id': tenant_id, 'framework': framework}) as run:
            mlflow.log_metrics(metrics)
            model_bytes = serialize_model(model)
            mlflow.log_artifact(
                self._bytes_to_tempfile(model_bytes, 'isolation_forest.pkl'),
                artifact_path='isolation_forest'
            )
            return run.info.run_id

    def load_isolation_forest(self, mlflow_run_id: str) -> IsolationForestModel:
        client = mlflow.tracking.MlflowClient()
        artifact_path = client.download_artifacts(mlflow_run_id, 'isolation_forest/isolation_forest.pkl')
        with open(artifact_path, 'rb') as f:
            return deserialize_model(f.read())

    def save_ensemble(
        self, ensemble: DRIEnsemble, tenant_id: str,
        metrics: dict, framework: str = 'soc2',
    ) -> str:
        exp_name = self._experiment_name('ensemble', tenant_id)
        mlflow.set_experiment(exp_name)

        with mlflow.start_run(tags={'tenant_id': tenant_id, 'framework': framework}) as run:
            mlflow.log_metrics(metrics)
            ensemble_bytes = ensemble.serialize()
            mlflow.log_artifact(
                self._bytes_to_tempfile(ensemble_bytes, 'ensemble.pkl'),
                artifact_path='ensemble'
            )
            return run.info.run_id

    def load_ensemble(self, mlflow_run_id: str) -> DRIEnsemble:
        client = mlflow.tracking.MlflowClient()
        artifact_path = client.download_artifacts(mlflow_run_id, 'ensemble/ensemble.pkl')
        with open(artifact_path, 'rb') as f:
            return DRIEnsemble.deserialize(f.read())

    def _bytes_to_tempfile(self, data: bytes, filename: str) -> str:
        import tempfile
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=f'_{filename}')
        tf.write(data)
        tf.close()
        return tf.name
