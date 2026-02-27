# Deployment Guide - Digital Ocean

> **Note:** This guide has not been fully tested with the current codebase. The deployment steps were originally verified with an earlier version. Expect to make adjustments during deployment.

## Overview

This guide covers deploying YokeFlow to a Digital Ocean Droplet with:
- PostgreSQL database (self-hosted or managed)
- FastAPI REST API + Next.js Web UI
- HTTPS with Let's Encrypt
- Nginx reverse proxy

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ Digital Ocean Droplet (8GB RAM / 4 vCPU - $48/mo)   │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Nginx (HTTPS reverse proxy)                         │
│    ├─→ FastAPI (port 8010)                           │
│    └─→ Next.js (port 3010)                           │
│                                                      │
│  Docker Compose Services:                            │
│    └─→ PostgreSQL (container)                        │
│                                                      │
│  Application Services (host):                        │
│    ├─→ FastAPI API server                            │
│    └─→ Next.js Web UI                                │
│                                                      │
│  Volumes:                                            │
│    ├─→ postgres_data (database persistence)          │
│    └─→ projects/ (generated project files)           │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## Prerequisites

### 1. Digital Ocean Account

- Sign up at [digitalocean.com](https://www.digitalocean.com)
- Add payment method

### 2. Domain Name (Optional but Recommended)

- Point DNS A record to your Droplet IP
- Required for HTTPS with Let's Encrypt

### 3. Server Requirements

- **OS:** Ubuntu 22.04 LTS (recommended)
- **Node.js:** Version 20 LTS (installed via NVM)
- **Python:** Version 3.9+
- **Docker:** For PostgreSQL (recommended: use "Docker on Ubuntu 22.04" from Digital Ocean Marketplace)

---

## Database Options

### Option A: Self-Hosted PostgreSQL (Recommended for Start)

- Free (included in Droplet cost)
- Full control
- Already configured in `docker-compose.yml`
- Manual backups required

### Option B: Digital Ocean Managed PostgreSQL

- Automatic backups, high availability, connection pooling
- $15-25/month additional
- Best for production with uptime requirements

---

## Deployment Steps

### Step 1: Create Droplet

Using the web console or CLI:

```bash
doctl compute droplet create yokeflow \
  --image docker-20-04 \
  --size s-4vcpu-8gb \
  --region nyc1 \
  --ssh-keys $(doctl compute ssh-key list --format ID --no-header)
```

**Specs:** 8GB RAM / 4 vCPU, Docker on Ubuntu image, ~$48/month

### Step 2: Initial Server Setup

```bash
ssh root@<DROPLET_IP>

# Update system
apt update && apt upgrade -y

# Install Node.js 20 via NVM
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm install 20
nvm use 20
nvm alias default 20

# Verify
node --version  # Should show v20.x.x

# Install tools
apt install -y git curl wget vim htop postgresql-client

# Clone repository
cd /var
git clone https://github.com/jeffjacobsen/yokeflow2.git
cd yokeflow2
```

### Step 3: Configure Environment

#### 3.1: Create YokeFlow Configuration

```bash
cat > .yokeflow.yaml << 'EOF'
models:
  initializer: claude-opus-4-6
  coding: claude-sonnet-4-6

timing:
  auto_continue_delay: 3

project:
  default_projects_dir: /var/yokeflow2/projects
EOF
```

**Important:** The `default_projects_dir` must be the host filesystem path where you cloned the repo.

#### 3.2: Configure Environment Variables

```bash
cp .env.example .env
vim .env
```

Key variables to set for production:

```bash
# PostgreSQL - use 'postgres' (Docker service name), not 'localhost'
DATABASE_URL=postgresql://agent:CHANGE_THIS_PASSWORD@postgres:5432/yokeflow
POSTGRES_PASSWORD=CHANGE_THIS_PASSWORD

# Claude API
CLAUDE_CODE_OAUTH_TOKEN=your_claude_oauth_token_here

# API
API_HOST=0.0.0.0
API_PORT=8010

# Web UI - use your public domain (HTTPS), NOT localhost
# These are embedded in browser JavaScript at build time
NEXT_PUBLIC_API_URL=https://your-domain.com
NEXT_PUBLIC_WS_URL=wss://your-domain.com

# Security (generate with: openssl rand -hex 32)
SECRET_KEY=your_secret_key_here

# UI Authentication (required for production)
UI_PASSWORD=your_secure_password_here
```

### Step 4: Build and Start Services

```bash
# Build MCP task manager
cd mcp-task-manager && npm install && npm run build && cd ..

# Build Next.js web UI
cd web-ui && npm install && npm run build && cd ..

# Start PostgreSQL via Docker Compose
docker compose up -d

# Check status
docker compose ps
```

### Step 5: Initialize Database

The schema auto-initializes on first PostgreSQL start via the volume mount in `docker-compose.yml`. Verify:

```bash
docker exec yokeflow_postgres \
  psql -U agent -d yokeflow -c "\dt"
```

If tables are missing, manually initialize:

```bash
docker exec -i yokeflow_postgres \
  psql -U agent -d yokeflow < schema/postgresql/schema.sql
```

### Step 5.5: Configure Firewall

**Do this BEFORE setting up SSL certificates.**

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (for certbot)
ufw allow 443/tcp   # HTTPS
ufw deny 2375/tcp   # Block Docker API (exposed by Marketplace image)
ufw deny 2376/tcp
ufw --force enable
```

### Step 6: Setup Nginx Reverse Proxy

```bash
apt install -y nginx

# WebSocket support
cat > /etc/nginx/conf.d/websocket.conf <<'EOF'
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}
EOF

