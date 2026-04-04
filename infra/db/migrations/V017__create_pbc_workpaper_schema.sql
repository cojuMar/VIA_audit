-- =============================================================================
-- V017: PBC Request Management, Issue Lifecycle & Workpapers
-- Sprint 13 — Project Aegis 2026
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. audit_engagements (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_engagements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    engagement_name TEXT NOT NULL,
    engagement_type TEXT NOT NULL CHECK (engagement_type IN ('internal_audit','external_audit','soc2_readiness','iso27001','pen_test','regulatory','sox','other')),
    fiscal_year INT,
    period_start DATE,
    period_end DATE,
    lead_auditor TEXT,
    status TEXT NOT NULL DEFAULT 'planning' CHECK (status IN ('planning','fieldwork','review','complete','cancelled')),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_engagements_tenant_id
    ON audit_engagements (tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_engagements_tenant_status
    ON audit_engagements (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_audit_engagements_tenant_type
    ON audit_engagements (tenant_id, engagement_type);

ALTER TABLE audit_engagements ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_engagements FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'audit_engagements'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.audit_engagements
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON audit_engagements TO aegis_app;

-- -----------------------------------------------------------------------------
-- 2. pbc_request_lists (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pbc_request_lists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    engagement_id UUID NOT NULL REFERENCES audit_engagements(id),
    list_name TEXT NOT NULL,
    description TEXT,
    due_date DATE,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','sent','in_progress','complete')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pbc_request_lists_tenant_engagement
    ON pbc_request_lists (tenant_id, engagement_id);
CREATE INDEX IF NOT EXISTS idx_pbc_request_lists_tenant_status
    ON pbc_request_lists (tenant_id, status);

ALTER TABLE pbc_request_lists ENABLE ROW LEVEL SECURITY;
ALTER TABLE pbc_request_lists FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'pbc_request_lists'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.pbc_request_lists
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON pbc_request_lists TO aegis_app;

-- -----------------------------------------------------------------------------
-- 3. pbc_requests (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pbc_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    list_id UUID NOT NULL REFERENCES pbc_request_lists(id),
    request_number INT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT,
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('high','medium','low')),
    assigned_to TEXT,
    due_date DATE,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','fulfilled','not_applicable','overdue')),
    framework_control_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_list_request_number UNIQUE (list_id, request_number)
);

CREATE INDEX IF NOT EXISTS idx_pbc_requests_tenant_list
    ON pbc_requests (tenant_id, list_id);
CREATE INDEX IF NOT EXISTS idx_pbc_requests_tenant_status
    ON pbc_requests (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_pbc_requests_tenant_assigned_to
    ON pbc_requests (tenant_id, assigned_to);
CREATE INDEX IF NOT EXISTS idx_pbc_requests_due_date_open
    ON pbc_requests (due_date)
    WHERE due_date IS NOT NULL AND status IN ('open','in_progress');

ALTER TABLE pbc_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE pbc_requests FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'pbc_requests'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.pbc_requests
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON pbc_requests TO aegis_app;

-- -----------------------------------------------------------------------------
-- 4. pbc_fulfillments (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pbc_fulfillments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL REFERENCES pbc_requests(id),
    submitted_by TEXT NOT NULL,
    response_text TEXT,
    minio_key TEXT,
    file_name TEXT,
    file_size_bytes BIGINT,
    submission_notes TEXT,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pbc_fulfillments_tenant_request
    ON pbc_fulfillments (tenant_id, request_id);
CREATE INDEX IF NOT EXISTS idx_pbc_fulfillments_tenant_submitted_at
    ON pbc_fulfillments (tenant_id, submitted_at DESC);

ALTER TABLE pbc_fulfillments ENABLE ROW LEVEL SECURITY;
ALTER TABLE pbc_fulfillments FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'pbc_fulfillments'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.pbc_fulfillments
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON pbc_fulfillments TO aegis_app;

-- -----------------------------------------------------------------------------
-- 5. audit_issues (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    engagement_id UUID NOT NULL REFERENCES audit_engagements(id),
    issue_number INT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    finding_type TEXT NOT NULL CHECK (finding_type IN ('deficiency','significant_deficiency','material_weakness','observation','recommendation')),
    severity TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','informational')),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','management_response_pending','in_remediation','resolved','closed','risk_accepted')),
    control_reference TEXT,
    framework_references TEXT[] DEFAULT '{}',
    root_cause TEXT,
    management_owner TEXT,
    target_remediation_date DATE,
    actual_remediation_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_engagement_issue_number UNIQUE (engagement_id, issue_number)
);

CREATE INDEX IF NOT EXISTS idx_audit_issues_tenant_engagement
    ON audit_issues (tenant_id, engagement_id);
CREATE INDEX IF NOT EXISTS idx_audit_issues_tenant_severity
    ON audit_issues (tenant_id, severity);
CREATE INDEX IF NOT EXISTS idx_audit_issues_tenant_status
    ON audit_issues (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_audit_issues_tenant_management_owner
    ON audit_issues (tenant_id, management_owner);

ALTER TABLE audit_issues ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_issues FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'audit_issues'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.audit_issues
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON audit_issues TO aegis_app;

-- -----------------------------------------------------------------------------
-- 6. issue_responses (tenant, RLS+FORCE, SELECT/INSERT ONLY — immutable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS issue_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    issue_id UUID NOT NULL REFERENCES audit_issues(id),
    response_type TEXT NOT NULL CHECK (response_type IN ('management_response','remediation_update','auditor_note','status_change','evidence_uploaded')),
    response_text TEXT NOT NULL,
    submitted_by TEXT NOT NULL,
    new_status TEXT,
    minio_key TEXT,
    file_name TEXT,
    responded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_issue_responses_tenant_issue
    ON issue_responses (tenant_id, issue_id);
CREATE INDEX IF NOT EXISTS idx_issue_responses_tenant_responded_at
    ON issue_responses (tenant_id, responded_at DESC);

ALTER TABLE issue_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE issue_responses FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'issue_responses'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.issue_responses
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT ON issue_responses TO aegis_app;

-- -----------------------------------------------------------------------------
-- 7. workpaper_templates (PLATFORM — no RLS, SELECT only)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS workpaper_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    template_type TEXT NOT NULL CHECK (template_type IN ('risk_assessment','control_testing','walkthrough','observation','summary','other')),
    sections JSONB NOT NULL DEFAULT '[]',
    framework_references TEXT[] DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT true
);

GRANT SELECT ON workpaper_templates TO aegis_app;

-- Seed workpaper templates
INSERT INTO workpaper_templates (template_key, title, description, template_type, framework_references, sections)
VALUES (
    'risk_assessment_template',
    'Risk Assessment Workpaper',
    'Structured workpaper for conducting and documenting risk assessments.',
    'risk_assessment',
    ARRAY['SOC2','ISO27001','NIST'],
    '[
      {"section_key":"objective","title":"Objective and Scope","instructions":"Describe the objective and scope of this risk assessment.","fields":[{"key":"objective_text","type":"textarea","label":"Objective"},{"key":"scope","type":"textarea","label":"Scope"},{"key":"period_covered","type":"text","label":"Period Covered"}]},
      {"section_key":"methodology","title":"Methodology","instructions":"Describe the risk assessment methodology used.","fields":[{"key":"methodology","type":"textarea","label":"Methodology Description"},{"key":"risk_criteria","type":"textarea","label":"Risk Acceptance Criteria"}]},
      {"section_key":"risk_matrix","title":"Risk Identification and Rating","instructions":"List all identified risks and rate them.","fields":[{"key":"risks","type":"risk_table","label":"Risk Register"}]},
      {"section_key":"conclusions","title":"Conclusions and Recommendations","instructions":"Summarize findings and recommendations.","fields":[{"key":"conclusions","type":"textarea","label":"Conclusions"},{"key":"recommendations","type":"textarea","label":"Recommendations"}]}
    ]'::JSONB
) ON CONFLICT (template_key) DO NOTHING;

INSERT INTO workpaper_templates (template_key, title, description, template_type, framework_references, sections)
VALUES (
    'control_testing_template',
    'Control Testing Workpaper',
    'Structured workpaper for documenting control testing procedures and conclusions.',
    'control_testing',
    ARRAY['SOC2','SOX','ISO27001'],
    '[
      {"section_key":"control_description","title":"Control Description","instructions":"Document the control being tested.","fields":[{"key":"control_id","type":"text","label":"Control ID"},{"key":"control_objective","type":"textarea","label":"Control Objective"},{"key":"control_type","type":"select","label":"Control Type","options":["Preventive","Detective","Corrective"]},{"key":"frequency","type":"select","label":"Frequency","options":["Continuous","Daily","Weekly","Monthly","Quarterly","Annual"]}]},
      {"section_key":"population","title":"Population and Sampling","instructions":"Define the population and sampling approach.","fields":[{"key":"population_size","type":"number","label":"Population Size"},{"key":"sample_size","type":"number","label":"Sample Size"},{"key":"sampling_method","type":"text","label":"Sampling Method"},{"key":"sample_selection","type":"textarea","label":"Sample Selection Rationale"}]},
      {"section_key":"testing_procedures","title":"Testing Procedures","instructions":"Document procedures performed.","fields":[{"key":"procedures","type":"textarea","label":"Procedures Performed"},{"key":"exceptions","type":"textarea","label":"Exceptions Noted"},{"key":"exception_rate","type":"number","label":"Exception Rate (%)"}]},
      {"section_key":"conclusion","title":"Testing Conclusion","instructions":"Conclude on control effectiveness.","fields":[{"key":"conclusion","type":"select","label":"Conclusion","options":["Effective","Effective with Exceptions","Ineffective"]},{"key":"conclusion_narrative","type":"textarea","label":"Conclusion Narrative"}]}
    ]'::JSONB
) ON CONFLICT (template_key) DO NOTHING;

INSERT INTO workpaper_templates (template_key, title, description, template_type, framework_references, sections)
VALUES (
    'walkthrough_template',
    'Process Walkthrough Workpaper',
    'Structured workpaper for documenting process walkthroughs and identifying controls.',
    'walkthrough',
    ARRAY['SOC2','SOX'],
    '[
      {"section_key":"process_overview","title":"Process Overview","instructions":"Document the process being walked through.","fields":[{"key":"process_name","type":"text","label":"Process Name"},{"key":"owner","type":"text","label":"Process Owner"},{"key":"description","type":"textarea","label":"Process Description"}]},
      {"section_key":"process_flow","title":"Process Flow","instructions":"Document the steps of the process and systems involved.","fields":[{"key":"steps","type":"textarea","label":"Process Steps"},{"key":"systems_involved","type":"textarea","label":"Systems Involved"}]},
      {"section_key":"control_identification","title":"Control Identification","instructions":"Identify controls observed during the walkthrough and any gaps noted.","fields":[{"key":"identified_controls","type":"textarea","label":"Identified Controls"},{"key":"gaps","type":"textarea","label":"Control Gaps"}]}
    ]'::JSONB
) ON CONFLICT (template_key) DO NOTHING;

INSERT INTO workpaper_templates (template_key, title, description, template_type, framework_references, sections)
VALUES (
    'observation_template',
    'Audit Observation Workpaper',
    'Structured workpaper for documenting audit observations, root causes, and management action plans.',
    'observation',
    ARRAY['SOC2','ISO27001','NIST'],
    '[
      {"section_key":"observation_summary","title":"Observation Summary","instructions":"Summarize the audit observation including condition and criteria.","fields":[{"key":"title","type":"text","label":"Observation Title"},{"key":"condition","type":"textarea","label":"Condition"},{"key":"criteria","type":"textarea","label":"Criteria"}]},
      {"section_key":"root_cause","title":"Root Cause Analysis","instructions":"Identify the root cause and contributing factors.","fields":[{"key":"root_cause_analysis","type":"textarea","label":"Root Cause Analysis"},{"key":"contributing_factors","type":"textarea","label":"Contributing Factors"}]},
      {"section_key":"impact","title":"Impact Assessment","instructions":"Describe the impact and assign a risk rating.","fields":[{"key":"impact_description","type":"textarea","label":"Impact Description"},{"key":"risk_rating","type":"select","label":"Risk Rating","options":["Critical","High","Medium","Low","Informational"]}]},
      {"section_key":"management_action","title":"Management Action Plan","instructions":"Document the agreed management action plan.","fields":[{"key":"action_plan","type":"textarea","label":"Action Plan"},{"key":"owner","type":"text","label":"Action Owner"},{"key":"target_date","type":"text","label":"Target Date"}]}
    ]'::JSONB
) ON CONFLICT (template_key) DO NOTHING;

