#!/bin/bash
# =============================================================
# coletar-prod.sh — fotografa o código que está EM PRODUÇÃO e empacota
# o que divergir do repositório, para trazer as alterações de volta ao git.
#
# Roda NO SERVIDOR de produção. É SÓ LEITURA: não altera /opt/airflow,
# não mexe em container, não toca no banco além de dois SELECTs.
# Tudo que produz vai para /tmp.
#
# Dois modos:
#   MODO=completo (padrão) — leva as pastas INTEIRAS. Não precisa de rede nem
#     de saber de qual commit a produção saiu: a comparação acontece do outro
#     lado, onde existe o histórico completo do git. É o modo recomendado.
#   MODO=diff — clona o repositório aqui e traz só a diferença. Útil quando o
#     que interessa é ver a divergência NA HORA, no próprio servidor.
#
# Uso:
#   bash coletar-prod.sh                             # completo
#   MODO=diff BASE=<commit|tag> bash coletar-prod.sh # só a diferença
#
# Saída: /tmp/orquestra-prod-<carimbo>.tar.gz  (+ a pasta antes de compactar)
# =============================================================
set -uo pipefail

AIRFLOW_DIR="${AIRFLOW_DIR:-/opt/airflow}"
REPO_URL="${REPO_URL:-https://github.com/carlosdev-joy/sge_app.git}"
MODO="${MODO:-completo}"
BASE="${BASE:-main}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="/tmp/orquestra-prod-$STAMP"
REF="/tmp/orquestra-ref-$STAMP"

# O que o deploy.sh governa — só isso pode divergir "legitimamente".
# dsx/, branding/, logs/ e dags/generated/ pertencem ao servidor: ficam de fora.
ALVOS_DIR=(api dags config docker)
ALVOS_FILE=(docker-compose.yaml Dockerfile)

# Ruído que nunca deve virar commit.
EXCL=(-x 'generated' -x '__pycache__' -x '*.pyc' -x '*.pyo' -x '.pytest_cache'
      -x '*.bak' -x '*.bak.*' -x '*.swp' -x '.DS_Store' -x 'logs')

mkdir -p "$OUT/arquivos"
REL="$OUT/RELATORIO.txt"

log() { echo "$@" | tee -a "$REL"; }

log "============================================================"
log " ORQUESTRA — coleta do que está em produção"
log " $(date '+%Y-%m-%d %H:%M:%S')  ·  host: $(hostname)"
log " modo: $MODO$([ "$MODO" = diff ] && echo "  ·  base de comparação: $BASE")"
log "============================================================"
log ""

# ── 1. Referência: o repositório, no ponto que queremos comparar ──
if [ "$MODO" = "completo" ]; then
    log "[1/5] Modo completo — sem clone, sem rede: as pastas vão inteiras."
    log ""
else
log "[1/5] Clonando o repositório para comparar ($BASE)..."
# Três tentativas, da mais barata para a mais cara — o proxy corporativo cobra
# por byte trafegado e o clone completo é ~200 MB.
if ! git clone --quiet --depth=1 --branch "$BASE" "$REPO_URL" "$REF" 2>>"$REL"; then
    # --branch não aceita SHA. Busca raso pelo commit exato.
    rm -rf "$REF"
    if ! ( git init -q "$REF" \
           && git -C "$REF" remote add origin "$REPO_URL" \
           && git -C "$REF" fetch -q --depth=1 origin "$BASE" \
           && git -C "$REF" checkout -q FETCH_HEAD ) 2>>"$REL"; then
        # Último recurso: histórico inteiro.
        rm -rf "$REF"
        git clone --quiet "$REPO_URL" "$REF" 2>>"$REL" && git -C "$REF" checkout --quiet "$BASE" 2>>"$REL"
    fi
fi
if [ ! -d "$REF/.git" ]; then
    log "  ERRO: não consegui clonar $REPO_URL (proxy? rede?). Sem referência não há comparação."
    exit 1
fi
log "  referência: $(git -C "$REF" log -1 --format='%h %s (%ai)')"
log ""
fi

# ── 2. Impressão digital do que está no ar ────────────────────────
# Os nomes com hash dos assets do front identificam EXATAMENTE qual build
# está em produção — é assim que se descobre de qual commit ela saiu.
log "[2/5] Impressão digital da versão em produção"
{
    echo "--- assets do front em $AIRFLOW_DIR/ui-react/dist/index.html ---"
    grep -o '[A-Za-z0-9._/-]*\.\(js\|css\)' "$AIRFLOW_DIR/ui-react/dist/index.html" 2>/dev/null | sort -u \
        || echo "(index.html não encontrado)"
    echo
    echo "--- data de modificação dos arquivos-chave ---"
    for a in "${ALVOS_DIR[@]}" "${ALVOS_FILE[@]}"; do
        [ -e "$AIRFLOW_DIR/$a" ] && find "$AIRFLOW_DIR/$a" -type f \
            \( -name '*.py' -o -name '*.yaml' -o -name '*.yml' -o -name '*.conf' -o -name 'Dockerfile' \) \
            -newermt '90 days ago' -printf '%TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null
    done | sort -r | head -40
} > "$OUT/IMPRESSAO-DIGITAL.txt"
log "  → IMPRESSAO-DIGITAL.txt ($(wc -l < "$OUT/IMPRESSAO-DIGITAL.txt") linhas)"
log ""

