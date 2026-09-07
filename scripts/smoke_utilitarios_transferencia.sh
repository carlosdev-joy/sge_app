#!/bin/bash
# Smoke da transferência de arquivos dos Utilitários (spec
# docs/spec-utilitarios-transferencia.md §7) pela API. Roda no DEV (sshd-amostra)
# ou em produção. Nunca imprime credenciais.
#
# Uso:  ORQ_URL=http://localhost:8000 ORQ_USER=... ORQ_PASS=... RAIZ=/dados/bi \
#         PASTA=/dados/bi/2026 ARQ=consulta.sql BIN=/dados/bi/imagem.bin \
#         scripts/smoke_utilitarios_transferencia.sh
#       (sem variáveis, lê .env.dev e usa a árvore do sshd-amostra)
# Download (F1/F2): itens b, c, e, f, m e n. Upload (F3/F4): g, h, i, j, k, k2 e l pela
# API. Os itens a e d (tela), a parte visual de g/h/k e o l (credencial de operador)
# ficam marcados "UI" com o roteiro impresso. Os itens e, h, k, k2 e m criam ou
# conferem arquivos no servidor e por isso exigem acesso a ele (`docker exec` no
# DEV); sem acesso, o script diz o que fazer à mão e o que sobrou para apagar.
# Resultado no DEV (2026-09-07, F5): 54 conferências ok, 0 falhas.
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
# enviar <pasta> <nome> <arquivo-local> [sobrescrever=true] [extra-curl…] → corpo JSON + status na última linha
enviar() { local p=$1 n=$2 f=$3 s=${4:-false}; shift 4 2>/dev/null || shift $#
  curl -s -u "$AUTH" -X PUT "$B/utilitarios/arquivo/enviar?servidor=datastage&sobrescrever=$s&diretorio=$(urlenc "$p")&nome=$(urlenc "$n")" \
    -H 'Content-Type: application/octet-stream' --data-binary "@$f" "$@" -w '\n%{http_code}'; }
urlenc() { python3 -c 'import sys,urllib.parse as u; print(u.quote(sys.argv[1], safe=""))' "$1"; }
status() { printf '%s' "$1" | tail -n1; }
corpo() { printf '%s' "$1" | sed '$d'; }
jq_() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)" 2>/dev/null; }
no_srv() { docker exec "$SSHD" sh -c "$1" 2>/dev/null; }
sha() { sha256sum "$1" | cut -c1-64; }
cab() { grep -i "^$2:" "$1.h" | tr -d '\r' | sed 's/^[^:]*: //'; }
ao_sair() { rm -rf "$TMP"; [ -n "$SOBRAS" ] && printf '  ⚠️ sem acesso ao servidor de arquivos, ficou para apagar à mão:%s\n' "$SOBRAS"; return 0; }
trap ao_sair EXIT

echo "== a) UI: com desenvolvedor, a tela Utilitários tem a 3ª aba Enviar arquivo; com operador, a aba aparece desabilitada com a explicação (sem relogin: não há permissão nova) =="
r=$(call GET /utilitarios/config); res "$(status "$r")" 200 "config com a tela liberada"
res "$(corpo "$r" | jq_ "d.get('transferencia_max_kb')")" 51200 "teto de transferência no config (51200 KB)"
teto_kb=$(corpo "$r" | jq_ "d.get('transferencia_max_kb')")

echo "== b) baixar um texto pequeno: sha256 igual ao do servidor =="
st=$(baixar "$(dirname "$PASTA/$ARQ")" "$ARQ" "$TMP/b.out"); [ "$st" = 200 ] || st=$(baixar "$RAIZ" "$ARQ" "$TMP/b.out")
res "$st" 200 "baixar $ARQ"
res "$(cab "$TMP/b.out" content-type)" "application/octet-stream" "content-type"
# O esperado segue a mesma régua da API (RFC 6266/5987): nome com espaço, acento ou `%` não é falha falsa.
esperado_cd=$(python3 - "$ARQ" <<'PY'
import sys, urllib.parse as u
n = sys.argv[1]
a = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in n) or "arquivo"
print("attachment; filename=\"%s\"; filename*=UTF-8''%s" % (a, u.quote(n, safe="")))
PY
)
res "$(cab "$TMP/b.out" content-disposition)" "$esperado_cd" "content-disposition"
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

