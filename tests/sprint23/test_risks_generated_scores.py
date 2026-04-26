"""
risks.{inherent,residual,target}_score are GENERATED ALWAYS — INSERT must
omit them, and Postgres must auto-compute on INSERT and on UPDATE of the
underlying likelihood/impact columns.
"""
from __future__ import annotations

import uuid
import pytest


@pytest.mark.asyncio
async def test_all_three_scores_generated(admin_conn):
    rows = await admin_conn.fetch("""
        SELECT column_name, is_generated
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='risks'
          AND column_name IN ('inherent_score','residual_score','target_score')
    """)
    state = {r["column_name"]: r["is_generated"] for r in rows}
    assert state == {
        "inherent_score": "ALWAYS",
        "residual_score": "ALWAYS",
        "target_score":   "ALWAYS",
    }, f"score columns not GENERATED ALWAYS: {state}"


@pytest.mark.asyncio
async def test_insert_without_score_columns_succeeds(admin_conn, demo_tenant):
    """The Sprint 23 fix: INSERT into risks omits all _score columns."""
    risk_uuid = str(uuid.uuid4())
    cat_id = await admin_conn.fetchval(
        "SELECT id FROM risk_categories LIMIT 1"
    )
    assert cat_id, "test prereq: at least one risk_categories row"

    async with admin_conn.transaction():
        await admin_conn.execute(
            "SELECT set_config('app.tenant_id', $1, true)", demo_tenant
        )
        await admin_conn.execute(
            """
            INSERT INTO risks (
                id, tenant_id, risk_id, title, description,
                category_id, inherent_likelihood, inherent_impact,
                residual_likelihood, residual_impact,
                target_likelihood, target_impact,
                source, status
            ) VALUES (
                $1,$2,$3,$4,$5,
                $6,$7,$8,
                $9,$10,
                $11,$12,
                'manual','open'
            )
            """,
            risk_uuid, demo_tenant, f"PROBE-{risk_uuid[:6]}",
            "sprint23 probe", "test", cat_id,
            4, 5, 2, 3, 1, 2,
        )
        row = await admin_conn.fetchrow(
            """
            SELECT inherent_score, residual_score, target_score
            FROM risks WHERE id=$1
            """,
            risk_uuid,
        )
        assert float(row["inherent_score"]) == 20.0  # 4*5
        assert float(row["residual_score"]) == 6.0   # 2*3
        assert float(row["target_score"])   == 2.0   # 1*2
        await admin_conn.execute("DELETE FROM risks WHERE id=$1", risk_uuid)


@pytest.mark.asyncio
async def test_insert_with_score_column_fails(admin_conn, demo_tenant):
    """Regression guard: any code still inserting into the generated columns
    must fail loudly (Postgres errors, not silent corruption)."""
    cat_id = await admin_conn.fetchval(
        "SELECT id FROM risk_categories LIMIT 1"
    )
    import asyncpg
    with pytest.raises(asyncpg.exceptions.GeneratedAlwaysError):
        async with admin_conn.transaction():
            await admin_conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", demo_tenant
            )
            await admin_conn.execute(
                """
                INSERT INTO risks (
                    id, tenant_id, risk_id, title, description, category_id,
                    inherent_likelihood, inherent_impact, inherent_score,
                    source, status
                ) VALUES (
                    gen_random_uuid(),$1,'BAD-PROBE','x','x',$2,
                    1,1,99.0,
                    'manual','open'
                )
                """,
                demo_tenant, cat_id,
            )