INSERT INTO workpaper_templates (template_key, title, description, template_type, framework_references, sections)
VALUES (
    'audit_summary_template',
    'Audit Summary and Opinion',
    'Structured workpaper for documenting the overall audit summary, findings count, and auditor opinion.',
    'summary',
    ARRAY['SOC2','ISO27001','SOX'],
    '[
      {"section_key":"executive_summary","title":"Executive Summary","instructions":"Provide the engagement scope, period, and audit team details.","fields":[{"key":"scope","type":"textarea","label":"Scope"},{"key":"period","type":"text","label":"Audit Period"},{"key":"audit_team","type":"textarea","label":"Audit Team"}]},
      {"section_key":"findings_summary","title":"Findings Summary","instructions":"Provide a count of findings by severity.","fields":[{"key":"total_issues","type":"number","label":"Total Issues"},{"key":"critical_count","type":"number","label":"Critical"},{"key":"high_count","type":"number","label":"High"},{"key":"medium_count","type":"number","label":"Medium"},{"key":"low_count","type":"number","label":"Low"}]},
      {"section_key":"opinion","title":"Auditor Opinion","instructions":"State the overall opinion and key recommendations.","fields":[{"key":"overall_opinion","type":"select","label":"Overall Opinion","options":["Unqualified","Qualified","Adverse","Disclaimer"]},{"key":"opinion_rationale","type":"textarea","label":"Opinion Rationale"},{"key":"recommendations","type":"textarea","label":"Key Recommendations"}]}
    ]'::JSONB
) ON CONFLICT (template_key) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 8. workpapers (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS workpapers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    engagement_id UUID NOT NULL REFERENCES audit_engagements(id),
    template_id UUID REFERENCES workpaper_templates(id),
    title TEXT NOT NULL,
    wp_reference TEXT,
    workpaper_type TEXT NOT NULL,
    preparer TEXT,
    reviewer TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','in_review','reviewed','final','superseded')),
    review_notes TEXT,
    finalized_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workpapers_tenant_engagement
    ON workpapers (tenant_id, engagement_id);
CREATE INDEX IF NOT EXISTS idx_workpapers_tenant_status
    ON workpapers (tenant_id, status);

ALTER TABLE workpapers ENABLE ROW LEVEL SECURITY;
ALTER TABLE workpapers FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'workpapers'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.workpapers
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON workpapers TO aegis_app;

-- -----------------------------------------------------------------------------
-- 9. workpaper_sections (tenant, RLS+FORCE, SELECT/INSERT/UPDATE)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS workpaper_sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    workpaper_id UUID NOT NULL REFERENCES workpapers(id),
    section_key TEXT NOT NULL,
    title TEXT NOT NULL,
    content JSONB NOT NULL DEFAULT '{}',
    sort_order INT NOT NULL DEFAULT 0,
    is_complete BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workpaper_sections_tenant_workpaper
    ON workpaper_sections (tenant_id, workpaper_id);
CREATE INDEX IF NOT EXISTS idx_workpaper_sections_tenant_workpaper_sort
    ON workpaper_sections (tenant_id, workpaper_id, sort_order);

ALTER TABLE workpaper_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE workpaper_sections FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE policyname = 'tenant_isolation' AND tablename = 'workpaper_sections'
    ) THEN
        CREATE POLICY "tenant_isolation" ON public.workpaper_sections
            USING (tenant_id = current_setting('app.tenant_id', TRUE)::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE)::UUID);
    END IF;
END; $$;

GRANT SELECT, INSERT, UPDATE ON workpaper_sections TO aegis_app;

-- Sprint 13: PBC, Issue Lifecycle & Workpapers schema complete (9 tables, 5 workpaper templates seeded)
