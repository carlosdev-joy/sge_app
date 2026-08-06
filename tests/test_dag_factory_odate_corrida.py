"""
O ODATE que a CORRIDA da malha carimba, no FONTE GERADO
(F5 de docs/spec-malha-execucao.md — §7 "Quem carimba o ODATE", Decisões 33 a
37, e a sonda do §12.2).

⚠️ Esta é a fase que mexe no fonte gerado: nenhuma DAG publicada muda de
comportamento até ser REGERADA (`force_all`), e as duas gerações convivem no ar
enquanto a regeração não acaba. Daí a divisão destes testes:

  1. **fiação** — o fonte gerado pergunta ao módulo da corrida com os argumentos
     certos e obedece à resposta (a REGRA da precedência é unitária em
     tests/test_malha_corrida.py, e não se duplica aqui);
  2. **memoização** (Decisão 36) — o run tem UM ODATE, e ele não muda nem quando
     a corrida fecha no meio do pipeline. É o teste que prova que a cura não
     fabrica a doença;
  3. **recusa nominal** (Decisões 34 e 35) — dois ODATEs abertos para o mesmo
     pipeline nunca viram escolha silenciosa, nem na agenda nem no push;
  4. **degradação byte a byte** — sem a 085 (ou com o interruptor em 0), o fonte
     NOVO emite exatamente o mesmo SQL e devolve exatamente a mesma data que o
     fonte de `main`. A comparação é entre as duas árvores, executadas lado a
     lado — não é leitura de código.

Harness reusado dos vizinhos (mesmo princípio do teste de paridade, que reusa o
dublê do teste do canônico): `_exec_ns`/`_HookF2`/`_ctx` de
tests/test_dag_factory_execucao.py e o dublê de `utils.dependencias` de
tests/test_dag_factory_dependencias_f3.py. Um harness próprio provaria a
concordância entre dois harnesses.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_dag_factory_execucao import (
    _ambiente_utils, _ctx, _exec_ns, _HookF2, _instala_hook, _job, _src)
from tests.test_dag_factory_dependencias_f3 import (
    _ambiente_utils as _amb_push, _cliente_trigger, _dep_fake,
    _src as _src_f3)

_ROOT = Path(__file__).parent.parent

# O mesmo commit base da âncora de tests/test_dag_factory_espera.py: o fonte
# gerado por ELE é o padrão-ouro da degradação ("byte a byte como hoje").
_COMMIT_BASE = "cbce3e2"

ODATE = date(2026, 8, 1)
ODATE_ONTEM = date(2026, 7, 31)


@pytest.fixture(scope="module")
def factory():
    spec = importlib.util.spec_from_file_location(
        "etl_dag_factory_odate_test", _ROOT / "dags/etl_dag_factory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def factory_main():
    """A factory do commit base, carregada como módulo independente."""
    try:
        bruto = subprocess.run(
            ["git", "-C", str(_ROOT), "show", f"{_COMMIT_BASE}:dags/etl_dag_factory.py"],
            capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:  # pragma: no cover
        pytest.skip(f"git indisponivel para o fonte de referencia: {e}")
    if bruto.returncode != 0:  # pragma: no cover
        pytest.skip(f"commit base {_COMMIT_BASE} indisponivel")
    with tempfile.NamedTemporaryFile("wb", suffix="_factory_main.py",
                                     delete=False) as fh:
        fh.write(bruto.stdout)
        caminho = fh.name
    try:
        spec = importlib.util.spec_from_file_location(
            "etl_dag_factory_main_odate", caminho)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        Path(caminho).unlink(missing_ok=True)


# ───────────────────────── o dublê do módulo da corrida ──────────────────────

class _Corrida:
    """Dublê de `utils.malha_corrida` para o fonte gerado.

    Registra CADA chamada — é assim que a memoização se prova: não basta a data
    sair igual quatro vezes, as três últimas não podem ter ido ao banco.

    `respostas` é uma FILA: a primeira chamada recebe a primeira resposta e as
    seguintes recebem a última. É o que reproduz "a corrida fechou no meio do
    pipeline" sem inventar relógio.
    """

    VAZIO = {"data": None, "corrida_id": None, "ambiguo": False,
             "degrau": None, "detalhe": None}

    def __init__(self, *respostas, ativa=True, por_pipeline=None):
        self.respostas = list(respostas) or [dict(self.VAZIO)]
        self.ativa = ativa
        self.por_pipeline = dict(por_pipeline or {})
        self.chamadas: list[dict] = []

    def corrida_ativa(self, conn):
        return self.ativa

    def odate(self, conn, pipeline, run_id=None, conf_id=None, herdada=None):
        self.chamadas.append({"pipeline": pipeline, "run_id": run_id,
                              "conf_id": conf_id, "herdada": herdada})
        if pipeline in self.por_pipeline:
            return {**self.VAZIO, **self.por_pipeline[pipeline]}
        i = min(len(self.chamadas) - 1, len(self.respostas) - 1)
        return {**self.VAZIO, **self.respostas[i]}

    def corrida_aberta_do_pipeline(self, conn, pipeline):
        return {"corridas": [], "odate": None, "ambiguo": False}


def _resp(data=None, corrida_id=None, degrau=None, ambiguo=False, detalhe=None):
    return {"data": data, "corrida_id": corrida_id, "degrau": degrau,
            "ambiguo": ambiguo, "detalhe": detalhe}


def _ns_com(factory, corrida, **over):
    """Namespace da DAG gerada com o dublê da corrida no lugar do módulo."""
    src = _src(factory, **over)
    ns = {}
    with _ambiente_utils(malha_corrida=corrida):
        exec(compile(src, "<dag>", "exec"), ns)
    return ns


# ═══════════════ 1. a marca sintática da sonda do §12.2 ═════════════════════

def test_a_marca_da_sonda_e_emitida_por_toda_dag(factory):
    """`_corrida.odate(` é o que a API procura no fonte PUBLICADO para saber,
    pipeline a pipeline, quem já foi regerado (§12.2). Ela não pode depender de
    o pipeline ter dependência, malha ou Teams: a sonda é por pipeline, e um
    membro sem dependência é justamente o caso do `Carga_Vida` invertido."""
    from api.services import espera as esp
    for over in ({}, {"envia_msg_inicio": 0, "envia_msg_fim": 0, "envia_msg_erro": 0},
                 {"schedule_type": "on_demand"}):
        src = _src(factory, **over)
        assert esp.MARCA_CORRIDA in src, over
    assert esp.MARCA_CORRIDA == "_corrida.odate("


def test_a_marca_so_aparece_em_CHAMADA_nunca_em_texto(factory):
    """§12.2 exige marca SINTÁTICA: ela não pode casar em comentário nem em
    código morto.

    O defeito real (achado 3 da revisão da F5): o aviso que explica a sonda
    estava no docstring da função GERADA, então o arquivo publicado tinha três
    ocorrências — duas chamadas e um texto. Uma DAG que perdesse a chamada mas
    guardasse o docstring passaria na sonda dizendo `ok`, e o operador
    confiaria numa regeração que não aconteceu.

    O teste é sobre o ARQUIVO PUBLICADO: cada linha que contém a marca tem de
    ser uma chamada de verdade — não um `#`, não uma linha dentro de `\"\"\"`."""
    import ast

    from api.services import espera as esp
    src = _src(factory)

    # Quantas vezes a sonda VERIA a marca (ela faz busca textual, é o ponto).
    textuais = src.count(esp.MARCA_CORRIDA)
    assert textuais, "a marca sumiu do fonte gerado"

    # Quantas CHAMADAS existem de verdade, segundo o parser do Python — a única
    # autoridade sobre o que é código e o que é texto. Comparar linha a linha
    # não serve: a linha de um docstring multilinha não contém as aspas, então
    # um aviso lá dentro passaria por chamada (foi assim que o defeito 3 nasceu,
    # e a primeira versão deste teste não o pegou).
    chamadas = sum(
        1 for no in ast.walk(ast.parse(src))
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute) and no.func.attr == "odate"
        and isinstance(no.func.value, ast.Name) and no.func.value.id == "_corrida")

    assert textuais == chamadas, (
        f"a sonda enxerga {textuais} ocorrência(s) de '{esp.MARCA_CORRIDA}' mas "
        f"só {chamadas} é/são chamada(s) de verdade: {textuais - chamadas} "
        f"está/estão em docstring ou comentário do arquivo PUBLICADO. Uma DAG "
        f"que perdesse a chamada e guardasse o texto passaria na sonda dizendo "
        f"'ok', e o operador confiaria numa regeração que não aconteceu — mova "
        f"o texto para um comentário DA FACTORY, que não é emitido.")


def test_o_import_do_modulo_da_corrida_e_guardado(factory):
    """Deploy parcial não pode derrubar DAG: sem `utils/malha_corrida.py` no
    servidor, `_corrida` vira None e a data volta a ser a de sempre."""
    src = _src(factory)
    assert "    from utils import malha_corrida as _corrida" in src
    assert "except Exception as _corrida_err:" in src
    assert "    _corrida = None" in src


# ═════════════════════ 2. a fiação dos degraus do §7 ════════════════════════

def test_a_pergunta_leva_run_id_conf_e_heranca(factory):
    """Os três insumos dos degraus 0, 1 e 2 saem do fonte gerado numa chamada
    só — se um deles ficar para trás, o degrau correspondente não existe."""
    corrida = _Corrida(_resp(data=ODATE, corrida_id=12, degrau="conf_corrida"))
    ns = _ns_com(factory, corrida)
    _instala_hook(ns, _HookF2())
    ctx = _ctx(conf={"data_referencia": "2026-07-31", "malha_execucao_id": 12})
    with _ambiente_utils(malha_corrida=corrida):
        assert ns["_data_referencia"](ctx) == ODATE
    assert corrida.chamadas == [{"pipeline": "PIPE_EXEC",
                                 "run_id": ctx["run_id"], "conf_id": 12,
                                 "herdada": ODATE_ONTEM}]


def test_conf_com_data_invalida_nao_aborta_e_vira_heranca_vazia(factory, capsys):
    corrida = _Corrida()
    ns = _ns_com(factory, corrida)
    _instala_hook(ns, _HookF2())
    with _ambiente_utils(malha_corrida=corrida):
        ns["_data_referencia"](_ctx(conf={"data_referencia": "31/07/2026"}))
    assert corrida.chamadas[0]["herdada"] is None
    assert "data_referencia herdada invalida" in capsys.readouterr().out


def test_a_resposta_do_modulo_e_obedecida(factory):
    """Degrau 3 — o membro com cron próprio ADERE ao ciclo em voo (Decisão 33).
    O cálculo pela virada daria 2026-08-01; a corrida está em 2026-07-31."""
    corrida = _Corrida(_resp(data=ODATE_ONTEM, corrida_id=9, degrau="corrida"))
    ns = _ns_com(factory, corrida)
    _instala_hook(ns, _HookF2())
    with _ambiente_utils(malha_corrida=corrida):
        assert ns["_data_referencia"](_ctx()) == ODATE_ONTEM


def test_sem_resposta_do_modulo_cai_na_heranca_e_depois_no_calculo(factory):
    corrida = _Corrida()          # nada a dizer: nem corrida, nem carimbo
    ns = _ns_com(factory, corrida)
    _instala_hook(ns, _HookF2())
    with _ambiente_utils(malha_corrida=corrida):
        herdado = ns["_data_referencia"](
            _ctx(conf={"data_referencia": "2026-07-31"}))
        ns["_ODATE_DO_RUN"].clear()
        calculado = ns["_data_referencia"](_ctx())
    assert herdado == ODATE_ONTEM
    assert calculado == ODATE        # o degrau 4, pelo momento lógico do run


# ═══════════ 3. a memoização por run_id — Decisão 36, ENTREGÁVEL ════════════

def test_quatro_chamadas_no_mesmo_run_uma_ida_ao_banco(factory):
    """A função é chamada 4× por run (check_agenda, registro, push, registro de
    sucesso/falha). As 3 últimas não podem ir ao banco — e o degrau 3 custa 1-2
    consultas que `_disparar_dependentes` multiplicaria por dependente."""
    corrida = _Corrida(_resp(data=ODATE_ONTEM, corrida_id=9, degrau="corrida"))
    ns = _ns_com(factory, corrida)
    _instala_hook(ns, _HookF2())
    ctx = _ctx()
    with _ambiente_utils(malha_corrida=corrida):
        datas = [ns["_data_referencia"](ctx) for _ in range(4)]
    assert datas == [ODATE_ONTEM] * 4
    assert len(corrida.chamadas) == 1


def test_a_corrida_que_fecha_no_meio_NAO_muda_o_odate_do_run(factory):
    """⛔ O teste que prova que a cura não fabrica a doença (Decisão 36).

    Cenário literal da spec: 01:10 o check_agenda resolve pelo degrau 3 e grava
    a linha `(P, D, run_id)`; 04:50 a corrida fecha; 04:52 o registro de sucesso
    pergunta de novo. Sem memoização, a 2ª resposta seria outra data, o UPDATE
    erraria a chave e o INSERT criaria uma SEGUNDA linha do mesmo run em outro
    ODATE — o run passaria a existir em dois dias."""
    corrida = _Corrida(_resp(data=ODATE_ONTEM, corrida_id=9, degrau="corrida"),
                       _resp())        # a corrida fechou: o módulo não responde
    ns = _ns_com(factory, corrida)
    _instala_hook(ns, _HookF2())
    ctx = _ctx()
    with _ambiente_utils(malha_corrida=corrida):
        primeira = ns["_data_referencia"](ctx)
        ultima = ns["_data_referencia"](ctx)
    assert primeira == ultima == ODATE_ONTEM


def test_runs_diferentes_nao_compartilham_a_memoria(factory):
    """A memória é do RUN, não do processo: um worker atende vários runs, e um
    cache por processo carimbaria o ODATE do run anterior no seguinte."""
    corrida = _Corrida(_resp(data=ODATE_ONTEM, degrau="corrida"),
                       _resp(data=ODATE, degrau="corrida"))
    ns = _ns_com(factory, corrida)
    _instala_hook(ns, _HookF2())
    with _ambiente_utils(malha_corrida=corrida):
        a = ns["_data_referencia"](_ctx(run_id="scheduled__A"))
        b = ns["_data_referencia"](_ctx(run_id="scheduled__B"))
    assert (a, b) == (ODATE_ONTEM, ODATE)


# ══════════ 4. o vínculo write-once na linha de execução (Decisão 9) ════════

def _sqls(hook):
    return [s for s, _ in hook.cursor.execs]


def test_o_update_carimba_a_corrida_com_COALESCE(factory):
    """WRITE-ONCE dentro do UPDATE multi-coluna do caminho quente: o UPDATE roda
    a cada estado do run e o Clear do rerun REUSA o run_id — sem o COALESCE, a
    linha da corrida #12 reexecutada amanhã passaria a pertencer à #13."""
    corrida = _Corrida(_resp(data=ODATE, corrida_id=12, degrau="corrida"))
    ns = _ns_com(factory, corrida)
    hook = _instala_hook(ns, _HookF2())
    with _ambiente_utils(malha_corrida=corrida):
        ns["_registrar_execucao"]("EXECUTANDO", _ctx())
    upd = [s for s in _sqls(hook) if s.startswith("UPDATE")][0]
    assert "malha_execucao_id=COALESCE(malha_execucao_id, %s)" in upd
    params = [p for s, p in hook.cursor.execs if s.startswith("UPDATE")][0]
    # a corrida entra ANTES da chave (status, motivo, origem, corrida, chave…)
    assert params[3] == 12 and params[4] == "PIPE_EXEC"


