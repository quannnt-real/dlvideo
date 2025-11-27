"""
Authentication Module for DLVideo
Handles user authentication, session management, and security
"""

import json
import hashlib
import secrets
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# File paths
DATA_DIR = Path(__file__).parent / 'data'
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / 'users.json'

# Security settings
SESSION_EXPIRY_HOURS = 24  # Session expires after 24 hours
MAX_LOGIN_ATTEMPTS = 5      # Max failed login attempts before lockout
LOCKOUT_DURATION_MINUTES = 15  # Lockout duration after max attempts

class AuthManager:
    """
    Manages user authentication and sessions
    Features:
    - Secure password hashing (SHA-256 + salt)
    - Session token management
    - Rate limiting for login attempts
    - Account lockout protection
    """

    def __init__(self):
        self.data = self._load_data()
        self._init_default_admin()

    def _load_data(self) -> Dict:
        """Load user data from JSON file"""
        if USERS_FILE.exists():
            try:
                with open(USERS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading users.json: {e}")
                return {"users": {}, "sessions": {}}
        return {"users": {}, "sessions": {}}

    def _save_data(self):
        """Save user data to JSON file"""
        try:
            with open(USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            logger.info("✅ User data saved successfully")
        except Exception as e:
            logger.error(f"❌ Error saving users.json: {e}")

    def _hash_password(self, password: str, salt: str = None) -> tuple:
        """
        Hash password with SHA-256 + random salt
        Returns: (hashed_password, salt)
        """
        if salt is None:
            salt = secrets.token_hex(32)  # 64-character hex salt

        # Combine password and salt, then hash
        combined = f"{password}{salt}".encode('utf-8')
        hashed = hashlib.sha256(combined).hexdigest()

        return hashed, salt

    def _generate_session_token(self) -> str:
        """Generate secure random session token"""
        return secrets.token_urlsafe(64)

    def _init_default_admin(self):
        """Initialize default admin account if not exists"""
        if "admin" not in self.data["users"]:
            # Default admin password: admin123 (MUST be changed on first login)
            password_hash, salt = self._hash_password("admin123")

            self.data["users"]["admin"] = {
                "username": "admin",
                "password_hash": password_hash,
                "salt": salt,
                "role": "admin",
                "created_at": datetime.now().isoformat(),
                "must_change_password": True,
                "login_attempts": 0,
                "locked_until": None,
                "last_login": None
            }
            self._save_data()
            logger.info("🔐 Default admin account created (username: admin, password: admin123)")

    def create_user(self, username: str, password: str, role: str = "user") -> Dict[str, Any]:
        """
        Create new user (only admin can do this)
        role: 'admin' or 'user'
        """
        if username in self.data["users"]:
            return {"success": False, "error": "Username already exists"}

        if len(password) < 6:
            return {"success": False, "error": "Password must be at least 6 characters"}

        if role not in ["admin", "user"]:
            return {"success": False, "error": "Invalid role"}

        password_hash, salt = self._hash_password(password)

        self.data["users"][username] = {
            "username": username,
            "password_hash": password_hash,
            "salt": salt,
            "role": role,
            "created_at": datetime.now().isoformat(),
            "must_change_password": False,
            "login_attempts": 0,
            "locked_until": None,
            "last_login": None
        }

        self._save_data()
        logger.info(f"✅ User created: {username} (role: {role})")

        return {"success": True, "username": username, "role": role}

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate user and create session
        Returns session token if successful
        """
        # Check if user exists
        if username not in self.data["users"]:
            logger.warning(f"❌ Login failed: User '{username}' not found")
            return {"success": False, "error": "Invalid username or password"}

        user = self.data["users"][username]

        # Check if account is locked
        if user.get("locked_until"):
            locked_until = datetime.fromisoformat(user["locked_until"])
            if datetime.now() < locked_until:
                remaining = (locked_until - datetime.now()).seconds // 60
                logger.warning(f"🔒 Login failed: Account '{username}' is locked for {remaining} more minutes")
                return {
                    "success": False,
                    "error": f"Account is locked. Try again in {remaining} minutes."
                }
            else:
                # Unlock account
                user["locked_until"] = None
                user["login_attempts"] = 0

        # Verify password
        password_hash, _ = self._hash_password(password, user["salt"])

        if password_hash != user["password_hash"]:
            # Increment failed login attempts
            user["login_attempts"] += 1

            if user["login_attempts"] >= MAX_LOGIN_ATTEMPTS:
                # Lock account
                locked_until = datetime.now() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
                user["locked_until"] = locked_until.isoformat()
                self._save_data()

                logger.warning(f"🔒 Account '{username}' locked due to too many failed attempts")
                return {
                    "success": False,
                    "error": f"Too many failed attempts. Account locked for {LOCKOUT_DURATION_MINUTES} minutes."
                }

            self._save_data()
            remaining_attempts = MAX_LOGIN_ATTEMPTS - user["login_attempts"]
            logger.warning(f"❌ Login failed for '{username}': Invalid password ({remaining_attempts} attempts remaining)")

            return {
                "success": False,
                "error": f"Invalid username or password. {remaining_attempts} attempts remaining."
            }

        # Login successful - reset attempts
        user["login_attempts"] = 0
        user["locked_until"] = None
        user["last_login"] = datetime.now().isoformat()

        # 🧹 CLEANUP: Remove all old sessions for this user (keep only new one)
        sessions_to_remove = [
            token for token, session in self.data["sessions"].items()
            if session["username"] == username
        ]
        for token in sessions_to_remove:
            del self.data["sessions"][token]
            logger.info(f"🗑️ Removed old session for user '{username}'")

        # Generate session token
        session_token = self._generate_session_token()
        expires_at = datetime.now() + timedelta(hours=SESSION_EXPIRY_HOURS)

        # Store session
        self.data["sessions"][session_token] = {
            "username": username,
            "role": user["role"],
            "created_at": datetime.now().isoformat(),
            "expires_at": expires_at.isoformat(),
            "ip_address": None  # Will be set by endpoint
        }

        self._save_data()

        logger.info(f"✅ User '{username}' logged in successfully (role: {user['role']})")

        return {
            "success": True,
            "session_token": session_token,
            "username": username,
            "role": user["role"],
            "must_change_password": user.get("must_change_password", False),
            "expires_at": expires_at.isoformat()
        }

    def verify_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        """
        Verify if session token is valid
        Returns user info if valid, None otherwise
        """
        if session_token not in self.data["sessions"]:
            return None

        session = self.data["sessions"][session_token]

        # Check if session expired
        expires_at = datetime.fromisoformat(session["expires_at"])
        if datetime.now() > expires_at:
            # Clean up expired session
            del self.data["sessions"][session_token]
            self._save_data()
            logger.info(f"🕐 Session expired for user '{session['username']}'")
            return None

        return {
            "username": session["username"],
            "role": session["role"],
            "expires_at": session["expires_at"]
        }

    def logout(self, session_token: str) -> bool:
        """Logout user by removing session"""
        if session_token in self.data["sessions"]:
            username = self.data["sessions"][session_token]["username"]
            del self.data["sessions"][session_token]
            self._save_data()
            logger.info(f"👋 User '{username}' logged out")
            return True
        return False

    def change_password(self, username: str, old_password: str, new_password: str) -> Dict[str, Any]:
        """Change user password"""
        if username not in self.data["users"]:
            return {"success": False, "error": "User not found"}

        user = self.data["users"][username]

        # Verify old password
        old_hash, _ = self._hash_password(old_password, user["salt"])
        if old_hash != user["password_hash"]:
            return {"success": False, "error": "Current password is incorrect"}

        if len(new_password) < 6:
            return {"success": False, "error": "New password must be at least 6 characters"}

        # Set new password
        new_hash, new_salt = self._hash_password(new_password)
        user["password_hash"] = new_hash
        user["salt"] = new_salt
        user["must_change_password"] = False

        self._save_data()
        logger.info(f"✅ Password changed for user '{username}'")

        return {"success": True, "message": "Password changed successfully"}

    def get_all_users(self) -> list:
        """Get list of all users (admin only, without sensitive data)"""
        users = []
        for username, user_data in self.data["users"].items():
            users.append({
                "username": username,
                "role": user_data["role"],
                "created_at": user_data["created_at"],
                "last_login": user_data.get("last_login"),
                "is_locked": user_data.get("locked_until") is not None
            })
        return users

    def delete_user(self, username: str, requester_username: str) -> Dict[str, Any]:
        """Delete user (admin only, cannot delete self or last admin)"""
        if username not in self.data["users"]:
            return {"success": False, "error": "User not found"}

        if username == requester_username:
            return {"success": False, "error": "Cannot delete your own account"}

        # Count admins
        admin_count = sum(1 for u in self.data["users"].values() if u["role"] == "admin")
        if self.data["users"][username]["role"] == "admin" and admin_count <= 1:
            return {"success": False, "error": "Cannot delete the last admin account"}

        # Delete user and their sessions
        del self.data["users"][username]

        # Remove all sessions for this user
        sessions_to_remove = [
            token for token, session in self.data["sessions"].items()
            if session["username"] == username
        ]
        for token in sessions_to_remove:
            del self.data["sessions"][token]

        self._save_data()
        logger.info(f"🗑️ User '{username}' deleted by '{requester_username}'")

        return {"success": True, "message": f"User '{username}' deleted successfully"}

    def cleanup_expired_sessions(self):
        """Remove all expired sessions (run periodically)"""
        now = datetime.now()
        expired_tokens = []

        for token, session in self.data["sessions"].items():
            expires_at = datetime.fromisoformat(session["expires_at"])
            if now > expires_at:
                expired_tokens.append(token)

        for token in expired_tokens:
            del self.data["sessions"][token]

        if expired_tokens:
            self._save_data()
            logger.info(f"🧹 Cleaned up {len(expired_tokens)} expired sessions")

        return len(expired_tokens)

    def reset_user_password(self, username: str, new_password: str, admin_username: str, current_session_token: str = None) -> Dict[str, Any]:
        """Admin reset user password (no old password needed)"""
        if username not in self.data["users"]:
            return {"success": False, "error": "User not found"}

        if len(new_password) < 6:
            return {"success": False, "error": "New password must be at least 6 characters"}

        user = self.data["users"][username]

        # Set new password
        new_hash, new_salt = self._hash_password(new_password)
        user["password_hash"] = new_hash
        user["salt"] = new_salt
        user["must_change_password"] = False

        # Invalidate sessions for this user
        # SPECIAL CASE: If admin is resetting their own password, keep current session
        is_self_reset = (username == admin_username)

        sessions_to_remove = [
            token for token, session in self.data["sessions"].items()
            if session["username"] == username and
            not (is_self_reset and token == current_session_token)  # Keep current session if self-reset
        ]

        for token in sessions_to_remove:
            del self.data["sessions"][token]

        self._save_data()

        if is_self_reset and current_session_token:
            logger.info(f"✅ Admin '{admin_username}' reset own password (kept current session, removed {len(sessions_to_remove)} other sessions)")
            return {"success": True, "message": f"Password updated successfully."}
        else:
            logger.info(f"✅ Admin '{admin_username}' reset password for user '{username}' and invalidated {len(sessions_to_remove)} sessions")
            return {"success": True, "message": f"Password reset successfully. User must login again."}

    def update_username(self, old_username: str, new_username: str, admin_username: str) -> Dict[str, Any]:
        """Admin change username"""
        if old_username not in self.data["users"]:
            return {"success": False, "error": "User not found"}

        if new_username in self.data["users"]:
            return {"success": False, "error": "Username already exists"}

        if len(new_username) < 3:
            return {"success": False, "error": "Username must be at least 3 characters"}

        if old_username == admin_username:
            return {"success": False, "error": "Cannot change your own username"}

        # Move user data to new username
        self.data["users"][new_username] = self.data["users"][old_username]
        self.data["users"][new_username]["username"] = new_username
        del self.data["users"][old_username]

        # Update all sessions for this user
        for token, session in self.data["sessions"].items():
            if session["username"] == old_username:
                session["username"] = new_username

        self._save_data()
        logger.info(f"✅ Admin '{admin_username}' changed username '{old_username}' to '{new_username}'")

        return {"success": True, "message": f"Username changed from '{old_username}' to '{new_username}'"}

    def delete_user_sessions(self, username: str, admin_username: str) -> Dict[str, Any]:
        """Admin delete all sessions for a specific user"""
        if username not in self.data["users"]:
            return {"success": False, "error": "User not found"}

        sessions_to_remove = [
            token for token, session in self.data["sessions"].items()
            if session["username"] == username
        ]

        for token in sessions_to_remove:
            del self.data["sessions"][token]

        self._save_data()
        logger.info(f"🗑️ Admin '{admin_username}' deleted {len(sessions_to_remove)} sessions for user '{username}'")

        return {"success": True, "message": f"Deleted {len(sessions_to_remove)} sessions for user '{username}'"}


# Global instance
auth_manager = AuthManager()
