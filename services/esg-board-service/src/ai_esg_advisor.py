from __future__ import annotations

import json

import anthropic


class AIESGAdvisor:
    def __init__(self, api_key: str) -> None:
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None
        self.model = "claude-haiku-20240307"

    # ------------------------------------------------------------------
    async def generate_esg_narrative(
        self,
        scorecard: dict,
        targets: list,
        reporting_period: str,
    ) -> str:
        fallback = (
            f"## ESG Performance Narrative — {reporting_period}\n\n"
            "### Overview\n"
            f"For the period {reporting_period}, the organisation achieved an overall "
            f"ESG disclosure coverage of {scorecard.get('overall_coverage_pct', 0):.1f}%. "
            "Environmental, social and governance metrics are tracked across multiple "
            "frameworks to provide comprehensive sustainability reporting.\n\n"
            "### Key Achievements\n"
            "- Continued progress on ESG data collection and disclosure quality\n"
            "- Active monitoring of science-based and voluntary targets\n"
            "- Strengthened governance oversight through board-level reporting\n\n"
            "### Areas of Focus\n"
            "- Closing disclosure gaps to improve overall ESG coverage\n"
            "- Aligning targets with leading industry benchmarks\n"
            "- Enhancing data assurance and third-party verification\n\n"
            "### Looking Ahead\n"
            "Management remains committed to improving ESG performance transparency "
            "and advancing progress against all active sustainability targets."
        )

        if not self.client:
            return fallback

        prompt = f"""You are an ESG reporting expert preparing a board-ready ESG performance narrative.

Given the following ESG scorecard and target information for {reporting_period}, write a concise 3-4 paragraph narrative for the board.

ESG Scorecard:
{json.dumps(scorecard, indent=2, default=str)}

Active Targets:
{json.dumps(targets[:20], indent=2, default=str)}

Requirements:
- Write 3-4 well-structured paragraphs in markdown
- Paragraph 1: Overall ESG performance summary with coverage highlights
- Paragraph 2: Key achievements and positive trends
- Paragraph 3: Areas of concern or underperformance
- Paragraph 4: Year-on-year trends summary and outlook
- Tone: Professional, factual, board-appropriate
- Use a level-2 heading (##) for the narrative title
- Return only the markdown narrative text, no other commentary"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception:
            return fallback

    # ------------------------------------------------------------------
    async def generate_board_pack_summary(
        self,
        package_items: list[dict],
        package_type: str,
    ) -> str:
        type_label = {
            "esg_report": "ESG Board Package",
            "audit_report": "Audit Committee Package",
            "board_pack": "Board Package",
        }.get(package_type, "Board Package")

        fallback = (
            f"## {type_label} — Executive Summary\n\n"
            "This package has been prepared for board review and contains "
            "the key information required to support informed decision-making. "
            "The sections below cover material topics relevant to the current "
            "reporting period.\n\n"
            "Management draw the board's attention to the items flagged for "
            "decision or discussion. Supporting detail is available on request "
            "from the respective business owners."
        )

        if not self.client:
            return fallback

        # Truncate large content_data to avoid exceeding token limits
        items_summary = []
        for item in package_items:
            entry = {"section": item.get("section", item.get("section_title", ""))}
            data = item.get("data", item.get("content_data", {}))
            if isinstance(data, (dict, list)):
                # Summarise by converting to truncated JSON
                raw = json.dumps(data, default=str)
                entry["data_preview"] = raw[:800] + ("..." if len(raw) > 800 else "")
            else:
                entry["data_preview"] = str(data)[:800]
            items_summary.append(entry)

        prompt = f"""You are preparing a concise executive summary for a {type_label} destined for senior board members.

Package sections:
{json.dumps(items_summary, indent=2)}

