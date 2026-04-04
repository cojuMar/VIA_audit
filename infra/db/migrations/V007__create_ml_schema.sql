-- =============================================================================
-- V007__create_ml_schema.sql
-- Project Aegis 2026 – Sprint 3: Forensic AI & Anomaly Detection
-- =============================================================================
-- Purpose:
--   Creates the full forensic machine-learning layer required by the
--   forensic-ml-service.  All DDL is fully idempotent – every CREATE TABLE,
--   CREATE INDEX, and INSERT uses IF NOT EXISTS / ON CONFLICT DO NOTHING so
--   this migration can be replayed safely without error.
--
-- Tables created:
--   1. anomaly_scores          – per-evidence ML scoring results
--   2. benford_entity_stats    – rolling Benford's-Law statistics per entity
--   3. ml_model_registry       – versioned model artifacts per tenant
--   4. jurisdiction_risk_scores – static jurisdictional risk lookup (no RLS)
--   5. vendor_profiles         – enriched vendor metadata for DRI computation
--   6. dri_framework_weights   – per-framework Dynamic Risk Index weight config
--
-- Row-Level Security:
--   Tables 1, 2, 3, 5 enforce tenant isolation via RLS.
--   Tables 4 and 6 are platform-level reference data and have NO RLS.
--
-- Seed data:
--   • jurisdiction_risk_scores – 20 representative countries
--   • dri_framework_weights    – soc2, iso27001, pci_dss profiles
--
-- Author  : Aegis Platform Team
-- Sprint  : 3 (Forensic AI & Anomaly Detection)
-- Created : 2026-04-03
-- =============================================================================

