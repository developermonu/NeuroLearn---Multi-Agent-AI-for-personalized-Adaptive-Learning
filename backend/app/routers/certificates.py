import uuid
import json
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.models.course import Enrollment, Exam
from app.models.quiz import Certificate, QuizSession
from app.models.learning_path import LearningPath
from app.services.auth_service import get_current_user
from app.services.certificate_service import certificate_service

router = APIRouter()


@router.post("/generate/{enrollment_id}", status_code=201)
async def generate_certificate(enrollment_id: str, db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(get_current_user)):
    enrollment_result = await db.execute(
        select(Enrollment).where(Enrollment.id == enrollment_id, Enrollment.user_id == current_user.id)
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    # Check if already has certificate
    existing = await db.execute(
        select(Certificate).where(Certificate.enrollment_id == enrollment_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Certificate already generated")

    # Get exam info
    exam_result = await db.execute(select(Exam).where(Exam.id == enrollment.exam_id))
    exam = exam_result.scalar_one_or_none()

    # Calculate final score from quiz sessions
    sessions_result = await db.execute(
        select(QuizSession).where(
            QuizSession.enrollment_id == enrollment_id,
            QuizSession.status == "completed"
        )
    )
    sessions = sessions_result.scalars().all()

    if not sessions:
        raise HTTPException(status_code=400, detail="No completed assessments found")

    # Get mock exam scores if available, otherwise average all scores
    mock_sessions = [s for s in sessions if s.quiz_type == "mock"]
    if mock_sessions:
        final_score = sum(s.score_pct for s in mock_sessions) / len(mock_sessions)
    else:
        final_score = sum(s.score_pct or 0 for s in sessions) / len(sessions)

    # Determine grade
    if final_score >= 90:
        grade = "Distinction"
    elif final_score >= 80:
        grade = "Merit"
    elif final_score >= 70:
        grade = "Credit"
    elif final_score >= 60:
        grade = "Pass"
    else:
        grade = "Attempted"

    # Generate verification code
    verification_code = hashlib.sha256(
        f"{enrollment_id}-{current_user.id}-{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()[:32]

    issued_at = datetime.now(timezone.utc)
    exam_name = exam.name if exam else "Unknown Exam"

    # Build W3C Verifiable Credential with real Ed25519 signing
    vc_json = certificate_service.build_vc(
        student_name=current_user.full_name,
        exam_name=exam_name,
        final_score=round(final_score, 1),
        grade=grade,
        verification_code=verification_code,
        issued_at=issued_at
    )

    # Generate PDF certificate
    pdf_bytes = certificate_service.generate_pdf(
        student_name=current_user.full_name,
        exam_name=exam_name,
        final_score=round(final_score, 1),
        grade=grade,
        verification_code=verification_code,
        issued_at=issued_at,
        verify_url=f"https://neurolearn.edu/verify/{verification_code}"
    )

    # Save PDF to local storage
    import os
    pdf_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "certificates")
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_filename = f"cert_{verification_code}.pdf"
    pdf_path = os.path.join(pdf_dir, pdf_filename)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    # Create certificate record
    certificate = Certificate(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        enrollment_id=enrollment_id,
        exam_name=exam_name,
        student_name=current_user.full_name,
        final_score=round(final_score, 1),
        grade=grade,
        pdf_url=f"/api/v1/certificates/download/{verification_code}",
        vc_json=json.dumps(vc_json),
        verification_code=verification_code,
        issued_at=issued_at
    )
    db.add(certificate)

    # Update enrollment status
    enrollment.status = "completed"

    await db.flush()

    return {
        "id": certificate.id,
        "exam_name": certificate.exam_name,
        "student_name": certificate.student_name,
        "final_score": certificate.final_score,
        "grade": certificate.grade,
        "verification_code": certificate.verification_code,
        "pdf_url": certificate.pdf_url,
        "vc_json": vc_json,
        "issued_at": certificate.issued_at.isoformat()
    }


@router.get("/download/{verification_code}")
async def download_certificate(verification_code: str, db: AsyncSession = Depends(get_db)):
    """Download the PDF certificate."""
    result = await db.execute(
        select(Certificate).where(Certificate.verification_code == verification_code)
    )
    cert = result.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")

    import os, io
    pdf_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "certificates")
    pdf_path = os.path.join(pdf_dir, f"cert_{verification_code}.pdf")

    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
    else:
        # Regenerate on the fly
        pdf_bytes = certificate_service.generate_pdf(
            student_name=cert.student_name,
            exam_name=cert.exam_name,
            final_score=cert.final_score,
            grade=cert.grade,
            verification_code=cert.verification_code,
            issued_at=cert.issued_at or datetime.now(timezone.utc),
            verify_url=f"https://neurolearn.edu/verify/{verification_code}"
        )

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="NeuroLearn_Certificate_{verification_code[:8]}.pdf"'}
    )


@router.get("/my")
async def my_certificates(db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Certificate).where(Certificate.user_id == current_user.id)
        .order_by(Certificate.issued_at.desc())
    )
    certs = result.scalars().all()
    return [{
        "id": c.id,
        "exam_name": c.exam_name,
        "student_name": c.student_name,
        "final_score": c.final_score,
        "grade": c.grade,
        "verification_code": c.verification_code,
        "pdf_url": c.pdf_url,
        "issued_at": c.issued_at.isoformat() if c.issued_at else None,
    } for c in certs]


@router.get("/verify/{verification_code}")
async def verify_certificate(verification_code: str, db: AsyncSession = Depends(get_db)):
    """Verify certificate authenticity using Ed25519 signature."""
    result = await db.execute(
        select(Certificate).where(Certificate.verification_code == verification_code)
    )
    cert = result.scalar_one_or_none()

    if not cert:
        return {"valid": False, "message": "Certificate not found"}

    # Cryptographic verification
    if cert.vc_json:
        verification_result = certificate_service.verify_vc(cert.vc_json)
        return {
            **verification_result,
            "student_name": cert.student_name,
            "exam_name": cert.exam_name,
            "final_score": cert.final_score,
            "grade": cert.grade,
            "pdf_url": cert.pdf_url,
            "issued_at": cert.issued_at.isoformat() if cert.issued_at else None
        }

    return {
        "valid": True,
        "student_name": cert.student_name,
        "exam_name": cert.exam_name,
        "final_score": cert.final_score,
        "grade": cert.grade,
        "issued_at": cert.issued_at.isoformat() if cert.issued_at else None
    }


@router.get("/public-key")
async def get_public_key():
    """Return the Ed25519 public key for external verification."""
    return {
        "key_type": "Ed25519",
        "public_key_hex": certificate_service.get_public_key_hex(),
        "verification_method": "did:web:neurolearn.edu#key-1",
        "usage": "Use this public key to verify certificate signatures"
    }
