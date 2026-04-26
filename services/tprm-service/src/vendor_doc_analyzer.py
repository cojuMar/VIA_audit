"""
Vendor Document Analyzer

Uses Claude Opus to analyze vendor-provided compliance documents:
- SOC 2 Type I/II reports
- ISO 27001 certificates
- PCI DSS Attestations of Compliance (AoC)
- Penetration test reports
- Privacy policies / DPAs

Extracts:
- Certification scope and validity dates
- Identified gaps or exceptions
- Overall security posture score (0–10, 10 = most secure)
- Summary of findings

Documents are stored in MinIO (aegis-vendor-docs bucket).
Analysis results stored in vendor_documents.ai_analysis JSONB.
"""
import logging
import hashlib
import io
from uuid import UUID
import anthropic
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


class VendorDocAnalyzer:
    def __init__(self, db_pool, minio_endpoint: str, minio_access_key: str,
                 minio_secret_key: str, bucket: str, anthropic_api_key: str = ""):
        self._pool = db_pool
        self._bucket = bucket
        self._client = anthropic.AsyncAnthropic(api_key=anthropic_api_key) if anthropic_api_key else None

        # MinIO client (dev graceful degradation)
        try:
            endpoint = minio_endpoint.replace('http://', '').replace('https://', '')
            secure = minio_endpoint.startswith('https://')
            self._minio = Minio(endpoint, access_key=minio_access_key,
                               secret_key=minio_secret_key, secure=secure)
        except Exception as e:
            logger.warning(f"MinIO client init failed (dev mode): {e}")
            self._minio = None

    async def upload_document(self, tenant_id: UUID, vendor_id: UUID,
                               document_type: str, filename: str,
                               content: bytes) -> UUID:
        """
        Upload document to MinIO and create DB record.
        Returns document_id.
        """
        checksum = hashlib.sha256(content).hexdigest()
        minio_path = f"vendor-docs/{str(tenant_id)[:8]}/{str(vendor_id)[:8]}/{document_type}/{filename}"

        # Upload to MinIO (fail gracefully in dev)
        if self._minio:
            try:
                self._minio.put_object(
                    self._bucket, minio_path,
                    io.BytesIO(content), len(content),
                    content_type="application/octet-stream"
                )
            except S3Error as e:
                logger.warning(f"MinIO upload failed (dev mode): {e}")
                minio_path = None
        else:
            minio_path = None

        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            doc_id = await conn.fetchval("""
                INSERT INTO vendor_documents
                    (tenant_id, vendor_id, document_type, filename, minio_path,
                     file_size_bytes, analysis_status)
                VALUES ($1, $2, $3, $4, $5, $6, 'pending')
                RETURNING id
            """, tenant_id, vendor_id, document_type, filename, minio_path, len(content))

        return doc_id

    async def analyze_document(self, tenant_id: UUID, document_id: UUID, content: bytes) -> dict:
        """
        Run AI analysis on document content.
        Updates vendor_documents.ai_analysis with results.
        """
        if not self._client:
            result = {
                "gaps": ["AI analysis unavailable — manual review required"],
                "score": 5.0,
                "summary": "Document uploaded. Manual review required.",
                "certifications_found": [],
                "expiry_date": None
            }
        else:
            result = await self._analyze_with_claude(content)

        import json
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            await conn.execute("""
                UPDATE vendor_documents SET
                    ai_analysis = $1::jsonb,
                    analysis_status = 'completed',
                    expiry_date = $2
                WHERE id = $3 AND tenant_id = $4
            """, json.dumps(result), result.get('expiry_date'), document_id, tenant_id)

        return result

    async def _analyze_with_claude(self, content: bytes) -> dict:
        """Send document content to Claude for analysis."""
        import re, json as json_mod
        # Take first 8000 chars of text content for analysis
        text_preview = content.decode('utf-8', errors='replace')[:8000]

        try:
            response = await self._client.messages.create(
                model="claude-opus-4-6",
                max_tokens=1000,
                temperature=0,
                messages=[{
                    "role": "user",
                    "content": f"""You are a compliance expert analyzing a vendor security document. Extract key information and output ONLY valid JSON:
{{
  "gaps": ["<gap or exception found>"],
  "score": <float 0-10 where 10=most secure>,
  "summary": "<3-4 sentence executive summary>",
  "certifications_found": ["<cert name and scope>"],
  "expiry_date": "<YYYY-MM-DD or null>"
}}

Document content (first 8000 chars):
{text_preview}"""
                }]
            )
            text = response.content[0].text.strip()
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json_mod.loads(match.group())
        except Exception as e:
            logger.error(f"Claude document analysis failed: {e}")

        return {
            "gaps": ["Analysis failed — manual review required"],
            "score": 5.0,
            "summary": "Document analysis encountered an error. Please review manually.",
            "certifications_found": [],
            "expiry_date": None
        }
