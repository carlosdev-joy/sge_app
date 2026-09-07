#!/bin/bash
# Smoke da transferência de arquivos dos Utilitários (spec
# docs/spec-utilitarios-transferencia.md §7) pela API. Roda no DEV (sshd-amostra)
# ou em produção. Nunca imprime credenciais.
#
# Uso:  ORQ_URL=http://localhost:8000 ORQ_USER=... ORQ_PASS=... RAIZ=/dados/bi \
#         PASTA=/dados/bi/2026 ARQ=consulta.sql BIN=/dados/bi/imagem.bin \
#         scripts/smoke_utilitarios_transferencia.sh
#       (sem variáveis, lê .env.dev e usa a árvore do sshd-amostra)
# F1 (download): itens b, c, e, f, m e n. Os itens de upload (g–l) entram na F3;
# a, d, k e a parte visual dos outros exigem o navegador — marcados "UI".
# Os itens e e m criam arquivos grandes no servidor e por isso exigem acesso a ele
# (`docker exec` no DEV); sem acesso, o script diz o que fazer à mão.
set -u
cd "$(dirname "$0")/.."
if [ -z "${ORQ_USER:-}" ] && [ -f .env.dev ]; then set -a; . ./.env.dev 2>/dev/null; set +a; fi
B=${ORQ_URL:-http://localhost:8000}
AUTH="${ORQ_USER:-$DEV_AIRFLOW_USER}:${ORQ_PASS:-$DEV_AIRFLOW_PASSWORD}"
RAIZ=${RAIZ:-/dados/bi}; PASTA=${PASTA:-/dados/bi/2026}; ARQ=${ARQ:-consulta.sql}
BIN=${BIN:-/dados/bi/imagem.bin}
SSHD=${SSHD:-orquestra-dev-sshd-amostra}   # só no DEV: permite conferir no servidor
TMP=$(mktemp -d); ok=0; falha=0; SOBRAS=""
res() { if [ "$1" = "$2" ]; then ok=$((ok+1)); printf '  ✅ %s → %s\n' "$3" "$2"; else falha=$((falha+1)); printf '  ❌ %s → esperado %s, veio %s  %s\n' "$3" "$2" "$1" "${4:-}"; fi; }
call() { local m=$1 p=$2 d=${3:-}; if [ -n "$d" ]; then curl -s -u "$AUTH" -X "$m" "$B$p" -H 'Content-Type: application/json' -d "$d" -w '\n%{http_code}'; else curl -s -u "$AUTH" -X "$m" "$B$p" -w '\n%{http_code}'; fi; }
# baixar <pasta> <nome> <arquivo-de-saída> → imprime o status; cabeçalhos em <saída>.h
baixar() { curl -s -u "$AUTH" -G "$B/utilitarios/arquivo/baixar" --data-urlencode "diretorio=$1" --data-urlencode "nome=$2" -o "$3" -D "$3.h" -w '%{http_code}'; }
status() { printf '%s' "$1" | tail -n1; }
corpo() { printf '%s' "$1" | sed '$d'; }
jq_() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)" 2>/dev/null; }
no_srv() { docker exec "$SSHD" sh -c "$1" 2>/dev/null; }
sha() { sha256sum "$1" | cut -c1-64; }
cab() { grep -i "^$2:" "$1.h" | tr -d '\r' | sed 's/^[^:]*: //'; }
ao_sair() { rm -rf "$TMP"; [ -n "$SOBRAS" ] && printf '  ⚠️ sem acesso ao servidor de arquivos, ficou para apagar à mão:%s\n' "$SOBRAS"; return 0; }
trap ao_sair EXIT

echo "== a) aba Enviar arquivo por perfil: UI (F4) =="
r=$(call GET /utilitarios/config); res "$(status "$r")" 200 "config com a tela liberada"
res "$(corpo "$r" | jq_ "d.get('transferencia_max_kb')")" 51200 "teto de transferência no config (51200 KB)"
teto_kb=$(corpo "$r" | jq_ "d.get('transferencia_max_kb')")

echo "== b) baixar um texto pequeno: sha256 igual ao do servidor =="
st=$(baixar "$(dirname "$PASTA/$ARQ")" "$ARQ" "$TMP/b.out"); [ "$st" = 200 ] || st=$(baixar "$RAIZ" "$ARQ" "$TMP/b.out")
res "$st" 200 "baixar $ARQ"
res "$(cab "$TMP/b.out" content-type)" "application/octet-stream" "content-type"
res "$(cab "$TMP/b.out" content-disposition)" "attachment; filename=\"$ARQ\"; filename*=UTF-8''$ARQ" "content-disposition"
res "$(cab "$TMP/b.out" content-length)" "$(stat -c %s "$TMP/b.out")" "content-length = bytes recebidos"
res "$(cab "$TMP/b.out" x-orquestra-sha256)" "$(sha "$TMP/b.out")" "x-orquestra-sha256 = sha256 do corpo"
if [ -n "$(no_srv 'echo ok')" ]; then
  cam=$( [ "$st" = 200 ] && ([ -f "$TMP/b.out" ] && echo "$PASTA/$ARQ") ); [ -n "$(no_srv "test -f '$cam' && echo 1")" ] || cam="$RAIZ/$ARQ"
  res "$(sha "$TMP/b.out")" "$(no_srv "sha256sum '$cam'" | cut -c1-64)" "sha256 local = sha256 no servidor"
fi

