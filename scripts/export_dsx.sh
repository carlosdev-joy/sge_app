#!/usr/bin/env bash
# =============================================================================
# scripts/export_dsx.sh
# -----------------------------------------------------------------------------
# Exporta job(s) DataStage para .dsx (ou .isx) e publica no DSX_BASE_DIR, para
# a tela "Impacto por Campo/Tabela/Arquivo" enxergar o arquivo automaticamente.
#
# IMPORTANTE: `dsjob` NÃO exporta — ele só controla/roda jobs. As ferramentas de
# export são `dsexport` / `dscmdexport` (cliente, geram .dsx) e `istool` (engine
# Unix, gera .isx). As flags variam por versão (11.3/11.5/11.7): confirme com
#   dsexport            (sem args)
#   dscmdexport -help
#   istool export -help
#
# Uso:
#   export_dsx.sh PROJETO JOB [ARQUIVO_SAIDA]
#   ex.: export_dsx.sh DM_CONTRATOS_CVP SSC_ATUARIAL /tmp/SSC_ATUARIAL.dsx
#
# Config por variáveis de ambiente (use um cofre / .env — NÃO hardcode a senha):
#   DS_DOMAIN       domínio:porta dos serviços      (ex.: dominio:9080)
#   DS_HOST         host do engine/servidor         (ex.: engine01)
#   DS_USER         usuário
#   DS_PASSWORD     senha
#   EXPORT_METHOD   dsexport (padrão) | dscmdexport | istool
#   DSX_BASE_DIR    destino de publicação           (padrão: /opt/airflow/dsx)
#   DSHOME          raiz do DataStage p/ achar os bins (opcional)
#   DS_JOB_PATH     (só istool) caminho do asset     (ex.: /PROJ/Jobs/Cat/JOB)
# =============================================================================
set -euo pipefail

usage() { sed -n '2,30p' "$0"; exit "${1:-2}"; }

[ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] && usage 0

# ── Configuração ────────────────────────────────────────────────────────────
DS_DOMAIN=${DS_DOMAIN:-}
DS_HOST=${DS_HOST:-}
DS_USER=${DS_USER:-}
DS_PASSWORD=${DS_PASSWORD:-}
EXPORT_METHOD=${EXPORT_METHOD:-dsexport}
DSX_BASE_DIR=${DSX_BASE_DIR:-/opt/airflow/dsx}
DSHOME=${DSHOME:-}
DS_JOB_PATH=${DS_JOB_PATH:-}

# ── Argumentos ──────────────────────────────────────────────────────────────
PROJETO=${1:-${DS_PROJECT:-}}
JOB=${2:-}
OUT=${3:-}

[ -n "$PROJETO" ] || { echo "ERRO: informe o PROJETO."; usage; }
if [ "$EXPORT_METHOD" != "dscmdexport" ] && [ -z "$JOB" ]; then
  echo "ERRO: informe o JOB (apenas dscmdexport exporta o projeto inteiro)."; usage
fi

# Saída padrão: <JOB|PROJETO>.dsx no diretório atual
if [ -z "$OUT" ]; then
  base="${JOB:-$PROJETO}"
  OUT="$(pwd)/${base}.dsx"
fi

# ── Validação de credenciais ────────────────────────────────────────────────
miss=""
for v in DS_DOMAIN DS_HOST DS_USER DS_PASSWORD; do
  [ -n "${!v}" ] || miss="$miss $v"
done
[ -z "$miss" ] || { echo "ERRO: variáveis de ambiente ausentes:$miss"; exit 3; }

# ── Localiza o binário (PATH ou \$DSHOME/bin) ────────────────────────────────
find_bin() {
  local b
  b="$(command -v "$1" 2>/dev/null || true)"
  [ -z "$b" ] && [ -n "$DSHOME" ] && [ -x "$DSHOME/bin/$1" ] && b="$DSHOME/bin/$1"
  [ -n "$b" ] && { echo "$b"; return 0; }
  return 1
}

mask() { sed -E 's/(\/P=|-password )[^ ]*/\1******/g'; }
log()  { echo "[export_dsx] $*"; }

mkdir -p "$(dirname "$OUT")"

# ── Execução por método ─────────────────────────────────────────────────────
case "$EXPORT_METHOD" in
  dsexport)
    BIN="$(find_bin dsexport)" || { echo "ERRO: 'dsexport' não encontrado (cliente DataStage / defina DSHOME)."; exit 4; }
    cmd=("$BIN" "/D=$DS_DOMAIN" "/H=$DS_HOST" "/U=$DS_USER" "/P=$DS_PASSWORD" "/JOB=$JOB" "$PROJETO" "$OUT")
    ;;
  dscmdexport)
    BIN="$(find_bin dscmdexport)" || { echo "ERRO: 'dscmdexport' não encontrado."; exit 4; }
    [ -n "$JOB" ] && log "AVISO: dscmdexport exporta o PROJETO inteiro; JOB '$JOB' será ignorado."
    cmd=("$BIN" "/D=$DS_DOMAIN" "/H=$DS_HOST" "/U=$DS_USER" "/P=$DS_PASSWORD" "$PROJETO" "$OUT" "/V")
    ;;
  istool)
    BIN="$(find_bin istool)" || { echo "ERRO: 'istool' não encontrado (engine InfoSphere)."; exit 4; }
    # istool gera .isx — ajusta a extensão se necessário
    case "$OUT" in *.isx) ;; *) OUT="${OUT%.dsx}.isx"; log "istool gera .isx → saída ajustada para $OUT" ;; esac
    JOBPATH="${DS_JOB_PATH:-/$PROJETO/Jobs/*/$JOB}"
    cmd=("$BIN" export -domain "$DS_DOMAIN" -username "$DS_USER" -password "$DS_PASSWORD"
         -archive "$OUT" -datastage "\"$JOBPATH\"")
    ;;
  *)
    echo "ERRO: EXPORT_METHOD inválido: '$EXPORT_METHOD' (use dsexport|dscmdexport|istool)."; exit 5
    ;;
esac

log "Método: $EXPORT_METHOD | Projeto: $PROJETO | Job: ${JOB:-<todos>}"
log "Comando: $(printf '%q ' "${cmd[@]}" | mask)"
"${cmd[@]}"
rc=$?
[ $rc -eq 0 ] || { echo "ERRO: export falhou (rc=$rc)."; exit $rc; }
[ -s "$OUT" ] || { echo "ERRO: arquivo de saída vazio/inexistente: $OUT"; exit 6; }
log "Export OK: $OUT ($(wc -c < "$OUT") bytes)"

# ── Publicação no DSX_BASE_DIR ──────────────────────────────────────────────
if [ -n "$DSX_BASE_DIR" ]; then
  dest="$DSX_BASE_DIR/$(basename "$OUT")"
  if [ "$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")" != "$(cd "$DSX_BASE_DIR" 2>/dev/null && pwd)/$(basename "$OUT")" ]; then
    mkdir -p "$DSX_BASE_DIR"
    cp -f "$OUT" "$dest"
    log "Publicado em: $dest (visível na tela de Impacto)"
  fi
fi

log "Concluído."