echo "== d) UI: Navegar… → ícone ⬇ numa linha de arquivo → download; o formulário não muda e o navegador continua aberto; a faixa no canto mostra o progresso ACIMA do modal =="

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
res "$(baixar "$RAIZ" nao_existe_smoke.bin "$TMP/f4.out")" 404 "arquivo inexistente dentro da raiz"
# O link para fora existe só na árvore do sshd-amostra (em produção seria 404, não 403).
if [ -n "$(no_srv 'echo ok')" ] && [ -n "$(no_srv "test -L '$RAIZ/link_fora' && echo 1")" ]; then
  res "$(baixar "$RAIZ/link_fora" segredo.txt "$TMP/f3.out")" 403 "link para fora da raiz"
else echo "  ($RAIZ/link_fora não existe neste servidor: passo do link pulado — em produção, crie um symlink para fora sob a raiz e espere 403)"; fi

echo "== g) enviar arquivo novo (3 MB, binário): sha256 confere, sem +x =="
head -c $((3*1024*1024)) /dev/urandom > "$TMP/smoke_transfer.txt"
r=$(enviar "$PASTA" smoke_transfer.txt "$TMP/smoke_transfer.txt"); res "$(status "$r")" 200 "enviar smoke_transfer.txt"
res "$(corpo "$r" | jq_ "str(d['criado'])+' '+str(d['tamanho_bytes'])")" "True $((3*1024*1024))" "criado, 3 MB"
res "$(corpo "$r" | jq_ "d['sha256']")" "$(sha "$TMP/smoke_transfer.txt")" "sha256 da resposta = sha256 local"
cam=$(corpo "$r" | jq_ "d['caminho']")
if [ -n "$(no_srv 'echo ok')" ]; then
  res "$(no_srv "sha256sum '$cam'" | cut -c1-64)" "$(sha "$TMP/smoke_transfer.txt")" "sha256 no servidor"
  res "$(no_srv "stat -c %A '$cam'" | grep -c x)" 0 "sem bit de execução"
  res "$(no_srv "ls -a '$PASTA'" | grep -c '\.tmp-')" 0 "nenhum .tmp sobrou"
else SOBRAS="$SOBRAS $cam"; fi

echo "== h) enviar de novo: 409; sobrescrever com .bak e modo preservado =="
r=$(enviar "$PASTA" smoke_transfer.txt "$TMP/smoke_transfer.txt"); res "$(status "$r")" 409 "sem sobrescrever"
res "$(corpo "$r" | jq_ "str(d['detail']['existente']['tamanho_bytes'])")" "$((3*1024*1024))" "409 traz o tamanho do atual"
[ -n "$(no_srv 'echo ok')" ] && no_srv "chmod 664 '$cam'"
printf 'v2\n' > "$TMP/v2.txt"
r=$(enviar "$PASTA" smoke_transfer.txt "$TMP/v2.txt" true); res "$(status "$r")" 200 "sobrescrever"
bak=$(corpo "$r" | jq_ "d['backup']"); res "$(corpo "$r" | jq_ "str(d['criado'])+' '+str(d['tamanho_bytes'])")" "False 3" "sobrescrito, 3 bytes"
if [ -n "$(no_srv 'echo ok')" ]; then
  res "$(no_srv "sha256sum '$bak'" | cut -c1-64)" "$(sha "$TMP/smoke_transfer.txt")" ".bak tem o conteúdo anterior"
  res "$(no_srv "cat '$cam'")" "v2" "o arquivo tem o novo"
  res "$(no_srv "stat -c %a '$cam'")" 664 "modo 664 preservado na sobrescrita"
  no_srv "rm -f '$cam' '$bak'"
else SOBRAS="$SOBRAS $bak"; fi

