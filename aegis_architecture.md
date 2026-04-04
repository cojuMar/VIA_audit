# Project Aegis 2026: Technical Architecture Document

## Executive Summary

Project Aegis 2026 is a Tri-Modal Multi-Tenant Audit and AI Compliance platform targeting mathematical proof of control through continuous assurance. The architecture must simultaneously satisfy mutually-tensioned requirements: cryptographic certainty in evidence chains, sub-second UX across 1000+ clients, regulatory immutability, and quantum-resistant security posture. This document resolves those tensions through explicit architectural trade-offs.

The platform serves three personas with fundamentally different threat models and latency budgets: Audit Firms (aggregate visibility, white-labeling, cross-client analytics), SMBs (self-service compliance, evidence collection, readiness scoring), and Autonomous Mode (real-time health monitoring with minimal human intervention). Each mode requires distinct data access patterns, rendering the naive "one schema fits all" approach architecturally unsound.

---

## 1. Overall System Architecture

### 1.1 Deployment Topology

The system deploys as a cloud-native, region-aware platform on a primary cloud provider (AWS recommended for SOC 2 alignment, with GCP as secondary for specific AI workloads). The topology separates planes of control to enforce the Chinese Wall principle at the infrastructure layer, not merely at the application layer.

```
Internet Edge
    |
[CloudFront/Global Load Balancer]
    |
[WAF + DDoS Shield + Prompt Injection Filter (Sprint 7)]
    |
[API Gateway Cluster] ── [JWT Validation Service] ── [Token Store (Redis Cluster)]
    |
[Service Mesh (Istio/Envoy)] ── mTLS between all internal services
    |
┌──────────────────────────────────────────────────────────────┐
│                    Application Plane                          │
│  [Auth Service]  [Ingestion Service]  [Audit Engine]         │
│  [ZK-Proof Worker Pool]  [ML Inference]  [RAG Pipeline]      │
│  [Reporting Service]  [UX BFF (per mode)]                    │
└──────────────────────────────────────────────────────────────┘
    |
┌──────────────────────────────────────────────────────────────┐
│                    Data Plane                                 │
│  [PostgreSQL Cluster - Pool Model (SMB)]                     │
│  [PostgreSQL Cluster - Siloed Schemas (Enterprise)]          │
│  [TimescaleDB - Time-series Evidence]                        │
│  [Weaviate/pgvector - RAG Vector Store]                      │
│  [S3-compatible WORM Object Store]                           │
│  [Redis Cluster - Token/Cache]                               │
└──────────────────────────────────────────────────────────────┘
    |
[PAM Broker] ── [HashiCorp Vault] ── [FIDO2 Identity Provider]
```

### 1.2 Service Decomposition

The platform decomposes into twelve bounded-context services organized around domain capability rather than technical layer:

**Identity and Access Plane**
- `auth-service`: FIDO2/WebAuthn registration and assertion, JWT issuance with tenant_id and role claims, session management
- `pam-broker`: JIT privilege escalation, short-lived certificate issuance, TTL enforcement, audit logging of all privileged sessions
- `tenant-registry`: Tenant onboarding, tier assignment (Pool vs. Silo), feature flag management

**Evidence and Data Plane**
- `ingestion-orchestrator`: Connector registry for 400+ tools, polling scheduler, webhook receiver, normalization pipeline
- `evidence-store`: Immutable append-only evidence records, hash-chaining, WORM tier promotion
- `zk-proof-worker`: Circuit compilation, proof generation, verification endpoint

**Intelligence Plane**
- `forensic-ml-service`: Ensemble model inference, anomaly scoring, Benford's Law evaluation, Dynamic Risk Index computation
- `rag-pipeline-service`: Retrieval, generation, faithfulness scoring, HITL escalation

**UX Delivery Plane**
- `firm-bff`: Backend for Frontend serving Firm Mode aggregations
- `smb-bff`: Backend for Frontend serving SMB Mode compliance workflows
- `autonomous-bff`: Backend for Frontend serving real-time health scores
- `reporting-service`: XBRL/iXBRL generation, SAF-T export, GIFI mapping, PDF compilation

### 1.3 Inter-Service Communication

Synchronous calls (user-facing latency-sensitive paths) use gRPC over the service mesh with mTLS. All calls carry a propagated JWT; the receiving service re-validates tenant_id against its own copy of the public key set — no implicit trust between services.

Asynchronous event flows (evidence ingestion, ML inference triggers, ZK proof generation) use Apache Kafka with tenant_id as a partition key. This ensures tenant data never co-mingles in processing buffers. Consumer groups are scoped per-service, and Kafka ACLs enforce that consumers can only read their designated topics.

Schema Registry (Confluent or Apicurio) enforces Avro schema compatibility across all event types. Breaking schema changes require explicit versioning and a migration window.

---

## 2. Technology Stack Decisions by Sprint

### Sprint 1: Chinese Wall and Access Architecture

**PostgreSQL 16 with Row-Level Security** — chosen over alternatives (CockroachDB, PlanetScale) because RLS is a first-class server-side primitive. Critically, RLS policies execute inside the query planner, meaning a compromised application layer cannot bypass them by crafting raw SQL. The `current_setting('app.tenant_id')` session variable is set by the connection pool manager from the validated JWT claim before any query executes. CockroachDB's RLS support is still maturing as of 2025; PlanetScale's MySQL lineage lacks native RLS.

**PgBouncer in transaction-mode pooling** for the Pool Model (SMB tier). Transaction-mode is mandatory here: session-mode pooling would hold a connection for the duration of a WebSocket session, destroying connection efficiency. The trade-off is that prepared statements and `SET` for session variables must be re-issued per transaction. The `app.tenant_id` variable must therefore be set within every transaction, enforced by a middleware interceptor at the repository layer.

**Separate PostgreSQL schema per enterprise tenant (Silo Model)** rather than separate databases. Separate schemas allow a single PostgreSQL cluster to serve enterprise tenants while enabling schema-level isolation, per-tenant migrations, and per-tenant backup/restore. Separate databases would require connection pools per database, creating O(N) connection overhead. The Bridge Model uses a cross-schema view layer for firm-level aggregation queries, with RLS enforcing that a firm can only access schemas belonging to their client set.

