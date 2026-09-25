#!/bin/bash
# =============================================================================
# smoke_admin.sh — o aceite da reestruturação do Admin, medido pela API.
# (docs/spec-admin-reestruturacao.md §8 — F6)
#
# Uso (depois do deploy, de qualquer máquina que alcance o Orquestra):
#     ORQ_USUARIO=admin ORQ_SENHA='…' bash scripts/smoke_admin.sh
#     ORQ_API=https://servidor/orquestra ORQ_UI=https://servidor \
#         ORQ_USUARIO=… ORQ_SENHA=… bash scripts/smoke_admin.sh
#
#   ORQ_API     base da API          (padrão: http://localhost:8090/orquestra)
#   ORQ_UI      base da SPA          (padrão: ORQ_API sem o "/orquestra" final)
#   ORQ_USUARIO / ORQ_SENHA          login de um usuário com tela_admin + acao_admin
#                                    — a senha vem do ambiente, NUNCA deste arquivo.
#
# O que é automatizável vira checagem com ✓/✗; o que precisa de olho humano
# (clicar, F5, Sheet no celular) sai no fim como o checklist letrado da §8.
#
# Não grava nada: as duas tentativas de escrita (config_upsert/config_delete de
# chave com dono) são RECUSADAS antes de abrir conexão com o banco — é
# exatamente isso que se confere. Requer curl e python3.
# =============================================================================
set -uo pipefail

ORQ_API="${ORQ_API:-http://localhost:8090/orquestra}"
ORQ_API="${ORQ_API%/}"
ORQ_UI="${ORQ_UI:-${ORQ_API%/orquestra}}"
ORQ_UI="${ORQ_UI%/}"
FALHAS=0
TOTAL=0
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

_ok()    { printf '  \033[32m✓\033[0m %s\n' "$1"; }
_falha() { printf '  \033[31m✗\033[0m %s\n' "$1"; FALHAS=$((FALHAS + 1)); }
_info()  { printf '    %s\n' "$1"; }

_checar() {  # $1 = descrição   $2 = "ok" ou qualquer outra coisa   $3 = detalhe
    TOTAL=$((TOTAL + 1))
    if [ "$2" = "ok" ]; then _ok "$1"; else _falha "$1"; _info "$3"; fi
}

# POST /admin com a sessão. $1 = corpo JSON, $2 = arquivo de saída. Imprime o HTTP.
_admin() {
    curl -sS -o "$2" -w '%{http_code}' -X POST "$ORQ_API/admin" \
         -H 'Content-Type: application/json' -H "Authorization: Bearer $TOKEN" \
         --data "$1" 2>/dev/null || echo "000"
}

# Padrões de chave sensível — ESPELHO de PADROES_SEGREDO em
# api/services/admin_config_donos.py (tests/test_migrations_126_127_admin.py prende).
SEGREDO="('teams_webhook','caixa_ia_api_key','ia_api_key','secret','password','token','senha','webhook','_key','_enc')"

# Lê um campo do JSON salvo (python3; sem jq no servidor air-gapped).
_json() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print($2)" "$1" 2>/dev/null; }

echo "============================================="
echo " SMOKE — Admin reestruturado   $(date '+%Y-%m-%d %H:%M')"
echo " API: $ORQ_API   UI: $ORQ_UI"
echo "============================================="

if [ -z "${ORQ_USUARIO:-}" ] || [ -z "${ORQ_SENHA:-}" ]; then
    echo "Defina ORQ_USUARIO e ORQ_SENHA no ambiente (a senha não fica no script)." >&2
    exit 2
fi

# ── 1. Login ─────────────────────────────────────────────────────────────────
echo
echo "[1] Login"
CORPO=$(ORQ_USUARIO="$ORQ_USUARIO" ORQ_SENHA="$ORQ_SENHA" python3 -c \
  'import json,os; print(json.dumps({"usuario": os.environ["ORQ_USUARIO"], "senha": os.environ["ORQ_SENHA"]}))')
