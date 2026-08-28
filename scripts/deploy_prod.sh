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

UIREACT_CHANGED=false
COMPOSE_CHANGED=false

echo "$CHANGED_FILES" | grep -q "^api/"      && API_CHANGED=true  || true
echo "$CHANGED_FILES" | grep -q "^ui/"       && UI_CHANGED=true   || true
echo "$CHANGED_FILES" | grep -q "^ui-react/dist/" && UIREACT_CHANGED=true || true
echo "$CHANGED_FILES" | grep -q "^dags/"     && DAGS_CHANGED=true || true
# ⚠️ .py em SUBPASTA de dags/ (utils/, Orquestrador/…) é MÓDULO, não DAG.
# O arquivo da DAG o DagBag reprocessa a cada execução — chega a apagá-lo de
# `sys.modules` antes. O `from utils.x import y` lá dentro é import comum: se o
# módulo já está no `sys.modules` do processo do worker Celery, o import
# devolve a versão EM MEMÓRIA, e os forks herdam esse cache.
# Mordeu em 2026-08-13 (PR #312, que mexia SÓ em dags/utils/): três ciclos do
# sync rodaram depois do deploy — todos VERDES, log impecável — gravando pelo
# código antigo. Uma hora e meia para achar um módulo em cache.
MODULO_CHANGED=false
echo "$CHANGED_FILES" | grep -qE "^dags/.+/.+\.py$" && MODULO_CHANGED=true || true
echo "$CHANGED_FILES" | grep -q "^sql/migrations/" && SQL_CHANGED=true || true
# Mudança na definição de infra (volumes/portas/imagem) exige recriar o container.
echo "$CHANGED_FILES" | grep -q "^docker-compose.ya\?ml$" && COMPOSE_CHANGED=true || true

echo "      api/            mudou: $API_CHANGED"
echo "      ui/             mudou: $UI_CHANGED"
echo "      ui-react/dist/  mudou: $UIREACT_CHANGED"
echo "      dags/           mudou: $DAGS_CHANGED"
echo "      dags/*/*.py     mudou: $MODULO_CHANGED  (modulo auxiliar — worker cacheia)"
echo "      migrations/     mudou: $SQL_CHANGED"
echo "      docker-compose  mudou: $COMPOSE_CHANGED"
echo ""

# ── 3. Rebuild e restart ──────────────────────────────────────
echo "[3/4] Aplicando mudanças nos containers..."

if [ "$API_CHANGED" = "true" ]; then
  echo "      → Rebuild orquestra-api..."
  docker compose build orquestra-api
  docker compose up -d --no-deps orquestra-api
  echo "      ✓ orquestra-api reiniciado"
fi

# nginx serve UI legada (ui/) e a UI React (ui-react/dist) por volume.
# - Conteúdo de ui/ ou ui-react/dist mudou  → restart simples (bind mount reflete vivo).
# - docker-compose.yaml mudou (volumes/portas/imagem) → precisa --force-recreate,
#   pois o Docker só aplica nova definição de infra recriando o container.
if [ "$COMPOSE_CHANGED" = "true" ]; then
  echo "      → docker-compose mudou — recriando ui-nginx (--force-recreate)"
  docker compose up -d --no-deps --force-recreate ui-nginx
  echo "      ✓ ui-nginx recriado com a nova definição"
elif [ "$UI_CHANGED" = "true" ] || [ "$UIREACT_CHANGED" = "true" ]; then
  echo "      → UI servida por volume — restart do nginx (sem rebuild)"
  docker compose up -d --no-deps ui-nginx
  echo "      ✓ ui-nginx reiniciado"
fi

if [ "$DAGS_CHANGED" = "true" ]; then
  echo "      → Arquivos de DAG atualizados via volume — o scheduler reprocessa"
  echo "        sozinho a cada execução."
fi

# ⚠️ ESTA SEÇÃO CORRIGE UMA AFIRMAÇÃO FALSA. Até 2026-08-28 o script dizia
# "nenhum restart necessário" para QUALQUER mudança em dags/ — o que é verdade
# para o arquivo da DAG e MENTIRA para os módulos que ela importa. O
# `/opt/git/deploy.sh` já tratava isso corretamente desde a #313; ter dois
# scripts com conselhos opostos é pior que não ter o segundo.
if [ "$MODULO_CHANGED" = "true" ]; then
  echo ""
  echo "  ╔══════════════════════════════════════════════════════════════╗"
  echo "  ║  MODULO AUXILIAR MUDOU — o worker Celery serve de CACHE      ║"
  echo "  ╚══════════════════════════════════════════════════════════════╝"
  echo "$CHANGED_FILES" | grep -E "^dags/.+/.+\.py$" | sed 's/^/      /'
  echo ""
  echo "      Sem reiniciar o worker, a task roda VERDE com o codigo ANTIGO."
  echo ""
  echo "      Tasks em execucao AGORA (o que o restart derruba):"
  ATIVAS=$(docker compose exec -T airflow-worker \
             celery -A airflow.providers.celery.executors.celery_executor.app \
             inspect active 2>/dev/null | grep -c "task_id" || echo "?")
  if [ "$ATIVAS" = "?" ]; then
    echo "        (nao foi possivel consultar — confira ANTES de reiniciar)"
  elif [ "$ATIVAS" = "0" ]; then
    echo "        nenhuma — o worker esta ocioso, o restart e inofensivo."
  else
    echo "        $ATIVAS task(s) — o restart as INTERROMPE."
  fi
  echo ""
  # Padrao NAO reinicia: derruba task em execucao. Regra da casa — acao
  # destrutiva pede confirmacao explicita.
  read -r -p "      Reiniciar o airflow-worker agora? [s/N] " RESP
  case "$RESP" in
    [sS]|[sS][iI][mM])
      docker compose restart airflow-worker
      echo "      ✓ airflow-worker reiniciado"
      ;;
    *)
      echo "      ⚠ NAO reiniciado. Rode quando puder:"
      echo "          docker compose restart airflow-worker"
      echo "        Ate la, as DAGs rodam com o codigo ANTIGO destes modulos."
      ;;
  esac
fi

if [ "$API_CHANGED" = "false" ] && [ "$UI_CHANGED" = "false" ] \
   && [ "$UIREACT_CHANGED" = "false" ] && [ "$DAGS_CHANGED" = "false" ] \
   && [ "$COMPOSE_CHANGED" = "false" ]; then
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
          echo "    sqlcmd -b -I -S <SERVIDOR> -d <BANCO> -i $REPO_DIR/$f"
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
      echo "    sqlcmd -b -I -S <SERVIDOR> -d <BANCO> -i $REPO_DIR/$f"
    done
    echo ""
  fi
  echo ""
else
  echo "      Nenhuma migration nova."
fi

# ── Checagem: chave das senhas de dbo.etl_conexao (migration 054) ─────
# Sem a chave, a tela Conexões de Dados e a resolução de conexões nas DAGs
# de cópia falham com mensagem clara. Mesmo valor para api e Airflow.
if ! grep -q "^ORQUESTRA_CONN_KEY=" "$REPO_DIR/.env" 2>/dev/null; then
  echo ""
  echo "  ⚠ ORQUESTRA_CONN_KEY ausente no $REPO_DIR/.env — gere e adicione:"
  echo "    python3 -c \"from cryptography.fernet import Fernet; print('ORQUESTRA_CONN_KEY=' + Fernet.generate_key().decode())\" >> $REPO_DIR/.env"
  echo "    (depois recrie orquestra-api e os containers do Airflow para carregar a variável)"
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
