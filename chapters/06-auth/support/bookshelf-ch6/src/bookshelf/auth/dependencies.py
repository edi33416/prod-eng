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
    # TODO(ch6): No credentials -> 401 "Not authenticated". Decode the token:
    # expired -> 401 "Token expired", invalid -> 401 "Invalid token".
    # Every 401 carries the header WWW-Authenticate: Bearer (_unauthorized).
    raise NotImplementedError


def require_role(role: str) -> Callable[[CurrentUser], CurrentUser]:
    def checker(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        # TODO(ch6): 403 "Insufficient permissions" unless user.role == role.
        raise NotImplementedError

    return checker


AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]
