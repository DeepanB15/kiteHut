"""
Remediation Authorization Boundary.

KiteHut does not yet have a user authentication/authorization system: there is
no user model, no credential issuance, and no repository ownership data. Rather
than inventing a weak authentication scheme, remediation is gated by explicit
server-side configuration and fails closed:

- ``REMEDIATION_API_TOKEN``: a server-side approver secret. Requests must send
  ``Authorization: Bearer <token>``. When unset, remediation is disabled.
- ``REMEDIATION_ALLOWED_REPOSITORIES``: comma-separated absolute repository
  roots the server permits remediation against. When empty, remediation is
  disabled.

Both are trusted server configuration and can never be supplied or overridden
by a request body. This is a documented stopgap that must be replaced by real
identity plus per-repository authorization once the auth subsystem exists.
"""

import os
from pathlib import Path
import secrets
from typing import Optional

from fastapi import Header, HTTPException, status

from app.core.config import settings


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    """Extract a bearer token from an Authorization header value."""
    if not authorization:
        return None
    scheme, _, credentials = authorization.partition(" ")
    if scheme.strip().lower() != "bearer":
        return None
    token = credentials.strip()
    return token or None


def require_remediation_approver(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    """
    Authenticate the remediation approver using server-side configuration.

    Returns an opaque principal label. Raises 503 when the server has no
    approver configured (fail closed) and 401 for missing/invalid credentials.
    """
    configured = settings.remediation_token
    if configured is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Remediation is disabled: no server-side approver is configured. "
                "Set REMEDIATION_API_TOKEN and REMEDIATION_ALLOWED_REPOSITORIES."
            ),
        )

    provided = _bearer_token(authorization)
    if provided is None or not secrets.compare_digest(
        provided.encode("utf-8"), configured.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid remediation credentials are required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return "remediation-approver"


def authorize_remediation_repository(repository_path: str) -> Path:
    """
    Resolve ``repository_path`` and require it to be inside a server-authorized
    repository root.

    Symlinks are resolved before the check, so a path that resolves outside the
    allowlist is rejected. Raises 403 for unauthorized paths and 400 for an
    authorized-but-unusable path.
    """
    roots = settings.allowed_remediation_roots
    if not roots:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No repositories are authorized for remediation on this server.",
        )

    try:
        requested = Path(repository_path).resolve()
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Repository is not authorized for remediation.",
        )

    requested_key = os.path.normcase(str(requested))
    for root in roots:
        root_key = os.path.normcase(str(root))
        if requested_key == root_key or requested_key.startswith(root_key + os.sep):
            break
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Repository is not authorized for remediation.",
        )

    if not requested.exists() or not requested.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Repository path '{repository_path}' does not exist.",
        )

    return requested
