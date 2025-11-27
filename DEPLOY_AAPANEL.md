# 🚀 Hướng dẫn Deploy DLVideo lên VPS với aaPanel

## 📋 Yêu cầu

- VPS đã cài aaPanel
- Domain: `dl.quannnt.com` đã trỏ về IP của VPS
- Python 3.11+
- Node.js 18+
- Git

---

## 🔧 Phần 1: Chuẩn bị Code trên Local

### 1.1. Commit và Push code lên Git

```bash
cd /Volumes/D/project-test/dlvideo

# Add tất cả thay đổi
git add .

# Commit với message
git commit -m "Clean code và chuẩn bị deploy production

- Xóa tất cả references đến emergent
- Xóa rrweb tracking scripts
- Thêm authentication system
- Chuẩn bị cho production deployment"

# Push lên GitHub (giả sử bạn đã tạo repo)
git remote add origin https://github.com/quannnt/dlvideo.git
git branch -M main
git push -u origin main
```

### 1.2. Tạo file .env mẫu cho production

```bash
# Tạo file .env.example (để làm template)
cat > .env.example << 'EOF'
# Backend Environment Variables
CORS_ORIGINS=https://dl.quannnt.com
SECRET_KEY=your-secret-key-here-change-in-production
DEBUG=False

# Frontend Environment Variables (trong frontend/.env)
REACT_APP_BACKEND_URL=https://dl.quannnt.com
EOF

git add .env.example
git commit -m "Add .env.example for production"
git push
```

---

## 🖥️ Phần 2: Setup VPS với aaPanel

### 2.1. Truy cập VPS qua SSH

```bash
ssh root@your-vps-ip
```

### 2.2. Cài đặt Python Manager trong aaPanel

1. Đăng nhập aaPanel: `http://your-vps-ip:7800`
2. Vào **App Store** → Tìm **Python Manager** → Install
3. Cài Python 3.11 hoặc 3.12

### 2.3. Clone Project từ Git

```bash
# Vào thư mục website của aaPanel
cd /www/wwwroot

# Clone project
git clone https://github.com/quannnt/dlvideo.git dl.quannnt.com
cd dl.quannnt.com

# Phân quyền
chown -R www:www /www/wwwroot/dl.quannnt.com
chmod -R 755 /www/wwwroot/dl.quannnt.com
```

---

## 🐍 Phần 3: Setup Backend (Python/FastAPI)

### 3.1. Tạo Virtual Environment

```bash
cd /www/wwwroot/dl.quannnt.com/backend

# Tạo venv
python3.11 -m venv venv

# Activate
source venv/bin/activate

# Cài dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 3.2. Tạo file .env cho backend

```bash
cd /www/wwwroot/dl.quannnt.com/backend

cat > .env << 'EOF'
CORS_ORIGINS=https://dl.quannnt.com
SECRET_KEY=YOUR_RANDOM_SECRET_KEY_HERE_CHANGE_THIS
DEBUG=False
EOF

# Phân quyền
chmod 600 .env
chown www:www .env
```

**QUAN TRỌNG:** Thay `YOUR_RANDOM_SECRET_KEY_HERE_CHANGE_THIS` bằng key ngẫu nhiên:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3.3. Tạo thư mục data và logs

```bash
cd /www/wwwroot/dl.quannnt.com/backend

mkdir -p data logs downloads
chown -R www:www data logs downloads
chmod -R 755 data logs downloads
```

### 3.4. Khởi chạy Backend với Supervisor

**Tạo file Supervisor config:**

```bash
cat > /etc/supervisor/conf.d/dlvideo-backend.conf << 'EOF'
[program:dlvideo-backend]
directory=/www/wwwroot/dl.quannnt.com/backend
command=/www/wwwroot/dl.quannnt.com/backend/venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000 --workers 2
user=www
autostart=true
autorestart=true
stderr_logfile=/www/wwwroot/dl.quannnt.com/backend/logs/error.log
stdout_logfile=/www/wwwroot/dl.quannnt.com/backend/logs/access.log
environment=PYTHONUNBUFFERED=1
EOF

# Reload Supervisor
supervisorctl reread
supervisorctl update
supervisorctl start dlvideo-backend
supervisorctl status dlvideo-backend
```

**Kiểm tra backend đang chạy:**
```bash
curl http://127.0.0.1:8000/
# Should return: {"message":"DLVideo API is running","status":"healthy"}
```

---

## ⚛️ Phần 4: Setup Frontend (React)

### 4.1. Cài Node.js và Yarn

```bash
# Cài Node.js 18 LTS qua aaPanel
# Hoặc dùng NVM:
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 18
nvm use 18

# Cài Yarn
npm install -g yarn
```

### 4.2. Build Frontend

```bash
cd /www/wwwroot/dl.quannnt.com/frontend

# Tạo .env cho production
cat > .env << 'EOF'
REACT_APP_BACKEND_URL=https://dl.quannnt.com
EOF

# Install dependencies
yarn install

# Build production
yarn build

