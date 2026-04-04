import json
import time
from uuid import UUID

import anthropic

from .config import Settings
from .db import tenant_conn
from .models import ChatRequest, ChatResponse, ReportRequest
from .tool_definitions import AEGIS_TOOLS
from .tool_executor import ToolExecutor


class AgentEngine:
    def __init__(self, settings: Settings, tool_executor: ToolExecutor):
        self.settings = settings
        self.tool_executor = tool_executor
        if settings.anthropic_api_key:
            self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        else:
            self.client = None

    async def chat(self, pool, tenant_id: str, request: ChatRequest) -> ChatResponse:
        """
        Main chat method implementing the agentic loop:

        1. Load or create conversation
        2. Load conversation history (last 20 messages)
        3. Build message list for Claude
        4. Call Claude with tools enabled (claude-opus-4-5)
        5. Process tool calls in a loop until no more tool_use blocks
        6. Save all messages as immutable records
        7. Update conversation stats
        8. Return final response
        """
        start_time = time.time()

        # Step 1: Load or create conversation
        async with tenant_conn(pool, tenant_id) as conn:
            if request.conversation_id:
                conv = await conn.fetchrow(
                    "SELECT * FROM agent_conversations WHERE id=$1 AND tenant_id=$2 AND status='active'",
                    UUID(request.conversation_id), UUID(tenant_id)
                )
                if not conv:
                    raise ValueError("Conversation not found")
                conv_id = str(conv["id"])
            else:
                conv_id = str(await conn.fetchval(
                    "INSERT INTO agent_conversations (tenant_id, user_identifier) VALUES ($1, $2) RETURNING id",
                    UUID(tenant_id), request.user_identifier
                ))

        # Step 2: Load history
        history = await self._load_history(pool, tenant_id, conv_id)

        # Step 3: Build messages
        messages = history + [{"role": "user", "content": request.message}]

        # Step 4-5: Agentic loop
        tool_calls_made = []
        total_input = 0
        total_output = 0
        final_content = ""
        user_msg_id = None

        if not self.client:
            # Fallback when no API key
            final_content = self._fallback_response(request.message)
        else:
            # Save user message (immutable)
            async with tenant_conn(pool, tenant_id) as conn:
                user_msg_id = str(await conn.fetchval(
                    "INSERT INTO agent_messages (tenant_id, conversation_id, role, content) VALUES ($1, $2, $3, $4) RETURNING id",
                    UUID(tenant_id), UUID(conv_id), "user", request.message
                ))

            # Agentic loop
            loop_messages = messages.copy()
            max_iterations = 10  # prevent infinite loops

            for _ in range(max_iterations):
                response = await self.client.messages.create(
                    model=self.settings.agent_model,
                    max_tokens=4096,
                    system=self._get_system_prompt(tenant_id),
                    messages=loop_messages,
                    tools=AEGIS_TOOLS,
                )

                total_input += response.usage.input_tokens
                total_output += response.usage.output_tokens

                # Check for tool use
                tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
                text_blocks = [b for b in response.content if b.type == "text"]

                if not tool_use_blocks:
                    # No more tools — we have the final response
                    final_content = text_blocks[0].text if text_blocks else ""
                    break

                # Execute all tool calls
                tool_results = []
                for tool_block in tool_use_blocks:
                    tool_calls_made.append(tool_block.name)
                    exec_start = time.time()
                    result = await self.tool_executor.execute(tool_block.name, tool_block.input, tenant_id)
                    exec_ms = int((time.time() - exec_start) * 1000)

                    # Save tool call (immutable)
                    async with tenant_conn(pool, tenant_id) as conn:
                        await conn.execute(
                            """INSERT INTO agent_tool_calls
                               (tenant_id, message_id, conversation_id, tool_name, tool_input, tool_output, execution_time_ms, success)
                               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                            UUID(tenant_id),
                            UUID(user_msg_id) if user_msg_id else None,
                            UUID(conv_id),
                            tool_block.name,
                            json.dumps(tool_block.input),
                            json.dumps(result),
                            exec_ms,
                            "error" not in result,
                        )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": json.dumps(result),
                    })

                # Add assistant response + tool results to loop messages
                loop_messages.append({"role": "assistant", "content": response.content})
                loop_messages.append({"role": "user", "content": tool_results})

        latency_ms = int((time.time() - start_time) * 1000)

        # Save assistant message (immutable)
        async with tenant_conn(pool, tenant_id) as conn:
            asst_msg_id = str(await conn.fetchval(
                """INSERT INTO agent_messages
                   (tenant_id, conversation_id, role, content, tool_calls, input_tokens, output_tokens, model_used, latency_ms)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id""",
                UUID(tenant_id), UUID(conv_id), "assistant", final_content,
                json.dumps(tool_calls_made), total_input, total_output,
                self.settings.agent_model, latency_ms,
            ))

            # Update conversation stats
            await conn.execute(
                """UPDATE agent_conversations
                   SET message_count = message_count + 2,
                       total_input_tokens = total_input_tokens + $1,
                       total_output_tokens = total_output_tokens + $2,
                       updated_at = NOW()
                   WHERE id = $3""",
                total_input, total_output, UUID(conv_id),
            )

        return ChatResponse(
            conversation_id=conv_id,
            message_id=asst_msg_id,
            content=final_content,
            tool_calls_made=list(set(tool_calls_made)),
            input_tokens=total_input,
            output_tokens=total_output,
            latency_ms=latency_ms,
        )

    def _get_system_prompt(self, tenant_id: str) -> str:
        return f"""You are Aegis AI, an intelligent compliance and audit assistant for an enterprise GRC platform.
You have access to real-time data from the Aegis platform through specialized tools.

Your capabilities:
- Query compliance scores and framework status
- Analyze gaps in compliance controls
- Review vendor risk portfolios
- Examine continuous monitoring findings (payroll anomalies, invoice duplicates, SoD violations, cloud misconfigs)
- Check training and policy compliance
- Review audit issues and PBC request status
- Search the knowledge base for policies and procedures
- Generate comprehensive compliance reports

Guidelines:
- Always use the available tools to fetch real data before answering questions about compliance status
- Be specific and cite exact numbers, percentages, and control IDs when available
- When findings are concerning, recommend concrete remediation actions
- Format responses clearly with headers, bullet points, and tables where helpful
- If a service is unavailable, acknowledge this and provide what information you can
- Never fabricate data — always use tool results
- Current tenant context: {tenant_id}"""

    def _fallback_response(self, message: str) -> str:
        return (
            f'I\'m Aegis AI, your compliance assistant. I\'m currently operating without an Anthropic API key '
            f'configured, so I cannot process your request: "{message[:100]}..."\n\n'
            f"To enable AI capabilities, please configure the ANTHROPIC_API_KEY environment variable.\n\n"
            f"In the meantime, you can access all compliance data directly through the platform's dashboards."
        )

    async def _load_history(self, pool, tenant_id: str, conv_id: str) -> list[dict]:
        """Load last 20 messages, format for Claude API."""
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """SELECT role, content FROM agent_messages
                   WHERE conversation_id = $1 AND tenant_id = $2
                   ORDER BY created_at DESC LIMIT 20""",
                UUID(conv_id), UUID(tenant_id),
            )
        # Reverse to chronological order
        return [
            {
                "role": r["role"] if r["role"] != "tool_result" else "user",
                "content": r["content"],
            }
            for r in reversed(rows)
        ]

    async def generate_report(self, pool, tenant_id: str, request: ReportRequest) -> dict:
        """
        Generate a structured compliance report using Claude.

        1. Gather relevant data using tool_executor
        2. Use Claude to synthesize into a formatted report
        3. Save as immutable agent_reports record
        4. Return report dict
        """
        start_time = time.time()

        # Gather data based on report_type
        data = {}
        if request.report_type in ("compliance_summary", "gap_analysis", "audit_readiness"):
            data["compliance"] = await self.tool_executor.execute("get_compliance_scores", {}, tenant_id)
        if request.report_type in ("vendor_risk",):
            data["vendors"] = await self.tool_executor.execute("get_vendor_risk_summary", {}, tenant_id)
        if request.report_type in ("monitoring_findings",):
            data["findings"] = await self.tool_executor.execute("get_monitoring_findings", {"limit": 50}, tenant_id)
        if request.report_type in ("training_status",):
            data["training"] = await self.tool_executor.execute("get_training_compliance", {}, tenant_id)
        if request.report_type in ("audit_readiness", "compliance_summary"):
            data["people"] = await self.tool_executor.execute("get_org_compliance_score", {}, tenant_id)

        # Generate with Claude (or fallback)
        if self.client:
            prompt = (
                f"Generate a professional {request.report_type.replace('_', ' ').title()} report based on this data:\n\n"
                f"{json.dumps(data, indent=2, default=str)}\n\n"
                f"User request: {request.natural_language_request}\n\n"
                f"Format as a comprehensive markdown report with:\n"
                f"- Executive Summary\n"
                f"- Key Findings (with specific numbers)\n"
                f"- Risk Analysis\n"
                f"- Recommendations\n"
                f"- Next Steps\n\n"
                f"Be specific, professional, and actionable."
            )

            response = await self.client.messages.create(
                model=self.settings.agent_model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
        else:
            content = (
                f"# {request.title or request.report_type.replace('_', ' ').title()}\n\n"
                f"*Report generation requires Anthropic API key.*\n\n"
                f"Data collected:\n```json\n{json.dumps(data, indent=2, default=str)}\n```"
            )
            input_tokens = 0
            output_tokens = 0

        gen_ms = int((time.time() - start_time) * 1000)

        # Save report (immutable)
        async with tenant_conn(pool, tenant_id) as conn:
            report_id = str(await conn.fetchval(
                """INSERT INTO agent_reports
                   (tenant_id, conversation_id, report_type, title, content, model_used, generation_time_ms, metadata)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id""",
                UUID(tenant_id),
                UUID(request.conversation_id) if request.conversation_id else None,
                request.report_type,
                request.title or f"{request.report_type.replace('_', ' ').title()} Report",
                content,
                self.settings.agent_model,
                gen_ms,
                json.dumps({"input_tokens": input_tokens, "output_tokens": output_tokens}),
            ))

        return {
            "report_id": report_id,
            "title": request.title or f"{request.report_type.replace('_', ' ').title()} Report",
            "content": content,
            "generation_time_ms": gen_ms,
        }
