AEGIS_TOOLS = [
    {
        "name": "get_compliance_scores",
        "description": "Get compliance scores for all active frameworks for the current tenant. Returns scores, status (compliant/at_risk/non_compliant), and framework details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "framework_slugs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of specific framework slugs to filter. Leave empty for all."
                }
            },
            "required": []
        }
    },
    {
        "name": "get_compliance_gaps",
        "description": "Get gap analysis for a specific compliance framework. Shows failing and not-started controls.",
        "input_schema": {
            "type": "object",
            "properties": {
                "framework_slug": {"type": "string", "description": "The framework slug (e.g. 'soc2-type2', 'iso27001-2022')"},
                "severity": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"], "description": "Filter by severity"}
            },
            "required": ["framework_slug"]
        }
    },
    {
        "name": "get_vendor_risk_summary",
        "description": "Get vendor risk portfolio summary including critical/high risk vendors and monitoring alerts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "risk_tier": {"type": "string", "enum": ["critical", "high", "medium", "low"], "description": "Filter by risk tier"}
            },
            "required": []
        }
    },
    {
        "name": "get_monitoring_findings",
        "description": "Get continuous monitoring findings. Can filter by category (payroll, ap, card, sod, cloud) and severity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                "category": {"type": "string", "enum": ["payroll", "ap", "card", "sod", "cloud"]},
                "limit": {"type": "integer", "default": 20}
            },
            "required": []
        }
    },
    {
        "name": "get_training_compliance",
        "description": "Get employee training compliance status. Returns overall rate, overdue assignments, and completion statistics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "department": {"type": "string", "description": "Filter by department name"}
            },
            "required": []
        }
    },
    {
        "name": "get_policy_compliance",
        "description": "Get policy acknowledgment compliance rate. Shows which policies have the lowest acknowledgment rates.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_open_pbc_requests",
        "description": "Get open and overdue PBC (Prepared by Client) requests across all engagements.",
        "input_schema": {
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string", "description": "Filter by specific engagement ID"}
            },
            "required": []
        }
    },
    {
        "name": "get_audit_issues",
        "description": "Get open audit issues. Can filter by severity and status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "informational"]},
                "status": {"type": "string"},
                "engagement_id": {"type": "string"}
            },
            "required": []
        }
    },
    {
        "name": "get_sod_violations",
        "description": "Get Segregation of Duties violations detected by continuous monitoring.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20}
            },
            "required": []
        }
    },
    {
        "name": "get_background_check_status",
        "description": "Get background check compliance status including expired and expiring checks.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "search_knowledge_base",
        "description": "Search the tenant's RAG knowledge base for relevant policies, procedures, and controls. Use this to answer questions about specific policies or controls.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "top_k": {"type": "integer", "default": 5, "description": "Number of results to return"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_integration_status",
        "description": "Get status of data integrations including last sync times and error counts.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "generate_compliance_report",
        "description": "Generate a detailed compliance report for a specific framework or overall posture.",
        "input_schema": {
            "type": "object",
            "properties": {
                "report_type": {"type": "string", "enum": ["compliance_summary", "gap_analysis", "vendor_risk", "monitoring_findings", "training_status", "audit_readiness"]},
                "framework_slug": {"type": "string", "description": "For framework-specific reports"}
            },
            "required": ["report_type"]
        }
    },
    {
        "name": "get_org_compliance_score",
        "description": "Get the overall people compliance score including policy, training, and background check metrics.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_cloud_config_issues",
        "description": "Get cloud configuration security issues from continuous monitoring (public S3 buckets, open security groups, MFA disabled).",
        "input_schema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "enum": ["aws", "gcp", "azure"]},
                "risk_level": {"type": "string", "enum": ["critical", "high", "medium", "low"]}
            },
            "required": []
        }
    }
]
