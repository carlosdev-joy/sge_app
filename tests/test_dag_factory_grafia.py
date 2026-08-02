"""
Grafia divergente entre tabelas + isolamento de pendentes na factory.

Incidente (produção, 2026-08-01): o pipeline 'SEQSSDVIDA6SINISTRO' foi
cadastrado em MAIÚSCULAS em dbo.etl_pipeline, mas as 6 etapas datastage vieram
do import .dsx como 'SeqSsdVida6Sinistro' (CamelCase). A colação CI do SQL
Server junta tudo; os dicts do Python, não — o agrupamento por nome cru fazia o
pipeline "perder" as etapas ("pipeline sem nenhuma etapa — nada a gerar") e,
como a sp_etl_pipelines_pendentes_criar é GLOBAL, o pendente quebrado reprovava
TODO run — inclusive o clique num pipeline saudável.

Três defesas testadas aqui:
  1. agrupamento pipeline↔etapas com chave normalizada (_chave_ci);
  2. em run de pipeline específico, pendência de TERCEIRO vira step 'aviso' e o
     loop segue (a intenção da PR #234 — falha visível — fica preservada para o
     pipeline SOLICITADO e para runs globais);
  3. dependência inexistente falha CLARO na geração (ValueError), e dependência
     existente com caixa divergente resolve para a grafia REAL da etapa (o
     _varname não normaliza caixa — referência com a grafia da dep seria
     NameError no import do Airflow).

Mesmo princípio dos demais testes de factory: módulos do Airflow stubados via
sys.modules antes do import; _generate_dag_source é função pura. Para o
gerar_dags completo, hook/cursor falsos devolvem os result sets da SP.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.operators.empty", "airflow.datasets", "airflow.utils",
    "airflow.utils.trigger_rule", "airflow.utils.state",
    "airflow.providers", "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum", "requests", "httpx",
]
for _mod in _AIRFLOW_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def factory():
    path = _ROOT / "dags/etl_dag_factory.py"
    spec = importlib.util.spec_from_file_location("etl_dag_factory_grafia_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pipeline(**overrides):
    base = {
        "pipeline_name": "PIPE", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "ambiente": "PROD", "schedule_type": "daily",
    }
    base.update(overrides)
    return base


def _job(name, jtype="datastage", order=1, depends=None):
    j = {"job_name": name, "job_type": jtype, "job_command": "ds.job",
         "execution_order": order}
    if depends is not None:
        j["depends_on_jobs"] = depends
    return j


def _exec_source(src):
    """Importa DE FATO a DAG gerada — pega NameError de tempo de carga (o que o
    Airflow faria ao importar o .py). Stuba ``utils.*`` SÓ durante o exec."""
    util_mods = ("utils", "utils.datastage_operator", "utils.conditions", "utils.job_operators")
    saved = {m: sys.modules.get(m) for m in util_mods}
    try:
        for m in util_mods:
            sys.modules[m] = MagicMock()
        exec(compile(src, "<dag>", "exec"), {})
    finally:
        for m, prev in saved.items():
            if prev is None:
                sys.modules.pop(m, None)
            else:
                sys.modules[m] = prev


# ───────────────── Infra falsa para o gerar_dags completo ───────────────────
# A SP devolve 2+ result sets (pipelines, etapas, [params]); as consultas de
# INFORMATION_SCHEMA respondem 0 (suplementos degradam, como num banco antigo)
# e o SELECT avançado de etl_pipeline devolve vazio (adv_map = {}).

_PIPE_COLS = ["pipeline_name", "project_name", "domain", "tags", "scheduled_time",
              "envia_msg_inicio", "envia_msg_fim", "envia_msg_erro"]
_JOB_COLS = ["pipeline_name", "job_name", "job_type", "job_command", "execution_order"]
_ADV_COLS = ["pipeline_name", "criticidade", "sla_minutos", "ambiente",
             "max_active_runs", "retries_count", "retry_delay_seconds",
             "pool_name", "descricao", "dag_start_date", "runbook_md"]
_PARAM_COLS = ["pipeline_name", "job_name", "param_name", "param_type",
               "param_value", "param_order"]


class _FakeCursor:
    def __init__(self, pipe_rows, job_rows, param_rows=None):
        self._pipe_rows, self._job_rows = pipe_rows, job_rows
        self._param_rows = param_rows
        self.sqls = []
        self._sets = []          # fila de result sets pendentes: (cols, rows)
        self.description = None
        self._rows = []

    def execute(self, sql, params=None):
        self.sqls.append(" ".join(str(sql).split()))
        s = self.sqls[-1]
        if "sp_etl_pipelines_pendentes_criar" in s:
            self._sets = [(_PIPE_COLS, self._pipe_rows), (_JOB_COLS, self._job_rows)]
            if self._param_rows is not None:
                self._sets.append((_PARAM_COLS, self._param_rows))
            self._pop_set()
        elif "INFORMATION_SCHEMA.COLUMNS" in s:
            self._sets, self.description, self._rows = [], [("c",)], [(0,)]
        elif "FROM dbo.etl_pipeline WHERE pipeline_name IN" in s:
            self._sets, self.description, self._rows = [], [(c,) for c in _ADV_COLS], []
        else:   # UPDATEs de dag_criada etc.
            self._sets, self.description, self._rows = [], None, []

    def _pop_set(self):
        cols, rows = self._sets.pop(0)
        self.description = [(c,) for c in cols]
        self._rows = list(rows)

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def fetchone(self):
        return self._rows[0] if self._rows else (0,)

    def nextset(self):
        if self._sets:
            self._pop_set()
            return True
        return False

    def close(self):
        pass


class _FakeHook:
    def __init__(self, cursor):
        self._cursor = cursor
        self.runs = []           # (sql, parameters) de cada hook.run

    def get_conn(self):
        cur = self._cursor
        return SimpleNamespace(cursor=lambda: cur, commit=lambda: None, close=lambda: None)

    def run(self, sql, parameters=None, **_kw):
        self.runs.append((" ".join(str(sql).split()), parameters))


def _run_factory(factory, monkeypatch, tmp_path, pipe_rows, job_rows, conf,
                 param_rows=None):
    cur = _FakeCursor(pipe_rows, job_rows, param_rows)
    hook = _FakeHook(cur)
    monkeypatch.setattr(factory, "MsSqlHook", lambda **_kw: hook)
    monkeypatch.setattr(factory, "_get_output_root", lambda: str(tmp_path))
    ctx = {"dag_run": SimpleNamespace(conf=conf, run_id="grafia_test_run")}
    factory.gerar_dags(**ctx)
    return hook


def _preparar_factory(factory, monkeypatch, tmp_path, pipe_rows, job_rows, conf):
    """Variante para casos que ESPERAM exceção: devolve (hook, chamada) para o
    teste embrulhar a chamada em pytest.raises e ainda inspecionar o log."""
    cur = _FakeCursor(pipe_rows, job_rows)
    hook = _FakeHook(cur)
    monkeypatch.setattr(factory, "MsSqlHook", lambda **_kw: hook)
    monkeypatch.setattr(factory, "_get_output_root", lambda: str(tmp_path))
    ctx = {"dag_run": SimpleNamespace(conf=conf, run_id="grafia_test_run")}
    return hook, (lambda: factory.gerar_dags(**ctx))


def _ultimo_log(hook):
    """Estado final + detalhes_json do último MERGE em etl_factory_log."""
    merges = [(s, p) for s, p in hook.runs if "etl_factory_log" in s]
    _, params = merges[-1]
    return params[1], json.loads(params[5])   # (estado, {"steps":…, "erros":…})


# ── (a) grafia divergente em caixa+espaço não perde as etapas ───────────────

def test_pipeline_maiusculo_encontra_etapas_camelcase(factory, monkeypatch, tmp_path):
    """O incidente: cadastro 'PIPE' × etapas do .dsx como 'Pipe ' (CamelCase e
    espaço à direita — que a colação CI do banco também ignora)."""
    hook = _run_factory(
        factory, monkeypatch, tmp_path,
        pipe_rows=[("PIPE", "BI_CVP", "T", "ETL", "06:00:00", 0, 0, 1)],
        job_rows=[("Pipe ", "JobA", "datastage", "ds.job", 1)],
        conf={},
    )
    estado, detalhes = _ultimo_log(hook)
    assert estado == "SUCCESS"
    assert detalhes["erros"] == []
    assert not any("sem nenhuma etapa" in s["msg"] for s in detalhes["steps"])

    dest = tmp_path / "generated" / "BI_CVP" / "T" / "PIPE.py"
    assert dest.exists(), "a DAG do pipeline tem que ser gravada"
    ast.parse(dest.read_text(encoding="utf-8"))


# ── (b) pendência de terceiro não derruba o run de pipeline específico ──────

def test_pendente_vazio_de_terceiro_vira_aviso(factory, monkeypatch, tmp_path):
    """A SP é global: o clique em BOM também traz o pendente VAZIO (quebrado).
    O run tem que gerar BOM, avisar sobre VAZIO e terminar SUCCESS."""
    hook = _run_factory(
        factory, monkeypatch, tmp_path,
        pipe_rows=[
            ("VAZIO", "BI_CVP", "T", "ETL", "06:00:00", 0, 0, 1),  # antes de BOM de propósito
            ("BOM",   "BI_CVP", "T", "ETL", "06:00:00", 0, 0, 1),
        ],
        job_rows=[("BOM", "JobA", "datastage", "ds.job", 1)],
        conf={"pipeline_name": "BOM"},
    )
    estado, detalhes = _ultimo_log(hook)
    assert estado == "SUCCESS"
    assert detalhes["erros"] == [], "pendência de terceiro não pode virar erro"

    avisos = [s for s in detalhes["steps"] if s["tipo"] == "aviso"]
    assert len(avisos) == 1
    assert "VAZIO" in avisos[0]["msg"]
    assert avisos[0]["msg"].endswith("— pendência de outro pipeline, ignorada nesta execução")

    assert (tmp_path / "generated" / "BI_CVP" / "T" / "BOM.py").exists()


# ── (c) pendente vazio É o solicitado → erro (guarda da intenção da #234) ───

def test_pendente_vazio_solicitado_continua_erro(factory, monkeypatch, tmp_path):
    """Comparação com o alvo é case-insensitive: o clique veio como 'vazio' e o
    cadastro é 'VAZIO' — é o MESMO pipeline, então o erro é dele e reprova."""
    with pytest.raises(factory._ErrosPorPipeline) as exc:
        _run_factory(
            factory, monkeypatch, tmp_path,
            pipe_rows=[("VAZIO", "BI_CVP", "T", "ETL", "06:00:00", 0, 0, 1)],
            job_rows=[],
            conf={"pipeline_name": "vazio"},
        )
    assert "sem nenhuma etapa" in str(exc.value)


def test_run_global_mantem_tudo_como_erro(factory, monkeypatch, tmp_path):
    """Sem pipeline_name no conf não existe 'terceiro': o pendente vazio segue
    reprovando o run — comportamento atual dos runs globais/force_all."""
    with pytest.raises(factory._ErrosPorPipeline):
        _run_factory(
            factory, monkeypatch, tmp_path,
            pipe_rows=[
                ("VAZIO", "BI_CVP", "T", "ETL", "06:00:00", 0, 0, 1),
                ("BOM",   "BI_CVP", "T", "ETL", "06:00:00", 0, 0, 1),
            ],
            job_rows=[("BOM", "JobA", "datastage", "ds.job", 1)],
            conf={},
        )


# ── (d) dependência inexistente falha claro na geração ──────────────────────

def test_dep_inexistente_levanta_valueerror(factory):
    """Antes, a dep fantasma era descartada em silêncio (a etapa virava raiz);
    agora nomeia o job e a dependência num ValueError da geração."""
    jobs = [_job("JobA"), _job("JobB", order=2, depends="JobX")]
    with pytest.raises(ValueError) as exc:
        factory._generate_dag_source(_pipeline(), jobs)
    msg = str(exc.value)
    assert "JobB" in msg and "JobX" in msg
    assert "não existe" in msg


# ── (e) dep existente com caixa divergente resolve para a grafia real ───────

def test_dep_caixa_divergente_gera_referencia_correta(factory):
    """_varname não normaliza caixa: se a dep 'joba' fosse usada como veio,
    sairia t_end_joba — NameError no import do Airflow. A dep tem que ser
    resolvida para a grafia REAL da etapa ('JobA')."""
    jobs = [_job("JobA"), _job("JobB", order=2, depends="joba")]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "t_end_JobA >> t_start_JobB" in src
    assert "t_end_joba" not in src


def test_dep_caixa_divergente_para_no_especial(factory):
    """A resolução também vale para os nós especiais: _end_ref decide entre
    t_end_/t_wait_/t_dec_/… por lookup case-sensitive em dicts — a dep
    'ENCONTRO' só encontra o Aguarde 'Encontro' com a grafia real."""
    jobs = [
        _job("JobA"), _job("JobB"),
        _job("Encontro", jtype="aguarde", order=2, depends="joba, JOBB"),
        _job("Limpa", jtype="shell", order=3, depends="ENCONTRO"),
    ]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "[t_end_JobA, t_end_JobB] >> t_wait_Encontro" in src
    assert "t_wait_Encontro >> t_start_Limpa" in src


def test_dep_com_grafia_exata_nao_muda(factory):
    """Não-regressão: pipeline com deps já corretas gera exatamente as mesmas
    referências de antes."""
    jobs = [_job("JobA"), _job("JobB", order=2, depends="JobA")]
    src = factory._generate_dag_source(_pipeline(), jobs)
    ast.parse(src)
    _exec_source(src)
    assert "t_end_JobA >> t_start_JobB" in src


# ── (f) params com grafia divergente do job não se perdem (revisão) ─────────

def test_params_grafia_divergente_nao_se_perdem(factory, monkeypatch, tmp_path):
    """etl_pipeline_job_param × etl_pipeline_job são tabelas DIFERENTES: params
    gravados como 'PIPE' têm que chegar ao job gravado como 'Pipe' — sem a
    chave CI a procedure rodaria SEM os parâmetros fixos, em silêncio."""
    hook = _run_factory(
        factory, monkeypatch, tmp_path,
        pipe_rows=[("PIPE", "BI_CVP", "T", "ETL", "06:00:00", 0, 0, 1)],
        job_rows=[("Pipe", "JobP", "storedproc", "dbo.sp_carga", 1)],
        conf={},
        param_rows=[("PIPE", "JobP", "ParamX", "VARCHAR", "abc", 1)],
    )
    estado, detalhes = _ultimo_log(hook)
    assert estado == "SUCCESS" and detalhes["erros"] == []
    src = (tmp_path / "generated" / "BI_CVP" / "T" / "PIPE.py").read_text(encoding="utf-8")
    assert "ParamX" in src, "o parâmetro fixo tem que entrar na DAG gerada"


# ── (g) alvo fora do lote reprova o run (revisão) ───────────────────────────

def test_alvo_fora_do_lote_reprova(factory, monkeypatch, tmp_path):
    """Corrida clique×inativação (ou typo em trigger manual): sem a checagem, o
    run demoveria tudo a aviso e fecharia verde sem citar o pipeline pedido."""
    hook, chamar = _preparar_factory(
        factory, monkeypatch, tmp_path,
        pipe_rows=[("OUTRO", "BI_CVP", "T", "ETL", "06:00:00", 0, 0, 1)],
        job_rows=[("OUTRO", "JobA", "datastage", "ds.job", 1)],
        conf={"pipeline_name": "FANTASMA"},
    )
    with pytest.raises(factory._ErrosPorPipeline):
        chamar()
    estado, detalhes = _ultimo_log(hook)
    assert estado == "FAILED"
    assert any("FANTASMA" in e and "não entrou na geração" in e
               for e in detalhes["erros"])
    # o terceiro saudável ainda foi gerado (catch-up preservado)
    assert (tmp_path / "generated" / "BI_CVP" / "T" / "OUTRO.py").exists()


def test_lote_vazio_com_alvo_reprova(factory, monkeypatch, tmp_path):
    """Variante: a SP não devolve NADA (alvo inativo/inexistente). Com alvo no
    conf, o SUCCESS 'vazio' de antes era um verde mentiroso."""
    hook, chamar = _preparar_factory(
        factory, monkeypatch, tmp_path,
        pipe_rows=[], job_rows=[], conf={"pipeline_name": "X"},
    )
    with pytest.raises(factory._ErrosPorPipeline):
        chamar()
    estado, detalhes = _ultimo_log(hook)
    assert estado == "FAILED"
    assert any("não entrou na geração" in e for e in detalhes["erros"])


def test_lote_vazio_sem_alvo_segue_vazio_benigno(factory, monkeypatch, tmp_path):
    """Não-regressão: run global com nada pendente continua SUCCESS + step
    'vazio', como sempre foi."""
    hook = _run_factory(
        factory, monkeypatch, tmp_path, pipe_rows=[], job_rows=[], conf={},
    )
    estado, detalhes = _ultimo_log(hook)
    assert estado == "SUCCESS"
    assert any(s["tipo"] == "vazio" for s in detalhes["steps"])
