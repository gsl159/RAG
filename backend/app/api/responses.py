"""
Standardised API response envelope for all endpoints.

Every endpoint returns either ``ok(...)`` or ``err(...)`` so that
clients always receive a predictable JSON structure.
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def ok(
    data: Any = None,
    message: str = "success",
    trace_id: str = "",
) -> dict:
    """Return a standard success payload.

    The caller **returns** this dict so FastAPI serialises it to JSON
    automatically (status code 200).

    Example
    -------
    .. code-block:: python

        @router.get("/example")
        async def example():
            return ok({"key": "value"})
    """
    return {
        "code": 0,
        "message": message,
        "data": data,
        "trace_id": trace_id,
    }


def err(
    code: int,
    message: str,
    status_code: int = 400,
    trace_id: str = "",
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Return a standard error payload with an explicit HTTP status.

    Example
    -------
    .. code-block:: python

        raise HTTPException(
            status_code=404,
            detail=err(1005, "Resource not found"),
        )
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "data": None,
            "trace_id": trace_id,
            "details": details or {},
        },
    )
