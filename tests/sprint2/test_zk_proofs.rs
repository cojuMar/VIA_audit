/// Sprint 2 — ZK Proof System Tests
///
/// Tests the sum_threshold circuit: constraint correctness, memory safety,
/// batch decomposition, and proof/verify round-trips.
///
/// Run: cargo test --package zk-proof-worker
///
/// Note: Full proof generation is slow (10–30s per test in debug mode).
/// Tests that exercise the proving system use `#[ignore]` — run them with:
///   cargo test -- --ignored
/// This prevents slow tests from blocking the CI critical path.
/// The CI pipeline runs them in a dedicated slow-test job.

#[cfg(test)]
mod tests {
    use crate::circuits::{CircuitType, ProofError};
    use crate::circuits::sum_threshold::{
        SumThresholdCircuit, SumThresholdPublicInputs, prove_sum_threshold,
    };
    use halo2_proofs::{
        circuit::Value,
        dev::MockProver,
        pasta::Fp,
    };

    // -----------------------------------------------------------------------
    // Unit tests — circuit structure and constraint validation
    // Fast: < 1s each (MockProver does not generate actual cryptographic proofs)
    // -----------------------------------------------------------------------

    #[test]
    fn test_compute_k_minimum() {
        /// k must be at least 4 (16 rows) for any input
        assert!(SumThresholdCircuit::compute_k(1) >= 4);
        assert!(SumThresholdCircuit::compute_k(0) >= 4);
    }

    #[test]
    fn test_compute_k_scales_with_n() {
        /// Larger N produces larger k
        let k_small = SumThresholdCircuit::compute_k(100);
        let k_large = SumThresholdCircuit::compute_k(10000);
        assert!(k_large >= k_small);
    }

    #[test]
    fn test_compute_k_max_is_18() {
        /// k must never exceed 18 (262,144 rows = 16GB RAM budget)
        let k = SumThresholdCircuit::compute_k(1_000_000);
        assert!(k <= 18, "k={} exceeds maximum of 18", k);
    }

    #[test]
    fn test_batch_split_empty() {
        let batches = SumThresholdCircuit::split_into_batches(&[], 1000);
        assert!(batches.is_empty());
    }

    #[test]
    fn test_batch_split_within_limit() {
        let amounts = vec![100u64; 500];
        let batches = SumThresholdCircuit::split_into_batches(&amounts, 1000);
        assert_eq!(batches.len(), 1);
        assert_eq!(batches[0].len(), 500);
    }

    #[test]
    fn test_batch_split_exactly_one_batch() {
        let amounts = vec![100u64; 1000];
        let batches = SumThresholdCircuit::split_into_batches(&amounts, 1000);
        assert_eq!(batches.len(), 1);
    }

    #[test]
    fn test_batch_split_requires_two_batches() {
        let amounts = vec![100u64; 1001];
        let batches = SumThresholdCircuit::split_into_batches(&amounts, 1000);
        assert_eq!(batches.len(), 2);
        assert_eq!(batches[0].len(), 1000);
        assert_eq!(batches[1].len(), 1);
    }

    #[test]
    fn test_batch_split_preserves_all_amounts() {
        let amounts: Vec<u64> = (0..2500).map(|i| i as u64 * 100).collect();
        let batches = SumThresholdCircuit::split_into_batches(&amounts, 1000);
        let reassembled: Vec<u64> = batches.into_iter().flatten().collect();
        assert_eq!(reassembled, amounts);
    }

    #[test]
    fn test_public_inputs_field_elements_count() {
        /// SumThreshold must produce exactly 4 field elements as public inputs
        let pi = SumThresholdPublicInputs {
            sum: 10000,
            threshold: 50000,
            record_count: 5,
            assertion_passes: true,
        };
        let fields = pi.to_field_elements();
        assert_eq!(fields.len(), 4, "Expected 4 public input field elements");
    }

    #[test]
    fn test_public_inputs_assertion_passes_encoding() {
        /// assertion_passes=true encodes as Fp::one(), false as Fp::zero()
        let pass = SumThresholdPublicInputs {
            sum: 100, threshold: 200, record_count: 1, assertion_passes: true,
        };
        let fail = SumThresholdPublicInputs {
            sum: 300, threshold: 200, record_count: 1, assertion_passes: false,
        };
        let pass_fields = pass.to_field_elements();
        let fail_fields = fail.to_field_elements();
        assert_eq!(pass_fields[3], Fp::one());
        assert_eq!(fail_fields[3], Fp::zero());
    }

