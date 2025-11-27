"""
Authentication Middleware for FastAPI
Protects API endpoints and verifies user sessions
"""

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import logging

from auth import auth_manager

logger = logging.getLogger(__name__)

# Public endpoints that don't require authentication
# IMPORTANT: Be specific! Don't use broad paths like "/api/" that match everything
PUBLIC_ENDPOINTS = [
    "/",
    "/docs",
    "/openapi.json",
    "/redoc",
]

# Auth-specific public endpoints (exact match only)
PUBLIC_AUTH_ENDPOINTS = [
    "/api/auth/login",
    "/api/auth/verify",
]

class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to verify authentication for protected endpoints
    """

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path
        method = request.method

        # 🔍 DEBUG: Log all incoming requests
        logger.info(f"📥 Incoming request: {method} {path}")
        logger.info(f"   Headers: {dict(request.headers)}")
        logger.info(f"   Cookies: {dict(request.cookies)}")
        logger.info(f"   Origin: {request.headers.get('origin', 'N/A')}")

        # CRITICAL: Allow ALL OPTIONS requests (CORS preflight)
        # OPTIONS requests DO NOT include cookies, so they would always fail auth
        if method == "OPTIONS":
            logger.info(f"✅ OPTIONS preflight request, allowing: {path}")
            return await call_next(request)

        # Allow public endpoints
        if self._is_public_endpoint(path):
            logger.info(f"✅ Public endpoint, allowing: {path}")
            return await call_next(request)

        # Allow static files (downloads directory)
        if path.startswith("/downloads/"):
            logger.info(f"✅ Static file, allowing: {path}")
            return await call_next(request)

        # Check for session token in headers or cookies
        session_token = request.headers.get("Authorization")
        if session_token and session_token.startswith("Bearer "):
            session_token = session_token.replace("Bearer ", "")
            logger.info(f"🔑 Found session token in Authorization header")

        if not session_token:
            session_token = request.cookies.get("session_token")
            if session_token:
                logger.info(f"🔑 Found session token in cookies: {session_token[:16]}...")
            else:
                logger.warning(f"🔑 No session token found in cookies")

        if not session_token:
            logger.warning(f"🚫 UNAUTHORIZED: No session token for {path}")
            logger.warning(f"   Available cookies: {list(request.cookies.keys())}")
            logger.warning(f"   Authorization header: {request.headers.get('Authorization', 'N/A')}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Not authenticated. Please login first."}
            )

        # Verify session
        logger.info(f"🔍 Verifying session token: {session_token[:16]}...")
        user_info = auth_manager.verify_session(session_token)
        if not user_info:
            logger.warning(f"🚫 UNAUTHORIZED: Invalid/expired session token for {path}")
            logger.warning(f"   Token: {session_token[:32]}...")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid or expired session. Please login again."}
            )

        # Add user info to request state for use in endpoints
        request.state.user = user_info
        request.state.session_token = session_token

        logger.info(f"✅ AUTHENTICATED: {path} by {user_info['username']} (role: {user_info['role']})")

        return await call_next(request)

    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public"""
        # Exact match for root and docs
        if path in PUBLIC_ENDPOINTS:
            return True

        # Exact match for auth endpoints
        if path in PUBLIC_AUTH_ENDPOINTS:
            return True

        # Allow docs with trailing slash
        for public_path in PUBLIC_ENDPOINTS:
            if public_path != "/" and path.startswith(public_path + "/"):
                return True

        return False


def require_role(allowed_roles: list):
    """
    Dependency to check user role in endpoints
    Usage:
        @app.get("/admin/users", dependencies=[Depends(require_role(["admin"]))])
    """
    def check_role(request: Request):
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )

        if user["role"] not in allowed_roles:
            logger.warning(f"🚫 Access denied: {user['username']} (role: {user['role']}) tried to access admin endpoint")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(allowed_roles)}"
            )

        return user

    return check_role
