from __future__ import annotations

from uuid import UUID

from .db import tenant_conn


class ConversationManager:
    async def list(self, pool, tenant_id: str, status: str = "active") -> list[dict]:
        """List conversations for a tenant filtered by status."""
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """SELECT id, tenant_id, user_identifier, title, status,
                          message_count, total_input_tokens, total_output_tokens,
                          created_at, updated_at
                   FROM agent_conversations
                   WHERE tenant_id = $1 AND status = $2
                   ORDER BY updated_at DESC""",
                UUID(tenant_id), status,
            )
        return [dict(r) for r in rows]

    async def get(self, pool, tenant_id: str, conv_id: str) -> dict | None:
        """Get a single conversation with its message count."""
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """SELECT id, tenant_id, user_identifier, title, status,
                          message_count, total_input_tokens, total_output_tokens,
                          created_at, updated_at
                   FROM agent_conversations
                   WHERE id = $1 AND tenant_id = $2""",
                UUID(conv_id), UUID(tenant_id),
            )
        return dict(row) if row else None

    async def get_messages(self, pool, tenant_id: str, conv_id: str) -> list[dict]:
        """Get all messages for a conversation in chronological order."""
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """SELECT id, tenant_id, conversation_id, role, content,
                          tool_calls, input_tokens, output_tokens, model_used,
                          latency_ms, created_at
                   FROM agent_messages
                   WHERE conversation_id = $1 AND tenant_id = $2
                   ORDER BY created_at ASC""",
                UUID(conv_id), UUID(tenant_id),
            )
        return [dict(r) for r in rows]

    async def archive(self, pool, tenant_id: str, conv_id: str) -> dict:
        """Archive a conversation (set status to 'archived')."""
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """UPDATE agent_conversations
                   SET status = 'archived', updated_at = NOW()
                   WHERE id = $1 AND tenant_id = $2
                   RETURNING id, status, updated_at""",
                UUID(conv_id), UUID(tenant_id),
            )
        if not row:
            raise ValueError("Conversation not found")
        return dict(row)

    async def update_title(self, pool, tenant_id: str, conv_id: str, title: str) -> dict:
        """Update the display title of a conversation."""
        async with tenant_conn(pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """UPDATE agent_conversations
                   SET title = $1, updated_at = NOW()
                   WHERE id = $2 AND tenant_id = $3
                   RETURNING id, title, updated_at""",
                title, UUID(conv_id), UUID(tenant_id),
            )
        if not row:
            raise ValueError("Conversation not found")
        return dict(row)

    async def get_stats(self, pool, tenant_id: str) -> dict:
        """
        Return usage statistics for the tenant:
        - total_conversations
        - total_messages
        - total_tool_calls
        - avg_tools_per_message
        - most_used_tools (list of {tool_name, count})
        - feedback_avg_rating
        """
        async with tenant_conn(pool, tenant_id) as conn:
            conv_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total_conversations FROM agent_conversations WHERE tenant_id = $1",
                UUID(tenant_id),
            )
            msg_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total_messages FROM agent_messages WHERE tenant_id = $1",
                UUID(tenant_id),
            )
            tool_row = await conn.fetchrow(
                "SELECT COUNT(*) AS total_tool_calls FROM agent_tool_calls WHERE tenant_id = $1",
                UUID(tenant_id),
            )
            # Average tool calls per assistant message
            avg_row = await conn.fetchrow(
                """SELECT AVG(jsonb_array_length(tool_calls::jsonb)) AS avg_tools
                   FROM agent_messages
                   WHERE tenant_id = $1 AND role = 'assistant'
                     AND tool_calls IS NOT NULL AND tool_calls != '[]'""",
                UUID(tenant_id),
            )
            # Most-used tools
            tool_rows = await conn.fetch(
                """SELECT tool_name, COUNT(*) AS cnt
                   FROM agent_tool_calls
                   WHERE tenant_id = $1
                   GROUP BY tool_name
                   ORDER BY cnt DESC
                   LIMIT 10""",
                UUID(tenant_id),
            )
            # Average feedback rating
            fb_row = await conn.fetchrow(
                "SELECT AVG(rating) AS avg_rating FROM agent_feedback WHERE tenant_id = $1",
                UUID(tenant_id),
            )

        total_tool_calls = tool_row["total_tool_calls"] if tool_row else 0
        total_messages = msg_row["total_messages"] if msg_row else 0
        avg_tools = float(avg_row["avg_tools"]) if avg_row and avg_row["avg_tools"] else 0.0
        avg_rating = float(fb_row["avg_rating"]) if fb_row and fb_row["avg_rating"] else None

        return {
            "total_conversations": conv_row["total_conversations"] if conv_row else 0,
            "total_messages": total_messages,
            "total_tool_calls": total_tool_calls,
            "avg_tools_per_message": round(avg_tools, 2),
            "most_used_tools": [{"tool_name": r["tool_name"], "count": r["cnt"]} for r in tool_rows],
            "feedback_avg_rating": round(avg_rating, 2) if avg_rating is not None else None,
        }