Requirements:
- Write 2-3 paragraphs in markdown
- Strategic and decision-focused; avoid operational detail
- Highlight key risks, findings or metrics requiring board attention
- Use a level-2 heading (##) titled "Executive Summary"
- Tone: Formal, concise, directorial
- Return only the markdown summary, no other text"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=768,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception:
            return fallback

    # ------------------------------------------------------------------
    async def assess_esg_materiality(
        self,
        entity_type: str,
        industry: str,
        metrics: list[dict],
    ) -> dict:
        fallback_high = [m for m in metrics if m.get("is_required")]
        fallback_other = [m for m in metrics if not m.get("is_required")]
        fallback_other_sorted = sorted(
            fallback_other, key=lambda m: m.get("display_name", "")
        )
        fallback = {
            "high_materiality": fallback_high,
            "medium_materiality": fallback_other_sorted[: len(fallback_other_sorted) // 2],
            "low_materiality": fallback_other_sorted[len(fallback_other_sorted) // 2 :],
        }

        if not self.client:
            return fallback

        prompt = f"""You are an ESG materiality expert.

Given the following organisation context and ESG metrics, rank each metric by materiality (financial impact + stakeholder salience).

Organisation:
- Entity type: {entity_type}
- Industry: {industry}

Metrics:
{json.dumps([{"id": m.get("id"), "name": m.get("display_name"), "category": m.get("category"), "is_required": m.get("is_required")} for m in metrics[:50]], indent=2)}

Return a JSON object with three keys:
- high_materiality: list of metric IDs with high financial or stakeholder impact
- medium_materiality: list of metric IDs with moderate impact
- low_materiality: list of metric IDs with low impact

Return ONLY valid JSON, no other text."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            ranked = json.loads(raw)

            # Map IDs back to full metric objects
            metric_map = {m["id"]: m for m in metrics}
            return {
                "high_materiality": [
                    metric_map[mid] for mid in ranked.get("high_materiality", [])
                    if mid in metric_map
                ],
                "medium_materiality": [
                    metric_map[mid] for mid in ranked.get("medium_materiality", [])
                    if mid in metric_map
                ],
                "low_materiality": [
                    metric_map[mid] for mid in ranked.get("low_materiality", [])
                    if mid in metric_map
                ],
            }
        except Exception:
            return fallback

    # ------------------------------------------------------------------
    async def suggest_esg_targets(
        self,
        current_disclosures: list[dict],
        peer_benchmarks: dict | None = None,
    ) -> list[dict]:
        # Fallback: 10 % improvement for each metric with a numeric value
        fallback = []
        for d in current_disclosures:
            val = d.get("numeric_value")
            if val is None:
                continue
            lower = d.get("lower_is_better", False)
            suggested = round(val * 0.9, 4) if lower else round(val * 1.1, 4)
            fallback.append(
                {
                    "metric_definition_id": d.get("metric_definition_id"),
                    "metric_name": d.get("metric_name", ""),
                    "current_value": val,
                    "target_value": suggested,
                    "target_year": 2030,
                    "rationale": "10% improvement on current baseline",
                }
            )
        if not self.client:
            return fallback

        prompt = f"""You are a sustainability strategy expert.

Based on the current ESG disclosure data below, suggest ambitious but achievable targets for each metric.

Current disclosures:
{json.dumps([{"metric_id": d.get("metric_definition_id"), "metric_name": d.get("metric_name"), "category": d.get("category"), "current_value": d.get("numeric_value"), "unit": d.get("unit")} for d in current_disclosures[:30]], indent=2)}

{"Peer benchmarks: " + json.dumps(peer_benchmarks, indent=2) if peer_benchmarks else "No peer benchmark data available."}

For each metric that has a numeric value, suggest:
- target_value: the suggested target (numeric)
- target_year: suggested year to achieve (2025-2035)
- rationale: 1-2 sentence explanation

Return a JSON array where each object has:
- metric_definition_id (string)
- target_value (number)
- target_year (integer)
- rationale (string)

Return ONLY valid JSON array, no other text."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            suggestions = json.loads(raw)
            # Enrich with current_value from disclosures map
            disc_map = {
                d["metric_definition_id"]: d for d in current_disclosures
            }
            for s in suggestions:
                mid = s.get("metric_definition_id")
                if mid and mid in disc_map:
                    s["current_value"] = disc_map[mid].get("numeric_value")
                    s.setdefault("metric_name", disc_map[mid].get("metric_name", ""))
            return suggestions
        except Exception:
            return fallback