# Site configuration
cat > /etc/nginx/sites-available/yokeflow <<'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # API endpoints
    location /api {
        proxy_pass http://localhost:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
    }

    # WebSocket
    location /api/ws {
        proxy_pass http://localhost:8010;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # Next.js Web UI
    location / {
        proxy_pass http://localhost:3010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    client_max_body_size 10M;
}
EOF

ln -s /etc/nginx/sites-available/yokeflow /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
mkdir -p /var/www/html/.well-known/acme-challenge
nginx -t && systemctl restart nginx && systemctl enable nginx
```

### Step 7: Start Application Services

You can either run the API and Web UI directly on the host or containerize them. For a simple deployment, run on the host:

```bash
# Create projects directory
mkdir -p projects

# Start API server (in a tmux/screen session or as a systemd service)
uvicorn server.api.app:app --host 0.0.0.0 --port 8010 &

# Start Web UI
cd web-ui && npm start &
```

For a containerized deployment, create a production Docker Compose file:

```bash
cat > docker-compose.prod.yml <<'EOF'
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    container_name: yokeflow_api
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - CLAUDE_CODE_OAUTH_TOKEN=${CLAUDE_CODE_OAUTH_TOKEN}
      - SECRET_KEY=${SECRET_KEY}
      - UI_PASSWORD=${UI_PASSWORD}
    ports:
      - "8010:8010"
    volumes:
      - ./projects:/app/projects
    depends_on:
      - postgres
    restart: unless-stopped
    networks:
      - yokeflow_network

  web:
    build:
      context: ./web-ui
      dockerfile: Dockerfile
      args:
        - NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
        - NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL}
    container_name: yokeflow_web
    ports:
      - "3010:3010"
    restart: unless-stopped
    networks:
      - yokeflow_network

  postgres:
    image: postgres:16-alpine
    container_name: yokeflow_postgres
    environment:
      POSTGRES_DB: yokeflow
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    # Do NOT expose port 5432 to the internet
    # API connects via Docker network
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./schema/postgresql:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agent -d yokeflow"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - yokeflow_network

volumes:
  postgres_data:
    name: yokeflow_postgres_data

networks:
  yokeflow_network:
    name: yokeflow_network
    driver: bridge
EOF
```

Create Dockerfiles:

```bash
# API Dockerfile
cat > Dockerfile.api <<'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install Node.js for MCP server
RUN apt-get update && apt-get install -y curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser appuser

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Build MCP server
RUN cd mcp-task-manager && npm install && npm run build && cd ..

# Change ownership to non-root user
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8010

CMD ["uvicorn", "server.api.app:app", "--host", "0.0.0.0", "--port", "8010"]
EOF

# Web UI Dockerfile
cat > web-ui/Dockerfile <<'EOF'
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Build args required for Next.js (baked into static files)
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL

RUN npm run build

EXPOSE 3010

CMD ["npm", "start"]
EOF
```

Start production services:

```bash
mkdir -p projects
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f
```

### Step 8: Setup SSL with Let's Encrypt

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
certbot renew --dry-run  # Test auto-renewal
```

If certbot fails with a 404 on the ACME challenge, ensure the `/.well-known/acme-challenge/` location block is in your Nginx config and `mkdir -p /var/www/html/.well-known/acme-challenge` has been run.

---

## Security & Authentication

### JWT Authentication (Built-in)

The platform includes JWT authentication:

