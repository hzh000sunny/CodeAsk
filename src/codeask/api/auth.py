"""Bootstrap authentication endpoints."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from codeask.identity import create_admin_session_token

router = APIRouter()


class AuthMeResponse(BaseModel):
    subject_id: str
    display_name: str
    role: str
    authenticated: bool


class AdminLoginRequest(BaseModel):
    username: str = Field(default="admin", min_length=1)
    password: str = Field(..., min_length=1)


@router.get("/auth/me", response_model=AuthMeResponse)
async def get_me(request: Request) -> AuthMeResponse:
    return AuthMeResponse(
        subject_id=request.state.subject_id,
        display_name=request.state.display_name,
        role=request.state.role,
        authenticated=request.state.authenticated,
    )


@router.post("/auth/admin/login", response_model=AuthMeResponse)
async def login_admin(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
) -> AuthMeResponse:
    settings = request.app.state.settings
    if payload.username != settings.admin_username or payload.password != settings.admin_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    token = create_admin_session_token(settings.data_key, settings.admin_session_ttl_hours)
    max_age = settings.admin_session_ttl_hours * 60 * 60
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
    )
    return AuthMeResponse(
        subject_id="admin",
        display_name="Admin",
        role="admin",
        authenticated=True,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> Response:
    response.delete_cookie(request.app.state.settings.auth_cookie_name)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
