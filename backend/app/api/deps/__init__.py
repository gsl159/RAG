"""
API-layer dependency wiring — re-exports all cross-cutting concerns.

Usage
-----
.. code-block:: python

    from app.api.deps import (
        get_container,
        get_current_user,
        require_role,
        check_rate_limit,
    )
"""

from app.api.deps.auth import (
    get_current_user,
    require_role,
    create_access_token,
    verify_token,
    verify_api_key,
    get_password_hash,
    verify_password,
)
from app.api.deps.rate_limit import (
    check_rate_limit_dep as check_rate_limit,
    check_login_rate_limit_dep as check_login_rate_limit,
)
from app.api.deps.container import get_container

__all__ = [
    "get_container",
    "get_current_user",
    "require_role",
    "create_access_token",
    "verify_token",
    "verify_api_key",
    "get_password_hash",
    "verify_password",
    "check_rate_limit",
    "check_login_rate_limit",
]