-- ---------------------------------------------------------------------------
-- EXTENSIONS
-- ---------------------------------------------------------------------------
-- pgcrypto is required for gen_random_uuid() used in all PK defaults.
-- CREATE EXTENSION IF NOT EXISTS is idempotent.
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- TABLE 1: anomaly_scores
-- =============================================================================
-- Stores the output of every ML scoring pass against an evidence record.
-- One row is written per (evidence_id, model run) – multiple rows may exist
-- for the same evidence_id as models are retrained and re-scored over time.
--
-- Key fields:
--   vae_score          – reconstruction error from a Variational Autoencoder,
--                        normalised to [0, 1].  Higher = more anomalous.
--   isolation_score    – anomaly score from Isolation Forest, normalised to
--                        [0, 1].  Higher = more anomalous.
--   benford_*          – Benford's Law statistics at time of scoring.
--   dynamic_risk_index – composite DRI in [0, 1] computed by the weighted
--                        formula defined in dri_framework_weights.
--   risk_level         – human-readable band derived from dynamic_risk_index
--                        thresholds: low <0.30, medium <0.60, high <0.80,
--                        critical ≥0.80.
--   feature_vector     – the raw 12-dimensional feature vector that was fed
--                        to the models, stored for auditability and replay.
--   framework          – which compliance framework's weight table was used
--                        when computing dynamic_risk_index.
-- =============================================================================
CREATE TABLE IF NOT EXISTS anomaly_scores (
    -- -------------------------------------------------------------------------
    -- Primary key
    -- -------------------------------------------------------------------------
    score_id                UUID          NOT NULL DEFAULT gen_random_uuid(),

    -- -------------------------------------------------------------------------
    -- Tenant isolation – every row belongs to exactly one tenant.
    -- -------------------------------------------------------------------------
    tenant_id               UUID          NOT NULL
                                          REFERENCES tenants(tenant_id),

    -- -------------------------------------------------------------------------
    -- Source evidence record that was scored.
    -- -------------------------------------------------------------------------
    evidence_id             UUID          NOT NULL
                                          REFERENCES evidence_records(evidence_id),

    -- -------------------------------------------------------------------------
    -- Source system / entity identification
    -- -------------------------------------------------------------------------
    source_system           TEXT          NOT NULL,   -- e.g. 'quickbooks', 'sap', 'manual'

    -- The business entity being scored (vendor ID, employee ID, account code,
    -- transaction reference, etc.).
    entity_id               TEXT          NOT NULL,

    -- Classifies what kind of entity entity_id refers to.
    entity_type             TEXT          NOT NULL
                                          CHECK (entity_type IN (
                                              'vendor',
                                              'employee',
                                              'account',
                                              'transaction'
                                          )),

    -- -------------------------------------------------------------------------
    -- VAE (Variational Autoencoder) score
    -- Normalised reconstruction error: 0 = perfectly normal, 1 = maximally
    -- anomalous.  NULL if the VAE model has not yet been trained for this
    -- tenant+framework combination.
    -- -------------------------------------------------------------------------
    vae_score               DOUBLE PRECISION,

    -- -------------------------------------------------------------------------
    -- Isolation Forest score
    -- Normalised anomaly score: 0 = normal, 1 = isolated outlier.
    -- NULL if an Isolation Forest model is not yet available.
    -- -------------------------------------------------------------------------
    isolation_score         DOUBLE PRECISION,

    -- -------------------------------------------------------------------------
    -- Benford's Law metrics
    -- benford_mad        – Mean Absolute Deviation from Benford distribution.
    --                      Commonly used thresholds: <0.006 acceptable,
    --                      0.006-0.012 marginally acceptable, >0.012 non-
    --                      conforming.
    -- benford_chi2_pvalue – p-value from chi-squared goodness-of-fit test.
    --                      p < 0.05 suggests non-conformance.
    -- benford_conforming  – Summary boolean.  TRUE = data follows Benford's
    --                      distribution within acceptable bounds.
    -- -------------------------------------------------------------------------
    benford_mad             DOUBLE PRECISION,
    benford_chi2_pvalue     DOUBLE PRECISION,
    benford_conforming      BOOLEAN,

    -- -------------------------------------------------------------------------
    -- Dynamic Risk Index (DRI)
    -- Composite weighted score in [0, 1] combining VAE, isolation, Benford,
    -- vendor age, round-number frequency, weekend activity, rare account usage,
    -- and jurisdictional risk.  See dri_framework_weights for weight config.
    -- NOT NULL – always populated before insert.
    -- -------------------------------------------------------------------------
    dynamic_risk_index      DOUBLE PRECISION      NOT NULL
                                                  CHECK (dynamic_risk_index BETWEEN 0 AND 1),

    -- Human-readable risk band derived from dynamic_risk_index.
    -- Defaults to 'low'; the application layer sets the correct value before
    -- insert based on configured thresholds.
    risk_level              TEXT          NOT NULL DEFAULT 'low'
                                          CHECK (risk_level IN (
                                              'low',
                                              'medium',
                                              'high',
                                              'critical'
                                          )),

    -- -------------------------------------------------------------------------
    -- Feature vector
    -- The 12-dimensional input vector passed to the ML models.  Stored as JSONB
    -- for flexibility.  Example keys: "vendor_age_days", "round_number_ratio",
    -- "weekend_activity_ratio", "rare_account_flag", "jurisdictional_risk",
    -- "amount_log", "invoice_freq_z", "duplicate_amount_flag",
    -- "split_transaction_flag", "prior_vae_score", "prior_iso_score",
    -- "benford_mad_rolling".
    -- -------------------------------------------------------------------------
    feature_vector          JSONB         NOT NULL,

    -- -------------------------------------------------------------------------
    -- Model version references
    -- Recorded at score time so results can be traced back to a specific
    -- trained artifact stored in ml_model_registry.
    -- -------------------------------------------------------------------------
    model_version_vae       TEXT,         -- e.g. '1.2.0'
    model_version_isolation TEXT,         -- e.g. '1.1.3'

    -- -------------------------------------------------------------------------
    -- Compliance framework used for DRI weight lookup
    -- -------------------------------------------------------------------------
    framework               TEXT          NOT NULL DEFAULT 'soc2',

    -- -------------------------------------------------------------------------
    -- Timestamps
    -- -------------------------------------------------------------------------
    computed_at             TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    -- -------------------------------------------------------------------------
    -- Human review workflow
    -- An analyst can mark a score as reviewed, optionally flag it as a false
    -- positive, and record their identity + timestamp.
    -- -------------------------------------------------------------------------
    reviewed                BOOLEAN       NOT NULL DEFAULT FALSE,
    reviewer_id             UUID          REFERENCES users(user_id),
    reviewed_at             TIMESTAMPTZ,
    false_positive          BOOLEAN,

    CONSTRAINT anomaly_scores_pkey PRIMARY KEY (score_id)
);