# ── 3. O conteúdo: pastas inteiras (completo) ou só a diferença (diff) ──
if [ "$MODO" = "completo" ]; then
log "[3/5] Copiando as pastas que o deploy governa..."
# api/wheels fica de fora: são 18 MB de binários que vêm do próprio repo e
# ninguém edita à mão. Os NOMES vão no relatório — se aparecer wheel que o
# repositório não tem, isso precisa ser visto, e some se não for registrado.
find "$AIRFLOW_DIR/api/wheels" -maxdepth 1 -name '*.whl' -printf '%f\n' 2>/dev/null \
    | sort > "$OUT/WHEELS-EM-PRODUCAO.txt"

TAR_EXCL=(--exclude='dags/generated' --exclude='__pycache__' --exclude='*.pyc'
          --exclude='*.pyo' --exclude='.pytest_cache' --exclude='*.bak'
          --exclude='*.bak.*' --exclude='*.swp' --exclude='api/wheels')
ALVOS_EXISTENTES=()
for a in "${ALVOS_DIR[@]}" "${ALVOS_FILE[@]}"; do
    [ -e "$AIRFLOW_DIR/$a" ] && ALVOS_EXISTENTES+=("$a")
done
# ui-react/dist inteira são ~4 MB de bundle que ninguém edita à mão; só o
# index.html vem junto, porque é ele que identifica de qual build isto saiu.
[ -f "$AIRFLOW_DIR/ui-react/dist/index.html" ] && ALVOS_EXISTENTES+=("ui-react/dist/index.html")

tar -C "$AIRFLOW_DIR" -cf - "${TAR_EXCL[@]}" "${ALVOS_EXISTENTES[@]}" 2>/dev/null \
    | tar -xf - -C "$OUT/arquivos" 2>/dev/null

find "$OUT/arquivos" -type f | sed "s|$OUT/arquivos/||" | sort > "$OUT/ARQUIVOS-DIVERGENTES.txt"
log "  pastas: ${ALVOS_EXISTENTES[*]}"
log "  arquivos copiados: $(wc -l < "$OUT/ARQUIVOS-DIVERGENTES.txt")  ·  $(du -sh "$OUT/arquivos" | cut -f1)"
log "  wheels em produção: $(wc -l < "$OUT/WHEELS-EM-PRODUCAO.txt") (nomes apenas)"
log ""
else
log "[3/5] Comparando produção com o repositório..."
PATCH="$OUT/divergencia.patch"
: > "$PATCH"
: > "$OUT/ARQUIVOS-DIVERGENTES.txt"

# O diff roda de dentro de um diretório com dois symlinks, a/ (repositório) e
# b/ (produção). Sem isso os cabeçalhos sairiam com caminhos absolutos de /tmp
# e o patch não aplicaria em lugar nenhum — teria vindo só para ser lido.
WORK="/tmp/orquestra-diff-$STAMP"
rm -rf "$WORK"; mkdir -p "$WORK"
ln -s "$REF" "$WORK/a"
ln -s "$AIRFLOW_DIR" "$WORK/b"

_registrar() {  # $1 = caminho relativo
    local rel="$1"
    echo "$rel" >> "$OUT/ARQUIVOS-DIVERGENTES.txt"
    mkdir -p "$OUT/arquivos/$(dirname "$rel")"
    cp -a "$AIRFLOW_DIR/$rel" "$OUT/arquivos/$rel" 2>/dev/null
}

cd "$WORK"
for d in "${ALVOS_DIR[@]}"; do
    [ -d "$AIRFLOW_DIR/$d" ] || { log "  $d/ — não existe no servidor, pulando"; continue; }
    # -N trata ausente como vazio (pega arquivo que só existe em produção)
    diff -ruN "${EXCL[@]}" "a/$d" "b/$d" 2>/dev/null >> "$PATCH"
    # lista só os nomes, para o inventário e para copiar os arquivos inteiros
    while IFS= read -r rel; do
        [ -n "$rel" ] && _registrar "$d/$rel"
    done < <(diff -rqN "${EXCL[@]}" "a/$d" "b/$d" 2>/dev/null \
             | sed -n -e "s|^Files a/$d/\(.*\) and .* differ$|\1|p" \
                      -e "s|^Only in b/$d\(.*\): \(.*\)$|\1/\2|p" \
             | sed 's|^/||')
