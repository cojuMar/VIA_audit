export interface Module {
  id: string;
  name: string;
  tagline: string;
  description: string;
  port: number;
  color: string;          // Tailwind color name (for dynamic classes below)
  iconBg: string;         // bg class
  iconColor: string;      // text class
  borderHover: string;    // hover border class
  pill: string;           // pill variant class
  category: 'core' | 'operations' | 'reporting' | 'field';
  workflow?: string;      // short workflow hint
}

export const MODULES: Module[] = [
  {
    id: 'framework',
    name: 'Compliance Frameworks',
    tagline: 'Standards & Controls Library',
    description:
      'Map your controls to NIST, ISO 27001, SOC 2, PCI-DSS, and custom frameworks. Track evidence and maintain a living compliance posture.',
    port: 5174,
    color: 'indigo',
    iconBg: 'bg-indigo-600',
    iconColor: 'text-indigo-300',
    borderHover: 'group-hover:border-indigo-500/60',
    pill: 'pill-indigo',
    category: 'core',
    workflow: 'Start here — define your control universe',
  },
  {
    id: 'tprm',
    name: 'Vendor / TPRM',
    tagline: 'Third-Party Risk Management',
    description:
      'Onboard vendors, send security questionnaires, score inherent and residual risk, and track remediation commitments.',
    port: 5175,
    color: 'violet',
    iconBg: 'bg-violet-600',
    iconColor: 'text-violet-300',
    borderHover: 'group-hover:border-violet-500/60',
    pill: 'pill-violet',
    category: 'core',
    workflow: 'Run vendor assessments alongside risk register',
  },
  {
    id: 'trust-portal',
    name: 'Client Trust Portal',
    tagline: 'Customer-Facing Transparency',
    description:
      'Publish security documentation and certifications to clients. Embedded chatbot answers compliance questions automatically.',
    port: 5176,
    color: 'cyan',
    iconBg: 'bg-cyan-600',
    iconColor: 'text-cyan-300',
    borderHover: 'group-hover:border-cyan-500/60',
    pill: 'pill-cyan',
    category: 'reporting',
    workflow: 'Share audit results with external stakeholders',
  },
  {
    id: 'monitoring',
    name: 'Continuous Monitoring',
    tagline: 'Real-Time Control Testing',
    description:
      'Automate evidence collection, schedule recurring tests, and surface findings before auditors do. Connects to AWS, Azure, GCP, and SaaS tools.',
    port: 5177,
    color: 'emerald',
    iconBg: 'bg-emerald-600',
    iconColor: 'text-emerald-300',
    borderHover: 'group-hover:border-emerald-500/60',
    pill: 'pill-green',
    category: 'operations',
    workflow: 'Feed findings into risk register automatically',
  },
  {
    id: 'people',
    name: 'People & Policy',
    tagline: 'HR Risk & Policy Management',
    description:
      'Track employee security training completion, manage policy acknowledgements, and monitor separation-of-duties conflicts.',
    port: 5178,
    color: 'teal',
    iconBg: 'bg-teal-600',
    iconColor: 'text-teal-300',
    borderHover: 'group-hover:border-teal-500/60',
    pill: 'pill-teal',
    category: 'core',
    workflow: 'Satisfy HR-related compliance requirements',
  },
  {
    id: 'pbc',
    name: 'PBC / Workpapers',
    tagline: 'Audit Evidence & Workpapers',
    description:
      'Issue PBC request lists to clients, track document uploads, review workpapers, and package final evidence for auditors.',
    port: 5179,
    color: 'blue',
    iconBg: 'bg-blue-600',
    iconColor: 'text-blue-300',
    borderHover: 'group-hover:border-blue-500/60',
    pill: 'pill-blue',
    category: 'operations',
    workflow: 'Collect evidence from clients during fieldwork',
  },
  {
    id: 'integration',
    name: 'Enterprise Integrations',
    tagline: 'Connect Everything',
    description:
      'Configure webhooks, Jira sync, Slack notifications, and REST connectors. Bi-directional sync keeps your ticketing and GRC in lockstep.',
    port: 5180,
    color: 'amber',
    iconBg: 'bg-amber-600',
    iconColor: 'text-amber-300',
    borderHover: 'group-hover:border-amber-500/60',
    pill: 'pill-amber',
    category: 'core',
    workflow: 'Wire up Jira/Slack before starting fieldwork',
  },
  {
    id: 'ai-agent',
    name: 'AI Agent Platform',
    tagline: 'Autonomous Audit Intelligence',
    description:
      'Conversational AI that drafts narratives, suggests controls, generates risk commentary, and answers policy questions from your document corpus.',
    port: 5181,
    color: 'rose',
    iconBg: 'bg-rose-600',
    iconColor: 'text-rose-300',
    borderHover: 'group-hover:border-rose-500/60',
    pill: 'pill-rose',
    category: 'operations',
    workflow: 'Use for narrative generation and Q&A during audits',
  },
  {
    id: 'risk',
    name: 'Risk Management',
    tagline: 'Enterprise Risk Register',
    description:
      'Maintain a living risk register with heat maps, treatment tracking, key risk indicators, and appetite statements aligned to business objectives.',
    port: 5182,
    color: 'orange',
    iconBg: 'bg-orange-600',
    iconColor: 'text-orange-300',
    borderHover: 'group-hover:border-orange-500/60',
    pill: 'pill-amber',
    category: 'core',
    workflow: 'Central risk register links to all other modules',
  },
  {
    id: 'audit-planning',
    name: 'Audit Planning',
    tagline: 'Audit Universe & Scheduling',
    description:
      'Build and prioritize your audit universe, schedule engagements, assign teams, and track fieldwork progress through completion.',
    port: 5183,
    color: 'sky',
    iconBg: 'bg-sky-600',
    iconColor: 'text-sky-300',
    borderHover: 'group-hover:border-sky-500/60',
    pill: 'pill-blue',
    category: 'operations',
    workflow: 'Plan audits against the risk register universe',
  },
  {
    id: 'esg',
    name: 'ESG & Board Management',
    tagline: 'Sustainability & Governance',
    description:
      'Track ESG metrics, generate board-ready reports, manage committee workflows, and align disclosures to GRI, SASB, and TCFD frameworks.',
    port: 5184,
    color: 'lime',
    iconBg: 'bg-lime-600',
    iconColor: 'text-lime-300',
    borderHover: 'group-hover:border-lime-500/60',
    pill: 'pill-green',
    category: 'reporting',
    workflow: 'Board-level reporting from risk and compliance data',
  },
  {
    id: 'mobile',
    name: 'Mobile Field Auditing',
    tagline: 'Offline-First Fieldwork',
    description:
      'Conduct walkthroughs, capture photos, fill checklists, and sync findings — all from a mobile browser with full offline support.',
    port: 5185,
    color: 'pink',
    iconBg: 'bg-pink-600',
    iconColor: 'text-pink-300',
    borderHover: 'group-hover:border-pink-500/60',
    pill: 'pill-rose',
    category: 'field',
    workflow: 'Use during on-site inspections and walkthroughs',
  },
];

export const WORKFLOW_STEPS = [
  { label: 'Define Controls', module: 'framework', desc: 'Map frameworks & controls' },
  { label: 'Assess Risk', module: 'risk', desc: 'Build risk register & appetite' },
  { label: 'Monitor', module: 'monitoring', desc: 'Automate evidence collection' },
  { label: 'Plan Audits', module: 'audit-planning', desc: 'Schedule engagements' },
  { label: 'Field Work', module: 'mobile', desc: 'On-site testing & PBC' },
  { label: 'Report', module: 'esg', desc: 'Board & trust portal' },
];