def test_o_insert_leva_a_coluna_so_quando_ha_corrida(factory):
    corrida = _Corrida(_resp(data=ODATE, corrida_id=12, degrau="corrida"))
    ns = _ns_com(factory, corrida)
    hook = _instala_hook(ns, _HookF2(rowcount_update=0))   # força o INSERT
    with _ambiente_utils(malha_corrida=corrida):
        ns["_registrar_execucao"]("SUCESSO", _ctx())
    ins = [s for s, _ in hook.cursor.execs if s.startswith("INSERT")][0]
    assert "disparado_por, motivo, malha_execucao_id)" in ins
    par = [p for s, p in hook.cursor.execs if s.startswith("INSERT")][0]
    assert par[-1] == 12


def test_sem_a_coluna_no_banco_a_linha_e_gravada_MESMO_ASSIM(factory, capsys):
    """Deploy parcial (célula 2 da matriz do §11.1): `dags/` novo, banco sem a
    085. Perder o registro da execução porque o vínculo não cabe seria trocar um
    dado extra por todo o resto."""
    corrida = _Corrida(_resp(data=ODATE, corrida_id=12, degrau="corrida"))
    ns = _ns_com(factory, corrida)
    hook = _instala_hook(ns, _HookF2())

    class _CursorSemColuna(type(hook.cursor)):
        pass

    original = hook.cursor.execute
    estado = {"explodiu": False}

    def execute(sql, params=None):
        if "malha_execucao_id" in str(sql):
            estado["explodiu"] = True
            raise RuntimeError("Invalid column name 'malha_execucao_id'. (207)")
        return original(sql, params)

    hook.cursor.execute = execute
    with _ambiente_utils(malha_corrida=corrida):
        ns["_registrar_execucao"]("SUCESSO", _ctx())
    saida = capsys.readouterr().out
    assert estado["explodiu"]
    assert "coluna malha_execucao_id ausente" in saida
    assert "[EXEC] SUCESSO registrado" in saida
    assert not any("malha_execucao_id" in s for s in _sqls(hook))


