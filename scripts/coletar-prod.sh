#!/bin/bash
# =============================================================
# coletar-prod.sh — fotografa o código que está EM PRODUÇÃO e empacota
# o que divergir do repositório, para trazer as alterações de volta ao git.
#
# Roda NO SERVIDOR de produção. É SÓ LEITURA: não altera /opt/airflow,
# não mexe em container, não toca no banco além de dois SELECTs.
# Tudo que produz vai para /tmp.
#
# Uso:
#   bash coletar-prod.sh                  # compara contra a main do GitHub
#   BASE=<commit|tag> bash coletar-prod.sh # compara contra um ponto específico
#
# Saída: /tmp/orquestra-prod-<carimbo>.tar.gz  (+ a pasta antes de compactar)
# =============================================================
set -uo pipefail

AIRFLOW_DIR="${AIRFLOW_DIR:-/opt/airflow}"
REPO_URL="${REPO_URL:-https://github.com/carlosdev-joy/sge_app.git}"
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
log " base de comparação: $BASE"
log "============================================================"
log ""

# ── 1. Referência: o repositório, no ponto que queremos comparar ──
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

# ── 3. O diff: produção × repositório ─────────────────────────────
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
log "    ARQUIVOS-DIVERGENTES.txt   — a lista, um caminho por linha"
log "    divergencia.patch          — o diff aplicável (repo → produção)"
log "    arquivos/                  — os arquivos de produção, inteiros"
log "    IMPRESSAO-DIGITAL.txt      — identifica de qual build produção saiu"
log "    BANCO.txt                  — migrations e DDL manual"
log ""
log "  Nada em $AIRFLOW_DIR foi alterado."
