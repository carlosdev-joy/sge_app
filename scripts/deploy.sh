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

# ═════════════════════════════════════════════════════════════
# REGRAS DE PROPRIEDADE (nunca mudar sem revisar com o time):
#   - PERTENCEM AO SERVIDOR e o deploy NUNCA toca: dsx/, branding/,
#     logs/ e dags/generated/ (criado em runtime pelo Airflow).
#   - AUTOMÁTICO (sempre): ui-react/dist, api/ (+ rebuild orquestra-api),
#     ui-nginx (recreate) e a CÓPIA dos insumos de build (Dockerfile,
#     docker/debs — só arquivos, nenhuma ação de container).
#   - SÓ COM CONFIRMAÇÃO (mostra o que mudaria; Enter = não):
#     dags/, config/ (com backup), docker-compose.yaml (com backup) e
#     migrations SQL (etapa 6c — migrate.py dentro do container da API).
#   - Containers do Airflow: só na etapa 8b, também com pergunta.
# ═════════════════════════════════════════════════════════════

# Pergunta padrão-NÃO. Sem terminal (cron/pipe) responde não: um deploy não
# interativo nunca sobrescreve dags/config silenciosamente.
_confirmar() {  # $1 = pergunta
    local resp="n"
    if [ -t 0 ]; then
        read -r -p "$1 [s/N] " resp || resp="n"
    fi
    case "$resp" in [sS]*) return 0 ;; *) return 1 ;; esac
}

# Lista os arquivos que MUDARIAM (novos ou alterados) sem aplicar nada.
# --checksum: compara por CONTEÚDO — o clone é fresco e toda data/mtime muda,
# então sem isso a lista traria o repositório inteiro em todo deploy.
# Sem --delete: o que existe só no servidor nunca aparece nem é removido.
_mudancas() {  # $1 = origem/  $2 = destino/  $3.. = flags extras (ex.: --exclude)
    local src="$1" dst="$2"; shift 2
    mkdir -p "$dst"
    rsync -ac --dry-run --itemize-changes "$@" "$src" "$dst" \
        | awk '$1 ~ /^[<>]f/ {print "    " $2}'
}

# ── 3. UI React (única interface — servida na raiz /) ─────────
mkdir -p "$AIRFLOW_DIR/ui-react/dist"
rsync -av --delete "$TMP_DIR/ui-react/dist/" "$AIRFLOW_DIR/ui-react/dist/"
echo "[DEPLOY] ✓ ui-react/dist sincronizado"

# ── 4. Config (nginx.conf, webserver_config) — SÓ COM CONFIRMAÇÃO ─
# config/ pode ter ajustes feitos direto no servidor — nunca sobrescrever
# às cegas. Mostra o que mudaria e pergunta; ao aplicar, faz backup de
# config/ inteiro em config.bak.<timestamp>.
MUD_CONFIG=$(_mudancas "$TMP_DIR/config/" "$AIRFLOW_DIR/config/")
if [ -z "$MUD_CONFIG" ]; then
    echo "[DEPLOY] config/ sem mudanças."
else
    echo "[DEPLOY] config/ — arquivos que MUDARIAM:"
    echo "$MUD_CONFIG"
    if _confirmar "[DEPLOY] Aplicar as mudancas de config/ acima? (pode sobrescrever ajustes feitos no servidor; backup automatico)"; then
        BAK="$AIRFLOW_DIR/config.bak.$(date +%Y%m%d-%H%M%S)"
        cp -a "$AIRFLOW_DIR/config" "$BAK"
        rsync -avc "$TMP_DIR/config/" "$AIRFLOW_DIR/config/"
        echo "[DEPLOY] ✓ config/ sincronizado (backup em $BAK)"
    else
        echo "[DEPLOY] config/ mantido como está."
    fi
fi

# ── 5. DAGs — SÓ COM CONFIRMAÇÃO ──────────────────────────────
# generated/ é criado em runtime pelo Airflow — NUNCA sobrescrever (regra
# de sempre, mantida aqui e na listagem). Sem --delete: o que existe só no
# servidor fica intocado. dsx/, branding/ e logs/ NÃO passam por aqui.
MUD_DAGS=$(_mudancas "$TMP_DIR/dags/" "$AIRFLOW_DIR/dags/" --exclude=generated/)
if [ -z "$MUD_DAGS" ]; then
    echo "[DEPLOY] dags/ sem mudanças."