def test_qualquer_outro_erro_NAO_vira_retry_silencioso(factory, capsys):
    """A cascata é do `_MARCA_085` e só dela: engolir um deadlock ou um timeout
    devolvendo "registrado sem o vínculo" esconderia o defeito de verdade."""
    corrida = _Corrida(_resp(data=ODATE, corrida_id=12, degrau="corrida"))
    ns = _ns_com(factory, corrida)
    hook = _instala_hook(ns, _HookF2())

    def execute(sql, params=None):
        raise RuntimeError("deadlock victim (1205)")

    hook.cursor.execute = execute
    with _ambiente_utils(malha_corrida=corrida):
        ns["_registrar_execucao"]("SUCESSO", _ctx())
    saida = capsys.readouterr().out
    assert "coluna malha_execucao_id ausente" not in saida
    assert "Aviso: execucao nao registrada" in saida


# ══════ 5. a recusa por ODATE ambíguo — Decisões 34 e 35, nas duas portas ═══

_AMBIGUO = _resp(ambiguo=True, degrau="corrida",
                 detalhe=("MALHA_ODATE_AMBIGUO: PIPE_EXEC e membro de corridas "
                          "abertas com ODATEs diferentes — #1 (2026-08-01), "
                          "#2 (2026-07-31)"))


