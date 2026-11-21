"""Status vocabularies.

These are plain string enums backed by ``VARCHAR + CHECK`` rather than a native
PostgreSQL ``ENUM`` type. Adding a value to a native enum requires an
``ALTER TYPE`` that cannot run inside a transaction on older servers; changing a
CHECK constraint is an ordinary, reversible migration.
"""

from enum import StrEnum


class TenantStatus(StrEnum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"


class JobOrderStatus(StrEnum):
    OPEN = "Open"
    CLOSED = "Closed"


class SubmissionStatus(StrEnum):
    """Only ``SHORTLISTED`` is written today.

    The assignment's Submission List asks to show "at what stage they are", so
    the column is modelled as a lifecycle from the start; later stages are a
    data change, not a schema change.
    """

    SHORTLISTED = "Shortlisted"
    SUBMITTED = "Submitted"
    INTERVIEWING = "Interviewing"
    OFFERED = "Offered"
    PLACED = "Placed"
    REJECTED = "Rejected"


def values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]
