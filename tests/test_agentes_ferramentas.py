"""api/services/agentes_ferramentas.py — as ferramentas do agente DataStage
(F2 da spec docs/spec-agentes-datastage.md).

O que estes testes prendem, e por que cada um existe:

  1. **`redigir()` mascara o VALOR, não some com a linha** — o operador
     precisa continuar vendo QUE campo existe; só o conteúdo sensível some.
     Canário: senha/token/Encrypted nunca sobrevivem, mesmo com variações de
     maiúscula/minúscula e separador (`:`/`=`).

  2. **`resolver_projeto` nunca toca o servidor** — só a BASE e a lista de
     `.dsx` (nomes, não conteúdo). Nome com caixa diferente casa e devolve o
     CANÔNICO (DataStage é sensível a caixa); nome desconhecido devolve
     sugestões, nunca inventa.

  3. **`ferramenta_dsjob` só aceita os 5 comandos da allowlist** — nem
     `logsum`/`logdetail` (podem trazer valor de dado), nem comando livre.
     Isso é reforçado ANTES de abrir qualquer sessão SSH.

  4. **O semáforo tem espera LIMITADA e nomeada** (`ServidorOcupado`), nunca
     trava a rodada indefinidamente; o teto muda em runtime sem derrubar
     quem já está dentro.

Nada aqui toca SSH de verdade: `run_dsjob` é sempre um dublê.
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from services import agentes_ferramentas as af  # noqa: E402
from services.ssh_datastage import DsConsoleError  # noqa: E402


# ═══════════ 1. redigir ══════════════════════════════════════════════════════

@pytest.mark.parametrize("linha,escondido", [
    ("senha: minhaSenha123", "minhaSenha123"),
    ("Password=abc123!!", "abc123!!"),
    ("PWD:  segredo", "segredo"),
    ("api_key = sk-ant-xxxxx", "sk-ant-xxxxx"),
    ("Token: eyJhbGciOi...", "eyJhbGciOi..."),
    ("valor Encrypted: {iisenc}AbCdEf==", "{iisenc}AbCdEf=="),
])
def test_redigir_esconde_o_valor(linha, escondido):
    saida = af.redigir(linha)
    assert escondido not in saida
    assert af._MASCARA in saida


def test_redigir_preserva_o_nome_do_campo():
    saida = af.redigir("senha: segredo123")
    assert "senha" in saida.lower()


def test_redigir_nao_mexe_em_linha_sem_segredo():
    texto = "job_name: BiCvp_Extrai_Pedidos\nstatus: RUN OK"
    assert af.redigir(texto) == texto


def test_redigir_texto_vazio_nao_levanta():
    assert af.redigir("") == ""
    assert af.redigir(None) == ""


def test_redigir_multiplas_linhas():
    texto = "job: X\nsenha: abc\nstatus: ok\ntoken: xyz"
    saida = af.redigir(texto)
    assert "abc" not in saida and "xyz" not in saida
    assert "job: X" in saida and "status: ok" in saida


# ═══════════ 2. truncagem ═════════════════════════════════════════════════════

def test_truncar_texto_curto_nao_muda():
    assert af._truncar("abc", limite=100) == "abc"


def test_truncar_texto_longo_avisa():
    texto = "x" * 10000
    saida = af._truncar(texto, limite=100)
    assert len(saida) < len(texto)
    assert "truncada" in saida


# ═══════════ 3. resolver_projeto — nunca toca o servidor ════════════════════

class _CurProjetos:
    def __init__(self, pipelines=(), isx=()):
        self.pipelines = pipelines
        self.isx = isx

    def execute(self, sql, params=None):
        s = sql.lower()
        if "distinct project_name from dbo.etl_pipeline" in s:
            self._rows = [(p,) for p in self.pipelines]
        elif "distinct ds_project from dbo.etl_ds_job_isx" in s:
            self._rows = [(p,) for p in self.isx]
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)


def test_resolver_projeto_nome_exato_resolve():
    cur = _CurProjetos(pipelines=["BI_CVP"])
    r = af.resolver_projeto(cur, "BI_CVP")
    assert r == {"estado": "resolvido", "projeto": "BI_CVP", "sugerido": None,
                 "tem_dsx": False, "sugestoes": []}


def test_resolver_projeto_caixa_diferente_e_so_sugestao_nao_resolve_sozinho():
    """Critério 11 da F2: nome só diferente na caixa NUNCA resolve sozinho —
    só sugere, e quem confirma é o usuário (via o modelo, numa 2ª chamada)."""
    cur = _CurProjetos(pipelines=["BI_CVP"])
    r = af.resolver_projeto(cur, "bi_cvp")
    assert r["estado"] == "quase"
    assert r["projeto"] is None  # NÃO resolvido ainda
    assert r["sugerido"] == "BI_CVP"  # a grafia CADASTRADA, para o modelo confirmar


def test_resolver_projeto_confirmado_com_a_grafia_exata_resolve():
    """A 2ª chamada, já com o nome exato sugerido, resolve — é assim que a
    'confirmação' do critério 11 se fecha, sem protocolo especial."""
    cur = _CurProjetos(pipelines=["BI_CVP"])
    quase = af.resolver_projeto(cur, "bi_cvp")
    confirmado = af.resolver_projeto(cur, quase["sugerido"])
    assert confirmado["estado"] == "resolvido" and confirmado["projeto"] == "BI_CVP"


def test_resolver_projeto_desconhecido_da_sugestoes_sem_inventar():
    cur = _CurProjetos(pipelines=["BI_CVP", "BI_VIDA"])
    r = af.resolver_projeto(cur, "NAO_EXISTE")
    assert r["estado"] == "desconhecido"
    assert r["projeto"] is None
    assert set(r["sugestoes"]) == {"BI_CVP", "BI_VIDA"}


def test_resolver_projeto_nome_vazio_e_desconhecido():
    cur = _CurProjetos(pipelines=["BI_CVP"])
    r = af.resolver_projeto(cur, "")
    assert r["estado"] == "desconhecido"
    assert r["projeto"] is None


def test_resolver_projeto_nao_toca_o_servidor_datastage(monkeypatch):
    """Nenhuma chamada de rede/SSH — só banco e a lista LOCAL de .dsx."""
    def _explode(*a, **k):
        raise AssertionError("resolver_projeto não deveria tocar o servidor")
    monkeypatch.setattr(af, "run_dsjob", _explode)
    cur = _CurProjetos(pipelines=["BI_CVP"])
    af.resolver_projeto(cur, "BI_CVP")
    af.resolver_projeto(cur, "desconhecido")  # não levanta


def test_resolver_projeto_usa_isx_quando_pipeline_nao_tem():
    cur = _CurProjetos(pipelines=[], isx=["DM_CONTRATOS_CVP"])
    r = af.resolver_projeto(cur, "DM_CONTRATOS_CVP")
    assert r["estado"] == "resolvido" and r["projeto"] == "DM_CONTRATOS_CVP"


def test_resolver_projeto_degrada_se_o_banco_falhar():
    class _Explode:
        def execute(self, *a, **k):
            raise Exception("tabela ausente")

        def fetchall(self):
            return []
    r = af.resolver_projeto(_Explode(), "qualquer")
    assert r["estado"] == "desconhecido"


def test_projeto_do_pipeline_job_usa_lineage_isx(monkeypatch):
    from services import lineage_isx
    monkeypatch.setattr(lineage_isx, "job_do_pipeline",
                        lambda cur, pipeline, job: {"ds_project": "BI_CVP"} if pipeline == "PIPE_VIDA" else None)
    assert af.projeto_do_pipeline_job(None, "PIPE_VIDA", "JobRaiz") == "BI_CVP"
    assert af.projeto_do_pipeline_job(None, "OUTRO", "JobRaiz") is None


def test_resolver_projeto_via_pipeline_job_resolve_sem_perguntar(monkeypatch):
    """Critério 10 da F2: citar um pipeline/job do Orquestra resolve direto
    — nunca cai em 'quase' por causa da caixa (a grafia já vem da base)."""
    from services import lineage_isx
    monkeypatch.setattr(lineage_isx, "job_do_pipeline",
                        lambda cur, pipeline, job: {"ds_project": "BI_CVP"} if pipeline == "PIPE_VIDA" else None)
    cur = _CurProjetos(pipelines=["BI_CVP"])
    r = af.resolver_projeto(cur, pipeline_name="PIPE_VIDA", job_name="JobRaiz")
    assert r == {"estado": "resolvido", "projeto": "BI_CVP", "sugerido": None,
                 "tem_dsx": False, "sugestoes": []}


def test_resolver_projeto_pipeline_job_desconhecido_nao_inventa(monkeypatch):
    from services import lineage_isx
    monkeypatch.setattr(lineage_isx, "job_do_pipeline", lambda cur, pipeline, job: None)
    cur = _CurProjetos(pipelines=["BI_CVP"])
    r = af.resolver_projeto(cur, pipeline_name="NAO_EXISTE", job_name="JobX")
    assert r["estado"] == "desconhecido"


# ═══════════ 4. ferramenta_base ═══════════════════════════════════════════════

class _CurBase:
    def __init__(self, linha=None, stages=0):
        self.linha = linha
        self.stages = stages

    def execute(self, sql, params=None):
        s = sql.lower()
        if "from dbo.etl_ds_job_isx" in s:
            self._rows = [self.linha] if self.linha else []
        elif "count(*) from dbo.etl_job_lineage" in s:
            self._rows = [(self.stages,)]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None


def test_ferramenta_base_encontrado():
    linha = ("PIPE_VIDA", "JobRaiz", "\\Jobs\\Cat", "PARALLEL", "2026-09-01T10:00:00",
             "descricao", "[]", "[]", "ok", None, "2026-09-10 10:00:00")
    cur = _CurBase(linha=linha, stages=5)
    r = af.ferramenta_base(cur, "BI_CVP", "JobRaiz")
    assert r["encontrado"] is True
    assert r["pipeline_name"] == "PIPE_VIDA" and r["stages"] == 5


def test_ferramenta_base_nao_encontrado():
    cur = _CurBase(linha=None)
    r = af.ferramenta_base(cur, "BI_CVP", "JobFantasma")
    assert r == {"encontrado": False}


def test_ferramenta_base_traz_idade_ja_calculada():
    """Critério 3 da F2: a resposta já informa a idade — o modelo não
    precisa calcular a partir de uma data crua."""
    import datetime as _dt
    ha_10_dias = (_dt.datetime.now() - _dt.timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S")
    linha = ("PIPE_VIDA", "JobRaiz", "\\Jobs\\Cat", "PARALLEL", ha_10_dias,
             "descricao", "[]", "[]", "ok", None, "2026-09-10 10:00:00")
    r = af.ferramenta_base(_CurBase(linha=linha, stages=1), "BI_CVP", "JobRaiz")
    assert r["idade_dias"] in (9, 10, 11)  # tolerância de fuso/arredondamento


def test_ferramenta_base_data_ausente_idade_none():
    linha = ("PIPE_VIDA", "JobRaiz", "\\Jobs\\Cat", "PARALLEL", None,
             "descricao", "[]", "[]", "ok", None, "2026-09-10 10:00:00")
    r = af.ferramenta_base(_CurBase(linha=linha, stages=1), "BI_CVP", "JobRaiz")
    assert r["idade_dias"] is None


@pytest.mark.parametrize("bruto", ["não é uma data", "", "31/02/2026"])
def test_idade_dias_formato_inesperado_nao_levanta(bruto):
    assert af._idade_dias(bruto) is None


# ═══════════ 5. ferramenta_dsjob — allowlist e semáforo ═════════════════════

@pytest.mark.asyncio
async def test_dsjob_fora_da_allowlist_nunca_abre_ssh(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError("run_dsjob não deveria ter sido chamado")
    monkeypatch.setattr(af, "run_dsjob", _explode)
    monkeypatch.setattr(af, "ssh_configured", lambda: True)
    for comando in ("logsum", "logdetail", "importar", "; rm -rf /"):
        with pytest.raises(DsConsoleError):
            await af.ferramenta_dsjob(comando, "BI_CVP", "Job", teto_sessoes=10, espera_max_s=1)


@pytest.mark.asyncio
async def test_dsjob_sem_ssh_configurado_e_dsconsoleerror(monkeypatch):
    monkeypatch.setattr(af, "ssh_configured", lambda: False)
    with pytest.raises(DsConsoleError):
        await af.ferramenta_dsjob("ljobs", "BI_CVP", None, teto_sessoes=10, espera_max_s=1)


@pytest.mark.asyncio
async def test_dsjob_comando_permitido_chama_run_dsjob_e_redige(monkeypatch):
    monkeypatch.setattr(af, "ssh_configured", lambda: True)
    chamadas = []

    def _fake(comando, projeto, job=None):
        chamadas.append((comando, projeto, job))
        return {"exit_code": 0, "stdout": "senha: abc123\njob_name: X", "stderr": "", "duration_ms": 50}
    monkeypatch.setattr(af, "run_dsjob", _fake)
    r = await af.ferramenta_dsjob("lparams", "BI_CVP", "JobX", teto_sessoes=10, espera_max_s=5)
    assert chamadas == [("lparams", "BI_CVP", "JobX")]
    assert "abc123" not in r["saida_redigida"]
    assert "job_name: X" in r["saida_redigida"]


@pytest.mark.asyncio
async def test_semaforo_limita_concorrencia_e_espera_estoura(monkeypatch):
    """Com teto 1, a 2ª chamada simultânea espera; se o servidor 'nunca
    solta', a espera estoura como ServidorOcupado nomeado (não um timeout
    genérico)."""
    monkeypatch.setattr(af, "ssh_configured", lambda: True)
    liberar = asyncio.Event()

    def _lento(comando, projeto, job=None):
        # roda em thread (asyncio.to_thread) — bloqueia até liberar() ser
        # setado no loop principal.
        import time as _t
        while not liberar.is_set():
            _t.sleep(0.01)
        return {"exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 1}
    monkeypatch.setattr(af, "run_dsjob", _lento)
    af.SEMAFORO_SSH = af.SemaforoSsh()  # semáforo limpo para este teste

    tarefa1 = asyncio.create_task(
        af.ferramenta_dsjob("ljobs", "BI_CVP", None, teto_sessoes=1, espera_max_s=5))
    await asyncio.sleep(0.05)  # garante que a 1ª já pegou o semáforo

    with pytest.raises(af.ServidorOcupado):
        await af.ferramenta_dsjob("ljobs", "BI_CVP", None, teto_sessoes=1, espera_max_s=0.2)

    liberar.set()
    r1 = await tarefa1
    assert r1["exit_code"] == 0


@pytest.mark.asyncio
async def test_semaforo_libera_para_o_proximo_apos_terminar(monkeypatch):
    monkeypatch.setattr(af, "ssh_configured", lambda: True)
    monkeypatch.setattr(af, "run_dsjob",
                        lambda c, p, j=None: {"exit_code": 0, "stdout": "ok", "stderr": "", "duration_ms": 1})
    af.SEMAFORO_SSH = af.SemaforoSsh()
    r1 = await af.ferramenta_dsjob("ljobs", "BI_CVP", None, teto_sessoes=1, espera_max_s=2)
    r2 = await af.ferramenta_dsjob("ljobs", "BI_CVP", None, teto_sessoes=1, espera_max_s=2)
    assert r1["exit_code"] == 0 and r2["exit_code"] == 0