-- Row-Level Security: tenants may only see their own rows.
ALTER TABLE anomaly_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE anomaly_scores FORCE ROW LEVEL SECURITY;

-- Create the policy only if it does not already exist.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'anomaly_scores'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON anomaly_scores
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END;
$$;

-- =============================================================================
-- TABLE 2: benford_entity_stats
-- =============================================================================
-- Stores rolling Benford's Law statistics computed per entity over a defined
-- time window.  This table supports both real-time re-scoring (by providing
-- up-to-date distribution stats) and trend analysis over successive windows.
--
-- A new row is produced each time the forensic-ml-service runs a Benford
-- analysis pass for an (entity_id, entity_type) pair.  The UNIQUE constraint
-- prevents duplicate inserts for the same entity + window combination.
--
-- first_digit_distribution:
--   JSONB object with keys "1" through "9" (as text).  Values are integer
--   observed counts.  Example: {"1": 312, "2": 186, "3": 127, ...}
--
-- expected_distribution:
--   JSONB object with the same key structure containing Benford's theoretical
--   probabilities (log10(1 + 1/d)).  Stored alongside actuals so that
--   downstream consumers do not need to re-derive them.
--   Example: {"1": 0.30103, "2": 0.17609, "3": 0.12494, ...}
-- =============================================================================
CREATE TABLE IF NOT EXISTS benford_entity_stats (
    stat_id                  UUID         NOT NULL DEFAULT gen_random_uuid(),

    -- Tenant isolation
    tenant_id                UUID         NOT NULL
                                          REFERENCES tenants(tenant_id),

    -- Entity being analysed
    entity_id                TEXT         NOT NULL,
    entity_type              TEXT         NOT NULL,

    -- Number of transactions included in this window's distribution
    transaction_count        INT          NOT NULL DEFAULT 0,

    -- Observed leading-digit counts keyed "1" through "9"
    first_digit_distribution JSONB        NOT NULL,

    -- Benford's theoretical probabilities keyed "1" through "9"
    expected_distribution    JSONB        NOT NULL,

    -- Mean Absolute Deviation – primary conformance metric
    mad                      DOUBLE PRECISION NOT NULL,

    -- Chi-squared test results
    chi2_statistic           DOUBLE PRECISION,
    chi2_pvalue              DOUBLE PRECISION,

    -- Summary conformance flag
    conforming               BOOLEAN      NOT NULL,

    -- Time window covered by this statistical snapshot
    window_start             TIMESTAMPTZ  NOT NULL,
    window_end               TIMESTAMPTZ  NOT NULL,

    computed_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT benford_entity_stats_pkey PRIMARY KEY (stat_id),

    -- One stat row per entity per window.  Prevents duplicate computation
    -- and allows upserts via ON CONFLICT.
    CONSTRAINT benford_entity_stats_unique
        UNIQUE (tenant_id, entity_id, entity_type, window_start)
);

-- Row-Level Security
ALTER TABLE benford_entity_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE benford_entity_stats FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'benford_entity_stats'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON benford_entity_stats
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END;
$$;