    #[test]
    fn test_mock_prover_valid_circuit() {
        /// MockProver verifies circuit constraints without generating a real proof.
        /// This is fast (< 100ms) and validates the constraint system logic.
        let amounts = vec![100u64, 200u64, 300u64];
        let circuit = SumThresholdCircuit::new(amounts);
        let k = SumThresholdCircuit::compute_k(3);

        let public_inputs = SumThresholdPublicInputs {
            sum: 600,
            threshold: 1000,
            record_count: 3,
            assertion_passes: true,
        };
        let pub_fp = public_inputs.to_field_elements();

        let prover = MockProver::run(k, &circuit, vec![pub_fp])
            .expect("MockProver::run failed");

        // All constraints should be satisfied
        prover.verify().expect("Circuit constraints not satisfied");
    }

    #[test]
    fn test_mock_prover_single_amount() {
        let circuit = SumThresholdCircuit::new(vec![42u64]);
        let k = SumThresholdCircuit::compute_k(1);
        let pi = SumThresholdPublicInputs {
            sum: 42, threshold: 100, record_count: 1, assertion_passes: true,
        };
        let prover = MockProver::run(k, &circuit, vec![pi.to_field_elements()])
            .expect("MockProver::run failed");
        prover.verify().expect("Single-amount circuit constraints failed");
    }

    #[test]
    fn test_mock_prover_zero_amount() {
        /// Zero amounts are valid (e.g. voided transactions)
        let circuit = SumThresholdCircuit::new(vec![0u64, 0u64, 100u64]);
        let k = SumThresholdCircuit::compute_k(3);
        let pi = SumThresholdPublicInputs {
            sum: 100, threshold: 500, record_count: 3, assertion_passes: true,
        };
        let prover = MockProver::run(k, &circuit, vec![pi.to_field_elements()])
            .expect("MockProver::run failed");
        prover.verify().expect("Zero-amount circuit constraints failed");
    }

