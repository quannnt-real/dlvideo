import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionToken, setSessionToken] = useState(null);

  // Check authentication status on mount
  useEffect(() => {
    verifySession();
  }, []);

  const verifySession = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/verify`, {
        credentials: 'include', // Include cookies
      });

      const data = await response.json();

      if (data.authenticated) {
        setUser({
          username: data.username,
          role: data.role,
          expiresAt: data.expires_at,
        });
      } else {
        setUser(null);
      }
    } catch (error) {
      console.error('Session verification failed:', error);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const login = async (username, password) => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include', // Include cookies
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();

      if (data.success) {
        setUser({
          username: data.username,
          role: data.role,
          expiresAt: data.expires_at,
        });
        setSessionToken(data.session_token);
        
        // Save token to localStorage for axios interceptor
        localStorage.setItem('session_token', data.session_token);

        return {
          success: true,
          mustChangePassword: data.must_change_password,
        };
      } else {
        return {
          success: false,
          error: data.error,
        };
      }
    } catch (error) {
      console.error('Login error:', error);
      return {
        success: false,
        error: 'Network error. Please try again.',
      };
    }
  };

  const logout = async () => {
    try {
      await fetch(`${BACKEND_URL}/api/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      });
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      setUser(null);
      setSessionToken(null);
      localStorage.removeItem('session_token');
    }
  };

  const changePassword = async (oldPassword, newPassword) => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/change-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        return { success: true };
      } else {
        return { success: false, error: data.detail || 'Password change failed' };
      }
    } catch (error) {
      console.error('Password change error:', error);
      return { success: false, error: 'Network error' };
    }
  };

  const value = {
    user,
    loading,
    sessionToken,
    login,
    logout,
    changePassword,
    verifySession,
    isAuthenticated: !!user,
    isAdmin: user?.role === 'admin',
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