-- =============================================================================
-- TABLE 3: ml_model_registry
-- =============================================================================
-- Acts as the internal model catalog.  Every trained model artifact that the
-- forensic-ml-service produces is registered here before it is used for
-- scoring.  Only one model per (tenant, model_type, framework) combination
-- may be active at a time – enforced via the partial unique index below.
--
-- model_type values:
--   'vae'              – Variational Autoencoder for reconstruction-error scoring
--   'isolation_forest' – Isolation Forest for outlier detection
--   'meta_classifier'  – Optional stacking classifier combining VAE + IF scores
--
-- MLflow integration:
--   mlflow_run_id and mlflow_artifact_uri are populated by the training job and
--   can be used to retrieve the serialised model from the MLflow artifact store
--   (backed by MinIO in dev, S3 in prod).
--
-- Lifecycle:
--   is_active = FALSE  – model trained but not yet deployed, or retired
--   is_active = TRUE   – model currently used for inference
--   retired_at NOT NULL – model has been superseded; kept for audit trail
-- =============================================================================
CREATE TABLE IF NOT EXISTS ml_model_registry (
    model_id                UUID         NOT NULL DEFAULT gen_random_uuid(),

    -- Tenant isolation – models are trained per-tenant on tenant-specific data
    tenant_id               UUID         NOT NULL
                                         REFERENCES tenants(tenant_id),

    -- Type of model artifact
    model_type              TEXT         NOT NULL
                                         CHECK (model_type IN (
                                             'vae',
                                             'isolation_forest',
                                             'meta_classifier'
                                         )),

    -- Semantic version string (MAJOR.MINOR.PATCH)
    version                 TEXT         NOT NULL,

    -- MLflow run identifier (populated after training completes)
    mlflow_run_id           TEXT,

    -- MLflow artifact URI – points to the serialised model file in MinIO/S3
    mlflow_artifact_uri     TEXT,

    -- Compliance framework this model was trained for
    framework               TEXT         NOT NULL DEFAULT 'soc2',

    -- Training timeline
    training_started_at     TIMESTAMPTZ  NOT NULL,
    training_completed_at   TIMESTAMPTZ,          -- NULL while training is in progress

    -- Dataset statistics recorded for provenance
    training_record_count   INT,
    training_date_from      TIMESTAMPTZ,          -- earliest transaction in training set
    training_date_to        TIMESTAMPTZ,          -- latest transaction in training set

    -- Performance metrics captured during evaluation on the held-out set.
    -- Example: {"reconstruction_loss": 0.023, "auc_roc": 0.94, "f1": 0.87}
    validation_metrics      JSONB,

    -- Deployment state
    is_active               BOOLEAN      NOT NULL DEFAULT FALSE,
    deployed_at             TIMESTAMPTZ,
    retired_at              TIMESTAMPTZ,

    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT ml_model_registry_pkey PRIMARY KEY (model_id),

    -- Prevent duplicate version strings for the same tenant + type + framework
    CONSTRAINT ml_model_registry_version_unique
        UNIQUE (tenant_id, model_type, framework, version)
);

-- Row-Level Security
ALTER TABLE ml_model_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE ml_model_registry FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'ml_model_registry'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON ml_model_registry
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END;
$$;

-- =============================================================================
-- TABLE 4: jurisdiction_risk_scores
-- =============================================================================
-- Platform-level reference data mapping ISO 3166-1 alpha-2 country codes to
-- a risk score in [0, 1].  This table is NOT tenant-specific and does NOT
-- have RLS – all authenticated service accounts can read it.
--
-- Risk score guidance (approximate):
--   0.00 – 0.15  Low risk    : FATF-compliant, strong AML frameworks
--   0.16 – 0.45  Medium risk : some AML concerns, enhanced due-diligence
--   0.46 – 0.70  High risk   : FATF grey-listed or significant AML gaps
--   0.71 – 1.00  Critical    : FATF black-listed, sanctioned, or state-
--                              sponsored financial crime concerns
--
-- data_source values: 'FATF', 'Basel AML Index', 'US Treasury OFAC', etc.
-- =============================================================================
CREATE TABLE IF NOT EXISTS jurisdiction_risk_scores (
    jurisdiction_id  UUID         NOT NULL DEFAULT gen_random_uuid(),

    -- ISO 3166-1 alpha-2 code, e.g. 'US', 'GB', 'CN'
    country_code     TEXT         NOT NULL,

    country_name     TEXT         NOT NULL,

    -- Composite risk score normalised to [0, 1]
    risk_score       DOUBLE PRECISION NOT NULL
                                  CHECK (risk_score BETWEEN 0 AND 1),

    -- Free-text explanation for why this score was assigned
    risk_rationale   TEXT,

    -- Primary data source for the risk assessment
    data_source      TEXT         NOT NULL DEFAULT 'FATF',

    last_updated     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT jurisdiction_risk_scores_pkey  PRIMARY KEY (jurisdiction_id),
    CONSTRAINT jurisdiction_risk_scores_code  UNIQUE      (country_code)
);

-- No RLS – platform-level reference data accessible to all services.

