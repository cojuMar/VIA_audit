from __future__ import annotations

import json

import anthropic


class AIFieldAdvisor:
    def __init__(self, api_key: str) -> None:
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None
        self.model = "claude-haiku-20240307"

    # ------------------------------------------------------------------

    async def generate_audit_findings_report(self, audit_summary: dict) -> str:
        """
        Generate a field audit findings report in markdown.
        Falls back to a structured template when AI is unavailable.
        """
        audit = audit_summary.get("audit", {})
        findings_by_severity = audit_summary.get("findings_by_severity", {})
        section_scores = audit_summary.get("section_scores", [])
        finding_count = audit_summary.get("finding_count", 0)

        fallback_lines = [
            "# Field Audit Findings Report",
            "",
            f"**Location:** {audit.get('location_name', 'Unknown')}",
            f"**Auditor:** {audit.get('auditor_name') or audit.get('auditor_email', 'Unknown')}",
            f"**Status:** {audit.get('status', 'Unknown')}",
            f"**Overall Score:** {audit.get('overall_score', 'N/A')}%",
            f"**Risk Level:** {audit.get('risk_level', 'Unknown').upper()}",
            "",
            "## Findings Summary",
            "",
            f"- **Total Findings:** {finding_count}",
            f"- Critical: {findings_by_severity.get('critical', 0)}",
            f"- High: {findings_by_severity.get('high', 0)}",
            f"- Medium: {findings_by_severity.get('medium', 0)}",
            f"- Low: {findings_by_severity.get('low', 0)}",
            "",
            "## Section Scores",
            "",
        ]
        for section in section_scores:
            score = section.get("score_pct")
            score_str = f"{score}%" if score is not None else "N/A"
            fallback_lines.append(
                f"- **{section['section_name']}**: {score_str} "
                f"({section.get('finding_count', 0)} findings)"
            )

        fallback_lines += [
            "",
            "## Recommendations",
            "",
            "1. Address all critical and high findings immediately.",
            "2. Develop corrective action plans for medium findings within 30 days.",
            "3. Monitor low findings for resolution within 90 days.",
            "4. Schedule a follow-up audit to verify remediation.",
        ]
        fallback = "\n".join(fallback_lines)

        if not self.client:
            return fallback

        prompt = f"""You are a senior internal audit professional writing a formal field audit findings report.

Audit Summary:
{json.dumps(audit_summary, indent=2, default=str)}

Write a comprehensive, professional markdown-formatted field audit report that includes:
1. Executive Summary (2-3 sentences on overall audit outcome)
2. Key Findings by Severity (critical → low, with brief description for each)
3. Section Performance Analysis (reference section_scores data)
4. Risk Assessment (explain the overall risk level and score)
5. Recommendations (prioritised, actionable steps for each severity tier)
6. Conclusion

Use professional audit language. Be concise and actionable."""

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

    async def prioritize_findings(
        self, findings: list[dict]
    ) -> list[dict]:
        """
        Re-rank findings by actual risk priority and add remediation suggestions.
        Falls back to severity-based sort with generic suggestions.
        """
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

        def _fallback_sort(findings: list[dict]) -> list[dict]:
            sorted_findings = sorted(
                findings,
                key=lambda f: severity_order.get(
                    (f.get("finding_severity") or "low").lower(), 3
                ),
            )
            generic_suggestions = {
                "critical": "Escalate immediately to management; implement emergency controls.",
                "high": "Develop a corrective action plan within 5 business days.",
                "medium": "Schedule remediation within 30 days and assign an owner.",
                "low": "Address during the next routine improvement cycle.",
            }
            for rank, f in enumerate(sorted_findings, start=1):
                f["priority_rank"] = rank
                sev = (f.get("finding_severity") or "low").lower()
                f["remediation_suggestion"] = generic_suggestions.get(
                    sev, generic_suggestions["low"]
                )
            return sorted_findings

        if not self.client or not findings:
            return _fallback_sort(findings)

        condensed = [
            {
                "id": str(f.get("id", f.get("sync_id", idx))),
                "question_id": f.get("question_id"),
                "finding_severity": f.get("finding_severity"),
                "comment": f.get("comment"),
                "response_value": f.get("response_value"),
            }
            for idx, f in enumerate(findings)
        ]

        prompt = f"""You are an internal audit risk specialist. Prioritize the following audit findings by actual business risk and provide specific remediation suggestions.

Findings:
{json.dumps(condensed, indent=2, default=str)}

For each finding, assign:
- priority_rank: integer starting at 1 (1 = highest priority)
- remediation_suggestion: specific, actionable 1-2 sentence recommendation

Return a JSON array with objects containing: id, priority_rank, remediation_suggestion.
Return ONLY valid JSON array, no other text."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            ranked = json.loads(raw)

            rank_map = {str(item["id"]): item for item in ranked if "id" in item}

            result = []
            for idx, f in enumerate(findings):
                enriched = dict(f)
                fid = str(f.get("id", f.get("sync_id", idx)))
                if fid in rank_map:
                    enriched["priority_rank"] = rank_map[fid].get("priority_rank", idx + 1)
                    enriched["remediation_suggestion"] = rank_map[fid].get(
                        "remediation_suggestion", ""
                    )
                else:
                    enriched["priority_rank"] = idx + 1
                    enriched["remediation_suggestion"] = ""
                result.append(enriched)

            return sorted(result, key=lambda f: f.get("priority_rank", 999))
        except Exception:
            return _fallback_sort(findings)

    # ------------------------------------------------------------------

    async def generate_offline_checklist_hints(
        self, template: dict
    ) -> dict:
        """
        Generate per-question guidance hints for offline use.
        Returns {question_id: {hint, common_finding, photo_tip}}.
        Falls back to empty hints dict.
        """
        if not self.client:
            return {}

        # Flatten all questions from all sections
        all_questions = []
        for section in template.get("sections", []):
            for q in section.get("questions", []):
                all_questions.append(
                    {
                        "id": str(q.get("id")),
                        "question_text": q.get("question_text"),
                        "question_type": q.get("question_type"),
                        "section_name": section.get("name"),
                    }
                )

        if not all_questions:
            return {}

        prompt = f"""You are a field audit expert. For each of the following audit questions, provide:
- hint: what the auditor should look for when answering this question (1-2 sentences)
- common_finding: the most common non-compliance finding for this question (1 sentence)
- photo_tip: guidance on what photo evidence to capture (1 sentence)

Template: {template.get('name', 'Audit Template')}

Questions:
{json.dumps(all_questions, indent=2, default=str)}

Return a JSON object where each key is the question id (string) and the value is:
{{
  "hint": "...",
  "common_finding": "...",
  "photo_tip": "..."
}}

Return ONLY valid JSON object, no other text."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            return json.loads(raw)
        except Exception:
            return {}
