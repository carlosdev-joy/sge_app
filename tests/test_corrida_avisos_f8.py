"""
F8 — os avisos que faltavam, e a Finalização Manual que alcança o ciclo.

O que a fase acrescenta aqui NÃO é uma recusa: é uma FRASE. O snapshot da
corrida congela membros, `conta_para_fim` e `modo_fechamento` na abertura
(§6.9/#16), então editar o desenho com ciclo em voo é legítimo e vale da
PRÓXIMA corrida em diante — o defeito era a tela não dizer isso. Sem a frase, o
operador adiciona um membro às 3h, não o vê no denominador e conclui que a tela
está quebrada; inativa a malha achando que parou a madrugada, e ela continua
andando; republica no meio do ciclo e metade dos membros roda com código novo.

Recusar seria pior que calar: transformaria "esta malha tem ciclo em voo" em
"esta malha não pode ser editada por horas" — justamente quando o operador está
acordado para preparar o ciclo seguinte.

E a Finalização Manual (Decisão 22): ela mexia em três tabelas e **nenhuma
delas era a 067**, que é a que o ciclo lê. Fechar a órfã era invisível para a
malha, e o membro continuava `vivo` no denominador até o teto — 24h por padrão.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user

ODATE = date(2026, 8, 4)


@pytest.fixture(scope="module")
def M():
    import routers.malhas as _m
    return _m


@pytest.fixture(scope="module")
def E():
    import routers.execucoes as _e
    return _e


@pytest.fixture(scope="module")
def F():
    import routers.finalizacao as _f
    return _f


def _corrida(status="ABERTA", data=ODATE, seq=1, malha="M1"):
    return {"id": 12, "malha_name": malha, "status": status, "sequencia": seq,
            "data_referencia": data, "aberta_em": None, "tentativas": 1}


class _McAviso:
    def __init__(self, corrida=None, tem_085=True, explode=False):
        self._c, self._085, self._explode = corrida, tem_085, explode

    def tabela_085_presente(self, cur):
        if self._explode:
            raise RuntimeError("banco fora do ar (teste)")
        return self._085

    def corrida_aberta(self, cur, malha):
        return self._c


# ══════════════════ o texto: um gesto, uma consequência ═════════════════════

@pytest.mark.parametrize("gesto,trecho", [
    ("inativar",      "continua até fechar sozinha"),
    ("membro_add",    "só passa a contar a partir do próximo ciclo"),
    ("membro_remove", "continua contando neste ciclo"),
    ("republicar",    "metade com cada uma"),
])
def test_cada_gesto_tem_a_SUA_consequencia(M, monkeypatch, gesto, trecho):
    """Uma frase genérica ("há um ciclo em andamento") não serve: o que o
    operador precisa saber é o que acontece com o gesto DELE. Adicionar membro
    e remover membro têm efeitos OPOSTOS sobre o denominador do ciclo em voo."""
    monkeypatch.setattr(M, "mc", _McAviso(_corrida()))
    aviso = M._aviso_ciclo_em_voo(object(), "M1", gesto)
    assert trecho in aviso
    # Decisão 74: a corrida se chama pela data; `#12` é chave de banco.
    assert "corrida de 2026-08-04" in aviso and "#" not in aviso


def test_a_segunda_corrida_do_dia_e_dita_pelo_ordinal(M, monkeypatch):
    monkeypatch.setattr(M, "mc", _McAviso(_corrida(seq=2)))
    assert "2ª corrida de 2026-08-04" in M._aviso_ciclo_em_voo(
        object(), "M1", "inativar")


@pytest.mark.parametrize("mc_falso", [
    _McAviso(None),                     # malha sem ciclo em voo
    _McAviso(_corrida(), tem_085=False),  # banco a meio deploy
    _McAviso(_corrida(), explode=True),   # leitura indisponível
])
def test_sem_ciclo_ou_sem_certeza_o_gesto_responde_como_antes(M, monkeypatch,
                                                              mc_falso):
    """`None` faz a chave nem entrar na resposta. Um aviso inventado por leitura
    que falhou seria pior que aviso nenhum: mandaria o operador procurar um
    ciclo que não existe."""
    monkeypatch.setattr(M, "mc", mc_falso)
    assert M._aviso_ciclo_em_voo(object(), "M1", "inativar") is None


def test_gesto_desconhecido_nao_inventa_frase(M, monkeypatch):
    monkeypatch.setattr(M, "mc", _McAviso(_corrida()))
    assert M._aviso_ciclo_em_voo(object(), "M1", "algo_novo") is None


# ═════════════════ a fiação: o aviso chega na resposta ══════════════════════

@pytest.fixture
def auth_editor(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "OP1", "perfil": "operador",
        "permissoes": [PERM_EDITAR, PERM_EXECUTAR, "tela_malhas"]}
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _cur_membro(ja_membro=False):
    cur = MagicMock()
    cur.description = []
    cur.rowcount = 1
    # _exigir_tabelas / _malha_oficial / _pipeline_oficial / "já é membro?"
    cur.fetchone.side_effect = [(1, 1), ("M1",), ("CARGA_A",),
                                (1,) if ja_membro else None]
    cur.fetchall.return_value = []
    return cur


def test_add_membro_devolve_o_aviso_do_ciclo_e_NAO_recusa(client, auth_editor,
                                                          M, monkeypatch):
    """O aceite da fase: "add_membro com corrida aberta → entra no cadastro,
    NÃO entra no snapshot, e a resposta diz isso"."""
    cur = _cur_membro()
    conn = MagicMock(); conn.cursor.return_value = cur
    monkeypatch.setattr(M, "_aviso_ciclo_em_voo",
                        lambda c, m, g: f"aviso de {g}")
    with patch("routers.malhas.get_db_conn", return_value=conn):
        r = client.post("/malhas/M1/pipelines",
                        json={"pipeline_name": "CARGA_A"})
    assert r.status_code == 200                      # avisa, nunca recusa
    assert r.json()["aviso_ciclo"] == "aviso de membro_add"
    # e o membro FOI gravado — o aviso não é uma recusa disfarçada
    assert any("INSERT INTO dbo.etl_malha_pipeline" in c.args[0]
               for c in cur.execute.call_args_list)
    conn.commit.assert_called_once()


