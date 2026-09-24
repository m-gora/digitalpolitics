from fastapi import HTTPException, Request, status

from dpp.auth.headers import Identity, parse_identity


async def get_identity(request: Request) -> Identity:
    """Read access is global for any authenticated user (arch-02): this
    dependency only checks that *some* identity is present.
    """
    identity = parse_identity(request)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing forward-auth headers (X-User-Id).",
        )
    return identity


def ensure_write_access(identity: Identity, district_id: object) -> None:
    """Write access is district-scoped (arch-02); raises 403 otherwise."""
    if not identity.has_write_access(district_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have write access to this district.",
        )