HTTP=$(curl -sS -o "$TMP/login.json" -w '%{http_code}' -X POST "$ORQ_API/auth/login" \
            -H 'Content-Type: application/json' --data "$CORPO" 2>/dev/null || echo "000")
TOKEN=$(_json "$TMP/login.json" "d.get('token','')")
TEM_ADMIN=$(_json "$TMP/login.json" "'sim' if {'tela_admin','acao_admin'} <= set(d['usuario'].get('permissoes') or []) else 'nao'")
_checar "login responde 200 com token" "$([ "$HTTP" = "200" ] && [ -n "$TOKEN" ] && echo ok)" "HTTP $HTTP"
_checar "o usuário tem tela_admin e acao_admin" "$([ "$TEM_ADMIN" = "sim" ] && echo ok)" \
        "sem as duas permissões os passos seguintes dão 403 — use um administrador"
[ -z "$TOKEN" ] && { echo; echo "Sem sessão — interrompido."; exit 1; }

# ── 2. /config público sem segredo ───────────────────────────────────────────
echo
echo "[2] GET /config (público, sem login) não expõe segredo"
HTTP=$(curl -sS -o "$TMP/config.json" -w '%{http_code}' "$ORQ_API/config" 2>/dev/null || echo "000")
VAZADAS=$(_json "$TMP/config.json" "','.join(k for k in d if any(p in k.lower() for p in $SEGREDO)) or '-'")
VERSAO=$(_json "$TMP/config.json" "d.get('app_version') or '-'")
_checar "GET /config responde 200" "$([ "$HTTP" = "200" ] && echo ok)" "HTTP $HTTP"
_checar "nenhuma chave sensível no /config" "$([ "$VAZADAS" = "-" ] && echo ok)" "vazaram: $VAZADAS"
_info "app_version publicada: $VERSAO  (confira em Admin › Sistema › Versões)"

# ── 3. config_list mascara segredo ───────────────────────────────────────────
echo
echo "[3] Parâmetros avançados (config_list) não devolve segredo cru"
HTTP=$(_admin '{"action":"config_list"}' "$TMP/list.json")
CRUAS=$(_json "$TMP/list.json" "','.join(k for k, v in d['config'].items() if v and any(p in k.lower() for p in $SEGREDO) and not str(v).startswith('••••')) or '-'")
FERNET=$(_json "$TMP/list.json" "','.join(k for k, v in d['config'].items() if str(v or '').startswith('gAAAAA')) or '-'")
_checar "config_list responde 200" "$([ "$HTTP" = "200" ] && echo ok)" "HTTP $HTTP"
_checar "toda chave sensível (*_enc, *senha*, *webhook*…) volta mascarada" \
        "$([ "$CRUAS" = "-" ] && echo ok)" "em claro: $CRUAS"
_checar "nenhum token Fernet (gAAAAA…) na resposta" "$([ "$FERNET" = "-" ] && echo ok)" "cifrado exposto em: $FERNET"
# Zero chave sensível com valor = checagem vazia (verde que não prova nada).
N_SENS=$(_json "$TMP/list.json" "sum(1 for k, v in d['config'].items() if v and any(p in k.lower() for p in $SEGREDO))")
_info "${N_SENS:-0} chave(s) sensível(is) com valor conferida(s)"
[ "${N_SENS:-0}" = "0" ] && _info "⚠ nenhuma chave sensível preenchida neste ambiente — a checagem acima não exercitou a máscara"

# ── 4. Trava de escrita da F5: chave com dono → 422 ──────────────────────────
echo
echo "[4] Editor genérico recusa chave que tem aba dona (422, sem tocar o banco)"
HTTP=$(_admin '{"action":"config_upsert","config_key":"email_remetente","config_value":"smoke@exemplo.invalid"}' "$TMP/u1.json")
DET=$(_json "$TMP/u1.json" "d.get('detail','')")
_checar "config_upsert email_remetente → 422 citando Comunicação › E-mail" \
        "$([ "$HTTP" = "422" ] && [[ "$DET" == *"Comunicação › E-mail"* ]] && echo ok)" "HTTP $HTTP — $DET"
