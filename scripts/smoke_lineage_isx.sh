#!/usr/bin/env bash
# Smoke do lineage ISX pela API (spec docs/spec-lineage-isx.md, §7 itens c–i).
#
# Uso (a senha pelo `read -s`, para não ficar no histórico do shell):
#   read -rs ORQ_PASS; export ORQ_PASS
#   ORQ_URL=http://host:8000 ORQ_USER=matricula \
#   PIPELINE=PIPE_VIDA JOB=SsdVidaDimePessoa02Ftp JOB_SEQ=SeqSsdVidaDime \
#   scripts/smoke_lineage_isx.sh
#
# ORQ_USER precisa de acao_editar (extrair). JOB e JOB_SEQ têm de estar mapeados
# no PIPELINE. Nada é gravado fora do lineage ISX do job; a senha só vai no corpo
# do login (por arquivo temporário 0700, não no argv).
set -euo pipefail

: "${ORQ_URL:?defina ORQ_URL (ex.: http://localhost:8000)}"
: "${ORQ_USER:?defina ORQ_USER}"
: "${ORQ_PASS:?defina ORQ_PASS}"
: "${PIPELINE:?defina PIPELINE}"
: "${JOB:?defina JOB}"
JOB_SEQ="${JOB_SEQ:-}"

ok()   { printf '  \033[32mOK\033[0m   %s\n' "$*"; }
fail() { printf '  \033[31mFALHOU\033[0m %s\n' "$*"; FALHAS=$((FALHAS + 1)); }
FALHAS=0
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

jq_ok() { command -v jq >/dev/null 2>&1; }
campo() { # campo <arquivo> <expr jq> — sem jq, imprime como o `jq -r` (true/false/null)
  if jq_ok; then jq -r "$2" "$1"; else
    python3 - "$1" "$2" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); v = d.get(sys.argv[2].lstrip("."))
