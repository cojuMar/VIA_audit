"""
Questionnaire Engine

Loads questionnaire templates from JSON files.
Sends questionnaires to vendors (records the send event in DB).
Accepts responses and AI-scores them.

AI scoring of responses:
  Uses Claude Haiku to read all Q&A pairs and produce:
  - A risk score (0.0–10.0, higher = riskier)
  - A list of concerning responses
  - A summary paragraph
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
import anthropic

logger = logging.getLogger(__name__)


class QuestionnaireEngine:
    def __init__(self, db_pool, templates_dir: str, anthropic_api_key: str = ""):
        self._pool = db_pool
        self._templates_dir = Path(templates_dir)
        self._client = anthropic.AsyncAnthropic(api_key=anthropic_api_key) if anthropic_api_key else None
        self._templates_cache: Dict[str, dict] = {}

    def load_template(self, slug: str) -> dict:
        """Load questionnaire template from JSON file. Cached after first load."""
        if slug in self._templates_cache:
            return self._templates_cache[slug]
        path = self._templates_dir / f"{slug}.json"
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {slug}.json")
        with open(path, 'r', encoding='utf-8') as f:
            template = json.load(f)
        self._templates_cache[slug] = template
        return template

    def list_templates(self) -> List[dict]:
        """List all available questionnaire templates."""
        templates = []
        for path in sorted(self._templates_dir.glob("*.json")):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                templates.append({
                    "slug": data.get("slug", path.stem),
                    "name": data.get("name"),
                    "version": data.get("version"),
                    "description": data.get("description"),
                    "question_count": sum(len(d.get("questions", [])) for d in data.get("domains", [])),
                    "estimated_minutes": data.get("estimated_completion_minutes")
                })
            except Exception as e:
                logger.warning(f"Failed to load template {path.name}: {e}")
        return templates

    async def send_questionnaire(self, tenant_id: UUID, vendor_id: UUID, template_slug: str, due_days: int = 14) -> UUID:
        """
        Create a questionnaire record in DB with status='sent'.
        Returns the questionnaire ID.
        """
        # Validate template exists
        self.load_template(template_slug)
        template_version = self._templates_cache[template_slug].get('version', '1.0')

        due_date = datetime.now(timezone.utc) + timedelta(days=due_days)

        async with self._pool.acquire() as conn:
            await conn.execute("SET LOCAL app.tenant_id = $1", str(tenant_id))
            qid = await conn.fetchval("""
                INSERT INTO vendor_questionnaires
                    (tenant_id, vendor_id, template_slug, template_version, status, sent_at, due_date)
                VALUES ($1, $2, $3, $4, 'sent', NOW(), $5)
                RETURNING id
            """, tenant_id, vendor_id, template_slug, template_version, due_date)

        logger.info(f"Questionnaire sent: vendor={vendor_id} template={template_slug}")
        return qid

    async def submit_responses(self, tenant_id: UUID, questionnaire_id: UUID, responses: Dict[str, Any]) -> dict:
        """
        Record vendor responses and trigger AI scoring.
        Returns AI scoring result.
        """
        async with self._pool.acquire() as conn:
            await conn.execute("SET LOCAL app.tenant_id = $1", str(tenant_id))

            row = await conn.fetchrow("""
                SELECT template_slug FROM vendor_questionnaires
                WHERE id = $1 AND tenant_id = $2
            """, questionnaire_id, tenant_id)

            if not row:
                raise ValueError(f"Questionnaire {questionnaire_id} not found")

            template = self.load_template(row['template_slug'])
            ai_result = await self._ai_score_responses(template, responses)

            await conn.execute("""
                UPDATE vendor_questionnaires SET
                    responses = $1::jsonb,
                    status = 'completed',
                    completed_at = NOW(),
                    ai_score = $2,
                    ai_summary = $3
                WHERE id = $4 AND tenant_id = $5
            """, json.dumps(responses), ai_result['score'], ai_result['summary'],
                questionnaire_id, tenant_id)

        return ai_result

    async def _ai_score_responses(self, template: dict, responses: Dict[str, Any]) -> dict:
        """Use Claude Haiku to score questionnaire responses."""
        if not self._client:
            return {"score": 5.0, "summary": "AI scoring unavailable — manual review required.", "concerns": []}

        # Build Q&A pairs
        qa_pairs = []
        for domain in template.get('domains', []):
            for q in domain.get('questions', []):
                answer = responses.get(q['id'], 'No response')
                qa_pairs.append(f"[{q['id']}] {q['text']}\nAnswer: {answer}")

        qa_text = "\n\n".join(qa_pairs[:50])  # Limit to avoid token overflow

        try:
            response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                temperature=0,
                messages=[{
                    "role": "user",
                    "content": f"""You are a vendor security risk analyst. Review these questionnaire responses and output ONLY valid JSON with this exact structure:
{{"score": <float 0-10 where 10=highest risk>, "summary": "<2-3 sentence summary>", "concerns": ["<concern1>", "<concern2>"]}}

Questionnaire responses:
{qa_text}"""
                }]
            )
            import re
            text = response.content[0].text.strip()
            # Extract JSON from response
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {"score": 5.0, "summary": text[:500], "concerns": []}
        except Exception as e:
            logger.warning(f"AI questionnaire scoring failed: {e}")
            return {"score": 5.0, "summary": "AI scoring failed — manual review required.", "concerns": []}
