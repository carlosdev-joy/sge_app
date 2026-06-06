#!/usr/bin/env bash
# =============================================================================
# dev-init-db.sh — Cria banco orquestra_dev e aplica schema completo
# =============================================================================
# Uso:
#   ./scripts/dev-init-db.sh                  # aplica scripts do repositório
#   ./scripts/dev-init-db.sh schema_prod.sql  # aplica schema exportado de prod
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

[ -f "$ENV_FILE" ] || error ".env.dev não encontrado."
set -a; source "$ENV_FILE"; set +a

SA_PASS="${DEV_MSSQL_SA_PASSWORD:-Orquestra@Dev2024}"
CONTAINER="orquestra-sqlserver-dev"
SQLCMD_BIN=$(docker exec "$CONTAINER" bash -c 'ls /opt/mssql-tools18/bin/sqlcmd 2>/dev/null || echo /opt/mssql-tools/bin/sqlcmd')
# -C = trust server certificate (required by sqlcmd 18+)
SQLCMD="docker exec $CONTAINER $SQLCMD_BIN -C -S localhost -U sa -P $SA_PASS"

# ── Função para executar SQL substituindo USE [DMDB41] pelo banco de dev ─────
run_sql_file() {
    local file="$1"
    local desc="$2"
    info "  → $desc"

    # Copia, substitui o banco e executa
    docker cp "$file" "$CONTAINER:/tmp/_current.sql"
    docker exec "$CONTAINER" bash -c "
        sed 's/USE \[DMDB41\]/USE [orquestra_dev]/gi; s/\[DMDB41\]\.\[dbo\]/[orquestra_dev].[dbo]/gi' /tmp/_current.sql > /tmp/_patched.sql && cp /tmp/_patched.sql /tmp/_current.sql
    "
    docker exec "$CONTAINER" bash -c "$SQLCMD_BIN -C -S localhost -U sa -P '$SA_PASS' -d orquestra_dev -i /tmp/_current.sql -b 2>&1 | grep -v '^$' | grep -v '^--'" || true
}

# ── Aguarda SQL Server ────────────────────────────────────────────────────────
info "Aguardando SQL Server..."
for i in $(seq 1 40); do
    if docker exec "$CONTAINER" bash -c "(/opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P '$SA_PASS' -Q 'SELECT 1' || /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P '$SA_PASS' -Q 'SELECT 1') &>/dev/null 2>&1"; then
        ok "SQL Server disponível."
        break
    fi
    [ "$i" -eq 40 ] && error "SQL Server não respondeu. Verifique: docker logs $CONTAINER"
    echo -n "."
    sleep 3
done

# ── Cria banco ────────────────────────────────────────────────────────────────
info "Criando banco orquestra_dev..."
$SQLCMD -Q "
IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = 'orquestra_dev')
    CREATE DATABASE [orquestra_dev];
" > /dev/null
ok "Banco criado."

# ── Aplica schema ─────────────────────────────────────────────────────────────
if [ -n "$SCHEMA_FILE" ] && [ -f "$SCHEMA_FILE" ]; then
    info "Aplicando schema externo: $SCHEMA_FILE"
    run_sql_file "$SCHEMA_FILE" "$(basename "$SCHEMA_FILE")"
    ok "Schema externo aplicado."