print(json.dumps(v) if isinstance(v, (bool, type(None))) else v)
PY
  fi
}
chamar() { # chamar <nome> <método> <caminho> [corpo] → grava $TMP/<nome>.json e devolve o status
  local nome=$1 metodo=$2 caminho=$3 corpo=${4:-}
  local args=(-s -o "$TMP/$nome.json" -w '%{http_code}' -X "$metodo" "$ORQ_URL$caminho")
  [ -n "${TOKEN:-}" ] && args+=(-H "Authorization: Bearer $TOKEN")
  [ -n "$corpo" ] && args+=(-H 'Content-Type: application/json' -d "$corpo")
  curl "${args[@]}"
}
enc() { python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$1"; }

echo "▶ login"
# O corpo com a senha vai por ARQUIVO (pasta 0700 do mktemp), nunca no argv do curl
# (visível em `ps`); o JSON é montado pelo python (senha com aspas não quebra).
python3 - > "$TMP/login_body.json" <<'PY'
import json, os
print(json.dumps({"usuario": os.environ["ORQ_USER"], "senha": os.environ["ORQ_PASS"]}))
PY
st=$(curl -s -o "$TMP/login.json" -w '%{http_code}' -X POST "$ORQ_URL/auth/login" \
  -H 'Content-Type: application/json' -d @"$TMP/login_body.json")
rm -f "$TMP/login_body.json"
[ "$st" = "200" ] || { echo "login falhou ($st)"; cat "$TMP/login.json"; exit 1; }
TOKEN=$(campo "$TMP/login.json" .token)
[ -n "$TOKEN" ] && [ "$TOKEN" != "None" ] || { echo "login sem token"; exit 1; }
ok "token obtido"

P=$(enc "$PIPELINE"); J=$(enc "$JOB")

echo "▶ c) localizar"
st=$(chamar c GET "/lineage/isx/localizar?pipeline_name=$P&job_name=$J")
if [ "$st" = "200" ] && [ "$(campo "$TMP/c.json" .encontrado)" = "true" ]; then
  ok "encontrado: pasta $(campo "$TMP/c.json" .folder_path) tipo $(campo "$TMP/c.json" .job_type) mod $(campo "$TMP/c.json" .last_modified)"
else fail "localizar → $st: $(cat "$TMP/c.json")"; fi

echo "▶ d) extrair (1ª vez, force para garantir o miss)"
t0=$(date +%s)
st=$(chamar d POST "/lineage/isx/extrair" "{\"pipeline_name\":\"$PIPELINE\",\"job_name\":\"$JOB\",\"force\":true}")
dt=$(( $(date +%s) - t0 ))
if [ "$st" = "200" ] && [ "$(campo "$TMP/d.json" .cache_hit)" = "false" ] && [ "$(campo "$TMP/d.json" .status)" = "ok" ]; then
  n=$(python3 -c "import json;print(len(json.load(open('$TMP/d.json'))['stages']))")
  sql=$(python3 -c "import json;print(sum(1 for s in json.load(open('$TMP/d.json'))['stages'] if s.get('sql_expression')))")
  ok "cache_hit=false, $n stages ($sql com SQL), extracted_by=$(campo "$TMP/d.json" .extracted_by), ${dt}s"
else fail "extrair → $st em ${dt}s: $(head -c 400 "$TMP/d.json")"; fi

echo "▶ e) extrair de novo → cache"
t0=$(date +%s%N)
st=$(chamar e POST "/lineage/isx/extrair" "{\"pipeline_name\":\"$PIPELINE\",\"job_name\":\"$JOB\"}")
dt=$(( ($(date +%s%N) - t0) / 1000000 ))
if [ "$st" = "200" ] && [ "$(campo "$TMP/e.json" .cache_hit)" = "true" ]; then ok "cache_hit=true em ${dt} ms"
else fail "cache → $st cache_hit=$(campo "$TMP/e.json" .cache_hit) em ${dt} ms"; fi
echo "     (manual: no servidor do DataStage, 'ps -ef | grep istool' durante o d mostra -authfile, nunca a senha)"

echo "▶ f) force → reextrai; linhas manual/dsx_auto do job continuam"
sleep 1   # extracted_at é DATETIME2(0): no mesmo segundo do item d o valor não mudaria
st=$(chamar f POST "/lineage/isx/extrair" "{\"pipeline_name\":\"$PIPELINE\",\"job_name\":\"$JOB\",\"force\":true}")
if [ "$st" = "200" ] && [ "$(campo "$TMP/f.json" .cache_hit)" = "false" ] \
   && [ "$(campo "$TMP/f.json" .extracted_at)" != "$(campo "$TMP/d.json" .extracted_at)" ]; then ok "reextraído em $(campo "$TMP/f.json" .extracted_at)"
else fail "force → $st cache_hit=$(campo "$TMP/f.json" .cache_hit)"; fi
echo "     (manual: SELECT extraction_method, COUNT(*) FROM dbo.etl_job_lineage WHERE job_name='$JOB' GROUP BY extraction_method)"

echo "▶ g) job fora de pipeline → 422; nome com ';' → 422 antes do SSH"
st=$(chamar g1 POST "/lineage/isx/extrair" "{\"pipeline_name\":\"$PIPELINE\",\"job_name\":\"JobQueNaoExisteNoPipeline_$$\"}")
[ "$st" = "422" ] && ok "fora do pipeline → 422: $(campo "$TMP/g1.json" .detail | head -c 90)" || fail "fora do pipeline → $st"
st=$(chamar g2 POST "/lineage/isx/extrair" "{\"pipeline_name\":\"$PIPELINE\",\"job_name\":\"x; id\"}")
[ "$st" = "422" ] && ok "nome inválido → 422" || fail "nome inválido → $st"

if [ -n "$JOB_SEQ" ]; then
  echo "▶ h) sequence → ds_job_type SEQUENCE e filhos"
  st=$(chamar h POST "/lineage/isx/extrair" "{\"pipeline_name\":\"$PIPELINE\",\"job_name\":\"$JOB_SEQ\",\"force\":true}")
  if [ "$st" = "200" ] && [ "$(campo "$TMP/h.json" .job_type)" = "SEQUENCE" ]; then
    ok "SEQUENCE com filhos: $(python3 -c "import json;print([c['job_name'] for c in json.load(open('$TMP/h.json'))['children']])")"
  else fail "sequence → $st job_type=$(campo "$TMP/h.json" .job_type): $(head -c 300 "$TMP/h.json")"; fi
else
  echo "▶ h) pulado (defina JOB_SEQ)"
fi

echo "▶ i) GET /lineage sem token → 401; com token, o job mostra só isx_auto"
st=$(curl -s -o /dev/null -w '%{http_code}' "$ORQ_URL/lineage?pipeline_name=$P")
[ "$st" = "401" ] && ok "sem token → 401" || fail "sem token → $st"
st=$(chamar i GET "/lineage?pipeline_name=$P")
if [ "$st" = "200" ]; then
  metodos=$(python3 - "$TMP/i.json" "$JOB" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); job = sys.argv[2]
for j in d["jobs"]:
    if j["job_name"] == job:
        print(sorted({x["extraction_method"] for g in ("origens", "transformacoes", "destinos") for x in j[g]}))
        break
else:
    print("job não está na resposta")
PY
)
  [ "$metodos" = "['isx_auto']" ] && ok "job $JOB só com isx_auto" || fail "métodos do job: $metodos"
else fail "GET /lineage com token → $st"; fi

echo "▶ estado do pipeline"
st=$(chamar p GET "/lineage/isx/pipeline?pipeline_name=$P")
[ "$st" = "200" ] && ok "$(python3 -c "import json;d=json.load(open('$TMP/p.json'));print(sum(1 for j in d['jobs'] if j['isx']), 'de', len(d['jobs']), 'jobs com ISX')")" || fail "pipeline → $st"

echo
if [ "$FALHAS" = 0 ]; then echo "✔ smoke ISX: tudo OK"; else echo "✘ smoke ISX: $FALHAS falha(s)"; exit 1; fi