HTTP=$(_admin '{"action":"config_delete","config_key":"email_remetente"}' "$TMP/u2.json")
_checar "config_delete email_remetente → 422" "$([ "$HTTP" = "422" ] && echo ok)" "HTTP $HTTP — $(_json "$TMP/u2.json" "d.get('detail','')")"
HTTP=$(_admin '{"action":"config_upsert","config_key":"teams_webhook_url","config_value":"https://exemplo.invalid"}' "$TMP/u3.json")
_checar "config_upsert teams_webhook_url → 422 (dono: Teams)" "$([ "$HTTP" = "422" ] && echo ok)" "HTTP $HTTP — $(_json "$TMP/u3.json" "d.get('detail','')")"
# "ｅmail_remetente" com o ｅ FULLWIDTH (U+FF45): no SQL Server casaria com a
# linha verdadeira; a API recusa chave fora de [A-Za-z0-9_.-].
HTTP=$(_admin '{"action":"config_upsert","config_key":"ｅmail_remetente","config_value":"smoke@exemplo.invalid"}' "$TMP/u4.json")
_checar "chave com caractere fullwidth → 422" "$([ "$HTTP" = "422" ] && echo ok)" "HTTP $HTTP — $(_json "$TMP/u4.json" "d.get('detail','')")"
HTTP=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$ORQ_API/admin" -H 'Content-Type: application/json' \
            --data '{"action":"config_list"}' 2>/dev/null || echo "000")
_checar "POST /admin sem sessão → 401" "$([ "$HTTP" = "401" ] && echo ok)" "HTTP $HTTP"

# ── 5. A SPA serve os endereços novos ────────────────────────────────────────
echo
echo "[5] Endereços do Admin (SPA)"
for caminho in /admin /admin/comunicacao/email /admin/sistema/parametros /admin/sistema/config; do
    HTTP=$(curl -sS -o "$TMP/spa.html" -w '%{http_code}' "$ORQ_UI$caminho" 2>/dev/null || echo "000")
    _checar "GET $caminho → 200 com a SPA" \
            "$([ "$HTTP" = "200" ] && grep -q 'id="root"' "$TMP/spa.html" && echo ok)" "HTTP $HTTP"
done

# ── Fecho ────────────────────────────────────────────────────────────────────
echo
echo "============================================="
if [ "$FALHAS" -eq 0 ]; then
    printf ' \033[32mSMOKE OK\033[0m — %d verificações\n' "$TOTAL"
else
    printf ' \033[31m%d de %d FALHARAM\033[0m\n' "$FALHAS" "$TOTAL"
fi
echo "============================================="
cat <<'EOF'

Checklist manual (spec §8 — precisa de olho humano, no navegador):
  a) Abrir /admin: cai em Acesso › Usuários, ou na última aba visitada.
  b) Comunicação › E-mail e F5: continua em E-mail. "Copiar link", abrir em outra aba: mesma tela.
  c) Buscar teams_webhook_url: leva a Teams, onde o "Testar Webhook" funciona.
  d) Buscar xyz123: aparece a mensagem de nada encontrado.
  e) IA › Triagem de chamados: liga e desliga, e o valor persiste.
  f) ServiceNow › Diagnóstico: roda a sonda e mostra as tabelas.
  g) /performance: gera a Aderência ao SLA do mês.
  h) /powerbi: a seção "Como liberar acessos" abre.
  i) Sistema › Parâmetros avançados: não lista email_* nem teams_*, mas lista app_base_url.
  j) ⌘K (Ctrl+K) "agentes": aparece Inteligência Artificial › Agentes (e "e-mail" → Comunicação › E-mail).
  k) Celular (390 px): o seletor abre o Sheet e navega.
EOF
exit $((FALHAS > 0))
