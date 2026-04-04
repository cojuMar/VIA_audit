use std::sync::Arc;
use tokio::sync::Semaphore;
use crate::{
    circuits::{CircuitType, ProofError},
    circuits::sum_threshold::{prove_sum_threshold, SumThresholdPublicInputs},
    config::Config,
    storage::ProofStorageClient,
};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Deserialize)]
pub struct ProofJob {
    pub proof_id: Uuid,
    pub tenant_id: Uuid,
    pub circuit_type: CircuitType,
    pub evidence_record_ids: Vec<Uuid>,
    pub public_inputs: serde_json::Value,
    /// Private inputs delivered separately via an encrypted channel
    /// (never in the Kafka message — those go via Vault transit engine)
    pub private_inputs_vault_path: String,
}

#[derive(Debug, Serialize)]
pub struct ProofResult {
    pub proof_id: Uuid,
    pub tenant_id: Uuid,
    pub circuit_type: CircuitType,
    pub proof_blob_uri: String,
    pub proof_hash: String,         // hex SHA-256
    pub public_inputs: serde_json::Value,
    pub generation_duration_ms: u64,
    pub batch_count: usize,
    pub success: bool,
    pub error: Option<String>,
}

pub struct Prover {
    config: Arc<Config>,
    /// Semaphore limits concurrent proofs to max_concurrent_proofs (=1).
    /// A single proof at k=18 can use up to 14GB RAM; concurrent proofs
    /// would OOM. This enforces serial execution.
    semaphore: Arc<Semaphore>,
    storage: Arc<ProofStorageClient>,
}

impl Prover {
    pub fn new(config: Arc<Config>, storage: Arc<ProofStorageClient>) -> Self {
        let semaphore = Arc::new(Semaphore::new(config.max_concurrent_proofs));
        Self { config, semaphore, storage }
    }

    /// Generate a proof for the given job.
    /// Acquires the semaphore before starting to prevent concurrent OOM.
    pub async fn generate(&self, job: ProofJob) -> ProofResult {
        let _permit = self.semaphore.acquire().await.expect("semaphore closed");

        let started = std::time::Instant::now();

        // Load private inputs from Vault transit engine
        // (in dev environment, accept from the job payload directly)
        let result = self.generate_inner(&job).await;

        let duration_ms = started.elapsed().as_millis() as u64;

        match result {
            Ok((proof_bytes, public_inputs_json, batch_count)) => {
                // Compute SHA-256 of proof blob
                use sha2::{Sha256, Digest};
                let proof_hash = hex::encode(Sha256::digest(&proof_bytes));

                // Upload to WORM storage
                let uri = match self.storage.upload_proof(
                    &job.tenant_id.to_string(),
                    &job.proof_id.to_string(),
                    &proof_bytes,
                ).await {
                    Ok(uri) => uri,
                    Err(e) => {
                        return ProofResult {
                            proof_id: job.proof_id,
                            tenant_id: job.tenant_id,
                            circuit_type: job.circuit_type,
                            proof_blob_uri: String::new(),
                            proof_hash: String::new(),
                            public_inputs: serde_json::Value::Null,
                            generation_duration_ms: duration_ms,
                            batch_count: 0,
                            success: false,
                            error: Some(format!("Storage upload failed: {}", e)),
                        };
                    }
                };

                ProofResult {
                    proof_id: job.proof_id,
                    tenant_id: job.tenant_id,
                    circuit_type: job.circuit_type,
                    proof_blob_uri: uri,
                    proof_hash,
                    public_inputs: public_inputs_json,
                    generation_duration_ms: duration_ms,
                    batch_count,
                    success: true,
                    error: None,
                }
            }
            Err(e) => ProofResult {
                proof_id: job.proof_id,
                tenant_id: job.tenant_id,
                circuit_type: job.circuit_type,
                proof_blob_uri: String::new(),
                proof_hash: String::new(),
                public_inputs: serde_json::Value::Null,
                generation_duration_ms: duration_ms,
                batch_count: 0,
                success: false,
                error: Some(e.to_string()),
            },
        }
    }

    async fn generate_inner(
        &self,
        job: &ProofJob,
    ) -> Result<(Vec<u8>, serde_json::Value, usize), ProofError> {
        match job.circuit_type {
            CircuitType::SumThreshold => {
                // Parse private inputs (amounts array) from Vault
                // In production: decrypt from Vault transit engine
                // In dev: accept from job.public_inputs for testing
                let amounts: Vec<u64> = job.public_inputs
                    .get("_private_amounts")
                    .and_then(|v| v.as_array())
                    .ok_or_else(|| ProofError::InvalidPublicInputs("Missing _private_amounts".to_string()))?
                    .iter()
                    .map(|v| v.as_u64().unwrap_or(0))
                    .collect();

                let threshold = job.public_inputs
                    .get("threshold")
                    .and_then(|v| v.as_u64())
                    .ok_or_else(|| ProofError::InvalidPublicInputs("Missing threshold".to_string()))?;

                let max_batch_size = self.config.worker_max_batch_size;
                let batch_count = amounts.len().div_ceil(max_batch_size).max(1);

                let (proof_bytes, public_inputs) = tokio::task::spawn_blocking(move || {
                    prove_sum_threshold(amounts, threshold, max_batch_size)
                })
                .await
                .map_err(|e| ProofError::GenerationFailed(format!("Task panicked: {}", e)))??;

                let public_inputs_json = serde_json::to_value(&public_inputs)
                    .map_err(|e| ProofError::GenerationFailed(e.to_string()))?;

                Ok((proof_bytes, public_inputs_json, batch_count))
            }
            CircuitType::AccessLogMembership => {
                // Stub — full implementation pending circuit security audit
                Err(ProofError::GenerationFailed(
                    "AccessLogMembership circuit pending security audit".to_string()
                ))
            }
            CircuitType::PolicyCompliance => {
                Err(ProofError::GenerationFailed(
                    "PolicyCompliance circuit pending security audit".to_string()
                ))
            }
        }
    }
}