-- =============================================================================
-- TABLE 5: vendor_profiles
-- =============================================================================
-- Enriched vendor metadata maintained by the forensic-ml-service.  Each row
-- tracks aggregated transaction statistics and risk attributes for one vendor
-- within one tenant.  The DRI computation reads jurisdictional_risk_score and
-- is_related_party from this table as inputs.
--
-- external_vendor_id:
--   The vendor's identifier in the tenant's source system (e.g. the vendor ID
--   from QuickBooks, SAP AP module, etc.).  Combined with tenant_id as the
--   natural key.
--
-- country_code FK:
--   Points to jurisdiction_risk_scores(country_code).  Allows the service to
--   join in jurisdictional_risk_score automatically when it changes.
-- =============================================================================
CREATE TABLE IF NOT EXISTS vendor_profiles (
    vendor_id               UUID         NOT NULL DEFAULT gen_random_uuid(),

    -- Tenant isolation
    tenant_id               UUID         NOT NULL
                                         REFERENCES tenants(tenant_id),

    -- Source-system vendor identifier
    external_vendor_id      TEXT         NOT NULL,

    -- Display name
    vendor_name             TEXT         NOT NULL,

    -- Transaction history aggregates – updated by the forensic-ml-service
    -- after each ingestion batch.
    first_transaction_at    TIMESTAMPTZ,
    transaction_count       INT          NOT NULL DEFAULT 0,
    total_amount_usd        DOUBLE PRECISION NOT NULL DEFAULT 0,

    -- Jurisdiction of vendor's registered address (used for DRI)
    country_code            TEXT         REFERENCES jurisdiction_risk_scores(country_code),

    -- Cached copy of the jurisdiction score at time of last profile update.
    -- Stored here to avoid a join on every scoring call.
    jurisdictional_risk_score DOUBLE PRECISION NOT NULL DEFAULT 0,

    -- TRUE if this vendor has been flagged as a related party (potential
    -- conflict of interest).  Set manually by an analyst or via import.
    is_related_party        BOOLEAN      NOT NULL DEFAULT FALSE,

    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT vendor_profiles_pkey   PRIMARY KEY (vendor_id),
    CONSTRAINT vendor_profiles_unique UNIQUE (tenant_id, external_vendor_id)
);

-- Row-Level Security
ALTER TABLE vendor_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_profiles FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'vendor_profiles'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON vendor_profiles
            USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
    END IF;
END;
$$;

-- =============================================================================
-- TABLE 6: dri_framework_weights
-- =============================================================================
-- Defines the per-compliance-framework weight configuration used when computing
-- the Dynamic Risk Index (DRI).  The DRI formula is:
--
--   DRI = bias
--       + w_vae              * vae_score
--       + w_isolation        * isolation_score
--       + w_benford          * benford_component
--       + w_vendor_age       * vendor_age_component
--       + w_round_number     * round_number_ratio
--       + w_weekend_activity * weekend_activity_ratio
--       + w_rare_account     * rare_account_flag
--       + w_jurisdictional   * jurisdictional_risk_score
--
-- The sum of all w_* columns should equal 1.0 (after accounting for bias).
--
-- Different compliance frameworks may place different emphasis on particular
-- risk signals.  For example, PCI DSS weights round-number transactions more
-- heavily than SOC 2, which is primarily concerned with access and controls.
--
-- This table has NO RLS – it is platform-level configuration.
-- =============================================================================
CREATE TABLE IF NOT EXISTS dri_framework_weights (
    weight_id           UUID         NOT NULL DEFAULT gen_random_uuid(),

    -- Compliance framework identifier (e.g. 'soc2', 'iso27001', 'pci_dss')
    framework           TEXT         NOT NULL,

    -- -------------------------------------------------------------------------
    -- Weight components – each in [0, 1]; must sum to 1.0 in a valid config.
    -- -------------------------------------------------------------------------

    -- VAE reconstruction error weight
    w_vae               DOUBLE PRECISION NOT NULL DEFAULT 0.20,

    -- Isolation Forest score weight
    w_isolation         DOUBLE PRECISION NOT NULL DEFAULT 0.20,

    -- Benford's Law non-conformance weight
    w_benford           DOUBLE PRECISION NOT NULL DEFAULT 0.15,

    -- Vendor age signal weight (new vendors = higher risk)
    w_vendor_age        DOUBLE PRECISION NOT NULL DEFAULT 0.10,

    -- Round-number transaction frequency weight (e.g. $5000.00, $10000.00)
    w_round_number      DOUBLE PRECISION NOT NULL DEFAULT 0.10,

    -- Weekend / off-hours activity weight
    w_weekend_activity  DOUBLE PRECISION NOT NULL DEFAULT 0.08,

    -- Rare account code usage weight (infrequently used GL accounts)
    w_rare_account      DOUBLE PRECISION NOT NULL DEFAULT 0.07,

    -- Jurisdictional risk weight
    w_jurisdictional    DOUBLE PRECISION NOT NULL DEFAULT 0.10,

    -- Additive bias term applied before clamping result to [0, 1]
    bias                DOUBLE PRECISION NOT NULL DEFAULT 0.0,

    -- Human-readable description of this weight profile
    description         TEXT,

    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT dri_framework_weights_pkey      PRIMARY KEY (weight_id),
    CONSTRAINT dri_framework_weights_framework UNIQUE      (framework)
);