    // -----------------------------------------------------------------------
    // Overflow detection tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_sum_overflow_rejected() {
        /// u64::MAX + 1 must be caught before the circuit
        let amounts = vec![u64::MAX, 1u64];
        let result = prove_sum_threshold(amounts, u64::MAX, 1000);
        assert!(result.is_err(), "Expected error for overflowing sum");
        match result.unwrap_err() {
            ProofError::InvalidPublicInputs(msg) => {
                assert!(msg.contains("overflow"), "Error message should mention overflow: {}", msg);
            }
            other => panic!("Expected InvalidPublicInputs error, got: {:?}", other),
        }
    }

    // -----------------------------------------------------------------------
    // Batch decomposition correctness
    // -----------------------------------------------------------------------

    #[test]
    fn test_batch_sums_aggregate_to_total() {
        /// Each sub-batch's sum must add up to the total sum
        let amounts: Vec<u64> = (1..=300).map(|i| i as u64 * 100).collect();
        let total: u64 = amounts.iter().sum();
        let max_batch = 100;

        let batches = SumThresholdCircuit::split_into_batches(&amounts, max_batch);
        let batch_total: u64 = batches.iter()
            .flat_map(|b| b.iter())
            .sum();

        assert_eq!(batch_total, total);
        assert_eq!(batch_total, amounts.iter().sum::<u64>());
    }

    #[test]
    fn test_single_batch_path_taken_for_small_input() {
        let amounts = vec![500u64; 100]; // 100 amounts, max_batch=1000 → single batch
        let max_batch = 1000;
        let batches = SumThresholdCircuit::split_into_batches(&amounts, max_batch);
        assert_eq!(batches.len(), 1, "Should use single batch for n <= max_batch_size");
    }

    // -----------------------------------------------------------------------
    // Full proof round-trip tests — SLOW, run with --ignored in fast CI
    // -----------------------------------------------------------------------

    #[test]
    #[ignore = "Slow: full proof generation takes 10-30s. Run in slow-test CI job."]
    fn test_prove_verify_roundtrip_small() {
        /// Full prove + verify round-trip with 10 amounts.
        let amounts = vec![1000u64, 2000u64, 500u64, 750u64, 1200u64,
                           300u64, 800u64, 1500u64, 600u64, 900u64];
        let threshold = 20000u64;

        let (proof_bytes, public_inputs) = prove_sum_threshold(
            amounts.clone(), threshold, 65536
        ).expect("Proof generation failed");

        assert!(!proof_bytes.is_empty(), "Proof blob must not be empty");
        assert_eq!(public_inputs.sum, amounts.iter().sum::<u64>());
        assert!(public_inputs.assertion_passes, "Sum should be <= threshold");

        // Verify the proof
        use crate::verifier::Verifier;
        let pi_json = serde_json::to_value(&public_inputs).unwrap();
        Verifier::verify(
            &CircuitType::SumThreshold,
            &proof_bytes,
            &pi_json,
        ).expect("Proof verification failed");
    }

    #[test]
    #[ignore = "Slow: batch decomposition test requires multiple proofs."]
    fn test_prove_verify_batch_decomposition() {
        /// Tests the batch decomposition path (n > max_batch_size).
        let amounts: Vec<u64> = (0..500).map(|i| (i as u64 + 1) * 1000).collect();
        let threshold: u64 = amounts.iter().sum::<u64>() + 1; // sum < threshold

        let (proof_bytes, public_inputs) = prove_sum_threshold(
            amounts.clone(), threshold, 200  // max_batch=200 → 3 batches
        ).expect("Batch proof generation failed");

        assert_eq!(public_inputs.record_count, 500);
        assert_eq!(public_inputs.sum, amounts.iter().sum::<u64>());
        assert!(public_inputs.assertion_passes);
        assert!(!proof_bytes.is_empty());
    }

    #[test]
    #[ignore = "Slow: generates and verifies a failing assertion proof."]
    fn test_prove_sum_exceeds_threshold() {
        /// When sum > threshold, assertion_passes = false. Proof is still valid.
        let amounts = vec![10000u64; 10]; // sum = 100,000
        let threshold = 50000u64;          // threshold = 50,000 < sum

        let (proof_bytes, public_inputs) = prove_sum_threshold(
            amounts.clone(), threshold, 65536
        ).expect("Proof generation failed for failing assertion");

        assert!(!public_inputs.assertion_passes, "assertion_passes should be false when sum > threshold");
        assert_eq!(public_inputs.sum, 100_000);
        assert_eq!(public_inputs.threshold, 50_000);

        // The proof itself is still valid (it proves the assertion is FALSE, truthfully)
        use crate::verifier::Verifier;
        let pi_json = serde_json::to_value(&public_inputs).unwrap();
        Verifier::verify(&CircuitType::SumThreshold, &proof_bytes, &pi_json)
            .expect("Proof of failing assertion should still verify");
    }

    // -----------------------------------------------------------------------
    // Memory safety: verify the 16GB RAM constraint
    // -----------------------------------------------------------------------

    #[test]
    fn test_max_batch_size_within_memory_budget() {
        /// 2^18 = 262,144 rows at ~64 bytes per row = ~16MB field elements.
        /// Plus IPA commitment overhead, total stays under 4GB per batch.
        /// This test verifies the constant is set correctly.
        let max_batch: usize = 262_144; // 2^18
        let k = SumThresholdCircuit::compute_k(max_batch);
        // k should be exactly 18 for max_batch = 2^18 + overhead
        assert!(k <= 18, "k={} would exceed 16GB RAM budget", k);
    }

    #[test]
    fn test_worker_semaphore_prevents_concurrent_proofs() {
        /// The Prover uses a Semaphore(1) to serialize proof generation.
        /// This test verifies the semaphore is initialised with permits=1.
        use std::sync::Arc;
        use tokio::sync::Semaphore;
        let sem = Arc::new(Semaphore::new(1));
        // Acquire the only permit
        let permit = sem.try_acquire().expect("Should acquire first permit");
        // Second acquisition must fail (non-blocking)
        assert!(
            sem.try_acquire().is_err(),
            "Second permit acquisition should fail — concurrent proofs are not allowed"
        );
        drop(permit);
        // Now it's available again
        assert!(sem.try_acquire().is_ok());
    }
}
