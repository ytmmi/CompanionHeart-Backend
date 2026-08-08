"""仅已认证 session 可调用的开发者全记忆网关。"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from app.developer import (
    DeveloperMemoryGateway,
    DeveloperMemoryQuery,
    DeveloperMemoryQueryResult,
    get_developer_auth,
)


router = APIRouter(prefix="/api/developer/memory", tags=["Developer"])
_gateway = DeveloperMemoryGateway()


def configure_developer_memory_gateway(gateway: DeveloperMemoryGateway) -> None:
    global _gateway
    _gateway = gateway


@router.post("/query", response_model=DeveloperMemoryQueryResult)
async def query_all_memory(
    body: DeveloperMemoryQuery,
    request: Request,
    x_developer_session_id: str | None = Header(None, alias="X-Developer-Session-Id"),
    x_companion_client_id: str = Header("local-desktop", alias="X-Companion-Client-Id"),
    x_companion_user_id: str = Header("local-default", alias="X-Companion-User-Id"),
) -> DeveloperMemoryQueryResult:
    session_id = x_developer_session_id or request.cookies.get(
        "companionheart_dev_session"
    )
    session = get_developer_auth().validate_session(
        session_id, client_id=x_companion_client_id
    )
    if session is None:
        raise HTTPException(status_code=403, detail="需要有效开发者会话")
    return await _gateway.query(
        developer_session_id=session.session_id,
        stable_user_id=x_companion_user_id,
        request=body,
    )
