#!/bin/bash
# deploy.sh — setup completo no VPS Ubuntu 22.04
# Execute como root: bash deploy.sh [seu-dominio.com.br]

set -e
echo "=== FrotaGov — Deploy ==="

DOMAIN=${1:-"seu-dominio.com.br"}
APP_DIR="/opt/frotagov"
DB_NAME="frotagov"
DB_USER="frotagov"
DB_PASS="frotagov"   # altere antes de executar em produção

# 1. Dependências do sistema
apt-get update -q
apt-get install -y \
    python3.11 python3.11-venv python3-pip \
    redis-server \
    postgresql postgresql-contrib \
    nginx certbot python3-certbot-nginx

# 2. Redis
systemctl enable redis-server
systemctl start redis-server

# 3. PostgreSQL
systemctl enable postgresql
systemctl start postgresql

# Cria usuário e banco (idempotente)
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" \
    | grep -q 1 || sudo -u postgres psql -c \
    "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" \
    | grep -q 1 || sudo -u postgres psql -c \
    "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"

# 4. Virtualenv e pacotes Python
python3.11 -m venv ${APP_DIR}/venv
${APP_DIR}/venv/bin/pip install --upgrade pip -q
${APP_DIR}/venv/bin/pip install -r ${APP_DIR}/requirements.txt

# 5. Arquivo .env
if [ ! -f ${APP_DIR}/.env ]; then
    cat > ${APP_DIR}/.env << EOF
SISATEC_CODIGO=SEU_CODIGO
SISATEC_KEY=SUA_CHAVE
USE_MOCK=false
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASS}@localhost/${DB_NAME}
DASHBOARD_USER=admin
DASHBOARD_PASS=TROQUE_ESTA_SENHA
ENV=production
SYNC_INTERVAL_MIN=3
EOF
    echo "ATENÇÃO: edite ${APP_DIR}/.env com suas credenciais antes de iniciar."
fi

# 6. Serviço systemd
cat > /etc/systemd/system/frotagov.service << EOF
[Unit]
Description=FrotaGov FastAPI
After=network.target redis.service postgresql.service

[Service]
User=www-data
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable frotagov

# 7. Nginx reverse proxy
cat > /etc/nginx/sites-available/frotagov << EOF
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;
    }
}
EOF

ln -sf /etc/nginx/sites-available/frotagov /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

echo ""
echo "=== Deploy concluído ==="
echo "Próximos passos:"
echo "  1. Edite ${APP_DIR}/.env com suas credenciais reais"
echo "  2. systemctl start frotagov"
echo "  3. Execute o backfill histórico (uma única vez):"
echo "       cd ${APP_DIR} && venv/bin/python -m scripts.backfill --anos 3"
echo "  4. Para HTTPS: certbot --nginx -d ${DOMAIN}"
echo "  5. Teste: curl http://localhost:8000/api/health"