**HashiCorp Vault with the PKI Secrets Engine** for JIT certificate issuance. Vault's dynamic secrets model means no long-lived credentials exist at rest. Auditor roles receive a Vault token with a 4-8 hour TTL; infrastructure roles receive certificates with a 5-15 minute TTL via the `vault write pki/issue` path. Certificate revocation uses OCSP stapling rather than CRL polling to minimize revocation latency.

**Ory Kratos + Ory Hydra** for identity and OAuth2/OIDC. Kratos handles identity lifecycle (registration, recovery, MFA enrollment) with native FIDO2/WebAuthn support via the `webauthn` strategy. Hydra provides the OAuth2 authorization server for third-party integrations. This combination is preferred over Auth0/Okta for on-premises deployment flexibility and avoidance of per-MAU pricing at scale.

**FIDO2/WebAuthn** replaces TOTP for all admin and auditor roles. The critical architectural decision is storing authenticator credential IDs and public keys in the `auth-service` database (not in the tenant's data plane), ensuring that a tenant database breach does not yield authentication material.

### Sprint 2: Zero-Touch Evidence Engine

**Apache Airflow 2.x with the Kubernetes executor** for ingestion orchestration. The Kubernetes executor spins up isolated pods per connector task, providing process-level isolation between tenant data streams. This is preferable to Celery (shared process pool) for a multi-tenant compliance context where evidence from different tenants must never share memory space. Airflow's DAG model naturally represents the ingestion pipeline: fetch, normalize, hash, sign, store.

**Connector SDK pattern**: Each of the 400+ integrations is a Python package implementing a standardized `ConnectorBase` interface with methods for `fetch_incremental`, `fetch_full`, `normalize_to_canonical`, and `test_connection`. New connectors are deployed as container images without core platform changes.

**Canonical Evidence Schema** uses JSON Schema Draft 2020-12 with a strict required fields contract: `evidence_id` (UUIDv7 for temporal ordering), `tenant_id`, `source_system`, `collected_at_utc`, `payload_hash` (SHA-256 of raw payload), `canonical_payload`, `collector_version`, `chain_hash` (SHA-256 of previous record's chain_hash XOR current payload_hash). The chain_hash field implements the hash-chain for tamper evidence.

**ZK-Proof architecture** requires significant design depth and is addressed in Section 4.

**Halo2 proving system** (Zcash Foundation) rather than Groth16 or PLONK for the primary ZK circuit library. Halo2 offers trusted-setup-free proofs (eliminating the ceremony coordination problem), polynomial commitment via IPA (Inner Product Argument) which is more memory-efficient than KZG at the proof sizes relevant here (thousands of constraints, not millions), and an active Rust ecosystem. The trade-off is larger proof sizes than Groth16 for equivalent constraint counts — acceptable given that proofs are stored in WORM storage rather than transmitted in every API response.

For the 16GB RAM optimization requirement: Halo2's prover operates on field arithmetic over BN254 or Pasta curves. A circuit with 2^20 constraints (approximately 1M gates, sufficient for a 1000-row ledger proof) requires approximately 8-12GB of RAM for witness generation and proof construction. Fitting this within 16GB requires circuit decomposition into sub-circuits proved recursively, with each sub-circuit sized to 2^18 constraints (~4GB working set).

### Sprint 3: Forensic AI and Anomaly Detection

**Python ML stack on dedicated GPU/CPU nodes** separated from the application plane. The model inference service is stateless from the application's perspective — it receives a feature vector, returns a score. Models are versioned in MLflow and loaded into memory per-worker.

**Autoencoder architecture**: A variational autoencoder (VAE) rather than a plain autoencoder, because VAEs produce a continuous latent space that enables anomaly scoring via reconstruction probability rather than just reconstruction error. A plain autoencoder's reconstruction error threshold is brittle across different transaction volume regimes; the VAE's ELBO-based scoring adapts better to distribution shifts.

**Isolation Forest** from scikit-learn as the second ensemble member. Critical implementation note: Isolation Forests must be trained per-tenant or per-industry-cohort, not globally. A global model trained on all tenants would violate the Chinese Wall (tenant data used to train a model that scores another tenant) and would perform poorly due to distribution mismatch between, say, a retail SMB and a financial services enterprise.

**Benford's Law implementation**: P(d) = log10(1 + 1/d) for d in {1..9}. The chi-squared test against the theoretical distribution is straightforward, but the critical architectural decision is the granularity of application: apply Benford's at the account-level, not the entity level. Applying it to total revenue masks the signal. It should be applied to: individual GL account balances by period, invoice amounts by vendor, expense report line items by employee. The chi-squared p-value and the mean absolute deviation (MAD) from the theoretical distribution both feed into the Dynamic Risk Index.

**Dynamic Risk Index formula** requires normalization. Each component (vendor age, round-number frequency, weekend activity, rare account interactions, jurisdictional risk) is scored 0-1 using a sigmoid transform on the raw metric. The composite score is a weighted sum where weights are configured per compliance framework (SOC 2 weights differ from ISO 27001). Weights are stored in the tenant's configuration schema, not hard-coded.

### Sprint 4: Generative Audit Logic and Guardrails

**Claude API (Anthropic)** as the generation model. The architectural implication is that audit findings generation is an API call, not a locally-hosted model. This creates a data residency consideration: the prompt includes evidence excerpts. The RAG retrieval step must filter evidence to only include excerpts necessary for the specific finding, minimizing the data surface area sent to the external API. For tenants with strict data residency requirements (EU GDPR Article 46), the evidence excerpts must be anonymized or summarized before leaving the tenant's data region.

**pgvector extension on PostgreSQL** for vector storage rather than a dedicated vector database (Pinecone, Weaviate) at initial scale. The rationale: evidence records already live in PostgreSQL; co-locating vector embeddings eliminates a network hop and allows transactional consistency between evidence records and their embeddings. The trade-off is that pgvector's HNSW index performance degrades beyond ~10M vectors — at that scale, migrating to Weaviate or Qdrant is warranted. The migration path is straightforward because the embedding model and schema are decoupled from the storage layer.

**Embedding model**: `text-embedding-3-large` (OpenAI) or `voyage-finance-2` (Voyage AI, specialized for financial/legal text). The finance-specialized model is preferred for production because audit evidence contains domain-specific terminology (GAAP, IFRS, SOC 2 control categories) where general-purpose embeddings underperform.

**Faithfulness and Groundedness scoring**: RAGAS framework for automated evaluation. Faithfulness measures whether each claim in the generated finding can be attributed to a retrieved evidence chunk. Groundedness measures whether the finding is supported by the evidence. The threshold of 0.45 triggering HITL is a percentile threshold on the combined score distribution — this threshold should be calibrated on a labeled dataset of known-good and known-hallucinated findings before production deployment.

### Sprint 5: Tri-Modal UX

**React 18 with Next.js 14** (App Router) for the frontend, with three separate Next.js applications (one per mode) sharing a component library. Separate applications rather than a single application with mode-switching: the security posture is stronger (Firm Mode's aggregate data never loads in an SMB session's JavaScript bundle), and deployment boundaries are cleaner.

**TanStack Query (React Query)** for server state management. Given that the dashboard shows live data from hundreds of clients, the stale-while-revalidate pattern with configurable refetch intervals per widget is essential. The alternative (Redux with polling sagas) adds unnecessary complexity.

**D3.js for heatmaps** in Firm Mode. The 1000+ client heatmap requires WebGL-accelerated rendering at scale. `d3-force` with canvas rendering (not SVG) at this client count; SVG DOM with 1000+ elements causes frame drops. Observable Plot as the higher-level wrapper over D3 for standard chart types.

**Server-Sent Events (SSE)** rather than WebSockets for the Autonomous Mode real-time health scores. SSE is unidirectional (server to client), which matches the use case (server pushes score updates; client does not send real-time data). SSE works through HTTP/2 multiplexing, simplifying infrastructure compared to WebSocket upgrade negotiation. WebSockets are reserved for the interactive audit workflow (HITL review) where bidirectional communication is required.

### Sprint 6: Immutable Output and Reporting

**AWS S3 Object Lock (Compliance mode)** or **MinIO with WORM configuration** for self-hosted deployments. Compliance mode (not Governance mode) is required because Governance mode allows administrators to delete objects — violating the "immutable" requirement. The retention period is configurable per regulatory framework: SOC 2 typically requires 1 year, HIPAA requires 6 years.

**Apache FOP or iText 7** for PDF generation. iText 7 is preferred for XBRL/iXBRL because it has native support for PDF/A (archival format) and digital signatures (PAdES). XBRL generation uses the Arelle library (Python) with the SEC's EDGAR taxonomy for US entities and the ESMA taxonomy for EU entities.

**SAF-T generation**: The SAF-T schema is XML-based (OECD standard). The reporting service transforms the canonical evidence schema to SAF-T XML using XSLT. Country-specific variations (Norway, Portugal, Austria have distinct SAF-T profiles) are handled via different XSLT stylesheets, selected based on tenant jurisdiction in the tenant registry.

### Sprint 7: Security and MAESTRO

**CRYSTALS-Kyber (ML-KEM, FIPS 203)** for key encapsulation and **CRYSTALS-Dilithium (ML-DSA, FIPS 204)** for digital signatures — both standardized by NIST in August 2024. Implementation via the **liboqs** library (Open Quantum Safe project) with the Go or Rust bindings. Critical note: lattice-based signatures are 2-5x larger than ECDSA signatures. The hash-chain records in the evidence store use Dilithium-3 signatures (NIST security level 3, approximately 3.3KB signature size). This is acceptable for WORM storage but requires XBRL export tooling to handle larger signature blobs.

**Hybrid classical/post-quantum key exchange** during the transition period: X25519 + Kyber-768 (X25519Kyber768Draft00 TLS extension). This provides protection against harvest-now/decrypt-later attacks while maintaining compatibility with existing TLS infrastructure.

---

## 3. Database Schema Patterns for Hybrid Multi-Tenant Model

### 3.1 Pool Model (SMB Tier)

The Pool Model uses a single PostgreSQL schema (`public` or `shared`) with RLS policies enforcing tenant isolation. Every table in this schema includes a `tenant_id UUID NOT NULL` column with an index.

The RLS policy pattern is consistent across all tables:

```sql
-- Applied to every table in the pool model
CREATE POLICY tenant_isolation ON evidence_records
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE evidence_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_records FORCE ROW LEVEL SECURITY;
-- FORCE RLS applies even to table owners, closing the superuser bypass loophole
```

The `FORCE ROW LEVEL SECURITY` directive is critical. Without it, a connection authenticated as the table owner (e.g., a service account used for migrations) bypasses RLS entirely. The Sprint 7 CI/CD tests must verify that `FORCE ROW LEVEL SECURITY` is active on all tenant-scoped tables.

Connection pool configuration for PgBouncer in transaction mode:

```
-- pgbouncer.ini (relevant section)
pool_mode = transaction
server_reset_query = RESET ALL; SET app.tenant_id = '';
-- The server_reset_query runs between transactions, clearing the tenant context
```

The application middleware layer must set `app.tenant_id` as the first statement in every transaction:

```sql
BEGIN;
SET LOCAL app.tenant_id = '{{validated_jwt_tenant_id}}';
-- All subsequent queries in this transaction are scoped to this tenant
SELECT * FROM evidence_records WHERE collected_at > NOW() - INTERVAL '24 hours';
COMMIT;
```

`SET LOCAL` (not `SET`) scopes the variable to the transaction, ensuring it is cleared on commit or rollback even if the application code fails to clean up.

### 3.2 Silo Model (Enterprise Tier)

Each enterprise tenant receives a dedicated PostgreSQL schema named `tenant_{tenant_id_prefix}`. The schema is created during tenant provisioning by the `tenant-registry` service executing a Liquibase migration against the enterprise cluster.

The Bridge Model for firm-level aggregation uses PostgreSQL's cross-schema view capability:

```sql
-- In the firm's aggregation schema
CREATE VIEW firm_risk_summary AS
    SELECT 'client_a' as client_id, risk_index, computed_at 
    FROM tenant_abc123.risk_scores
    WHERE computed_at > NOW() - INTERVAL '7 days'
UNION ALL
    SELECT 'client_b' as client_id, risk_index, computed_at
    FROM tenant_def456.risk_scores  
    WHERE computed_at > NOW() - INTERVAL '7 days';

-- RLS on this view scopes it to the firm's tenant_id
-- The firm's JWT must include both firm_id and client_id claims
```

The firm's JWT claims structure:

```json
{
  "sub": "user_uuid",
  "tenant_id": "firm_tenant_uuid",
  "role": "auditor",
  "client_access": ["client_tenant_uuid_1", "client_tenant_uuid_2"],
  "iat": 1700000000,
  "exp": 1700028800,
  "jti": "unique_token_id"
}
```

The `client_access` claim is a signed claim — the application validates it against the firm's authorization record before constructing the Bridge View query. This prevents a compromised JWT from claiming access to arbitrary client tenants.

### 3.3 Core Evidence Schema

```sql
-- Pool model table (enterprise equivalent is identical structure, different schema)
CREATE TABLE evidence_records (
    evidence_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    source_system       TEXT NOT NULL,          -- 'aws_cloudtrail', 'quickbooks', etc.
    collected_at_utc    TIMESTAMPTZ NOT NULL,
    payload_hash        BYTEA NOT NULL,          -- SHA-256 of raw_payload
    canonical_payload   JSONB NOT NULL,
    chain_hash          BYTEA NOT NULL,          -- Hash-chain field
    chain_sequence      BIGINT NOT NULL,         -- Monotonic per tenant
    collector_version   TEXT NOT NULL,
    zk_proof_id         UUID REFERENCES zk_proofs(proof_id),
    dilithium_signature BYTEA,                   -- Post-quantum signature
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Partial index for recent evidence (hot path)
CREATE INDEX idx_evidence_tenant_recent 
    ON evidence_records (tenant_id, collected_at_utc DESC)
    WHERE collected_at_utc > NOW() - INTERVAL '90 days';

-- The chain_sequence must be enforced as monotonic per tenant
-- Use a SEQUENCE per tenant in the silo model, or a distributed counter in the pool model
CREATE TABLE chain_sequence_counters (
    tenant_id   UUID PRIMARY KEY,
    next_seq    BIGINT NOT NULL DEFAULT 1
);
```

### 3.4 TimescaleDB for Time-Series Evidence

Continuous monitoring at hourly cadence generates high-cardinality time-series data unsuitable for standard PostgreSQL heap tables. TimescaleDB (PostgreSQL extension) provides automatic partitioning via hypertables:

```sql
-- Convert evidence_records to a hypertable
SELECT create_hypertable('evidence_records', 'collected_at_utc',
    chunk_time_interval => INTERVAL '1 day',
    partitioning_column => 'tenant_id',
    number_partitions => 16);

-- Continuous aggregates for the Firm Mode dashboard
CREATE MATERIALIZED VIEW hourly_risk_summary
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', collected_at_utc) AS bucket,
    tenant_id,
    source_system,
    COUNT(*) AS record_count,
    AVG((canonical_payload->>'anomaly_score')::float) AS avg_anomaly_score
FROM evidence_records
GROUP BY bucket, tenant_id, source_system;
```

---

## 4. ZK-Proof Implementation Approach

### 4.1 What to Prove

The ZK-proof system serves a specific purpose: proving that a set of evidence records satisfies a compliance assertion without revealing the underlying business data. For example:

- "The sum of all expense transactions in GL account 5XXX over Q3 is within the materiality threshold" — proved without revealing individual transaction amounts
- "No transaction in the payroll run exceeds the per-employee cap defined in policy" — proved without revealing individual salaries
- "All access log events were generated by authenticated sessions" — proved without revealing session tokens

This scope — proving properties of aggregates and policy compliance — determines the circuit design.

### 4.2 Circuit Architecture

Each compliance assertion type corresponds to a circuit. The circuit registry stores circuit definitions as Halo2 `ConstraintSystem` configurations. The `zk-proof-worker` service loads the appropriate circuit for a given assertion type.

A representative circuit for the "sum within threshold" assertion:

The circuit takes as private inputs (witness): an array of N transaction amounts `[a_1, ..., a_N]`. The public inputs (instance): the claimed sum S, the materiality threshold T, and the Merkle root of the evidence record hashes.

The circuit enforces:
1. **Range constraints**: Each `a_i` is in [0, 2^64) — prevents overflow attacks
2. **Sum constraint**: `a_1 + ... + a_N = S` — enforces the claimed sum
3. **Threshold constraint**: `S <= T` — enforces the compliance assertion
4. **Merkle membership**: Each `a_i` is extracted from a leaf in the Merkle tree with the claimed root — binds the proof to specific evidence records

The Merkle tree uses Poseidon hash (designed for ZK circuits, 3-5x fewer constraints than SHA-256 in a circuit context). The Merkle root is recorded in the evidence store at ingestion time by the `evidence-store` service.

### 4.3 Memory Optimization for 16GB RAM

The 16GB constraint requires recursive proof composition. A single circuit over 2^20 constraints exceeds 12GB during proof generation. The solution:

**Batch decomposition**: Split N evidence records into batches of K records (K sized to fit in 2^18 constraints, approximately 4GB). Generate an inner proof for each batch. Compose inner proofs into an outer proof using Halo2's accumulation scheme (IPA accumulation).

The outer circuit takes as inputs the K inner proof accumulators and verifies them collectively. This reduces the outer circuit's constraint count to O(K * verifier_constraint_cost) rather than O(N * constraint_cost).

**Worker pool sizing**: The `zk-proof-worker` Kubernetes deployment requests 14GB RAM per pod with a 16GB limit. Pod autoscaling is horizontal (more pods) not vertical — a single pod never exceeds 16GB. Proof generation jobs are queued in Kafka; workers pull jobs and process them sequentially within a pod.

### 4.4 Proof Storage and Verification

Proofs are stored in the WORM object store as binary blobs. The `evidence_records` table's `zk_proof_id` column references the `zk_proofs` table:

```sql
CREATE TABLE zk_proofs (
    proof_id        UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL,
    circuit_type    TEXT NOT NULL,      -- 'sum_threshold', 'access_log', etc.
    circuit_version TEXT NOT NULL,
    public_inputs   JSONB NOT NULL,     -- The verifiable claims
    proof_blob_uri  TEXT NOT NULL,      -- S3/WORM object URI
    proof_hash      BYTEA NOT NULL,     -- SHA-256 of proof_blob
    verified_at     TIMESTAMPTZ,
    verifier_output BOOLEAN,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

Verification is a cheap operation (milliseconds) compared to proof generation (minutes). The `reporting-service` verifies proofs before including them in exported audit reports, providing an independent verification step.

---

## 5. ML Pipeline Architecture for Forensic Engine

### 5.1 Pipeline Overview

The ML pipeline is a five-stage process: feature extraction, model inference, ensemble aggregation, risk index computation, and result persistence. Each stage is a separate microservice responsibility to enable independent scaling and model updates without pipeline disruption.

### 5.2 Feature Extraction

The `forensic-ml-service` receives a `TenantEvidenceWindow` event from Kafka, containing a reference to a 24-hour window of evidence records for a tenant. It executes the following feature computations against the evidence store:

**Transaction-level features** (computed per transaction):
- `amount_log`: log10(|amount|) — compressed scale for the autoencoder
- `is_round_number`: Boolean, amount modulo 1000 == 0
- `day_of_week`: 0-6, with 5 and 6 (weekend) flagged
- `hour_of_day`: 0-23, with hours outside 7-19 flagged
- `vendor_age_days`: Days since first transaction with this vendor in the tenant's history
- `account_interaction_frequency`: Percentile rank of this account pair's interaction frequency
- `jurisdictional_risk_score`: Static lookup from the risk score table populated during vendor onboarding

**Entity-level features** (computed per vendor/employee):
- `benford_mad`: Mean Absolute Deviation from Benford's distribution over trailing 90 days of amounts
- `benford_chi2_pvalue`: Chi-squared test p-value
- `transaction_velocity_z`: Z-score of transaction count in this window vs. trailing 12-week mean
- `amount_variance_z`: Z-score of amount variance in this window vs. trailing 12-week mean

### 5.3 Autoencoder (VAE) Architecture

Input dimension: 12 features (the transaction-level features above, normalized). Encoder: three fully-connected layers (128 → 64 → 32) with ReLU activations. Latent space: 16-dimensional (mean and log-variance vectors). Decoder: mirror of encoder (32 → 64 → 128 → 12) with sigmoid output.

Anomaly score = negative ELBO = reconstruction loss + KL divergence. Transactions with scores in the top 5th percentile of the tenant's trailing 30-day distribution are flagged.

Training cadence: weekly retraining per tenant using the trailing 6 months of labeled (human-reviewed) transactions. MLflow tracks model versions; the `forensic-ml-service` loads the latest production-tagged model at startup. A/B testing between model versions is supported via feature flags in the tenant configuration.

### 5.4 Isolation Forest

Parameters: `n_estimators=200`, `contamination='auto'`, `max_samples=256`. The `max_samples=256` parameter is critical for performance — larger values increase accuracy marginally but increase prediction time super-linearly.

The Isolation Forest receives the same 12-dimensional feature vector as the VAE. Its score is the anomaly score from `decision_function()`, normalized to [0, 1] via a min-max scaler fitted on the training set.

### 5.5 Benford's Law Engine

Applied at entity level, not transaction level. For each vendor with at least 30 transactions in the trailing 90 days (minimum sample for statistical validity):

```python
from scipy.stats import chisquare
import numpy as np

def benford_score(amounts: list[float]) -> dict:
    # Extract first significant digits
    first_digits = [int(str(abs(a)).lstrip('0').replace('.','')[0]) 
                    for a in amounts if a != 0]
    
    observed_freq = np.bincount(first_digits, minlength=10)[1:]  # digits 1-9
    observed_prob = observed_freq / len(first_digits)
    
    expected_prob = np.array([np.log10(1 + 1/d) for d in range(1, 10)])
    
    # MAD: key metric for financial audit (Nigrini threshold: <0.006 conforming)
    mad = np.mean(np.abs(observed_prob - expected_prob))
    
    # Chi-squared (sensitive to sample size, use MAD as primary metric)
    chi2_stat, p_value = chisquare(observed_freq, 
                                    f_exp=expected_prob * len(first_digits))
    
    return {
        'mad': mad,
        'chi2_pvalue': p_value,
        'conforming': mad < 0.006,  # Nigrini's threshold
        'risk_level': 'high' if mad > 0.015 else 'medium' if mad > 0.006 else 'low'
    }
```

### 5.6 Ensemble Aggregation and Dynamic Risk Index

The three model scores are combined using a learned meta-classifier (logistic regression trained on human-labeled anomalies) rather than a fixed weighted average. The meta-classifier input is the three model scores plus the entity-level Benford metrics.

Dynamic Risk Index (DRI) computation:

```
DRI = sigmoid(
    w1 * normalized_vae_score +
    w2 * normalized_isolation_score +
    w3 * benford_risk_encoded +
    w4 * vendor_age_risk +
    w5 * round_number_frequency +
    w6 * weekend_activity_ratio +
    w7 * rare_account_interaction_score +
    w8 * jurisdictional_risk_score
    + bias
)
```

Weights `w1..w8` and `bias` are the logistic regression parameters. Per-framework weight overrides in tenant configuration are applied as multiplicative adjustments to the learned weights before normalization.

---

## 6. RAG Pipeline with Hallucination Guardrail

### 6.1 Pipeline Architecture

The RAG pipeline is a six-stage process with a quality gate between generation and delivery:

```
[Finding Request] 
    → [Context Retrieval] 
    → [Context Ranking + Deduplication]
    → [Prompt Construction]
    → [Claude API Generation]
    → [Faithfulness + Groundedness Scoring]
    → [Score < 0.45? → HITL Queue : Delivery]
```

### 6.2 Context Retrieval

Evidence chunks are pre-processed into 512-token chunks with 64-token overlap (to preserve context at chunk boundaries) by the ingestion pipeline at ingest time. Each chunk is embedded using the finance-specialized embedding model and stored in pgvector.

Retrieval uses hybrid search: dense vector similarity (cosine distance in pgvector) combined with sparse BM25 (PostgreSQL full-text search with `tsvector`) via reciprocal rank fusion. Neither pure semantic search nor pure keyword search is sufficient for audit evidence — technical terms like account codes and control identifiers require exact matching (BM25), while conceptual similarity requires semantic search.

```sql
-- Hybrid retrieval query (simplified)
WITH dense_results AS (
    SELECT evidence_id, 
           1 - (embedding <=> query_embedding) AS score,
           chunk_text
    FROM evidence_chunks
    WHERE tenant_id = current_setting('app.tenant_id')::uuid
    ORDER BY embedding <=> query_embedding
    LIMIT 50
),
sparse_results AS (
    SELECT evidence_id,
           ts_rank(tsv_content, query_tsv) AS score,
           chunk_text
    FROM evidence_chunks
    WHERE tenant_id = current_setting('app.tenant_id')::uuid
      AND tsv_content @@ query_tsv
    ORDER BY score DESC
    LIMIT 50
),
-- Reciprocal rank fusion
rrf AS (
    SELECT evidence_id,
           SUM(1.0 / (60 + rank)) AS rrf_score
    FROM (
        SELECT evidence_id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rank 
        FROM dense_results
        UNION ALL
        SELECT evidence_id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rank 
        FROM sparse_results
    ) ranked
    GROUP BY evidence_id
)
SELECT ec.chunk_text, ec.evidence_id, r.rrf_score
FROM rrf r JOIN evidence_chunks ec USING (evidence_id)
ORDER BY r.rrf_score DESC
LIMIT 10;
```

### 6.3 Prompt Construction

The prompt structure enforces groundedness by construction — the model is given the retrieved evidence chunks and instructed to cite specific evidence IDs in its findings:

```
System: You are an audit AI generating findings for a compliance report. 
You MUST only make claims that are directly supported by the provided 
evidence chunks. Each claim in your finding MUST be followed by the 
evidence_id that supports it in the format [EV-{id}]. If you cannot 
support a claim with evidence, omit the claim entirely.

Evidence:
[EV-{id_1}]: {chunk_text_1}
[EV-{id_2}]: {chunk_text_2}
...

Finding request: {finding_description}

Generate the audit finding. Every factual claim must cite its evidence ID.
```

### 6.4 Faithfulness and Groundedness Scoring

After generation, the RAGAS evaluation framework scores the output:

**Faithfulness**: Each sentence in the generated finding is decomposed into atomic claims. Each claim is checked against the retrieved context using a lightweight NLI (Natural Language Inference) model (fine-tuned DeBERTa-v3-base). Faithfulness = (# claims supported by context) / (# total claims).

**Groundedness** (answer relevance in RAGAS terminology): The generated finding is embedded; the question is reverse-engineered from the finding and compared to the original request. High groundedness means the finding answers the right question.

**Combined score** = 0.6 * faithfulness + 0.4 * groundedness (weights calibrated on the labeled evaluation set).

### 6.5 HITL Escalation

When combined score < 0.45, the finding is not delivered to the client. Instead:

1. The finding, context, and scores are written to the `hitl_queue` table with status `PENDING_REVIEW`
2. The assigned auditor receives a notification (email + in-app)
3. The auditor reviews the finding in the Firm Mode UI, with the evidence chunks highlighted and the problematic claims flagged
4. The auditor can approve (overriding the guardrail with logged justification), edit (triggering re-scoring), or reject (marking the finding as not-generatable, requiring manual authoring)
5. All HITL decisions are logged immutably in the evidence store with the auditor's FIDO2-authenticated identity

The 0.45 threshold is a configurable parameter in the tenant configuration, not a hard-coded constant. Firms in conservative regulatory environments may lower it to 0.35; the threshold itself is part of the audit trail.

---

## 7. Security Architecture and Threat Model

### 7.1 MAESTRO Framework Application

The MAESTRO framework (Mission, Adversaries, Environment, Strategies, Tactics, Response, Outcomes) applied to Project Aegis:

**Mission-critical assets**: Evidence integrity, tenant isolation, cryptographic key material, audit finding authenticity.

**Adversary taxonomy**:
- Tier 1 (Insider threat): Auditor or admin with legitimate access attempting to tamper with evidence
- Tier 2 (Compromised tenant): Tenant attempting to access another tenant's data
- Tier 3 (External attacker): Attempting to inject false evidence or exfiltrate data
- Tier 4 (AI adversary): Prompt injection into the RAG pipeline to generate false findings

### 7.2 Prompt Injection Defense

The prompt injection filter sits at the API Gateway layer and intercepts all requests to the `rag-pipeline-service`. It applies three defenses in sequence:

**Input sanitization**: Strip control characters, Unicode direction overrides (U+202E), and known injection patterns (e.g., "ignore previous instructions", "you are now", "system:"). This is a blocklist and is insufficient alone.

**Structured prompt architecture**: The Claude API is called with the `system` parameter containing the audit instructions, and the `user` parameter containing only the finding request. Evidence chunks are passed in the `user` message with explicit XML-like delimiters (`<evidence>`, `</evidence>`) that the system prompt instructs the model to treat as data, not instructions. This exploits the structural difference between system and user turns.

**Output validation**: The generated finding is checked for evidence of successful injection: does it contain instructions, code, or claims inconsistent with the evidence? The NLI model used for faithfulness scoring also detects out-of-distribution content.

**Indirect injection from evidence**: A critical threat vector is injected instructions embedded in raw evidence data (e.g., a vendor name containing "Ignore all previous instructions"). Mitigation: evidence chunks are passed through an injection scanner before entering the prompt. The scanner flags evidence records containing injection patterns; flagged records are redacted in the prompt and the flag is recorded in the evidence record metadata.

### 7.3 Cross-Tenant Access Testing in CI/CD

The Sprint 7 requirement for automated cross-tenant access tests is implemented as a suite of integration tests running in the CI/CD pipeline (GitHub Actions or GitLab CI) against a test environment with seeded multi-tenant data:

```
Test Suite: CrossTenantIsolation
  - [CRITICAL] tenant_a_jwt cannot read tenant_b_evidence_records
  - [CRITICAL] tenant_a_jwt cannot modify tenant_b_risk_scores
  - [CRITICAL] firm_jwt with client_access=[tenant_a] cannot read tenant_b_data
  - [CRITICAL] pool_model superuser cannot bypass FORCE RLS
  - [HIGH] audit_role_jwt cannot access pam_broker endpoints
  - [HIGH] expired_jwt is rejected with 401, not 403
  - [HIGH] jwt_with_tampered_tenant_id is rejected (signature validation)
  - [MEDIUM] zk_proof_for_tenant_a cannot be submitted as tenant_b_proof
```

Tests marked `[CRITICAL]` are blocking — CI/CD fails and deployment is halted if any critical test fails. `[HIGH]` tests generate alerts but do not block deployment (they block the next release cycle). This is a risk trade-off: blocking all tests on a `[HIGH]` failure would create operational risk if a non-critical security regression is introduced in a hot-fix path.

### 7.4 Post-Quantum Cryptography Deployment

The PQC deployment uses a hybrid approach during the migration window (estimated 3-5 years before classical cryptography is fully deprecated):

**TLS layer**: `X25519Kyber768Draft00` cipher suite for key exchange, `ECDSA + Dilithium-3` hybrid signatures for server certificates. Both classical and post-quantum keys are included in the Certificate message; a MITM attacker must break both to compromise the session.

**Evidence signing**: Dilithium-3 signatures on every evidence record. The `dilithium_signature` column in `evidence_records` stores the 3.3KB signature blob. At 1M evidence records per large enterprise tenant, this is 3.3GB of signature data per tenant per year — a material storage cost that must be factored into pricing.

**Key management**: Vault PKI Secrets Engine extended with `liboqs-go` bindings for Dilithium key generation. The Vault cluster itself is protected by Kyber-1024 key encapsulation for inter-node communication.

**Classical fallback**: The system maintains classical ECDSA signatures in parallel with Dilithium during the transition period. Both signatures are stored; verification uses whichever algorithm is appropriate for the verifier's capabilities. This adds 64 bytes (ECDSA) alongside the 3.3KB Dilithium signature per record.

### 7.5 PAM Architecture Detail

The PAM Broker service implements the following JIT access flow:

1. Auditor authenticates via FIDO2/WebAuthn to the `auth-service` (step-up authentication required even if already authenticated with password)
2. Auditor submits an access request to the PAM Broker with: resource type, justification, ticket ID (from ITSM integration), expected duration
3. PAM Broker validates the request against the access policy (role-based maximum TTLs, time-of-day restrictions, geo-restrictions)
4. If approved, PAM Broker calls Vault to issue a dynamic credential: a short-lived PostgreSQL role with the minimum necessary grants, TTL set to the approved duration
5. The credential is delivered to the requesting service (not the auditor's browser) and logged in the PAM audit table with the approving authority, justification, and FIDO2 assertion ID
6. At TTL expiry, Vault revokes the credential. The PostgreSQL role is dropped. Any active sessions using the role are terminated.
7. All queries executed during the privileged session are captured by PostgreSQL's `log_statement = 'all'` configuration and streamed to the immutable audit log

Emergency access ("break glass"): A separate flow requiring dual authorization (two senior admins via FIDO2), immediate notification to the CISO, and a post-access review requirement. Break glass access is limited to 15 minutes and cannot be extended.

---

## 8. Critical Implementation Risks and Mitigations

### Risk 1: RLS Bypass via Connection Pool State Leakage

**Description**: PgBouncer in transaction mode reuses server connections across clients. If the `SET LOCAL app.tenant_id` is not re-issued at the start of every transaction (e.g., due to a code path that omits the interceptor), a subsequent transaction on the same connection would execute with the previous tenant's context.

**Severity**: Critical — complete tenant data exposure.

**Mitigation**:
- The `server_reset_query` in PgBouncer resets `app.tenant_id` to an empty string between transactions. Any query executing without a valid `app.tenant_id` will return zero rows (RLS policy fails closed on empty UUID match) rather than returning another tenant's data.
- CI/CD integration test: execute a query after transaction commit without setting `app.tenant_id`; verify zero rows returned.
- Application-level: the repository base class sets `app.tenant_id` as a mandatory first statement. Code review policy prohibits direct database access outside the repository layer.
- Monitoring: Alert on any query that accesses a tenant-scoped table with `app.tenant_id = ''` — this should never occur in production and indicates a code defect.

### Risk 2: ZK-Proof Circuit Soundness Vulnerabilities

**Description**: A bug in the Halo2 circuit (incorrect constraint, missing range check) could allow a prover to generate a valid-looking proof for a false statement. This would undermine the "mathematical proof of control" guarantee.

**Severity**: Critical — fraudulent compliance attestations.

**Mitigation**:
- Formal verification of circuit constraints using Lean4 or Coq for the most critical circuits (sum threshold, access log membership). This is expensive but non-negotiable for compliance use.
- Independent security audit of all circuit implementations by a specialist ZK cryptography firm (Trail of Bits, ZKSecurity) before production deployment.
- Proof of knowledge test suite: for each circuit, generate test proofs with known-invalid witnesses and verify that the verifier rejects them. This tests soundness experimentally.
- Circuit versioning: every circuit change requires a new version; old proofs remain valid under the version that generated them. Automated regression test suite runs on every circuit change.

### Risk 3: Hallucination Guardrail Miscalibration

**Description**: The 0.45 faithfulness/groundedness threshold may be miscalibrated on production data, allowing hallucinated findings to pass or rejecting valid findings at high rates. Both failure modes are costly: false negatives risk regulatory liability; false positives create HITL queue overload.

**Severity**: High.

**Mitigation**:
- Labeled evaluation dataset of at least 500 findings (250 known-good, 250 known-hallucinated) collected during the beta period. The threshold is calibrated to achieve at least 95% precision on catching hallucinations at the cost of acceptable false positive rate.
- Shadow mode deployment: run the guardrail in logging-only mode for the first 30 days, collecting score distributions without blocking delivery. This generates the calibration dataset.
- Threshold monitoring: track the weekly distribution of scores and HITL escalation rate. Alert if HITL rate exceeds 20% (guardrail too strict) or falls below 2% (possible degradation in scoring quality).
- Per-tenant threshold calibration: allow firms to adjust the threshold within a guardrail-enforced range (0.30 to 0.65). Thresholds below 0.30 are not permitted (security floor).

### Risk 4: Ingestion Pipeline Scalability at 400+ Connectors

**Description**: 400+ connectors polling at hourly cadence against rate-limited third-party APIs creates thundering herd problems (synchronized polling hitting API rate limits) and connector failure cascades (one failing connector blocking the orchestration queue).

**Severity**: Medium-High — data freshness for continuous assurance.

**Mitigation**:
- Jittered polling: each connector's hourly poll is scheduled at `hour_start + jitter(connector_id, tenant_id)` where jitter is a deterministic hash-based offset in [0, 3600) seconds. This spreads load across the hour.
- Per-connector circuit breaker (Resilience4j pattern): after 3 consecutive failures, a connector enters half-open state with exponential backoff. Connector health is surfaced in the SMB Mode dashboard.
- Tenant-level data freshness SLA: each evidence record has a `freshness_status` field. If a connector has not successfully polled within 2x its expected interval, the affected tenant's compliance status is degraded to "stale evidence" with a visible warning.
- Kafka partition isolation: each tenant's ingestion events use a dedicated Kafka partition set (using tenant_id as partition key). A backpressure event for one tenant's slow connector does not block other tenants' ingestion streams.

### Risk 5: Post-Quantum Migration Operational Complexity

**Description**: Deploying Dilithium-3 signatures alongside ECDSA doubles signing and verification overhead and significantly increases storage requirements. The `liboqs` library is less battle-tested than OpenSSL.

**Severity**: Medium.

**Mitigation**:
- Phase the PQC rollout: deploy Kyber for key exchange first (lower risk, no signature size impact), then Dilithium for new evidence records, then backfill Dilithium signatures for historical records.
- `liboqs` is wrapped in a cryptographic abstraction layer (`CryptoProvider` interface) that can swap implementations. If `liboqs` has a critical vulnerability, the fallback to classical crypto is a configuration change.
- Storage cost for Dilithium signatures is mitigated by storing signatures in a separate column family (or separate table) from the evidence payload, enabling tiered storage policies that move older signatures to cheaper object storage.

### Risk 6: FIDO2 Authenticator Loss and Recovery

**Description**: If an auditor loses their FIDO2 hardware token and cannot authenticate, there must be a recovery path that does not introduce a weaker authentication bypass (which would be the attack surface for social engineering).

**Severity**: Medium — operational continuity.

**Mitigation**:
- Each user must register at least two FIDO2 authenticators during onboarding (primary device + backup security key stored securely).
- Account recovery requires: (a) a recovery code generated at FIDO2 enrollment and stored by the user, (b) verification of the recovery code, (c) a 24-hour waiting period before the new authenticator is activated (prevents real-time account takeover even if the recovery code is stolen), (d) notification to the user's registered email and their firm's security contact.
- Recovery codes are hashed (Argon2id) before storage. The plaintext is shown only once at generation.
- Break-glass recovery (no recovery code available): requires the user's manager and the firm's security contact to jointly authorize the recovery through an out-of-band verification process managed by the Aegis security team.

---

## Appendix: Phased Delivery Sequencing

The seven sprints have architectural dependencies that constrain sequencing:

**Phase 1 (Weeks 1-8): Foundations** — Sprint 1 (auth, multi-tenant DB, PAM) must be completed first. No other sprint can deliver production data without tenant isolation.

**Phase 2 (Weeks 9-16): Evidence Layer** — Sprint 2 (ingestion, hash-chaining) and Sprint 6 (WORM storage, immutability primitives) are co-dependent. WORM storage must be available before evidence is written to production.

**Phase 3 (Weeks 17-24): Intelligence Layer** — Sprint 3 (ML) and Sprint 4 (RAG/Claude) can be developed in parallel. Both depend on the evidence layer from Phase 2.

**Phase 4 (Weeks 25-32): Delivery Layer** — Sprint 5 (UX) depends on all intelligence layer services having stable APIs. Sprint 7 (MAESTRO hardening) runs continuously from Phase 1, but the formal threat model validation is a Phase 4 milestone.

**ZK-Proof (Sprint 2 component)** is the highest-risk deliverable due to circuit design complexity and security audit requirements. Circuit development should begin in Phase 1 even though it is not in the critical path until Phase 2. The circuit security audit (8-12 week lead time for specialist firms) must be booked before Phase 2 begins.

---

### Critical Files for Implementation

Given that this is a greenfield system, the critical files for implementation are the foundational architectural artifacts that downstream code depends on:

- `/infra/db/migrations/V001__create_pool_model_schema.sql` — The base schema with RLS policies, `FORCE ROW LEVEL SECURITY` directives, and the `chain_sequence_counters` table. Every application service depends on this being correct. A defect here creates a cascading security failure.
- `/services/auth-service/src/tenant_context_middleware.ts` — The middleware that validates the JWT and executes `SET LOCAL app.tenant_id` before every database transaction. This is the single point of enforcement for tenant isolation in the pool model.
- `/services/zk-proof-worker/circuits/sum_threshold.rs` — The Halo2 circuit for the primary compliance assertion type. This file is the subject of the formal verification and security audit; it gates the ZK-proof feature's production readiness.
- `/services/rag-pipeline-service/src/hallucination_guardrail.py` — The RAGAS-based faithfulness/groundedness scoring with the HITL escalation logic. Miscalibration here directly affects audit finding reliability.
- `/services/forensic-ml-service/src/ensemble.py` — The VAE, Isolation Forest, and Benford's Law ensemble aggregation with the Dynamic Risk Index computation. The per-tenant training isolation logic in this file is the critical Chinese Wall enforcement for the ML pipeline.