def test_sem_ciclo_em_voo_a_resposta_e_a_de_sempre_byte_a_byte(client,
                                                              auth_editor, M,
                                                              monkeypatch):
    """Front antigo ignora a chave — e malha sem corrida aberta nem recebe a
    chave. É assim que a fase é aditiva de verdade."""
    conn = MagicMock(); conn.cursor.return_value = _cur_membro()
    monkeypatch.setattr(M, "_aviso_ciclo_em_voo", lambda c, m, g: None)
    with patch("routers.malhas.get_db_conn", return_value=conn):
        r = client.post("/malhas/M1/pipelines",
                        json={"pipeline_name": "CARGA_A"})
    assert r.status_code == 200 and "aviso_ciclo" not in r.json()


# ═══════ o disparo AVULSO: nunca abre, nunca reabre — mas é contado ═════════

class _McPipeline:
    def __init__(self, corridas, ambiguo=False, tem_085=True):
        self._c, self._amb, self._085 = corridas, ambiguo, tem_085

    def tabela_085_presente(self, cur):
        return self._085

    def corrida_aberta_do_pipeline(self, cur, pipeline):
        return {"corridas": self._c, "ambiguo": self._amb,
                "odate": self._c[0]["data_referencia"] if self._c else None}


@pytest.fixture
def auth_leitor(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "OP1", "perfil": "consulta", "permissoes": []}
    yield
    app.dependency_overrides.pop(get_current_user, None)


