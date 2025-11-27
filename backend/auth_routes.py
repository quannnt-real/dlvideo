"""
Authentication API Routes
Handles login, logout, user management, and session verification
"""

from fastapi import APIRouter, Request, HTTPException, Depends, Response
from pydantic import BaseModel, Field
from typing import Optional, List
import logging
from datetime import datetime

from auth import auth_manager
from auth_middleware import require_role

logger = logging.getLogger(__name__)

# Create auth router
auth_router = APIRouter(prefix="/api/auth", tags=["authentication"])

# Pydantic models
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)

class LoginResponse(BaseModel):
    success: bool
    session_token: Optional[str] = None
    username: Optional[str] = None
    role: Optional[str] = None
    must_change_password: Optional[bool] = None
    expires_at: Optional[str] = None
    error: Optional[str] = None

class VerifyResponse(BaseModel):
    authenticated: bool
    username: Optional[str] = None
    role: Optional[str] = None
    expires_at: Optional[str] = None

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    role: str = Field(..., pattern="^(admin|user)$")

class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=6)

class UserInfo(BaseModel):
    username: str
    role: str
    created_at: str
    last_login: Optional[str]
    is_locked: bool


# ===== PUBLIC ENDPOINTS =====

@auth_router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, response: Response, http_request: Request):
    """
    Login endpoint - Public
    Returns session token on success
    """
    logger.info(f"🔐 Login attempt for user: {request.username}")

    # Get client IP for logging
    client_ip = http_request.client.host

    # Attempt login
    result = auth_manager.login(request.username, request.password)

    if result["success"]:
        # Set session cookie (HttpOnly for security)
        response.set_cookie(
            key="session_token",
            value=result["session_token"],
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
            max_age=24 * 60 * 60  # 24 hours
        )

        # Update session with IP
        if result["session_token"] in auth_manager.data["sessions"]:
            auth_manager.data["sessions"][result["session_token"]]["ip_address"] = client_ip
            auth_manager._save_data()

        logger.info(f"✅ Login successful: {request.username} from {client_ip}")

        return LoginResponse(
            success=True,
            session_token=result["session_token"],
            username=result["username"],
            role=result["role"],
            must_change_password=result.get("must_change_password", False),
            expires_at=result["expires_at"]
        )
    else:
        logger.warning(f"❌ Login failed for {request.username}: {result['error']}")
        return LoginResponse(
            success=False,
            error=result["error"]
        )


@auth_router.get("/verify", response_model=VerifyResponse)
async def verify_session(request: Request):
    """
    Verify session token - Public
    Can be called to check if user is logged in
    """
    # Get session token from header or cookie
    session_token = request.headers.get("Authorization")
    if session_token and session_token.startswith("Bearer "):
        session_token = session_token.replace("Bearer ", "")

    if not session_token:
        session_token = request.cookies.get("session_token")

    if not session_token:
        return VerifyResponse(authenticated=False)

    # Verify session
    user_info = auth_manager.verify_session(session_token)

    if user_info:
        return VerifyResponse(
            authenticated=True,
            username=user_info["username"],
            role=user_info["role"],
            expires_at=user_info["expires_at"]
        )
    else:
        return VerifyResponse(authenticated=False)


# ===== PROTECTED ENDPOINTS =====

@auth_router.post("/logout")
async def logout(request: Request, response: Response):
    """
    Logout endpoint - Protected
    Invalidates session token
    """
    session_token = getattr(request.state, "session_token", None)

    if session_token:
        auth_manager.logout(session_token)
        response.delete_cookie("session_token")
        logger.info("👋 User logged out")
        return {"success": True, "message": "Logged out successfully"}

    return {"success": False, "error": "No active session"}


@auth_router.post("/change-password")
async def change_password(request_body: ChangePasswordRequest, http_request: Request):
    """
    Change password endpoint - Protected
    User must be logged in
    """
    user_info = getattr(http_request.state, "user", None)
    if not user_info:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = auth_manager.change_password(
        user_info["username"],
        request_body.old_password,
        request_body.new_password
    )

    if result["success"]:
        logger.info(f"✅ Password changed for {user_info['username']}")
        return result
    else:
        logger.warning(f"❌ Password change failed for {user_info['username']}: {result['error']}")
        raise HTTPException(status_code=400, detail=result["error"])


@auth_router.get("/me")
async def get_current_user(request: Request):
    """
    Get current user info - Protected
    """
    user_info = getattr(request.state, "user", None)
    if not user_info:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return {
        "username": user_info["username"],
        "role": user_info["role"],
        "expires_at": user_info["expires_at"]
    }


# ===== ADMIN ONLY ENDPOINTS =====