def test_agenda_recusa_com_motivo_nominal_e_nao_escolhe(factory):
    corrida = _Corrida(_AMBIGUO)
    ns = _ns_com(factory, corrida)
    _instala_hook(ns, _HookF2())
    with _ambiente_utils(malha_corrida=corrida):
        ok, motivo = ns["_check_agenda_regras"](_ctx())
    assert ok is False
    assert "MALHA_ODATE_AMBIGUO" in motivo
    assert "#1 (2026-08-01)" in motivo and "#2 (2026-07-31)" in motivo


def test_a_recusa_grava_evento_e_a_linha_PULADA_tem_data(factory):
    """A recusa não pode ser só log: o evento é o que chega ao painel e ao
    Teams. E a linha PULADA precisa de uma data para existir — é o degrau 4, o
    cálculo do próprio pipeline, JAMAIS uma das duas corridas em disputa."""
    corrida = _Corrida(_AMBIGUO)
    ns = _ns_com(factory, corrida)
    hook = _instala_hook(ns, _HookF2())
    with _ambiente_utils(malha_corrida=corrida):
        assert ns["check_agenda"](**_ctx()) is False
    sqls = _sqls(hook)
    evento = [s for s in sqls if "etl_dependencia_evento" in s]
    assert evento, sqls
    par_ev = [p for s, p in hook.cursor.execs if "etl_dependencia_evento" in s][0]
    assert "DATA_DIVERGENTE" in par_ev and ODATE in par_ev
    upd = [p for s, p in hook.cursor.execs if s.startswith("UPDATE")][0]
    assert upd[0] == "PULADO" and "MALHA_ODATE_AMBIGUO" in upd[1]
    assert ODATE in upd            # a data calculada, e nenhum vínculo de corrida
    assert 12 not in upd


