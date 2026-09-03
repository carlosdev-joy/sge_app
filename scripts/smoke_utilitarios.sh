#!/bin/bash
# Smoke dos Utilitários de arquivos (spec docs/spec-utilitarios-arquivos.md §7, itens a–p)
# pela API. Roda no DEV (sshd-amostra) ou em produção. Nunca imprime credenciais.
#
# Uso:  ORQ_URL=http://localhost:8000 ORQ_USER=... ORQ_PASS=... RAIZ=/dados/bi \
#         PASTA=/dados/bi/2026 ARQ=consulta.sql LATIN1=/dados/param/parametros_latin1.param \
#         scripts/smoke_utilitarios.sh
#       (sem variáveis, lê .env.dev e usa as raízes do sshd-amostra)
# Os itens a, b, f e a parte visual do j exigem o navegador — ficam marcados "UI".
set -u
cd "$(dirname "$0")/.."
if [ -z "${ORQ_USER:-}" ] && [ -f .env.dev ]; then set -a; . ./.env.dev 2>/dev/null; set +a; fi
B=${ORQ_URL:-http://localhost:8000}
AUTH="${ORQ_USER:-$DEV_AIRFLOW_USER}:${ORQ_PASS:-$DEV_AIRFLOW_PASSWORD}"
RAIZ=${RAIZ:-/dados/bi}; PASTA=${PASTA:-/dados/bi/2026}; ARQ=${ARQ:-consulta.sql}
LATIN1=${LATIN1:-/dados/param/parametros_latin1.param}
SSHD=${SSHD:-orquestra-dev-sshd-amostra}   # só no DEV: permite conferir no servidor
ok=0; falha=0
res() { if [ "$1" = "$2" ]; then ok=$((ok+1)); printf '  ✅ %s → %s\n' "$3" "$2"; else falha=$((falha+1)); printf '  ❌ %s → esperado %s, veio %s  %s\n' "$3" "$2" "$1" "${4:-}"; fi; }
call() { local m=$1 p=$2 d=${3:-}; if [ -n "$d" ]; then curl -s -u "$AUTH" -X "$m" "$B$p" -H 'Content-Type: application/json' -d "$d" -w '\n%{http_code}'; else curl -s -u "$AUTH" -X "$m" "$B$p" -w '\n%{http_code}'; fi; }
status() { printf '%s' "$1" | tail -n1; }
corpo() { printf '%s' "$1" | sed '$d'; }
jq_() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)" 2>/dev/null; }
no_srv() { docker exec "$SSHD" sh -c "$1" 2>/dev/null; }
# Extensões: NUNCA inclui o que não estava (produção pode ter excluído de propósito) e
# devolve o que excluiu mesmo se o script morrer no meio (trap).
ext_presente() { call GET /utilitarios/admin/extensoes | sed '$d' | jq_ "'$1' in [x['extensao'] for x in d]" | grep -q True; }
REMOVIDAS=""
repor_extensao() { local r; r=$(call POST /utilitarios/admin/extensoes "{\"extensao\":\"$1\"}"); res "$(status "$r")" 200 "incluir $1 de volta"; REMOVIDAS=${REMOVIDAS// $1/}; }
excluir_e_repor() { if ext_presente "$1"; then local r; r=$(call DELETE /utilitarios/admin/extensoes/$1); res "$(status "$r")" 200 "excluir $1"; REMOVIDAS="$REMOVIDAS $1"; repor_extensao "$1"; else echo "  ($1 não está na lista: excluir/reincluir pulado)"; fi; }
SOBRAS=""
ao_sair() { local e; for e in $REMOVIDAS; do echo "  ⚠️ repondo a extensão $e (script interrompido)"; call POST /utilitarios/admin/extensoes "{\"extensao\":\"$e\"}" >/dev/null; done
  [ -n "$SOBRAS" ] && printf '  ⚠️ sem acesso ao servidor de arquivos, ficou para apagar à mão:%s\n' "$SOBRAS"; return 0; }
trap ao_sair EXIT

echo "== a) permissão por perfil: UI (sair e entrar; consulta não vê o menu) =="
r=$(call GET /utilitarios/config); res "$(status "$r")" 200 "config com a tela liberada"
echo "== b) checkbox Utilitários nos perfis: UI (Admin › Usuários & Perfis) =="
echo "== c) raízes: Testar cada uma; raiz relativa recusada =="
r=$(call GET /utilitarios/admin/raizes); res "$(status "$r")" 200 "listar raízes"
for id in $(corpo "$r" | jq_ "' '.join(str(x['id']) for x in d if x['ativo'])"); do
  t=$(call POST /utilitarios/admin/raizes/$id/testar); printf '  raiz %s: %s\n' "$id" "$(corpo "$t" | jq_ "d.get('detalhe')")"
done
r=$(call POST /utilitarios/admin/raizes '{"servidor":"datastage","caminho":"dados/relativa"}'); res "$(status "$r")" 422 "raiz relativa recusada"
echo "== d) extensões: excluir yml, incluir de volta; sh fora da lista =="
excluir_e_repor yml
r=$(call GET /utilitarios/admin/extensoes); res "$(corpo "$r" | jq_ "'sh' in [x['extensao'] for x in d]")" False "sh não está na lista"
echo "== e) ver arquivo: conteúdo idêntico ao servidor =="
r=$(call POST /utilitarios/arquivo/ler "{\"diretorio\":\"$(dirname $PASTA/$ARQ | sed 's#/$##')\",\"nome\":\"$ARQ\"}")
[ "$(status "$r")" = 200 ] || r=$(call POST /utilitarios/arquivo/ler "{\"diretorio\":\"$RAIZ\",\"nome\":\"$ARQ\"}")
res "$(status "$r")" 200 "ler $ARQ"
if [ -n "$(no_srv 'echo ok')" ]; then
  cam=$(corpo "$r" | jq_ "d['caminho']"); srv=$(no_srv "wc -lc < '$cam'" | awk '{print $1" "$2}')
  api="$(corpo "$r" | jq_ "str(d['linhas'])+' '+str(d['tamanho_bytes'])")"
  res "$api" "$srv" "linhas e bytes = wc -lc no servidor"
  res "$(corpo "$r" | python3 -c "import sys,json; sys.stdout.write(json.load(sys.stdin)['conteudo'])" | md5sum | cut -c1-8)" "$(no_srv "cat '$cam'" | md5sum | cut -c1-8)" "conteúdo = cat"
fi
echo "== f) Copiar → colar: UI =="
echo "== g) Latin-1 =="
r=$(call POST /utilitarios/arquivo/ler "{\"diretorio\":\"$(dirname $LATIN1)\",\"nome\":\"$(basename $LATIN1)\"}")
res "$(corpo "$r" | jq_ "d.get('codificacao')")" latin-1 "codificação detectada"
res "$(corpo "$r" | jq_ "'ção' in d.get('conteudo','')")" True "acento correto"
echo "== h) fora das raízes → 403 e auditoria negado =="
r=$(call POST /utilitarios/arquivo/ler '{"diretorio":"/etc","nome":"passwd"}'); res "$(status "$r")" 403 "/etc/passwd"
r=$(call POST /utilitarios/arquivo/ler "{\"diretorio\":\"$RAIZ/../../etc\",\"nome\":\"passwd\"}"); res "$(status "$r")" 403 "$RAIZ/../../etc/passwd"
echo "== i) acima do teto → 413 e últimas N linhas =="
teto=$(call GET /utilitarios/config | sed '$d' | jq_ "d['tamanho_max_kb']")
if [ -n "$(no_srv 'echo ok')" ]; then
  no_srv "awk 'BEGIN{for(i=1;i<=$((teto*40));i++) print \"linha \" i \" de log com texto para passar do teto\"}' > $PASTA/smoke_grande.log"
  r=$(call POST /utilitarios/arquivo/ler "{\"diretorio\":\"$PASTA\",\"nome\":\"smoke_grande.log\"}"); res "$(status "$r")" 413 "log acima do teto"
  r=$(call POST /utilitarios/arquivo/ler "{\"diretorio\":\"$PASTA\",\"nome\":\"smoke_grande.log\",\"ultimas_linhas\":200}")
  res "$(status "$r")" 200 "últimas 200 linhas"; res "$(corpo "$r" | jq_ "str(d['linhas'])+' '+str(d['truncado'])")" "200 True" "200 linhas inteiras e truncado"
  res "$(corpo "$r" | jq_ "d['conteudo'].splitlines()[-1].startswith('linha $((teto*40)) ')")" True "a última linha é a última do arquivo"
  no_srv "rm -f $PASTA/smoke_grande.log"
else echo "  (sem acesso ao servidor de arquivos: passo i NÃO executado — crie um log > ${teto} KB à mão e leia com 'últimas N linhas')"; fi
echo "== j) navegar =="
r=$(call GET "/utilitarios/pasta/listar"); res "$(status "$r")" 200 "nível zero"; printf '  raízes: %s\n' "$(corpo "$r" | jq_ "[e['nome'] for e in d['entradas']]")"
r=$(call GET "/utilitarios/pasta/listar?caminho=$PASTA"); res "$(status "$r")" 200 "listar $PASTA"
res "$(corpo "$r" | jq_ "d['pai']")" "$(dirname $PASTA)" "pai = pasta acima"
r=$(call GET "/utilitarios/pasta/listar?caminho=$RAIZ"); res "$(corpo "$r" | jq_ "d['pai']")" None "na raiz não sobe mais"
res "$(corpo "$r" | jq_ "any(e['nome'].startswith('.') for e in d['entradas'])")" False "ocultos não aparecem"
echo "== k) criar smoke_orquestra.txt =="
r=$(call POST /utilitarios/arquivo/gravar "{\"diretorio\":\"$PASTA\",\"nome\":\"smoke_orquestra\",\"extensao\":\"txt\",\"conteudo\":\"linha 1\r\nlinha 2 com ação\"}")
res "$(status "$r")" 200 "gravar novo"; res "$(corpo "$r" | jq_ "str(d['criado'])+' '+str(d['tamanho_bytes'])+' '+d['sha256'][:8]")" "True 27 $(printf 'linha 1\nlinha 2 com ação\n' | sha256sum | cut -c1-8)" "criado, 27 bytes (ação = 6 bytes), hash"
[ -n "$(no_srv 'echo ok')" ] || SOBRAS="$SOBRAS $PASTA/smoke_orquestra.txt"
if [ -n "$(no_srv 'echo ok')" ]; then
  res "$(no_srv "od -c $PASTA/smoke_orquestra.txt | grep -c '\\\\r'")" 0 "sem \\r no servidor"
  res "$(no_srv "tail -c1 $PASTA/smoke_orquestra.txt | od -An -c | tr -d ' '")" '\n' "termina em \\n"
fi
echo "== l) gravar de novo: 409, depois sobrescrever com .bak =="
r=$(call POST /utilitarios/arquivo/gravar "{\"diretorio\":\"$PASTA\",\"nome\":\"smoke_orquestra\",\"extensao\":\"txt\",\"conteudo\":\"v2\"}")
res "$(status "$r")" 409 "sem sobrescrever"; res "$(corpo "$r" | jq_ "str(d['detail']['existente']['tamanho_bytes'])")" 27 "409 traz tamanho do atual"
r=$(call POST /utilitarios/arquivo/gravar "{\"diretorio\":\"$PASTA\",\"nome\":\"smoke_orquestra\",\"extensao\":\"txt\",\"conteudo\":\"v2\",\"sobrescrever\":true}")
res "$(status "$r")" 200 "sobrescrever"; bak=$(corpo "$r" | jq_ "d['backup']"); printf '  backup: %s\n' "$bak"
[ -n "$(no_srv 'echo ok')" ] || SOBRAS="$SOBRAS $bak"
if [ -n "$(no_srv 'echo ok')" ]; then
  res "$(no_srv "cat '$bak' | head -1")" "linha 1" ".bak tem o conteúdo anterior"
  res "$(no_srv "cat $PASTA/smoke_orquestra.txt")" "v2" "o arquivo tem o novo"
  no_srv "rm -f $PASTA/smoke_orquestra.txt '$bak'"
fi
echo "== m) extensão fora da lista =="
r=$(call POST /utilitarios/arquivo/gravar "{\"diretorio\":\"$PASTA\",\"nome\":\"smoke\",\"extensao\":\"exe\",\"conteudo\":\"x\"}"); res "$(status "$r")" 422 "exe recusada"
if ext_presente txt; then
  r=$(call DELETE /utilitarios/admin/extensoes/txt); res "$(status "$r")" 200 "excluir txt"; REMOVIDAS="$REMOVIDAS txt"
  r=$(call POST /utilitarios/arquivo/gravar "{\"diretorio\":\"$PASTA\",\"nome\":\"smoke\",\"extensao\":\"txt\",\"conteudo\":\"x\"}")
  res "$(status "$r")" 422 "txt recusada depois de excluída"; printf '  %s\n' "$(corpo "$r" | jq_ "d['detail']")"
  repor_extensao txt
else echo "  (txt não está na lista: o passo de excluir/reincluir foi pulado)"; fi
echo "== n) operador: UI (editor desabilitado) + POST gravar → 403: exige credencial de operador =="
echo "== o) carregar Latin-1, alterar e gravar de volta (numa cópia) =="
[ -n "$(no_srv 'echo ok')" ] || echo "  (sem acesso ao servidor de arquivos: passo o NÃO executado — faça pela tela num arquivo Latin-1 de teste)"
if [ -n "$(no_srv 'echo ok')" ]; then
  no_srv "cp '$LATIN1' $PASTA/smoke_latin1.param"
  r=$(call POST /utilitarios/arquivo/ler "{\"diretorio\":\"$PASTA\",\"nome\":\"smoke_latin1.param\"}")
  conteudo=$(corpo "$r" | jq_ "json.dumps(d['conteudo'] + 'NOVA=1\n')")
  r=$(call POST /utilitarios/arquivo/gravar "{\"diretorio\":\"$PASTA\",\"nome\":\"smoke_latin1\",\"extensao\":\"param\",\"conteudo\":$conteudo,\"codificacao\":\"latin-1\",\"sobrescrever\":true}")
  res "$(status "$r")" 200 "gravar em latin-1"
  res "$(no_srv "od -An -tx1 $PASTA/smoke_latin1.param | tr -d ' \n' | grep -c 'e7e3'")" 1 "ç e ã continuam em Latin-1 (e7 e3)"
  no_srv "rm -f $PASTA/smoke_latin1.param $PASTA/smoke_latin1.param.bak-*"
fi
echo "== p) auditoria =="
if [ -n "$(no_srv 'echo ok')" ]; then
  vaz=$(docker exec -i orquestra-api python - <<'PY'
from db import get_db_conn
c = get_db_conn(); cur = c.cursor()
cur.execute("SELECT TOP 12 acao, resultado, LEFT(caminho, 45), LEFT(sha256, 8) FROM dbo.etl_utilitario_arquivo_log ORDER BY id DESC")
for r in cur.fetchall(): print("  ", tuple(r))
cur.execute("SELECT COUNT(*) FROM dbo.etl_utilitario_arquivo_log WHERE detalhe LIKE '%linha 2 com%' OR caminho LIKE '%linha 2 com%'")
print(cur.fetchone()[0])
PY
)
  res "$(printf '%s' "$vaz" | tail -n1)" 0 "nenhuma linha da auditoria contém conteúdo de arquivo"; printf '%s\n' "$vaz" | sed '$d'
else echo "  SELECT TOP 20 acao, resultado, caminho, sha256 FROM dbo.etl_utilitario_arquivo_log ORDER BY id DESC"; fi
echo; echo "RESULTADO: $ok ok, $falha falhas (itens UI à parte)"
[ "$falha" -eq 0 ]
