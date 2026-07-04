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
SELF="/opt/git/deploy.sh"

echo "[DEPLOY] Iniciando deploy — $(date '+%Y-%m-%d %H:%M:%S')"

# ── 1. Clonar repositório ─────────────────────────────────────
# Na primeira execução clona normalmente.
# No restart pós-atualização (_DEPLOY_UPDATED=1) o TMP_DIR já existe,
# então pula o clone para não refazer o trabalho.
if [ -z "$_DEPLOY_UPDATED" ]; then
    rm -rf "$TMP_DIR"
    git clone --depth=1 --branch "$BRANCH" "$REPO_URL" "$TMP_DIR"
fi

COMMIT=$(git -C "$TMP_DIR" log -1 --format="%h %s (%ai)")
echo "[DEPLOY] Commit: $COMMIT"

# ── 2. Auto-atualização do script ─────────────────────────────
# Compara o arquivo em execução com scripts/deploy.sh do repo.
# Se forem diferentes: copia, exporta a flag e faz 'exec' — que
# substitui o processo atual pelo novo script (sem criar filho).
# A flag _DEPLOY_UPDATED impede loop infinito: no restart o bloco
# é ignorado e o deploy continua normalmente.
if [ -z "$_DEPLOY_UPDATED" ] && ! cmp -s "$TMP_DIR/scripts/deploy.sh" "$SELF"; then
    echo "[DEPLOY] Nova versão do script detectada — aplicando e reiniciando..."
    cp "$TMP_DIR/scripts/deploy.sh" "$SELF"
    export _DEPLOY_UPDATED=1
    exec bash "$SELF"
fi

# ── 3. UI React (única interface — servida na raiz /) ─────────
mkdir -p "$AIRFLOW_DIR/ui-react/dist"
rsync -av --delete "$TMP_DIR/ui-react/dist/" "$AIRFLOW_DIR/ui-react/dist/"
echo "[DEPLOY] ✓ ui-react/dist sincronizado"

# ── 4. Config (nginx.conf, webserver_config) ──────────────────
rsync -av "$TMP_DIR/config/" "$AIRFLOW_DIR/config/"
echo "[DEPLOY] ✓ config/ sincronizado"

# ── 5. DAGs ───────────────────────────────────────────────────
# generated/ é criado em runtime pelo Airflow — nunca sobrescrever
rsync -av --exclude=generated/ "$TMP_DIR/dags/" "$AIRFLOW_DIR/dags/"
chown -R airflow:airflow "$AIRFLOW_DIR/dags/"
chmod -R 777 "$AIRFLOW_DIR/dags/"
echo "[DEPLOY] ✓ dags/ sincronizado"

# ── 6. Docker Compose ─────────────────────────────────────────
cp "$TMP_DIR/docker-compose.yaml" "$AIRFLOW_DIR/docker-compose.yaml"

# ── 6b. Insumos do build da imagem Airflow ────────────────────
# O rebuild da imagem (bcp/ODBC do módulo Cópia de Dados) é 100% offline e
# precisa, NO SERVIDOR, do Dockerfile da raiz e dos .deb vendorados em
# docker/debs. O build em si continua manual/raro (exige janela sem jobs);
# aqui só garantimos que os arquivos existam quando ele for feito.
cp "$TMP_DIR/Dockerfile" "$AIRFLOW_DIR/Dockerfile"
rsync -av "$TMP_DIR/docker/" "$AIRFLOW_DIR/docker/"
echo "[DEPLOY] ✓ Dockerfile + docker/ (debs) sincronizados"

# ── 7. API — rebuild com wheels locais (sem internet) ─────────
rsync -av "$TMP_DIR/api/" "$AIRFLOW_DIR/api/"

cd "$AIRFLOW_DIR"
echo "[DEPLOY] Rebuilding orquestra-api..."
docker compose build orquestra-api
docker compose up -d --no-deps orquestra-api
echo "[DEPLOY] ✓ orquestra-api atualizado"

