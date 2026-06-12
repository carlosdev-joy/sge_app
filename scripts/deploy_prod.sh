#!/bin/bash
# =============================================================
# deploy_prod.sh — Atualiza produção a partir da main do git
#
# Uso:
#   cd /opt/airflow          # pasta raiz do projeto
#   bash scripts/deploy_prod.sh
#
# O que faz:
#   1. git pull origin main
#   2. Rebuild do container orquestra-api (apenas se api/ mudou)
#   3. Restart dos serviços afetados (sem downtime do Airflow)
#   4. Instruções manuais para migração SQL (quando necessário)
# =============================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

echo ""
echo "============================================="
echo " ORQUESTRA — Deploy Produção"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================="
echo ""

# ── 1. Git pull ───────────────────────────────────────────────
echo "[1/4] Atualizando repositório..."
git fetch origin main
BEFORE=$(git rev-parse HEAD)
git pull origin main --ff-only
AFTER=$(git rev-parse HEAD)

if [ "$BEFORE" = "$AFTER" ]; then
  echo "      Nada de novo — já está na versão mais recente."
  echo ""
fi

echo "      Commits aplicados:"
git log --oneline "$BEFORE".."$AFTER" | sed 's/^/        /'
echo ""

# ── 2. Detectar o que mudou ───────────────────────────────────
echo "[2/4] Verificando o que mudou..."

CHANGED_FILES=$(git diff --name-only "$BEFORE" "$AFTER" 2>/dev/null || echo "")

API_CHANGED=false
UI_CHANGED=false
DAGS_CHANGED=false
SQL_CHANGED=false

echo "$CHANGED_FILES" | grep -q "^api/"      && API_CHANGED=true  || true
echo "$CHANGED_FILES" | grep -q "^ui/"       && UI_CHANGED=true   || true
echo "$CHANGED_FILES" | grep -q "^dags/"     && DAGS_CHANGED=true || true
echo "$CHANGED_FILES" | grep -q "^sql/migrations/" && SQL_CHANGED=true || true

echo "      api/        mudou: $API_CHANGED"
echo "      ui/         mudou: $UI_CHANGED"
echo "      dags/       mudou: $DAGS_CHANGED"
echo "      migrations/ mudou: $SQL_CHANGED"
echo ""

# ── 3. Rebuild e restart ──────────────────────────────────────
echo "[3/4] Aplicando mudanças nos containers..."

if [ "$API_CHANGED" = "true" ]; then
  echo "      → Rebuild orquestra-api..."
  docker compose build orquestra-api
  docker compose up -d --no-deps orquestra-api
  echo "      ✓ orquestra-api reiniciado"
elif [ "$UI_CHANGED" = "true" ]; then
  echo "      → UI mudou mas é servida por volume — nginx não precisa rebuild"
  docker compose restart ui-nginx
  echo "      ✓ ui-nginx reiniciado"
fi

if [ "$DAGS_CHANGED" = "true" ]; then
  echo "      → DAGs atualizadas via volume — scheduler pega automaticamente"
  echo "        (nenhum restart necessário)"
fi

if [ "$API_CHANGED" = "false" ] && [ "$UI_CHANGED" = "false" ] && [ "$DAGS_CHANGED" = "false" ]; then
  echo "      Nenhum container precisa de restart."
fi
echo ""

# ── 4. Migrações SQL pendentes ────────────────────────────────
echo "[4/4] Verificando migrações SQL..."

if [ "$SQL_CHANGED" = "true" ]; then
  echo ""
  echo "  Migrações SQL detectadas. Tentando aplicar via sql/migrate.py..."
  echo ""

  # Tenta usar migrate.py (requer MSSQL_CONN_STR no ambiente ou no .env)
  if [ -f "$REPO_DIR/sql/migrate.py" ] && python3 -c "import pyodbc" 2>/dev/null; then
    if python3 "$REPO_DIR/sql/migrate.py" --status 2>/dev/null | grep -q "PENDENTE"; then
      echo "  Aplicando migrations pendentes..."
      if python3 "$REPO_DIR/sql/migrate.py"; then
        echo "  ✓ Migrations aplicadas com sucesso."
      else
        echo ""
        echo "  ╔══════════════════════════════════════════════════════╗"
        echo "  ║  ERRO ao aplicar migrations — execute manualmente    ║"
        echo "  ╚══════════════════════════════════════════════════════╝"
        echo ""
        echo "  Comando alternativo:"
        echo "    MSSQL_CONN_STR=\"...\" python3 $REPO_DIR/sql/migrate.py"
        echo ""
        echo "  Ou via sqlcmd (arquivos novos detectados):"
        git diff --name-only "$BEFORE" "$AFTER" | grep "^sql/migrations/" | while read f; do
          echo "    sqlcmd -S <SERVIDOR> -d <BANCO> -i $REPO_DIR/$f"
        done
      fi
    else
      echo "  ✓ Nenhuma migration pendente (todas já aplicadas)."
    fi
  else
    # Fallback: instrução manual
    echo "  ╔══════════════════════════════════════════════════════╗"
    echo "  ║  Aplique as migrations manualmente (pyodbc ausente)  ║"
    echo "  ╚══════════════════════════════════════════════════════╝"
    echo ""
    echo "  Opção 1 — migrate.py (recomendado, offline):"
    echo "    MSSQL_CONN_STR=\"DSN=...\" python3 $REPO_DIR/sql/migrate.py"
    echo ""
    echo "  Opção 2 — sqlcmd por arquivo:"
    git diff --name-only "$BEFORE" "$AFTER" | grep "^sql/migrations/" | while read f; do
      echo "    sqlcmd -S <SERVIDOR> -d <BANCO> -i $REPO_DIR/$f"
    done
    echo ""
  fi
  echo ""
else
  echo "      Nenhuma migration nova."
fi

# ── Status final ──────────────────────────────────────────────
echo ""
echo "============================================="
echo " Deploy concluído — $(date '+%H:%M:%S')"
echo " Versão: $(git rev-parse --short HEAD)"
echo "============================================="
echo ""
echo "  Verificar saúde:"
echo "    docker compose ps"
echo "    curl -s http://localhost/orquestra/health | python3 -m json.tool"
echo ""
