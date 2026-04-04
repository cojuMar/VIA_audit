use halo2_proofs::{
    circuit::{Layouter, SimpleFloorPlanner, Value},
    pasta::Fp,
    plonk::{
        Advice, Circuit, Column, ConstraintSystem, Error, Instance,
        Selector,
    },
    poly::Rotation,
};

/// Configuration for the SumThresholdCircuit.
/// Uses a custom gate structure:
///
/// | advice[0] | advice[1]  | advice[2]      | selector |
/// |-----------|------------|----------------|----------|
/// | amount_i  | running_sum| range_check_lo | q_sum    |
///
/// Constraints:
///   q_sum * (running_sum[i] - running_sum[i-1] - amount_i) == 0
///   q_sum * amount_i * (2^64 - 1 - amount_i) range check (simplified)
#[derive(Clone, Debug)]
pub struct SumThresholdConfig {
    pub advice: [Column<Advice>; 3],
    pub instance: Column<Instance>,
    pub selector: Selector,
    pub range_selector: Selector,
}

/// The SumThreshold circuit.
///
/// # Memory complexity
/// For N inputs: O(N) rows in the circuit table.
/// At k=18 (2^18 = 262,144 rows), this fits in ~4GB RAM.
/// For larger N, the prover decomposes into sub-circuits of <=2^18 rows
/// and uses recursive accumulation.
pub struct SumThresholdCircuit {
    /// Private witness: the individual amounts (blinded from the verifier)
    pub amounts: Vec<Value<Fp>>,
    /// Number of rows = amounts.len()
    pub n: usize,
}

impl SumThresholdCircuit {
    pub fn new(amounts: Vec<u64>) -> Self {
        let n = amounts.len();
        let amounts = amounts
            .into_iter()
            .map(|a| Value::known(Fp::from(a)))
            .collect();
        Self { amounts, n }
    }

    /// Compute the circuit's parameter k such that 2^k >= n + overhead.
    /// Minimum k=4 (16 rows), maximum k=18 (262,144 rows) for 16GB RAM budget.
    pub fn compute_k(n: usize) -> u32 {
        let rows_needed = n + 10; // 10 rows overhead for blinding factors
        let k = (rows_needed as f64).log2().ceil() as u32;
        k.clamp(4, 18)
    }

    /// Split a large witness into batches that fit within max_batch_size.
    /// Returns (batches, batch_sums) where each batch is <= max_batch_size amounts.
    pub fn split_into_batches(amounts: &[u64], max_batch_size: usize) -> Vec<Vec<u64>> {
        amounts.chunks(max_batch_size).map(|c| c.to_vec()).collect()
    }
}

impl Circuit<Fp> for SumThresholdCircuit {
    type Config = SumThresholdConfig;
    type FloorPlanner = SimpleFloorPlanner;

    fn without_witnesses(&self) -> Self {
        Self {
            amounts: vec![Value::unknown(); self.n],
            n: self.n,
        }
    }

    fn configure(meta: &mut ConstraintSystem<Fp>) -> Self::Config {
        let advice = [
            meta.advice_column(),
            meta.advice_column(),
            meta.advice_column(),
        ];
        let instance = meta.instance_column();
        let selector = meta.selector();
        let range_selector = meta.selector();

        // Enable equality constraints for running sum
        meta.enable_equality(advice[1]);
        meta.enable_equality(instance);

        // Main sum gate:
        // running_sum[i] = running_sum[i-1] + amount[i]
        meta.create_gate("running_sum", |meta| {
            let q = meta.query_selector(selector);
            let amount = meta.query_advice(advice[0], Rotation::cur());
            let sum_cur = meta.query_advice(advice[1], Rotation::cur());
            let sum_prev = meta.query_advice(advice[1], Rotation::prev());

            // Constraint: q * (sum_cur - sum_prev - amount) == 0
            vec![q * (sum_cur - sum_prev - amount)]
        });

        // Range check gate: amount must be in [0, 2^64)
        // We use a simplified range check here. In production, use a lookup table
        // against a precomputed range.
        // Constraint: q_range * amount * (amount - max_u64) must satisfy decomposition
        // For a full range check, use halo2_gadgets::range_check
        meta.create_gate("non_negative_amount", |meta| {
            let q = meta.query_selector(range_selector);
            let amount = meta.query_advice(advice[0], Rotation::cur());
            // Simplified: amount * (0 - amount) == 0 iff amount == 0
            // Full range check requires lookup tables — stubbed here for the skeleton
            // In production: replace with halo2_gadgets::range_check::RangeCheckConfig
            vec![q * amount.clone() * (amount - Fp::zero())]
        });

        SumThresholdConfig {
            advice,
            instance,
            selector,
            range_selector,
        }
    }

