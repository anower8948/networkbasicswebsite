"""Course completion certificates.

A certificate carries two identifiers, and the distinction matters:

* **`serial`** is internal and sequential-looking (`NLP-2026-0001`). It reads
  like a document number and appears on the certificate itself.
* **`verification_code`** is a high-entropy random token. It is the only thing a
  stranger needs to check the certificate, and being unguessable is what stops
  someone enumerating every certificate the platform has ever issued.

Verification is **public and deliberately thin**: it answers "is this real, who
holds it, and for what", and nothing else. A verification endpoint that returned
an email address would turn a CV line into a data leak.
"""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.enums import EnrollmentStatus
from app.models.gamification import Certificate
from app.models.user import User
from app.repositories.catalog import CourseRepository
from app.repositories.gamification import CertificateRepository
from app.repositories.learning import EnrollmentRepository
from app.schemas.gamification import CertificateRead, CertificateVerification

logger = get_logger(__name__)

# 32 hex characters — enough that guessing is hopeless, short enough to paste.
VERIFICATION_CODE_BYTES = 16


class CourseNotCompleted(ValidationError):
    code = "course_not_completed"
    message = "Finish the course before claiming its certificate."


class CertificateService:
    """Issues, lists, and verifies certificates."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.certificates = CertificateRepository(session)
        self.courses = CourseRepository(session)
        self.enrollments = EnrollmentRepository(session)

    async def issue(self, user: User, course_slug: str) -> CertificateRead:
        """Issue the certificate for a completed course, or return the existing one.

        Idempotent by design: the unique constraint on `(user_id, course_id)`
        makes a double-click impossible to turn into two certificates, and
        returning the existing row is friendlier than a 409.
        """
        course = await self.courses.get_by_slug(course_slug)
        if course is None:
            raise NotFoundError("Course not found.")
        if not course.grants_certificate:
            raise ValidationError("This course does not award a certificate.")

        existing = await self.certificates.get_for_user_course(user.id, course.id)
        if existing is not None:
            return self._read(existing, course.title)

        enrollment = await self.enrollments.get_for_user_course(user.id, course.id)
        if enrollment is None or enrollment.status is not EnrollmentStatus.COMPLETED:
            raise CourseNotCompleted()

        certificate = Certificate(
            user_id=user.id,
            course_id=course.id,
            serial=await self._next_serial(),
            verification_code=secrets.token_hex(VERIFICATION_CODE_BYTES),
            # Captured at issue time on purpose: a certificate should not
            # silently change the name on it when the holder edits their
            # profile two years later.
            recipient_name=user.full_name or user.username,
            final_score=int(enrollment.progress_percent),
        )
        self.certificates.add(certificate)
        await self.session.commit()

        logger.info(
            "Certificate issued",
            extra={"user_id": str(user.id), "course": course.slug, "serial": certificate.serial},
        )
        return self._read(certificate, course.title)

    async def list_for_user(self, user: User) -> list[CertificateRead]:
        certificates = await self.certificates.list_for_user(user.id)
        return [self._read(item, item.course.title) for item in certificates]

    async def verify(self, code: str) -> CertificateVerification:
        """The public check. Never raises for a bad code — it answers `valid: false`.

        A 404 here would let someone distinguish "wrong code" from "revoked
        certificate", and there is no reason to tell them apart.
        """
        certificate = await self.certificates.get_by_verification_code(code.strip())
        if certificate is None:
            return CertificateVerification(valid=False)

        return CertificateVerification(
            valid=certificate.revoked_at is None,
            recipient_name=certificate.recipient_name,
            course_title=certificate.course.title,
            issued_at=certificate.issued_at,
            revoked=certificate.revoked_at is not None,
        )

    async def revoke(self, certificate_id: uuid.UUID) -> CertificateRead:
        """Admin action. Revoking keeps the row so the code still resolves —
        to `valid: false`, which is the useful answer."""
        certificate = await self.certificates.get(certificate_id)
        if certificate is None:
            raise NotFoundError("Certificate not found.")

        certificate.revoked_at = utcnow()
        await self.session.commit()

        course = await self.courses.get(certificate.course_id)
        return self._read(certificate, course.title if course else "")

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _next_serial(self) -> str:
        """A human-readable document number, unique by construction.

        The count is a *starting point*, not the identity: two concurrent
        issues would compute the same count, so the loop steps past a collision
        rather than trusting it. The unique index is still the final authority.
        """
        year = utcnow().year
        issued = await self.certificates.count()
        for offset in range(1, 100):
            candidate = f"NLP-{year}-{issued + offset:05d}"
            if not await self.certificates.serial_exists(candidate):
                return candidate
        # Unreachable in practice; a random suffix beats failing the issue.
        return f"NLP-{year}-{secrets.token_hex(4).upper()}"

    @staticmethod
    def _read(certificate: Certificate, course_title: str) -> CertificateRead:
        return CertificateRead(
            id=certificate.id,
            course_id=certificate.course_id,
            course_title=course_title,
            serial=certificate.serial,
            verification_code=certificate.verification_code,
            recipient_name=certificate.recipient_name,
            final_score=certificate.final_score,
            issued_at=certificate.issued_at,
            revoked_at=certificate.revoked_at,
        )


__all__ = ["CertificateService", "CourseNotCompleted"]
