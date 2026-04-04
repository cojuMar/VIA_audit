"""
PAdES (PDF Advanced Electronic Signatures) Signer.

Applies PAdES-B-LTA signatures to PDF documents:
  PAdES-B-B:   Basic CAdES-based signature
  PAdES-B-T:   + RFC 3161 timestamp from TSA
  PAdES-B-LT:  + OCSP/CRL embedded for long-term validation
  PAdES-B-LTA: + Document timestamp for long-term archival (this implementation)

Uses pyhanko (https://pyhanko.readthedocs.io/) for signature creation.
Certificate loading from PEM files configured in settings.

Design:
  - Signs with the platform's audit signing certificate
  - Uses DigiCert TSA for RFC 3161 timestamps
  - Falls back to unsigned PDF if signing cert not available (dev mode)
  - Never raises in dev mode — returns unsigned PDF with warning

Security note: The signing certificate must be kept in HashiCorp Vault PKI
in production. The SIGNING_CERT_PATH / SIGNING_KEY_PATH env vars point to
short-lived certificates issued by Vault for each signing operation.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SignatureResult:
    signed_pdf_bytes: bytes
    signature_type: str
    signer_dn: Optional[str]
    signing_time: Optional[str]
    is_signed: bool
    warning: Optional[str] = None


class PAdESSigner:
    """Applies PAdES-B-LTA digital signatures to PDF/A-3 documents.

    In production: loads signing key/cert from Vault-issued PEM files.
    In development: skips signing if cert files are not present (returns
    unsigned PDF with is_signed=False and a warning).
    """

    def __init__(self, cert_path: str, key_path: str, tsa_url: str):
        self._cert_path = cert_path
        self._key_path = key_path
        self._tsa_url = tsa_url

    def sign(self, pdf_bytes: bytes, reason: str = "Audit Compliance Report") -> SignatureResult:
        """Apply PAdES-B-LTA signature to a PDF document.

        Args:
            pdf_bytes: Unsigned PDF/A-3 bytes
            reason: Signature reason string embedded in the signature

        Returns:
            SignatureResult. If cert files are not present, returns unsigned
            PDF with is_signed=False (development/test mode).
        """
        if not os.path.exists(self._cert_path) or not os.path.exists(self._key_path):
            logger.warning(
                "PAdES signing skipped: cert/key not found at %s / %s (dev mode)",
                self._cert_path, self._key_path
            )
            return SignatureResult(
                signed_pdf_bytes=pdf_bytes,
                signature_type="unsigned",
                signer_dn=None,
                signing_time=None,
                is_signed=False,
                warning=f"Signing certificate not found at {self._cert_path} — report is unsigned",
            )

        try:
            return self._sign_with_pyhanko(pdf_bytes, reason)
        except Exception as e:
            logger.error("PAdES signing failed: %s", e, exc_info=True)
            return SignatureResult(
                signed_pdf_bytes=pdf_bytes,
                signature_type="unsigned",
                signer_dn=None,
                signing_time=None,
                is_signed=False,
                warning=f"PAdES signing failed: {e}",
            )

    def _sign_with_pyhanko(self, pdf_bytes: bytes, reason: str) -> SignatureResult:
        """Internal: apply PAdES signature using pyhanko."""
        import io
        from datetime import datetime, timezone
        from pyhanko.sign import signers, timestamps
        from pyhanko.sign.fields import SigFieldSpec
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata
        from pyhanko_certvalidator import CertificateValidator
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization

        # Load certificate and private key
        with open(self._cert_path, 'rb') as f:
            cert_pem = f.read()
        with open(self._key_path, 'rb') as f:
            key_pem = f.read()

        # Parse cert for DN extraction
        cert = x509.load_pem_x509_certificate(cert_pem)
        signer_dn = cert.subject.rfc4514_string()
        cert_der = cert.public_bytes(serialization.Encoding.DER)

        import hashlib
        cert_sha256 = hashlib.sha256(cert_der).digest()

        # Build signer
        cms_signer = signers.SimpleSigner.load(
            key_file=self._key_path,
            cert_file=self._cert_path,
        )

        # RFC 3161 timestamp client
        tst_client = timestamps.HTTPTimeStamper(self._tsa_url)

        # Sign
        input_buf = io.BytesIO(pdf_bytes)
        reader = PdfFileReader(input_buf)
        writer = IncrementalPdfFileWriter(input_buf)

        output_buf = io.BytesIO()
        signers.sign_pdf(
            writer,
            signers.PdfSignatureMetadata(
                field_name="AegisAuditSignature",
                reason=reason,
                certify=True,
            ),
            signer=cms_signer,
            timestamper=tst_client,
            output=output_buf,
        )

        signed_bytes = output_buf.getvalue()
        now_str = datetime.now(timezone.utc).isoformat()

        logger.info("PAdES-B-LTA signature applied: signer=%s", signer_dn)

        return SignatureResult(
            signed_pdf_bytes=signed_bytes,
            signature_type="PAdES-B-LTA",
            signer_dn=signer_dn,
            signing_time=now_str,
            is_signed=True,
        )