# ── 8. Nginx — recria para aplicar a definição de volumes do compose ─
# IMPORTANTE: 'docker restart' NÃO aplica novos volumes/portas do compose.
# --force-recreate garante isso mesmo sem mudança de imagem.
docker compose up -d --no-deps --force-recreate ui-nginx
echo "[DEPLOY] ✓ ui-nginx recriado (volumes do compose aplicados)"

# ── 8b. Imagem/containers do Airflow (OPCIONAL — pergunta) ────
# Recriar webserver/scheduler/worker/triggerer INTERROMPE jobs em execução,
# então NUNCA é automático: o padrão é NÃO (Enter, ou execução sem terminal),
# e o deploy segue tocando só api/nginx, como sempre. Responda 's' apenas em
# janela sem jobs — necessário para aplicar imagem nova (bcp/ODBC) ou env
# nova nos containers (ex.: ORQUESTRA_CONN_KEY do .env).
RESP_AIRFLOW="n"
if [ -t 0 ]; then
    read -r -p "[DEPLOY] Rebuildar a imagem do Airflow e RECRIAR os containers agora? (interrompe jobs em execucao) [s/N] " RESP_AIRFLOW || RESP_AIRFLOW="n"
fi
case "$RESP_AIRFLOW" in
    [sS]*)
        cd "$AIRFLOW_DIR"
        if docker image inspect apache/airflow:2.11.2 >/dev/null 2>&1; then
            # Base oficial presente no host → build canônico do Dockerfile da
            # raiz. Builder clássico: o servidor NÃO alcança o Docker Hub e o
            # BuildKit tenta resolver a base no registry mesmo com ela local.
            echo "[DEPLOY] Base apache/airflow local — build canônico (offline)..."
            DOCKER_BUILDKIT=0 COMPOSE_BAKE=false docker compose build \
                airflow-webserver airflow-scheduler airflow-worker \
                airflow-triggerer airflow-init
        else
            # Base ausente (prunada) e sem acesso ao Docker Hub → imagem
            # DERIVADA da atual + .deb vendorados (docker/debs) — 100% offline.
            # Quando a base voltar ao host (docker load), o ramo acima assume.
            echo "[DEPLOY] Base apache/airflow ausente — build derivado da imagem local..."
            cat > "$AIRFLOW_DIR/Dockerfile.hotfix" <<'DOCKEREOF'
FROM airflow-airflow-worker
USER root
COPY debs/*.deb /tmp/debs/
RUN ACCEPT_EULA=Y dpkg -i /tmp/debs/*.deb && rm -rf /tmp/debs
ENV PATH="$PATH:/opt/mssql-tools18/bin"
USER airflow
DOCKEREOF
            DOCKER_BUILDKIT=0 docker build -f "$AIRFLOW_DIR/Dockerfile.hotfix" \
                -t airflow-hotfix "$AIRFLOW_DIR/docker"
            for t in webserver scheduler worker triggerer init; do
                docker tag airflow-hotfix "airflow-airflow-$t"
            done
        fi
        docker compose up -d --force-recreate --no-build \
            airflow-webserver airflow-scheduler airflow-worker airflow-triggerer
        echo "[DEPLOY] ✓ Containers do Airflow recriados com a imagem nova"
        ;;
    *)
        echo "[DEPLOY] Containers do Airflow NÃO tocados (padrão seguro)."
        ;;
esac

# ── 9. Limpeza ────────────────────────────────────────────────
rm -rf "$TMP_DIR"

echo ""
echo "[DEPLOY] ✓ Concluído em $(date '+%Y-%m-%d %H:%M:%S')"
echo "[DEPLOY] ✓ Deploy concluído com sucesso"
echo ""
echo "  Verificar:"
echo "    docker compose ps"
echo "    curl -s http://localhost/orquestra/health"