def test_a_recusa_vale_para_disparo_MANUAL_tambem(factory):
    """Fica fora do `if _origem == 'agenda'` de propósito: o ODATE é do RUN. Um
    manual sem data tem exatamente o mesmo problema."""
    corrida = _Corrida(_AMBIGUO)
    ns = _ns_com(factory, corrida)
    _instala_hook(ns, _HookF2())
    with _ambiente_utils(malha_corrida=corrida):
        ok, motivo = ns["_check_agenda_regras"](_ctx(run_id="manual__2026-08-01"))
    assert ok is False and "MALHA_ODATE_AMBIGUO" in motivo


def test_odate_indisponivel_nao_derruba_a_carga(factory, capsys):
    """A checagem é LEITURA, e leitura degrada: um módulo que levanta não pode
    pular a execução — muito menos derrubar a task."""
    class _Explode(_Corrida):
        def odate(self, *a, **kw):
            raise RuntimeError("banco fora")

    corrida = _Explode()
    ns = _ns_com(factory, corrida)
    _instala_hook(ns, _HookF2())
    with _ambiente_utils(malha_corrida=corrida):
        ok, motivo = ns["_check_agenda_regras"](_ctx())
    assert ok is True and motivo is None
    assert "ODATE da corrida indisponivel" in capsys.readouterr().out


# ═══════════ 6. o push: herança da corrida e as duas marcas novas ═══════════

def _ns_push(factory, corrida, dep):
    src = _src_f3(factory)
    ns = {}
    with _amb_push(dependencias=dep, malha_corrida=corrida):
        exec(compile(src, "<dag>", "exec"), ns)
    return ns


def _dispara(ns, corrida, dep, ctx=None):
    with _amb_push(dependencias=dep, malha_corrida=corrida):
        with _cliente_trigger() as disparos:
            ns["_disparar_dependentes"](ctx or _ctx())
    return disparos


def test_o_conf_do_filho_leva_a_corrida_do_pai(factory):
    """Degrau 1 da cascata: a corrida do pai viaja no conf. Sem ela, cada filho
    resolveria o ODATE por conta própria — que é como a cascata se parte em dois
    dias quando a corrida fecha no meio."""
    corrida = _Corrida(_resp(data=ODATE, corrida_id=12, degrau="corrida"))
    dep = _dep_fake()
    ns = _ns_push(factory, corrida, dep)
    _instala_hook(ns, _HookF2())
    disparos = _dispara(ns, corrida, dep)
    assert disparos and disparos[0]["conf"]["malha_execucao_id"] == 12
    assert disparos[0]["conf"]["data_referencia"] == "2026-08-01"


def test_sem_corrida_o_conf_sai_como_sempre_saiu(factory):
    """A chave é ADITIVA: fora de malha o conf não muda de forma, e nenhum
    consumidor precisa aprender chave nova para continuar funcionando."""
    corrida = _Corrida()
    dep = _dep_fake()
    ns = _ns_push(factory, corrida, dep)
    _instala_hook(ns, _HookF2())
    disparos = _dispara(ns, corrida, dep)
    assert set(disparos[0]["conf"]) == {"data_referencia", "dia_operacional",
                                        "disparado_por"}


def test_push_RECUSA_filho_com_odate_ambiguo(factory, capsys):
    """Decisão 35 — é AQUI que a recusa dispara de verdade: o pipeline
    compartilhado por duas malhas é, quase por definição, um dependente, e ele
    chega por push, não por cron."""
    corrida = _Corrida(
        _resp(data=ODATE, corrida_id=12, degrau="corrida"),
        por_pipeline={"PIPE_C": {"ambiguo": True,
                                 "detalhe": "MALHA_ODATE_AMBIGUO: PIPE_C ..."}})
    dep = _dep_fake()
    ns = _ns_push(factory, corrida, dep)
    _instala_hook(ns, _HookF2())
    disparos = _dispara(ns, corrida, dep)
    assert disparos == []
    assert ("evento", "PIPE_C", ODATE, "DATA_DIVERGENTE",
            "MALHA_ODATE_AMBIGUO: PIPE_C ...") in dep.chamadas
    assert "NAO disparado" in capsys.readouterr().out


def test_claim_perdido_deixa_de_ser_silencio_total(factory):
    """Decisão 35, segunda metade: a malha A empurra e ganha o claim; a malha B
    empurra, recebe `ganho is None` e — até esta fase — seguia sem deixar marca
    nenhuma de que a corrida B ficou sem o membro."""
    corrida = _Corrida(
        _resp(data=ODATE, corrida_id=12, degrau="corrida"),
        por_pipeline={"PIPE_C": {"data": ODATE, "corrida_id": 99,
                                 "degrau": "corrida"}})
    dep = _dep_fake(reservar="perde")
    ns = _ns_push(factory, corrida, dep)
    _instala_hook(ns, _HookF2())
    disparos = _dispara(ns, corrida, dep)
    assert disparos == []
    eventos = [c for c in dep.chamadas if c[0] == "evento"]
    assert len(eventos) == 1
    assert "MALHA_CORRIDA_SEM_MEMBRO" in eventos[0][4]
    assert "#99" in eventos[0][4] and "#12" in eventos[0][4]