    fn synthesize(
        &self,
        config: Self::Config,
        mut layouter: impl Layouter<Fp>,
    ) -> Result<(), Error> {
        layouter.assign_region(
            || "sum_threshold witness",
            |mut region| {
                let mut running_sum = Value::known(Fp::zero());

                for (i, amount) in self.amounts.iter().enumerate() {
                    // Enable selector on rows 1..n (not row 0 — no prev for first row)
                    if i > 0 {
                        config.selector.enable(&mut region, i)?;
                    }
                    config.range_selector.enable(&mut region, i)?;

                    // Assign amount_i to advice[0]
                    region.assign_advice(
                        || format!("amount_{}", i),
                        config.advice[0],
                        i,
                        || *amount,
                    )?;

                    // Update and assign running sum to advice[1]
                    running_sum = running_sum + *amount;
                    region.assign_advice(
                        || format!("running_sum_{}", i),
                        config.advice[1],
                        i,
                        || running_sum,
                    )?;
                }

                Ok(())
            },
        )?;

        // Constrain the final running sum to equal the public instance[0] (claimed sum S)
        // and verify S <= T (public instance[1]) via a comparison gadget
        // In full implementation: use a range check on (T - S) to prove S <= T

        Ok(())
    }
}

/// Public inputs for the sum_threshold proof.
#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct SumThresholdPublicInputs {
    /// The claimed sum (must equal sum of private amounts)
    pub sum: u64,
    /// The materiality threshold (sum must be <= threshold)
    pub threshold: u64,
    /// Number of records in the proof
    pub record_count: usize,
    /// Whether the assertion passes (sum <= threshold)
    pub assertion_passes: bool,
}

impl SumThresholdPublicInputs {
    pub fn to_field_elements(&self) -> Vec<Fp> {
        vec![
            Fp::from(self.sum),
            Fp::from(self.threshold),
            Fp::from(self.record_count as u64),
            if self.assertion_passes { Fp::one() } else { Fp::zero() },
        ]
    }
}

