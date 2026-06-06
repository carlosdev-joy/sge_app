#!/usr/bin/env bash
# =============================================================================
# dev-update.sh — Atualiza o ambiente de dev com o último código da branch
# =============================================================================
# Uso:
#   ./scripts/dev-update.sh [BRANCH]
#
# O que faz:
#   1. git pull da branch atual (ou da branch especificada)
#   2. Reconstrói a imagem se o Dockerfile mudou
#   3. Reinicia apenas os containers afetados
# =============================================================================

set -euo pipefail

BRANCH="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env.dev"

cd "$PROJECT_DIR"

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'; BOLD='\033[1m'
info() { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}    $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }

[ -f "$ENV_FILE" ] || { warn ".env.dev não encontrado. Execute ./scripts/dev-setup.sh primeiro."; exit 1; }
set -a; source "$ENV_FILE"; set +a

echo -e "${BOLD}ORQUESTRA — Atualização Dev${NC}"

# ── Git pull ────────────────────────────────────────────────────────────────
if [ -n "$BRANCH" ]; then
    info "Trocando para branch: $BRANCH"
    git fetch origin "$BRANCH"
    git checkout "$BRANCH"
fi

CURRENT_BRANCH="$(git branch --show-current)"
info "Pull da branch: $CURRENT_BRANCH"
git pull origin "$CURRENT_BRANCH"
ok "Código atualizado: $(git log -1 --format='%h %s')"

# ── Rebuild se Dockerfile mudou ─────────────────────────────────────────────
if git diff HEAD~1 --name-only 2>/dev/null | grep -q "^Dockerfile\|^requirements"; then
    info "Dockerfile modificado — rebuild da imagem..."
    docker compose \
        -f docker-compose.yaml \
        -f docker-compose.dev.yaml \
        --env-file "$ENV_FILE" \
        build --quiet
    ok "Imagem reconstruída."
fi

# ── Reinicia os serviços com o novo código ──────────────────────────────────
info "Reiniciando serviços..."
docker compose \
    -f docker-compose.yaml \
    -f docker-compose.dev.yaml \
    --env-file "$ENV_FILE" \
    up -d --remove-orphans

ok "Ambiente atualizado."
echo ""
echo -e "  ${BOLD}UI:${NC}     http://$(hostname -I | awk '{print $1}'):8081"
echo -e "  ${BOLD}Branch:${NC} $CURRENT_BRANCH"
echo ""