echo "== i) extensão fora da lista / sem extensão / nome com maiúscula =="
r=$(enviar "$PASTA" qualquer.exe "$TMP/v2.txt"); res "$(status "$r")" 422 "exe recusada"; printf '  %s\n' "$(corpo "$r" | jq_ "d['detail']")"
r=$(enviar "$PASTA" script.SH "$TMP/v2.txt"); res "$(status "$r")" 422 "SH recusada (compara em minúsculas)"
r=$(enviar "$PASTA" README "$TMP/v2.txt"); res "$(status "$r")" 422 "sem extensão recusado"
r=$(enviar "$PASTA" RELATORIO.TXT "$TMP/v2.txt"); res "$(status "$r")" 200 "RELATORIO.TXT aceito com txt na lista"
res "$(corpo "$r" | jq_ "d['caminho'].endswith('/RELATORIO.TXT')")" True "nome mantido como está"
if [ -n "$(no_srv 'echo ok')" ]; then no_srv "rm -f '$PASTA/RELATORIO.TXT'"; else SOBRAS="$SOBRAS $PASTA/RELATORIO.TXT"; fi

echo "== j) Content-Length acima do teto → 413 antes do corpo; sem Content-Length → 411 =="
# Só direto na API: o nginx bufferiza o corpo e reenvia com Content-Length (um chunked
# vira 200 e um Content-Length mentiroso vira 400 do próprio nginx após o timeout).
if printf '%s' "$B" | grep -q '/orquestra'; then
  echo "  (atrás do nginx: passo j pulado — rode com ORQ_URL apontando direto para a API, porta 8000)"
else
  t0=$(date +%s); r=$(enviar "$PASTA" grande.txt "$TMP/v2.txt" false -H "Content-Length: $((teto_kb*1024+1))" --max-time 8); t1=$(date +%s)
  res "$(status "$r")" 413 "Content-Length de 50 MB + 1"; res "$([ $((t1-t0)) -le 3 ] && echo rapido)" rapido "recusado sem ler o corpo (≤ 3 s)"
  r=$(enviar "$PASTA" chunked.txt "$TMP/v2.txt" false -H "Transfer-Encoding: chunked" -H "Content-Length:"); res "$(status "$r")" 411 "sem Content-Length (chunked)"
  if [ -n "$(no_srv 'echo ok')" ]; then
    res "$(no_srv "ls -a '$PASTA'" | grep -c 'grande.txt\|chunked.txt')" 0 "nada gravado"
    no_srv "rm -f '$PASTA/grande.txt' '$PASTA/chunked.txt'"
  fi
fi

echo "== k) cliente desiste no meio do envio: nenhuma escrita parcial (o SSH só começa com o corpo inteiro) =="
if printf '%s' "$B" | grep -q '/orquestra'; then
  echo "  (atrás do nginx: passo k pulado — o proxy recebe o corpo inteiro antes de chamar a API; cancelar no navegador depois disso GRAVA o arquivo)"
elif [ -n "$(no_srv 'echo ok')" ]; then
  head -c $((30*1024*1024)) /dev/urandom > "$TMP/smoke_30mb.bin"
  ( enviar "$PASTA" smoke_30mb.txt "$TMP/smoke_30mb.bin" false --limit-rate 5M --max-time 2 >/dev/null 2>&1 ) ; sleep 2
  res "$(no_srv "ls -a '$PASTA'" | grep -c 'smoke_30mb')" 0 "nem o arquivo nem o .tmp existem"
  res "$(enviar "$PASTA" depois.txt "$TMP/v2.txt" | tail -n1)" 200 "envio normal depois da desistência"
  no_srv "rm -f '$PASTA/depois.txt'"
else echo "  (sem acesso ao servidor de arquivos: passo k NÃO executado — interrompa um envio grande e confira que não ficou .tmp na pasta)"; fi

