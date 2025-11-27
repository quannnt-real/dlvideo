# 📦 Hướng dẫn Push Code lên Git và Deploy

## ✅ Đã hoàn thành

### 1. Clean Code - Xóa Emergent References
- ✅ Xóa emergent và rrweb scripts từ `frontend/public/index.html`
- ✅ Xóa `.gitconfig` với email emergent
- ✅ Xóa `backend_test.py` chứa URL emergent
- ✅ Xóa toàn bộ `frontend/plugins` folder
- ✅ Update `.gitignore` để exclude sensitive files

### 2. Files đã tạo
- ✅ `.env.example` - Template cho environment variables
- ✅ `.gitattributes` - Đảm bảo line endings nhất quán
- ✅ `DEPLOY_AAPANEL.md` - Hướng dẫn deploy chi tiết lên VPS
- ✅ `GIT_DEPLOY_GUIDE.md` - File này

---

## 🚀 Bước 1: Commit và Push Code lên GitHub

**Lưu ý:** Repository này đã tồn tại trên GitHub. Bạn chỉ cần commit và push các thay đổi mới.

### 1.1. Kiểm tra Git Status

```bash
cd /Volumes/D/project-test/dlvideo

# Kiểm tra status
git status

# Kiểm tra remote đã có chưa
git remote -v
```

### 1.2. Add & Commit Code

```bash
# Add tất cả files đã cleanup
git add .

# Commit với message chi tiết
git commit -m "Production ready: Clean code and add authentication system

Changes:
- Remove emergent tracking scripts and references
- Add complete authentication system (admin/user roles)
- Add session-based auth with CAPTCHA and rate limiting
- Add Admin Panel for user management
- Add security features (robots.txt, meta tags)
- Add extensive logging for debugging
- Add deployment guide for aaPanel
- Clean up test files and debug docs

Features:
- Video/Audio downloader with 1000+ platforms support
- Audio editor with trim, concat, fade
- User management with role-based access
- Session management with auto-cleanup
- CORS configuration for production
- Ready for deployment on dl.quannnt.com"

# Kiểm tra commit
git log -1
```

### 1.3. Push lên GitHub

```bash
# Push lên remote repository đã có
git push origin main
```

**Nhập username và password khi được hỏi** (hoặc Personal Access Token nếu dùng HTTPS)

### 1.4. Verify trên GitHub

1. Truy cập `https://github.com/YOUR_USERNAME/dlvideo`
2. Kiểm tra files đã được push đầy đủ
3. **QUAN TRỌNG**: Check `.gitignore` đã hoạt động:
   - `backend/data/users.json` KHÔNG có trên Git ✅
   - `backend/logs/*.log` KHÔNG có trên Git ✅
   - `.env` files KHÔNG có trên Git ✅
   - `INITIAL_SETUP.md` KHÔNG có trên Git ✅

---

## 🌐 Bước 2: Deploy lên VPS

### 2.1. Chuẩn bị VPS

**Yêu cầu:**
- VPS đã cài aaPanel
- Domain `dl.quannnt.com` đã trỏ về VPS IP
- SSH access vào VPS

**Kiểm tra domain đã trỏ đúng:**
```bash
# Từ máy local
ping dl.quannnt.com

# Hoặc:
nslookup dl.quannnt.com
```

### 2.2. Follow DEPLOY_AAPANEL.md

Xem hướng dẫn chi tiết trong file: [DEPLOY_AAPANEL.md](./DEPLOY_AAPANEL.md)

**Tóm tắt các bước:**

1. **SSH vào VPS**
   ```bash
   ssh root@YOUR_VPS_IP
   ```

2. **Clone repo**
   ```bash
   cd /www/wwwroot
   git clone https://github.com/YOUR_USERNAME/dlvideo.git dl.quannnt.com
   cd dl.quannnt.com
   ```

3. **Setup Backend**
   ```bash
   cd backend
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt

   # Tạo .env
   cat > .env << 'EOF'
   CORS_ORIGINS=https://dl.quannnt.com
   SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
   DEBUG=False
   EOF
   ```

4. **Setup Supervisor cho Backend**
   ```bash
   # Copy config từ DEPLOY_AAPANEL.md
   nano /etc/supervisor/conf.d/dlvideo-backend.conf

   supervisorctl reread
   supervisorctl update
   supervisorctl start dlvideo-backend
   ```

5. **Setup Frontend**
   ```bash
   cd frontend
   yarn install

   # Tạo .env
   echo "REACT_APP_BACKEND_URL=https://dl.quannnt.com" > .env

   # Build
   yarn build
   ```

