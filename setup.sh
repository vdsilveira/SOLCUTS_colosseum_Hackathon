#!/bin/bash

# ==============================================================
# SolCuts Project Setup (Docker Compose)
# ==============================================================
# Lê services.conf para determinar quais componentes rodam
# localmente e gera o docker-compose.yaml correspondente.
#
# Uso:
#   ./setup.sh           → configura .env e gera compose
#   ./setup.sh --force   → recria .env + regenera tudo
# ==============================================================

set -e

# --- Cores ----------------------------------------------------
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"
CONF_FILE="$ROOT_DIR/services.conf"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yaml"

TOTAL_STEPS=6

# --- Funções de output ----------------------------------------
header() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  ${BOLD}SolCuts — Docker Compose Setup${NC}                    ${BLUE}║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
    echo ""
}
step()  { echo -e "\n${CYAN}[$1/$TOTAL_STEPS]${NC} ${BOLD}$2${NC}"; }
ok()    { echo -e "    ${GREEN}✔ $1${NC}"; }
warn()  { echo -e "    ${YELLOW}⚠ $1${NC}"; }
fail()  { echo -e "    ${RED}✖ $1${NC}"; }
info()  { echo -e "    ${BLUE}ℹ $1${NC}"; }
badge_local()  { echo -e "${GREEN}[local ]${NC}"; }
badge_remote() { echo -e "${YELLOW}[remote]${NC}"; }

header

# =============================================================
# STEP 1 — Ler services.conf
# =============================================================
step 1 "Lendo configuração de topologia (services.conf)..."

if [ ! -f "$CONF_FILE" ]; then
    fail "services.conf não encontrado em $ROOT_DIR"
    echo ""
    echo -e "  Crie o arquivo services.conf. Exemplo:"
    echo -e "  ${DIM}METRICS_API_MODE=local${NC}"
    echo -e "  ${DIM}CORE_API_MODE=local${NC}"
    echo -e "  ${DIM}ORACLE_MODE=local${NC}"
    exit 1
fi

# Carregar valores com defaults seguros
METRICS_API_MODE=$(grep    "^METRICS_API_MODE="    "$CONF_FILE" | cut -d'=' -f2 | tr -d ' ')
METRICS_API_PORT=$(grep    "^METRICS_API_PORT="    "$CONF_FILE" | cut -d'=' -f2 | tr -d ' ')
METRICS_API_REMOTE=$(grep  "^METRICS_API_REMOTE_URL=" "$CONF_FILE" | cut -d'=' -f2- | tr -d ' ')

CORE_API_MODE=$(grep       "^CORE_API_MODE="       "$CONF_FILE" | cut -d'=' -f2 | tr -d ' ')
CORE_API_PORT=$(grep       "^CORE_API_PORT="       "$CONF_FILE" | cut -d'=' -f2 | tr -d ' ')
CORE_API_REMOTE=$(grep     "^CORE_API_REMOTE_URL=" "$CONF_FILE" | cut -d'=' -f2- | tr -d ' ')

ORACLE_MODE=$(grep         "^ORACLE_MODE="         "$CONF_FILE" | cut -d'=' -f2 | tr -d ' ')

# Defaults
METRICS_API_MODE="${METRICS_API_MODE:-local}"
METRICS_API_PORT="${METRICS_API_PORT:-8000}"
CORE_API_MODE="${CORE_API_MODE:-local}"
CORE_API_PORT="${CORE_API_PORT:-8001}"
ORACLE_MODE="${ORACLE_MODE:-local}"

# Derivar URLs efetivas (usadas pelo Oracle e outros)
if [ "$METRICS_API_MODE" = "remote" ] && [ -n "$METRICS_API_REMOTE" ]; then
    EFFECTIVE_METRICS_URL="$METRICS_API_REMOTE"
else
    EFFECTIVE_METRICS_URL="http://metrics-api:${METRICS_API_PORT}"
fi

echo ""
echo -e "    ${BOLD}Topologia definida:${NC}"
printf  "    %-16s %s  %s\n" "metrics-api" "$([ "$METRICS_API_MODE" = "local" ] && badge_local || badge_remote)" "${METRICS_API_MODE}"
printf  "    %-16s %s  %s\n" "core-api"    "$([ "$CORE_API_MODE" = "local" ]    && badge_local || badge_remote)" "${CORE_API_MODE}"
printf  "    %-16s %s  %s\n" "oracle"      "$([ "$ORACLE_MODE" = "local" ]       && badge_local || badge_remote)" "${ORACLE_MODE}"

if [ "$METRICS_API_MODE" = "remote" ]; then
    info "Metrics API → $METRICS_API_REMOTE"
