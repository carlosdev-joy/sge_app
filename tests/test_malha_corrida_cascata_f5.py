"""
O ODATE da corrida de ponta a ponta: o FONTE GERADO contra o módulo REAL e um
SQL Server em miniatura (F5 de docs/spec-malha-execucao.md — §7, Decisões 33 a
37).

Por que este arquivo existe ao lado de tests/test_dag_factory_odate_corrida.py:
aquele prova a **fiação** (o fonte gerado pergunta ao módulo com os argumentos
certos e obedece à resposta) usando um dublê do módulo; tests/test_malha_corrida
prova a **regra** (a precedência dos degraus) usando um dublê do banco. Nenhum
dos dois prova o que a fase inteira promete, que é uma frase sobre a LINHA
gravada:

  «a cascata inteira existe em UM ODATE só, e todas as linhas trazem o MESMO
   `malha_execucao_id`»

Isso é a composição de três peças — fonte gerado + módulo real + banco — e
composição só se prova junto. Aqui o único dublê é o BANCO (o `Banco` de
tests/test_malha_corrida.py, que interpreta o SQL de verdade: índices únicos,
CHECKs, `rowcount`), acrescido das três consultas da 067 que o upsert do fonte
gerado emite. O módulo `utils/malha_corrida.py` é o REAL, e as DAGs são as que a
factory gera AGORA.

REGRA DO DUBLÊ, herdada de tests/test_malha_corrida.py e paga com 3 defeitos
ALTOS nas F2/F4: guarda que mora no `WHERE` do módulo **só** é aplicada aqui se
o SQL emitido a contiver. É por isso que `_upd_execucao` abaixo lê o texto para
decidir se aplica o write-once (`COALESCE`) e a guarda de estado terminal — sem
isso, apagar o `COALESCE` do gerador passaria verde.

O que cada teste guarda está no nome. Os quatro que a spec nomeia como aceite da
F5 e que só existem aqui:
  • o `Carga_Vida` invertido, com a linha gravada como prova;
  • a cascata inteira num `malha_execucao_id` só;
  • as 4 chamadas do run com a corrida FECHANDO no meio — mesmo ODATE, UMA
    resolução, UMA linha;
  • o rerun que reusa o `run_id` e preserva a corrida original.
"""
from __future__ import annotations

import importlib.util
import sys
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_malha_corrida import (
    Banco, Cur, banco as _banco_085, erro_coluna_ausente)
from tests.test_dag_factory_dependencias_f3 import (
    _ambiente_utils as _amb, _cliente_trigger, _ctx, _dep_fake, _instala_hook,
    _src)

_ROOT = Path(__file__).parent.parent

# O ODATE do CICLO e o ODATE que o pipeline calcularia sozinho. Eles são
# DIFERENTES de propósito em todos os testes: se fossem iguais, "a corrida
# venceu" e "o cálculo venceu" produziriam a mesma linha e o teste passaria
# verde pelo motivo errado — que é exatamente como o incidente `Carga_Vida`
# atravessou a 081.
ODATE_CICLO = date(2026, 7, 31)
ODATE_CALCULADO = date(2026, 8, 1)      # o `_ctx` roda em 2026-08-01 06:00

_COMMIT_BASE = "cbce3e2"                # o fonte de antes da F5 (ver o vizinho)


