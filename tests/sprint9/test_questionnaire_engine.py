import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/tprm-service'))

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from src.questionnaire_engine import QuestionnaireEngine

# ---------------------------------------------------------------------------
# Template presence guard
# ---------------------------------------------------------------------------

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), '../../questionnaire-templates')
_HAS_TEMPLATES = os.path.isdir(TEMPLATES_DIR) and len(os.listdir(TEMPLATES_DIR)) > 0

skip_no_templates = pytest.mark.skipif(
    not _HAS_TEMPLATES,
    reason="questionnaire-templates/ directory is absent or empty"
)

# ---------------------------------------------------------------------------
# Pool helper (shared)
# ---------------------------------------------------------------------------

def _make_pool():
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


# ---------------------------------------------------------------------------
# TestTemplateLoading
# ---------------------------------------------------------------------------

class TestTemplateLoading:
    @skip_no_templates
    def test_list_templates_returns_list(self):
        engine = QuestionnaireEngine(
            db_pool=_make_pool(),
            templates_dir=TEMPLATES_DIR,
            anthropic_api_key="",
        )
        result = engine.list_templates()
        assert isinstance(result, list)
        assert len(result) >= 2  # at minimum sig-lite + caiq-v4 are present

    @skip_no_templates
    def test_sig_lite_has_18_domains(self):
        engine = QuestionnaireEngine(
            db_pool=_make_pool(),
            templates_dir=TEMPLATES_DIR,
            anthropic_api_key="",
        )
        template = engine.load_template('sig-lite')
        domains = template.get('domains', [])
        assert len(domains) == 18, (
            f"sig-lite expected 18 domains, got {len(domains)}"
        )

    @skip_no_templates
    def test_sig_lite_minimum_54_questions(self):
        engine = QuestionnaireEngine(
            db_pool=_make_pool(),
            templates_dir=TEMPLATES_DIR,
            anthropic_api_key="",
        )
        template = engine.load_template('sig-lite')
        total = sum(len(d.get('questions', [])) for d in template.get('domains', []))
        assert total >= 54, (
            f"sig-lite expected >= 54 questions, got {total}"
        )

    @skip_no_templates
    def test_caiq_has_17_domains(self):
        engine = QuestionnaireEngine(
            db_pool=_make_pool(),
            templates_dir=TEMPLATES_DIR,
            anthropic_api_key="",
        )
        template = engine.load_template('caiq-v4')
        domains = template.get('domains', [])
        assert len(domains) == 17, (
            f"caiq-v4 expected 17 domains, got {len(domains)}"
        )

    @skip_no_templates
    def test_custom_base_has_4_domains(self):
        custom_path = os.path.join(TEMPLATES_DIR, 'custom-base.json')
        if not os.path.exists(custom_path):
            pytest.skip("custom-base.json not present in questionnaire-templates/")
        engine = QuestionnaireEngine(
            db_pool=_make_pool(),
            templates_dir=TEMPLATES_DIR,
            anthropic_api_key="",
        )
        template = engine.load_template('custom-base')
        domains = template.get('domains', [])
        assert len(domains) == 4, (
            f"custom-base expected 4 domains, got {len(domains)}"
        )

    @skip_no_templates
    def test_all_questions_have_required_fields(self):
        engine = QuestionnaireEngine(
            db_pool=_make_pool(),
            templates_dir=TEMPLATES_DIR,
            anthropic_api_key="",
        )
        required = {'id', 'text', 'type', 'risk_weight'}
        for path in sorted(Path(TEMPLATES_DIR).glob("*.json")):
            template = engine.load_template(path.stem)
            for domain in template.get('domains', []):
                for q in domain.get('questions', []):
                    missing = required - set(q.keys())
                    assert not missing, (
                        f"Template '{path.stem}' domain '{domain.get('id')}' "
                        f"question '{q.get('id', '?')}' missing fields: {missing}"
                    )

    def test_load_nonexistent_template_raises(self):
        engine = QuestionnaireEngine(
            db_pool=_make_pool(),
            templates_dir=TEMPLATES_DIR,
            anthropic_api_key="",
        )
        with pytest.raises(FileNotFoundError):
            engine.load_template('nonexistent')


# ---------------------------------------------------------------------------
# TestAIScoring
# ---------------------------------------------------------------------------

class TestAIScoring:
    """Tests for QuestionnaireEngine._ai_score_responses — mocks Anthropic."""

    _MINIMAL_TEMPLATE = {
        "slug": "test",
        "name": "Test",
        "version": "1.0",
        "domains": [
            {
                "id": "A",
                "name": "Security",
                "questions": [
                    {"id": "A.1", "text": "Do you encrypt data at rest?", "type": "yes_no_na", "risk_weight": 3},
                ]
            }
        ]
    }

    def _make_engine_with_mock_client(self, mock_client):
        engine = QuestionnaireEngine(
            db_pool=_make_pool(),
            templates_dir=TEMPLATES_DIR,
            anthropic_api_key="sk-dummy",
        )
        engine._client = mock_client
        return engine

    @pytest.mark.asyncio
    async def test_ai_score_returns_dict_with_required_keys(self):
        ai_response_json = '{"score": 3.5, "summary": "Low risk vendor.", "concerns": ["No MFA"]}'
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=ai_response_json)]

        mock_client = AsyncMock()
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        engine = self._make_engine_with_mock_client(mock_client)
        result = await engine._ai_score_responses(self._MINIMAL_TEMPLATE, {'A.1': 'yes'})

        assert isinstance(result, dict)
        assert 'score' in result
        assert 'summary' in result
        assert 'concerns' in result

    @pytest.mark.asyncio
    async def test_ai_score_fallback_when_no_api_key(self):
        engine = QuestionnaireEngine(
            db_pool=_make_pool(),
            templates_dir=TEMPLATES_DIR,
            anthropic_api_key="",
        )
        # _client is None — should return fallback without calling Anthropic
        result = await engine._ai_score_responses(self._MINIMAL_TEMPLATE, {'A.1': 'yes'})

        assert isinstance(result, dict)
        assert 'score' in result
        assert 'summary' in result
        assert 'concerns' in result

    @pytest.mark.asyncio
    async def test_ai_score_fallback_on_exception(self):
        mock_client = AsyncMock()
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=Exception("Network error"))

        engine = self._make_engine_with_mock_client(mock_client)
        # Must not raise — returns fallback dict
        result = await engine._ai_score_responses(self._MINIMAL_TEMPLATE, {'A.1': 'yes'})

        assert isinstance(result, dict)
        assert 'score' in result
        assert 'summary' in result

    @pytest.mark.asyncio
    async def test_ai_score_score_is_float(self):
        ai_response_json = '{"score": 4.0, "summary": "Acceptable security posture.", "concerns": []}'
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=ai_response_json)]

        mock_client = AsyncMock()
        mock_client.messages = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        engine = self._make_engine_with_mock_client(mock_client)
        result = await engine._ai_score_responses(self._MINIMAL_TEMPLATE, {'A.1': 'yes'})

        score = result['score']
        assert isinstance(score, (int, float)), f"score must be numeric, got {type(score)}"
        assert 0.0 <= float(score) <= 10.0, f"score {score} outside [0, 10]"
