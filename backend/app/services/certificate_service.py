"""
Certificate Service: Ed25519 Signing, PDF Generation, QR Codes, W3C VCs.
"""
import json
import uuid
import hashlib
import logging
import io
import os
from datetime import datetime
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class CertificateService:
    """Handles W3C Verifiable Credential issuance with Ed25519 and PDF generation."""

    def __init__(self):
        self._private_key = None
        self._public_key = None
        self._initialized = False

    def _ensure_keys(self):
        """Load or generate Ed25519 key pair for VC signing."""
        if self._initialized:
            return
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives import serialization

            # Check if keys exist in environment/config
            from app.config import settings
            key_path = getattr(settings, 'ED25519_KEY_PATH', None)

            if key_path and os.path.exists(key_path):
                with open(key_path, "rb") as f:
                    self._private_key = serialization.load_pem_private_key(f.read(), password=None)
            else:
                # Generate a new key pair
                self._private_key = Ed25519PrivateKey.generate()
                logger.info("Generated new Ed25519 key pair for certificate signing")

                # Save keys if path is specified
                if key_path:
                    pem = self._private_key.private_bytes(
                        serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption()
                    )
                    os.makedirs(os.path.dirname(key_path), exist_ok=True)
                    with open(key_path, "wb") as f:
                        f.write(pem)

            self._public_key = self._private_key.public_key()
            self._initialized = True
        except ImportError:
            logger.warning("cryptography library not available. Using HMAC fallback for signing.")
            self._initialized = True
        except Exception as e:
            logger.error(f"Key initialization failed: {e}")
            self._initialized = True

    def get_public_key_hex(self) -> str:
        """Return the public key as hex string for verification."""
        self._ensure_keys()
        if self._public_key is None:
            return "fallback-no-ed25519"
        try:
            from cryptography.hazmat.primitives import serialization
            raw = self._public_key.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
            return raw.hex()
        except Exception:
            return "fallback-no-ed25519"

    def sign_payload(self, payload: str) -> str:
        """Sign a payload using Ed25519 private key. Returns hex signature."""
        self._ensure_keys()
        if self._private_key is None:
            # HMAC fallback
            from app.config import settings
            sig = hashlib.sha512((payload + settings.APP_SECRET_KEY).encode()).hexdigest()
            return sig
        try:
            signature = self._private_key.sign(payload.encode("utf-8"))
            return signature.hex()
        except Exception as e:
            logger.error(f"Signing failed: {e}")
            from app.config import settings
            return hashlib.sha512((payload + settings.APP_SECRET_KEY).encode()).hexdigest()

    def verify_signature(self, payload: str, signature_hex: str) -> bool:
        """Verify an Ed25519 signature. Returns True if valid."""
        self._ensure_keys()
        if self._public_key is None:
            # HMAC fallback verification
            from app.config import settings
            expected = hashlib.sha512((payload + settings.APP_SECRET_KEY).encode()).hexdigest()
            return signature_hex == expected
        try:
            sig_bytes = bytes.fromhex(signature_hex)
            self._public_key.verify(sig_bytes, payload.encode("utf-8"))
            return True
        except Exception:
            return False

    def build_vc(self, student_name: str, exam_name: str, final_score: float,
                 grade: str, verification_code: str, issued_at: datetime) -> Dict:
        """Build and sign a W3C Verifiable Credential (JSON-LD format)."""
        self._ensure_keys()

        vc = {
            "@context": [
                "https://www.w3.org/2018/credentials/v1",
                "https://www.w3.org/2018/credentials/examples/v1"
            ],
            "id": f"urn:uuid:{uuid.uuid4()}",
            "type": ["VerifiableCredential", "AcademicCertificate"],
            "issuer": {
                "id": "did:web:neurolearn.edu",
                "name": "NeuroLearn Adaptive Learning Platform"
            },
            "issuanceDate": issued_at.isoformat() + "Z",
            "credentialSubject": {
                "id": f"did:neurolearn:student:{verification_code}",
                "name": student_name,
                "achievement": {
                    "type": "ExamCompletion",
                    "exam": exam_name,
                    "score": final_score,
                    "grade": grade,
                    "completionDate": issued_at.strftime("%Y-%m-%d")
                }
            }
        }

        # Sign the credential
        canonical = json.dumps(vc, sort_keys=True, separators=(",", ":"))
        signature = self.sign_payload(canonical)

        vc["proof"] = {
            "type": "Ed25519Signature2020",
            "created": issued_at.isoformat() + "Z",
            "verificationMethod": f"did:web:neurolearn.edu#key-1",
            "proofPurpose": "assertionMethod",
            "proofValue": signature,
            "publicKeyHex": self.get_public_key_hex()
        }

        return vc

    def verify_vc(self, vc_json: str) -> Dict:
        """Verify a W3C Verifiable Credential's signature."""
        try:
            vc = json.loads(vc_json) if isinstance(vc_json, str) else vc_json
            proof = vc.pop("proof", None)
            if not proof:
                return {"valid": False, "reason": "No proof found in credential"}

            signature_hex = proof.get("proofValue", "")
            canonical = json.dumps(vc, sort_keys=True, separators=(",", ":"))

            is_valid = self.verify_signature(canonical, signature_hex)

            # Restore proof
            vc["proof"] = proof

            return {
                "valid": is_valid,
                "issuer": vc.get("issuer", {}).get("name", "Unknown"),
                "subject": vc.get("credentialSubject", {}).get("name", "Unknown"),
                "exam": vc.get("credentialSubject", {}).get("achievement", {}).get("exam", "Unknown"),
                "score": vc.get("credentialSubject", {}).get("achievement", {}).get("score", 0),
                "issued_at": vc.get("issuanceDate", ""),
                "signature_type": proof.get("type", "Unknown"),
            }
        except Exception as e:
            return {"valid": False, "reason": str(e)}

    def generate_pdf(self, student_name: str, exam_name: str, final_score: float,
                     grade: str, verification_code: str, issued_at: datetime,
                     verify_url: str = "") -> bytes:
        """Generate a styled PDF certificate with QR code."""
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.units import inch, cm
            from reportlab.lib.colors import HexColor
            from reportlab.pdfgen import canvas
            from reportlab.lib.utils import ImageReader

            buffer = io.BytesIO()
            page_w, page_h = landscape(A4)
            c = canvas.Canvas(buffer, pagesize=landscape(A4))

            # --- Background ---
            c.setFillColor(HexColor("#0f172a"))
            c.rect(0, 0, page_w, page_h, fill=True, stroke=False)

            # --- Border ---
            border_margin = 30
            c.setStrokeColor(HexColor("#6366f1"))
            c.setLineWidth(3)
            c.roundRect(border_margin, border_margin,
                        page_w - 2 * border_margin, page_h - 2 * border_margin,
                        radius=15, fill=False)

            # Inner border
            c.setStrokeColor(HexColor("#818cf830"))
            c.setLineWidth(1)
            c.roundRect(border_margin + 10, border_margin + 10,
                        page_w - 2 * (border_margin + 10), page_h - 2 * (border_margin + 10),
                        radius=10, fill=False)

            # --- Header ---
            c.setFillColor(HexColor("#a5b4fc"))
            c.setFont("Helvetica", 14)
            c.drawCentredString(page_w / 2, page_h - 80, "NEUROLEARN ADAPTIVE LEARNING PLATFORM")

            c.setFillColor(HexColor("#6366f1"))
            c.setFont("Helvetica-Bold", 36)
            c.drawCentredString(page_w / 2, page_h - 130, "CERTIFICATE OF COMPLETION")

            # --- Decorative line ---
            c.setStrokeColor(HexColor("#6366f1"))
            c.setLineWidth(2)
            c.line(page_w / 2 - 150, page_h - 145, page_w / 2 + 150, page_h - 145)

            # --- Content ---
            c.setFillColor(HexColor("#e2e8f0"))
            c.setFont("Helvetica", 14)
            c.drawCentredString(page_w / 2, page_h - 185, "This is to certify that")

            c.setFillColor(HexColor("#ffffff"))
            c.setFont("Helvetica-Bold", 28)
            c.drawCentredString(page_w / 2, page_h - 225, student_name)

            c.setFillColor(HexColor("#e2e8f0"))
            c.setFont("Helvetica", 14)
            c.drawCentredString(page_w / 2, page_h - 260, "has successfully completed the")

            c.setFillColor(HexColor("#a5b4fc"))
            c.setFont("Helvetica-Bold", 22)
            c.drawCentredString(page_w / 2, page_h - 295, exam_name)

            # --- Score & Grade ---
            c.setFillColor(HexColor("#e2e8f0"))
            c.setFont("Helvetica", 14)
            c.drawCentredString(page_w / 2, page_h - 340,
                                f"Final Score: {final_score:.1f}%  |  Grade: {grade}  |  Date: {issued_at.strftime('%B %d, %Y')}")

            # --- Verification code ---
            c.setFillColor(HexColor("#94a3b8"))
            c.setFont("Helvetica", 10)
            c.drawCentredString(page_w / 2, border_margin + 55,
                                f"Verification Code: {verification_code}")
            c.drawCentredString(page_w / 2, border_margin + 40,
                                "Verify at: neurolearn.edu/verify or scan QR code")

            # --- QR Code ---
            try:
                import qrcode
                qr_data = verify_url or f"https://neurolearn.edu/verify/{verification_code}"
                qr = qrcode.QRCode(version=1, box_size=4, border=1)
                qr.add_data(qr_data)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="#6366f1", back_color="#0f172a")
                qr_buffer = io.BytesIO()
                qr_img.save(qr_buffer, format="PNG")
                qr_buffer.seek(0)
                qr_reader = ImageReader(qr_buffer)
                qr_size = 80
                c.drawImage(qr_reader,
                            page_w - border_margin - qr_size - 30,
                            border_margin + 25,
                            width=qr_size, height=qr_size)
            except ImportError:
                logger.warning("qrcode library not available, skipping QR code generation")

            # --- Signature lines ---
            sig_y = border_margin + 90
            c.setStrokeColor(HexColor("#6366f1"))
            c.setLineWidth(1)

            # Left signature
            c.line(120, sig_y, 300, sig_y)
            c.setFillColor(HexColor("#94a3b8"))
            c.setFont("Helvetica", 9)
            c.drawCentredString(210, sig_y - 15, "Platform Director")

            # Right signature
            c.line(page_w - 300, sig_y, page_w - 120, sig_y)
            c.drawCentredString(page_w - 210, sig_y - 15, "Academic Verifier")

            # --- Footer ---
            c.setFillColor(HexColor("#64748b"))
            c.setFont("Helvetica", 7)
            c.drawCentredString(page_w / 2, border_margin + 15,
                                "This credential is cryptographically signed using Ed25519Signature2020 and conforms to W3C Verifiable Credentials standard.")

            c.save()
            return buffer.getvalue()

        except ImportError as e:
            logger.error(f"PDF generation dependencies missing: {e}")
            # Return a minimal text-based fallback
            return self._generate_text_certificate(student_name, exam_name, final_score, grade, verification_code, issued_at)

    def _generate_text_certificate(self, student_name, exam_name, final_score, grade, verification_code, issued_at) -> bytes:
        """Minimal text fallback if reportlab is not available."""
        text = f"""
=================================================================
              NEUROLEARN - CERTIFICATE OF COMPLETION
=================================================================

This is to certify that:

    {student_name}

has successfully completed:

    {exam_name}

Final Score: {final_score:.1f}%
Grade: {grade}
Date: {issued_at.strftime('%B %d, %Y')}
Verification Code: {verification_code}

=================================================================
        """
        return text.encode("utf-8")


# Module-level singleton
certificate_service = CertificateService()
