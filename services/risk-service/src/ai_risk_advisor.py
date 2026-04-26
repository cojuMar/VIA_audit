import json
import logging

import asyncpg

from .db import tenant_conn

logger = logging.getLogger(__name__)

try:
    import anthropic as _anthropic_module
except ImportError:
    _anthropic_module = None  # type: ignore[assignment]


class AIRiskAdvisor:
    def __init__(self, settings) -> None:
        self.client = None
        if _anthropic_module and settings.anthropic_api_key:
            self.client = _anthropic_module.AsyncAnthropic(
                api_key=settings.anthropic_api_key
            )

    # ------------------------------------------------------------------
    # suggest_treatments
    # ------------------------------------------------------------------
    async def suggest_treatments(self, risk: dict) -> list[dict]:
        """
        Given a risk dict, use Claude Haiku to suggest 3 treatment options.
        Returns list of {treatment_type, title, description, estimated_effort}.
        Graceful fallback if no API key.
        """
        if not self.client:
            return self._fallback_treatments(risk)

        prompt = (
            f"You are a risk management expert. Given the following risk, suggest exactly "
            f"3 treatment options (one each of mitigate, transfer, and accept or avoid).\n\n"
            f"Risk title: {risk.get('title', 'N/A')}\n"
            f"Description: {risk.get('description', 'N/A')}\n"
            f"Category: {risk.get('category_name', risk.get('category', 'N/A'))}\n"
            f"Inherent score: {risk.get('inherent_score', 'N/A')}\n"
            f"Residual score: {risk.get('residual_score', 'N/A')}\n\n"
            f"Return a JSON array with 3 objects, each having keys: "
            f"treatment_type (one of: mitigate, accept, transfer, avoid), "
            f"title (short), description (2-3 sentences), estimated_effort (low/medium/high). "
            f"Return ONLY the JSON array, no other text."
        )

        try:
            message = await self.client.messages.create(
                model="claude-haiku-20240307",
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
            text = message.content[0].text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception as exc:
            logger.warning("AI suggest_treatments failed: %s", exc)
            return self._fallback_treatments(risk)

    def _fallback_treatments(self, risk: dict) -> list[dict]:
        return [
            {
                "treatment_type": "mitigate",
                "title": "Implement additional controls",
                "description": (
                    "Review and strengthen existing controls to reduce the likelihood "
                    "and/or impact of this risk. Consider additional monitoring and "
                    "preventative measures."
                ),
                "estimated_effort": "medium",
            },
            {
                "treatment_type": "transfer",
                "title": "Transfer risk via insurance or contract",
                "description": (
                    "Evaluate insurance products or contractual arrangements that "
                    "transfer the financial impact of this risk to a third party."
                ),
                "estimated_effort": "low",
            },
            {
                "treatment_type": "accept",
                "title": "Accept risk within appetite",
                "description": (
                    "If the residual risk falls within the organisation's risk appetite, "
                    "formally accept the risk and document the rationale for acceptance."
                ),
                "estimated_effort": "low",
            },
        ]

    # ------------------------------------------------------------------
    # assess_risk_description
    # ------------------------------------------------------------------
    async def assess_risk_description(
        self, title: str, description: str
    ) -> dict:
        """
        Use Claude to suggest likelihood/impact scores and category.
        Returns {suggested_likelihood, suggested_impact, suggested_category, rationale}.
        """
        if not self.client:
            return {
                "suggested_likelihood": 3,
                "suggested_impact": 3,
                "suggested_category": "operational",
                "rationale": "AI assessment unavailable — default scores applied.",
            }

        prompt = (
            f"You are a risk management expert. Assess the following risk and suggest "
            f"likelihood and impact scores on a 1-5 scale, and an appropriate category.\n\n"
            f"Risk title: {title}\n"
            f"Description: {description}\n\n"
            f"Categories available: financial, operational, compliance, cybersecurity, "
            f"strategic, reputational.\n\n"
            f"Return a JSON object with keys: "
            f"suggested_likelihood (integer 1-5), suggested_impact (integer 1-5), "
            f"suggested_category (string), rationale (1-2 sentences). "
            f"Return ONLY the JSON object, no other text."
        )

        try:
            message = await self.client.messages.create(
                model="claude-haiku-20240307",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            text = message.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text)
            # Clamp values
            result["suggested_likelihood"] = max(
                1, min(5, int(result.get("suggested_likelihood", 3)))
            )
            result["suggested_impact"] = max(
                1, min(5, int(result.get("suggested_impact", 3)))
            )
            return result
        except Exception as exc:
            logger.warning("AI assess_risk_description failed: %s", exc)
            return {
                "suggested_likelihood": 3,
                "suggested_impact": 3,
                "suggested_category": "operational",
                "rationale": "AI assessment failed — default scores applied.",
            }

    # ------------------------------------------------------------------
    # generate_risk_narrative
    # ------------------------------------------------------------------
    async def generate_risk_narrative(
        self, pool: asyncpg.Pool, tenant_id: str
    ) -> str:
        """
        Generate a 3-paragraph risk narrative suitable for board reporting.
        Fetches top 10 risks first, then generates narrative.
        """
        # Fetch top 10 open risks ordered by score
        async with tenant_conn(pool, tenant_id) as conn:
            rows = await conn.fetch(
                """
                SELECT r.risk_id, r.title, r.description,
                       COALESCE(r.residual_score, r.inherent_score) AS score,
                       rc.display_name AS category
                FROM risks r
                LEFT JOIN risk_categories rc ON rc.id = r.category_id
                WHERE r.tenant_id = $1 AND r.status != 'closed'
                ORDER BY score DESC NULLS LAST
                LIMIT 10
                """,
                tenant_id,
            )

        risks_summary = "\n".join(
            f"- [{r['risk_id']}] {r['title']} (category: {r['category'] or 'N/A'}, "
            f"score: {r['score'] or 0:.0f}): {(r['description'] or '')[:120]}"
            for r in rows
        )

        if not self.client:
            top_risk = rows[0]["title"] if rows else "No risks recorded"
            return (
                f"The organisation currently has {len(rows)} open risks. "
                f"The highest-rated risk is '{top_risk}'. "
                f"Management is actively monitoring and treating these risks in line with appetite.\n\n"
                f"Treatment plans are in place for material risks and progress is reviewed quarterly. "
                f"Key risk indicators are tracked and reported monthly to the Risk Committee.\n\n"
                f"The board is asked to note the current risk profile and approve any changes to "
                f"risk appetite statements for the forthcoming period."
            )

        prompt = (
            f"You are a Chief Risk Officer preparing a board report. "
            f"Write a concise 3-paragraph risk narrative based on the following top risks:\n\n"
            f"{risks_summary}\n\n"
            f"Paragraph 1: Overall risk landscape and key themes.\n"
            f"Paragraph 2: Material risks and treatment progress.\n"
            f"Paragraph 3: Outlook and recommendations for the board.\n"
            f"Write in formal board-report language. Do not use bullet points."
        )

        try:
            message = await self.client.messages.create(
                model="claude-haiku-20240307",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception as exc:
            logger.warning("AI generate_risk_narrative failed: %s", exc)
            return (
                f"The organisation currently has {len(rows)} open risks. "
                f"Management is monitoring these risks and treatment actions are underway. "
                f"The board is asked to note the current risk profile."
            )