echo "== c) binário: o Ver arquivo recusa (415), o Baixar entrega íntegro =="
r=$(call POST /utilitarios/arquivo/ler "{\"diretorio\":\"$(dirname "$BIN")\",\"nome\":\"$(basename "$BIN")\"}"); res "$(status "$r")" 415 "ler $BIN"
res "$(baixar "$(dirname "$BIN")" "$(basename "$BIN")" "$TMP/c.out")" 200 "baixar $BIN"
res "$(cab "$TMP/c.out" x-orquestra-sha256)" "$(sha "$TMP/c.out")" "sha256 do binário confere"
[ -n "$(no_srv 'echo ok')" ] && res "$(sha "$TMP/c.out")" "$(no_srv "sha256sum '$BIN'" | cut -c1-64)" "sha256 = servidor"

echo "== d) Baixar pelo navegador de pastas: UI (F2) =="

echo "== e) acima de 50 MB → 413 sem baixar =="
if [ -n "$(no_srv 'echo ok')" ]; then
  no_srv "head -c $((teto_kb*1024+1)) /dev/zero > '$PASTA/smoke_teto.bin'"
  t0=$(date +%s); st=$(baixar "$PASTA" smoke_teto.bin "$TMP/e.out"); t1=$(date +%s)
  res "$st" 413 "50 MB + 1 byte"; res "$(python3 -c "import json;print('acima do teto' in json.load(open('$TMP/e.out'))['detail'])")" True "mensagem nomeia o teto"
  res "$([ $((t1-t0)) -le 2 ] && echo rapido)" rapido "recusado sem transferir (≤ 2 s)"
  no_srv "rm -f '$PASTA/smoke_teto.bin'"
else echo "  (sem acesso ao servidor de arquivos: passo e NÃO executado — crie um arquivo > ${teto_kb} KB abaixo da raiz e baixe: espera 413)"; fi

echo "== f) fora das raízes → 403 e auditoria negado =="
res "$(baixar /etc passwd "$TMP/f.out")" 403 "/etc/passwd"
res "$(baixar "$RAIZ/../../etc" passwd "$TMP/f2.out")" 403 "$RAIZ/../../etc/passwd"
res "$(baixar "$RAIZ/link_fora" segredo.txt "$TMP/f3.out")" 403 "link para fora da raiz"
res "$(baixar "$RAIZ" nao_existe_smoke.bin "$TMP/f4.out")" 404 "arquivo inexistente dentro da raiz"

echo "== g–l) upload: F3/F4 =="

echo "== m) transferências em paralelo: vagas esgotadas respondem 503 na hora =="
if [ -n "$(no_srv 'echo ok')" ]; then
  no_srv "head -c $((20*1024*1024)) /dev/urandom > '$PASTA/smoke_20mb.bin'"
  # Um status por arquivo (o `-w` do curl não quebra linha; sem o `echo` os seis colariam numa linha só).
  n=6; for i in $(seq 1 $n); do { baixar "$PASTA" smoke_20mb.bin "$TMP/m$i.out"; echo; } > "$TMP/m$i.st" & done; wait
  c200=$(cat "$TMP"/m*.st | grep -c '^200$'); c503=$(cat "$TMP"/m*.st | grep -c '^503$')
  printf '  %s pedidos: %s ok, %s ocupado\n' "$n" "$c200" "$c503"
  res "$([ "$c200" -ge 2 ] && echo sim)" sim "pelo menos 2 downloads simultâneos passaram"
  res "$((c200+c503))" "$n" "todo pedido foi 200 ou 503 (nenhum outro status)"
  [ "$c503" -ge 1 ] || echo "  ⚠️ nenhum 503: as vagas são por worker (2 × workers do uvicorn) e os pedidos podem não ter coincidido — não é falha"
  for f in "$TMP"/m*.out; do [ "$(cat "${f%.out}.st")" = 200 ] && res "$(sha "$f")" "$(no_srv "sha256sum '$PASTA/smoke_20mb.bin'" | cut -c1-64)" "$(basename "$f") íntegro"; done
  no_srv "rm -f '$PASTA/smoke_20mb.bin'"
else echo "  (sem acesso ao servidor de arquivos: passo m NÃO executado — dispare 6 downloads de um arquivo de ~20 MB em paralelo: espera 200 e 503, nada mais)"; fi

echo "== n) auditoria: baixar com tamanho e sha256, sem conteúdo =="
if docker exec orquestra-api true 2>/dev/null; then
  vaz=$(docker exec -i orquestra-api python - <<'PY'
from db import get_db_conn
c = get_db_conn(); cur = c.cursor()
cur.execute("SELECT TOP 12 acao, resultado, LEFT(caminho, 45), tamanho_bytes, LEFT(sha256, 8) FROM dbo.etl_utilitario_arquivo_log WHERE acao = 'baixar' ORDER BY id DESC")
for r in cur.fetchall(): print("  ", tuple(r))
cur.execute("SELECT COUNT(*) FROM dbo.etl_utilitario_arquivo_log WHERE acao = 'baixar' AND resultado = 'ok' AND (sha256 IS NULL OR tamanho_bytes IS NULL)")
print(cur.fetchone()[0])
PY
)
  res "$(printf '%s' "$vaz" | tail -n1)" 0 "todo 'baixar' ok tem tamanho e sha256"; printf '%s\n' "$vaz" | sed '$d'
else echo "  SELECT TOP 20 acao, resultado, caminho, tamanho_bytes, sha256 FROM dbo.etl_utilitario_arquivo_log WHERE acao IN ('baixar','enviar') ORDER BY id DESC"; fi
echo; echo "RESULTADO: $ok ok, $falha falhas (itens UI e de upload à parte)"
[ "$falha" -eq 0 ]
