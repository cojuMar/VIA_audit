import json
import logging
from uuid import uuid4

import asyncpg
import httpx

from .config import Settings
from .db import tenant_conn
from .models import DeflectionRequest

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a security compliance analyst. Answer vendor security questions accurately "
    "and professionally using only the provided evidence. Be concise. "
    "If evidence is insufficient, state that clearly."
)


class QuestionnaireDeflector:
    def __init__(self, settings: Settings) -> None:
        self._rag_url = settings.rag_pipeline_url
        self._http = httpx.AsyncClient(timeout=30.0)

        self._claude = None
        if settings.anthropic_api_key:
            try:
                import anthropic
                self._claude = anthropic.AsyncAnthropic(
                    api_key=settings.anthropic_api_key
                )
            except Exception as exc:
                logger.warning("Anthropic client init failed: %s", exc)

    async def deflect(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        request: DeflectionRequest,
    ) -> dict:
        """Process a vendor questionnaire and return AI-generated answers."""
        record_id = str(uuid4())

        # 1. INSERT pending record
        async with tenant_conn(pool, tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO portal_questionnaire_deflections (
                    id, tenant_id, requester_name, requester_email,
                    requester_company, questionnaire_type, questions,
                    status, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', NOW())
                """,
                record_id,
                tenant_id,
                request.requester_name,
                request.requester_email,
                request.requester_company,
                request.questionnaire_type,
                json.dumps(request.questions),
            )

        # 2. For each question, fetch RAG evidence
        deflection_mappings: list[dict] = []
        for question in request.questions:
            rag_evidence = await self._fetch_rag_evidence(tenant_id, question)
            ai_response = await self._generate_answer(question, rag_evidence)
            deflection_mappings.append(
                {
                    "question": question,
                    "rag_evidence": rag_evidence,
                    "ai_response": ai_response,
                }
            )

        # 3. Determine which model was used
        ai_model_used = "claude-haiku-4-5" if self._claude else "rag-only"

        # 4. UPDATE record to completed
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                UPDATE portal_questionnaire_deflections
                SET status              = 'completed',
                    deflection_mappings = $1,
                    ai_model_used       = $2,
                    completed_at        = NOW()
                WHERE id = $3
                RETURNING *
                """,
                json.dumps(deflection_mappings),
                ai_model_used,
                record_id,
            )

        result = dict(row)
        result["deflection_mappings"] = deflection_mappings
        return result

    async def get_deflection(
        self, pool: asyncpg.Pool, tenant_id: str, deflection_id: str
    ) -> dict | None:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM portal_questionnaire_deflections
                WHERE id = $1 AND tenant_id = $2
                """,
                deflection_id,
                tenant_id,
            )
        if row is None:
            return None
        record = dict(row)
        # Parse stored JSON if it came back as a string
        if isinstance(record.get("deflection_mappings"), str):
            try:
                record["deflection_mappings"] = json.loads(record["deflection_mappings"])
            except Exception:
                pass
        return record

    async def list_deflections(
        self, pool: asyncpg.Pool, tenant_id: str, limit: int = 50
    ) -> list[dict]:
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT id, requester_name, requester_email, requester_company,
                       questionnaire_type, status, ai_model_used,
                       created_at, completed_at
                FROM portal_questionnaire_deflections
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                tenant_id,
                limit,
            )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _fetch_rag_evidence(self, tenant_id: str, query: str) -> list[dict]:
        """Call rag-pipeline-service; return empty list on failure."""
        try:
            resp = await self._http.post(
                f"{self._rag_url}/narratives/search",
                json={"query": query, "tenant_id": tenant_id, "top_k": 3},
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else data.get("results", [])
        except Exception as exc:
            logger.warning("RAG pipeline unavailable for question '%s': %s", query[:60], exc)
            return []

    async def _generate_answer(
        self, question: str, rag_evidence: list[dict]
    ) -> str:
        """Use Claude to draft an answer, falling back to a placeholder."""
        if not self._claude:
            if rag_evidence:
                return "\n".join(
                    e.get("content", e.get("text", "")) for e in rag_evidence[:2]
                ) or "No evidence available."
            return "No evidence available at this time."

        evidence_block = "\n\n".join(
            f"[Evidence {i+1}]\n{e.get('content', e.get('text', ''))}"
            for i, e in enumerate(rag_evidence)
        ) or "No evidence available."

        user_message = (
            f"Question: {question}\n\n"
            f"Evidence:\n{evidence_block}\n\n"
            "Please provide a concise, professional answer."
        )

        try:
            response = await self._claude.messages.create(
                model="claude-haiku-4-5",
                max_tokens=512,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text
        except Exception as exc:
            logger.error("Claude API error: %s", exc)
            return "Unable to generate answer — please review manually."
