import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import './LoginPage.css';

function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [loginAttempts, setLoginAttempts] = useState(0);
  const [captchaAnswer, setCaptchaAnswer] = useState('');
  const [captchaQuestion, setCaptchaQuestion] = useState({ question: '', answer: 0 });

  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/');
    }
  }, [isAuthenticated, navigate]);

  // Generate simple math CAPTCHA after 2 failed attempts
  useEffect(() => {
    if (loginAttempts >= 2) {
      generateCaptcha();
    }
  }, [loginAttempts]);

  const generateCaptcha = () => {
    const num1 = Math.floor(Math.random() * 10) + 1;
    const num2 = Math.floor(Math.random() * 10) + 1;
    setCaptchaQuestion({
      question: `${num1} + ${num2}`,
      answer: num1 + num2,
    });
    setCaptchaAnswer('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    // Validate inputs
    if (!username || !password) {
      setError('Vui lòng nhập đầy đủ thông tin');
      return;
    }

    // Validate CAPTCHA if required
    if (loginAttempts >= 2) {
      if (parseInt(captchaAnswer) !== captchaQuestion.answer) {
        setError('CAPTCHA không đúng, vui lòng thử lại');
        generateCaptcha();
        return;
      }
    }

    setLoading(true);

    try {
      const result = await login(username, password);

      if (result.success) {
        // Login successful
        if (result.mustChangePassword) {
          navigate('/change-password');
        } else {
          navigate('/');
        }
      } else {
        // Login failed
        setError(result.error || 'Đăng nhập thất bại');
        setLoginAttempts((prev) => prev + 1);
        setPassword('');
      }
    } catch (err) {
      setError('Lỗi kết nối. Vui lòng thử lại.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-header">
          <h1>🔐 System Access</h1>
          <p>Authorized Users Only</p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">Tên đăng nhập</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Nhập tên đăng nhập"
              disabled={loading}
              autoComplete="username"
              autoFocus
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Mật khẩu</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Nhập mật khẩu"
              disabled={loading}
              autoComplete="current-password"
            />
          </div>

          {/* CAPTCHA - Only show after 2 failed attempts */}
          {loginAttempts >= 2 && (
            <div className="form-group captcha-group">
              <label htmlFor="captcha">
                Bảo mật: {captchaQuestion.question} = ?
              </label>
              <input
                id="captcha"
                type="number"
                value={captchaAnswer}
                onChange={(e) => setCaptchaAnswer(e.target.value)}
                placeholder="Nhập kết quả"
                disabled={loading}
                required
              />
              <small className="captcha-hint">
                🛡️ Vui lòng giải CAPTCHA để chống bot
              </small>
            </div>
          )}

          {error && (
            <div className="error-message">
              ❌ {error}
            </div>
          )}

          <button type="submit" className="login-button" disabled={loading}>
            {loading ? 'Đang đăng nhập...' : 'Đăng nhập'}
          </button>

          <div className="login-footer">
            <small>
              🔒 Protected System - Authorized Access Only
            </small>
            {loginAttempts >= 2 && (
              <small className="warning-text">
                ⚠️ Tài khoản sẽ bị khóa sau {5 - loginAttempts} lần thử sai nữa
              </small>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}

export default LoginPage;
