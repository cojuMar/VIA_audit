-- =============================================================================
-- Demo Seed Data — Tenant 00000000-0000-0000-0000-000000000001
-- =============================================================================
SET app.tenant_id = '00000000-0000-0000-0000-000000000001';

-- 1. Tenant
INSERT INTO tenants (tenant_id, external_id, display_name, tier, region)
VALUES ('00000000-0000-0000-0000-000000000001', 'demo-tenant', 'Acme Financial Group', 'enterprise_silo', 'us-east-1')
ON CONFLICT (tenant_id) DO NOTHING;

-- 2. Audit Entities (audit universe)
INSERT INTO audit_entities (id, tenant_id, name, description, entity_type_id, owner_name, owner_email, department, risk_score, last_audit_date, next_audit_due, audit_frequency_months, is_in_universe)
VALUES
  ('e0000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'Core Banking Platform', 'Primary transactional banking system and ledger', '3d5e5a6e-6a50-4dcc-bca7-029fac001cef', 'James Parker', 'j.parker@acme.com', 'Technology', 9.2, '2025-06-15', '2026-06-15', 12, true),
  ('e0000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'Accounts Payable Process', 'End-to-end AP cycle: invoice receipt to payment disbursement', 'f486f18d-9dbe-4b3d-bac0-b9d1a69fbdff', 'Sarah Chen', 's.chen@acme.com', 'Finance', 7.8, '2025-03-01', '2026-03-01', 12, true),
  ('e0000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'New York Headquarters', 'Primary corporate office with 1000 employees', '376d7d3f-495f-45f4-a371-c7fbc79572ca', 'Tom Reilly', 't.reilly@acme.com', 'Operations', 5.5, '2024-11-10', '2025-11-10', 12, true),
  ('e0000001-0000-4000-a000-000000000004', '00000000-0000-0000-0000-000000000001', 'Identity and Access Management', 'IAM platform governing all user provisioning and SSO', '3d5e5a6e-6a50-4dcc-bca7-029fac001cef', 'Laura Kim', 'l.kim@acme.com', 'Cybersecurity', 8.5, '2025-09-20', '2026-03-20', 6, true),
  ('e0000001-0000-4000-a000-000000000005', '00000000-0000-0000-0000-000000000001', 'Payroll and HR Systems', 'ADP payroll, Workday HRIS, benefits management', '3d5e5a6e-6a50-4dcc-bca7-029fac001cef', 'Mike Torres', 'm.torres@acme.com', 'Human Resources', 6.3, '2024-08-30', '2025-08-30', 12, true)
ON CONFLICT DO NOTHING;

-- 3. Audit Plan 2026
INSERT INTO audit_plans (id, tenant_id, plan_year, title, description, status, total_budget_hours, approved_by, approved_at, created_by)
VALUES ('a0000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 2026, 'FY2026 Internal Audit Plan', 'Annual risk-based audit plan covering all high-risk areas identified in the 2025 risk assessment', 'approved', 4800, 'Board Audit Committee', NOW() - INTERVAL '45 days', 'Chief Audit Executive')
ON CONFLICT DO NOTHING;

-- 4. Plan Items
INSERT INTO audit_plan_items (id, tenant_id, plan_id, audit_entity_id, title, audit_type, priority, planned_start_date, planned_end_date, budget_hours, assigned_lead, status, rationale)
VALUES
  ('a1000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'a0000001-0000-4000-a000-000000000001', 'e0000001-0000-4000-a000-000000000001', 'Core Banking IT General Controls', 'internal', 'critical', '2026-01-13', '2026-03-14', 800, 'Alex Morgan', 'in_progress', 'Highest risk entity; regulatory exam expected Q3 2026'),
  ('a1000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'a0000001-0000-4000-a000-000000000001', 'e0000001-0000-4000-a000-000000000002', 'Accounts Payable Controls Review', 'internal', 'high', '2026-02-02', '2026-03-27', 400, 'Jordan Lee', 'in_progress', 'Three AP exceptions flagged in prior year; follow-up required'),
  ('a1000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'a0000001-0000-4000-a000-000000000001', 'e0000001-0000-4000-a000-000000000004', 'IAM Privileged Access Review', 'internal', 'critical', '2026-03-02', '2026-04-11', 320, 'Alex Morgan', 'scheduled', 'SOX ITGC requirement; privileged user count increased 40% YoY')
ON CONFLICT DO NOTHING;

-- 5. Engagements
INSERT INTO audit_engagements (id, tenant_id, plan_item_id, title, engagement_code, audit_type, status, scope, objectives, planned_start_date, planned_end_date, actual_start_date, budget_hours, lead_auditor, team_members, engagement_manager)
VALUES
  ('a2000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'a1000001-0000-4000-a000-000000000001', 'Core Banking IT General Controls Audit', 'AUD-2026-001', 'internal', 'fieldwork', 'Core Banking Platform v12.4 and all supporting infrastructure, covering period Jan 1 2025 to Dec 31 2025. Excludes third-party payment processors covered under TPRM.', 'Evaluate design and operating effectiveness of IT general controls: (1) access management, (2) change management, (3) IT operations, (4) data backup and recovery. Assess alignment with SOX ITGC and PCI DSS 4.0.', '2026-01-13', '2026-03-14', '2026-01-13', 800, 'Alex Morgan', ARRAY['Dana Singh', 'Chris Webb', 'Pat Nguyen'], 'Jordan Lee'),
  ('a2000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'a1000001-0000-4000-a000-000000000002', 'Accounts Payable Controls Review', 'AUD-2026-002', 'internal', 'reporting', 'AP transactions processed through Oracle Fusion for the period Oct 1 to Dec 31 2025. Sample population: 2847 invoices totaling $14.2M.', 'Assess compliance with AP Policy v3.2, segregation of duties controls, approval workflow effectiveness, and duplicate payment detection. Respond to three prior-year findings (AP-01, AP-02, AP-03).', '2026-02-02', '2026-03-27', '2026-02-02', 400, 'Jordan Lee', ARRAY['Taylor Brooks', 'Sam Rivera'], 'Chris Webb'),
  ('a2000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'a1000001-0000-4000-a000-000000000003', 'IAM Privileged Access Review', 'AUD-2026-003', 'internal', 'planning', 'All privileged accounts across 14 production systems, including database admins, network admins, and service accounts. Scope period: Q1 2026.', 'Verify privileged access is provisioned on least-privilege basis, periodic re-certification is performed, and orphaned accounts are removed within SLA. Validate against CIS Controls v8 safeguards 5.4 and 6.8.', '2026-03-02', '2026-04-11', NULL, 320, 'Alex Morgan', ARRAY['Dana Singh', 'Riley Cox'], 'Jordan Lee')
ON CONFLICT DO NOTHING;

-- 6. Milestones
INSERT INTO audit_milestones (id, tenant_id, engagement_id, title, milestone_type, due_date, completed_date, status, owner, notes)
VALUES
  ('a3000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Kickoff Meeting', 'kickoff', '2026-01-13', '2026-01-13', 'completed', 'Alex Morgan', 'Kickoff held with IT management and CISO. Audit charter signed.'),
  ('a3000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Planning Complete', 'planning_complete', '2026-01-24', '2026-01-24', 'completed', 'Alex Morgan', 'Risk assessment and audit program finalized.'),
  ('a3000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Fieldwork Start', 'fieldwork_start', '2026-01-27', '2026-01-27', 'completed', 'Dana Singh', 'Testing commenced on access management controls.'),
  ('a3000001-0000-4000-a000-000000000004', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Fieldwork Complete', 'fieldwork_complete', '2026-02-28', NULL, 'overdue', 'Dana Singh', 'Testing in progress, 68% complete. 2 findings identified.'),
  ('a3000001-0000-4000-a000-000000000005', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Draft Report Issued', 'draft_report', '2026-03-07', NULL, 'pending', 'Alex Morgan', NULL),
  ('a3000001-0000-4000-a000-000000000006', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Management Response', 'management_response', '2026-03-14', NULL, 'pending', 'Alex Morgan', NULL),
  ('a3000001-0000-4000-a000-000000000007', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000002', 'Kickoff Meeting', 'kickoff', '2026-02-02', '2026-02-02', 'completed', 'Jordan Lee', NULL),
  ('a3000001-0000-4000-a000-000000000008', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000002', 'Fieldwork Complete', 'fieldwork_complete', '2026-03-07', '2026-03-07', 'completed', 'Taylor Brooks', 'All 80 transaction samples tested. 2 exceptions noted.'),
  ('a3000001-0000-4000-a000-000000000009', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000002', 'Draft Report', 'draft_report', '2026-03-14', '2026-03-14', 'completed', 'Jordan Lee', 'Draft issued to VP Finance on 14-Mar.'),
  ('a3000001-0000-4000-a000-000000000010', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000002', 'Management Response Due', 'management_response', '2026-03-21', NULL, 'overdue', 'Jordan Lee', 'Response overdue by 3 weeks. Escalated to CAE.'),
  ('a3000001-0000-4000-a000-000000000011', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000003', 'Kickoff Meeting', 'kickoff', '2026-03-03', '2026-03-03', 'completed', 'Alex Morgan', 'Kickoff held with IAM team.'),
  ('a3000001-0000-4000-a000-000000000012', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000003', 'Planning Complete', 'planning_complete', '2026-04-11', NULL, 'in_progress', 'Alex Morgan', 'Risk assessment 80% complete.')
ON CONFLICT DO NOTHING;

-- 7. Resource Assignments
INSERT INTO resource_assignments (id, tenant_id, engagement_id, auditor_name, auditor_email, role, allocated_hours, start_date, end_date, is_active)
VALUES
  ('a4000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Alex Morgan', 'a.morgan@acme.com', 'lead', 320, '2026-01-13', '2026-03-14', true),
  ('a4000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Dana Singh', 'd.singh@acme.com', 'staff', 200, '2026-01-27', '2026-03-14', true),
  ('a4000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Chris Webb', 'c.webb@acme.com', 'staff', 160, '2026-01-27', '2026-03-14', true),
  ('a4000001-0000-4000-a000-000000000004', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000002', 'Jordan Lee', 'j.lee@acme.com', 'lead', 160, '2026-02-02', '2026-03-27', true),
  ('a4000001-0000-4000-a000-000000000005', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000002', 'Taylor Brooks', 't.brooks@acme.com', 'staff', 120, '2026-02-02', '2026-03-27', true),
  ('a4000001-0000-4000-a000-000000000006', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000003', 'Alex Morgan', 'a.morgan@acme.com', 'lead', 140, '2026-03-02', '2026-04-11', true),
  ('a4000001-0000-4000-a000-000000000007', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000003', 'Dana Singh', 'd.singh@acme.com', 'staff', 100, '2026-03-02', '2026-04-11', true)
ON CONFLICT DO NOTHING;

-- 8. Time Entries
INSERT INTO time_entries (tenant_id, engagement_id, auditor_name, auditor_email, entry_date, hours, activity_type, description, is_billable)
VALUES
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Alex Morgan', 'a.morgan@acme.com', '2026-01-13', 4.0, 'planning', 'Kickoff meeting preparation and execution', true),
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Alex Morgan', 'a.morgan@acme.com', '2026-01-14', 7.5, 'planning', 'Risk assessment walkthrough with IT management', true),
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Dana Singh', 'd.singh@acme.com', '2026-01-27', 8.0, 'fieldwork', 'User access review, pulling AD groups and entitlements', true),
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Dana Singh', 'd.singh@acme.com', '2026-01-28', 8.0, 'fieldwork', 'Comparing entitlements to provisioning tickets (50 samples)', true),
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Chris Webb', 'c.webb@acme.com', '2026-02-03', 7.0, 'fieldwork', 'Change management control testing, 25 change tickets reviewed', true),
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Chris Webb', 'c.webb@acme.com', '2026-02-04', 6.5, 'fieldwork', 'Change management exception documentation', true),
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Alex Morgan', 'a.morgan@acme.com', '2026-02-10', 5.0, 'review', 'Reviewed Dana test work for access management section', true),
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Pat Nguyen', 'p.nguyen@acme.com', '2026-02-17', 8.0, 'fieldwork', 'Backup and recovery testing, DR runbooks and last 90-day logs', true),
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000002', 'Jordan Lee', 'j.lee@acme.com', '2026-02-03', 6.0, 'planning', 'AP process walkthrough with Controller', true),
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000002', 'Taylor Brooks', 't.brooks@acme.com', '2026-02-10', 8.0, 'fieldwork', 'Invoice testing, pulled Oracle report, 40 samples selected', true),
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000002', 'Taylor Brooks', 't.brooks@acme.com', '2026-02-11', 8.0, 'fieldwork', 'Matched invoices to POs; 2 missing 3-way match exceptions found', true),
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000002', 'Jordan Lee', 'j.lee@acme.com', '2026-03-01', 7.5, 'reporting', 'Draft report preparation, findings writeup', true),
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000003', 'Alex Morgan', 'a.morgan@acme.com', '2026-03-03', 3.5, 'planning', 'Kickoff meeting with IAM team and CISO', true),
  ('00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000003', 'Dana Singh', 'd.singh@acme.com', '2026-03-04', 6.0, 'planning', 'Preliminary data request, pulling privileged account listings', true);

-- =============================================================================
-- TC-02: Risk Management
-- =============================================================================
INSERT INTO risks (id, tenant_id, risk_id, title, description, category_id, owner, department, status, inherent_likelihood, inherent_impact, residual_likelihood, residual_impact, target_likelihood, target_impact, source, identified_date, review_date)
VALUES
  ('a5000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'RSK-2026-001', 'Ransomware Attack on Core Banking', 'Threat actors encrypt core banking data, causing system unavailability and potential data loss. Increased risk due to recent sector-wide attacks.', '1f70b934-b71c-4b6e-8e3b-01a6c82a3645', 'Laura Kim', 'Cybersecurity', 'open', 4, 5, 2, 5, 2, 3, 'manual', '2026-01-15', '2026-07-15'),
  ('a5000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'RSK-2026-002', 'Unauthorized Privileged Access', 'Privilege escalation or misuse by insiders or compromised credentials resulting in unauthorized access to sensitive financial data.', '1f70b934-b71c-4b6e-8e3b-01a6c82a3645', 'James Parker', 'Technology', 'open', 3, 5, 2, 4, 1, 3, 'manual', '2026-01-20', '2026-04-20'),
  ('a5000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'RSK-2026-003', 'AP Duplicate Payment Fraud', 'Duplicate or fictitious invoices processed due to inadequate 3-way match controls, leading to financial loss and regulatory scrutiny.', '2884a6a9-33cd-4633-aa2f-4b6403216046', 'Sarah Chen', 'Finance', 'open', 3, 4, 2, 3, 1, 3, 'manual', '2026-02-01', '2026-05-01'),
  ('a5000001-0000-4000-a000-000000000004', '00000000-0000-0000-0000-000000000001', 'RSK-2026-004', 'SOX Compliance Gap', 'Failure to maintain adequate SOX ITGC controls resulting in material weakness finding during external audit.', '9e9a5167-a3b0-4c89-9b00-80e87cc43a0f', 'Alex Morgan', 'Audit', 'open', 2, 5, 2, 4, 1, 4, 'manual', '2026-01-10', '2026-06-10'),
  ('a5000001-0000-4000-a000-000000000005', '00000000-0000-0000-0000-000000000001', 'RSK-2026-005', 'Third-Party Vendor Data Breach', 'A key vendor with access to Acme customer PII suffers a data breach, exposing regulated data and triggering notification obligations.', '08fc7b7f-b10c-4f72-a8e9-992aed1345e7', 'Jordan Lee', 'Operations', 'open', 3, 4, 2, 3, 2, 3, 'manual', '2026-01-25', '2026-07-25'),
  ('a5000001-0000-4000-a000-000000000006', '00000000-0000-0000-0000-000000000001', 'RSK-2026-006', 'Critical Talent Loss in Audit Team', 'Departure of experienced audit staff reduces audit coverage capacity and institutional knowledge for regulatory exams.', 'b0354a2a-d775-4e1c-80cf-74318c63cbd3', 'Jordan Lee', 'Audit', 'open', 2, 3, 2, 2, 1, 2, 'manual', '2026-02-15', '2026-08-15'),
  ('a5000001-0000-4000-a000-000000000007', '00000000-0000-0000-0000-000000000001', 'RSK-2026-007', 'Core Banking System Outage', 'Extended unplanned downtime of core banking platform due to software defect or infrastructure failure.', '30a491ea-7416-4a40-9cc8-8c66d7c5db71', 'James Parker', 'Technology', 'open', 2, 5, 1, 5, 1, 4, 'manual', '2026-01-05', '2026-07-05')
ON CONFLICT DO NOTHING;

-- Risk Treatments
INSERT INTO risk_treatments (id, tenant_id, risk_id, treatment_type, description, owner, target_date, status, created_at)
VALUES
  ('a6000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'a5000001-0000-4000-a000-000000000001', 'mitigate', 'Deploy endpoint detection and response (EDR) across all servers; implement immutable backup architecture with offline copies; conduct tabletop ransomware simulation exercise by Q2 2026.', 'Laura Kim', '2026-06-30', 'in_progress', NOW()),
  ('a6000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'a5000001-0000-4000-a000-000000000002', 'mitigate', 'Implement CyberArk PAM for all privileged accounts; enforce MFA on all privileged sessions; conduct quarterly access re-certifications.', 'James Parker', '2026-05-31', 'in_progress', NOW()),
  ('a6000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'a5000001-0000-4000-a000-000000000003', 'mitigate', 'Implement mandatory 3-way match on all invoices above $5K; deploy duplicate payment detection algorithm; restrict vendor master edits to segregated role.', 'Sarah Chen', '2026-04-30', 'completed', NOW()),
  ('a6000001-0000-4000-a000-000000000004', '00000000-0000-0000-0000-000000000001', 'a5000001-0000-4000-a000-000000000004', 'mitigate', 'Remediate 3 open ITGC findings from prior audit by Q2 2026; implement continuous control monitoring for key SOX controls.', 'Alex Morgan', '2026-06-30', 'in_progress', NOW())
ON CONFLICT DO NOTHING;

-- =============================================================================
-- TC-03: PBC / Workpapers
-- =============================================================================
INSERT INTO workpapers (id, tenant_id, engagement_id, title, wp_reference, workpaper_type, preparer, reviewer, status, review_notes)
VALUES
  ('a7000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'User Access Review — Core Banking', 'WP-001', 'control_test', 'Dana Singh', 'Alex Morgan', 'in_review', 'Two exceptions identified: (1) 3 terminated users with active accounts, (2) 1 DBA with excessive permissions. Findings documented in finding sheet.'),
  ('a7000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Change Management Control Testing', 'WP-002', 'control_test', 'Chris Webb', 'Alex Morgan', 'reviewed', 'All 25 changes reviewed. 1 emergency change lacked post-implementation review. Finding rated Low.'),
  ('a7000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000001', 'Backup and Recovery Testing', 'WP-003', 'control_test', 'Pat Nguyen', 'Alex Morgan', 'draft', NULL),
  ('a7000001-0000-4000-a000-000000000004', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000002', 'Invoice Sample Testing — 3-Way Match', 'WP-004', 'substantive_test', 'Taylor Brooks', 'Jordan Lee', 'reviewed', 'Population: 2847 invoices, $14.2M. Sample: 80 items. 2 exceptions: invoices #INV-4892 and #INV-5103 processed without matching PO.'),
  ('a7000001-0000-4000-a000-000000000005', '00000000-0000-0000-0000-000000000001', 'a2000001-0000-4000-a000-000000000002', 'Vendor Master Change Review', 'WP-005', 'control_test', 'Sam Rivera', 'Jordan Lee', 'final', NULL)
ON CONFLICT DO NOTHING;

INSERT INTO workpaper_sections (tenant_id, workpaper_id, section_key, title, content, sort_order, is_complete)
VALUES
  ('00000000-0000-0000-0000-000000000001', 'a7000001-0000-4000-a000-000000000001', 'objective', 'Audit Objective', '{"text": "Determine whether user access to Core Banking Platform is provisioned on a least-privilege basis and that terminated employees have access removed within the 24-hour SLA."}', 1, true),
  ('00000000-0000-0000-0000-000000000001', 'a7000001-0000-4000-a000-000000000001', 'population', 'Population and Sample', '{"text": "Population: 847 active user accounts as of Jan 31 2026. Sample: 50 accounts selected using random sampling with bias toward privileged roles."}', 2, true),
  ('00000000-0000-0000-0000-000000000001', 'a7000001-0000-4000-a000-000000000001', 'testing', 'Testing Performed', '{"text": "Compared active AD accounts against HR terminated employee list. Cross-referenced role assignments against provisioning request tickets."}', 3, true),
  ('00000000-0000-0000-0000-000000000001', 'a7000001-0000-4000-a000-000000000001', 'results', 'Results and Exceptions', '{"text": "3 exceptions: accounts for terminated employees J. Davis (terminated 2025-12-15), M. Okafor (terminated 2025-11-30), R. Patel (terminated 2026-01-05) were still active at time of testing. 1 DBA account had permissions exceeding job requirements.", "exception_count": 4, "sample_size": 50}', 4, true),
  ('00000000-0000-0000-0000-000000000001', 'a7000001-0000-4000-a000-000000000004', 'objective', 'Audit Objective', '{"text": "Assess whether all AP invoices are subject to adequate 3-way match controls (purchase order, goods receipt, invoice) before payment approval."}', 1, true),
  ('00000000-0000-0000-0000-000000000001', 'a7000001-0000-4000-a000-000000000004', 'results', 'Results and Exceptions', '{"text": "78 of 80 samples passed. 2 exceptions: Invoice #INV-4892 ($23,450 to TechVend LLC) and Invoice #INV-5103 ($8,200 to OfficeSupply Co) processed without matching PO. Both payments already disbursed.", "exception_count": 2, "sample_size": 80}', 2, true)
ON CONFLICT DO NOTHING;

-- =============================================================================
-- TC-04: Compliance Frameworks
-- =============================================================================
INSERT INTO compliance_frameworks (id, slug, name, version, category, description, issuing_body, is_active)
VALUES
  ('a8000001-0000-4000-a000-000000000001', 'nist-csf-2', 'NIST Cybersecurity Framework', '2.0', 'security', 'NIST CSF 2.0 provides guidance to industry, government agencies, and other organizations to manage cybersecurity risks.', 'NIST', true),
  ('a8000001-0000-4000-a000-000000000002', 'iso27001-2022', 'ISO/IEC 27001', '2022', 'security', 'International standard for information security management systems (ISMS).', 'ISO/IEC', true),
  ('a8000001-0000-4000-a000-000000000003', 'sox-itgc', 'SOX IT General Controls', '2024', 'financial', 'IT General Controls framework aligned with Sarbanes-Oxley Section 302 and 404 requirements.', 'PCAOB', true)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO tenant_frameworks (id, tenant_id, framework_id, activated_at, target_cert_date, scope_notes, is_active)
VALUES
  ('a9000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'a8000001-0000-4000-a000-000000000001', NOW() - INTERVAL '180 days', NOW() + INTERVAL '180 days', 'All production systems and cloud infrastructure in scope. Excludes legacy mainframe (decommission scheduled Q3 2026).', true),
  ('a9000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'a8000001-0000-4000-a000-000000000002', NOW() - INTERVAL '365 days', NOW() + INTERVAL '90 days', 'Full ISMS scope: HQ, DR site, and all cloud services. Surveillance audit scheduled May 2026.', true),
  ('a9000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'a8000001-0000-4000-a000-000000000003', NOW() - INTERVAL '730 days', NULL, 'In-scope systems: Core Banking, Oracle Fusion ERP, Workday HRIS. External auditor: Deloitte.', true)
ON CONFLICT DO NOTHING;

-- =============================================================================
-- TC-05: Vendor / TPRM
-- =============================================================================
INSERT INTO vendors (id, tenant_id, name, website, description, vendor_type, risk_tier, status, primary_contact_name, primary_contact_email, data_types_processed, integrations_depth, processes_pii, processes_phi, processes_pci, uses_ai, inherent_risk_score, residual_risk_score, last_reviewed_at, next_review_at)
VALUES
  ('aa000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'CloudSec Analytics', 'https://cloudsec-example.com', 'SIEM and threat intelligence platform processing log data from all production systems.', 'technology', 'critical', 'active', 'Jason Wu', 'j.wu@cloudsec-example.com', ARRAY['log_data', 'security_events', 'pii'], 'deep', true, false, false, true, 8.5, 6.2, NOW() - INTERVAL '90 days', NOW() + INTERVAL '90 days'),
  ('aa000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'PaymentGate Corp', 'https://paymentgate-example.com', 'Payment processing gateway handling card transactions and ACH transfers.', 'payment_processor', 'critical', 'active', 'Maria Gonzalez', 'm.gonzalez@paymentgate-example.com', ARRAY['pci_data', 'transaction_data', 'pii'], 'deep', true, false, true, false, 9.0, 7.1, NOW() - INTERVAL '180 days', NOW() + INTERVAL '5 days'),
  ('aa000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'DataGuard Backup Services', 'https://dataguard-example.com', 'Offsite backup and disaster recovery services for all production databases.', 'cloud_provider', 'high', 'active', 'Andrew Kim', 'a.kim@dataguard-example.com', ARRAY['financial_data', 'pii', 'system_backups'], 'medium', true, false, false, false, 7.5, 5.8, NOW() - INTERVAL '120 days', NOW() + INTERVAL '60 days'),
  ('aa000001-0000-4000-a000-000000000004', '00000000-0000-0000-0000-000000000001', 'HR Insights Pro', 'https://hrinsights-example.com', 'HR analytics platform with access to employee data from Workday integration.', 'saas', 'high', 'active', 'Lisa Park', 'l.park@hrinsights-example.com', ARRAY['employee_pii', 'salary_data', 'performance_data'], 'medium', true, false, false, true, 6.8, 5.2, NOW() - INTERVAL '200 days', NOW() - INTERVAL '20 days'),
  ('aa000001-0000-4000-a000-000000000005', '00000000-0000-0000-0000-000000000001', 'OfficeSupply Co', 'https://officesupply-example.com', 'General office supplies vendor. No system access or data processing.', 'supplier', 'low', 'active', 'Bob Chen', 'b.chen@officesupply-example.com', ARRAY[]::text[], 'none', false, false, false, false, 2.0, 2.0, NOW() - INTERVAL '400 days', NOW() + INTERVAL '200 days')
ON CONFLICT DO NOTHING;

INSERT INTO vendor_questionnaires (id, tenant_id, vendor_id, template_slug, template_version, status, sent_at, due_date, completed_at, responses, ai_score, ai_summary)
VALUES
  ('ab000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'aa000001-0000-4000-a000-000000000001', 'caiq-v4', '4.0', 'completed', NOW() - INTERVAL '60 days', NOW() - INTERVAL '30 days', NOW() - INTERVAL '25 days', '{"GRM-01": {"answer": "yes", "evidence": "ISO 27001 certificate attached"}, "AIS-01": {"answer": "yes", "evidence": "AI governance policy v2.1 provided"}, "BCR-01": {"answer": "yes", "evidence": "BCP tested Q4 2025, RTO < 4 hours"}, "DSP-01": {"answer": "yes", "evidence": "Data processing agreement signed 2025-06"}}', 82.5, 'Overall strong security posture. ISO 27001 certified with recent surveillance audit. Minor gaps in AI model documentation and supply chain risk assessment. Recommend annual re-assessment with focus on AI governance maturity.'),
  ('ab000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'aa000001-0000-4000-a000-000000000002', 'caiq-v4', '4.0', 'in_progress', NOW() - INTERVAL '14 days', NOW() + INTERVAL '7 days', NULL, '{"GRM-01": {"answer": "yes", "evidence": "PCI DSS Level 1 cert provided"}, "BCR-01": {"answer": "yes", "evidence": "Quarterly DR tests"}}', NULL, NULL),
  ('ab000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'aa000001-0000-4000-a000-000000000004', 'sig-lite', '2024', 'sent', NOW() - INTERVAL '5 days', NOW() + INTERVAL '25 days', NULL, '{}', NULL, NULL)
ON CONFLICT DO NOTHING;

SELECT 'Seed complete.' AS status,
  (SELECT COUNT(*) FROM audit_engagements WHERE tenant_id = '00000000-0000-0000-0000-000000000001') AS engagements,
  (SELECT COUNT(*) FROM audit_milestones WHERE tenant_id = '00000000-0000-0000-0000-000000000001') AS milestones,
  (SELECT COUNT(*) FROM risks WHERE tenant_id = '00000000-0000-0000-0000-000000000001') AS risks,
  (SELECT COUNT(*) FROM vendors WHERE tenant_id = '00000000-0000-0000-0000-000000000001') AS vendors,
  (SELECT COUNT(*) FROM workpapers WHERE tenant_id = '00000000-0000-0000-0000-000000000001') AS workpapers;