def test_disparo_avulso_avisa_que_sera_contado_na_corrida(client, auth_leitor,
                                                          E, monkeypatch):
    """§6.9/#5 — o disparo avulso NÃO abre e NÃO reabre; ele ADERE. Sem a frase,
    o operador dispara "só este pipeline" às 3h e o número da malha muda sozinho
    na tela ao lado."""
    monkeypatch.setattr(E, "mc", _McPipeline([_corrida()]))
    with patch("routers.execucoes.get_db_conn", return_value=MagicMock()):
        r = client.get("/pipelines/CARGA_A/corrida")
    assert r.status_code == 200
    body = r.json()
    assert body["efeito"] == "conta"
    assert "CONTADA nesse ciclo" in body["mensagem"]
    assert body["corrida"]["malha"] == "M1"


def test_odate_diferente_do_ciclo_avisa_que_a_execucao_fica_de_FORA(
        client, auth_leitor, E, monkeypatch):
    """Decisão 23 exige o ODATE nos dois ramos: a execução pedida para outra
    data não é contada no ciclo — e isso precisa ser dito, senão o operador
    acredita ter reprocessado a malha."""
    monkeypatch.setattr(E, "mc", _McPipeline([_corrida()]))
    with patch("routers.execucoes.get_db_conn", return_value=MagicMock()):
        r = client.get("/pipelines/CARGA_A/corrida?data_referencia=2026-08-03")
    assert r.json()["efeito"] == "fora_do_ciclo"
    assert "FORA desse ciclo" in r.json()["mensagem"]


def test_dois_ciclos_com_datas_diferentes_avisam_RECUSA(client, auth_leitor,
                                                        E, monkeypatch):
    """Decisão 34 — dois ODATEs abertos para o mesmo pipeline nunca viram
    escolha: viram recusa. Dizer isso ANTES evita o disparo que já nasce
    `PULADO` com data divergente."""
    outra = dict(_corrida(), malha="M2", data_referencia=date(2026, 8, 3))
    monkeypatch.setattr(E, "mc", _McPipeline([_corrida(), outra],
                                             ambiguo=True))
    with patch("routers.execucoes.get_db_conn", return_value=MagicMock()):
        r = client.get("/pipelines/CARGA_A/corrida")
    assert r.json()["efeito"] == "ambiguo"
    assert "recusado" in r.json()["mensagem"]


@pytest.mark.parametrize("mc_falso", [
    _McPipeline([]),                       # pipeline fora de malha
    _McPipeline([_corrida()], tem_085=False),
])
def test_pipeline_sem_ciclo_devolve_corrida_nula(client, auth_leitor, E,
                                                 monkeypatch, mc_falso):
    monkeypatch.setattr(E, "mc", mc_falso)
    with patch("routers.execucoes.get_db_conn", return_value=MagicMock()):
        r = client.get("/pipelines/CARGA_A/corrida")
    assert r.status_code == 200 and r.json()["corrida"] is None


# ════════ Finalização Manual: o gesto passa a alcançar a 067 (D22) ══════════

class _IdentFalso:
    """A ponte ts_nodash ↔ run_id. `resolve=False` reproduz o caso MEDIDO no
    dev: run_id gerado pelo Orquestra (`guardia__…`, `manual_orq_…`) não é
    traduzível, e a resolução devolve só os `candidatos` da janela."""

    def __init__(self, resolve=True, tem_067=True, candidatos=()):
        self._resolve, self._067 = resolve, tem_067
        self._cands = list(candidatos)

    def tem_tabela_067(self, cur):
        return self._067

    def resolve_por_ts_nodash(self, cur, pipeline, ts):
        if not self._resolve:
            return {"run_id": None, "data_referencia": None,
                    "candidatos": self._cands}
        return {"run_id": f"scheduled__{ts}", "data_referencia": ODATE,
                "candidatos": self._cands}


def _cand(run_id, status="EXECUTANDO", substituida_em=None):
    return {"run_id": run_id, "status": status,
            "substituida_em": substituida_em}


