"""CV upload validation.

Three independent checks, because any one of them alone is weak:

* **Extension** - what the user thinks they uploaded.
* **Magic bytes** - what the file actually is. A ``.pdf`` extension on a
  renamed executable fails here. This is why the MIME type we store is derived
  from the signature rather than copied from the client's ``Content-Type``,
  which is attacker-controlled and routinely wrong even when it is not.
* **Size** - checked against the already-read bytes, so a lying
  ``Content-Length`` cannot get past it.

The file is never executed, rendered or written to disk - it goes straight into
a ``BYTEA`` column - so this is about storing honest metadata and refusing
junk, not about sandboxing.
"""

from dataclasses import dataclass

from app.core.config import settings
from app.core.errors import ValidationError

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# Signature -> (extension, mime). DOCX is a ZIP container, hence the PK header.
_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"%PDF-", ".pdf", PDF_MIME),
    (b"PK\x03\x04", ".docx", DOCX_MIME),
]

ALLOWED_EXTENSIONS = {".pdf", ".docx"}


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    filename: str
    mime_type: str
    size_bytes: int
    content: bytes


def _extension_of(filename: str) -> str:
    _, dot, suffix = filename.rpartition(".")
    return f".{suffix.lower()}" if dot else ""


def validate_cv(filename: str | None, content: bytes) -> ValidatedUpload:
    """Validate an uploaded CV, or raise :class:`ValidationError`."""
    safe_name = (filename or "").strip()
    if not safe_name:
        raise ValidationError("The uploaded file has no filename.", {"field": "file"})

    extension = _extension_of(safe_name)
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            "Only .pdf and .docx CV files are accepted.",
            {"field": "file", "received_extension": extension or "(none)"},
        )

    if not content:
        raise ValidationError("The uploaded file is empty.", {"field": "file"})

    if len(content) > settings.max_cv_size_bytes:
        raise ValidationError(
            f"CV files may not exceed {settings.max_cv_size_mb} MB.",
            {
                "field": "file",
                "max_bytes": settings.max_cv_size_bytes,
                "received_bytes": len(content),
            },
        )

    detected = next(
        ((ext, mime) for signature, ext, mime in _SIGNATURES if content.startswith(signature)),
        None,
    )
    if detected is None:
        raise ValidationError(
            "The file contents are not a readable PDF or DOCX document.",
            {"field": "file"},
        )

    detected_extension, mime_type = detected
    if detected_extension != extension:
        raise ValidationError(
            f"The file is named '{extension}' but its contents are {detected_extension}.",
            {"field": "file", "named": extension, "detected": detected_extension},
        )

    # Strip any directory component a client may have sent along with the name.
    base_name = safe_name.replace("\\", "/").rsplit("/", 1)[-1][:255]

    return ValidatedUpload(
        filename=base_name,
        mime_type=mime_type,
        size_bytes=len(content),
        content=content,
    )