# Phân quyền build folder
chown -R www:www build
chmod -R 755 build
```

---

## 🌐 Phần 5: Setup Nginx Reverse Proxy

### 5.1. Tạo Website trong aaPanel

1. Vào **Website** → **Add site**
2. Domain: `dl.quannnt.com`
3. Root directory: `/www/wwwroot/dl.quannnt.com/frontend/build`
4. PHP: Không cần (uncheck PHP)
5. Create

### 5.2. Cấu hình Nginx

**Click vào site → Settings → Config file**, thay thế bằng config sau:

```nginx
server {
    listen 80;
    listen 443 ssl http2;
    server_name dl.quannnt.com;

    # SSL Certificate (sẽ setup ở bước tiếp theo)
    # ssl_certificate /www/server/panel/vhost/cert/dl.quannnt.com/fullchain.pem;
    # ssl_certificate_key /www/server/panel/vhost/cert/dl.quannnt.com/privkey.pem;

    # Root directory cho React build
    root /www/wwwroot/dl.quannnt.com/frontend/build;
    index index.html;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript
               application/x-javascript application/xml+rss
               application/javascript application/json;

    # Backend API proxy
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts cho video download
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    # Downloads folder
    location /downloads {
        alias /www/wwwroot/dl.quannnt.com/backend/downloads;
        expires 1h;
        add_header Cache-Control "public, immutable";
    }

    # React Router - redirect all to index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Static files caching
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Access log
    access_log /www/wwwlogs/dl.quannnt.com.log;
    error_log /www/wwwlogs/dl.quannnt.com.error.log;
}
```

**Reload Nginx:**
```bash
nginx -t  # Test config
systemctl reload nginx
```

### 5.3. Cài SSL Certificate (Let's Encrypt)

1. Vào **Website** → Click vào `dl.quannnt.com`
2. Chọn tab **SSL**
3. Chọn **Let's Encrypt**
4. Nhập email, tick "Force HTTPS"
5. Apply

**Hoặc dùng CLI:**
```bash
# Cài Certbot
apt-get install certbot python3-certbot-nginx -y

# Lấy certificate
certbot --nginx -d dl.quannnt.com

# Auto renew đã được setup sẵn
```

---

## 🔐 Phần 6: Security và Final Setup

### 6.1. Setup Firewall trong aaPanel

1. **Security** → **Firewall**
2. Chỉ mở các ports:
   - 22 (SSH)
   - 80 (HTTP)
   - 443 (HTTPS)
   - 7800 (aaPanel - nếu cần)
3. Đóng port 8000 (backend chỉ listen localhost)

### 6.2. Tạo Admin User đầu tiên

**Sau khi deploy xong, truy cập:**
```
https://dl.quannnt.com/login
```

Lần đầu tiên hệ thống sẽ tự động tạo admin account. Check file:
```bash
cat /www/wwwroot/dl.quannnt.com/backend/INITIAL_SETUP.md
```

**QUAN TRỌNG:** Sau khi login và đổi password, xóa file này:
```bash
rm /www/wwwroot/dl.quannnt.com/backend/INITIAL_SETUP.md
```

### 6.3. Setup Auto Cleanup Downloads

**Tạo cron job để xóa files download cũ:**

```bash
crontab -e
```

Thêm dòng:
```
0 3 * * * find /www/wwwroot/dl.quannnt.com/backend/downloads -type f -mtime +1 -delete
```

(Xóa files cũ hơn 1 ngày, chạy lúc 3h sáng mỗi ngày)

---

## 📊 Phần 7: Monitoring và Logs

### 7.1. Xem logs Backend

```bash
# Access log
tail -f /www/wwwroot/dl.quannnt.com/backend/logs/access.log

# Error log
tail -f /www/wwwroot/dl.quannnt.com/backend/logs/error.log

# Debug log
tail -f /www/wwwroot/dl.quannnt.com/backend/logs/debug.log
```

### 7.2. Xem logs Nginx

```bash
tail -f /www/wwwlogs/dl.quannnt.com.log
tail -f /www/wwwlogs/dl.quannnt.com.error.log
```

### 7.3. Restart Services

```bash
# Restart Backend
supervisorctl restart dlvideo-backend

# Restart Nginx
systemctl restart nginx

# Check status
supervisorctl status dlvideo-backend
systemctl status nginx
```

---

## 🔄 Phần 8: Update Code (Deploy Updates)

Khi có code mới:

```bash
cd /www/wwwroot/dl.quannnt.com

# Pull code mới
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

## ✅ Checklist Deploy

- [ ] Code đã clean (xóa emergent references)
- [ ] Git repo đã push
- [ ] VPS đã cài aaPanel
- [ ] Domain đã trỏ về VPS
- [ ] Python 3.11+ đã cài
- [ ] Node.js 18+ đã cài
- [ ] Backend đã setup và chạy (port 8000)
- [ ] Frontend đã build
- [ ] Nginx đã cấu hình đúng
- [ ] SSL certificate đã cài (Let's Encrypt)
- [ ] Firewall đã setup
- [ ] Admin account đã tạo và đổi password
- [ ] Logs đang hoạt động
- [ ] Auto cleanup downloads đã setup

---

## 🐛 Troubleshooting

### Backend không chạy

```bash
# Check logs
supervisorctl tail dlvideo-backend stderr

# Check port
netstat -tulpn | grep 8000

# Restart
supervisorctl restart dlvideo-backend
```

### Frontend không load

```bash
# Check Nginx config
nginx -t

# Check build folder
ls -la /www/wwwroot/dl.quannnt.com/frontend/build

# Rebuild
cd /www/wwwroot/dl.quannnt.com/frontend
yarn build
```

### 401 Unauthorized trên Admin Panel

- Check CORS_ORIGINS trong backend/.env
- Phải là: `CORS_ORIGINS=https://dl.quannnt.com`
- Restart backend sau khi sửa

### SSL không hoạt động

```bash
# Force renew
certbot renew --force-renewal

# Check certificate
certbot certificates
```

---

## 📞 Support

Nếu gặp vấn đề khi deploy, check:
1. Logs backend: `/www/wwwroot/dl.quannnt.com/backend/logs/`
2. Logs Nginx: `/www/wwwlogs/dl.quannnt.com.error.log`
3. Supervisor status: `supervisorctl status`

---

**🎉 Chúc bạn deploy thành công!**
