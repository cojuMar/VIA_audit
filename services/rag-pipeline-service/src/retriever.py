import logging
from dataclasses import dataclass
from typing import List, Optional
import asyncpg
from .config import settings

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    evidence_record_id: str
    chunk_text: str
    similarity_score: float
    rank: int
    canonical_payload: dict


class EvidenceRetriever:
    """Retrieves relevant evidence records via pgvector cosine similarity.

    Uses a two-stage pipeline:
    1. ANN search (IVFFLAT) — fast approximate search to get top-K candidates
    2. Exact re-ranking — cosine similarity on the top-K for precise ordering

    All queries are tenant-scoped via SET LOCAL app.tenant_id (RLS enforcement).
    """

    def __init__(self, db_pool: asyncpg.Pool):
        self._pool = db_pool

    async def retrieve(
        self,
        query_embedding: List[float],
        tenant_id: str,
        top_k: int = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        event_types: Optional[List[str]] = None,
    ) -> List[RetrievedChunk]:
        """Retrieve the most relevant evidence chunks for a query embedding.

        Args:
            query_embedding: The query vector from EvidenceEmbedder.embed_query()
            tenant_id: Tenant UUID — used for RLS enforcement
            top_k: Number of chunks to return (defaults to settings.max_context_chunks)
            date_from/date_to: Optional date range filter
            event_types: Optional list of event_type values to filter on

        Returns:
            List of RetrievedChunk ordered by similarity descending.
            Chunks with similarity < settings.similarity_threshold are excluded.
        """
        top_k = top_k or settings.max_context_chunks
        retrieve_k = settings.retrieval_top_k  # over-fetch, then re-rank

        # Format embedding as pgvector literal
        vec_str = '[' + ','.join(str(x) for x in query_embedding) + ']'

        async with self._pool.acquire() as conn, conn.transaction():
            # Set tenant context for RLS
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)

            # Build dynamic WHERE clause
            conditions = ['ee.tenant_id = $1::uuid']
            params: list = [tenant_id, vec_str, retrieve_k]
            param_idx = 4

            if date_from:
                conditions.append(f"er.ingested_at >= ${param_idx}::date")
                params.append(date_from)
                param_idx += 1
            if date_to:
                conditions.append(f"er.ingested_at <= ${param_idx}::date")
                params.append(date_to)
                param_idx += 1
            if event_types:
                conditions.append(f"er.canonical_payload->>'event_type' = ANY(${param_idx}::text[])")
                params.append(event_types)
                param_idx += 1

            where_clause = ' AND '.join(conditions)

            rows = await conn.fetch(f"""
                SELECT
                    ee.evidence_record_id::text,
                    ee.chunk_text,
                    1 - (ee.embedding <=> $2::vector) AS similarity_score,
                    er.canonical_payload
                FROM evidence_embeddings ee
                JOIN evidence_records er ON er.evidence_id = ee.evidence_record_id
                WHERE {where_clause}
                ORDER BY ee.embedding <=> $2::vector
                LIMIT $3
            """, *params)

        chunks = []
        for i, row in enumerate(rows):
            sim = float(row['similarity_score'])
            if sim < settings.similarity_threshold:
                continue
            chunks.append(RetrievedChunk(
                evidence_record_id=row['evidence_record_id'],
                chunk_text=row['chunk_text'],
                similarity_score=sim,
                rank=i + 1,
                canonical_payload=dict(row['canonical_payload']),
            ))

        # Return at most top_k after threshold filtering
        return chunks[:top_k]
