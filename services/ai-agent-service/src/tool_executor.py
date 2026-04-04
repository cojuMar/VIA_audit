import httpx

from .config import Settings


class ToolExecutor:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient):
        self.settings = settings
        self.http = http_client

    async def execute(self, tool_name: str, tool_input: dict, tenant_id: str) -> dict:
        """Route tool calls to appropriate service endpoints."""
        headers = {"X-Tenant-ID": tenant_id}

        try:
            if tool_name == "get_compliance_scores":
                return await self._call(
                    f"{self.settings.framework_service_url}/scores/{tenant_id}",
                    headers=headers
                )

            elif tool_name == "get_compliance_gaps":
                slug = tool_input.get("framework_slug", "")
                params = {"severity": tool_input["severity"]} if tool_input.get("severity") else {}
                return await self._call(
                    f"{self.settings.framework_service_url}/gaps/{tenant_id}/{slug}",
                    params=params,
                    headers=headers
                )

            elif tool_name == "get_vendor_risk_summary":
                params = {}
                if tool_input.get("risk_tier"):
                    params["risk_tier"] = tool_input["risk_tier"]
                return await self._call(
                    f"{self.settings.tprm_service_url}/vendors/summary",
                    params=params,
                    headers=headers
                )

            elif tool_name == "get_monitoring_findings":
                params = {k: v for k, v in {
                    "severity": tool_input.get("severity"),
                    "finding_type": tool_input.get("category"),
                    "limit": tool_input.get("limit", 20),
                }.items() if v is not None}
                return await self._call(
                    f"{self.settings.monitoring_service_url}/findings",
                    params=params,
                    headers=headers
                )

            elif tool_name == "get_training_compliance":
                return await self._call(
                    f"{self.settings.people_service_url}/training/compliance-rate",
                    headers=headers
                )

            elif tool_name == "get_policy_compliance":
                return await self._call(
                    f"{self.settings.people_service_url}/policies/compliance-rate",
                    headers=headers
                )

            elif tool_name == "get_open_pbc_requests":
                params = {}
                if tool_input.get("engagement_id"):
                    params["engagement_id"] = tool_input["engagement_id"]
                return await self._call(
                    f"{self.settings.pbc_service_url}/pbc/overdue",
                    params=params,
                    headers=headers
                )

            elif tool_name == "get_audit_issues":
                params = {k: v for k, v in {
                    "severity": tool_input.get("severity"),
                    "status": tool_input.get("status"),
                    "engagement_id": tool_input.get("engagement_id"),
                }.items() if v is not None}
                return await self._call(
                    f"{self.settings.pbc_service_url}/issues",
                    params=params,
                    headers=headers
                )

            elif tool_name == "get_sod_violations":
                params = {"limit": tool_input.get("limit", 20)}
                return await self._call(
                    f"{self.settings.monitoring_service_url}/sod/violations",
                    params=params,
                    headers=headers
                )

            elif tool_name == "get_background_check_status":
                return await self._call(
                    f"{self.settings.people_service_url}/background-checks/summary",
                    headers=headers
                )

            elif tool_name == "search_knowledge_base":
                resp = await self.http.post(
                    f"{self.settings.rag_pipeline_url}/narratives/search",
                    json={
                        "query": tool_input["query"],
                        "tenant_id": tenant_id,
                        "top_k": tool_input.get("top_k", 5),
                    },
                    headers=headers,
                    timeout=10.0,
                )
                return resp.json() if resp.status_code == 200 else {"error": f"RAG search failed: {resp.status_code}"}

            elif tool_name == "get_integration_status":
                integration_url = self.settings.framework_service_url.replace(
                    "framework-service:3012", "integration-service:3019"
                )
                return await self._call(f"{integration_url}/dashboard", headers=headers)

            elif tool_name == "generate_compliance_report":
                # Signal to the agent engine to generate the report inline
                return {
                    "action": "generate_report",
                    "report_type": tool_input.get("report_type"),
                    "framework_slug": tool_input.get("framework_slug"),
                }

            elif tool_name == "get_org_compliance_score":
                return await self._call(
                    f"{self.settings.people_service_url}/compliance/summary",
                    headers=headers
                )

            elif tool_name == "get_cloud_config_issues":
                params = {k: v for k, v in {
                    "provider": tool_input.get("provider"),
                    "risk_level": tool_input.get("risk_level"),
                }.items() if v is not None}
                return await self._call(
                    f"{self.settings.monitoring_service_url}/cloud/snapshots",
                    params=params,
                    headers=headers
                )

            else:
                return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            return {"error": str(e), "tool": tool_name}

    async def _call(self, url: str, params: dict = None, headers: dict = None) -> dict:
        """Make GET request with graceful fallback."""
        try:
            resp = await self.http.get(url, params=params, headers=headers or {}, timeout=10.0)
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"Service returned {resp.status_code}", "url": url}
        except Exception as e:
            return {"error": str(e), "service_unavailable": True}