else
    echo "[DEPLOY] dags/ — arquivos que MUDARIAM (generated/ preservado):"
    echo "$MUD_DAGS"
    if _confirmar "[DEPLOY] Aplicar as mudancas de dags/ acima? (o scheduler/worker recarrega pelo volume nas proximas execucoes)"; then
        rsync -avc --exclude=generated/ "$TMP_DIR/dags/" "$AIRFLOW_DIR/dags/"
        chown -R airflow:airflow "$AIRFLOW_DIR/dags/"
        chmod -R 777 "$AIRFLOW_DIR/dags/"
        echo "[DEPLOY] ✓ dags/ sincronizado"
    else
        echo "[DEPLOY] dags/ mantido como está."
    fi
fi

# ── 6. Docker Compose — SÓ COM CONFIRMAÇÃO se divergir ────────
if cmp -s "$TMP_DIR/docker-compose.yaml" "$AIRFLOW_DIR/docker-compose.yaml"; then
    echo "[DEPLOY] docker-compose.yaml sem mudanças."
elif _confirmar "[DEPLOY] docker-compose.yaml mudou no repo. Sobrescrever o do servidor? (backup automatico)"; then
    cp -a "$AIRFLOW_DIR/docker-compose.yaml" \
          "$AIRFLOW_DIR/docker-compose.yaml.bak.$(date +%Y%m%d-%H%M%S)"
    cp "$TMP_DIR/docker-compose.yaml" "$AIRFLOW_DIR/docker-compose.yaml"
    echo "[DEPLOY] ✓ docker-compose.yaml atualizado"
else
    echo "[DEPLOY] docker-compose.yaml mantido como está."
fi

# ── 6b. Insumos do build da imagem Airflow ────────────────────
# O rebuild da imagem (bcp/ODBC do módulo Cópia de Dados) é 100% offline e
# precisa, NO SERVIDOR, do Dockerfile da raiz e dos .deb vendorados em
# docker/debs. O build em si continua manual/raro (exige janela sem jobs);
# aqui só garantimos que os arquivos existam quando ele for feito.
cp "$TMP_DIR/Dockerfile" "$AIRFLOW_DIR/Dockerfile"
rsync -av "$TMP_DIR/docker/" "$AIRFLOW_DIR/docker/"
echo "[DEPLOY] ✓ Dockerfile + docker/ (debs) sincronizados"

# ── 6c. Migrations SQL — SÓ COM CONFIRMAÇÃO ───────────────────
# Antes do rebuild da API (tela/permissão nova depende da migration; o resto
# degrada graciosamente se ela vier depois). Roda o migrate.py DENTRO do
# container orquestra-api atual: ele já tem python + pyodbc + MSSQL_CONN_STR,
# e o host não precisa de driver ODBC. Idempotentes, rastreadas em
# dbo.etl_schema_version. A cópia em /tmp do container morre no rebuild da
# etapa 7 — nada fica para trás. Falha ao APLICAR aborta o deploy (set -e):
# a API antiga continua no ar, estado consistente.
cd "$AIRFLOW_DIR"
API_CID=$(docker compose ps -q orquestra-api 2>/dev/null || true)
MIG_CMD="docker compose cp $TMP_DIR/sql orquestra-api:/tmp/deploy_sql && docker compose exec orquestra-api python /tmp/deploy_sql/migrate.py"
if [ -z "$API_CID" ]; then
    echo "[DEPLOY] AVISO: orquestra-api não está de pé — migrations NÃO verificadas."
    echo "         Aplique depois com: cd $AIRFLOW_DIR && $MIG_CMD"
else
    docker compose exec -T orquestra-api rm -rf /tmp/deploy_sql 2>/dev/null || true
    docker compose cp "$TMP_DIR/sql" orquestra-api:/tmp/deploy_sql >/dev/null
    MIG_DRY=$(docker compose exec -T orquestra-api python /tmp/deploy_sql/migrate.py --dry-run 2>&1 || true)
    if echo "$MIG_DRY" | grep -q "Nenhuma migration pendente"; then
        echo "[DEPLOY] Migrations SQL: nenhuma pendente."
    elif echo "$MIG_DRY" | grep -q "DRY-RUN"; then
        echo "[DEPLOY] Migrations SQL PENDENTES:"
        echo "$MIG_DRY" | sed 's/^/    /'
        if _confirmar "[DEPLOY] Aplicar as migrations acima agora? (idempotentes; recomendado backup do banco)"; then
            docker compose exec -T orquestra-api python /tmp/deploy_sql/migrate.py
            echo "[DEPLOY] ✓ Migrations aplicadas"
        else
            echo "[DEPLOY] AVISO: migrations NÃO aplicadas — telas/permissões novas podem não aparecer."
            echo "         Aplique depois com: cd $AIRFLOW_DIR && $MIG_CMD"
        fi
    else
        echo "[DEPLOY] AVISO: não foi possível verificar migrations (segue sem aplicar):"
        echo "$MIG_DRY" | sed 's/^/    /'
    fi
fi

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
