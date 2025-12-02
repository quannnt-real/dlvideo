import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { ThemeToggleSimple } from '../components/ThemeToggle';
import './AdminPanel.css';

function AdminPanel() {
  const [users, setUsers] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [activeTab, setActiveTab] = useState('users'); // 'users' or 'sessions'

  // Create user form
  const [newUser, setNewUser] = useState({
    username: '',
    password: '',
    role: 'user',
  });

  // Edit/Reset modals
  const [editingUser, setEditingUser] = useState(null);
  const [resetPasswordUser, setResetPasswordUser] = useState(null);
  const [changingOwnPassword, setChangingOwnPassword] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [newUsername, setNewUsername] = useState('');

  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isAdmin) {
      navigate('/');
    } else {
      loadUsers();
      loadSessions();
    }
  }, [isAdmin, navigate]);

  const loadUsers = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/users`, {
        credentials: 'include',
      });

      if (response.ok) {
        const data = await response.json();
        setUsers(data);
      } else {
        setError('Không thể tải danh sách người dùng');
      }
    } catch (err) {
      setError('Lỗi kết nối server');
    } finally {
      setLoading(false);
    }
  };

  const loadSessions = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/sessions`, {
        credentials: 'include',
      });

      if (response.ok) {
        const data = await response.json();
        setSessions(data.sessions || []);
      }
    } catch (err) {
      console.error('Error loading sessions:', err);
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setError('');

    if (newUser.password.length < 6) {
      setError('Mật khẩu phải có ít nhất 6 ký tự');
      return;
    }

    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/users`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(newUser),
      });

      const data = await response.json();

      if (response.ok && data.success) {
        alert(`✅ Tạo người dùng thành công: ${newUser.username}`);
        setNewUser({ username: '', password: '', role: 'user' });
        setShowCreateForm(false);
        loadUsers();
      } else {
        setError(data.error || data.detail || 'Tạo người dùng thất bại');
      }
    } catch (err) {
      setError('Lỗi kết nối server');
    }
  };

  const handleResetPassword = async () => {
    if (newPassword.length < 6) {
      alert('❌ Mật khẩu phải có ít nhất 6 ký tự');
      return;
    }

    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/reset-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          username: resetPasswordUser,
          new_password: newPassword,
        }),
      });

      const data = await response.json();

      if (response.ok && data.success) {
        alert(`✅ ${data.message}`);
        setResetPasswordUser(null);
        setNewPassword('');
        loadUsers();
        loadSessions(); // Refresh sessions (user was logged out)
      } else {
        alert(`❌ ${data.error || data.detail || 'Reset mật khẩu thất bại'}`);
      }
    } catch (err) {
      alert('❌ Lỗi kết nối server');
    }
  };

  const handleUpdateUsername = async () => {
    if (newUsername.length < 3) {
      alert('❌ Username phải có ít nhất 3 ký tự');
      return;
    }

    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/update-username`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          old_username: editingUser,
          new_username: newUsername,
        }),
      });

      const data = await response.json();

      if (response.ok && data.success) {
        alert(`✅ ${data.message}`);
        setEditingUser(null);
        setNewUsername('');
        loadUsers();
        loadSessions(); // Refresh sessions (username updated)
      } else {
        alert(`❌ ${data.error || data.detail || 'Đổi username thất bại'}`);
      }
    } catch (err) {
      alert('❌ Lỗi kết nối server');
    }
  };

  const handleDeleteUser = async (username) => {
    if (!window.confirm(`Bạn có chắc muốn xóa người dùng "${username}"?`)) {
      return;
    }

    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/users/${username}`, {
        method: 'DELETE',
        credentials: 'include',
      });

      const data = await response.json();

      if (response.ok && data.success) {
        alert(`✅ Đã xóa người dùng: ${username}`);
        loadUsers();
        loadSessions();
      } else {
        alert(`❌ ${data.error || data.detail || 'Xóa người dùng thất bại'}`);
      }
    } catch (err) {
      alert('❌ Lỗi kết nối server');
    }
  };

  const handleDeleteUserSessions = async (username) => {
    if (!window.confirm(`Xóa tất cả phiên đăng nhập của "${username}"?`)) {
      return;
    }

    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/sessions/${username}`, {
        method: 'DELETE',
        credentials: 'include',
      });

      const data = await response.json();

      if (response.ok && data.success) {
        alert(`✅ ${data.message}`);
        loadSessions();
      } else {
        alert(`❌ ${data.error || data.detail || 'Xóa phiên thất bại'}`);
      }
    } catch (err) {
      alert('❌ Lỗi kết nối server');
    }
  };

  const handleCleanupSessions = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/auth/cleanup-sessions`, {
        method: 'POST',
        credentials: 'include',
      });

      const data = await response.json();

      if (response.ok) {
        alert(`✅ Đã xóa ${data.cleaned_sessions} phiên hết hạn`);
        loadSessions();
      }
    } catch (err) {
      alert('❌ Lỗi kết nối server');
    }
  };

  if (loading) {
    return (
      <div className="admin-panel">
        <div className="loading">Đang tải...</div>
      </div>
    );
  }

  return (
    <div className="admin-panel">
      {/* Theme Toggle */}
      <div style={{ position: 'fixed', top: '1rem', right: '1rem', zIndex: 50 }}>
        <ThemeToggleSimple />
      </div>

      <div className="admin-header">
        <div>
          <h1>🔧 Admin Panel</h1>
          <p>Quản lý người dùng và phiên đăng nhập</p>
        </div>
        <div className="header-actions">
          <span className="current-user">👤 {user?.username} (Admin)</span>
          <button onClick={() => {
            setChangingOwnPassword(true);
            setResetPasswordUser(user?.username);
            setNewPassword('');
          }} className="btn-warning">
            🔑 Đổi mật khẩu
          </button>
          <button onClick={() => navigate('/')} className="btn-secondary">
            🏠 Trang chủ
          </button>
          <button onClick={logout} className="btn-danger">
            🚪 Đăng xuất
          </button>
        </div>
      </div>

      <div className="admin-tabs">
        <button
          className={`tab ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          👥 Người dùng ({users.length})
        </button>
        <button
          className={`tab ${activeTab === 'sessions' ? 'active' : ''}`}
          onClick={() => setActiveTab('sessions')}
        >
          🔐 Phiên đăng nhập ({sessions.length})
        </button>
      </div>

      {error && <div className="error-message">❌ {error}</div>}

      {activeTab === 'users' && (
        <div className="tab-content">
          <div className="content-header">
            <h2>Danh sách người dùng</h2>
            <button
              onClick={() => setShowCreateForm(!showCreateForm)}
              className="btn-primary"
            >
              {showCreateForm ? '❌ Hủy' : '➕ Tạo người dùng mới'}
            </button>
          </div>

          {showCreateForm && (
            <form className="create-user-form" onSubmit={handleCreateUser}>
              <h3>Tạo người dùng mới</h3>
              <div className="form-row">
                <div className="form-group">
                  <label>Tên đăng nhập</label>
                  <input
                    type="text"
                    value={newUser.username}
                    onChange={(e) =>
                      setNewUser({ ...newUser, username: e.target.value })
                    }
                    placeholder="Nhập tên đăng nhập"
                    required
                    minLength="3"
                  />
                </div>
                <div className="form-group">
                  <label>Mật khẩu</label>
                  <input
                    type="password"
                    value={newUser.password}
                    onChange={(e) =>
                      setNewUser({ ...newUser, password: e.target.value })
                    }
                    placeholder="Nhập mật khẩu (tối thiểu 6 ký tự)"
                    required
                    minLength="6"
                  />
                </div>
                <div className="form-group">
                  <label>Vai trò</label>
                  <select
                    value={newUser.role}
                    onChange={(e) =>
                      setNewUser({ ...newUser, role: e.target.value })
                    }
                  >
                    <option value="user">👤 User</option>
                    <option value="admin">🔧 Admin</option>
                  </select>
                </div>
              </div>
              <button type="submit" className="btn-success">
                ✅ Tạo người dùng
              </button>
            </form>
          )}

          <div className="users-table">
            <table>
              <thead>
                <tr>
                  <th>Tên đăng nhập</th>
                  <th>Vai trò</th>
                  <th>Ngày tạo</th>
                  <th>Đăng nhập gần nhất</th>
                  <th>Trạng thái</th>
                  <th>Hành động</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.username}>
                    <td>
                      <strong>{u.username}</strong>
                    </td>
                    <td>
                      {u.role === 'admin' ? '🔧 Admin' : '👤 User'}
                    </td>
                    <td>{new Date(u.created_at).toLocaleString('vi-VN')}</td>
                    <td>
                      {u.last_login
                        ? new Date(u.last_login).toLocaleString('vi-VN')
                        : 'Chưa đăng nhập'}
                    </td>
                    <td>
                      {u.is_locked ? (
                        <span className="badge badge-danger">🔒 Bị khóa</span>
                      ) : (
                        <span className="badge badge-success">✅ Hoạt động</span>
                      )}
                    </td>
                    <td>
                      <div className="action-buttons">
                        {u.username !== user?.username && (
                          <>
                            <button
                              onClick={() => {
                                setEditingUser(u.username);
                                setNewUsername(u.username);
                              }}
                              className="btn-info btn-small"
                              title="Đổi username"
                            >
                              ✏️
                            </button>
                            <button
                              onClick={() => {
                                setResetPasswordUser(u.username);
                                setNewPassword('');
                              }}
                              className="btn-warning btn-small"
                              title="Reset mật khẩu"
                            >
                              🔑
                            </button>
                            <button
                              onClick={() => handleDeleteUserSessions(u.username)}
                              className="btn-secondary btn-small"
                              title="Xóa phiên đăng nhập"
                            >
                              🚫
                            </button>
                            <button
                              onClick={() => handleDeleteUser(u.username)}
                              className="btn-danger btn-small"
                              title="Xóa user"
                            >
                              🗑️
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'sessions' && (
        <div className="tab-content">
          <div className="content-header">
            <h2>Phiên đăng nhập đang hoạt động</h2>
            <button onClick={handleCleanupSessions} className="btn-warning">
              🧹 Xóa phiên hết hạn
            </button>
          </div>

          <div className="sessions-table">
            <table>
              <thead>
                <tr>
                  <th>Người dùng</th>
                  <th>Vai trò</th>
                  <th>Địa chỉ IP</th>
                  <th>Thời gian tạo</th>
                  <th>Hết hạn</th>
                  <th>Token</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((session, idx) => (
                  <tr key={idx}>
                    <td>
                      <strong>{session.username}</strong>
                    </td>
                    <td>
                      {session.role === 'admin' ? '🔧 Admin' : '👤 User'}
                    </td>
                    <td>{session.ip_address || 'Unknown'}</td>
                    <td>{new Date(session.created_at).toLocaleString('vi-VN')}</td>
                    <td>{new Date(session.expires_at).toLocaleString('vi-VN')}</td>
                    <td>
                      <code>{session.token_preview}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {sessions.length === 0 && (
              <div className="empty-state">Không có phiên đăng nhập nào</div>
            )}
          </div>
        </div>
      )}

      {/* Modal: Edit Username */}
      {editingUser && (
        <div className="modal-overlay" onClick={() => setEditingUser(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>✏️ Đổi Username</h3>
            <p>User hiện tại: <strong>{editingUser}</strong></p>
            <div className="form-group">
              <label>Username mới</label>
              <input
                type="text"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    handleUpdateUsername();
                  }
                }}
                placeholder="Nhập username mới"
                minLength="3"
                autoFocus
              />
            </div>
            <div className="modal-actions">
              <button onClick={handleUpdateUsername} className="btn-success">
                ✅ Cập nhật
              </button>
              <button onClick={() => setEditingUser(null)} className="btn-secondary">
                ❌ Hủy
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Reset Password */}
      {resetPasswordUser && (
        <div className="modal-overlay" onClick={() => {
          setResetPasswordUser(null);
          setChangingOwnPassword(false);
        }}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>🔑 Đổi Mật Khẩu</h3>
            <p>User: <strong>{resetPasswordUser}</strong></p>
            <div className="form-group">
              <label>Mật khẩu mới</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    handleResetPassword();
                  }
                }}
                placeholder="Nhập mật khẩu mới"
                minLength="6"
                autoFocus
              />
            </div>
            <div className="modal-actions">
              <button onClick={handleResetPassword} className="btn-success">
                ✅ Cập nhật
              </button>
              <button onClick={() => {
                setResetPasswordUser(null);
                setChangingOwnPassword(false);
              }} className="btn-secondary">
                ❌ Hủy
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminPanel;
