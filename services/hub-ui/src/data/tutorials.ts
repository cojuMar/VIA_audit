export type Role = 'super_admin' | 'admin' | 'end_user';

export interface TutorialStep {
  title: string;
  content: string;
}

export interface Tutorial {
  id: string;
  title: string;
  description: string;
  category: string;
  duration: string;           // e.g. "10 min"
  difficulty: 'Beginner' | 'Intermediate' | 'Advanced';
  roles: Role[];              // which roles can see this
  module?: string;            // linked module id
  steps: TutorialStep[];
  tags: string[];
}

export const TUTORIALS: Tutorial[] = [
  // ─────────────────────────────────────────────
  //  END USER  (visible to all roles)
  // ─────────────────────────────────────────────
  {
    id: 'welcome',
    title: 'Welcome to Aegis 2026',
    description:
      'A quick orientation to the platform — what it does, who it\'s for, and how to get started.',
    category: 'Getting Started',
    duration: '5 min',
    difficulty: 'Beginner',
    roles: ['super_admin', 'admin', 'end_user'],
    steps: [
      {
        title: 'What is Aegis 2026?',
        content:
          'Aegis 2026 is a tri-modal audit and governance platform. It combines risk management, compliance frameworks, continuous monitoring, audit planning, and ESG reporting into a single integrated system. Every module shares the same data model and talks to the same underlying risk register.',
      },
      {
        title: 'The Hub is Your Home Page',
        content:
          'This hub (port 5173) is your starting point. From here you can launch any of the 12 modules, learn the recommended workflow, and access tutorials tailored to your role. Bookmark http://localhost:5173 as your entry point.',
      },
      {
        title: 'Tenant Scoping',
        content:
          'All data in Aegis is scoped to a tenant. Append ?tenantId=YOUR-UUID to any module URL to scope the data you see. A demo tenant is always available at tenantId=00000000-0000-0000-0000-000000000001.',
      },
      {
        title: 'Getting Help',
        content:
          'Use the AI Agent module (port 5181) to ask platform questions in plain English. It has access to your policy documents and can explain findings, draft narratives, and guide you through workflows.',
      },
    ],
    tags: ['orientation', 'basics'],
  },
  {
    id: 'navigation',
    title: 'Navigating the Platform',
    description:
      'Learn how to move between modules, understand the sidebar, and use global search.',
    category: 'Getting Started',
    duration: '8 min',
    difficulty: 'Beginner',
    roles: ['super_admin', 'admin', 'end_user'],
    steps: [
      {
        title: 'Module Layout',
        content:
          'Each module has a consistent layout: a left sidebar for navigation within that module, a top header showing the current tenant and your role, and a main content area. The sidebar icons always follow the same order — dashboard, list view, create, settings.',
      },
      {
        title: 'Switching Between Modules',
        content:
          'Return to this hub at any time using the "Hub" link in the top-right of any module, or simply navigate to http://localhost:5173. You can have multiple modules open in different browser tabs simultaneously.',
      },
      {
        title: 'Filters and Search',
        content:
          'Every list view supports URL-based filters. You can share filtered views with colleagues by copying the URL. Use the search icon (🔍) in list views to filter by name, status, or date range.',
      },
      {
        title: 'Exporting Data',
        content:
          'Most list views have an Export button that produces CSV or PDF output. The AI Agent can also generate summary narratives from any data set on demand.',
      },
    ],
    tags: ['navigation', 'layout', 'search'],
  },
  {
    id: 'dashboard-basics',
    title: 'Understanding Your Dashboard',
    description: 'Interpret the key metrics, charts, and status indicators shown on each module\'s dashboard.',
    category: 'Getting Started',
    duration: '10 min',
    difficulty: 'Beginner',
    roles: ['super_admin', 'admin', 'end_user'],
    module: 'risk',
    steps: [
      {
        title: 'Risk Heat Map',
        content:
          'The heat map plots risks on a likelihood × impact grid. Risks in the top-right (high likelihood, high impact) are your most critical items. Colors follow a standard traffic-light scheme: red = critical, amber = elevated, green = acceptable.',
      },
      {
        title: 'KRI Status Indicators',
        content:
          'Key Risk Indicators (KRIs) appear as colored dots next to each risk. Green means the indicator is within appetite, amber means approaching the threshold, and red means the threshold has been breached and action is required.',
      },
      {
        title: 'Compliance Posture Widget',
        content:
          'The donut chart on the compliance dashboard shows what percentage of controls are evidenced, partially evidenced, or not started. Use this as a daily health check before beginning fieldwork.',
      },
      {
        title: 'Trend Lines',
        content:
          'Trend charts in the monitoring module show how your control pass rate has changed over time. A declining trend is an early warning signal that should be escalated to the audit team.',
      },
    ],
    tags: ['dashboard', 'metrics', 'kri'],
  },
  {
    id: 'mobile-app',
    title: 'Using the Mobile Field App',
    description:
      'Conduct on-site audits from a mobile browser — take photos, fill checklists, and sync findings.',
    category: 'Field Work',
    duration: '12 min',
    difficulty: 'Beginner',
    roles: ['super_admin', 'admin', 'end_user'],
    module: 'mobile',
    steps: [
      {
        title: 'Opening on Mobile',
        content:
          'Navigate to http://YOUR-SERVER-IP:5185 on your phone or tablet. The app is a Progressive Web App (PWA) — you can "Add to Home Screen" for an app-like experience. It works offline once cached.',
      },
      {
        title: 'Starting a Walkthrough',
        content:
          'Select an active engagement from the list, then tap "New Walkthrough". Choose a control from the library or enter a custom test procedure. The app will guide you through each test step.',
      },
      {
        title: 'Capturing Evidence',
        content:
          'Tap the camera icon on any finding to attach a photo directly from your device. Photos are compressed and synced to MinIO when connectivity is restored. Add annotations or notes in the text field below each photo.',
      },
      {
        title: 'Syncing Findings',
        content:
          'Tap the sync icon (↑) in the top-right when you have a connection. The app shows a badge with the number of pending offline items. Synced findings appear immediately in the PBC module and Audit Planning module.',
      },
    ],
    tags: ['mobile', 'field', 'offline', 'pwa'],
  },
  {
    id: 'trust-portal-client',
    title: 'The Client Trust Portal',
    description:
      'How clients and external stakeholders interact with your published compliance data.',
    category: 'Sharing & Reporting',
    duration: '7 min',
    difficulty: 'Beginner',
    roles: ['super_admin', 'admin', 'end_user'],
    module: 'trust-portal',
    steps: [
      {
        title: 'What Clients See',
        content:
          'Your clients access a branded portal at port 5176. They can download the documents you\'ve published — security policies, SOC 2 reports, penetration test summaries — and ask compliance questions via the embedded AI chatbot.',
      },
      {
        title: 'Sharing a Document',
        content:
          'In the Trust Portal module, click "Publish Document", choose the file from your workpaper library, set visibility (public or invite-only), and save. The document is immediately available to authorized visitors.',
      },
      {
        title: 'Chatbot Interactions',
        content:
          'The portal chatbot is powered by your own RAG pipeline. It answers questions based only on documents you\'ve published — it will never reveal unpublished data. Review chatbot conversations in the "Chat Logs" section.',
      },
    ],
    tags: ['trust-portal', 'clients', 'sharing'],
  },
  {
    id: 'reading-reports',
    title: 'Reading Risk & Compliance Reports',
    description: 'Understand the standard report formats and know which report to use for which audience.',
    category: 'Reporting',
    duration: '10 min',
    difficulty: 'Beginner',
    roles: ['super_admin', 'admin', 'end_user'],
    steps: [
      {
        title: 'Executive Summary',
        content:
          'The one-page executive summary is auto-generated from the risk register and compliance posture. It is suitable for a CFO or board member who needs a quick status update. Find it under Reports → Executive Summary in any module.',
      },
      {
        title: 'Detailed Findings Report',
        content:
          'The detailed findings report lists every open finding, its severity, owner, and remediation deadline. Use this report in daily standup meetings with the audit team. It is filterable by module, severity, and status.',
      },
      {
        title: 'Evidence Packages',
        content:
          'Evidence packages are ZIP archives containing all workpapers for a specific engagement. They are generated from the PBC module once all requests are fulfilled and reviewed. Auditors receive evidence packages directly from the portal.',
      },
    ],
    tags: ['reports', 'evidence', 'executive'],
  },

  // ─────────────────────────────────────────────
  //  ADMIN  (visible to admin + super_admin)
  // ─────────────────────────────────────────────
  {
    id: 'risk-workflow',
    title: 'End-to-End Risk Management Workflow',
    description:
      'From identifying a risk to closing a treatment — the complete lifecycle inside the Risk module.',
    category: 'Risk Management',
    duration: '20 min',
    difficulty: 'Intermediate',
    roles: ['super_admin', 'admin'],
    module: 'risk',
    steps: [
      {
        title: 'Creating a Risk',
        content:
          'Navigate to Risk Management (5182) → Risks → New Risk. Fill in the title, description, likelihood (1-5), impact (1-5), and assign an owner. Attach it to a risk category (e.g. Operational, Cyber, Regulatory). The inherent score is calculated automatically.',
      },
      {
        title: 'Setting Risk Appetite',
        content:
          'Go to Appetite → Configure to define your organization\'s risk tolerance thresholds per category. Risks exceeding the appetite boundary will automatically surface in the red zone of the heat map and trigger KRI alerts.',
      },
      {
        title: 'Adding Key Risk Indicators',
        content:
          'In the risk detail view, click "Add KRI". Define the metric name, data source, and threshold values for green/amber/red. The system will evaluate the KRI on each new reading and update the risk status automatically.',
      },
      {
        title: 'Creating a Treatment Plan',
        content:
          'Click "Add Treatment" on any risk. Choose a treatment type (Accept, Mitigate, Transfer, Avoid), assign an owner, set a due date, and describe the control action. Treatments appear in the treatment tracker where progress is reported monthly.',
      },
      {
        title: 'Linking to Monitoring',
        content:
          'Risks can be linked to monitoring control tests. When a test fails in the monitoring module, the linked risk is automatically flagged for review. This closes the loop between continuous monitoring and the risk register.',
      },
    ],
    tags: ['risk', 'treatment', 'kri', 'appetite', 'workflow'],
  },
  {
    id: 'compliance-setup',
    title: 'Setting Up Compliance Frameworks',
    description: 'Import a framework, map controls to your environment, and assign evidence owners.',
    category: 'Compliance',
    duration: '25 min',
    difficulty: 'Intermediate',
    roles: ['super_admin', 'admin'],
    module: 'framework',
    steps: [
      {
        title: 'Importing a Framework',
        content:
          'Go to Compliance Frameworks (5174) → Frameworks → Import. Choose from built-in frameworks (NIST CSF, ISO 27001, SOC 2 Type II, PCI-DSS 4.0, CIS Controls v8) or upload a custom CSV. Each control is tagged with domain, category, and sub-category.',
      },
      {
        title: 'Mapping Controls to Assets',
        content:
          'Select a framework and click "Map Controls". For each control, assign the systems, processes, or people it applies to. This mapping drives what evidence is requested in PBC lists and what tests are scheduled in the monitoring module.',
      },
      {
        title: 'Assigning Control Owners',
        content:
          'Each control should have a designated owner responsible for maintaining evidence. Assign owners in bulk by filtering by domain and using the "Assign All" action. Owners receive automated email reminders when evidence is stale.',
      },
      {
        title: 'Evidence Status Lifecycle',
        content:
          'Controls move through a status lifecycle: Not Started → In Progress → Evidence Provided → Under Review → Evidenced. Only controls in the "Evidenced" state count toward your compliance percentage on the dashboard.',
      },
    ],
    tags: ['framework', 'controls', 'evidence', 'iso', 'soc2'],
  },
  {
    id: 'audit-planning-workflow',
    title: 'Planning and Running an Audit Engagement',
    description:
      'Build an audit universe, schedule an engagement, assign a team, and manage fieldwork to completion.',
    category: 'Audit Planning',
    duration: '30 min',
    difficulty: 'Intermediate',
    roles: ['super_admin', 'admin'],
    module: 'audit-planning',
    steps: [
      {
        title: 'Building the Audit Universe',
        content:
          'Go to Audit Planning (5183) → Universe. Add auditable entities — business units, systems, processes, or vendors. For each entity, set the risk ranking (pulled from the risk register), audit frequency, and last audit date. The system highlights overdue audits automatically.',
      },
      {
        title: 'Creating an Engagement',
        content:
          'Click "New Engagement". Select auditable entities, set the planned start and end dates, choose the audit type (internal, external, SOC 2, PCI, etc.), and assign a lead auditor. The engagement is now visible on the team calendar.',
      },
      {
        title: 'Issuing PBC Requests',
        content:
          'From the engagement detail, click "Issue PBC List". Choose controls from the framework mapping to auto-populate the request list. Clients receive a notification and can upload documents directly to the portal.',
      },
      {
        title: 'Tracking Fieldwork Progress',
        content:
          'The engagement dashboard shows a progress bar broken down by phase: Planning, Fieldwork, Review, Reporting. Click any phase to see individual test procedures and their completion status. Use the mobile app for on-site walkthroughs.',
      },
      {
        title: 'Closing the Engagement',
        content:
          'Once all findings are addressed and workpapers signed off, click "Close Engagement". This locks the engagement record, generates the final evidence package, and moves all linked open risks to the post-audit treatment tracking phase.',
      },
    ],
    tags: ['audit', 'engagement', 'pbc', 'fieldwork', 'planning'],
  },
  {
    id: 'vendor-assessment',
    title: 'Running a Vendor Risk Assessment',
    description:
      'Onboard a new vendor, send a questionnaire, score the assessment, and track remediation.',
    category: 'Vendor Risk',
    duration: '18 min',
    difficulty: 'Intermediate',
    roles: ['super_admin', 'admin'],
    module: 'tprm',
    steps: [
      {
        title: 'Onboarding a Vendor',
        content:
          'Go to Vendor / TPRM (5175) → Vendors → Add Vendor. Enter company details, primary contact, contract dates, and data access level (none, limited, broad). The system automatically calculates an inherent risk score based on data access and service criticality.',
      },
      {
        title: 'Sending a Questionnaire',
        content:
          'Select the vendor and click "Send Assessment". Choose a questionnaire template (Standard SIG Lite, CAIQ, or custom). The vendor receives an email with a secure link and can complete the form without requiring a platform account.',
      },
      {
        title: 'Scoring the Response',
        content:
          'When the vendor submits their response, go to Assessments → Review. Score each domain on a 1-5 scale. The system calculates a residual risk score automatically. Flag any non-compliant responses for remediation.',
      },
      {
        title: 'Tracking Remediation',
        content:
          'For each flagged item, create a remediation request with a deadline. The vendor is notified by email. Monitor the status in the vendor detail view. Overdue remediations escalate automatically to the vendor owner.',
      },
    ],
    tags: ['vendor', 'tprm', 'questionnaire', 'assessment'],
  },
  {
    id: 'monitoring-setup',
    title: 'Setting Up Continuous Monitoring',
    description:
      'Configure automated control tests, connect data sources, and interpret finding severities.',
    category: 'Monitoring',
    duration: '22 min',
    difficulty: 'Intermediate',
    roles: ['super_admin', 'admin'],
    module: 'monitoring',
    steps: [
      {
        title: 'Connecting a Data Source',
        content:
          'Go to Integrations (5180) → Connectors → New. Choose your data source (AWS CloudTrail, Azure Activity Log, GitHub, Okta, etc.) and provide API credentials. The integration service will begin pulling events on the configured schedule.',
      },
      {
        title: 'Creating a Control Test',
        content:
          'In the Monitoring module (5177), click "New Test". Select the linked compliance control, define the test logic (e.g. "MFA enabled for all admin users"), set the severity, and configure the run schedule (hourly, daily, weekly).',
      },
      {
        title: 'Reviewing Findings',
        content:
          'Each test failure generates a finding. Findings are triaged by severity: Critical, High, Medium, Low, Informational. Review findings in the Findings queue, assign owners, and set remediation deadlines.',
      },
      {
        title: 'Suppressing False Positives',
        content:
          'If a finding is a known exception, click "Suppress" and add a business justification. Suppressed findings are excluded from your pass rate metrics but remain in the audit trail. Suppressions expire automatically after 90 days.',
      },
    ],
    tags: ['monitoring', 'controls', 'findings', 'automation'],
  },
  {
    id: 'esg-reporting',
    title: 'ESG Metrics & Board Reporting',
    description: 'Track ESG KPIs, align to GRI/SASB, and generate board-ready reports.',
    category: 'ESG',
    duration: '20 min',
    difficulty: 'Intermediate',
    roles: ['super_admin', 'admin'],
    module: 'esg',
    steps: [
      {
        title: 'Defining ESG Metrics',
        content:
          'Go to ESG & Board (5184) → Metrics → Configure. Map your KPIs to standard frameworks (GRI, SASB, TCFD). For each metric, define the unit of measure, reporting frequency, and data owner responsible for updating figures.',
      },
      {
        title: 'Recording Metric Values',
        content:
          'Click a metric and select "Add Data Point". Enter the value for the reporting period. The system plots trends automatically and compares against prior-year figures and industry benchmarks where available.',
      },
      {
        title: 'Generating a Board Report',
        content:
          'Go to Reports → Board Pack. Select the reporting period and the sections to include (Executive Summary, Risk Overview, Compliance Posture, ESG Scorecard). The report is generated as a professional PDF ready for board distribution.',
      },
      {
        title: 'Committee Workflows',
        content:
          'Use the Board Committee module to manage meeting agendas, track action items, and record minutes. Action items from board meetings can be linked directly to risks and treatment plans for end-to-end governance tracking.',
      },
    ],
    tags: ['esg', 'board', 'reporting', 'gri', 'sasb'],
  },
  {
    id: 'team-management',
    title: 'Managing Your Audit Team',
    description: 'Assign roles, manage workloads, and track team capacity across engagements.',
    category: 'Administration',
    duration: '15 min',
    difficulty: 'Intermediate',
    roles: ['super_admin', 'admin'],
    module: 'people',
    steps: [
      {
        title: 'Adding Team Members',
        content:
          'Go to People & Policy (5178) → Team → Invite User. Enter their email and assign a role (Admin, Auditor, Read-Only). They will receive an invitation email. New users are scoped to the current tenant by default.',
      },
      {
        title: 'Assigning to Engagements',
        content:
          'From the Audit Planning engagement detail, click "Manage Team". Select team members from the people directory and assign them a role on the engagement (Lead Auditor, Staff Auditor, Reviewer, Client Liaison).',
      },
      {
        title: 'Tracking Capacity',
        content:
          'The Team Capacity view shows each member\'s active engagement load as a percentage. Aim to keep individuals below 80% to allow buffer for urgent findings and reviews. The view highlights over-allocated team members in amber.',
      },
    ],
    tags: ['team', 'people', 'capacity', 'roles'],
  },
  {
    id: 'ai-agent-usage',
    title: 'Getting the Most from the AI Agent',
    description:
      'Learn how to use the AI Agent for narrative drafting, control Q&A, and risk commentary.',
    category: 'AI Tools',
    duration: '15 min',
    difficulty: 'Intermediate',
    roles: ['super_admin', 'admin'],
    module: 'ai-agent',
    steps: [
      {
        title: 'Starting a Conversation',
        content:
          'Open the AI Agent Platform (5181) and start a new session. Type your question in natural language. The agent has access to your risk register, compliance frameworks, monitoring findings, and published policy documents.',
      },
      {
        title: 'Drafting Narratives',
        content:
          'Ask the agent: "Draft an executive summary of our current compliance posture for the Q2 board meeting." It will pull data from your live dashboards and produce a professional narrative you can copy into your board pack.',
      },
      {
        title: 'Answering Audit Questions',
        content:
          'Ask control-specific questions like: "What evidence do we have for ISO 27001 control A.9.4.2?" The agent searches your workpaper library and summarises what\'s available, flagging any gaps.',
      },
      {
        title: 'Limitations',
        content:
          'The AI Agent does not have access to systems outside Aegis, cannot send emails or make changes on your behalf, and will not answer questions about data from other tenants. Always review AI-generated content before distributing externally.',
      },
    ],
    tags: ['ai', 'agent', 'narrative', 'automation'],
  },

  // ─────────────────────────────────────────────
  //  SUPER ADMIN  (visible only to super_admin)
  // ─────────────────────────────────────────────
  {
    id: 'platform-architecture',
    title: 'Platform Architecture Overview',
    description:
      'A technical deep-dive: services, networking, data flows, and where each component lives.',
    category: 'System Administration',
    duration: '30 min',
    difficulty: 'Advanced',
    roles: ['super_admin'],
    steps: [
      {
        title: 'Service Topology',
        content:
          'Aegis 2026 runs 16 Python FastAPI microservices and 10 React/Vite frontends in Docker containers on a single Docker Compose stack. All services communicate on the aegis-internal Docker network. Only UI containers are exposed on aegis-external for host port publishing.',
      },
      {
        title: 'Data Stores',
        content:
          'PostgreSQL 16 (port 5432) is the primary data store. Every table has a tenant_id column and is protected by Row-Level Security (RLS) policies. Redis (6379) is used for session caching. MinIO (9000/9001) stores binary evidence files and workpapers.',
      },
      {
        title: 'Authentication Flow',
        content:
          'The JWT_SECRET environment variable signs all session tokens. Set a strong secret in .env for production. Tokens are passed as Bearer headers to all API calls. Tenant context is set per database connection using PostgreSQL set_config("app.tenant_id").',
      },
      {
        title: 'Network Architecture',
        content:
          'Two Docker networks exist: aegis-internal (internal:true, no external routing) for service-to-service communication, and aegis-external for host port publishing. nginx containers sit in both networks — they accept requests from the host and proxy to backends over the internal network.',
      },
      {
        title: 'RAG Pipeline',
        content:
          'The rag-pipeline-service handles document ingestion, chunking, embedding, and vector search. Documents uploaded to MinIO are automatically indexed. Embeddings are stored in PostgreSQL with the pgvector extension. The AI Agent queries this pipeline for context-aware responses.',
      },
    ],
    tags: ['architecture', 'docker', 'database', 'networking', 'jwt'],
  },
  {
    id: 'tenant-management',
    title: 'Managing Tenants',
    description:
      'Create, configure, and isolate tenants in the multi-tenant Aegis deployment.',
    category: 'System Administration',
    duration: '20 min',
    difficulty: 'Advanced',
    roles: ['super_admin'],
    steps: [
      {
        title: 'How Multi-tenancy Works',
        content:
          'Each tenant is identified by a UUID. The tenant_id is passed in the X-Tenant-ID header on every API request. PostgreSQL RLS policies automatically restrict all queries to the current tenant — no application-level filtering is needed.',
      },
      {
        title: 'Creating a Tenant',
        content:
          'Use the framework-service API: POST /tenants with a body of {"name": "ACME Corp", "plan": "enterprise"}. A UUID is generated automatically. Seed the tenant with reference data (frameworks, risk categories) using the /tenants/{id}/seed endpoint.',
      },
      {
        title: 'Tenant Isolation Testing',
        content:
          'Always verify tenant isolation after changes. Create two tenants, add data to tenant A, then query with tenant B\'s ID. The response must be empty. The RLS policy on every table enforces this: WHERE tenant_id = current_setting("app.tenant_id")::uuid.',
      },
      {
        title: 'Demo Tenant',
        content:
          'The demo tenant 00000000-0000-0000-0000-000000000001 is seeded by migrations with sample data. It is safe to reset this tenant at any time using the /tenants/demo/reset endpoint. All start.ps1 URLs default to this tenant.',
      },
    ],
    tags: ['tenant', 'multi-tenant', 'rls', 'isolation'],
  },
  {
    id: 'database-admin',
    title: 'Database Administration & Migrations',
    description: 'Apply migrations, manage the schema, and perform routine maintenance.',
    category: 'System Administration',
    duration: '25 min',
    difficulty: 'Advanced',
    roles: ['super_admin'],
    steps: [
      {
        title: 'Migration Strategy',
        content:
          'Aegis uses sequential SQL migration files named V001__description.sql through V023__description.sql. Migrations are applied at startup by start.ps1 using a temporary postgres:16-alpine container. Each migration is idempotent — already-applied migrations are skipped (errors are suppressed with || true).',
      },
      {
        title: 'Adding a New Migration',
        content:
          'Create infra/db/migrations/V024__my_change.sql. Use CREATE TABLE IF NOT EXISTS, ALTER TABLE ... ADD COLUMN IF NOT EXISTS, and CREATE INDEX IF NOT EXISTS to ensure idempotency. Never DROP columns in migrations — use soft deletes (is_deleted boolean) instead.',
      },
      {
        title: 'Connecting Directly',
        content:
          'Connect to PostgreSQL with: psql postgresql://aegis_admin:aegis_dev_pw@localhost:5432/aegis. The aegis_admin role has full DDL access. The aegis_app role (used by services) has DML access only. Never use aegis_admin credentials in application code.',
      },
      {
        title: 'Backup & Restore',
        content:
          'Take a backup with: docker exec POSTGRES_CONTAINER pg_dump -U aegis_admin aegis > backup.sql. Restore with: docker exec -i POSTGRES_CONTAINER psql -U aegis_admin aegis < backup.sql. Schedule daily backups using a cron job or a Docker sidecar.',
      },
    ],
    tags: ['database', 'migrations', 'postgresql', 'backup'],
  },
  {
    id: 'security-configuration',
    title: 'Security Configuration & Hardening',
    description:
      'Environment variables, JWT rotation, network hardening, and production checklist.',
    category: 'System Administration',
    duration: '35 min',
    difficulty: 'Advanced',
    roles: ['super_admin'],
    steps: [
      {
        title: 'Critical Environment Variables',
        content:
          'Always override these in production: JWT_SECRET (min 64 chars, random), POSTGRES_PASSWORD, POSTGRES_APP_PASSWORD, MINIO_ROOT_PASSWORD. Never use the dev defaults in a production deployment. Set them in .env and ensure .env is not committed to git.',
      },
      {
        title: 'JWT Secret Rotation',
        content:
          'To rotate the JWT secret: update JWT_SECRET in .env, restart all API services (docker compose restart), and inform users they will need to log in again (all existing tokens are invalidated). Schedule rotation at least annually or after any suspected compromise.',
      },
      {
        title: 'Network Hardening',
        content:
          'In production, place a reverse proxy (nginx or Traefik) in front of the stack and serve all traffic over HTTPS. Do not expose individual service ports (3020-3035) directly to the internet — only expose the UI ports through the reverse proxy. Restrict MinIO port 9000 to the internal network only.',
      },
      {
        title: 'Audit Trail',
        content:
          'Every tenant_conn database call is executed within a PostgreSQL transaction that sets app.tenant_id. This value is captured by PostgreSQL audit extensions (if configured). Review the trust_portal_access_logs table for a complete record of client portal activity.',
      },
      {
        title: 'Production Readiness Checklist',
        content:
          '□ All default passwords changed  □ JWT_SECRET is 64+ random chars  □ HTTPS enabled via reverse proxy  □ MinIO not publicly accessible  □ PostgreSQL port 5432 not publicly accessible  □ .env not in git  □ Backup schedule configured  □ Log aggregation configured  □ RLS policies tested per tenant',
      },
    ],
    tags: ['security', 'jwt', 'production', 'hardening', 'checklist'],
  },
  {
    id: 'performance-tuning',
    title: 'Performance Tuning & Resource Management',
    description: 'Configure Docker resource limits, tune worker counts, and diagnose bottlenecks.',
    category: 'System Administration',
    duration: '20 min',
    difficulty: 'Advanced',
    roles: ['super_admin'],
    steps: [
      {
        title: 'Resource Limits',
        content:
          'Each service has memory and CPU limits defined in docker-compose.yml. Development defaults are conservative (256-512 MB RAM, 0.5 CPU cores per service). For production, adjust based on observed usage. Monitor with: docker stats --no-stream.',
      },
      {
        title: 'Worker Configuration',
        content:
          'All API services run with --workers 1 in development to minimise memory use. For production, increase to 2-4 workers for services under heavy load (risk-service, monitoring-service, rag-pipeline-service). Each worker is an independent Python process, so memory use scales linearly.',
      },
      {
        title: 'Database Connection Pooling',
        content:
          'Each service creates an asyncpg connection pool with min_size=2, max_size=10. With 16 services × 10 connections = 160 potential connections. PostgreSQL defaults to max_connections=100, so set max_connections=200 in postgresql.conf for production.',
      },
      {
        title: 'Diagnosing Slow Queries',
        content:
          'Enable pg_stat_statements: CREATE EXTENSION IF NOT EXISTS pg_stat_statements; Then query: SELECT query, mean_exec_time, calls FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 20; Add indexes for slow queries that appear frequently.',
      },
    ],
    tags: ['performance', 'docker', 'workers', 'database', 'tuning'],
  },
  {
    id: 'api-integrations',
    title: 'API & Integration Configuration',
    description:
      'Configure external API keys, set up webhooks, and manage the integration service.',
    category: 'System Administration',
    duration: '25 min',
    difficulty: 'Advanced',
    roles: ['super_admin'],
    steps: [
      {
        title: 'Anthropic API Key',
        content:
          'The AI Agent and RAG pipeline require an Anthropic API key. Set ANTHROPIC_API_KEY in .env. The rag-pipeline-service uses this to call claude-sonnet-4-6 for narrative generation. Without this key, the AI features degrade gracefully — they return a fallback message instead of an error.',
      },
      {
        title: 'Integration Connectors',
        content:
          'Configure connectors in Enterprise Integrations (5180) → Connectors. Each connector stores credentials in the integrations table (encrypted at rest). Supported connectors: Jira, Slack, GitHub, AWS CloudTrail, Azure Monitor, Okta, PagerDuty.',
      },
      {
        title: 'Webhook Configuration',
        content:
          'Aegis can send webhook events to external systems. Configure webhook endpoints in Integrations → Webhooks → New Webhook. Choose the events to subscribe to (risk.created, finding.critical, audit.closed, etc.). Events are sent as JSON POST requests with HMAC signatures.',
      },
      {
        title: 'Service Health Endpoints',
        content:
          'Every API service exposes a /health endpoint (e.g., http://localhost:3021/health). Use these for load balancer health checks in production. The endpoint returns {"status": "ok", "db": "connected"} when healthy.',
      },
    ],
    tags: ['api', 'integrations', 'webhooks', 'anthropic', 'connectors'],
  },
];
