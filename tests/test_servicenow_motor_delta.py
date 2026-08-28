"""O motor incremental: ponto de corte, query do delta, notas e snapshot.

Portado do motor que roda em produção (F1 do porte). O ciclo completo
(`etl_servicenow_sync`) varre a fila a cada 15 min; o DELTA existe para trazer
só o que mudou, e o FULL para reconciliar o que o delta não vê.

O que estes testes prendem:

  1. **O corte do delta vem do último ciclo OK** — não de "agora menos X". Com
     um ciclo que falhou no meio, recomeçar do relógio deixaria um buraco na
     janela, e ninguém notaria: a fila continuaria parecendo em dia.
  2. **Sem ciclo anterior, o corte é conservador** (30 min atrás) em vez de
     varrer tudo — o primeiro delta de um ambiente novo não pode virar carga
     completa disfarçada.
  3. **O delta NUNCA roda sem filtro de grupo.** Sem grupo, a query traria a
     instância inteira da Caixa para dentro do espelho.
  4. **As notas do journal são só `work_notes`** e o MERGE não sobrescreve o
     que já está gravado: nota é imutável na origem, e reescrever apagaria o
     texto original se a API devolvesse truncado.
  5. **Placeholder `%s`** — a árvore `dags/` fala pymssql. Um `?` aqui dá
     "Incorrect syntax near '?'" com a task VERDE, porque o try/except engole.

Nada aqui toca rede, banco ou Airflow.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from unittest.mock import MagicMock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "dags"))

from utils.servicenow_sync import (  # noqa: E402
    buscar_notas, capturar_snapshot, query_delta, ultimo_delta_em,
    upsert_nota_sql,
)


def _hook(valor):
    """Hook dublê: devolve `valor` no fetchone do SELECT."""
    cur = MagicMock()
    cur.fetchone.return_value = valor
    conn = MagicMock()
    conn.cursor.return_value = cur
    hook = MagicMock()
    hook.get_conn.return_value = conn
    return hook, cur


# ═══════════ 1. o ponto de corte ════════════════════════════════════════════

def test_o_corte_vem_do_ultimo_ciclo_que_deu_certo():
    ts = _dt.datetime(2026, 8, 22, 14, 30)
    hook, _ = _hook((ts,))
    assert ultimo_delta_em(hook) == ts


def test_sem_ciclo_anterior_o_corte_e_conservador():
    """30 min atrás, não "o começo dos tempos".

    O primeiro delta de um ambiente novo não pode virar carga completa
    disfarçada — a instância cobra por volume e a janela de manutenção não
    esperaria por isso.
    """
    hook, _ = _hook((None,))
    antes = _dt.datetime.now() - _dt.timedelta(minutes=31)
    resultado = ultimo_delta_em(hook)
    depois = _dt.datetime.now() - _dt.timedelta(minutes=29)
    assert antes <= resultado <= depois


# ═══════════ 2. a query do delta ════════════════════════════════════════════

def test_a_query_do_delta_leva_o_corte_e_os_grupos():
    q = query_delta(["Eng. Dados", "Dados Cloud"],
                    _dt.datetime(2026, 8, 22, 9, 0))
    assert "sys_updated_on>=" in q
    assert "2026-08-22" in q
    assert "assignment_group.name=Eng. Dados" in q
    assert "assignment_group.name=Dados Cloud" in q


def test_delta_sem_grupo_e_recusado():
    """Sem filtro, a query traria a instância inteira da Caixa.

    É o tipo de erro que só aparece depois — quando o espelho já tem chamado
    de time nenhum e ninguém sabe de onde veio.
    """
    import pytest
    with pytest.raises(ValueError, match="grupo"):
        query_delta([], _dt.datetime(2026, 8, 22, 9, 0))


# ═══════════ 3. notas do journal ════════════════════════════════════════════

def _resposta(payload):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = {"result": payload}
    cliente = MagicMock()
    cliente.get.return_value = r
    return cliente


def test_a_nota_chega_normalizada():
    """⚠️ ESTE TESTE FOI REESCRITO — a versão anterior AFIRMAVA O DEFEITO.

    Ela alimentava o dublê com a resposta de `sys_journal_field` e conferia que
    o motor a normalizava. O motor fazia isso corretamente; só que essa tabela é
    **inacessível para a conta de integração** e responde 200 com lista VAZIA.
    O teste passava verde sobre um caminho que, em produção, nunca trouxe uma
    linha — e `dbo.etl_chamado_nota` ficou com zero registros o tempo todo.

    Agora o dublê devolve o que a instância REALMENTE devolve: o diário
    concatenado nos campos do próprio registro. Ver
    `tests/test_chamados_notas_diario.py` para o parser em detalhe.
    """
    cliente = _resposta([{
        "sys_id": "SYS001",
        "work_notes": ("22/08/2026 10:00:00 - João Silva (Anotações de trabalho)\n"
                       "texto da nota"),
        "comments": "",
    }])
    notas = buscar_notas(cliente, "https://x.service-now.com", "SYS001")
    assert len(notas) == 1
    n = notas[0]
    assert n["sys_id_chamado"] == "SYS001"
    assert n["tipo"] == "work_notes"
    assert n["autor"] == "João Silva"
    assert n["texto"] == "texto da nota"
    # O id é derivado do conteúdo: o diário não traz sys_id de nota nenhum.
    assert len(n["sys_id_nota"]) == 32


def test_a_nota_nao_vem_mais_da_tabela_inacessivel():
    """A regressão que este módulo precisa impedir: voltar ao journal devolve
    o silêncio de 200-com-lista-vazia que escondeu as notas desde sempre."""
    cliente = _resposta([])
    buscar_notas(cliente, "https://x.service-now.com", "SYS001")
    url = cliente.get.call_args[0][0]
    assert "sys_journal_field" not in url
    assert "/api/now/table/task" in url


def test_sem_nota_devolve_lista_vazia_e_nao_explode():
    assert buscar_notas(_resposta([]), "https://x", "SYS001") == []


def test_o_merge_de_nota_nao_reescreve_o_que_ja_existe():
    """Nota é imutável na origem.

    Um UPDATE aqui reescreveria o texto original toda vez que a API
    devolvesse a nota truncada — e o histórico do chamado encolheria sozinho,
    sem erro nenhum.
    """
    sql = upsert_nota_sql()
    assert "WHEN MATCHED THEN UPDATE" not in sql
    assert "WHEN NOT MATCHED" in sql


def test_o_merge_de_nota_usa_placeholder_da_arvore_dags():
    sql = upsert_nota_sql()
    assert "%s" in sql, "dags/ fala pymssql"
    assert "?" not in sql, (
        "'?' é o placeholder da árvore api/ (pyodbc) — aqui daria 'Incorrect "
        "syntax near' com a task VERDE, porque o try/except engole")


# ═══════════ 4. snapshot de indicadores ═════════════════════════════════════

def test_o_snapshot_grava_e_devolve_o_id():
    """O id volta para o caller: é ele que amarra as linhas por analista e por
    grupo ao snapshot certo. Perder esse id gravaria os detalhamentos órfãos,
    e o histórico do dashboard passaria a somar nada."""
    cur = MagicMock()
    # A ordem dos fetchone é a ordem das consultas de capturar_snapshot:
    # contagens gerais (7 valores), idade média, tempo médio, três COUNT e,
    # por fim, o id do INSERT.
    cur.fetchone.side_effect = [
        (10, 4, 3, 2, 1, 0, 5),   # total, novo, andamento, aguardando, resolvido, outros, sla
        (7.5,),                    # idade média
        (36.0,),                   # tempo médio de resolução
        (2,), (3,), (1,),          # encerrados 7d, abertos 7d, iniciativas
        (99,),                     # o id do snapshot recém-inserido
    ]
    cur.fetchall.return_value = []
    conn = MagicMock(); conn.cursor.return_value = cur
    hook = MagicMock(); hook.get_conn.return_value = conn

    assert capturar_snapshot(hook) == 99
    escrito = " ".join(str(c) for c in cur.execute.call_args_list)
    assert "etl_indicador_snapshot" in escrito


# ═══════════ 5. o snapshot agrupa pela CHAVE, não por perto dela ════════════

def test_o_snapshot_por_analista_agrupa_pela_chave_da_pk():
    """Defeito real, encontrado rodando o delta no dev em 2026-08-28.

    A PK de `etl_indicador_snapshot_analista` é (id_snapshot,
    atribuido_a_email). O código agrupava por `atribuido_a, atribuido_a_email`:
    dois chamados SEM responsável (e-mail '') com nomes diferentes viravam duas
    linhas com a MESMA chave, e o ciclo inteiro abortava com
    "Violation of PRIMARY KEY constraint 'PK_snapshot_analista'".

    Não era hipótese: com a coluna recém-criada — todos os e-mails vazios — o
    delta falhou na primeira execução. Em produção o defeito está latente,
    esperando o segundo chamado sem responsável na fila.
    """
    import inspect
    from utils import servicenow_sync

    fonte = inspect.getsource(servicenow_sync.capturar_snapshot)
    assert "GROUP BY ISNULL(atribuido_a_email,'')" in fonte, (
        "o agrupamento precisa ser pela CHAVE da PK; agrupar por nome + chave "
        "produz duplicata quando o e-mail se repete (ou é vazio)")
    assert "GROUP BY atribuido_a, atribuido_a_email" not in fonte


def test_o_snapshot_por_grupo_agrupa_pelo_valor_normalizado():
    """A mesma armadilha, mais discreta: o SELECT normalizava com ISNULL e o
    GROUP BY era pela coluna crua. NULL e '' são dois grupos antes do ISNULL e
    o mesmo valor depois — duas linhas com a chave (id_snapshot, '')."""
    import inspect
    from utils import servicenow_sync

    fonte = inspect.getsource(servicenow_sync.capturar_snapshot)
    assert "GROUP BY ISNULL(grupo,'')" in fonte


# ═══════════ 6. de onde vêm os grupos ═══════════════════════════════════════

def _hook_grupos(da_tabela, da_config=""):
    """Dublê: 1ª consulta devolve a tabela; 2ª (se houver), a config."""
    cur = MagicMock()
    cur.fetchall.return_value = [(g,) for g in da_tabela]
    cur.fetchone.return_value = (da_config,)
    conn = MagicMock(); conn.cursor.return_value = cur
    hook = MagicMock(); hook.get_conn.return_value = conn
    return hook


def test_a_tabela_de_grupos_tem_precedencia():
    """É o cadastro mais específico — tem ativo/inativo por grupo."""
    from utils.servicenow_sync import grupos_ativos
    assert grupos_ativos(_hook_grupos(["Eng. Dados"], "Outro Grupo")) \
        == ["Eng. Dados"]


def test_sem_grupo_na_tabela_cai_para_a_config():
    """Ambiente recém-migrado: a 098 cria a tabela VAZIA.

    Sem este fallback o delta pula em silêncio para sempre — foi o que
    aconteceu no dev em 2026-08-28 ("nenhum grupo ativo em
    etl_servicenow_grupo — skip"), com a config preenchida ao lado.
    """
    from utils.servicenow_sync import grupos_ativos
    assert grupos_ativos(_hook_grupos([], "TI_CVP_GERESD_ED")) \
        == ["TI_CVP_GERESD_ED"]


def test_o_fallback_usa_o_mesmo_separador_da_arvore_api():
    """'A; B ;;C' → ['A','B','C'], igual a `servicenow.parse_grupos()`.

    Separador diferente faria a MESMA string significar coisas diferentes nos
    dois lados — e a fila do delta não seria a da tela.
    """
    from utils.servicenow_sync import grupos_ativos
    assert grupos_ativos(_hook_grupos([], "A; B ;;C")) == ["A", "B", "C"]


def test_nome_em_branco_na_tabela_nao_vira_grupo():
    """Linha com nome vazio produziria `assignment_group.name=` — filtro que
    não filtra, e a query voltaria com a instância inteira."""
    from utils.servicenow_sync import grupos_ativos
    assert grupos_ativos(_hook_grupos(["  ", ""], "Config")) == ["Config"]
