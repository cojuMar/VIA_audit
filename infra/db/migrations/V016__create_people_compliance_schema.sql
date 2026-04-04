-- =============================================================================
-- V016__create_people_compliance_schema.sql
-- Sprint 12: People, Policy & Training Compliance
-- 9 tables: employees, hr_policies, policy_versions, policy_acknowledgments,
--           training_courses, training_assignments, training_completions,
--           background_checks, compliance_escalations
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. employees  (tenant-mutable: RLS + FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    employee_id TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    department TEXT,
    job_title TEXT,
    job_role TEXT NOT NULL DEFAULT 'all',
    manager_id TEXT,
    hire_date DATE,
    employment_status TEXT NOT NULL DEFAULT 'active'
        CHECK (employment_status IN ('active','on_leave','terminated')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_employee_id UNIQUE (tenant_id, employee_id)
);

CREATE INDEX IF NOT EXISTS idx_employees_tenant_id
    ON employees (tenant_id);
CREATE INDEX IF NOT EXISTS idx_employees_tenant_status
    ON employees (tenant_id, employment_status);
CREATE INDEX IF NOT EXISTS idx_employees_tenant_department
    ON employees (tenant_id, department);
CREATE INDEX IF NOT EXISTS idx_employees_tenant_job_role
    ON employees (tenant_id, job_role);

ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'employees'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.employees
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON employees TO aegis_app;

-- -----------------------------------------------------------------------------
-- 2. hr_policies  (tenant-mutable: RLS + FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hr_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    policy_key TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL CHECK (category IN ('security','hr','finance','it','compliance','safety','other')),
    applies_to_roles TEXT[] NOT NULL DEFAULT '{all}',
    applies_to_departments TEXT[] DEFAULT '{}',
    current_version TEXT NOT NULL DEFAULT '1.0',
    acknowledgment_required BOOLEAN NOT NULL DEFAULT true,
    acknowledgment_frequency_days INT NOT NULL DEFAULT 365,
    minio_key TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_policy_key UNIQUE (tenant_id, policy_key)
);

CREATE INDEX IF NOT EXISTS idx_hr_policies_tenant_id
    ON hr_policies (tenant_id);
CREATE INDEX IF NOT EXISTS idx_hr_policies_tenant_category
    ON hr_policies (tenant_id, category);
CREATE INDEX IF NOT EXISTS idx_hr_policies_tenant_is_active
    ON hr_policies (tenant_id, is_active);

ALTER TABLE hr_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE hr_policies FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'hr_policies'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.hr_policies
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON hr_policies TO aegis_app;

-- -----------------------------------------------------------------------------
-- 3. policy_versions  (tenant-immutable: RLS + FORCE, SELECT/INSERT ONLY)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS policy_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    policy_id UUID NOT NULL REFERENCES hr_policies(id),
    version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    change_summary TEXT,
    effective_date DATE NOT NULL DEFAULT CURRENT_DATE,
    minio_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_policy_versions_tenant_policy
    ON policy_versions (tenant_id, policy_id);
CREATE INDEX IF NOT EXISTS idx_policy_versions_tenant_created_at
    ON policy_versions (tenant_id, created_at DESC);

ALTER TABLE policy_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_versions FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'policy_versions'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.policy_versions
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON policy_versions TO aegis_app;

-- -----------------------------------------------------------------------------
-- 4. policy_acknowledgments  (tenant-immutable: RLS + FORCE, SELECT/INSERT ONLY)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS policy_acknowledgments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    policy_id UUID NOT NULL REFERENCES hr_policies(id),
    employee_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip_address INET,
    user_agent TEXT,
    acknowledgment_method TEXT NOT NULL DEFAULT 'portal'
        CHECK (acknowledgment_method IN ('portal','email','in_person','lms'))
);

CREATE INDEX IF NOT EXISTS idx_policy_acks_tenant_employee
    ON policy_acknowledgments (tenant_id, employee_id);
CREATE INDEX IF NOT EXISTS idx_policy_acks_tenant_policy
    ON policy_acknowledgments (tenant_id, policy_id);
CREATE INDEX IF NOT EXISTS idx_policy_acks_tenant_acknowledged_at
    ON policy_acknowledgments (tenant_id, acknowledged_at DESC);
CREATE INDEX IF NOT EXISTS idx_policy_acks_tenant_employee_policy
    ON policy_acknowledgments (tenant_id, employee_id, policy_id);

ALTER TABLE policy_acknowledgments ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_acknowledgments FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'policy_acknowledgments'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.policy_acknowledgments
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON policy_acknowledgments TO aegis_app;

-- -----------------------------------------------------------------------------
-- 5. training_courses  (tenant-mutable: RLS + FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS training_courses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    course_key TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL CHECK (category IN ('security_awareness','privacy','compliance','technical','hr','safety','other')),
    applies_to_roles TEXT[] NOT NULL DEFAULT '{all}',
    duration_minutes INT,
    passing_score_pct INT NOT NULL DEFAULT 80,
    recurrence_days INT,
    provider TEXT NOT NULL DEFAULT 'internal',
    external_course_id TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_course_key UNIQUE (tenant_id, course_key)
);