@pytest.fixture(scope="module")
def factory():
    spec = importlib.util.spec_from_file_location(
        "etl_dag_factory_cascata_test", _ROOT / "dags/etl_dag_factory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mcr():
    """O módulo do ciclo REAL — o mesmo arquivo que vai para o servidor."""
    spec = importlib.util.spec_from_file_location(
        "utils_malha_corrida_cascata", _ROOT / "dags/utils/malha_corrida.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _sem_cache(mcr):
    """O interruptor é cacheado por PROCESSO: sem isto o primeiro teste que o
    lê decide a resposta de todos os outros."""
    mcr.limpar_cache()
    yield
    mcr.limpar_cache()


# ═══════════ o banco: a 085 do vizinho + a 067 que o motor escreve ══════════

class _CurMotor(Cur):
    """`Cur` da 085 acrescido das TRÊS consultas que `_registrar_execucao`
    emite sobre `dbo.etl_pipeline_execucao` (o upsert do caminho quente).

    O que se interpreta aqui é o TEXTO do statement, não a intenção: o
    write-once só vale se o SQL trouxer o `COALESCE`, a guarda de terminal só
    vale se o SQL trouxer o `AND status NOT IN`, e a coluna só é gravada se o
    SQL a nomear. Um dublê que aplicasse essas regras por conta própria estaria
    provando a si mesmo — foi assim que dois defeitos passaram verdes na F2.
    """

    def execute(self, sql, params=()):
        db = self.db
        s = " ".join(str(sql).split()).replace("%s", "?")
        p = tuple(params or ())
        if not s.startswith(("UPDATE dbo.etl_pipeline_execucao SET status=",
                             "INSERT INTO dbo.etl_pipeline_execucao",
                             "SELECT 1 FROM dbo.etl_pipeline_execucao")):
            return super().execute(sql, params)
        db.sqls.append((s, p))
        self._rows = []
        self.rowcount = -1
        if db.explodir:
            raise RuntimeError("banco fora do ar (teste)")
        # Sem a 085 a COLUNA não existe: o 207 é o que o driver devolve, e é
        # dele que a cascata de fallback do fonte gerado depende.
        if not db.com_085 and "malha_execucao_id" in s:
            raise erro_coluna_ausente("malha_execucao_id", db.driver)
        if s.startswith("UPDATE"):
            return self._upd_execucao(s, p)
        if s.startswith("INSERT"):
            return self._ins_execucao(s, p)
        chave = (p[0], p[1], str(p[2]))
        self._rows = [(1,)] if self._linhas(*chave) else []

    # ── implementações ──────────────────────────────────────────────────────
    def _linhas(self, pipe, dref, exec_id):
        return [l for l in self.db.execucoes
                if l["pipeline_name"] == pipe and l["data_referencia"] == dref
                and str(l["execution_id"]) == str(exec_id)]

    def _upd_execucao(self, s, p):
        tem_coluna = "malha_execucao_id" in s
        vinculo = p[3] if tem_coluna else None
        pipe, dref, exec_id = p[4:] if tem_coluna else p[3:]
        # As duas guardas são LIDAS do texto, nunca assumidas.
        write_once = "malha_execucao_id=COALESCE(malha_execucao_id, ?)" in s
        guarda_terminal = "AND status NOT IN ('SUCESSO', 'FALHA')" in s
        n = 0
        for linha in self._linhas(pipe, dref, exec_id):
            if guarda_terminal and linha["status"] in ("SUCESSO", "FALHA"):
                continue
            linha.update(status=p[0], motivo=p[1], disparado_por=p[2])
            if tem_coluna and (not write_once
                               or linha.get("malha_execucao_id") is None):
                linha["malha_execucao_id"] = vinculo
            n += 1
        self.rowcount = n

    def _ins_execucao(self, s, p):
        db = self.db
        tem_coluna = "malha_execucao_id" in s
        assert tem_coluna == (len(p) == 7), f"INSERT com {len(p)} params: {s}"
        db.execucoes.append({
            "id": db.proximo_exec_id, "pipeline_name": p[0],
            "data_referencia": p[1], "execution_id": p[2], "status": p[3],
            "disparado_por": p[4], "motivo": p[5],
            "malha_execucao_id": p[6] if tem_coluna else None})
        db.proximo_exec_id += 1
        self.rowcount = 1


class _BancoMotor(Banco):
    """O `Banco` da 085 com a 067 escrevível — e um `id` crescente por linha,
    porque o degrau 0 lê `TOP 1 ... ORDER BY id`."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.proximo_exec_id = 1 + max(
            [l.get("id", 0) for l in self.execucoes], default=0)

    def cursor(self):
        return _CurMotor(self)


def _banco(**kw) -> _BancoMotor:
    base = _banco_085(**kw)
    return _BancoMotor(
        malhas=base.malhas, malha_pipeline=base.malha_pipeline,
        pipelines=base.pipelines, dependencias=base.dependencias,
        config=base.config, execucoes=base.execucoes, com_085=base.com_085,
        explodir=base.explodir, driver=base.driver, agora=base.agora)


class _HookMotor:
    """MsSqlHook falso cujo `get_conn` é o banco em miniatura — o mesmo objeto
    para o módulo da corrida, para o upsert e para o push."""

    def __init__(self, db, virada=None, tem_067=True):
        self.db = db
        self.virada = virada
        self.tem_067 = tem_067
        self.get_firsts = []

    def get_first(self, sql, parameters=None):
        s = " ".join(str(sql).split())
        self.get_firsts.append((s, parameters))
        if "OBJECT_ID" in s:
            return (1,) if self.tem_067 else (None,)
        if "hora_virada" in s:
            return (self.virada,)
        return None            # blackout/calendário: nada bloqueia

    def get_conn(self):
        return self.db

    def run(self, *a, **kw):
        pass


def _dag(factory, mcr, pipeline, db, **over):
    """Uma DAG gerada AGORA para `pipeline`, com o módulo REAL da corrida e o
    hook apontando para `db`. Devolve (namespace, hook)."""
    ns = {}
    with _amb(malha_corrida=mcr):
        exec(compile(_src(factory, pipeline_name=pipeline, **over),
                     f"<dag {pipeline}>", "exec"), ns)
    return ns, _instala_hook(ns, _HookMotor(db))


def _linha_do_run(db, pipeline, run_id):
    achadas = [l for l in db.execucoes if l["pipeline_name"] == pipeline
               and str(l["execution_id"]) == str(run_id)]
    assert len(achadas) == 1, f"{len(achadas)} linhas do run {run_id}: {achadas}"
    return achadas[0]


def _consultas_de_odate(db, pipeline):
    """As idas ao banco que resolvem o ODATE DESTE pipeline — degrau 0
    (`TOP 1 data_referencia`), degrau 1 e degrau 3 (`etl_malha_execucao me`).

    Filtra por pipeline de propósito: o push consulta o ODATE de cada FILHO na
    mesma conexão, e contar tudo junto diria "foi ao banco de novo" quando quem
    foi ao banco foi outra pergunta, sobre outro pipeline."""
    return [(s, p) for s, p in db.sqls
            if ("SELECT TOP 1 data_referencia" in s
                or "FROM dbo.etl_malha_execucao me" in s)
            and pipeline in p]


def _abre(mcr, db, malha="M1", odate=ODATE_CICLO, origem="manual"):
    c = mcr.abrir_corrida(db, malha, odate, origem)
    mcr.congelar_snapshot(db, c["id"], malha)
    return c


# ══════════ 1. o `Carga_Vida` invertido — a linha gravada como prova ════════

def test_o_membro_com_cron_proprio_carimba_o_ODATE_DA_CORRIDA(factory, mcr):
    """⛔ O caso que a spec inteira existe para resolver, invertido (Decisão 33).

    `PIPE_A` parte pelo PRÓPRIO cron, sem conf nenhum — não é dependente de
    ninguém, não recebeu data de pai algum e não precisou ser rewireado como
    membro de cascata. A malha tem corrida aberta em 2026-07-31; o cálculo pela
    virada, o de sempre, daria 2026-08-01. A linha gravada tem de dizer
    2026-07-31, e tem de nascer vinculada à corrida.

    Se o degrau 3 sumir, a data volta a ser a calculada e esta asserção cai —
    que é o incidente `Carga_Vida` com o mecanismo criado para matá-lo já
    instalado."""
    db = _banco()
    c = _abre(mcr, db)
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    ctx = _ctx()
    with _amb(malha_corrida=mcr):
        assert ns["_odate_pela_virada"](ctx) == ODATE_CALCULADO   # o de sempre
        ns["_registrar_execucao"]("EXECUTANDO", ctx)
    linha = _linha_do_run(db, "PIPE_A", ctx["run_id"])
    assert linha["data_referencia"] == ODATE_CICLO
    assert linha["malha_execucao_id"] == c["id"]


def test_a_DAG_de_ANTES_da_F5_no_mesmo_cenario_grava_o_outro_dia(factory, mcr):
    """O contraste que dá sentido ao teste de cima — e a razão de a F5 exigir
    `force_all`: o fonte publicado ANTES desta fase, no cenário idêntico, grava
    2026-08-01 e fica fora do ciclo. Enquanto a regeração não acontece, os dois
    comportamentos convivem no ar; é isso que a sonda do §12.2 mede."""
    import subprocess
    import tempfile
    bruto = subprocess.run(
        ["git", "-C", str(_ROOT), "show", f"{_COMMIT_BASE}:dags/etl_dag_factory.py"],
        capture_output=True, timeout=30)
    if bruto.returncode != 0:  # pragma: no cover
        pytest.skip(f"commit base {_COMMIT_BASE} indisponivel")
    with tempfile.NamedTemporaryFile("wb", suffix="_factory_pre_f5.py",
                                     delete=False) as fh:
        fh.write(bruto.stdout)
        caminho = fh.name
    try:
        spec = importlib.util.spec_from_file_location("factory_pre_f5", caminho)
        velha = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(velha)
    finally:
        Path(caminho).unlink(missing_ok=True)
    db = _banco()
    _abre(mcr, db)
    ns, _ = _dag(velha, mcr, "PIPE_A", db)
    ctx = _ctx()
    with _amb(malha_corrida=mcr):
        ns["_registrar_execucao"]("EXECUTANDO", ctx)
    linha = _linha_do_run(db, "PIPE_A", ctx["run_id"])
    assert linha["data_referencia"] == ODATE_CALCULADO
    assert linha["malha_execucao_id"] is None


# ═══════ 2. a cascata inteira num ODATE só e num vínculo só (aceite) ════════

def _push(ns, mcr, db, ctx, filhos):
    """O push do pai para `filhos`, com a linha do filho NASCENDO no claim —
    como `reservar_corrida` faz de verdade: com data e run_id, e SEM
    `malha_execucao_id`. É essa linha órfã que o degrau 0 do filho encontra
    pronta, e foi ela que produziu o `DEV_F10_D` sem vínculo medido no dev."""
    dep = _dep_fake(dependentes=list(filhos))
    reservar_original = dep.reservar_corrida

    def reservar(conn, filho, data_ref, run_id, origem):
        ganho = reservar_original(conn, filho, data_ref, run_id, origem)
        if ganho:
            db.execucoes.append({
                "id": db.proximo_exec_id, "pipeline_name": filho,
                "data_referencia": data_ref, "execution_id": ganho,
                "status": "EXECUTANDO", "disparado_por": origem,
                "motivo": None, "malha_execucao_id": None})
            db.proximo_exec_id += 1
        return ganho

    dep.reservar_corrida = reservar
    with _amb(dependencias=dep, malha_corrida=mcr):
        with _cliente_trigger() as disparos:
            ns["_disparar_dependentes"](ctx)
    return disparos


def test_a_cascata_inteira_traz_o_MESMO_malha_execucao_id(factory, mcr):
    """Aceite da F5: a raiz parte por cron e as três linhas — raiz, filho e
    neto — existem no MESMO ODATE e na MESMA corrida.

    O caminho é o de produção inteiro: degrau 3 na raiz (ela não tem conf),
    `montar_conf` levando a corrida no conf, degrau 0 + proveniência no filho
    (cuja linha nasceu órfã no claim do pai) e o `COALESCE` gravando o vínculo
    uma vez só."""
    db = _banco()
    c = _abre(mcr, db)
    ns_a, _ = _dag(factory, mcr, "PIPE_A", db)
    ctx_a = _ctx()
    with _amb(malha_corrida=mcr):
        ns_a["_registrar_execucao"]("EXECUTANDO", ctx_a)
        ns_a["_registrar_execucao"]("SUCESSO", ctx_a)
    disparos_b = _push(ns_a, mcr, db, ctx_a, ["PIPE_B"])
    assert disparos_b[0]["conf"]["malha_execucao_id"] == c["id"]

    ns_b, _ = _dag(factory, mcr, "PIPE_B", db)
    ctx_b = _ctx(run_id=disparos_b[0]["run_id"], conf=disparos_b[0]["conf"])
    with _amb(malha_corrida=mcr):
        ns_b["_registrar_execucao"]("EXECUTANDO", ctx_b)
        ns_b["_registrar_execucao"]("SUCESSO", ctx_b)
    disparos_c = _push(ns_b, mcr, db, ctx_b, ["PIPE_C"])

    ns_c, _ = _dag(factory, mcr, "PIPE_C", db)
    ctx_c = _ctx(run_id=disparos_c[0]["run_id"], conf=disparos_c[0]["conf"])
    with _amb(malha_corrida=mcr):
        ns_c["_registrar_execucao"]("SUCESSO", ctx_c)

    assert len(db.execucoes) == 3, db.execucoes
    assert {l["pipeline_name"] for l in db.execucoes} == {"PIPE_A", "PIPE_B",
                                                          "PIPE_C"}
    assert {l["data_referencia"] for l in db.execucoes} == {ODATE_CICLO}
    assert {l["malha_execucao_id"] for l in db.execucoes} == {c["id"]}


def test_a_linha_ORFA_do_claim_do_pai_ganha_o_vinculo_quando_o_filho_roda(
        factory, mcr):
    """⛔ Defeito MEDIDO no dev em 2026-08-05 (`DEV_F10_D` concluiu com
    `malha_execucao_id` NULL): a linha do dependente NASCE no claim do pai, sem
    vínculo, e o degrau 0 responde a data. Se ele respondesse a data E desse a
    proveniência por resolvida, toda a cascata — a maior parte de uma malha —
    ficaria fora do ciclo a que pertence, e o "4 de 7" do card contaria
    errado."""
    db = _banco()
    c = _abre(mcr, db)
    ns_a, _ = _dag(factory, mcr, "PIPE_A", db)
    ctx_a = _ctx()
    with _amb(malha_corrida=mcr):
        ns_a["_registrar_execucao"]("SUCESSO", ctx_a)
    disparos = _push(ns_a, mcr, db, ctx_a, ["PIPE_B"])
    orfa = _linha_do_run(db, "PIPE_B", disparos[0]["run_id"])
    assert orfa["malha_execucao_id"] is None      # como o claim a criou

    ns_b, _ = _dag(factory, mcr, "PIPE_B", db)
    with _amb(malha_corrida=mcr):
        ns_b["_registrar_execucao"]("EXECUTANDO",
                                    _ctx(run_id=disparos[0]["run_id"],
                                         conf=disparos[0]["conf"]))
    assert orfa["malha_execucao_id"] == c["id"]
    assert orfa["data_referencia"] == ODATE_CICLO


# ══════ 3. a memoização (Decisão 36) nos QUATRO pontos de chamada reais ═════

def test_as_quatro_chamadas_do_run_com_a_corrida_FECHANDO_no_meio(factory, mcr):
    """⛔ O teste que prova que a cura não fabrica a doença (Decisão 36), nos
    pontos de chamada de VERDADE: `check_agenda`, o registro do EXECUTANDO, o
    push e o registro do SUCESSO.

    Cenário literal da spec: 01:10 o `check_agenda` resolve pelo degrau 3 e
    grava `(PIPE_A, 2026-07-31, run)`; 04:50 a corrida FECHA; 04:52 o registro
    de sucesso pergunta de novo. Sem memoização a resposta seria 2026-08-01, o
    `UPDATE ... WHERE data_referencia=%s` erraria a chave e o INSERT criaria uma
    SEGUNDA linha do mesmo run em outro dia — o run passaria a existir em dois
    ODATEs, que é a doença desta spec produzida por ela.

    As duas asserções são independentes de propósito: UMA linha (a doença não
    aconteceu) e UMA resolução (as chamadas 2 a 4 não foram ao banco)."""
    db = _banco()
    c = _abre(mcr, db)
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    ctx = _ctx()
    with _amb(malha_corrida=mcr):
        ns["_check_agenda_regras"](ctx)                    # 1ª — 01:10
        depois_da_1a = len(_consultas_de_odate(db, "PIPE_A"))
        assert mcr.fechar_corrida(db, c["id"], "CONCLUIDA", "guardia")  # 04:50
        ns["_registrar_execucao"]("EXECUTANDO", ctx)       # 2ª
        _push(ns, mcr, db, ctx, ["PIPE_B"])                # 3ª
        ns["_registrar_execucao"]("SUCESSO", ctx)          # 4ª — 04:52
    linha = _linha_do_run(db, "PIPE_A", ctx["run_id"])
    assert linha["data_referencia"] == ODATE_CICLO
    assert linha["status"] == "SUCESSO"
    assert linha["malha_execucao_id"] == c["id"]
    assert [l for l in db.execucoes if l["pipeline_name"] == "PIPE_A"] == [linha]
    # 1 a 2 consultas na PRIMEIRA chamada (degrau 0 + degrau 3), e nenhuma
    # depois: a memoização é entregável da fase, não detalhe de implementação.
    assert 1 <= depois_da_1a <= 2
    assert len(_consultas_de_odate(db, "PIPE_A")) == depois_da_1a


def test_banco_mudo_na_1a_chamada_nao_vira_a_data_oficial_do_run(factory, mcr):
    """O avesso da memoização: ela guarda a resposta, e resposta dada com o
    banco MUDO não pode virar memória.

    Cenário: um blip de pool derruba a PRIMEIRA pergunta do run. Sem esta
    guarda, o run responderia pelo cálculo próprio, gravaria a linha com essa
    data, e todas as tasks seguintes herdariam a resposta de um banco que
    estava calado por um segundo — o `Carga_Vida` de volta, agora disparado por
    infraestrutura em vez de por DAG velha.

    Com a guarda, a próxima task REFAZ a pergunta e encontra a corrida."""
    db = _banco()
    c = _abre(mcr, db)
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    ctx = _ctx()

    class _MudoUmaVez:
        """Falha só na 1ª chamada — é o que um blip de pool faz."""
        def __init__(self):
            self.n = 0

        def odate(self, *a, **kw):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("[08S01] Communication link failure")
            return mcr.odate(*a, **kw)

        def __getattr__(self, nome):
            return getattr(mcr, nome)

    # A troca é no NAMESPACE da DAG, não em sys.modules: o `exec` do fonte
    # gerado já resolveu o alias `_corrida` quando o módulo foi montado, e
    # trocar sys.modules depois não alcança quem já ligou.
    mudo = _MudoUmaVez()
    with _amb(malha_corrida=mcr):
        ns["_corrida"] = mudo
        primeira = ns["_odate_do_run"](ctx)
        segunda = ns["_odate_do_run"](ctx)

    # A 1ª responde pelo cálculo (o banco não respondeu) e NÃO é memoizada;
    # a 2ª pergunta de novo, alcança o banco e acha a corrida.
    assert primeira["degrau"] == "calculo" and primeira["corrida"] is None
    assert segunda["corrida"] == c["id"], \
        "a resposta do banco mudo virou a data oficial do run"
    assert segunda["data"] == ODATE_CICLO


def test_o_push_resolve_o_ODATE_do_FILHO_e_isso_nao_e_furo_na_memoizacao(
        factory, mcr):
    """A memoização é do RUN DESTE pipeline. O push pergunta o ODATE de cada
    FILHO (é a recusa por ambiguidade da Decisão 35, e ela é sobre o filho) —
    contar essa pergunta como "foi ao banco de novo" faria o teste de cima
    proibir a trava que a fase acabou de instalar."""
    db = _banco()
    _abre(mcr, db)
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    ctx = _ctx()
    with _amb(malha_corrida=mcr):
        ns["_registrar_execucao"]("EXECUTANDO", ctx)
        antes_pai = len(_consultas_de_odate(db, "PIPE_A"))
        _push(ns, mcr, db, ctx, ["PIPE_B"])
    assert len(_consultas_de_odate(db, "PIPE_A")) == antes_pai
    assert _consultas_de_odate(db, "PIPE_B"), "o filho não foi consultado"


# ═════════════ 4. rerun: o run tem UM ODATE, e ele não muda ═════════════════

def test_rerun_que_reusa_o_run_id_PRESERVA_a_corrida_original(factory, mcr):
    """Aceite da F5. O Clear do Airflow REUSA o `run_id`: o run volta a rodar
    num dia em que a corrida original já fechou e outra, de OUTRO ODATE, está
    aberta. A linha não pode mudar de dia nem de dono — se mudasse, o histórico
    do ciclo de ontem perderia o membro e o de hoje ganharia um que nunca rodou
    nele.

    Quem garante isso é o degrau 0 (o ODATE já gravado na linha deste `run_id`);
    o `COALESCE` do UPDATE é a segunda trava, provada no teste seguinte."""
    db = _banco()
    c = _abre(mcr, db)
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    ctx = _ctx()
    with _amb(malha_corrida=mcr):
        ns["_registrar_execucao"]("SUCESSO", ctx)
    assert mcr.fechar_corrida(db, c["id"], "CONCLUIDA", "guardia")
    nova = _abre(mcr, db, odate=ODATE_CALCULADO)         # o ciclo de hoje
    assert nova["id"] != c["id"]

    # O rerun é outro PROCESSO: a memória em RAM do run não o atravessa.
    ns_rerun, _ = _dag(factory, mcr, "PIPE_A", db)
    with _amb(malha_corrida=mcr):
        ns_rerun["_registrar_execucao"]("EXECUTANDO", ctx)
        ns_rerun["_registrar_execucao"]("SUCESSO", ctx)
    linha = _linha_do_run(db, "PIPE_A", ctx["run_id"])
    assert linha["data_referencia"] == ODATE_CICLO
    assert linha["malha_execucao_id"] == c["id"]
    assert len(db.execucoes) == 1, db.execucoes


def test_a_linha_que_JA_TEM_dono_nao_troca_de_corrida(factory, mcr):
    """O `COALESCE` (write-once, Decisão 9) como ÚLTIMA trava, no caminho em que
    o degrau 0 não pôde responder.

    Cenário reachável, não hipotético: a leitura do degrau 0 degrada larga (uma
    consulta que falha por um instante devolve `{}` com log, por contrato do
    módulo). Aí o degrau 3 responde a corrida ABERTA — que, num redisparo do
    mesmo dia, é OUTRA. Sem o `COALESCE`, a linha da corrida #1 passaria a
    pertencer à #2 e o ciclo de ontem perderia o membro no meio do relatório."""
    db = _banco()
    c = _abre(mcr, db)
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    ctx = _ctx()
    with _amb(malha_corrida=mcr):
        ns["_registrar_execucao"]("EXECUTANDO", ctx)
    linha = _linha_do_run(db, "PIPE_A", ctx["run_id"])
    assert linha["malha_execucao_id"] == c["id"]
    # Redisparo do MESMO dia: a #1 fecha e a #2 abre com o MESMO ODATE — as
    # duas são legítimas (Decisão 7), e é por isso que a identidade é o `id`.
    assert mcr.fechar_corrida(db, c["id"], "CONCLUIDA", "guardia")
    segunda = _abre(mcr, db, odate=ODATE_CICLO)
    assert segunda["id"] != c["id"]

    class _CurSemDegrau0(_CurMotor):
        def execute(self, sql, params=()):
            if "SELECT TOP 1 data_referencia" in str(sql):
                raise RuntimeError("timeout na leitura do carimbo (teste)")
            return super().execute(sql, params)

    db.cursor = lambda: _CurSemDegrau0(db)
    ns_2, _ = _dag(factory, mcr, "PIPE_A", db)
    with _amb(malha_corrida=mcr):
        ns_2["_registrar_execucao"]("SUCESSO", ctx)
    assert linha["malha_execucao_id"] == c["id"]      # NÃO virou a #2
    assert linha["status"] == "SUCESSO"               # e o resto foi gravado


# ═══════ 5. a recusa por ODATE ambíguo, com o módulo real (Decisão 34) ══════

def test_agenda_PULA_com_MALHA_ODATE_AMBIGUO_e_nao_escolhe_nenhuma_das_duas(
        factory, mcr):
    """`PIPE_B` é membro de M1 e de M2. Com as duas correndo em ODATEs
    diferentes, não há resposta certa — e inventar uma é reintroduzir a doença
    com rótulo novo. A linha PULADA nasce na data do PRÓPRIO pipeline (degrau
    4), jamais numa das duas em disputa, e sem vínculo nenhum."""
    db = _banco()
    m1 = _abre(mcr, db, malha="M1", odate=ODATE_CICLO)
    m2 = _abre(mcr, db, malha="M2", odate=ODATE_CALCULADO)
    ns, _ = _dag(factory, mcr, "PIPE_B", db)
    ctx = _ctx()
    with _amb(malha_corrida=mcr):
        ok, motivo = ns["_check_agenda_regras"](ctx)
        assert ns["check_agenda"](**ctx) is False
    assert ok is False
    assert mcr.MOTIVO_ODATE_AMBIGUO in motivo
    assert f"#{m1['id']}" in motivo and f"#{m2['id']}" in motivo
    linha = _linha_do_run(db, "PIPE_B", ctx["run_id"])
    assert linha["status"] == "PULADO"
    assert mcr.MOTIVO_ODATE_AMBIGUO in linha["motivo"]
    assert linha["data_referencia"] == ODATE_CALCULADO   # o cálculo, não a M2
    assert linha["malha_execucao_id"] is None


def test_um_filho_ambiguo_NAO_cancela_os_OUTROS_do_mesmo_push(factory, mcr):
    """LOTE, e não "um caso": o push avalia N candidatos, e a cláusula nova
    entra no meio do laço. Um `continue` no lugar errado — ou uma exceção não
    contida — levaria a recusa de UM membro a matar a cascata inteira, que é o
    invariante D23 da F3 ("erro em um candidato não cancela os demais").

    `PIPE_B` é de M1 e M2, com ODATEs diferentes: ambíguo, recusado. `PIPE_C` é
    só de M1: sai normalmente, e com a corrida do pai no conf."""
    db = _banco()
    m1 = _abre(mcr, db, malha="M1", odate=ODATE_CICLO)
    _abre(mcr, db, malha="M2", odate=ODATE_CALCULADO)
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    ctx = _ctx()
    with _amb(malha_corrida=mcr):
        ns["_registrar_execucao"]("SUCESSO", ctx)
        disparos = _push(ns, mcr, db, ctx, ["PIPE_B", "PIPE_C"])
    assert [d["dag_id"] for d in disparos] == ["PIPE_C"]
    assert disparos[0]["conf"]["malha_execucao_id"] == m1["id"]
    assert disparos[0]["conf"]["data_referencia"] == "2026-07-31"


def test_o_push_RECUSA_o_filho_ambiguo_e_a_corrida_do_pai_NAO_o_arrasta(
        factory, mcr):
    """Decisão 35 — é nesta porta que a recusa dispara de verdade: o membro
    compartilhado por duas malhas é, quase por definição, um DEPENDENTE, e ele
    chega por push. Empurrar a data do pai para dentro dele faria uma das duas
    corridas rodar com o ODATE da outra."""
    db = _banco()
    _abre(mcr, db, malha="M1", odate=ODATE_CICLO)
    _abre(mcr, db, malha="M2", odate=ODATE_CALCULADO)
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    ctx = _ctx()
    with _amb(malha_corrida=mcr):
        ns["_registrar_execucao"]("SUCESSO", ctx)
        disparos = _push(ns, mcr, db, ctx, ["PIPE_B"])
    assert disparos == []
    assert not [l for l in db.execucoes if l["pipeline_name"] == "PIPE_B"]


# ═════════ 6. degradação: a carga NUNCA cai por causa desta fase ════════════

def test_sem_a_085_no_banco_a_linha_e_gravada_e_a_data_e_a_de_sempre(
        factory, mcr):
    """Célula 2 da matriz do §11.1: `dags/` novo, banco velho. Sem a 085 o
    interruptor não existe, a corrida é muda e o motor grava exatamente o que
    gravava antes — na data CALCULADA, sem a coluna."""
    db = _banco(com_085=False, config={})
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    ctx = _ctx()
    with _amb(malha_corrida=mcr):
        ns["_registrar_execucao"]("EXECUTANDO", ctx)
    linha = _linha_do_run(db, "PIPE_A", ctx["run_id"])
    assert linha["data_referencia"] == ODATE_CALCULADO
    assert linha["malha_execucao_id"] is None
    assert not [s for s, _ in db.sqls if "malha_execucao_id" in s]


def test_interruptor_LIGADO_num_banco_SEM_as_tabelas_nao_derruba_a_carga(
        factory, mcr, capsys):
    """A célula que ninguém planeja e que acontece: a chave de configuração
    existe (rollback parcial, restore de outro ambiente, alguém que inseriu a
    linha na mão) e as tabelas não. Leitura degrada LARGA — a carga anda, a data
    é a calculada e a linha é gravada."""
    db = _banco(com_085=False)          # config ainda traz malha_corrida_ativa=1
    assert db.config["malha_corrida_ativa"] == "1"
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    ctx = _ctx()
    with _amb(malha_corrida=mcr):
        ns["_registrar_execucao"]("SUCESSO", ctx)
    linha = _linha_do_run(db, "PIPE_A", ctx["run_id"])
    assert linha["data_referencia"] == ODATE_CALCULADO
    assert linha["malha_execucao_id"] is None
    assert "[EXEC] SUCESSO registrado" in capsys.readouterr().out


def test_banco_fora_do_ar_no_meio_do_run_nao_muda_a_data_ja_decidida(
        factory, mcr, capsys):
    """O ODATE já foi resolvido; o banco cai; o registro seguinte não pode
    inventar outra data — a memória do run é em RAM e não depende do banco."""
    db = _banco()
    c = _abre(mcr, db)
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    ctx = _ctx()
    with _amb(malha_corrida=mcr):
        ns["_registrar_execucao"]("EXECUTANDO", ctx)
        db.explodir = True
        ns["_registrar_execucao"]("SUCESSO", ctx)
        db.explodir = False
        assert ns["_data_referencia"](ctx) == ODATE_CICLO
    linha = _linha_do_run(db, "PIPE_A", ctx["run_id"])
    assert linha["data_referencia"] == ODATE_CICLO
    assert linha["malha_execucao_id"] == c["id"]
    assert "Aviso: execucao nao registrada" in capsys.readouterr().out


# ═════ 7. o bloco de malha do check_agenda: 5 perguntas viram UMA ═══════════

@contextmanager
def _malha_ciclo_espiao():
    """`utils.malha_ciclo` espionado: as cinco perguntas do ciclo inferido mais
    o `inicio_retido`, que é de outra natureza (hold é gesto humano sobre a
    PARTIDA e não é substituído pela corrida)."""
    chamadas: list = []

    def _registra(nome, retorno):
        def _f(*a, **kw):
            chamadas.append(nome)
            return retorno
        return _f

    stub = SimpleNamespace(
        malhas_do_pipeline=_registra("malhas_do_pipeline", ["M1"]),
        inicio_retido=_registra("inicio_retido", None),
        virada_da_malha=_registra("virada_da_malha", None),
        inicio_do_ciclo=_registra("inicio_do_ciclo", datetime(2026, 8, 1)),
        estado_do_ciclo=_registra("estado_do_ciclo",
                                  {"divergentes": [], "em_aberto": []}),
        equalizar_ligado=_registra("equalizar_ligado", False),
        equalizar=_registra("equalizar", []),
        resumo=_registra("resumo", ""),
    )
    anterior = sys.modules.get("utils.malha_ciclo")
    sys.modules["utils.malha_ciclo"] = stub
    try:
        yield chamadas
    finally:
        if anterior is None:
            sys.modules.pop("utils.malha_ciclo", None)
        else:
            sys.modules["utils.malha_ciclo"] = anterior


def test_com_a_corrida_LIGADA_o_ciclo_inferido_sai_do_caminho_mas_o_HOLD_fica(
        factory, mcr):
    """Entregável da F5: as cinco perguntas de `utils/malha_ciclo` (virada,
    início, estado, equalização, resumo) e a heurística de janela viram UMA
    chamada, já feita em `_odate_do_run`.

    O `inicio_retido` NÃO sai: hold é gesto humano sobre a PARTIDA, a corrida
    não o substitui (é a F7 que reescreve hold) e não se remove código que ainda
    protege alguém."""
    db = _banco()
    _abre(mcr, db)
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    with _amb(malha_corrida=mcr), _malha_ciclo_espiao() as chamadas:
        ok, _ = ns["_check_agenda_regras"](_ctx())
    assert ok is True
    assert "inicio_retido" in chamadas
    assert not ({"virada_da_malha", "inicio_do_ciclo", "estado_do_ciclo",
                 "equalizar_ligado", "resumo"} & set(chamadas)), chamadas


def test_com_a_corrida_DESLIGADA_as_cinco_perguntas_continuam_sendo_feitas(
        factory, mcr):
    """A outra metade da mesma frase: com o interruptor em 0 — o estado do dev
    hoje e de todo banco sem a 085 — o bloco antigo roda igualzinho. Ele é o
    fallback declarado no §7, não código morto."""
    db = _banco(config={"malha_corrida_ativa": "0"})
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    with _amb(malha_corrida=mcr), _malha_ciclo_espiao() as chamadas:
        ok, _ = ns["_check_agenda_regras"](_ctx())
    assert ok is True
    assert {"inicio_retido", "virada_da_malha", "inicio_do_ciclo",
            "estado_do_ciclo"} <= set(chamadas), chamadas


def test_o_hold_do_Inicio_continua_parando_a_partida_com_a_corrida_ligada(
        factory, mcr):
    db = _banco()
    _abre(mcr, db)
    ns, _ = _dag(factory, mcr, "PIPE_A", db)
    with _amb(malha_corrida=mcr), _malha_ciclo_espiao() as chamadas:
        sys.modules["utils.malha_ciclo"].inicio_retido = lambda *a, **kw: 42
        ok, motivo = ns["_check_agenda_regras"](_ctx())
    assert ok is False and "segurada no Inicio #42" in motivo
    # e a recusa é ANTES de qualquer pergunta do ciclo inferido: o hold não
    # depende de a corrida existir, e não é ele que a corrida substitui.
    assert "estado_do_ciclo" not in chamadas
