SET app.tenant_id = '00000000-0000-0000-0000-000000000001';

-- Risk Treatments (with title)
INSERT INTO risk_treatments (id, tenant_id, risk_id, title, treatment_type, description, owner, status, target_date)
VALUES
  ('a6000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'a5000001-0000-4000-a000-000000000001', 'Deploy EDR and Immutable Backup Architecture', 'mitigate', 'Deploy endpoint detection and response across all servers; implement immutable backup architecture with offline copies; conduct tabletop ransomware simulation by Q2 2026.', 'Laura Kim', 'in_progress', '2026-06-30'),
  ('a6000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'a5000001-0000-4000-a000-000000000002', 'Implement CyberArk PAM for Privileged Accounts', 'mitigate', 'Implement CyberArk PAM for all privileged accounts; enforce MFA on all privileged sessions; conduct quarterly access re-certifications.', 'James Parker', 'in_progress', '2026-05-31'),
  ('a6000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'a5000001-0000-4000-a000-000000000003', 'Mandatory 3-Way Match and Duplicate Detection', 'mitigate', 'Implement mandatory 3-way match on all invoices above $5K; deploy duplicate payment detection algorithm; restrict vendor master edits to segregated role.', 'Sarah Chen', 'completed', '2026-04-30'),
  ('a6000001-0000-4000-a000-000000000004', '00000000-0000-0000-0000-000000000001', 'a5000001-0000-4000-a000-000000000004', 'Remediate Open ITGC Findings', 'mitigate', 'Remediate 3 open ITGC findings from prior audit by Q2 2026; implement continuous control monitoring for key SOX controls.', 'Alex Morgan', 'in_progress', '2026-06-30')
ON CONFLICT DO NOTHING;

-- Tenant Frameworks (use real framework IDs from migration-seeded data)
INSERT INTO tenant_frameworks (id, tenant_id, framework_id, activated_at, target_cert_date, scope_notes, is_active)
VALUES
  ('a9000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', '533ea268-b58e-4571-98f7-1a6369b374c0', NOW() - INTERVAL '180 days', NOW() + INTERVAL '180 days', 'All production systems and cloud infrastructure in scope. Excludes legacy mainframe scheduled for decommission Q3 2026.', true),
  ('a9000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', '042d1247-1e1c-4a57-8cee-4fa3efb72b7f', NOW() - INTERVAL '365 days', NOW() + INTERVAL '90 days', 'Full ISMS scope: HQ, DR site, and all cloud services. Surveillance audit scheduled May 2026.', true),
  ('a9000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', '84d7a565-8872-438b-a600-b87683e44769', NOW() - INTERVAL '730 days', NULL, 'In-scope systems: Core Banking, Oracle Fusion ERP, Workday HRIS. External auditor: Deloitte.', true)
ON CONFLICT DO NOTHING;

-- Vendors (valid integrations_depth values)
INSERT INTO vendors (id, tenant_id, name, website, description, vendor_type, risk_tier, status, primary_contact_name, primary_contact_email, data_types_processed, integrations_depth, processes_pii, processes_phi, processes_pci, uses_ai, inherent_risk_score, residual_risk_score, last_reviewed_at, next_review_at)
VALUES
  ('aa000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'CloudSec Analytics', 'https://cloudsec-example.com', 'SIEM and threat intelligence platform processing log data from all production systems.', 'technology', 'critical', 'active', 'Jason Wu', 'j.wu@cloudsec-example.com', ARRAY['log_data', 'security_events', 'pii'], 'read_only', true, false, false, true, 8.5, 6.2, NOW() - INTERVAL '90 days', NOW() + INTERVAL '90 days'),
  ('aa000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'PaymentGate Corp', 'https://paymentgate-example.com', 'Payment processing gateway handling card transactions and ACH transfers.', 'payment_processor', 'critical', 'active', 'Maria Gonzalez', 'm.gonzalez@paymentgate-example.com', ARRAY['pci_data', 'transaction_data', 'pii'], 'core_infrastructure', true, false, true, false, 9.0, 7.1, NOW() - INTERVAL '180 days', NOW() + INTERVAL '5 days'),
  ('aa000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'DataGuard Backup Services', 'https://dataguard-example.com', 'Offsite backup and disaster recovery services for all production databases.', 'cloud_provider', 'high', 'active', 'Andrew Kim', 'a.kim@dataguard-example.com', ARRAY['financial_data', 'pii', 'system_backups'], 'admin', true, false, false, false, 7.5, 5.8, NOW() - INTERVAL '120 days', NOW() + INTERVAL '60 days'),
  ('aa000001-0000-4000-a000-000000000004', '00000000-0000-0000-0000-000000000001', 'HR Insights Pro', 'https://hrinsights-example.com', 'HR analytics platform with access to employee data from Workday integration.', 'saas', 'high', 'active', 'Lisa Park', 'l.park@hrinsights-example.com', ARRAY['employee_pii', 'salary_data', 'performance_data'], 'read_write', true, false, false, true, 6.8, 5.2, NOW() - INTERVAL '200 days', NOW() - INTERVAL '20 days'),
  ('aa000001-0000-4000-a000-000000000005', '00000000-0000-0000-0000-000000000001', 'OfficeSupply Co', 'https://officesupply-example.com', 'General office supplies vendor. No system access or data processing.', 'supplier', 'low', 'active', 'Bob Chen', 'b.chen@officesupply-example.com', ARRAY[]::text[], 'none', false, false, false, false, 2.0, 2.0, NOW() - INTERVAL '400 days', NOW() + INTERVAL '200 days')
ON CONFLICT DO NOTHING;

-- Vendor Questionnaires
INSERT INTO vendor_questionnaires (id, tenant_id, vendor_id, template_slug, template_version, status, sent_at, due_date, completed_at, responses, ai_score, ai_summary)
VALUES
  ('ab000001-0000-4000-a000-000000000001', '00000000-0000-0000-0000-000000000001', 'aa000001-0000-4000-a000-000000000001', 'caiq-v4', '4.0', 'completed', NOW() - INTERVAL '60 days', NOW() - INTERVAL '30 days', NOW() - INTERVAL '25 days', '{"GRM-01": {"answer": "yes", "evidence": "ISO 27001 certificate attached"}, "AIS-01": {"answer": "yes", "evidence": "AI governance policy v2.1 provided"}, "BCR-01": {"answer": "yes", "evidence": "BCP tested Q4 2025, RTO < 4 hours"}, "DSP-01": {"answer": "yes", "evidence": "Data processing agreement signed 2025-06"}}', 82.5, 'Overall strong security posture. ISO 27001 certified. Minor gaps in AI model documentation and supply chain risk assessment.'),
  ('ab000001-0000-4000-a000-000000000002', '00000000-0000-0000-0000-000000000001', 'aa000001-0000-4000-a000-000000000002', 'caiq-v4', '4.0', 'in_progress', NOW() - INTERVAL '14 days', NOW() + INTERVAL '7 days', NULL, '{"GRM-01": {"answer": "yes", "evidence": "PCI DSS Level 1 cert provided"}, "BCR-01": {"answer": "yes", "evidence": "Quarterly DR tests"}}', NULL, NULL),
  ('ab000001-0000-4000-a000-000000000003', '00000000-0000-0000-0000-000000000001', 'aa000001-0000-4000-a000-000000000004', 'sig-lite', '2024', 'sent', NOW() - INTERVAL '5 days', NOW() + INTERVAL '25 days', NULL, '{}', NULL, NULL)
ON CONFLICT DO NOTHING;

SELECT 'Seed complete.' AS status,
  (SELECT COUNT(*) FROM audit_engagements WHERE tenant_id = '00000000-0000-0000-0000-000000000001') AS engagements,
  (SELECT COUNT(*) FROM audit_milestones WHERE tenant_id = '00000000-0000-0000-0000-000000000001') AS milestones,
  (SELECT COUNT(*) FROM risks WHERE tenant_id = '00000000-0000-0000-0000-000000000001') AS risks,
  (SELECT COUNT(*) FROM risk_treatments WHERE tenant_id = '00000000-0000-0000-0000-000000000001') AS treatments,
  (SELECT COUNT(*) FROM tenant_frameworks WHERE tenant_id = '00000000-0000-0000-0000-000000000001') AS frameworks,
  (SELECT COUNT(*) FROM vendors WHERE tenant_id = '00000000-0000-0000-0000-000000000001') AS vendors,
  (SELECT COUNT(*) FROM workpapers WHERE tenant_id = '00000000-0000-0000-0000-000000000001') AS workpapers;