done

for f in "${ALVOS_FILE[@]}"; do
    [ -f "$AIRFLOW_DIR/$f" ] || continue
    if ! cmp -s "$REF/$f" "$AIRFLOW_DIR/$f"; then
        diff -uN "a/$f" "b/$f" 2>/dev/null >> "$PATCH"
        _registrar "$f"
    fi
done
cd /tmp
rm -rf "$WORK"

# A linha "diff -ruN -x ... a/x b/x" só polui a leitura; git apply ignora,
# mas quem revisa não. Enxuga para "diff -u a/x b/x".
sed -i -E 's|^diff -ruN( -x [^ ]+)+ |diff -u |' "$PATCH" 2>/dev/null

QTD=$(wc -l < "$OUT/ARQUIVOS-DIVERGENTES.txt")
log "  arquivos divergentes: $QTD"
if [ "$QTD" -gt 0 ]; then
    sed 's/^/    /' "$OUT/ARQUIVOS-DIVERGENTES.txt" | tee -a "$REL"
fi
log ""
fi

# ── 4. Estado do banco ────────────────────────────────────────────
# Alteração de schema feita na mão NÃO aparece em diff de arquivo:
# ou vira migration aqui, ou some no próximo ambiente.
log "[4/5] Banco: migrations registradas e objetos alterados"
cd "$AIRFLOW_DIR" 2>/dev/null || true
if docker compose ps -q orquestra-api >/dev/null 2>&1 && [ -n "$(docker compose ps -q orquestra-api 2>/dev/null)" ]; then
    docker compose exec -T orquestra-api python - <<'PY' > "$OUT/BANCO.txt" 2>&1
import os, sys
try:
    import pyodbc
    cn = pyodbc.connect(os.environ["MSSQL_CONN_STR"], timeout=15)
    cur = cn.cursor()
    print("--- migrations registradas em dbo.etl_schema_version ---")
    try:
        cur.execute("SELECT migration_name, applied_by, applied_at FROM dbo.etl_schema_version ORDER BY migration_name")
        for r in cur.fetchall():
            print(f"  {r[0]:<45} {str(r[1]):<15} {r[2]}")
    except Exception as e:
        cur.execute("SELECT migration_name FROM dbo.etl_schema_version ORDER BY migration_name")
        for r in cur.fetchall():
            print(f"  {r[0]}")
        print(f"  (sem applied_by/applied_at: {e})")
    print()
    print("--- objetos do banco criados/alterados nos últimos 90 dias ---")
    print("--- (DDL feito na mão aparece AQUI e em lugar nenhum do git) ---")
    cur.execute("""
        SELECT name, type_desc, create_date, modify_date
          FROM sys.objects
         WHERE is_ms_shipped = 0
           AND modify_date > DATEADD(day, -90, GETDATE())
         ORDER BY modify_date DESC
    """)
    for r in cur.fetchall():
        print(f"  {r[3]}  {r[1]:<22} {r[0]}")
except Exception as e:
    print(f"ERRO ao consultar o banco: {e}", file=sys.stdout)
PY
    log "  → BANCO.txt"
    grep -c "^  " "$OUT/BANCO.txt" >/dev/null 2>&1 && head -3 "$OUT/BANCO.txt" | sed 's/^/    /' | tee -a "$REL"
else
    echo "orquestra-api não está de pé — banco não consultado." > "$OUT/BANCO.txt"
    log "  orquestra-api fora do ar: banco NÃO consultado."
fi
log ""

# ── 5. Empacotar ──────────────────────────────────────────────────
log "[5/5] Empacotando..."
rm -rf "$REF"
tar -czf "$OUT.tar.gz" -C /tmp "$(basename "$OUT")" 2>/dev/null
log ""
log "  PACOTE: $OUT.tar.gz  ($(du -h "$OUT.tar.gz" | cut -f1))"
log "  sha256: $(sha256sum "$OUT.tar.gz" | cut -d' ' -f1)"
log "  pasta:  $OUT"
log ""
log "  Dentro dele:"
log "    RELATORIO.txt              — este resumo"
if [ "$MODO" = "completo" ]; then
log "    arquivos/                  — as pastas de produção, inteiras"
log "    ARQUIVOS-DIVERGENTES.txt   — o inventário do que veio"
log "    WHEELS-EM-PRODUCAO.txt     — nomes das wheels (os .whl não vieram)"
else
log "    ARQUIVOS-DIVERGENTES.txt   — a lista, um caminho por linha"
log "    divergencia.patch          — o diff aplicável (repo → produção)"
log "    arquivos/                  — os arquivos divergentes, inteiros"
fi
log "    IMPRESSAO-DIGITAL.txt      — identifica de qual build produção saiu"
log "    BANCO.txt                  — migrations e DDL manual"
log ""
log "  Nada em $AIRFLOW_DIR foi alterado."