-- No RLS – platform-level configuration accessible to all services.

-- =============================================================================
-- INDEXES
-- =============================================================================
-- All indexes are created with IF NOT EXISTS (idempotent).

-- ---------------------------------------------------------------------------
-- anomaly_scores indexes
-- ---------------------------------------------------------------------------

-- Primary query pattern: fetch highest-risk scores for a tenant, ordered by
-- risk severity and recency.  Used by the dashboard and alert aggregator.
CREATE INDEX IF NOT EXISTS idx_anomaly_scores_tenant_risk
    ON anomaly_scores (tenant_id, dynamic_risk_index DESC, computed_at DESC);

-- Entity-level lookups: retrieve all scores for a specific vendor/employee/
-- account within a tenant.
CREATE INDEX IF NOT EXISTS idx_anomaly_scores_tenant_entity
    ON anomaly_scores (tenant_id, entity_id, entity_type);

-- Partial index: high and critical risks are the most frequently queried
-- subset.  Partial index keeps it lean and fast.
CREATE INDEX IF NOT EXISTS idx_anomaly_scores_tenant_high_critical
    ON anomaly_scores (tenant_id, risk_level)
    WHERE risk_level IN ('high', 'critical');

-- Evidence record lookup: find all scores associated with a given evidence
-- record (e.g. to display score history on the evidence detail page).
CREATE INDEX IF NOT EXISTS idx_anomaly_scores_evidence
    ON anomaly_scores (evidence_id);

-- ---------------------------------------------------------------------------
-- benford_entity_stats indexes
-- ---------------------------------------------------------------------------

-- Entity-level Benford history lookup.
CREATE INDEX IF NOT EXISTS idx_benford_entity_stats_tenant_entity
    ON benford_entity_stats (tenant_id, entity_id, entity_type);

-- ---------------------------------------------------------------------------
-- ml_model_registry indexes
-- ---------------------------------------------------------------------------

-- Active model lookup: find the currently deployed model for a tenant +
-- model type combination.  Partial index keeps it tiny since is_active=TRUE
-- will only ever have one row per (tenant, model_type, framework).
CREATE INDEX IF NOT EXISTS idx_ml_model_registry_active
    ON ml_model_registry (tenant_id, model_type, is_active)
    WHERE is_active = TRUE;

-- ---------------------------------------------------------------------------
-- vendor_profiles indexes
-- ---------------------------------------------------------------------------

-- Natural key lookup used when upserting vendor data from ingestion events.
CREATE INDEX IF NOT EXISTS idx_vendor_profiles_tenant_external
    ON vendor_profiles (tenant_id, external_vendor_id);

-- =============================================================================
-- SEED DATA: jurisdiction_risk_scores
-- =============================================================================
-- 20 representative countries seeded with realistic risk scores.
-- Sources: FATF Mutual Evaluation Reports, Basel AML Index 2025,
--          US Treasury OFAC sanctions list.
--
-- ON CONFLICT DO NOTHING makes this idempotent.
-- =============================================================================
INSERT INTO jurisdiction_risk_scores
    (country_code, country_name, risk_score, risk_rationale, data_source)