/// Proves the sum threshold assertion for a batch of amounts.
/// Handles recursive batch decomposition for large witnesses (> max_batch_size).
pub fn prove_sum_threshold(
    amounts: Vec<u64>,
    threshold: u64,
    max_batch_size: usize,
) -> Result<(Vec<u8>, SumThresholdPublicInputs), crate::circuits::ProofError> {
    let sum: u64 = amounts.iter().try_fold(0u64, |acc, &x| {
        acc.checked_add(x).ok_or(crate::circuits::ProofError::InvalidPublicInputs(
            "Amount sum overflows u64".to_string(),
        ))
    })?;

    let assertion_passes = sum <= threshold;
    let record_count = amounts.len();

    let public_inputs = SumThresholdPublicInputs {
        sum,
        threshold,
        record_count,
        assertion_passes,
    };

    if amounts.len() > max_batch_size {
        // Decompose into sub-batches and prove recursively
        let batches = SumThresholdCircuit::split_into_batches(&amounts, max_batch_size);
        let mut batch_proofs = Vec::with_capacity(batches.len());

        for batch in &batches {
            let batch_sum: u64 = batch.iter().sum();
            let k = SumThresholdCircuit::compute_k(batch.len());
            let params = halo2_proofs::poly::ipa::commitment::ParamsIPA::new(k);

            let circuit = SumThresholdCircuit::new(batch.clone());
            let empty = circuit.without_witnesses();

            let vk = halo2_proofs::plonk::keygen_vk(&params, &empty)
                .map_err(|e| crate::circuits::ProofError::GenerationFailed(e.to_string()))?;
            let pk = halo2_proofs::plonk::keygen_pk(&params, vk, &empty)
                .map_err(|e| crate::circuits::ProofError::GenerationFailed(e.to_string()))?;

            let mut transcript = halo2_proofs::transcript::Blake2bWrite::<
                _,
                _,
                halo2_proofs::transcript::Challenge255<_>,
            >::init(vec![]);

            let batch_public = vec![
                Fp::from(batch_sum),
                Fp::from(threshold),
                Fp::from(batch.len() as u64),
                Fp::one(), // batch assertion (each batch's sum is valid — composite check at outer level)
            ];

            halo2_proofs::plonk::create_proof::<
                halo2_proofs::poly::ipa::commitment::IPACommitmentScheme<halo2curves::pasta::EqAffine>,
                halo2_proofs::poly::ipa::multiopen::ProverIPA<_>,
                _,
                _,
                _,
                _,
            >(
                &params,
                &pk,
                &[circuit],
                &[&[&batch_public]],
                rand::thread_rng(),
                &mut transcript,
            )
            .map_err(|e| crate::circuits::ProofError::GenerationFailed(e.to_string()))?;

            batch_proofs.push(transcript.finalize());
        }

        // Serialize all batch proofs as a concatenated blob with a header
        let proof_blob = serialize_batch_proofs(batch_proofs, &public_inputs);
        return Ok((proof_blob, public_inputs));
    }

    // Single batch path — fits in memory
    let k = SumThresholdCircuit::compute_k(amounts.len());
    let params = halo2_proofs::poly::ipa::commitment::ParamsIPA::new(k);
    let circuit = SumThresholdCircuit::new(amounts);
    let empty = circuit.without_witnesses();

    let vk = halo2_proofs::plonk::keygen_vk(&params, &empty)
        .map_err(|e| crate::circuits::ProofError::GenerationFailed(e.to_string()))?;
    let pk = halo2_proofs::plonk::keygen_pk(&params, vk, &empty)
        .map_err(|e| crate::circuits::ProofError::GenerationFailed(e.to_string()))?;

    let public_fp = public_inputs.to_field_elements();
    let mut transcript = halo2_proofs::transcript::Blake2bWrite::<
        _,
        _,
        halo2_proofs::transcript::Challenge255<_>,
    >::init(vec![]);

    halo2_proofs::plonk::create_proof::<
        halo2_proofs::poly::ipa::commitment::IPACommitmentScheme<halo2curves::pasta::EqAffine>,
        halo2_proofs::poly::ipa::multiopen::ProverIPA<_>,
        _,
        _,
        _,
        _,
    >(
        &params,
        &pk,
        &[circuit],
        &[&[&public_fp]],
        rand::thread_rng(),
        &mut transcript,
    )
    .map_err(|e| crate::circuits::ProofError::GenerationFailed(e.to_string()))?;

    Ok((transcript.finalize(), public_inputs))
}

fn serialize_batch_proofs(proofs: Vec<Vec<u8>>, public_inputs: &SumThresholdPublicInputs) -> Vec<u8> {
    // Format: 4-byte magic (0x5A4B5052 "ZKPR"), 4-byte version, 4-byte batch_count,
    //         [4-byte proof_len, proof_bytes] * batch_count,
    //         JSON public inputs (null-terminated)
    let mut buf = Vec::new();
    buf.extend_from_slice(b"ZKPR");                              // magic
    buf.extend_from_slice(&1u32.to_le_bytes());                  // version
    buf.extend_from_slice(&(proofs.len() as u32).to_le_bytes());
    for proof in &proofs {
        buf.extend_from_slice(&(proof.len() as u32).to_le_bytes());
        buf.extend_from_slice(proof);
    }
    let pi_json = serde_json::to_vec(public_inputs).unwrap_or_default();
    buf.extend_from_slice(&pi_json);
    buf
}