CREATE INDEX IF NOT EXISTS idx_training_courses_tenant_id
    ON training_courses (tenant_id);
CREATE INDEX IF NOT EXISTS idx_training_courses_tenant_category
    ON training_courses (tenant_id, category);

ALTER TABLE training_courses ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_courses FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'training_courses'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.training_courses
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON training_courses TO aegis_app;

-- -----------------------------------------------------------------------------
-- 6. training_assignments  (tenant-mutable: RLS + FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS training_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    course_id UUID NOT NULL REFERENCES training_courses(id),
    employee_id TEXT NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    due_date DATE,
    status TEXT NOT NULL DEFAULT 'assigned'
        CHECK (status IN ('assigned','in_progress','completed','overdue','waived')),
    reminder_sent_count INT NOT NULL DEFAULT 0,
    last_reminder_at TIMESTAMPTZ,
    waived_by TEXT,
    waived_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_training_assignments_tenant_employee
    ON training_assignments (tenant_id, employee_id);
CREATE INDEX IF NOT EXISTS idx_training_assignments_tenant_status
    ON training_assignments (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_training_assignments_tenant_course
    ON training_assignments (tenant_id, course_id);
CREATE INDEX IF NOT EXISTS idx_training_assignments_due_date
    ON training_assignments (due_date)
    WHERE due_date IS NOT NULL AND status IN ('assigned','in_progress');

ALTER TABLE training_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_assignments FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'training_assignments'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.training_assignments
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON training_assignments TO aegis_app;

-- -----------------------------------------------------------------------------
-- 7. training_completions  (tenant-immutable: RLS + FORCE, SELECT/INSERT ONLY)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS training_completions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    assignment_id UUID NOT NULL REFERENCES training_assignments(id),
    employee_id TEXT NOT NULL,
    course_id UUID NOT NULL REFERENCES training_courses(id),
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    score_pct INT,
    passed BOOLEAN NOT NULL DEFAULT true,
    completion_method TEXT NOT NULL DEFAULT 'portal',
    certificate_key TEXT,
    external_completion_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_training_completions_tenant_employee
    ON training_completions (tenant_id, employee_id);
CREATE INDEX IF NOT EXISTS idx_training_completions_tenant_course
    ON training_completions (tenant_id, course_id);
CREATE INDEX IF NOT EXISTS idx_training_completions_tenant_completed_at
    ON training_completions (tenant_id, completed_at DESC);

ALTER TABLE training_completions ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_completions FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'training_completions'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.training_completions
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON training_completions TO aegis_app;

-- -----------------------------------------------------------------------------
-- 8. background_checks  (tenant-mutable: RLS + FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS background_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    employee_id TEXT NOT NULL,
    check_type TEXT NOT NULL CHECK (check_type IN ('pre_employment','annual','role_change','enhanced')),
    provider TEXT NOT NULL DEFAULT 'manual',
    external_check_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','in_progress','passed','failed','expired','cancelled')),
    initiated_at DATE NOT NULL DEFAULT CURRENT_DATE,
    completed_at DATE,
    expiry_date DATE,
    result_summary TEXT,
    adjudication TEXT CHECK (adjudication IN ('clear','review','adverse_action'))
);

CREATE INDEX IF NOT EXISTS idx_background_checks_tenant_employee
    ON background_checks (tenant_id, employee_id);
CREATE INDEX IF NOT EXISTS idx_background_checks_tenant_status
    ON background_checks (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_background_checks_expiry_date
    ON background_checks (expiry_date)
    WHERE expiry_date IS NOT NULL;

ALTER TABLE background_checks ENABLE ROW LEVEL SECURITY;
ALTER TABLE background_checks FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'background_checks'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.background_checks
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON background_checks TO aegis_app;

-- -----------------------------------------------------------------------------
-- 9. compliance_escalations  (tenant-immutable: RLS + FORCE, SELECT/INSERT ONLY)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_escalations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    escalation_type TEXT NOT NULL
        CHECK (escalation_type IN ('policy_overdue','training_overdue','background_check_expired','training_failed')),
    employee_id TEXT NOT NULL,
    reference_id UUID,
    reference_type TEXT CHECK (reference_type IN ('policy','training_assignment','background_check')),
    days_overdue INT,
    escalated_to TEXT,
    message TEXT,
    resolved BOOLEAN NOT NULL DEFAULT false,
    escalated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_compliance_escalations_tenant_employee
    ON compliance_escalations (tenant_id, employee_id);
CREATE INDEX IF NOT EXISTS idx_compliance_escalations_tenant_type
    ON compliance_escalations (tenant_id, escalation_type);
CREATE INDEX IF NOT EXISTS idx_compliance_escalations_tenant_escalated_at
    ON compliance_escalations (tenant_id, escalated_at DESC);
CREATE INDEX IF NOT EXISTS idx_compliance_escalations_tenant_resolved
    ON compliance_escalations (tenant_id, resolved);

ALTER TABLE compliance_escalations ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance_escalations FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'compliance_escalations'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.compliance_escalations
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON compliance_escalations TO aegis_app;

-- Sprint 12: People, Policy & Training Compliance schema complete (9 tables)
