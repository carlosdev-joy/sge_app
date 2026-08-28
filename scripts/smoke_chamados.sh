#!/bin/bash
# =============================================================================
# smoke_chamados.sh — o aceite do módulo de Chamados, medido.
#
# Uso (no servidor, com os containers de pé):
#     cd /opt/airflow && bash scripts/smoke_chamados.sh
#
# ⚠️ POR QUE UM SCRIPT, E NÃO UMA LISTA PARA CONFERIR A OLHO.
# A §7.3 da spec do porte pedia seis passos manuais. Conferir "a aba
# Indicadores bate com a Fila no total" a olho significa ler dois números em
# telas diferentes e confiar na memória — que é exatamente o modo de falso
# verde que este módulo pagou várias vezes. Aqui os dois números são LIDOS e
# COMPARADOS, e a saída diz qual falhou.
#
# Não escreve nada. Só lê o banco e a API.
# =============================================================================
set -uo pipefail

API="${API:-orquestra-api}"
FALHAS=0
TOTAL=0

_ok()    { printf '  \033[32m✓\033[0m %s\n' "$1"; }
_falha() { printf '  \033[31m✗\033[0m %s\n' "$1"; FALHAS=$((FALHAS + 1)); }
_info()  { printf '    %s\n' "$1"; }

_checar() {  # $1 = descrição   $2 = "ok" ou qualquer outra coisa   $3 = detalhe
    TOTAL=$((TOTAL + 1))
    if [ "$2" = "ok" ]; then _ok "$1"; else _falha "$1"; _info "$3"; fi
}

# Roda um python dentro do container da API — ele já tem pyodbc e a conexão.
_py() { docker compose exec -T "$API" python -c "$1" 2>&1; }

echo "============================================="
echo " SMOKE — Chamados (ServiceNow)   $(date '+%Y-%m-%d %H:%M')"
echo "============================================="
echo

