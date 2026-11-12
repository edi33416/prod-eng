from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from bookshelf.auth.tokens import CurrentUser, decode_access_token

# auto_error=False: we raise our own 401 (with the WWW-Authenticate header
# RFC 6750 asks for) instead of relying on the library's default.
_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if credentials is None:
        raise _unauthorized("Not authenticated")
    try:
        return decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired") from None
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token") from None


def require_role(role: str) -> Callable[[CurrentUser], CurrentUser]:
    def checker(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if user.role != role:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker


AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]
