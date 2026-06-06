#!/usr/bin/env bash
# =============================================================================
# dev-setup.sh — Configura o ambiente de DESENVOLVIMENTO do ORQUESTRA na VPS
# =============================================================================
# Uso:
#   chmod +x scripts/dev-setup.sh
#   ./scripts/dev-setup.sh [BRANCH]
#
# Exemplos:
#   ./scripts/dev-setup.sh                          # usa a branch atual
#   ./scripts/dev-setup.sh claude/peaceful-planck-5Hg5k
#   ./scripts/dev-setup.sh develop
#
# Pré-requisitos na VPS:
#   - Docker + Docker Compose v2
#   - Git
#   - Acesso de rede ao servidor MSSQL de dev
# =============================================================================

set -euo pipefail

BRANCH="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env.dev"

cd "$PROJECT_DIR"

# ── Cores ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════╗"
echo "║   ORQUESTRA — Setup Ambiente de Dev          ║"
echo "╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# ── 1. Verificações de pré-requisitos ────────────────────────────────────────
info "Verificando pré-requisitos..."
command -v docker  >/dev/null 2>&1 || error "Docker não encontrado. Instale o Docker primeiro."
command -v git     >/dev/null 2>&1 || error "Git não encontrado."
docker compose version >/dev/null 2>&1 || error "Docker Compose v2 não encontrado."
ok "Docker $(docker --version | awk '{print $3}' | tr -d ',') | Compose $(docker compose version --short)"

# ── 2. Branch ────────────────────────────────────────────────────────────────
if [ -n "$BRANCH" ]; then
    info "Checkout da branch: $BRANCH"
    git fetch origin "$BRANCH" 2>/dev/null || warn "Branch '$BRANCH' não encontrada no remote."
    git checkout "$BRANCH" 2>/dev/null || error "Não foi possível fazer checkout da branch '$BRANCH'."
    git pull origin "$BRANCH" 2>/dev/null || warn "Não foi possível fazer pull. Verifique a conexão."
    ok "Branch: $(git branch --show-current)"
else
    ok "Branch atual: $(git branch --show-current)"
fi

# ── 3. Arquivo .env.dev ──────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
    warn ".env.dev não encontrado. Criando a partir do template..."
    cp "$PROJECT_DIR/.env.dev.example" "$ENV_FILE"
    echo ""
    echo -e "${YELLOW}╔══════════════════════════════════════════════════════════════╗"
    echo    "║  ATENÇÃO: Edite o arquivo .env.dev antes de continuar!       ║"
    echo    "║  Configure especialmente DEV_MSSQL_CONN com o banco de dev.  ║"
    echo    "╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${CYAN}nano $ENV_FILE${NC}"
    echo ""
    read -rp "Pressione ENTER após editar .env.dev (ou Ctrl+C para cancelar)..."
fi

# Carrega variáveis do .env.dev
set -a; source "$ENV_FILE"; set +a
ok ".env.dev carregado"

# ── 4. Diretórios necessários ────────────────────────────────────────────────
info "Criando diretórios..."
mkdir -p logs plugins dsx
ok "Diretórios: logs/ plugins/ dsx/"

# ── 5. AIRFLOW_UID ──────────────────────────────────────────────────────────
if ! grep -q "^AIRFLOW_UID=" "$ENV_FILE" 2>/dev/null; then
    echo "AIRFLOW_UID=$(id -u)" >> "$ENV_FILE"
fi
ok "AIRFLOW_UID=$(id -u)"

# ── 6. Build da imagem ───────────────────────────────────────────────────────
info "Build da imagem Docker (pode demorar na primeira vez)..."
docker compose \
    -f docker-compose.yaml \
    -f docker-compose.dev.yaml \
    --env-file "$ENV_FILE" \
    build --quiet
ok "Imagem construída."

# ── 7. Inicialização do banco do Airflow ─────────────────────────────────────
info "Inicializando banco do Airflow..."
docker compose \
    -f docker-compose.yaml \
    -f docker-compose.dev.yaml \
    --env-file "$ENV_FILE" \
    up airflow-init --wait
ok "Banco inicializado."

# ── 8. Subindo os serviços ────────────────────────────────────────────────────
info "Subindo todos os serviços..."
docker compose \
    -f docker-compose.yaml \
    -f docker-compose.dev.yaml \
    --env-file "$ENV_FILE" \
    up -d --remove-orphans
ok "Serviços no ar."

# ── 9. Status final ───────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}✓ Ambiente de desenvolvimento ativo!${NC}"
echo ""
echo -e "  ${BOLD}UI:${NC}              http://$(hostname -I | awk '{print $1}'):8081"
echo -e "  ${BOLD}Airflow:${NC}         http://$(hostname -I | awk '{print $1}'):8082"
echo -e "  ${BOLD}Usuário Airflow:${NC} ${DEV_AIRFLOW_USER:-admin}"
echo -e "  ${BOLD}Branch:${NC}          $(git branch --show-current)"
echo ""
echo -e "  Para parar:    ${CYAN}./scripts/dev-down.sh${NC}"
echo -e "  Para atualizar:${CYAN}./scripts/dev-update.sh${NC}"
echo ""