def test_claim_perdido_na_MESMA_corrida_continua_mudo(factory):
    """Dois pais da mesma corrida disputando o mesmo filho é o funcionamento
    normal do claim — gravar evento aí ensinaria a operação a ignorar eventos."""
    corrida = _Corrida(
        _resp(data=ODATE, corrida_id=12, degrau="corrida"),
        por_pipeline={"PIPE_C": {"data": ODATE, "corrida_id": 12,
                                 "degrau": "corrida"}})
    dep = _dep_fake(reservar="perde")
    ns = _ns_push(factory, corrida, dep)
    _instala_hook(ns, _HookF2())
    _dispara(ns, corrida, dep)
    assert [c for c in dep.chamadas if c[0] == "evento"] == []


# ══════ 6b. F6 — a porta do PUSH entrega a corrida da LINHA ao predicado ════

def _corrida_perguntada(dep):
    """O 4º elemento do registro de `liberado` no dublê — a corrida passada."""
    return [c[3] for c in dep.chamadas if c[0] == "liberado"]


def test_push_pergunta_pela_corrida_do_FILHO_e_nao_do_pai(factory):
    """Decisão 39 — a linha avaliada é a do FILHO, então o corte é o
    `aberta_em` da corrida DELE.

    Passar a do pai pareceria "quase certo" e seria errado exatamente no caso
    que a malha existe para tratar: pai e filho em corridas diferentes (membro
    compartilhado, rerun, cadeia que atravessa a virada). O filho seria julgado
    pelo relógio de um ciclo que não é o dele."""
    corrida = _Corrida(
        _resp(data=ODATE, corrida_id=12, degrau="corrida"),
        por_pipeline={"PIPE_C": {"data": ODATE, "corrida_id": 99,
                                 "degrau": "corrida"}})
    dep = _dep_fake()
    ns = _ns_push(factory, corrida, dep)
    _instala_hook(ns, _HookF2())
    _dispara(ns, corrida, dep)
    assert _corrida_perguntada(dep) == [99]


def test_push_sem_corrida_pergunta_com_None_e_o_degrau_2_resolve(factory):
    """Fora de malha (ou com o interruptor em 0) a corrida é None e o predicado
    resolve pelos degraus 2 e 3 — o comportamento de antes da fase."""
    corrida = _Corrida()
    dep = _dep_fake()
    ns = _ns_push(factory, corrida, dep)
    _instala_hook(ns, _HookF2())
    _dispara(ns, corrida, dep)
    assert _corrida_perguntada(dep) == [None]


def test_push_com_utils_anterior_a_F6_nao_para_a_cascata(factory, capsys):
    """A rede de ROLLBACK, e ela vale o teste porque a rota já foi MEDIDA uma
    vez neste projeto: `dags/utils/` revertido com o `generated/` ainda
    regerado (o `force_all` não se desfaz e o deploy nunca limpa a pasta).

    Sem a rede, `liberado` de 3 argumentos levanta `TypeError`, o `except` do
    laço engole por filho e NENHUM dependente roda — com o pai VERDE. Com ela,
    perde-se só o degrau 1 do corte."""
    corrida = _Corrida(_resp(data=ODATE, corrida_id=12, degrau="corrida"))
    dep = _dep_fake()

    def _antigo(conn, filho, data_ref):            # a assinatura de antes da F6
        dep.chamadas.append(("liberado", filho, data_ref, "3-args"))
        return True, []

    dep.liberado = _antigo
    ns = _ns_push(factory, corrida, dep)
    _instala_hook(ns, _HookF2())
    disparos = _dispara(ns, corrida, dep)
    assert disparos, "a cascata NAO pode parar com o pai verde"
    assert _corrida_perguntada(dep) == ["3-args"]
    assert "anterior a F6" in capsys.readouterr().out


# ════════ 7. DEGRADAÇÃO — o fonte novo × o fonte de main, lado a lado ═══════
#
# Aqui não se lê código: roda-se o MESMO cenário nas duas árvores e comparam-se
# a data devolvida e a lista de `(sql, params)` que foi ao banco.

class _CorridaDesligada(_Corrida):
    """Interruptor em 0 / 085 ausente — as duas coisas são o mesmo caminho."""

    def __init__(self):
        super().__init__(ativa=False)

    def odate(self, *a, **kw):
        self.chamadas.append(kw)
        return dict(self.VAZIO)


@pytest.mark.parametrize("conf", [
    None,
    {"data_referencia": "2026-07-31"},
    {"data_referencia": "data-invalida"},
])
@pytest.mark.parametrize("virada", [None, "20:00:00"])
def test_sem_a_085_a_data_e_o_sql_sao_os_de_main(factory, factory_main, conf,
                                                 virada):
    """A data de hoje, BYTE A BYTE: mesma resposta e mesmas consultas."""
    corrida = _CorridaDesligada()
    ns_novo = _ns_com(factory, corrida)
    ns_velho = {}
    with _ambiente_utils(malha_corrida=corrida):
        exec(compile(_src(factory_main), "<dag-main>", "exec"), ns_velho)
    hook_novo = _instala_hook(ns_novo, _HookF2(virada=virada))
    hook_velho = _instala_hook(ns_velho, _HookF2(virada=virada))
    ctx = _ctx(conf=conf)
    with _ambiente_utils(malha_corrida=corrida):
        data_nova = ns_novo["_data_referencia"](ctx)
        data_velha = ns_velho["_data_referencia"](ctx)
    assert data_nova == data_velha
    assert hook_novo.get_firsts == hook_velho.get_firsts