# ── 1. O espelho responde ────────────────────────────────────────────────────
echo "[1] O espelho responde"
SAIDA=$(_py "
import sys; sys.path.insert(0,'/app')
from routers.chamados import get_db_conn
cur = get_db_conn().cursor()
cur.execute('SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo=1')
print('ATIVOS', cur.fetchone()[0])
")
ATIVOS=$(echo "$SAIDA" | sed -n 's/^ATIVOS //p')
_checar "a tabela etl_chamado responde" \
        "$([ -n "$ATIVOS" ] && echo ok)" "$SAIDA"
[ -n "$ATIVOS" ] && _info "$ATIVOS chamados ativos"

# ── 2. As 9 tabelas do módulo existem ────────────────────────────────────────
echo
echo "[2] As tabelas do módulo (migrations 094–100)"
SAIDA=$(_py "
import sys; sys.path.insert(0,'/app')
from routers.chamados import get_db_conn
T=['etl_chamado_nota','etl_chamado_anexo','etl_chamado_ciclo',
   'etl_indicador_meta','etl_indicador_snapshot','etl_indicador_snapshot_analista',
   'etl_indicador_snapshot_grupo','etl_servicenow_grupo','etl_sn_categoria']
cur = get_db_conn().cursor()
faltam=[t for t in T if not cur.execute(
    \"SELECT OBJECT_ID('dbo.'+?, 'U')\", [t]).fetchone()[0]]
print('FALTAM', ','.join(faltam) if faltam else '-')
")
FALTAM=$(echo "$SAIDA" | sed -n 's/^FALTAM //p')
_checar "as 9 tabelas existem" "$([ "$FALTAM" = "-" ] && echo ok)" \
        "faltando: $FALTAM"

# ── 3. ⚠️ A Fila e os Indicadores contam o MESMO ─────────────────────────────
# O defeito original do porte, e o mais caro: dois números certos que discordam.
echo
echo "[3] Fila × Indicadores — o mesmo recorte"
SAIDA=$(_py "
import sys; sys.path.insert(0,'/app')
from routers.chamados import get_db_conn, _so_trabalhos
cur = get_db_conn().cursor()
cur.execute('SELECT COUNT(*) FROM dbo.etl_chamado WHERE ativo=1 ' + _so_trabalhos())
trabalhos = cur.fetchone()[0]
from routers.chamados import listar_chamados, indicadores
u = {'matricula':'SMOKE','perfil':'admin','permissoes':['tela_chamados']}
fila = listar_chamados(0, u)
ind  = indicadores(None, u)
print('BANCO', trabalhos)
print('FILA', fila['total'])
print('COLUNAS', sum(fila['por_coluna'].values()))
print('IND', ind['total_ativos'])
")
B=$(echo "$SAIDA" | sed -n 's/^BANCO //p')
F=$(echo "$SAIDA" | sed -n 's/^FILA //p')
C=$(echo "$SAIDA" | sed -n 's/^COLUNAS //p')
I=$(echo "$SAIDA" | sed -n 's/^IND //p')
_info "banco=$B  fila.total=$F  soma(colunas)=$C  indicadores=$I"
_checar "fila.total == recorte do banco"   "$([ "$F" = "$B" ] && echo ok)" "$SAIDA"
_checar "soma das colunas == fila.total"   "$([ "$C" = "$F" ] && echo ok)" "$SAIDA"
_checar "indicadores == fila"              "$([ "$I" = "$B" ] && echo ok)" "$SAIDA"

# ── 4. A órfã: a divergência é fato ou hipótese? (§7.1 da spec) ──────────────
echo
echo "[4] Tarefas órfãs — a divergência silenciosa"
SAIDA=$(_py "
import sys; sys.path.insert(0,'/app')
from routers.chamados import get_db_conn
cur = get_db_conn().cursor()
cur.execute('''SELECT
 (SELECT COUNT(*) FROM dbo.etl_chamado
   WHERE ativo=1 AND tipo='task' AND pai_sys_id IS NULL),
 (SELECT COUNT(*) FROM dbo.etl_chamado t
   WHERE t.ativo=1 AND t.tipo='task' AND t.pai_sys_id IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM dbo.etl_chamado p
                      WHERE p.sys_id=t.pai_sys_id AND p.ativo=1))''')
a, b = cur.fetchone()
print('ORFAS', a, b)
")
read -r _ SEM_PAI PAI_FORA <<<"$(echo "$SAIDA" | grep '^ORFAS')"
_info "sem pai gravado: ${SEM_PAI:-?}   pai fora da fila: ${PAI_FORA:-?}"
_checar "nenhuma órfã (ou, havendo, os totais acima ainda batem)" \
        "$([ "${SEM_PAI:-0}" = "0" ] && [ "${PAI_FORA:-0}" = "0" ] && echo ok)" \
        "há órfãs — confira o passo [3]: se os números batem, o recorte está certo"

# ── 5. As anotações estão sendo COLETADAS ────────────────────────────────────
# ⚠️ Zero aqui é o defeito que passou despercebido a vida inteira do módulo: a
# tabela vazia e a DAG verde. A tela dizia "nenhuma anotação", que é a mesma
# frase de um chamado que de fato não tem.
echo
echo "[5] Anotações e anexos — a coleta"
SAIDA=$(_py "
import sys; sys.path.insert(0,'/app')
from routers.chamados import get_db_conn
cur = get_db_conn().cursor()
cur.execute('SELECT (SELECT COUNT(*) FROM dbo.etl_chamado_nota),'
            '       (SELECT COUNT(*) FROM dbo.etl_chamado_anexo)')
n, a = cur.fetchone()
print('NOTAS', n, a)
")
read -r _ NOTAS ANEXOS <<<"$(echo "$SAIDA" | grep '^NOTAS')"
_info "notas: ${NOTAS:-?}   anexos: ${ANEXOS:-?}"
_checar "há notas coletadas" "$([ "${NOTAS:-0}" -gt 0 ] 2>/dev/null && echo ok)" \
        "ZERO notas — a coleta não está rodando (NÃO é ausência de notas)"

# ── 6. O solicitante chega preenchido ────────────────────────────────────────
echo
echo "[6] Solicitante"
SAIDA=$(_py "
import sys; sys.path.insert(0,'/app')
from routers.chamados import get_db_conn
cur = get_db_conn().cursor()
cur.execute('''SELECT tipo,
   SUM(CASE WHEN NULLIF(LTRIM(RTRIM(demandante)),'') IS NOT NULL THEN 1 ELSE 0 END),
   COUNT(*)
 FROM dbo.etl_chamado WHERE ativo=1 AND tipo IN ('ritm','incident')
 GROUP BY tipo''')
faltando=[]
for tipo, com, tot in cur.fetchall():
    print('TIPO', tipo, com, tot)
    if com == 0 and tot > 0: faltando.append(tipo)
print('SEM', ','.join(faltando) if faltando else '-')
")
echo "$SAIDA" | sed -n 's/^TIPO /    /p'
SEM=$(echo "$SAIDA" | sed -n 's/^SEM //p')
_checar "RITM e incidente têm solicitante" "$([ "$SEM" = "-" ] && echo ok)" \
        "sem solicitante em: $SEM  (o incidente usa caller_id, não requested_for)"

# ── 7. O carimbo de frescor aponta para o motor VIVO ─────────────────────────
echo
echo "[7] Frescor da sincronização"
SAIDA=$(_py "
import sys; sys.path.insert(0,'/app')
from routers.chamados import get_db_conn, _ultimo_ciclo
c = _ultimo_ciclo(get_db_conn().cursor())
print('CICLO', (c or {}).get('fonte','-'), (c or {}).get('idade_minutos','-'),
      (c or {}).get('status','-'))
")
read -r _ FONTE IDADE STATUS <<<"$(echo "$SAIDA" | grep '^CICLO')"
_info "motor: ${FONTE:-?}   idade: ${IDADE:-?} min   status: ${STATUS:-?}"
_checar "há ciclo registrado" "$([ "${FONTE:-–}" != "-" ] && echo ok)" "$SAIDA"
_checar "o ciclo é recente (< 60 min)" \
        "$([ "${IDADE:-99999}" -lt 60 ] 2>/dev/null && echo ok)" \
        "o carimbo mostra ${IDADE} min — a DAG do motor pode ter parado"

# ── 8. As rotas de leitura respondem ─────────────────────────────────────────
echo
echo "[8] As rotas respondem"
SAIDA=$(_py "
import sys; sys.path.insert(0,'/app')
from routers import chamados as r
u = {'matricula':'SMOKE','perfil':'admin','permissoes':['tela_chamados']}
alvos = [('/chamados', lambda: r.listar_chamados(0,u)),
         ('/chamados/indicadores', lambda: r.indicadores(None,u)),
         ('/chamados/dashboard', lambda: r.dashboard('geral',u)),
         ('/chamados/historico', lambda: r.historico(30,u)),
         ('/chamados/categorias', lambda: r.listar_categorias(u))]
for nome, fn in alvos:
    try:
        saida = fn()
        ausente = saida.get('migration_ausente') or saida.get('blocos_indisponiveis')
        print('ROTA', nome, 'DEGRADADA' if ausente else 'OK')
    except Exception as e:
        print('ROTA', nome, 'ERRO:' + type(e).__name__)
")
echo "$SAIDA" | sed -n 's/^ROTA /    /p'
RUINS=$(echo "$SAIDA" | grep -c 'ERRO:\|DEGRADADA' || true)
_checar "as 5 rotas respondem sem degradar" \
        "$([ "$RUINS" = "0" ] && echo ok)" \
        "alguma rota degradou — veja acima qual"

# ── Fecho ────────────────────────────────────────────────────────────────────
echo
echo "============================================="
if [ "$FALHAS" -eq 0 ]; then
    printf ' \033[32mSMOKE OK\033[0m — %d verificações\n' "$TOTAL"
else
    printf ' \033[31m%d de %d FALHARAM\033[0m\n' "$FALHAS" "$TOTAL"
fi
echo "============================================="
echo
echo "O que este script NÃO cobre (precisa de olho humano):"
echo "  • baixar um anexo pelo proxy e abrir o arquivo;"
echo "  • um usuário SEM acao_admin recebendo 403 nas rotas /admin;"
echo "  • a tela renderizando — cards, filtros, tabelas e o modal."
echo "  Ver docs/manual-chamados.md."
exit $((FALHAS > 0))
