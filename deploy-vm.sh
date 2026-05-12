#!/bin/bash
# ==============================================================
# SolCuts — Deploy automatizado para Hetzner VM (Ubuntu 24.04)
# Uso:  scp deploy-vm.sh root@<IP>:/root/ && ssh root@<IP> ./deploy-vm.sh
# ==============================================================
set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'
NC='\033[0m'

REPO_URL="https://github.com/vdsilveira/SOLCUTS_colosseum_Hackathon.git"
INSTALL_DIR="/srv/solcuts"
CORE_API_PORT=8001
SERVER_IP=""

ok()   { echo -e "  ${GREEN}✔${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
step() { echo -e "\n${CYAN}[$1/7]${NC} ${BOLD}$2${NC}"; }

# ──────────────────────────────────────────────
# STEP 1 — Detectar IP público
# ──────────────────────────────────────────────
step 1 "Detectando IP público do servidor..."
SERVER_IP=$(curl -s ifconfig.me || curl -s icanhazip.com)
[ -z "$SERVER_IP" ] && { warn "Falha ao detectar IP"; exit 1; }
ok "IP: $SERVER_IP"

# ──────────────────────────────────────────────
# STEP 2 — Instalar dependências do sistema
# ──────────────────────────────────────────────
step 2 "Instalando Docker, Git e firewall..."
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 git ufw

systemctl enable --now docker
ok "Docker + Compose instalados"

ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow "$CORE_API_PORT"/tcp
ufw --force enable
ok "Firewall configurado (22, 80, 443, $CORE_API_PORT)"

# ──────────────────────────────────────────────
# STEP 3 — Clonar repositório + submodules
# ──────────────────────────────────────────────
step 3 "Clonando repositório e submodules..."
rm -rf "$INSTALL_DIR"
git clone "$REPO_URL" "$INSTALL_DIR"
cd "$INSTALL_DIR"
git submodule update --init --recursive
ok "Repositório em $INSTALL_DIR"

# ──────────────────────────────────────────────
# STEP 4 — Configurar .env
# ──────────────────────────────────────────────
step 4 "Configurando .env..."

cp .env.example .env

SHARED_KEY=$(openssl rand -hex 16)
sed -i "s|^APP_API_KEY=.*|APP_API_KEY=$SHARED_KEY|" .env
sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=[\"http://$SERVER_IP:$CORE_API_PORT\",\"http://localhost:3000\",\"https://solcuts.vercel.app\"]|" .env

ok "APP_API_KEY gerada: ${SHARED_KEY:0:8}..."
ok "CORS_ORIGINS configurado para IP direto + Vercel"

echo ""
echo -e "  ${YELLOW}⚠  Configure manualmente no .env:${NC}"
echo -e "     ${BOLD}YOUTUBE_API_KEY${NC}"
echo -e "     ${BOLD}ORACLE_PUBLIC_KEY${NC} + ${BOLD}ORACLE_PRIVATE_KEY${NC}"
echo -e "     ${DIM}Caminho: $INSTALL_DIR/.env${NC}"
echo ""
read -rp "  Pressione ENTER após editar (ou Ctrl+C para pular)..."

# ──────────────────────────────────────────────
# STEP 5 — Gerar docker-compose.yaml
# ──────────────────────────────────────────────
step 5 "Rodando setup.sh..."
chmod +x setup.sh
./setup.sh
ok "docker-compose.yaml gerado"

# ──────────────────────────────────────────────
# STEP 6 — Build + Start
# ──────────────────────────────────────────────
step 6 "Buildando containers..."
docker compose up --build -d
ok "Containers rodando:"
docker compose ps

# ──────────────────────────────────────────────
# STEP 7 — Healthcheck
# ──────────────────────────────────────────────
step 7 "Verificando saúde..."
sleep 5
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$CORE_API_PORT/health" 2>/dev/null || echo "000")
if [ "$STATUS" = "200" ]; then
    ok "core-api saudável (HTTP $STATUS)"
else
    warn "core-api retornou HTTP $STATUS — logs: docker compose logs core-api"
fi

# ──────────────────────────────────────────────
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}Deploy concluído!${NC}"
echo ""
echo -e "  ${BOLD}core-api:${NC}  http://$SERVER_IP:$CORE_API_PORT"
echo -e "  ${BOLD}Swagger:${NC}   http://$SERVER_IP:$CORE_API_PORT/docs"
echo -e "  ${BOLD}Logs:${NC}      docker compose logs -f"
echo ""
echo -e "  ${BOLD}Frontend (Vercel) — no seu PC:${NC}"
echo -e "    1. cd DApp_Frontend_colosseum_Hackathon"
echo -e "    2. echo 'NEXT_PUBLIC_CORE_API_URL=http://$SERVER_IP:$CORE_API_PORT/api/v1' > .env.local"
echo -e "    3. vercel --prod"
echo ""
echo -e "  ${YELLOW}Não esqueça: ORACLE_PUBLIC_KEY + ORACLE_PRIVATE_KEY no .env${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