else
    echo ""
    info "Aplicando scripts do repositório..."

    # ORDEM IMPORTA: tabelas base → tabelas dependentes → procs → alterações → migrations

    # 1. Tabelas base
    info "1/5 Tabelas base..."
    for f in \
        "script/tabela/etl_pipeline.sql" \
        "script/tabela/etl_pipeline_job.sql" \
        "script/tabela/etl_job_execution.sql" \
        "script/tabela/etl_job_lineage.sql" \
        "script/tabela/etl_stage_type_map.sql" \
        "script/tabela/etl_pipeline_performance_snapshot.sql"
    do
        [ -f "$PROJECT_DIR/$f" ] && run_sql_file "$PROJECT_DIR/$f" "$(basename "$f")"
    done

    # 2. Tabelas de config e staging
    info "2/5 Tabelas de config e staging..."
    for f in \
        "script/proc/etl_app_config_tables.sql" \
        "script/proc/etl_seq_import_tables.sql" \
        "script/proc/etl_admin_sql.sql"
    do
        [ -f "$PROJECT_DIR/$f" ] && run_sql_file "$PROJECT_DIR/$f" "$(basename "$f")"
    done

    # 3. Stored procedures
    info "3/5 Stored procedures..."
    for f in \
        "script/proc/sp_etl_pipeline_upsert.sql" \
        "script/proc/sp_etl_pipeline_job_upsert.sql" \
        "script/proc/sp_etl_pipeline_job_reorder.sql" \
        "script/proc/sp_etl_job_execution_log.sql" \
        "script/proc/sp_etl_job_lineage_upsert.sql" \
        "script/proc/sp_etl_pipelines_pendentes_criar.sql" \
        "script/proc/fix_sp_etl_seq_import_approve.sql"
    do
        [ -f "$PROJECT_DIR/$f" ] && run_sql_file "$PROJECT_DIR/$f" "$(basename "$f")"
    done

    # 4. Alterações (em ordem cronológica)
    info "4/5 Alterações históricas..."
    for dir in $(ls -d "$PROJECT_DIR"/script/alteracoes/2* 2>/dev/null | sort); do
        # Prefere 000_deploy_all.sql se existir, senão aplica arquivo por arquivo
        if [ -f "$dir/000_deploy_all.sql" ]; then
            run_sql_file "$dir/000_deploy_all.sql" "$(basename "$dir")/000_deploy_all.sql"
        else
            for f in $(ls "$dir"/*.sql 2>/dev/null | sort); do
                run_sql_file "$f" "$(basename "$dir")/$(basename "$f")"
            done
        fi
    done
    for dir in $(ls -d "$PROJECT_DIR"/script/alteracoes/ui* 2>/dev/null | sort); do
        for f in $(ls "$dir"/*.sql 2>/dev/null | sort); do
            run_sql_file "$f" "$(basename "$dir")/$(basename "$f")"
        done
    done

    # 5. Migrations (novas colunas/tabelas adicionadas no branch atual)
    info "5/5 Migrations recentes..."
    for f in $(ls "$PROJECT_DIR"/sql/migrations/*.sql 2>/dev/null | sort); do
        run_sql_file "$f" "migrations/$(basename "$f")"
    done

    ok "Todos os scripts aplicados."
fi

# ── Cria usuário de aplicação ─────────────────────────────────────────────────
info "Criando usuário de aplicação..."
$SQLCMD -Q "
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'orquestra_app')
    CREATE LOGIN [orquestra_app] WITH PASSWORD = '$SA_PASS';
USE [orquestra_dev];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'orquestra_app')
BEGIN
    CREATE USER [orquestra_app] FOR LOGIN [orquestra_app];
    ALTER ROLE [db_owner] ADD MEMBER [orquestra_app];
END;
" > /dev/null 2>&1 || true
ok "Usuário orquestra_app criado."

# ── Resultado ─────────────────────────────────────────────────────────────────
VPS_IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${GREEN}${BOLD}✓ Banco de dev pronto!${NC}"
echo ""
echo -e "  ${BOLD}Servidor SSMS:${NC}  $VPS_IP,1433"
echo -e "  ${BOLD}Banco:${NC}          orquestra_dev"
echo -e "  ${BOLD}Usuário:${NC}        sa"
echo -e "  ${BOLD}Senha:${NC}          $SA_PASS"
echo ""
echo -e "  Para importar schema de prod depois:"
echo -e "  ${CYAN}./scripts/dev-init-db.sh /caminho/para/schema_prod.sql${NC}"
echo ""
