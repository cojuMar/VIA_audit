import logging
import secrets
from uuid import uuid4

import asyncpg
import httpx

from .config import Settings
from .db import tenant_conn

logger = logging.getLogger(__name__)


class PortalChatbot:
    def __init__(self, settings: Settings) -> None:
        self._rag_url = settings.rag_pipeline_url
        self._http = httpx.AsyncClient(timeout=30.0)

    async def create_session(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        visitor_email: str | None,
        visitor_company: str | None,
    ) -> dict:
        """Create a new chatbot session and return it with a token."""
        session_id = str(uuid4())
        token = secrets.token_urlsafe(32)

        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO portal_chatbot_sessions (
                    id, tenant_id, visitor_email, visitor_company,
                    session_token, message_count, created_at, last_active_at
                ) VALUES ($1, $2, $3, $4, $5, 0, NOW(), NOW())
                RETURNING *
                """,
                session_id,
                tenant_id,
                visitor_email,
                visitor_company,
                token,
            )
        return dict(row)

    async def get_session(
        self, pool: asyncpg.Pool, tenant_id: str, session_token: str
    ) -> dict | None:
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM portal_chatbot_sessions
                WHERE tenant_id = $1 AND session_token = $2
                """,
                tenant_id,
                session_token,
            )
        return dict(row) if row else None

    async def send_message(
        self,
        pool: asyncpg.Pool,
        tenant_id: str,
        session_token: str,
        user_message: str,
        ip: str,
    ) -> dict:
        """Process a user message and return the assistant reply."""
        # 1. Verify session
        session = await self.get_session(pool, tenant_id, session_token)
        if session is None:
            raise ValueError("Invalid or expired session token")

        session_id = str(session["id"])

        # 2. INSERT user message (immutable)
        async with tenant_conn(pool, tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO portal_chatbot_messages (
                    id, session_id, tenant_id, role, content,
                    sources, ip_address, created_at
                ) VALUES ($1, $2, $3, 'user', $4, '[]', $5, NOW())
                """,
                str(uuid4()),
                session_id,
                tenant_id,
                user_message,
                ip,
            )

        # 3. Call RAG pipeline
        response_text, sources = await self._call_rag(tenant_id, user_message)

        # 4. INSERT assistant message (immutable)
        import json
        async with tenant_conn(pool, tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO portal_chatbot_messages (
                    id, session_id, tenant_id, role, content,
                    sources, ip_address, created_at
                ) VALUES ($1, $2, $3, 'assistant', $4, $5, $6, NOW())
                """,
                str(uuid4()),
                session_id,
                tenant_id,
                response_text,
                json.dumps(sources),
                ip,
            )

            # 5. UPDATE session metadata
            await conn.execute(
                """
                UPDATE portal_chatbot_sessions
                SET last_active_at = NOW(),
                    message_count  = message_count + 2
                WHERE id = $1
                """,
                session_id,
            )

            # 6. Log access event
            await conn.execute(
                """
                INSERT INTO trust_portal_access_logs (
                    id, tenant_id, event_type, visitor_email,
                    ip_address, user_agent, metadata, created_at
                ) VALUES ($1, $2, 'chatbot_message', $3, $4, 'chatbot', $5, NOW())
                """,
                str(uuid4()),
                tenant_id,
                session.get("visitor_email"),
                ip,
                json.dumps({"session_id": session_id, "message_preview": user_message[:100]}),
            )

        return {"role": "assistant", "content": response_text, "sources": sources}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _call_rag(
        self, tenant_id: str, query: str
    ) -> tuple[str, list[dict]]:
        """Call rag-pipeline /narratives/generate; graceful fallback."""
        try:
            resp = await self._http.post(
                f"{self._rag_url}/narratives/generate",
                json={"query": query, "tenant_id": tenant_id},
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("narrative") or data.get("response") or data.get("text", "")
            sources = data.get("sources") or data.get("evidence") or []
            return text, sources
        except Exception as exc:
            logger.warning("RAG pipeline unavailable for chatbot query: %s", exc)
            return (
                "I'm sorry, I'm having trouble retrieving information right now. "
                "Please try again shortly or contact us directly.",
                [],
            )