fi
if [ "$CORE_API_MODE" = "remote" ]; then
    info "Core API    → $CORE_API_REMOTE"
fi

# =============================================================
# STEP 2 — Criar .env a partir do template
# =============================================================
step 2 "Criando .env centralizado..."

if [ -f "$ENV_FILE" ] && [ "$1" != "--force" ]; then
    warn ".env já existe. Mantendo. Use --force para recriar."
else
    cp "$ROOT_DIR/.env.example" "$ENV_FILE"
    ok ".env criado a partir de .env.example."
fi

# =============================================================
# STEP 3 — Gerar APP_API_KEY compartilhada
# =============================================================
step 3 "Gerando APP_API_KEY compartilhada..."

CURRENT_KEY=$(grep "^APP_API_KEY=" "$ENV_FILE" | cut -d'=' -f2)

if [ "$CURRENT_KEY" = "CHANGE_ME" ] || [ -z "$CURRENT_KEY" ] || [ "$1" = "--force" ]; then
    SHARED_KEY=$(openssl rand -hex 16)
    sed -i "s|^APP_API_KEY=.*|APP_API_KEY=$SHARED_KEY|" "$ENV_FILE"
    ok "APP_API_KEY gerada: ${SHARED_KEY:0:8}..."
else
    ok "APP_API_KEY já configurada. Mantendo."
fi

# =============================================================
# STEP 4 — Sincronizar PROGRAM_ID + Gerar Oracle Keypair
# =============================================================
step 4 "Sincronizando configurações Solana..."

ANCHOR_TOML="$ROOT_DIR/programs_colosseum_Hackathon/Anchor.toml"
if [ -f "$ANCHOR_TOML" ]; then
    PROG_ID=$(grep -oP 'colosseum_hackathon = "\K[^"]+' "$ANCHOR_TOML" || true)
    if [ -n "$PROG_ID" ]; then
        sed -i "s|^PROGRAM_ID=.*|PROGRAM_ID=$PROG_ID|" "$ENV_FILE"
        ok "PROGRAM_ID sincronizado: $PROG_ID"
    else
        warn "Não foi possível extrair PROGRAM_ID do Anchor.toml."
    fi
else
    warn "Anchor.toml não encontrado. Configure PROGRAM_ID no .env."
fi

if [ "$ORACLE_MODE" = "local" ]; then
    CURRENT_PUB=$(grep "^ORACLE_PUBLIC_KEY=" "$ENV_FILE" | cut -d'=' -f2)
    if [ "$CURRENT_PUB" = "CHANGE_ME" ] || [ -z "$CURRENT_PUB" ] || [ "$1" = "--force" ]; then
        KEYGEN="$ROOT_DIR/AI_agente-Oracle_colosseum_Hackathon/scripts/generate_oracle_keypair.py"
        if [ -f "$KEYGEN" ]; then
            OUT=$(python3 "$KEYGEN" 2>/dev/null || true)
            PUB=$(echo "$OUT" | grep -i "public"  | grep -oP '[A-Za-z0-9]{32,}' | head -1 || true)
            PRIV=$(echo "$OUT" | grep -i "private" | grep -oP '[A-Za-z0-9]{32,}' | head -1 || true)
            if [ -n "$PUB" ] && [ -n "$PRIV" ]; then
                sed -i "s|^ORACLE_PUBLIC_KEY=.*|ORACLE_PUBLIC_KEY=$PUB|"   "$ENV_FILE"
                sed -i "s|^ORACLE_PRIVATE_KEY=.*|ORACLE_PRIVATE_KEY=$PRIV|" "$ENV_FILE"
                ok "Oracle Keypair gerado. Public: ${PUB:0:12}..."
            else
                warn "Keypair script rodou mas saída inesperada. Configure manualmente."
            fi
        else
            warn "generate_oracle_keypair.py não encontrado."
        fi
    else
        ok "Oracle Keypair já configurado. Mantendo."
    fi
else
    info "Oracle em modo remote — keypair não necessário localmente."
fi

# =============================================================
# STEP 5 — Gerar docker-compose.yaml
# =============================================================
step 5 "Gerando docker-compose.yaml..."

# Verifica se ao menos um serviço é local
LOCAL_SERVICES=()
[ "$METRICS_API_MODE" = "local" ] && LOCAL_SERVICES+=("metrics-api")
[ "$CORE_API_MODE"    = "local" ] && LOCAL_SERVICES+=("core-api")
[ "$ORACLE_MODE"      = "local" ] && LOCAL_SERVICES+=("oracle")