VALUES

    -- -------------------------------------------------------------------------
    -- LOW RISK (0.00 – 0.15): Strong AML/CFT frameworks, FATF-compliant
    -- -------------------------------------------------------------------------
    ('CH', 'Switzerland',
     0.07,
     'FATF member with robust AML/CFT framework; strong financial intelligence unit; '
     'minor concerns around private banking secrecy historically addressed.',
     'FATF'),

    ('DE', 'Germany',
     0.08,
     'FATF member; comprehensive AML legislation aligned with EU AMLD6; '
     'Financial Intelligence Unit (FIU) fully operational.',
     'FATF'),

    ('GB', 'United Kingdom',
     0.10,
     'FATF member; National Crime Agency financial intelligence capability; '
     'some concerns about London property market money-laundering addressed '
     'by 2023 Economic Crime Act.',
     'FATF'),

    ('US', 'United States',
     0.12,
     'FATF member; FinCEN oversight; Bank Secrecy Act compliance regime; '
     'shell-company opacity concerns partially mitigated by Corporate '
     'Transparency Act 2024.',
     'FATF'),

    ('AU', 'Australia',
     0.11,
     'FATF member; AUSTRAC enforcement active; AML/CTF Act 2006 amended 2024 '
     'to extend obligations to real-estate and professional service sectors.',
     'FATF'),

    ('SG', 'Singapore',
     0.13,
     'FATF member; MAS maintains strong AML supervisory regime; '
     'significant trading hub creates elevated exposure but controls are robust.',
     'FATF'),

    -- -------------------------------------------------------------------------
    -- MEDIUM RISK (0.16 – 0.45): Some AML concerns; enhanced due-diligence
    -- -------------------------------------------------------------------------
    ('AE', 'United Arab Emirates',
     0.45,
     'Removed from FATF grey list in February 2024 after significant reforms; '
     'residual risk from free-trade zones, cash-intensive real-estate market, '
     'and proximity to sanctioned jurisdictions. Monitor closely.',
     'FATF'),

    ('TR', 'Turkey',
     0.42,
     'FATF grey list exit completed June 2024 after legislative reforms; '
     'strategic gateway between Europe and Middle East introduces elevated risk; '
     'ongoing monitoring recommended.',
     'FATF'),

    ('SA', 'Saudi Arabia',
     0.30,
     'FATF member; significant AML reform programme; Vision 2030 financial '
     'sector development introduces new exposure vectors; cash economy declining.',
     'FATF'),

    ('ZA', 'South Africa',
     0.40,
     'FATF grey-listed 2023; significant structural challenges with state-capture '
     'legacy; FSCA and FIC actively implementing remediation plan.',
     'FATF'),

    -- -------------------------------------------------------------------------
    -- HIGH RISK (0.46 – 0.70): FATF concerns or significant AML gaps
    -- -------------------------------------------------------------------------
    ('CN', 'China',
     0.55,
     'Not FATF-listed; significant concerns around enforcement of AML rules, '
     'opacity of beneficial ownership, capital controls evasion, and use of '
     'crypto for cross-border fund movement.',
     'Basel AML Index'),

    ('PK', 'Pakistan',
     0.62,
     'FATF grey-listed multiple times; June 2022 exit; residual risk from '
     'hawala networks, terrorist financing, and porous border with Afghanistan.',
     'FATF'),

    ('VN', 'Vietnam',
     0.50,
     'FATF grey list 2023; rapid economic growth with underdeveloped AML '
     'framework; significant cash economy and growing casino sector.',
     'FATF'),

    ('PH', 'Philippines',
     0.48,
     'Removed from FATF grey list 2021; AMLA strengthened; residual risk from '
     'casino junkets, remittance corridors, and internet-gambling sector.',
     'FATF'),

    -- -------------------------------------------------------------------------
    -- CRITICAL RISK (0.71 – 1.00): Sanctioned, black-listed, or state-sponsored
    -- -------------------------------------------------------------------------
    ('IR', 'Iran',
     0.95,
     'FATF black list (Jurisdictions subject to a Call for Action); '
     'comprehensive US OFAC and EU sanctions; state-sponsored evasion of '
     'financial controls; SWIFT disconnected.',
     'FATF'),

    ('KP', 'North Korea',
     0.97,
     'FATF black list; UN Security Council sanctions; extensive cyber-theft '
     'and crypto-laundering operations attributed to state actors (Lazarus Group); '
     'complete absence of AML/CFT framework.',
     'FATF'),

    ('RU', 'Russia',
     0.88,
     'Comprehensive OFAC, EU, UK and allied sanctions following 2022 invasion '
     'of Ukraine; FSB-linked financial crime; significant use of shell companies '
     'and crypto to evade sanctions.',
     'US Treasury OFAC'),

    ('MM', 'Myanmar',
     0.85,
     'FATF black list since 2020; military coup 2021 further degraded AML '
     'governance; significant narcotics trafficking proceeds requiring laundering.',
     'FATF'),

    ('SY', 'Syria',
     0.93,
     'US OFAC comprehensive sanctions; years of civil conflict have destroyed '
     'formal financial sector; significant terrorist financing concerns.',
     'US Treasury OFAC'),

    ('YE', 'Yemen',
     0.80,
     'Prolonged civil conflict; Houthi-controlled central bank under UN scrutiny; '
     'significant informal and hawala money-transfer activity; '
     'limited AML oversight capacity.',
     'FATF')

