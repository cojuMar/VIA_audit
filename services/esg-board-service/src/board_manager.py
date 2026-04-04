from __future__ import annotations

import uuid
from datetime import datetime, timezone

import asyncpg

from .db import tenant_conn
from .models import AgendaItemCreate, CommitteeCreate, MeetingCreate


class BoardManager:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------
    # Committees
    # ------------------------------------------------------------------

    async def create_committee(
        self, tenant_id: str, data: CommitteeCreate
    ) -> dict:
        committee_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO board_committees (
                    id, tenant_id, name, committee_type, charter,
                    members, chair, quorum_requirement, meeting_frequency,
                    is_active, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, TRUE, $10, $10
                )
                RETURNING *
                """,
                committee_id,
                tenant_id,
                data.name,
                data.committee_type,
                data.charter,
                data.members,
                data.chair,
                data.quorum_requirement,
                data.meeting_frequency,
                now,
            )
        return dict(row)

    async def update_committee(
        self, tenant_id: str, committee_id: str, updates: dict
    ) -> dict:
        allowed = {
            "name", "committee_type", "charter", "members", "chair",
            "quorum_requirement", "meeting_frequency", "is_active",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            raise ValueError("No valid fields to update")

        set_clauses = [
            f"{k} = ${i + 1}" for i, k in enumerate(filtered)
        ]
        set_clauses.append(f"updated_at = ${len(filtered) + 1}")
        values = list(filtered.values()) + [datetime.now(timezone.utc)]

        query = (
            f"UPDATE board_committees SET {', '.join(set_clauses)} "
            f"WHERE id = ${len(values) + 1} AND tenant_id = ${len(values) + 2} "
            f"RETURNING *"
        )
        values += [committee_id, tenant_id]

        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(query, *values)
        if row is None:
            raise ValueError(f"Committee {committee_id} not found")
        return dict(row)

    async def list_committees(
        self, tenant_id: str, active_only: bool = True
    ) -> list[dict]:
        where = "WHERE c.is_active = TRUE" if active_only else ""
        query = f"""
            SELECT
                c.*,
                COUNT(m.id) AS meeting_count
            FROM board_committees c
            LEFT JOIN board_meetings m ON m.committee_id = c.id
            {where}
            GROUP BY c.id
            ORDER BY c.name
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(query)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Meetings
    # ------------------------------------------------------------------

    async def create_meeting(
        self, tenant_id: str, data: MeetingCreate
    ) -> dict:
        meeting_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        scheduled_dt = datetime.fromisoformat(data.scheduled_date)

        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO board_meetings (
                    id, tenant_id, committee_id, title, meeting_type,
                    scheduled_date, location, virtual_link, attendees,
                    status, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, 'scheduled', $10, $10
                )
                RETURNING *
                """,
                meeting_id,
                tenant_id,
                data.committee_id,
                data.title,
                data.meeting_type,
                scheduled_dt,
                data.location,
                data.virtual_link,
                data.attendees,
                now,
            )
        return dict(row)

    async def update_meeting(
        self, tenant_id: str, meeting_id: str, updates: dict
    ) -> dict:
        allowed = {
            "title", "meeting_type", "scheduled_date", "location",
            "virtual_link", "attendees", "status", "committee_id",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            raise ValueError("No valid fields to update")

        # Convert scheduled_date string to datetime if present
        if "scheduled_date" in filtered and isinstance(
            filtered["scheduled_date"], str
        ):
            filtered["scheduled_date"] = datetime.fromisoformat(
                filtered["scheduled_date"]
            )

        set_clauses = [
            f"{k} = ${i + 1}" for i, k in enumerate(filtered)
        ]
        set_clauses.append(f"updated_at = ${len(filtered) + 1}")
        values = list(filtered.values()) + [datetime.now(timezone.utc)]

        query = (
            f"UPDATE board_meetings SET {', '.join(set_clauses)} "
            f"WHERE id = ${len(values) + 1} AND tenant_id = ${len(values) + 2} "
            f"RETURNING *"
        )
        values += [meeting_id, tenant_id]

        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(query, *values)
        if row is None:
            raise ValueError(f"Meeting {meeting_id} not found")
        return dict(row)

    async def get_meeting(self, tenant_id: str, meeting_id: str) -> dict:
        async with tenant_conn(self.pool, tenant_id) as conn:
            meeting_row = await conn.fetchrow(
                """
                SELECT
                    m.*,
                    c.name AS committee_name
                FROM board_meetings m
                LEFT JOIN board_committees c ON c.id = m.committee_id
                WHERE m.id = $1
                """,
                meeting_id,
            )
            if meeting_row is None:
                raise ValueError(f"Meeting {meeting_id} not found")

            agenda_rows = await conn.fetch(
                """
                SELECT *
                FROM board_agenda_items
                WHERE meeting_id = $1
                ORDER BY sequence_number
                """,
                meeting_id,
            )

        result = dict(meeting_row)
        result["agenda_items"] = [dict(r) for r in agenda_rows]
        return result

    async def list_meetings(
        self,
        tenant_id: str,
        status: str | None = None,
        committee_id: str | None = None,
        upcoming_only: bool = False,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list = []
        idx = 1

        if status:
            conditions.append(f"m.status = ${idx}")
            params.append(status)
            idx += 1
        if committee_id:
            conditions.append(f"m.committee_id = ${idx}")
            params.append(committee_id)
            idx += 1
        if upcoming_only:
            conditions.append(f"m.scheduled_date >= NOW()")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"""
            SELECT
                m.*,
                c.name AS committee_name,
                COUNT(ai.id) AS agenda_item_count
            FROM board_meetings m
            LEFT JOIN board_committees c ON c.id = m.committee_id
            LEFT JOIN board_agenda_items ai ON ai.meeting_id = m.id
            {where}
            GROUP BY m.id, c.name
            ORDER BY m.scheduled_date DESC
        """
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Agenda items
    # ------------------------------------------------------------------

    async def add_agenda_item(
        self, tenant_id: str, data: AgendaItemCreate
    ) -> dict:
        item_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO board_agenda_items (
                    id, tenant_id, meeting_id, sequence_number, title,
                    item_type, description, presenter, duration_minutes,
                    created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10
                )
                RETURNING *
                """,
                item_id,
                tenant_id,
                data.meeting_id,
                data.sequence_number,
                data.title,
                data.item_type,
                data.description,
                data.presenter,
                data.duration_minutes,
                now,
            )
        return dict(row)

    async def update_agenda_item(
        self, tenant_id: str, item_id: str, updates: dict
    ) -> dict:
        allowed = {
            "sequence_number", "title", "item_type", "description",
            "presenter", "duration_minutes",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            raise ValueError("No valid fields to update")

        set_clauses = [
            f"{k} = ${i + 1}" for i, k in enumerate(filtered)
        ]
        set_clauses.append(f"updated_at = ${len(filtered) + 1}")
        values = list(filtered.values()) + [datetime.now(timezone.utc)]

        query = (
            f"UPDATE board_agenda_items SET {', '.join(set_clauses)} "
            f"WHERE id = ${len(values) + 1} AND tenant_id = ${len(values) + 2} "
            f"RETURNING *"
        )
        values += [item_id, tenant_id]

        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(query, *values)
        if row is None:
            raise ValueError(f"Agenda item {item_id} not found")
        return dict(row)

    # ------------------------------------------------------------------
    # Meeting completion & minutes
    # ------------------------------------------------------------------

    async def complete_meeting(
        self,
        tenant_id: str,
        meeting_id: str,
        minutes_text: str,
        attendees: list[str],
        quorum_met: bool,
    ) -> dict:
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                UPDATE board_meetings
                SET
                    status        = 'completed',
                    actual_date   = NOW(),
                    minutes_text  = $1,
                    attendees     = $2,
                    quorum_met    = $3,
                    updated_at    = NOW()
                WHERE id = $4 AND tenant_id = $5
                RETURNING *
                """,
                minutes_text,
                attendees,
                quorum_met,
                meeting_id,
                tenant_id,
            )
        if row is None:
            raise ValueError(f"Meeting {meeting_id} not found")
        return dict(row)

    async def approve_minutes(
        self, tenant_id: str, meeting_id: str
    ) -> dict:
        async with tenant_conn(self.pool, tenant_id) as conn:
            row = await conn.fetchrow(
                """
                UPDATE board_meetings
                SET
                    minutes_approved    = TRUE,
                    minutes_approved_at = NOW(),
                    updated_at          = NOW()
                WHERE id = $1 AND tenant_id = $2
                RETURNING *
                """,
                meeting_id,
                tenant_id,
            )
        if row is None:
            raise ValueError(f"Meeting {meeting_id} not found")
        return dict(row)

    # ------------------------------------------------------------------
    # Calendar
    # ------------------------------------------------------------------

    async def get_board_calendar(self, tenant_id: str, year: int) -> dict:
        async with tenant_conn(self.pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT
                    m.*,
                    c.name AS committee_name,
                    EXTRACT(QUARTER FROM m.scheduled_date)::int AS quarter
                FROM board_meetings m
                LEFT JOIN board_committees c ON c.id = m.committee_id
                WHERE EXTRACT(YEAR FROM m.scheduled_date) = $1
                ORDER BY m.scheduled_date
                """,
                year,
            )

        calendar: dict = {"Q1": [], "Q2": [], "Q3": [], "Q4": [], "total": 0}
        for r in rows:
            rd = dict(r)
            q = f"Q{rd.pop('quarter', 1)}"
            calendar[q].append(rd)
            calendar["total"] += 1

        return calendar