@pytest.mark.parametrize("status", ["EXECUTANDO", "PULADO", "SUCESSO", "FALHA"])
@pytest.mark.parametrize("rowcount", [1, 0])
def test_sem_a_085_o_registro_emite_o_mesmo_sql_de_main(factory, factory_main,
                                                        status, rowcount):
    """O upsert do caminho quente: sem vínculo, o texto e os parâmetros que vão
    ao banco são os de antes desta fase — nos quatro status e nos dois caminhos
    (UPDATE que achou a linha e UPDATE que não achou e vira INSERT)."""
    corrida = _CorridaDesligada()
    ns_novo = _ns_com(factory, corrida)
    ns_velho = {}
    with _ambiente_utils(malha_corrida=corrida):
        exec(compile(_src(factory_main), "<dag-main>", "exec"), ns_velho)
    hook_novo = _instala_hook(ns_novo, _HookF2(rowcount_update=rowcount))
    hook_velho = _instala_hook(ns_velho, _HookF2(rowcount_update=rowcount))
    ctx = _ctx()
    with _ambiente_utils(malha_corrida=corrida):
        ns_novo["_registrar_execucao"](status, ctx, motivo="teste")
        ns_velho["_registrar_execucao"](status, ctx, motivo="teste")
    assert hook_novo.cursor.execs == hook_velho.cursor.execs
    assert hook_novo.commits == hook_velho.commits
    assert not any("malha_execucao_id" in s for s, _ in hook_novo.cursor.execs)


def test_sem_o_modulo_no_servidor_a_dag_importa_e_a_data_sai(factory,
                                                             factory_main):
    """O import guardado, provado: `utils.malha_corrida` FORA do sys.modules."""
    src = _src(factory)
    ns = {}
    pacote = SimpleNamespace()          # `from utils import malha_corrida` falha
    util_mods = {"utils": pacote}
    salvos = {m: sys.modules.get(m) for m in util_mods}
    try:
        with _ambiente_utils():
            sys.modules.update(util_mods)
            sys.modules.pop("utils.malha_corrida", None)
            exec(compile(src, "<dag>", "exec"), ns)
            assert ns["_corrida"] is None
            _instala_hook(ns, _HookF2())
            assert ns["_data_referencia"](_ctx()) == ODATE
    finally:
        for m, prev in salvos.items():
            if prev is None:
                sys.modules.pop(m, None)
            else:
                sys.modules[m] = prev


# ══════ 8. a sonda do §12.2, do lado da API — as duas gerações no disco ═════
#
# Estes testes escrevem no disco o fonte gerado pelas DUAS factories e
# perguntam à sonda da API o que ela vê. É a prova de ponta a ponta do
# `force_all`: o que a API responde sobre um pipeline é função do arquivo que o
# Airflow vai importar, não de um dublê.

def _publicar(raiz, factory_mod, pipeline="PIPE_EXEC", project="BI_CVP",
              domain="TESTE"):
    destino = Path(raiz) / "generated" / project / domain
    destino.mkdir(parents=True, exist_ok=True)
    alvo = destino / f"{pipeline}.py"
    alvo.write_text(factory_mod._generate_dag_source(
        {"pipeline_name": pipeline, "project_name": project, "domain": domain,
         "tags": "ETL", "scheduled_time": "06:00:00", "envia_msg_inicio": 0,
         "envia_msg_fim": 1, "envia_msg_erro": 1, "ambiente": "PROD",
         "schedule_type": "daily"},
        [_job("JobA")]), encoding="utf-8")
    return alvo


def test_a_sonda_separa_a_dag_regerada_da_dag_velha(tmp_path, factory,
                                                    factory_main, monkeypatch):
    """As duas gerações convivem no ar enquanto o `force_all` não termina — e
    é exatamente isso que a sonda tem de distinguir, arquivo a arquivo."""
    from api.services import espera as esp
    esp._cache_portao.clear()
    monkeypatch.setenv("DAGS_FOLDER", str(tmp_path))
    nova = _publicar(tmp_path, factory, pipeline="PIPE_NOVO")
    velha = _publicar(tmp_path, factory_main, pipeline="PIPE_VELHO")
    assert esp.carimbo_corrida_no_arquivo(nova) == esp.CORRIDA_OK
    assert esp.carimbo_corrida_no_arquivo(velha) == esp.CORRIDA_AUSENTE


def test_DESCONHECIDO_nao_e_ausencia(tmp_path, monkeypatch):
    """⚠️ O terceiro valor é uma DÚVIDA, não uma acusação: "não montei o
    caminho" e "não li o arquivo" não provam nada sobre o fonte publicado.
    Tratá-los como ausência mandaria republicar meia malha por causa de um
    cadastro com caractere estranho no domínio."""
    from api.services import espera as esp
    esp._cache_portao.clear()
    monkeypatch.setenv("DAGS_FOLDER", str(tmp_path))
    assert esp.carimbo_corrida_no_arquivo(None) == esp.CORRIDA_DESCONHECIDO
    assert esp.carimbo_corrida_no_arquivo(
        tmp_path / "nao_existe.py") == esp.CORRIDA_DESCONHECIDO
    # cadastro sem domínio → não dá para montar o caminho
    class _Cur:
        def execute(self, *a, **kw):
            self._row = ("BI_CVP", "")

        def fetchone(self):
            return self._row
    assert esp.estado_carimbo_corrida(_Cur(), "PIPE") == esp.CORRIDA_DESCONHECIDO


