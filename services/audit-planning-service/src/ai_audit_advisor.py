from __future__ import annotations

import json

import anthropic


class AIAuditAdvisor:
    def __init__(self, api_key: str) -> None:
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None
        self.model = "claude-haiku-20240307"

    # ------------------------------------------------------------------
    async def suggest_audit_scope(
        self, entity: dict, risk_context: dict
    ) -> dict:
        fallback = {
            "objectives": [
                "Assess adequacy of internal controls",
                "Evaluate compliance with applicable policies",
                "Identify operational risk exposures",
            ],
            "scope_areas": [
                "Control environment",
                "Process workflows",
                "Risk management practices",
            ],
            "key_risks": [
                "Control deficiencies",
                "Regulatory non-compliance",
                "Operational inefficiencies",
            ],
            "suggested_hours": 80,
            "suggested_team_size": 2,
        }

        if not self.client:
            return fallback

        prompt = f"""You are an internal audit planning expert.

Given the following audit entity and risk context, suggest an appropriate audit scope.

Entity:
{json.dumps(entity, indent=2, default=str)}

Risk Context:
{json.dumps(risk_context, indent=2, default=str)}

Return a JSON object with these keys:
- objectives: list of 3-5 audit objectives (strings)
- scope_areas: list of 3-6 key scope areas to be covered (strings)
- key_risks: list of 3-5 key risks to address (strings)
- suggested_hours: estimated total audit hours (integer)
- suggested_team_size: recommended team size (integer)

Return ONLY valid JSON, no other text."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            return json.loads(raw)
        except Exception:
            return fallback

    # ------------------------------------------------------------------
    async def generate_audit_program(self, engagement: dict) -> str:
        fallback = (
            "# Audit Program\n\n"
            "## Objectives\n"
            "- Assess the adequacy and effectiveness of internal controls\n"
            "- Evaluate compliance with policies and procedures\n\n"
            "## Test Steps\n"
            "1. Obtain and review relevant policies and procedures\n"
            "2. Conduct walkthroughs of key processes\n"
            "3. Select a representative sample for testing\n"
            "4. Perform substantive testing on sampled items\n"
            "5. Document and evaluate exceptions\n\n"
            "## Sampling Guidance\n"
            "- Use statistical or judgmental sampling as appropriate\n"
            "- Minimum sample size: 25 items or full population if < 25\n\n"
            "## Key Controls to Test\n"
            "- Segregation of duties\n"
            "- Authorization controls\n"
            "- Reconciliation procedures\n"
            "- IT general controls\n"
        )

        if not self.client:
            return fallback

        prompt = f"""You are an internal audit expert. Generate a structured audit program for the following engagement.

Engagement Details:
{json.dumps(engagement, indent=2, default=str)}

Produce a markdown-formatted audit program that includes:
1. Audit objectives
2. Scope and approach
3. Detailed test steps (numbered)
4. Sampling guidance
5. Key controls to test
6. Documentation requirements

Be specific and practical. Use markdown formatting with headers, lists, and tables where appropriate."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception:
            return fallback

    # ------------------------------------------------------------------
    async def prioritize_universe(
        self, entities: list[dict]
    ) -> list[dict]:
        if not self.client or not entities:
            # Fallback: sort by risk_score DESC, ai_priority_score = risk_score
            sorted_entities = sorted(
                entities,
                key=lambda e: float(e.get("risk_score", 0)),
                reverse=True,
            )
            for e in sorted_entities:
                e["ai_priority_score"] = float(e.get("risk_score", 0))
                e["ai_rationale"] = (
                    "Priority based on risk score (AI advisor not available)."
                )
            return sorted_entities

        # Prepare a condensed list for the prompt
        condensed = [
            {
                "id": str(e.get("id")),
                "name": e.get("name"),
                "risk_score": e.get("risk_score"),
                "last_audit_date": str(e.get("last_audit_date", "unknown")),
                "department": e.get("department"),
                "entity_type": e.get("entity_type_name"),
            }
            for e in entities
        ]

        prompt = f"""You are an internal audit planning expert prioritizing an audit universe.

For each entity below, assign an ai_priority_score (0-10, where 10 is highest priority) and a brief ai_rationale.
Consider: risk score, time since last audit, regulatory exposure, department criticality.

Entities:
{json.dumps(condensed, indent=2, default=str)}

Return a JSON array where each element has:
- id: the entity id
- ai_priority_score: float 0-10
- ai_rationale: string (1-2 sentences)

Return ONLY valid JSON array, no other text."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            scored = json.loads(raw)

            # Merge scores back into entity dicts
            score_map = {
                item["id"]: item for item in scored if "id" in item
            }
            result = []
            for entity in entities:
                eid = str(entity.get("id"))
                enriched = dict(entity)
                if eid in score_map:
                    enriched["ai_priority_score"] = score_map[eid].get(
                        "ai_priority_score", float(entity.get("risk_score", 0))
                    )
                    enriched["ai_rationale"] = score_map[eid].get(
                        "ai_rationale", ""
                    )
                else:
                    enriched["ai_priority_score"] = float(
                        entity.get("risk_score", 0)
                    )
                    enriched["ai_rationale"] = "Score not available from AI."
                result.append(enriched)

            return sorted(
                result,
                key=lambda e: float(e.get("ai_priority_score", 0)),
                reverse=True,
            )
        except Exception:
            # Graceful fallback
            sorted_entities = sorted(
                entities,
                key=lambda e: float(e.get("risk_score", 0)),
                reverse=True,
            )
            for e in sorted_entities:
                e["ai_priority_score"] = float(e.get("risk_score", 0))
                e["ai_rationale"] = "Fallback: sorted by risk score."
            return sorted_entities