if [ ${#LOCAL_SERVICES[@]} -eq 0 ]; then
    warn "Nenhum serviço está configurado como local."
    warn "Todos os serviços são remote. Nenhum docker-compose.yaml será gerado."
    SKIP_COMPOSE=true
else
    SKIP_COMPOSE=false
fi

if [ "$SKIP_COMPOSE" = "false" ]; then

# Coletar quais serviços locais o oracle depende
ORACLE_DEPS=""
if [ "$ORACLE_MODE" = "local" ] && [ "$METRICS_API_MODE" = "local" ]; then
    ORACLE_DEPS="      metrics-api:\n        condition: service_healthy\n"
fi

# --- Início da geração do arquivo ---
cat > "$COMPOSE_FILE" <<'COMPOSE_HEADER'
# =============================================================
# SolCuts - Docker Compose (GERADO AUTOMATICAMENTE pelo setup.sh)
# NÃO EDITE MANUALMENTE — edite services.conf e rode ./setup.sh
# =============================================================

services:
COMPOSE_HEADER

# ---- Bloco: metrics-api (local) ----------------------------
if [ "$METRICS_API_MODE" = "local" ]; then
cat >> "$COMPOSE_FILE" <<METRICS
  # ---- Metrics API (YouTube / Social Media) ------------------
  metrics-api:
    build:
      context: ./Backend-views-Solana
      dockerfile: Dockerfile
    container_name: solcuts-metrics-api
    ports:
      - "${METRICS_API_PORT}:8000"
    environment:
      - YOUTUBE_API_KEY=\${YOUTUBE_API_KEY}
      - APP_API_KEY=\${APP_API_KEY}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
    restart: unless-stopped

METRICS
fi

# ---- Bloco: core-api (local) --------------------------------
if [ "$CORE_API_MODE" = "local" ]; then
cat >> "$COMPOSE_FILE" <<CORE
  # ---- Core API (Pools, Entries, Audit Logs) -----------------
  core-api:
    build:
      context: ./core-api
      dockerfile: Dockerfile
    container_name: solcuts-core-api
    ports:
      - "${CORE_API_PORT}:8001"
    environment:
      - DATABASE_URL=\${DATABASE_URL:-sqlite+aiosqlite:///./solcuts.db}
      - CORS_ORIGINS=\${CORS_ORIGINS:-["http://localhost:3000"]}
    volumes:
      - core-api-data:/app/data
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
    restart: unless-stopped

CORE
fi

# ---- Bloco: oracle (local) ----------------------------------
if [ "$ORACLE_MODE" = "local" ]; then

# Montar bloco depends_on apenas se metrics-api for local
DEPS_BLOCK=""
if [ "$METRICS_API_MODE" = "local" ]; then
DEPS_BLOCK="    depends_on:
      metrics-api:
        condition: service_healthy
"
fi

cat >> "$COMPOSE_FILE" <<ORACLE
  # ---- Oracle Agent (Validação + Solana CPI) -----------------
  oracle:
    build:
      context: ./AI_agente-Oracle_colosseum_Hackathon
      dockerfile: Dockerfile
    container_name: solcuts-oracle
${DEPS_BLOCK}    environment:
      - METRICS_API_URL=${EFFECTIVE_METRICS_URL}
      - APP_API_KEY=\${APP_API_KEY}
      - SOLANA_RPC_URL=\${SOLANA_RPC_URL:-https://api.devnet.solana.com}
      - PROGRAM_ID=\${PROGRAM_ID}
      - ORACLE_PUBLIC_KEY=\${ORACLE_PUBLIC_KEY}
      - ORACLE_PRIVATE_KEY=\${ORACLE_PRIVATE_KEY}
      - TRANSCRIPT_MIN_SCORE=\${TRANSCRIPT_MIN_SCORE:-0.70}
      - FRAME_SIMILARITY_THRESHOLD=\${FRAME_SIMILARITY_THRESHOLD:-0.70}
      - FRAME_MIN_MATCHES=\${FRAME_MIN_MATCHES:-3}
      - FRAME_TOTAL_SAMPLES=\${FRAME_TOTAL_SAMPLES:-5}
      - POLL_INTERVAL_SECONDS=\${POLL_INTERVAL_SECONDS:-300}
      - DATABASE_URL=\${ORACLE_DATABASE_URL:-sqlite:///oracle.db}
      - ALERT_WEBHOOK_URL=\${ALERT_WEBHOOK_URL:-}
    volumes:
      - oracle-data:/app/data
    restart: unless-stopped

ORACLE
fi

# ---- Volumes (apenas se algum serviço local usa volume) -----
VOLUMES_NEEDED=false
[ "$CORE_API_MODE" = "local" ]  && VOLUMES_NEEDED=true
[ "$ORACLE_MODE"   = "local" ]  && VOLUMES_NEEDED=true

if [ "$VOLUMES_NEEDED" = "true" ]; then
cat >> "$COMPOSE_FILE" <<VOLUMES
volumes:
VOLUMES
    [ "$CORE_API_MODE" = "local" ] && cat >> "$COMPOSE_FILE" <<COREVOL
  core-api-data:
    driver: local
COREVOL
    [ "$ORACLE_MODE" = "local" ] && cat >> "$COMPOSE_FILE" <<ORACLEVOL
  oracle-data:
    driver: local
ORACLEVOL
fi

ok "docker-compose.yaml gerado com sucesso."
info "Serviços locais : ${LOCAL_SERVICES[*]}"

fi # fi SKIP_COMPOSE

# =============================================================
# STEP 6 — Validar .env e mostrar resumo
# =============================================================
step 6 "Validando configuração..."

echo ""
echo -e "  ${BOLD}Resumo do .env:${NC}"
echo -e "  ─────────────────────────────────────────────"

check_var() {
    local var_name=$1
    local required=${2:-true}
    local val
    val=$(grep "^${var_name}=" "$ENV_FILE" | cut -d'=' -f2)
    if [ -z "$val" ] || [ "$val" = "CHANGE_ME" ]; then
        if [ "$required" = "true" ]; then
            echo -e "  ${RED}✖${NC} ${var_name} ${RED}← NECESSÁRIO${NC}"
            return 1
        else
            echo -e "  ${DIM}–${NC} ${var_name} ${DIM}(opcional)${NC}"
            return 0
        fi
    else
        local display="${val:0:22}"
        [ ${#val} -gt 22 ] && display="${display}..."
        echo -e "  ${GREEN}✔${NC} ${var_name} = ${display}"
        return 0
    fi
}

MISSING=0
check_var "APP_API_KEY"                                                || MISSING=$((MISSING+1))
[ "$METRICS_API_MODE" = "local" ] && { check_var "YOUTUBE_API_KEY"   || MISSING=$((MISSING+1)); }
check_var "SOLANA_RPC_URL"                                            || MISSING=$((MISSING+1))
check_var "PROGRAM_ID"                                                || MISSING=$((MISSING+1))
[ "$ORACLE_MODE" = "local" ] && { check_var "ORACLE_PUBLIC_KEY"      || MISSING=$((MISSING+1)); }
[ "$ORACLE_MODE" = "local" ] && { check_var "ORACLE_PRIVATE_KEY"     || MISSING=$((MISSING+1)); }
check_var "ALERT_WEBHOOK_URL" false

echo -e "  ─────────────────────────────────────────────"
echo ""

if [ $MISSING -gt 0 ]; then
    echo -e "  ${YELLOW}⚠  $MISSING variável(is) ainda precisam ser configuradas no .env${NC}"
    echo ""
fi

# =============================================================
# FINALIZAÇÃO
# =============================================================
echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  ${GREEN}Setup Concluído!${NC}                                  ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$SKIP_COMPOSE" = "false" ]; then
    echo -e "  ${BOLD}Para subir os serviços locais:${NC}"
    echo -e "  ${CYAN}docker compose up --build${NC}"
    echo ""
    echo -e "  ${BOLD}Serviços e portas:${NC}"
    [ "$METRICS_API_MODE" = "local" ] && echo -e "  ${GREEN}•${NC} metrics-api  → http://localhost:${METRICS_API_PORT}"
    [ "$METRICS_API_MODE" = "remote" ] && echo -e "  ${YELLOW}•${NC} metrics-api  → $METRICS_API_REMOTE ${DIM}(remote)${NC}"
    [ "$CORE_API_MODE" = "local" ]    && echo -e "  ${GREEN}•${NC} core-api     → http://localhost:${CORE_API_PORT}"
    [ "$CORE_API_MODE" = "remote" ]   && echo -e "  ${YELLOW}•${NC} core-api     → $CORE_API_REMOTE ${DIM}(remote)${NC}"
    [ "$ORACLE_MODE" = "local" ]      && echo -e "  ${GREEN}•${NC} oracle       → (worker, sem porta HTTP)"
    [ "$ORACLE_MODE" = "remote" ]     && echo -e "  ${YELLOW}•${NC} oracle       → (remote)${NC}"
else
    echo -e "  ${YELLOW}Todos os serviços são remote. Nenhum container para subir.${NC}"
fi

echo ""
echo -e "  ${DIM}Para alterar a topologia, edite services.conf e rode ./setup.sh novamente.${NC}"
echo ""