- **Backend:** `server/api/auth.py` — bcrypt password verification, 24-hour token expiration, all endpoints protected except `/api/auth/login` and `/health`
- **Frontend:** Login page at `/login`, JWT stored in localStorage, auto-redirect on 401
- **Single-user mode:** Password set via `UI_PASSWORD` environment variable
- **Development mode:** When `UI_PASSWORD` is not set, authentication is bypassed

**Required environment variables:**
```bash
SECRET_KEY=your_secret_key_here        # openssl rand -hex 32
UI_PASSWORD=your_secure_password_here
```

### CORS Configuration

Update `allow_origins` for production:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Rate Limiting (Optional)

```bash
pip install slowapi
```

See [slowapi documentation](https://slowapi.readthedocs.io/) for integration with FastAPI.

---

## Backup & Monitoring

### PostgreSQL Backup Script

```bash
cat > /usr/local/bin/backup-postgres.sh <<'EOF'
#!/bin/bash
set -e

BACKUP_DIR="/var/backups/yokeflow"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

mkdir -p $BACKUP_DIR

docker exec yokeflow_postgres \
  pg_dump -U agent -d yokeflow -F c -b -v \
  > $BACKUP_DIR/postgres_${TIMESTAMP}.dump

gzip $BACKUP_DIR/postgres_${TIMESTAMP}.dump

find $BACKUP_DIR -name "postgres_*.dump.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: postgres_${TIMESTAMP}.dump.gz"
EOF

chmod +x /usr/local/bin/backup-postgres.sh
```

Schedule daily backup:

```bash
# Add to crontab (crontab -e):
0 2 * * * /usr/local/bin/backup-postgres.sh >> /var/log/postgres-backup.log 2>&1
```

### Restore from Backup

```bash
gunzip /var/backups/yokeflow/postgres_YYYYMMDD_HHMMSS.dump.gz

docker exec -i yokeflow_postgres \
  pg_restore -U agent -d yokeflow --clean \
  < /var/backups/yokeflow/postgres_YYYYMMDD_HHMMSS.dump
```

### Monitoring

```bash
# Docker containers
docker compose ps

# API logs
docker compose logs -f api

# Nginx logs
tail -f /var/log/nginx/error.log

# Disk space
df -h

# Docker disk usage
docker system df
```

---

## Cost Analysis

| Component | Monthly Cost |
|-----------|-------------|
| Droplet (8GB/4vCPU) | $48 |
| Self-hosted PostgreSQL | $0 (included) |
| Managed PostgreSQL (optional) | $15-25 |
| Let's Encrypt SSL | $0 |
| Domain (.com) | ~$1 |
| **Total (self-hosted DB)** | **~$49** |
| **Total (managed DB)** | **~$64-74** |

---

## Troubleshooting

### PostgreSQL Authentication Errors ("Role postgres does not exist")

**Cause:** Port 5432 is exposed to the internet, allowing bots to attempt connections.

**Fix:** Remove the `ports` mapping from the postgres service in your Docker Compose file. The API container connects via Docker network and doesn't need port exposure. If you need direct access, use an SSH tunnel: `ssh -L 5432:localhost:5432 root@your-server`

### TypeScript Build Error: "Unexpected token '?'"

**Cause:** Node.js version is too old. Node.js 20 LTS is required.

**Fix:** Install via NVM: `nvm install 20 && nvm use 20 && nvm alias default 20`

### `docker-compose` Command Not Found

Ubuntu 22.04+ uses Docker Compose V2. Use `docker compose` (with a space) instead of `docker-compose`.

### Web UI Still Uses localhost After Changing NEXT_PUBLIC_API_URL

Next.js bakes `NEXT_PUBLIC_*` variables into static files at build time. You must rebuild the web container after changing these values:

```bash
docker compose -f docker-compose.prod.yml build --no-cache web
docker compose -f docker-compose.prod.yml up -d web
```

### API Returns Empty Data or Connection Error

If `DATABASE_URL` uses `localhost`, the API container can't reach PostgreSQL. Use the Docker service name `postgres` instead:

```bash
DATABASE_URL=postgresql://agent:password@postgres:5432/yokeflow
```

### Certbot ACME Challenge Fails

Ensure the firewall allows ports 80 and 443 (`ufw allow 80/tcp && ufw allow 443/tcp`) and that the Nginx config includes the `/.well-known/acme-challenge/` location block.

### SSL Certificate Renewal

```bash
certbot renew --force-renewal
certbot certificates
```

---

## Maintenance

- **Daily:** Check disk space (`df -h`), check containers (`docker ps`)
- **Weekly:** Clean Docker resources (`docker system prune -f`)
- **Monthly:** Update system packages, vacuum database (`VACUUM ANALYZE;`)