echo "== k2) rollback de verdade: rename do original recusado (subpasta 1777 de outro dono) → 403, original íntegro, sem .tmp =="
# Como /tmp: pasta 1777 do root, arquivo do root. O usuário SSH cria o .tmp (pode), mas o
# rename do original para .bak é EPERM (sticky: não é dono do arquivo nem da pasta).
# (Sticky na pasta do PRÓPRIO usuário não prova nada: o dono da pasta renomeia tudo.)
if [ -n "$(no_srv 'echo ok')" ]; then
  no_srv "mkdir -p '$PASTA/smoke_sticky' && chown root:root '$PASTA/smoke_sticky' && chmod 1777 '$PASTA/smoke_sticky' && printf 'alheio\n' > '$PASTA/smoke_sticky/alheio.txt'"
  r=$(enviar "$PASTA/smoke_sticky" alheio.txt "$TMP/v2.txt" true); res "$(status "$r")" 403 "sobrescrever arquivo de outro dono em pasta sticky"
  printf '  %s\n' "$(corpo "$r" | jq_ "d['detail']")"
  res "$(no_srv "cat '$PASTA/smoke_sticky/alheio.txt'")" alheio "original íntegro"
  res "$(no_srv "ls -a '$PASTA/smoke_sticky'" | grep -c '\.tmp-\|\.bak-')" 0 "nenhum .tmp nem .bak sobrou"
  no_srv "rm -rf '$PASTA/smoke_sticky'"
else echo "  (sem acesso ao servidor de arquivos: passo k2 NÃO executado)"; fi

echo "== l) UI/credencial de operador: a aba Enviar arquivo aparece desabilitada; PUT /utilitarios/arquivo/enviar direto → 403 auditado como negado =="
echo "== k3) UI: enviar ~40 MB e clicar Cancelar no meio → modal 'cancelado antes de terminar', nada no servidor; cancelar DEPOIS de subir inteiro é impossível (o botão some, X/Esc não interrompem) e o resultado chega =="

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
  # Cliente que desiste no meio (fecha depois de 64 KB): a API segue servindo e a vaga volta.
  curl -s -u "$AUTH" -G "$B/utilitarios/arquivo/baixar" --data-urlencode "diretorio=$PASTA" --data-urlencode "nome=smoke_20mb.bin" 2>/dev/null | head -c 65536 > /dev/null
  sleep 1; res "$(baixar "$PASTA" smoke_20mb.bin "$TMP/m_depois.out")" 200 "download normal depois de um cliente desistir no meio"
  no_srv "rm -f '$PASTA/smoke_20mb.bin'"
else echo "  (sem acesso ao servidor de arquivos: passo m NÃO executado — dispare 6 downloads de um arquivo de ~20 MB em paralelo: espera 200 e 503, nada mais)"; fi

echo "== n) auditoria: baixar com tamanho e sha256, sem conteúdo =="
if docker exec orquestra-api true 2>/dev/null; then
  vaz=$(docker exec -i orquestra-api python - <<'PY'
from db import get_db_conn
c = get_db_conn(); cur = c.cursor()
cur.execute("SELECT TOP 16 acao, resultado, LEFT(caminho, 45), tamanho_bytes, LEFT(sha256, 8) FROM dbo.etl_utilitario_arquivo_log WHERE acao IN ('baixar', 'enviar') ORDER BY id DESC")
for r in cur.fetchall(): print("  ", tuple(r))
cur.execute("SELECT COUNT(*) FROM dbo.etl_utilitario_arquivo_log WHERE acao IN ('baixar', 'enviar') AND resultado = 'ok' AND (sha256 IS NULL OR tamanho_bytes IS NULL)")
print(cur.fetchone()[0])
PY
)
  res "$(printf '%s' "$vaz" | tail -n1)" 0 "todo 'baixar'/'enviar' ok tem tamanho e sha256"; printf '%s\n' "$vaz" | sed '$d'
else echo "  SELECT TOP 20 acao, resultado, caminho, tamanho_bytes, sha256 FROM dbo.etl_utilitario_arquivo_log WHERE acao IN ('baixar','enviar') ORDER BY id DESC"; fi
echo; echo "RESULTADO: $ok ok, $falha falhas (itens UI à parte)"
[ "$falha" -eq 0 ]