class _McFinal:
    def __init__(self, corridas=(), estado=None, tem_085=True):
        self._c, self._e, self._085 = list(corridas), estado, tem_085

    def tabela_085_presente(self, cur):
        return self._085

    def corrida_aberta_do_pipeline(self, cur, pipeline):
        return {"corridas": self._c, "ambiguo": False, "odate": ODATE}

    def estado(self, cur, corrida, dispensa_sem_linha=None):
        return self._e


def _cur_067(datas=(ODATE,)):
    """O UPDATE devolve as datas fechadas por `OUTPUT inserted.data_referencia`
    — é delas que sai o "que ciclo reavaliar"."""
    cur = MagicMock()
    cur.fetchall.return_value = [(d,) for d in datas]
    return cur


def test_finalizacao_fecha_a_linha_que_o_CICLO_le_e_reavalia(F, monkeypatch):
    """Decisão 22 — antes desta fase o gesto fechava três tabelas e nenhuma
    delas era a 067: a malha continuava esperando o membro até o teto."""
    monkeypatch.setattr(F, "ident_svc", _IdentFalso())
    monkeypatch.setattr(F, "mc", _McFinal(
        corridas=[_corrida()],
        estado={"vivos": [], "ok": ["CARGA_B"],
                "pendentes": [{"pipeline": "CARGA_C", "classe": "falhou"}]}))
    cur = _cur_067()
    saida = F._fechar_linha_do_ciclo(cur, "CARGA_A", ["20260804T0300"],
                                     "SUCCESS", "OP1", "worker caiu")

    assert saida["linhas_ciclo_fechadas"] == 1
    sql, params = cur.execute.call_args_list[0].args
    assert "UPDATE dbo.etl_pipeline_execucao" in sql
    # Nunca reescreve terminal, nunca ressuscita: só o que está EXECUTANDO.
    assert "AND status = 'EXECUTANDO'" in sql
    assert params[0] == "SUCESSO"
    assert "finalizacao manual por OP1: worker caiu" in params[1]
    # A reavaliação sai no MESMO gesto — sem esperar os 5 min do ciclo.
    assert saida["corridas"] == [{"malha": "M1",
                                  "data_referencia": "2026-08-04",
                                  "em_execucao": 0, "pendentes": ["CARGA_C"],
                                  "concluidos": 1}]


@pytest.mark.parametrize("status_final,esperado", [
    ("SUCCESS", "SUCESSO"), ("WARNING", "SUCESSO"), ("FAILED", "FALHA")])
def test_o_status_declarado_vira_o_do_ciclo(F, monkeypatch, status_final,
                                            esperado):
    """WARNING conta como conclusão porque é assim que `liberado()` e
    `pipelines_todos_sucesso` já o tratam. Inventar um terceiro estado aqui
    deixaria a corrida esperando para sempre por um pipeline que o operador
    declarou terminado."""
    monkeypatch.setattr(F, "ident_svc", _IdentFalso())
    monkeypatch.setattr(F, "mc", _McFinal())
    cur = _cur_067()
    F._fechar_linha_do_ciclo(cur, "CARGA_A", ["ts"], status_final, "OP1", None)
    assert cur.execute.call_args_list[0].args[1][0] == esperado


def test_run_id_do_ORQUESTRA_cai_no_candidato_unico_em_execucao(F, monkeypatch):
    """MEDIDO no dev: `guardia__…` e `manual_orq_…` não são traduzíveis para
    ts_nodash (o timestamp deles é relógio local). Sem este segundo caminho, a
    Decisão 22 valeria só para o membro AGENDADO — justamente o que menos
    precisa dela, porque quem trava a malha é o push."""
    monkeypatch.setattr(F, "ident_svc", _IdentFalso(
        resolve=False,
        candidatos=[_cand("guardia__2026-08-04__CARGA_A__x"),
                    _cand("run_velho", status="SUCESSO")]))
    monkeypatch.setattr(F, "mc", _McFinal())
    cur = _cur_067()
    saida = F._fechar_linha_do_ciclo(cur, "CARGA_A", ["ts"], "SUCCESS", "OP1",
                                     None)
    assert saida["linhas_ciclo_fechadas"] == 1
    assert cur.execute.call_args_list[0].args[1][3] == \
        "guardia__2026-08-04__CARGA_A__x"