@auth_router.post("/users", dependencies=[Depends(require_role(["admin"]))])
async def create_user(request_body: CreateUserRequest, http_request: Request):
    """
    Create new user - Admin only
    """
    admin_user = getattr(http_request.state, "user", None)
    logger.info(f"➕ Admin {admin_user['username']} creating user: {request_body.username} (role: {request_body.role})")

    result = auth_manager.create_user(
        request_body.username,
        request_body.password,
        request_body.role
    )

    if result["success"]:
        logger.info(f"✅ User created by admin {admin_user['username']}: {request_body.username}")
        return result
    else:
        logger.warning(f"❌ User creation failed: {result['error']}")
        raise HTTPException(status_code=400, detail=result["error"])


@auth_router.get("/users", response_model=List[UserInfo], dependencies=[Depends(require_role(["admin"]))])
async def get_all_users(request: Request):
    """
    Get all users - Admin only
    """
    admin_user = getattr(request.state, "user", None)
    logger.info(f"📋 Admin {admin_user['username']} requested user list")
    users = auth_manager.get_all_users()
    logger.info(f"📋 Returning {len(users)} users")
    return users


@auth_router.delete("/users/{username}", dependencies=[Depends(require_role(["admin"]))])
async def delete_user(username: str, request: Request):
    """
    Delete user - Admin only
    """
    admin_user = getattr(request.state, "user", None)

    result = auth_manager.delete_user(username, admin_user["username"])

    if result["success"]:
        logger.info(f"✅ User deleted by admin {admin_user['username']}: {username}")
        return result
    else:
        logger.warning(f"❌ User deletion failed: {result['error']}")
        raise HTTPException(status_code=400, detail=result["error"])


@auth_router.post("/cleanup-sessions", dependencies=[Depends(require_role(["admin"]))])
async def cleanup_expired_sessions():
    """
    Manually trigger cleanup of expired sessions - Admin only
    """
    count = auth_manager.cleanup_expired_sessions()
    return {"success": True, "cleaned_sessions": count}


@auth_router.get("/sessions", dependencies=[Depends(require_role(["admin"]))])
async def get_active_sessions(request: Request):
    """
    Get all active sessions - Admin only
    """
    sessions = []
    now = datetime.now()

    for token, session in auth_manager.data["sessions"].items():
        expires_at = datetime.fromisoformat(session["expires_at"])
        if now < expires_at:  # Only show active sessions
            sessions.append({
                "username": session["username"],
                "role": session["role"],
                "created_at": session["created_at"],
                "expires_at": session["expires_at"],
                "ip_address": session.get("ip_address", "Unknown"),
                "token_preview": token[:20] + "..."  # Show first 20 chars only
            })

    return {"active_sessions": len(sessions), "sessions": sessions}


class ResetPasswordRequest(BaseModel):
    username: str = Field(..., min_length=3)
    new_password: str = Field(..., min_length=6)


@auth_router.post("/reset-password", dependencies=[Depends(require_role(["admin"]))])
async def reset_user_password(request_body: ResetPasswordRequest, http_request: Request):
    """
    Admin reset user password - Admin only
    """
    admin_user = getattr(http_request.state, "user", None)
    current_session_token = getattr(http_request.state, "session_token", None)

    result = auth_manager.reset_user_password(
        request_body.username,
        request_body.new_password,
        admin_user["username"],
        current_session_token  # Pass current session token to preserve it if self-reset
    )

    if result["success"]:
        logger.info(f"✅ Password reset by admin {admin_user['username']} for user: {request_body.username}")
        return result
    else:
        logger.warning(f"❌ Password reset failed: {result['error']}")
        raise HTTPException(status_code=400, detail=result["error"])


class UpdateUsernameRequest(BaseModel):
    old_username: str = Field(..., min_length=3)
    new_username: str = Field(..., min_length=3)


@auth_router.post("/update-username", dependencies=[Depends(require_role(["admin"]))])
async def update_username(request_body: UpdateUsernameRequest, http_request: Request):
    """
    Admin change username - Admin only
    """
    admin_user = getattr(http_request.state, "user", None)

    result = auth_manager.update_username(
        request_body.old_username,
        request_body.new_username,
        admin_user["username"]
    )

    if result["success"]:
        logger.info(f"✅ Username updated by admin {admin_user['username']}: {request_body.old_username} → {request_body.new_username}")
        return result
    else:
        logger.warning(f"❌ Username update failed: {result['error']}")
        raise HTTPException(status_code=400, detail=result["error"])


@auth_router.delete("/sessions/{username}", dependencies=[Depends(require_role(["admin"]))])
async def delete_user_sessions(username: str, request: Request):
    """
    Admin delete all sessions for a specific user - Admin only
    """
    admin_user = getattr(request.state, "user", None)

    result = auth_manager.delete_user_sessions(username, admin_user["username"])

    if result["success"]:
        logger.info(f"✅ Sessions deleted by admin {admin_user['username']} for user: {username}")
        return result
    else:
        logger.warning(f"❌ Session deletion failed: {result['error']}")
        raise HTTPException(status_code=400, detail=result["error"])
