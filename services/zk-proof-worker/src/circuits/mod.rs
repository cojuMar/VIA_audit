pub mod sum_threshold;
pub mod access_log;

use halo2_proofs::{
    plonk::{ProvingKey, VerifyingKey},
};

/// All supported circuit types. Each variant corresponds to a compliance assertion.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CircuitType {
    /// Proves: sum(private_amounts) == claimed_sum AND claimed_sum <= threshold
    SumThreshold,
    /// Proves: all session_ids in the access log belong to the set of authenticated sessions
    AccessLogMembership,
    /// Proves: all policy assertions hold over the evidence set without revealing specifics
    PolicyCompliance,
}

/// Trait that all Aegis ZK circuits must implement.
/// Abstracts over the Halo2 circuit setup, proving, and verification.
pub trait AegisCircuit: Sized {
    type PublicInputs: serde::Serialize + for<'de> serde::Deserialize<'de>;
    type PrivateInputs;

    /// Circuit identifier string — matches the DB circuit_type column.
    fn circuit_type() -> CircuitType;

    /// Maximum number of witness elements per batch (determines RAM usage).
    fn max_batch_size() -> usize;

    /// Build the circuit instance from private inputs.
    fn build(private_inputs: Self::PrivateInputs) -> Self;

    /// Generate the setup parameters (done once, cached).
    fn generate_params(k: u32) -> halo2_proofs::poly::ipa::commitment::ParamsIPA<halo2curves::pasta::EqAffine>;

    /// Generate a proof. Returns proof bytes.
    fn prove(
        params: &halo2_proofs::poly::ipa::commitment::ParamsIPA<halo2curves::pasta::EqAffine>,
        pk: &ProvingKey<halo2curves::pasta::EqAffine>,
        circuit: Self,
        public_inputs: &[halo2_proofs::pasta::Fp],
    ) -> Result<Vec<u8>, ProofError>;

    /// Verify a proof. Returns Ok(()) if valid, Err if invalid.
    fn verify(
        params: &halo2_proofs::poly::ipa::commitment::ParamsIPA<halo2curves::pasta::EqAffine>,
        vk: &VerifyingKey<halo2curves::pasta::EqAffine>,
        proof: &[u8],
        public_inputs: &[halo2_proofs::pasta::Fp],
    ) -> Result<(), ProofError>;
}

#[derive(Debug, thiserror::Error)]
pub enum ProofError {
    #[error("Circuit constraint violation: {0}")]
    ConstraintViolation(String),
    #[error("Proof generation failed: {0}")]
    GenerationFailed(String),
    #[error("Proof verification failed: invalid proof")]
    VerificationFailed,
    #[error("Invalid public inputs: {0}")]
    InvalidPublicInputs(String),
    #[error("Batch size {0} exceeds maximum {1}")]
    BatchTooLarge(usize, usize),
}