def test_duas_execucoes_na_janela_DECLARAM_a_ambiguidade_e_nao_escolhem(
        F, monkeypatch):
    """Fechar a errada carimbaria SUCESSO num pipeline que ainda está rodando —
    e o dependente partiria com o dado da véspera. Ambiguidade aqui se declara,
    nunca se resolve por escolha (a mesma régua da Decisão 34)."""
    monkeypatch.setattr(F, "ident_svc", _IdentFalso(
        resolve=False, candidatos=[_cand("run_1"), _cand("run_2")]))
    monkeypatch.setattr(F, "mc", _McFinal())
    cur = _cur_067()
    saida = F._fechar_linha_do_ciclo(cur, "CARGA_A", ["ts"], "SUCCESS", "OP1",
                                     None)
    assert saida["linhas_ciclo_fechadas"] == 0
    assert any("2 execuções em andamento" in a for a in saida["avisos"])
    cur.execute.assert_not_called()


def test_candidata_APOSENTADA_nao_conta_como_execucao_viva(F, monkeypatch):
    """Linha que um rerun já aposentou não é candidata: encerrá-la não
    destravaria nada e ainda carimbaria um SUCESSO sobre trabalho substituído."""
    monkeypatch.setattr(F, "ident_svc", _IdentFalso(
        resolve=False,
        candidatos=[_cand("run_1", substituida_em="2026-08-04"),
                    _cand("run_2")]))
    monkeypatch.setattr(F, "mc", _McFinal())
    cur = _cur_067()
    F._fechar_linha_do_ciclo(cur, "CARGA_A", ["ts"], "SUCCESS", "OP1", None)
    assert cur.execute.call_args_list[0].args[1][3] == "run_2"


def test_sem_linha_na_067_nao_e_erro_e_nao_ha_ciclo_a_reavaliar(F, monkeypatch):
    """Pipeline pré-retomada, ou disparo fora do Orquestra: a 067 simplesmente
    não tem linha em execução. O gesto principal (fechar os logs) já
    aconteceu."""
    monkeypatch.setattr(F, "ident_svc", _IdentFalso(resolve=False))
    monkeypatch.setattr(F, "mc", _McFinal())
    cur = _cur_067()
    saida = F._fechar_linha_do_ciclo(cur, "CARGA_A", ["ts"], "SUCCESS", "OP1",
                                     None)
    assert saida == {"linhas_ciclo_fechadas": 0, "corridas": [], "avisos": []}
    cur.execute.assert_not_called()


def test_sem_a_067_o_passo_inteiro_e_pulado(F, monkeypatch):
    monkeypatch.setattr(F, "ident_svc", _IdentFalso(tem_067=False))
    monkeypatch.setattr(F, "mc", _McFinal())
    cur = _cur_067()
    assert F._fechar_linha_do_ciclo(cur, "P", ["ts"], "SUCCESS", "OP1",
                                    None)["linhas_ciclo_fechadas"] == 0
    cur.execute.assert_not_called()


def test_falha_ao_alcancar_o_ciclo_vira_aviso_e_nunca_derruba_a_finalizacao(
        F, monkeypatch):
    """A finalização é a ferramenta de emergência do plantão: ela não pode
    falhar porque a malha não pôde ser consultada."""
    class _Explode(_IdentFalso):
        def resolve_por_ts_nodash(self, *a, **kw):
            raise RuntimeError("deadlock (teste)")

    monkeypatch.setattr(F, "ident_svc", _Explode())
    monkeypatch.setattr(F, "mc", _McFinal())
    saida = F._fechar_linha_do_ciclo(_cur_067(), "P", ["ts"], "SUCCESS", "OP1",
                                     None)
    assert saida["linhas_ciclo_fechadas"] == 0
    assert any("continuar esperando" in a for a in saida["avisos"])