def test_a_sonda_e_por_pipeline_e_devolve_as_duas_colunas(tmp_path, factory,
                                                          factory_main,
                                                          monkeypatch):
    """§12.2 — `pipeline` e `sonda`, na ordem recebida: é assim que o operador
    vê QUEM ficou para trás e republica só aquele. A conferência agregada
    ("N de M") esconde justamente a informação que resolve o problema."""
    from api.services import espera as esp
    esp._cache_portao.clear()
    monkeypatch.setenv("DAGS_FOLDER", str(tmp_path))
    _publicar(tmp_path, factory, pipeline="PIPE_NOVO")
    _publicar(tmp_path, factory_main, pipeline="PIPE_VELHO")

    class _CurCad:
        def execute(self, sql, params=()):
            self._row = ("BI_CVP", "TESTE")

        def fetchone(self):
            return self._row

    linhas = esp.carimbo_corrida_dos_pipelines(
        _CurCad(), ["PIPE_NOVO", "PIPE_VELHO", "PIPE_SEM_ARQUIVO"])
    assert linhas == [
        {"pipeline": "PIPE_NOVO", "sonda": esp.CORRIDA_OK},
        {"pipeline": "PIPE_VELHO", "sonda": esp.CORRIDA_AUSENTE},
        {"pipeline": "PIPE_SEM_ARQUIVO", "sonda": esp.CORRIDA_DESCONHECIDO},
    ]


def test_o_cache_da_sonda_e_por_marca(tmp_path, factory, monkeypatch):
    """Duas marcas no mesmo arquivo respondem coisas diferentes; uma chave de
    cache só faria a segunda pergunta herdar a resposta da primeira — e a DAG
    com portão passaria por 'já tem o carimbo do ODATE'."""
    from api.services import espera as esp
    esp._cache_portao.clear()
    monkeypatch.setenv("DAGS_FOLDER", str(tmp_path))
    alvo = _publicar(tmp_path, factory)
    assert esp.portao_no_arquivo(alvo) == esp.PORTAO_OK
    assert esp.carimbo_corrida_no_arquivo(alvo) == esp.CORRIDA_OK
    assert len(esp._cache_portao) == 2


def test_com_o_modulo_REAL_desligado_o_sql_da_carga_nao_muda(factory,
                                                             factory_main):
    """A degradação com o módulo de VERDADE (não com o dublê): interruptor em
    0 é o estado do dev hoje e de qualquer banco sem a 085.

    O que se compara é o SQL que toca as tabelas da CARGA — ele tem de ser o de
    `main`, statement por statement, parâmetro por parâmetro. O único acréscimo
    permitido é UMA leitura de `etl_app_config`: o kill switch, lido uma vez por
    processo (o mesmo custo de `dependencia_modo_sequencia`). Se um dia essa
    conta crescer, este teste falha e obriga a olhar.
    """
    import importlib.util as _iu
    spec = _iu.spec_from_file_location("malha_corrida_real_f5",
                                       _ROOT / "dags/utils/malha_corrida.py")
    real = _iu.module_from_spec(spec)
    spec.loader.exec_module(real)
    real.limpar_cache()

    class _HookConfig(_HookF2):
        """Devolve `0` para o interruptor — e grava tudo que passou."""

        def get_conn(self):
            conn = super().get_conn()

            class _Cur:
                def __init__(self, real_cur):
                    self._c = real_cur
                    self.rowcount = -1

                def execute(self, sql, params=()):
                    if "malha_corrida_ativa" in str(params):
                        self._c.execs.append((" ".join(str(sql).split()),
                                              tuple(params)))
                        self._resposta = ("0",)
                        return
                    self._resposta = None
                    return self._c.execute(sql, params)

                def fetchone(self):
                    if self._resposta is not None:
                        return self._resposta
                    return self._c.fetchone()

                def fetchall(self):
                    return []

                def __getattr__(self, nome):
                    return getattr(self._c, nome)

            cur = _Cur(self.cursor)
            conn.cursor = lambda: cur
            return conn

    ns_novo = {}
    ns_velho = {}
    with _ambiente_utils(malha_corrida=real):
        exec(compile(_src(factory), "<dag>", "exec"), ns_novo)
        exec(compile(_src(factory_main), "<dag-main>", "exec"), ns_velho)
        hook_novo = _instala_hook(ns_novo, _HookConfig())
        hook_velho = _instala_hook(ns_velho, _HookF2())
        ctx = _ctx()
        assert ns_novo["_data_referencia"](ctx) == ns_velho["_data_referencia"](ctx)
        ns_novo["_registrar_execucao"]("SUCESSO", ctx)
        ns_velho["_registrar_execucao"]("SUCESSO", ctx)
    config_novo = [c for c in hook_novo.cursor.execs
                   if "etl_app_config" in c[0]]
    carga_novo = [c for c in hook_novo.cursor.execs
                  if "etl_app_config" not in c[0]]
    assert len(config_novo) == 1, config_novo
    assert carga_novo == hook_velho.cursor.execs