6. **Setup Nginx**
   - Tạo website trong aaPanel: `dl.quannnt.com`
   - Copy Nginx config từ DEPLOY_AAPANEL.md
   - Restart Nginx

7. **Setup SSL**
   ```bash
   certbot --nginx -d dl.quannnt.com
   ```

8. **Kiểm tra**
   - Truy cập: https://dl.quannnt.com
   - Login với admin/admin123
   - Đổi password ngay!

---

## 🔄 Update Code sau khi Deploy

Khi có thay đổi code:

### 3.1. Commit và Push từ Local

```bash
cd /Volumes/D/project-test/dlvideo

git add .
git commit -m "Your commit message"
git push origin main
```

### 3.2. Pull và Deploy trên VPS

```bash
# SSH vào VPS
ssh root@YOUR_VPS_IP

# Pull code mới
cd /www/wwwroot/dl.quannnt.com
git pull origin main

# Update Backend
cd backend
source venv/bin/activate
pip install -r requirements.txt
deactivate
supervisorctl restart dlvideo-backend

# Update Frontend
cd ../frontend
yarn install
yarn build
chown -R www:www build

# Reload Nginx
systemctl reload nginx
```

---

## 📝 Checklist Deploy

### Trước khi Deploy
- [ ] Code đã clean (không có emergent references)
- [ ] Đã test đầy đủ trên local
- [ ] Đã commit và push lên GitHub
- [ ] .env.example đã tạo (KHÔNG commit .env thật!)
- [ ] DEPLOY_AAPANEL.md đã đọc kỹ

### Deploy trên VPS
- [ ] VPS đã cài aaPanel
- [ ] Domain đã trỏ về VPS
- [ ] Code đã clone về `/www/wwwroot/dl.quannnt.com`
- [ ] Backend đã setup và running (port 8000)
- [ ] Frontend đã build
- [ ] Nginx đã cấu hình và reverse proxy
- [ ] SSL certificate đã cài (Let's Encrypt)
- [ ] Firewall đã setup (đóng port 8000)
- [ ] Admin account đã tạo và đổi password
- [ ] Logs đang ghi đúng
- [ ] Downloads auto-cleanup đã setup (cron job)

### Sau Deploy
- [ ] Test login: https://dl.quannnt.com/login
- [ ] Test download video
- [ ] Test download audio
- [ ] Test audio editor
- [ ] Test admin panel (create user, delete, etc.)
- [ ] Check logs: `tail -f /www/wwwroot/dl.quannnt.com/backend/logs/debug.log`
- [ ] Check backend status: `supervisorctl status dlvideo-backend`

---

## 🔒 Security Checklist

- [ ] `.env` files KHÔNG được commit lên Git
- [ ] `backend/data/users.json` KHÔNG được commit (gitignored)
- [ ] Default admin password đã đổi
- [ ] `INITIAL_SETUP.md` đã xóa khỏi VPS
- [ ] SSL certificate đã enabled
- [ ] CORS origins chính xác (https://dl.quannnt.com)
- [ ] robots.txt và meta tags đã có
- [ ] Firewall chỉ mở port 22, 80, 443
- [ ] Backend chỉ listen localhost:8000 (không public)
- [ ] Rate limiting và CAPTCHA đang hoạt động

---

## 📞 Troubleshooting

### Git push bị reject
```bash
# Pull trước rồi push lại
git pull origin main --rebase
git push origin main
```

### Authentication failed khi push
- Dùng Personal Access Token thay password
- Hoặc setup SSH keys: https://docs.github.com/en/authentication/connecting-to-github-with-ssh

### Backend không start trên VPS
```bash
# Check logs
supervisorctl tail dlvideo-backend stderr

# Check port
netstat -tulpn | grep 8000

# Restart
supervisorctl restart dlvideo-backend
```

### Frontend build fail
```bash
# Clear cache và rebuild
cd frontend
rm -rf node_modules build
yarn install
yarn build
```

### 401 Unauthorized sau deploy
- Check `.env` CORS_ORIGINS phải là `https://dl.quannnt.com`
- Restart backend: `supervisorctl restart dlvideo-backend`
- Clear browser cookies và login lại

---

## 📚 Tài liệu khác

- [DEPLOY_AAPANEL.md](./DEPLOY_AAPANEL.md) - Hướng dẫn deploy chi tiết
- [README.md](./README.md) - Tài liệu dự án
- [.env.example](./.env.example) - Template environment variables

---

**🎉 Chúc bạn deploy thành công!**

Nếu gặp vấn đề, check logs:
- Backend: `/www/wwwroot/dl.quannnt.com/backend/logs/`
- Nginx: `/www/wwwlogs/dl.quannnt.com.error.log`
- Supervisor: `supervisorctl tail dlvideo-backend stderr`
