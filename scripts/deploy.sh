#!/bin/bash
# =============================================================
# deploy.sh — Deploy do ORQUESTRA a partir do GitHub
#
# Localização no servidor: /opt/git/deploy.sh
# Uso: bash /opt/git/deploy.sh
# =============================================================
set -e

REPO_URL="https://github.com/carlosdev-joy/sge_app.git"
BRANCH="main"
TMP_DIR="/opt/git/checkout_tmp"
AIRFLOW_DIR="/opt/airflow"

echo "[DEPLOY] Iniciando deploy — $(date '+%Y-%m-%d %H:%M:%S')"

# ── 1. Clonar repositório ─────────────────────────────────────
rm -rf "$TMP_DIR"
git clone --depth=1 --branch "$BRANCH" "$REPO_URL" "$TMP_DIR"

COMMIT=$(git -C "$TMP_DIR" log -1 --format="%h %s (%ai)")
echo "[DEPLOY] Commit: $COMMIT"

# ── 2. UI React (única interface — servida na raiz /) ─────────
mkdir -p "$AIRFLOW_DIR/ui-react/dist"
rsync -av --delete "$TMP_DIR/ui-react/dist/" "$AIRFLOW_DIR/ui-react/dist/"
echo "[DEPLOY] ✓ ui-react/dist sincronizado"

# ── 3. Config (nginx.conf, webserver_config) ──────────────────
rsync -av "$TMP_DIR/config/" "$AIRFLOW_DIR/config/"
echo "[DEPLOY] ✓ config/ sincronizado"

# ── 3. DAGs ───────────────────────────────────────────────────
rsync -av "$TMP_DIR/dags/" "$AIRFLOW_DIR/dags/"
chown -R airflow:airflow "$AIRFLOW_DIR/dags/"
chmod -R 777 "$AIRFLOW_DIR/dags/"

# ── 4. Docker Compose ─────────────────────────────────────────
cp "$TMP_DIR/docker-compose.yaml" "$AIRFLOW_DIR/docker-compose.yaml"

# ── 5. API — rebuild se houve mudança ─────────────────────────
rsync -av "$TMP_DIR/api/" "$AIRFLOW_DIR/api/"

cd "$AIRFLOW_DIR"
echo "[DEPLOY] Rebuilding orquestra-api..."
docker compose build orquestra-api
docker compose up -d --no-deps orquestra-api
echo "[DEPLOY] ✓ orquestra-api atualizado"

# ── 6. Nginx — recria para aplicar a definição de volumes do compose ─
# IMPORTANTE: 'docker restart' NÃO aplica novos volumes/portas do compose.
# --force-recreate garante isso mesmo sem mudança de imagem.
docker compose up -d --no-deps --force-recreate ui-nginx
echo "[DEPLOY] ✓ ui-nginx recriado (volumes do compose aplicados)"

# ── 7. Limpeza ────────────────────────────────────────────────
rm -rf "$TMP_DIR"

echo ""
echo "[DEPLOY] ✓ Concluído em $(date '+%Y-%m-%d %H:%M:%S')"
echo "[DEPLOY] ✓ Deploy concluído com sucesso"
echo ""
echo "  Verificar:"
echo "    docker compose ps"
echo "    curl -s http://localhost/orquestra/health"
