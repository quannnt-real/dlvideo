import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { ThemeToggleSimple } from '../components/ThemeToggle';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Lock, User, Shield, AlertCircle } from 'lucide-react';

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
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 p-4">
      {/* Theme Toggle - Top Right */}
      <div className="absolute top-4 right-4">
        <ThemeToggleSimple />
      </div>

      <Card className="w-full max-w-md shadow-xl border-0 bg-white/80 dark:bg-slate-800/90 backdrop-blur-sm">
        <CardHeader className="text-center space-y-2 pb-4">
          <div className="mx-auto w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-2">
            <Shield className="w-8 h-8 text-primary" />
          </div>
          <CardTitle className="text-2xl font-bold text-foreground">System Access</CardTitle>
          <CardDescription className="text-muted-foreground">
            Authorized Users Only
          </CardDescription>
        </CardHeader>

        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username" className="text-foreground">Tên đăng nhập</Label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Nhập tên đăng nhập"
                  disabled={loading}
                  autoComplete="username"
                  autoFocus
                  className="pl-10"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="text-foreground">Mật khẩu</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Nhập mật khẩu"
                  disabled={loading}
                  autoComplete="current-password"
                  className="pl-10"
                />
              </div>
            </div>

            {/* CAPTCHA - Only show after 2 failed attempts */}
            {loginAttempts >= 2 && (
              <div className="space-y-2 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
                <Label htmlFor="captcha" className="text-foreground flex items-center gap-2">
                  <Shield className="h-4 w-4 text-amber-600 dark:text-amber-400" />
                  Bảo mật: {captchaQuestion.question} = ?
                </Label>
                <Input
                  id="captcha"
                  type="number"
                  value={captchaAnswer}
                  onChange={(e) => setCaptchaAnswer(e.target.value)}
                  placeholder="Nhập kết quả"
                  disabled={loading}
                  required
                />
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  🛡️ Vui lòng giải CAPTCHA để chống bot
                </p>
              </div>
            )}

            {error && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 text-destructive border border-destructive/20">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                <span className="text-sm">{error}</span>
              </div>
            )}

            <Button 
              type="submit" 
              className="w-full" 
              disabled={loading}
              size="lg"
            >
              {loading ? (
                <>
                  <span className="animate-spin mr-2">⏳</span>
                  Đang đăng nhập...
                </>
              ) : (
                'Đăng nhập'
              )}
            </Button>

            <div className="text-center space-y-2 pt-2">
              <p className="text-xs text-muted-foreground flex items-center justify-center gap-1">
                <Lock className="h-3 w-3" />
                Protected System - Authorized Access Only
              </p>
              {loginAttempts >= 2 && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  ⚠️ Tài khoản sẽ bị khóa sau {5 - loginAttempts} lần thử sai nữa
                </p>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

export default LoginPage;