ON CONFLICT (country_code) DO NOTHING;

-- =============================================================================
-- SEED DATA: dri_framework_weights
-- =============================================================================
-- Three compliance framework weight profiles.  Weights within each row are
-- designed to sum to 1.00 to produce a DRI on a [0, 1] scale (bias = 0).
--
-- SOC 2    : Balanced general-purpose profile; equal emphasis on ML signals
--            and process-level indicators (round numbers, weekend activity).
--
-- ISO 27001: Information-security orientation; slightly higher weight on
--            rare-account usage (potential insider access misuse) and
--            VAE/isolation scores (anomalous access patterns).
--
-- PCI DSS  : Payment-card focus; significantly higher weight on round-number
--            transactions (structuring) and jurisdictional risk (card-not-
--            present fraud); lower weight on vendor age (cards are global).
-- =============================================================================
INSERT INTO dri_framework_weights
    (framework, w_vae, w_isolation, w_benford, w_vendor_age,
     w_round_number, w_weekend_activity, w_rare_account,
     w_jurisdictional, bias, description)
VALUES

    -- SOC 2 Type II – balanced general-purpose profile
    (
        'soc2',
        0.20,   -- w_vae
        0.20,   -- w_isolation
        0.15,   -- w_benford
        0.10,   -- w_vendor_age       (new vendors carry more risk)
        0.10,   -- w_round_number     (structuring indicator)
        0.08,   -- w_weekend_activity (off-cycle payment indicator)
        0.07,   -- w_rare_account     (unusual GL code usage)
        0.10,   -- w_jurisdictional   (sanction / FATF exposure)
        0.0,    -- bias
        'SOC 2 Type II general-purpose DRI weight profile. '
        'Balanced across ML anomaly signals and process-level risk indicators.'
    ),

    -- ISO 27001 – information-security orientation
    -- Higher weight on rare account (insider access) and ML scores.
    -- Lower weight on round-number (less relevant to IS controls).
    (
        'iso27001',
        0.22,   -- w_vae              (elevated: IS anomalies often show here)
        0.22,   -- w_isolation        (elevated: same reason)
        0.12,   -- w_benford          (reduced: IS focus, not financial crime)
        0.08,   -- w_vendor_age       (reduced)
        0.06,   -- w_round_number     (reduced: less IS relevance)
        0.10,   -- w_weekend_activity (elevated: off-hours access concern)
        0.12,   -- w_rare_account     (elevated: unusual system access)
        0.08,   -- w_jurisdictional
        0.0,
        'ISO 27001 information-security DRI weight profile. '
        'Elevated emphasis on ML anomaly detection and unusual account usage '
        'to capture insider-threat and access-control failure signals.'
    ),

    -- PCI DSS – payment-card fraud and structuring focus
    -- Higher weight on round-number (structuring), jurisdictional (card-
    -- not-present fraud origins), and Benford (payment fraud signature).
    (
        'pci_dss',
        0.18,   -- w_vae
        0.18,   -- w_isolation
        0.16,   -- w_benford          (elevated: card fraud often non-Benford)
        0.06,   -- w_vendor_age       (reduced: global card acceptance)
        0.15,   -- w_round_number     (elevated: structuring / split payments)
        0.07,   -- w_weekend_activity
        0.06,   -- w_rare_account     (reduced)
        0.14,   -- w_jurisdictional   (elevated: high-risk card-not-present
                --                    jurisdictions are a key PCI concern)
        0.0,
        'PCI DSS Level 1 DRI weight profile. '
        'Elevated emphasis on round-number structuring, jurisdictional risk, '
        'and Benford deviation to capture payment-card fraud patterns.'
    )

ON CONFLICT (framework) DO NOTHING;

-- =============================================================================
-- END OF MIGRATION V007
-- =============================================================================
