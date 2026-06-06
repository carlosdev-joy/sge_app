#!/usr/bin/env bash
# =============================================================================
# dev-init-db.sh — Cria o banco orquestra_dev e aplica o schema
# =============================================================================
# Uso:
#   ./scripts/dev-init-db.sh                  # aplica migrations do repositório
#   ./scripts/dev-init-db.sh schema_prod.sql  # aplica schema exportado de prod
#
# Pré-requisito: container sqlserver-dev rodando (docker compose ... up -d)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env.dev"
SCHEMA_FILE="${1:-}"

cd "$PROJECT_DIR"

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'; BOLD='\033[1m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

[ -f "$ENV_FILE" ] || error ".env.dev não encontrado. Execute dev-setup.sh primeiro."
set -a; source "$ENV_FILE"; set +a

SA_PASS="${DEV_MSSQL_SA_PASSWORD:-Orquestra@Dev2024}"
CONTAINER="orquestra-sqlserver-dev"

# ── Aguarda SQL Server estar pronto ──────────────────────────────────────────
info "Aguardando SQL Server ficar disponível..."
for i in $(seq 1 30); do
    if docker exec "$CONTAINER" /opt/mssql-tools/bin/sqlcmd \
        -S localhost -U sa -P "$SA_PASS" -Q "SELECT 1" &>/dev/null; then
        ok "SQL Server disponível."
        break
    fi
    [ "$i" -eq 30 ] && error "SQL Server não respondeu após 30 tentativas."
    echo -n "."
    sleep 3
done

# ── Cria o banco orquestra_dev ───────────────────────────────────────────────
info "Criando banco de dados orquestra_dev..."
docker exec "$CONTAINER" /opt/mssql-tools/bin/sqlcmd \
    -S localhost -U sa -P "$SA_PASS" \
    -Q "IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = 'orquestra_dev')
        CREATE DATABASE [orquestra_dev];"
ok "Banco orquestra_dev pronto."

# ── Aplica schema ─────────────────────────────────────────────────────────────
if [ -n "$SCHEMA_FILE" ] && [ -f "$SCHEMA_FILE" ]; then
    info "Aplicando schema de produção: $SCHEMA_FILE"
    docker cp "$SCHEMA_FILE" "$CONTAINER:/tmp/schema.sql"
    docker exec "$CONTAINER" /opt/mssql-tools/bin/sqlcmd \
        -S localhost -U sa -P "$SA_PASS" \
        -d orquestra_dev \
        -i /tmp/schema.sql \
        -b
    ok "Schema de produção aplicado."
else
    # Aplica migrations do repositório
    info "Aplicando migrations do repositório..."
    for migration in "$PROJECT_DIR"/sql/migrations/*.sql; do
        [ -f "$migration" ] || continue
        fname="$(basename "$migration")"
        info "  → $fname"
        docker cp "$migration" "$CONTAINER:/tmp/migration.sql"
        docker exec "$CONTAINER" /opt/mssql-tools/bin/sqlcmd \
            -S localhost -U sa -P "$SA_PASS" \
            -d orquestra_dev \
            -i /tmp/migration.sql \
            -b \
            2>&1 || warn "  Aviso em $fname (pode ser objeto já existente)"
    done
    ok "Migrations aplicadas."
fi

# ── Cria usuário de aplicação (opcional) ─────────────────────────────────────
info "Criando login de aplicação 'orquestra_app'..."
docker exec "$CONTAINER" /opt/mssql-tools/bin/sqlcmd \
    -S localhost -U sa -P "$SA_PASS" \
    -Q "
    IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'orquestra_app')
    BEGIN
        CREATE LOGIN [orquestra_app] WITH PASSWORD = '$SA_PASS';
    END;
    USE [orquestra_dev];
    IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'orquestra_app')
    BEGIN
        CREATE USER [orquestra_app] FOR LOGIN [orquestra_app];
        ALTER ROLE [db_owner] ADD MEMBER [orquestra_app];
    END;
    " 2>/dev/null || true

echo ""
echo -e "${GREEN}${BOLD}✓ Banco de dev pronto!${NC}"
echo ""
echo -e "  ${BOLD}Servidor:${NC}  IP-DA-VPS,1433"
echo -e "  ${BOLD}Banco:${NC}     orquestra_dev"
echo -e "  ${BOLD}Usuário:${NC}   sa"
echo -e "  ${BOLD}Senha:${NC}     $SA_PASS"
echo ""
echo -e "  Para conectar via SSMS: ${CYAN}IP-DA-VPS,1433${NC}"
echo ""
echo -e "  Para aplicar schema de prod quando tiver:"
echo -e "  ${CYAN}./scripts/dev-init-db.sh /caminho/schema_prod.sql${NC}"
echo ""
