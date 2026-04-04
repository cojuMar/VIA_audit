import asyncio
import logging
from typing import List, Optional
import voyageai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from .config import settings

logger = logging.getLogger(__name__)

MAX_VOYAGE_TOKENS = 4000
VOYAGE_BATCH_SIZE = 128


def _truncate_to_tokens(text: str, max_tokens: int = MAX_VOYAGE_TOKENS) -> str:
    """Truncate text at word boundary to approximate token limit.
    Voyage-law-2 uses ~4 chars per token on average for legal text."""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    # Truncate at last word boundary before max_chars
    truncated = text[:max_chars]
    last_space = truncated.rfind(' ')
    return truncated[:last_space] if last_space > 0 else truncated


class EvidenceEmbedder:
    """Embeds evidence record text using Voyage AI voyage-law-2 model.

    Voyage-law-2 is optimised for legal/compliance text retrieval — significantly
    outperforms general-purpose models on regulatory document similarity tasks.
    """

    def __init__(self):
        self._client = voyageai.AsyncClient(api_key=settings.voyage_api_key)
        self._model = settings.embedding_model

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        before_sleep=lambda rs: logger.warning(
            "Voyage API retry %d/5: %s", rs.attempt_number, rs.outcome.exception()
        ),
    )
    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a single batch. Called with retry logic."""
        truncated = [_truncate_to_tokens(t) for t in texts]
        result = await self._client.embed(
            truncated,
            model=self._model,
            input_type="document",
        )
        return result.embeddings

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts, batching to respect Voyage rate limits."""
        if not texts:
            return []

        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), VOYAGE_BATCH_SIZE):
            batch = texts[i:i + VOYAGE_BATCH_SIZE]
            embeddings = await self._embed_batch(batch)
            all_embeddings.extend(embeddings)
            if i + VOYAGE_BATCH_SIZE < len(texts):
                await asyncio.sleep(0.1)  # gentle rate limit respect

        return all_embeddings

    async def embed_query(self, query_text: str) -> List[float]:
        """Embed a single query string for retrieval (input_type='query')."""
        truncated = _truncate_to_tokens(query_text)
        result = await self._client.embed(
            [truncated],
            model=self._model,
            input_type="query",
        )
        return result.embeddings[0]

    def evidence_record_to_text(self, canonical_payload: dict, metadata: Optional[dict] = None) -> str:
        """Convert a canonical evidence record to embeddable text.

        Constructs a structured text representation that preserves the audit
        trail semantics while being semantically rich for embedding.
        Note: amounts are excluded — they live in metadata as ZK private inputs.
        """
        parts = []

        event_type = canonical_payload.get('event_type', 'unknown')
        entity_type = canonical_payload.get('entity_type', 'unknown')
        entity_id = canonical_payload.get('entity_id', 'unknown')
        outcome = canonical_payload.get('outcome', 'unknown')
        timestamp = canonical_payload.get('timestamp_utc', '')
        actor = canonical_payload.get('actor_id', 'system')
        resource = canonical_payload.get('resource', '')

        parts.append(f"Event: {event_type}")
        parts.append(f"Entity: {entity_type} ({entity_id})")
        parts.append(f"Actor: {actor}")
        parts.append(f"Outcome: {outcome}")
        parts.append(f"Timestamp: {timestamp}")

        if resource:
            parts.append(f"Resource: {resource}")

        # Include non-sensitive metadata fields (exclude amount — ZK private input)
        if metadata:
            safe_meta = {k: v for k, v in metadata.items()
                        if k not in ('amount', 'balance', 'credit', 'debit')}
            if safe_meta:
                meta_str = '; '.join(f"{k}={v}" for k, v in safe_meta.items())
                parts.append(f"Context: {meta_str}")

        return '\n'.join(parts)
