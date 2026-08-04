"""
F4 da spec de operação no nível de etapa (docs/spec-operacao-nivel-etapa.md):
rerun a partir da etapa, com escolha de cascata e tentativas acumuladas.

Cobre as duas decisões JÁ TOMADAS pelo usuário no §7:

  • **decisão 1 — cascata: SEMPRE PERGUNTAR.** O gesto nunca decide sozinho:
    `cascata` é campo do corpo, default False; a prévia mostra o fecho a
    jusante separado entre quem será reaberto e quem não tem corrida a
    reabrir; e a identidade AMBÍGUA é RECUSADA (409) em vez de escolhida.
  • **decisão 2 — tentativas: ACUMULAR.** A tentativa superada vai para
    `etl_job_execution_tentativa`; o drill-down mostra a MAIS RECENTE com as
    anteriores junto; e `etl_job_execution` continua com UMA linha por etapa,
    que é o que preserva os ~17 agregados de produção mapeados.

Mais a NÃO-REGRESSÃO do que já existia: o corpo do clearTaskInstances e o
caminho histórico de Logs/Dashboard (`execution_id` sem `data_referencia`).

Dublês locais; nada toca rede nem banco.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EXECUTAR, get_current_user
from services import execucao_identidade as ident
from services import rerun as rr

_ROOT = Path(__file__).parent.parent
_D = date(2026, 8, 3)


@pytest.fixture(autouse=True)
def _dags_do_repo(monkeypatch):
    """`DAGS_FOLDER` apontando para o `dags/` DESTE repo — o que a API vê em
    produção (bind mount read-only do compose).

    Autouse porque a sonda de capacidade do deploy parcial passou a ser parte
    do caminho da cascata: sem a variável, a suíte rodaria contra
    `/opt/airflow/dags`, que não existe na máquina de teste, e TODA cascata
    apareceria indisponível — mascarando o que os testes querem ver. Com ela,
    a sonda lê o módulo do motor de verdade: se alguém tirar a cláusula de
    corrida substituída e a declaração `CAPACIDADES` junto, estes testes caem.
    """
    monkeypatch.setenv("DAGS_FOLDER", str(_ROOT / "dags"))
    rr._cache_capacidade.clear()
    yield
    rr._cache_capacidade.clear()


# ═══════════════════════════════════════════════════════════════════════════
# 1. TENTATIVAS ACUMULADAS — a leitura (decisão 2)
# ═══════════════════════════════════════════════════════════════════════════

def _exec(job, *, attempt=1, status="SUCCESS", inicio="2026-08-03 09:00:00"):
    return {"job_name": job, "task_id": job, "attempt": attempt,
            "status": status, "inicio": inicio, "fim": None,
            "duration_seconds": 10, "status_code": None,
            "log_file": None, "host": "w1"}


def _hist(job, attempt, status, inicio):
    return {"job_name": job, "task_id": job, "attempt": attempt,
            "status": status, "inicio": inicio, "fim": inicio,
            "duration_seconds": 5, "status_code": None, "log_file": None,
            "host": "w1", "arquivado_em": None}


def _no(job, **kw):
    base = {"job_name": job, "job_type": "http", "execution_order": 1,
            "depends_on_jobs": []}
    base.update(kw)
    return base


def test_etapa_mostra_a_tentativa_mais_recente_com_as_anteriores():
    """Decisão 2: 'o drill-down mostra a linha do tempo real do dia'.

    A etapa exibe a tentativa CORRENTE (2, SUCCESS) e carrega a anterior
    (1, FAILED) — a linha do tempo inteira, sem esconder a falha."""
    etapas = ident.compor_etapas(
        [_no("http_saude")],
        [_exec("http_saude", attempt=2, status="SUCCESS", inicio="2026-08-03 11:03:00")],
        [_hist("http_saude", 1, "FAILED", "2026-08-03 10:12:00")])
    assert len(etapas) == 1
    e = etapas[0]
    assert e["attempt"] == 2 and e["status"] == "SUCCESS"
    assert e["total_tentativas"] == 2
    assert [t["attempt"] for t in e["tentativas"]] == [1]
    assert e["tentativas"][0]["status"] == "FAILED"


def test_com_duas_linhas_correntes_vence_a_de_maior_attempt():
    """O defeito que a F2 registrou: `setdefault` fazia vencer a linha MAIS
    ANTIGA. Com tentativas numeradas isso mostraria a que falhou depois de o
    operador já ter reexecutado e passado — a pior mentira desta tela.

    A ordem de chegada é propositalmente a errada (a antiga primeiro), como
    `ORDER BY start_time` entrega."""
    etapas = ident.compor_etapas(
        [_no("j")],
        [_exec("j", attempt=1, status="FAILED", inicio="2026-08-03 10:00:00"),
         _exec("j", attempt=2, status="SUCCESS", inicio="2026-08-03 11:00:00")],
        [])
    assert etapas[0]["attempt"] == 2
    assert etapas[0]["status"] == "SUCCESS"


def test_attempt_nulo_perde_de_tentativa_numerada():
    """Dado pré-078 (attempt NULL) convive com dado novo: a linha que se
    declara tentativa 2 vence a que não se declara nada."""
    etapas = ident.compor_etapas(
        [_no("j")],
        [_exec("j", attempt=2, status="SUCCESS", inicio="2026-08-03 09:00:00"),
         _exec("j", attempt=None, status="FAILED", inicio="2026-08-03 23:00:00")],
        [])
    assert etapas[0]["attempt"] == 2 and etapas[0]["status"] == "SUCCESS"


def test_sem_tentativa_anterior_o_payload_e_o_da_f3_mais_lista_vazia():
    e = ident.compor_etapas([_no("j")], [_exec("j")], [])[0]
    assert e["tentativas"] == [] and e["total_tentativas"] == 1


def test_etapa_sem_execucao_continua_neutra_e_sem_tentativas():
    """Regra de honestidade do §3 preservada: ausência de linha não é sucesso
    — e também não inventa tentativa."""
    e = ident.compor_etapas([_no("j")], [], [])[0]
    assert e["status"] is None and e["sem_execucao"] is True
    assert e["tentativas"] == [] and e["total_tentativas"] == 0


def test_etapa_fora_do_desenho_tambem_ganha_a_linha_do_tempo():
    """Etapa que rodou e saiu do desenho continua aparecendo (F2) — e agora
    com as tentativas dela."""
    etapas = ident.compor_etapas(
        [], [_exec("velha", attempt=2)], [_hist("velha", 1, "FAILED", "2026-08-03 08:00:00")])
    assert etapas[0]["no_desenho"] is False
    assert [t["attempt"] for t in etapas[0]["tentativas"]] == [1]


class _CurTent:
    """Cursor mínimo para `tentativas_anteriores`."""

    def __init__(self, *, tem_tabela=True, linhas=(), erro=None):
        self.tem_tabela = tem_tabela
        self.linhas = list(linhas)
        self.erro = erro
        self._rows = []

    def execute(self, sql, params=()):
        s = " ".join(str(sql).split())
        if s.startswith("SELECT OBJECT_ID('dbo.etl_job_execution_tentativa'"):
            self._rows = [(1 if self.tem_tabela else None,)]
            return
        if self.erro:
            raise self.erro
        self._rows = list(self.linhas)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


def test_tentativas_anteriores_degrada_sem_a_078():
    """Deploy parcial (078 pendente): devolve [] em vez de estourar 'Invalid
    object name' — o drill-down não pode quebrar por causa disso."""
    assert ident.tentativas_anteriores(_CurTent(tem_tabela=False), "P", "TS") == []


def test_tentativas_anteriores_engole_erro_de_consulta():
    cur = _CurTent(erro=RuntimeError("timeout"))
    assert ident.tentativas_anteriores(cur, "P", "TS") == []


def test_tentativas_anteriores_mapeia_as_colunas_na_ordem():
    cur = _CurTent(linhas=[("j", "j", 1, "FAILED", "i", "f", 7, 3, "log", "w1", "a")])
    t = ident.tentativas_anteriores(cur, "P", "TS")[0]
    assert (t["job_name"], t["attempt"], t["status"], t["duration_seconds"],
            t["status_code"], t["host"]) == ("j", 1, "FAILED", 7, 3, "w1")


# ═══════════════════════════════════════════════════════════════════════════
# 2. TENTATIVAS ACUMULADAS — a migration e a SP (decisão 2)
# ═══════════════════════════════════════════════════════════════════════════

def _sql_078():
    return (_ROOT / "sql/migrations/078_tentativas_acumuladas.sql").read_text(
        encoding="utf-8")


def test_078_e_idempotente_por_construcao():
    """Sem SQL Server no CI, a idempotência é garantida POR CONSTRUÇÃO: toda
    criação está atrás de uma guarda de existência, e o ALTER de coluna atrás
    de COL_LENGTH IS NULL."""
    sql = _sql_078()
    assert "IF OBJECT_ID('dbo.etl_job_execution_tentativa', 'U') IS NULL" in sql
    assert "IF COL_LENGTH('dbo.etl_pipeline_execucao', 'substituida_em') IS NULL" in sql
    assert "IF COL_LENGTH('dbo.etl_pipeline_execucao', 'substituida_por') IS NULL" in sql
    assert "CREATE OR ALTER PROCEDURE" in sql
    assert "WHERE attempt IS NULL" in sql          # backfill só do que falta


def test_078_nao_mexe_na_pk_de_etl_job_execution():
    """A decisão de desenho da fase: `etl_job_execution` continua com UMA
    linha por (execution_id, pipeline, job_name, task_id).

    Mexer na PK dela quebraria os agregados de produção mapeados (status_geral
    grudado em FALHA, COUNT/SUM inflados, MIN(start_time) da 1ª tentativa) —
    inclusive o SQL congelado dentro de DAGs já publicadas. Este teste é a
    trava contra alguém "consertar" isso sem reler o cabeçalho da migration."""
    sql = _sql_078()
    assert "DROP CONSTRAINT PK_etl_job_execution" not in sql
    assert "ADD CONSTRAINT PK_etl_job_execution" not in sql


def test_078_arquiva_so_tentativa_terminada_e_de_forma_idempotente():
    """As duas guardas que impedem tentativa FANTASMA e duplicata:

      • só é tentativa nova se a linha viva JÁ chegou ao fim — um retry do
        próprio `log_start` não inventa tentativa;
      • o INSERT no histórico é `WHERE NOT EXISTS` sobre a PK — morrer entre o
        arquivamento e o incremento não duplica na repetição."""
    sql = _sql_078()
    assert "end_time IS NOT NULL OR status <> ''RUNNING''" in sql
    assert "NOT EXISTS" in sql and "etl_job_execution_tentativa t" in sql
    # tentativa nova não herda o resultado da anterior
    assert "status_code = CASE WHEN @nova_tentativa = 1 THEN NULL" in sql


def test_078_mantem_a_assinatura_de_11_parametros_da_sp():
    """A assinatura NÃO muda: as DAGs já publicadas chamam a SP com esses 11
    parâmetros como texto gerado, e a acumulação vale para elas SEM regerar
    DAG nenhuma."""
    sql = _sql_078()
    for p in ("@execution_id", "@project", "@job_name", "@pipeline", "@host",
              "@start_time", "@end_time", "@duration_seconds", "@status",
              "@log_file", "@task_id"):
        assert f" {p} " in sql or f"\n {p} " in sql
    assert "@attempt" not in sql.split("CREATE OR ALTER PROCEDURE")[1].split("AS")[0]


def test_078_guarda_a_ausencia_da_tabela_de_historico_na_sp():
    """Deploy parcial ao contrário (SP nova, tabela ausente): a SP se comporta
    como a v2 em vez de derrubar a telemetria de todo pipeline."""
    assert "OBJECT_ID(''dbo.etl_job_execution_tentativa'', ''U'') IS NOT NULL" in _sql_078()


# ═══════════════════════════════════════════════════════════════════════════
# 3. O CORPO DO CLEAR — não-regressão
# ═══════════════════════════════════════════════════════════════════════════

def test_corpo_do_clear():
    """As guardas que já existiam (`dag_run_id` obrigatório, downstream sim,
    upstream/past/future não, reset_dag_runs) MAIS o `only_failed: False`."""
    assert rr.corpo_clear("run_1", "etapa_x") == {
        "dry_run": False,
        "dag_run_id": "run_1",
        "task_ids": ["etapa_x"],
        "include_downstream": True,
        "include_future": False,
        "include_past": False,
        "include_upstream": False,
        "only_failed": False,
        "reset_dag_runs": True,
    }


def test_clear_manda_only_failed_false():
    """DEFEITO ANTIGO ENCONTRADO NA PROVA VIVA: `only_failed` tem default TRUE
    no Airflow e o rerun nunca o enviava — então o clear "a partir desta
    etapa" PULAVA a etapa escolhida sempre que ela não estivesse falha.

    Medido no dev com dry_run real: `task_ids=[http_saude]` em estado SUCCESS
    devolvia uma lista SEM `http_saude`. É o que tornava impossível o
    requisito (b) do §4 ("não depender de FAILED"), e também o que impedia o
    `log_start_<etapa>` (sempre SUCCESS) de ser limpo — logo, o que impedia a
    tentativa de ser contada.

    Este assert é a trava: some com ele e a fase inteira volta a ser mentira
    silenciosa."""
    assert rr.corpo_clear("run_1", "etapa_x")["only_failed"] is False


def test_previa_usa_o_mesmo_corpo_so_mudando_dry_run():
    """O que o modal prometeu é o que é executado: um corpo, dois usos."""
    a = rr.corpo_clear("run_1", "etapa_x", dry_run=True, task_ids=["log_start_etapa_x", "etapa_x"])
    b = rr.corpo_clear("run_1", "etapa_x", task_ids=["log_start_etapa_x", "etapa_x"])
    assert a.pop("dry_run") is True and b.pop("dry_run") is False
    assert a == b


def test_clear_inclui_o_marcador_de_inicio_da_etapa():
    """DEFEITO ANTIGO ENCONTRADO NA PROVA VIVA: `log_start_<etapa>` é UPSTREAM
    da etapa, então `include_downstream` NUNCA o alcança. Medido no dev com
    execução real — a etapa retomada ficava com o `start_time` da tentativa
    anterior (89s reportados para ~10s de execução) e a tentativa jamais era
    contada, porque quem decide "houve tentativa nova" é o log_start."""
    tasks = ["check_agenda", "log_start_etapa_x", "etapa_x", "log_end_etapa_x",
             "publish_dataset"]
    assert rr.task_ids_do_clear("etapa_x", tasks) == ["log_start_etapa_x", "etapa_x"]


def test_clear_sem_marcador_mantem_o_comportamento_historico():
    """Task que não é etapa (ou DAG de shape antigo, ou lista indisponível):
    a lista volta a ser só a task — byte a byte o de antes desta fase."""
    assert rr.task_ids_do_clear("publish_dataset",
                                ["publish_dataset", "check_agenda"]) == ["publish_dataset"]
    assert rr.task_ids_do_clear("etapa_x", []) == ["etapa_x"]
    assert rr.task_ids_do_clear("etapa_x", None) == ["etapa_x"]


def test_etapas_do_clear_separa_etapas_de_tasks_de_apoio():
    """O Airflow devolve TASKS; o operador raciocina em ETAPAS. As de apoio
    (log_start/log_end/publish_dataset) não somem — some seria esconder que o
    publish_dataset roda de novo, e é ele quem faz o push da cascata."""
    tis = [{"task_id": "log_start_a"}, {"task_id": "a"}, {"task_id": "log_end_a"},
           {"task_id": "B"}, {"task_id": "publish_dataset"}]
    out = rr.etapas_do_clear(tis, [_no("a"), _no("b")])
    assert out["etapas"] == ["a", "b"]        # casefold: 'B' casa com o nó 'b'
    assert out["tasks_de_apoio"] == 3
    assert out["total_tasks"] == 5


def test_etapas_do_clear_devolve_a_grafia_do_desenho():
    """Colação CI do banco × dict case-sensitive do Python (PR #236): a tela
    mostra a grafia do DESENHO, não a do task_id."""
    out = rr.etapas_do_clear([{"task_id": "ETAPA_X"}], [_no("Etapa_X")])
    assert out["etapas"] == ["Etapa_X"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. CASCATA — o fecho a jusante (decisão 1)
# ═══════════════════════════════════════════════════════════════════════════

class _CurGrafo:
    """Cursor de grafo: responde `dependentes_diretos`, `corridas_do_dia`,
    a checagem da coluna da 078 e grava os UPDATEs/INSERTs executados."""

    def __init__(self, grafo, *, corridas=None, tem_078=True):
        self.grafo = {k.casefold(): list(v) for k, v in grafo.items()}
        self.corridas = corridas or {}
        self.tem_078 = tem_078
        self.execs = []
        self.rowcount = 0
        self._rows = []

    def execute(self, sql, params=()):
        s = " ".join(str(sql).split())
        self.execs.append((s, params))
        self._rows = []
        self.rowcount = 0
        if s.startswith("SELECT COL_LENGTH('dbo.etl_pipeline_execucao', 'substituida_em')"):
            self._rows = [(8 if self.tem_078 else None,)]
            return
        if s.startswith("SELECT d.pipeline_name FROM dbo.etl_pipeline_dependencia"):
            self._rows = [(f,) for f in self.grafo.get(str(params[0]).casefold(), [])]
            return
        if s.startswith("SELECT execution_id, status, inicio, fim, disparado_por"):
            linhas = self.corridas.get(str(params[0]).casefold(), [])
            self._rows = [(c["run_id"], c["status"], c.get("inicio"),
                           c.get("fim"), c.get("disparado_por"), None)
                          for c in linhas]
            return
        if s.startswith("UPDATE dbo.etl_pipeline_execucao"):
            self.rowcount = 1
            return
        if s.startswith("INSERT INTO dbo.etl_pipeline_audit"):
            self.rowcount = 1
            return
        raise AssertionError(f"SQL não previsto no dublê: {s[:140]}")

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


def test_fecho_e_transitivo_e_em_largura():
    """Cascata é o fecho a jusante, não só os filhos diretos: se A→C→E,
    reabrir só C faria a corrida nova de C travar em E pelo mesmo claim, e E
    ficaria com dado velho — o segundo erro que a decisão 1 proíbe.
    Ordem BFS porque é a ordem em que a cascata realmente acontece."""
    cur = _CurGrafo({"A": ["C", "D"], "C": ["E"], "D": [], "E": []})
    deps, truncado = rr.fecho_dependentes(cur, "A")
    assert deps == ["C", "D", "E"] and truncado is False


def test_a_raiz_nao_entra_no_fecho():
    cur = _CurGrafo({"A": ["C"], "C": []})
    deps, _ = rr.fecho_dependentes(cur, "A")
    assert "A" not in deps


def test_ciclo_nao_gira_para_sempre():
    """O cadastro de dependências não impede A→B→A."""
    cur = _CurGrafo({"A": ["B"], "B": ["A", "C"], "C": ["B"]})
    deps, truncado = rr.fecho_dependentes(cur, "A")
    assert deps == ["B", "C"] and truncado is False


def test_fecho_respeita_o_teto_e_declara_o_truncamento(monkeypatch):
    """Estourar o teto NÃO vira silêncio: `truncado=True` sobe para a tela."""
    monkeypatch.setattr(rr, "MAX_FECHO", 2)
    cur = _CurGrafo({"A": ["B", "C", "D"], "B": [], "C": [], "D": []})
    deps, truncado = rr.fecho_dependentes(cur, "A")
    assert len(deps) == 2 and truncado is True


def test_grafo_indisponivel_propaga_em_vez_de_virar_sem_dependentes():
    """Erro de consulta nunca pode virar 'não há dependentes' — seria dizer ao
    operador que ninguém é afetado (D21 aplicado à cascata)."""
    class _Quebra(_CurGrafo):
        def execute(self, sql, params=()):
            if "etl_pipeline_dependencia" in str(sql):
                raise RuntimeError("timeout")
            return super().execute(sql, params)
    with pytest.raises(RuntimeError):
        rr.fecho_dependentes(_Quebra({"A": ["C"]}), "A")


def test_afetados_separa_quem_tem_corrida_de_quem_nao_tem():
    """O modal não pode prometer o que não vai acontecer: reabrir pipeline que
    NÃO rodou no ODATE não faz nada (não há corrida a aposentar)."""
    cur = _CurGrafo(
        {"A": ["C", "D"], "C": [], "D": []},
        corridas={"c": [{"run_id": "r_c", "status": "SUCESSO"}]})
    info = rr.afetados(cur, "A", _D)
    assert info["dependentes"] == ["C", "D"]
    assert info["com_corrida"] == ["C"] and info["sem_corrida"] == ["D"]


def test_corrida_apenas_ORDENADA_nao_conta_como_reabrivel():
    """AGUARDANDO_DEPENDENCIA = ordenada e ainda não rodada: ela já vai rodar.
    O predicado do modal é o MESMO de `marcar_substituidas` — se divergissem,
    a promessa da tela e o efeito divergiriam."""
    cur = _CurGrafo(
        {"A": ["C"], "C": []},
        corridas={"c": [{"run_id": "r_c", "status": "AGUARDANDO_DEPENDENCIA"}]})
    info = rr.afetados(cur, "A", _D)
    assert info["com_corrida"] == [] and info["sem_corrida"] == ["C"]


def test_sem_a_078_a_cascata_se_declara_indisponivel():
    cur = _CurGrafo({"A": ["C"], "C": []}, tem_078=False)
    assert rr.afetados(cur, "A", _D)["cascata_indisponivel"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 5. CASCATA — a reabertura (decisão 1)
# ═══════════════════════════════════════════════════════════════════════════

def test_reabertura_nao_apaga_nem_reescreve_o_desfecho_da_corrida():
    """O caminho explícito: a corrida antiga é APOSENTADA, não destruída. Ela
    mantém status, horários e `disparado_por` — o histórico que a fase existe
    para preservar. Só ganha o carimbo de quem aposentou e quando."""
    cur = _CurGrafo({"A": ["C"], "C": []})
    n = rr.marcar_substituidas(cur, ["C"], _D, "DEV1")
    sql, params = [e for e in cur.execs if e[0].startswith("UPDATE")][0]
    assert n == 1
    assert "SET substituida_em = GETDATE()" in sql
    assert "status" not in sql.split("WHERE")[0].replace("substituida_em", "") \
        or "SET status" not in sql
    assert "DELETE" not in sql
    assert params[0] == "rerun:DEV1"


def test_reabertura_e_idempotente_e_ignora_corrida_ordenada():
    cur = _CurGrafo({"A": ["C"], "C": []})
    rr.marcar_substituidas(cur, ["C"], _D, "DEV1")
    sql, _ = [e for e in cur.execs if e[0].startswith("UPDATE")][0]
    assert "AND substituida_em IS NULL" in sql            # não re-carimba
    assert "AND status <> 'AGUARDANDO_DEPENDENCIA'" in sql


def test_sem_a_078_nada_e_reaberto():
    cur = _CurGrafo({"A": ["C"], "C": []}, tem_078=False)
    assert rr.marcar_substituidas(cur, ["C"], _D, "DEV1") == 0
    assert not [e for e in cur.execs if e[0].startswith("UPDATE")]


def test_claim_de_dags_ignora_corrida_substituida():
    """O outro lado do contrato: é o claim de dags/utils/dependencias.py que
    faz a cascata acontecer pelo caminho NORMAL do motor. Sem esta cláusula a
    reabertura não teria efeito nenhum.

    Lido do FONTE porque o módulo de dags/ não é importável a partir de api/
    (árvores de deploy separadas) — e o que importa aqui é o contrato entre as
    duas peças, não a execução."""
    fonte = (_ROOT / "dags/utils/dependencias.py").read_text(encoding="utf-8")
    claim = fonte.split("def reservar_corrida")[1].split("def ordenar_corrida")[0]
    assert "AND substituida_em IS NULL)" in claim          # caminho (b)
    assert "AND e.substituida_em IS NULL" in claim         # caminho (a)
    ordenar = fonte.split("def ordenar_corrida")[1].split("def devolver_reserva")[0]
    assert "AND substituida_em IS NULL)" in ordenar        # as duas portas concordam


def test_claim_tem_fallback_para_banco_sem_a_078():
    """Deploy parcial (dags/ novo, banco velho) não pode derrubar o push de
    TODO pipeline com dependente — e o fallback reage SÓ ao Invalid column
    name da coluna, nunca a um deadlock/timeout."""
    fonte = (_ROOT / "dags/utils/dependencias.py").read_text(encoding="utf-8")
    assert "_MARCA_078 = \"substituida_em\"" in fonte
    assert "if _MARCA_078 not in str(e):" in fonte and "raise" in fonte


# ═══════════════════════════════════════════════════════════════════════════
# 6. AUDITORIA
# ═══════════════════════════════════════════════════════════════════════════

def test_auditoria_grava_quem_quando_de_onde_e_com_que_alcance():
    cur = _CurGrafo({})
    ok = rr.registrar_auditoria(cur, "PIPE_A", "DEV1", {
        "dag_run_id": "run_1", "data_referencia": "2026-08-03",
        "task_id": "etapa_x", "cascata": True,
        "dependentes_reabertos": ["C", "D"], "corridas_substituidas": 2,
        "tasks_limpas": 7})
    sql, params = cur.execs[-1]
    assert ok is True
    assert sql.startswith("INSERT INTO dbo.etl_pipeline_audit")
    assert params[0] == "PIPE_A" and params[1] == "DEV1"
    assert params[2] == "rerun_etapa"
    assert "run_1" in params[3] and "2026-08-03" in params[3]
    assert '"cascata": true' in params[4] and '"etapa_x"' in params[4]
    assert '"C"' in params[4] and '"D"' in params[4]


def test_auditoria_nunca_derruba_o_gesto():
    """O clear JÁ aconteceu quando a auditoria roda: falhar em auditar não
    pode transformar um rerun feito em erro 500 para o operador."""
    class _Quebra(_CurGrafo):
        def execute(self, sql, params=()):
            raise RuntimeError("tabela ausente")
    assert rr.registrar_auditoria(_Quebra({}), "P", "U", {}) is False


# ═══════════════════════════════════════════════════════════════════════════
# 7. O ENDPOINT — permissão, recusa e as duas opções
# ═══════════════════════════════════════════════════════════════════════════

class _RespFake:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


class _ClientFake:
    """Cliente Airflow de mentira — grava cada POST feito.

    `is_paused=None` = o Airflow não respondeu a pergunta (o default, e o
    comportamento histórico do dublê): o gesto SEGUE, porque não saber não
    pode bloquear o rerun de Logs/Dashboard.
    """

    def __init__(self, *, task_instances=None, is_paused=None):
        self.posts = []
        self.task_instances = task_instances or [{"task_id": "etapa_x"}]
        self.is_paused = is_paused

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        if url.endswith("/dagRuns"):
            return _RespFake({"dag_runs": []})
        if url.endswith("/tasks"):
            return _RespFake({"tasks": [{"task_id": t} for t in ("etapa_x",)]})
        return _RespFake({"is_paused": self.is_paused})

    async def post(self, url, json=None):
        self.posts.append((url, json))
        return _RespFake({"task_instances": self.task_instances})


class _DbRerun:
    """Banco de mentira do endpoint: pipeline oficial, corridas do ODATE,
    grafo de dependência, desenho e as escritas do pós-clear."""

    def __init__(self, *, corridas=(), grafo=None, tem_078=True,
                 executando_rowcount=1):
        self.corridas = list(corridas)
        self.grafo = {k.casefold(): v for k, v in (grafo or {}).items()}
        self.tem_078 = tem_078
        # rowcount do carimbo de EXECUTANDO: 0 é o caso em que o
        # `execution_id` não casa com nenhuma linha — a marca que protege o
        # filho direto simplesmente não acontece.
        self.executando_rowcount = executando_rowcount
        self.escritas = []
        self._cur = None

    def cursor(self):
        self._cur = _CurRerun(self)
        return self._cur

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _CurRerun:
    def __init__(self, db):
        self.db = db
        self._rows = []
        self.rowcount = 0

    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        self._rows = []
        self.rowcount = 0
        if s.startswith("SELECT pipeline_name FROM dbo.etl_pipeline WHERE"):
            self._rows = [("DEV_F10_A",)]
            return
        if s.startswith("SELECT config_value FROM dbo.etl_app_config"):
            self._rows = [("00:00",)]
            return
        if s.startswith("SELECT OBJECT_ID('dbo.etl_pipeline_execucao'"):
            self._rows = [(1,)]
            return
        if s.startswith("SELECT OBJECT_ID('dbo.etl_pipeline_dependencia'"):
            self._rows = [(1,)]
            return
        if s.startswith("SELECT COL_LENGTH('dbo.etl_pipeline_execucao', 'substituida_em')"):
            self._rows = [(8 if db.tem_078 else None,)]
            return
        if s.startswith("SELECT data_referencia, status, inicio, fim, "
                        "disparado_por, motivo FROM dbo.etl_pipeline_execucao"):
            # corrida_por_run_id — o caminho de quem já escolheu a corrida à
            # mão (a variante das duas corridas no ODATE).
            _pipe, rid = params
            self._rows = [(_D, c["status"], c.get("inicio"), c.get("fim"),
                           c.get("disparado_por"), None)
                          for c in db.corridas if str(c["run_id"]) == str(rid)]
            return
        if s.startswith("SELECT execution_id, status, inicio, fim, disparado_por, motivo "
                        "FROM dbo.etl_pipeline_execucao"):
            pipe, _d = params
            self._rows = [(c["run_id"], c["status"], c.get("inicio"), c.get("fim"),
                           c.get("disparado_por"), None)
                          for c in db.corridas
                          if c["pipeline"].casefold() == str(pipe).casefold()]
            return
        if s.startswith("SELECT d.pipeline_name FROM dbo.etl_pipeline_dependencia"):
            self._rows = [(f,) for f in db.grafo.get(str(params[0]).casefold(), [])]
            return
        if s.startswith("SELECT execution_id, status, inicio, fim, disparado_por,"):
            pipe = str(params[0]).casefold()
            self._rows = [(c["run_id"], c["status"], c.get("inicio"), c.get("fim"),
                           c.get("disparado_por"), None)
                          for c in db.corridas if c["pipeline"].casefold() == pipe]
            return
        if s.startswith("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS"):
            self._rows = [("job_name",), ("job_type",), ("execution_order",),
                          ("depends_on_jobs",)]
            return
        if s.startswith("SELECT job_name, ISNULL(job_type"):
            self._rows = [("etapa_x", "http", 1, None)]
            return
        if s.startswith("UPDATE dbo.etl_pipeline_execucao") \
                or s.startswith("INSERT INTO dbo.etl_pipeline_audit"):
            db.escritas.append((s, params))
            # rowcount REALISTA na aposentadoria das irmãs (`execution_id <> ?`):
            # conta as OUTRAS corridas vivas do pipeline na data. Com um dublê
            # que devolvesse 1 sempre, um pipeline de corrida única acusaria
            # irmã aposentada — e o teste da variante das duas corridas não
            # provaria nada.
            if s.startswith("UPDATE dbo.etl_pipeline_execucao SET status='EXECUTANDO'"):
                self.rowcount = db.executando_rowcount
                return
            if "execution_id <> ?" in s:
                pipe, escolhida = str(params[1]), str(params[3])
                self.rowcount = len(
                    [c for c in db.corridas
                     if c["pipeline"].casefold() == pipe.casefold()
                     and str(c["run_id"]) != escolhida
                     and c.get("status") != "AGUARDANDO_DEPENDENCIA"])
                return
            self.rowcount = 1
            return
        raise AssertionError(f"SQL não previsto no dublê: {s[:140]}")

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


def _corrida(run_id, pipeline="DEV_F10_A", status="SUCESSO", inicio=None):
    return {"run_id": run_id, "pipeline": pipeline, "status": status,
            "inicio": inicio or datetime(2026, 8, 3, 9, 0, 0),
            "fim": None, "disparado_por": "manual"}


# run_id da forma do Airflow — traduzível pela string, sem precisar do Airflow.
_RUN_A = "manual__2026-08-03T12:49:24+00:00"
_RUN_B = "manual__2026-08-03T15:00:00+00:00"


@pytest.fixture
def cliente(client, app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EXECUTAR, "tela_malha"],
    }
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def cliente_sem_perm(client, app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "CONS", "perfil": "consulta", "permissoes": ["tela_malha"],
    }
    yield client
    app.dependency_overrides.pop(get_current_user, None)


def _post(cliente, db, body, af=None):
    af = af or _ClientFake()
    with patch("routers.execucoes.get_db_conn", return_value=db), \
         patch("routers.execucoes.get_airflow_client", return_value=af):
        r = cliente.post("/execucoes/rerun", json=body)
    return r, af


def test_rerun_exige_permissao_de_executar(cliente_sem_perm):
    r = cliente_sem_perm.post("/execucoes/rerun", json={
        "pipeline_name": "DEV_F10_A", "task_id": "etapa_x"})
    assert r.status_code == 403


def test_previa_exige_permissao_de_executar(cliente_sem_perm):
    r = cliente_sem_perm.get(
        "/pipelines/DEV_F10_A/rerun/previa?task_id=etapa_x")
    assert r.status_code == 403


def test_odate_ambiguo_e_RECUSADO_com_a_lista_de_candidatos(cliente):
    """Modo estrito da F2 aplicado ao gesto destrutivo: duas corridas no ODATE
    → 409 com os candidatos, para a tela PERGUNTAR. Nunca 'a mais recente'."""
    db = _DbRerun(corridas=[_corrida(_RUN_A), _corrida(_RUN_B)])
    r, af = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                                "task_id": "etapa_x",
                                "data_referencia": "2026-08-03"})
    assert r.status_code == 409
    det = r.json()["detail"]
    assert det["erro"] == "corrida_ambigua"
    assert len(det["candidatos"]) == 2
    assert af.posts == []           # NADA foi limpo


def test_odate_sem_corrida_e_404_sem_tocar_no_airflow(cliente):
    db = _DbRerun(corridas=[])
    r, af = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                                "task_id": "etapa_x",
                                "data_referencia": "2026-08-03"})
    assert r.status_code == 404 and af.posts == []


def test_sem_cascata_nenhum_dependente_e_reaberto(cliente):
    """Opção 'só este pipeline': o claim segue barrando os dependentes (o
    comportamento de hoje) — e nenhuma corrida é aposentada."""
    db = _DbRerun(corridas=[_corrida(_RUN_A)],
                  grafo={"DEV_F10_A": ["DEV_F10_C", "DEV_F10_D"]})
    r, af = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                                "task_id": "etapa_x",
                                "data_referencia": "2026-08-03"})
    assert r.status_code == 200
    body = r.json()
    assert body["cascata"] is False
    assert body["dependentes_reabertos"] == []
    assert body["corridas_substituidas"] == 0
    # Nenhum DEPENDENTE aposentado. (A aposentadoria das corridas IRMÃS do
    # próprio pipeline é outra pergunta e vale sem cascata — ver
    # `test_variante_duas_corridas_*`; com uma corrida só ela não muda nada,
    # e é isso que `corridas_irmas_aposentadas` diz.)
    assert body["corridas_irmas_aposentadas"] == 0
    assert not [e for e in db.escritas
                if "substituida_em" in e[0] and "execution_id <> ?" not in e[0]]


def test_com_cascata_os_dependentes_com_corrida_sao_reabertos(cliente):
    """Opção 'este e os dependentes': as corridas do ODATE dos dependentes são
    aposentadas — é o que faz o push do pai reexecutado ganhar o claim e
    disparar de novo, com o MESMO ODATE."""
    db = _DbRerun(
        corridas=[_corrida(_RUN_A),
                  _corrida("dep__c", pipeline="DEV_F10_C"),
                  _corrida("dep__d", pipeline="DEV_F10_D")],
        grafo={"DEV_F10_A": ["DEV_F10_C", "DEV_F10_D"]})
    r, af = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                                "task_id": "etapa_x",
                                "data_referencia": "2026-08-03",
                                "cascata": True})
    assert r.status_code == 200
    body = r.json()
    assert body["cascata"] is True
    assert sorted(body["dependentes_reabertos"]) == ["DEV_F10_C", "DEV_F10_D"]
    assert body["corridas_substituidas"] == 2
    subs = [e for e in db.escritas if "substituida_em = GETDATE()" in e[0]
            and "execution_id <> ?" not in e[0]]
    assert {e[1][1] for e in subs} == {"DEV_F10_C", "DEV_F10_D"}


def test_rerun_marca_o_proprio_pipeline_como_executando(cliente):
    """Enquanto a linha do pai disser SUCESSO, um push de outro pai (ou a
    guardiã) pode liberar um dependente com o dado VELHO — exatamente o que a
    decisão 1 proíbe. O `publish_dataset` reescreve para SUCESSO ao concluir."""
    db = _DbRerun(corridas=[_corrida(_RUN_A)], grafo={"DEV_F10_A": []})
    r, _ = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                               "task_id": "etapa_x",
                               "data_referencia": "2026-08-03"})
    assert r.status_code == 200
    marca = [e for e in db.escritas if "SET status='EXECUTANDO'" in e[0]]
    assert len(marca) == 1
    assert marca[0][1] == ("DEV_F10_A", date(2026, 8, 3), _RUN_A)


def test_rerun_audita_sempre(cliente):
    db = _DbRerun(corridas=[_corrida(_RUN_A)], grafo={"DEV_F10_A": []})
    r, _ = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                               "task_id": "etapa_x",
                               "data_referencia": "2026-08-03"})
    assert r.json()["auditado"] is True
    aud = [e for e in db.escritas if "etl_pipeline_audit" in e[0]]
    assert len(aud) == 1 and aud[0][1][2] == "rerun_etapa"


def test_cascata_sem_a_078_avisa_em_vez_de_prometer(cliente):
    """Deploy parcial: o gesto acontece (o clear é real), mas a resposta DIZ
    que os dependentes não vão rodar de novo — nunca um sucesso mudo."""
    db = _DbRerun(corridas=[_corrida(_RUN_A),
                            _corrida("dep__c", pipeline="DEV_F10_C")],
                  grafo={"DEV_F10_A": ["DEV_F10_C"]}, tem_078=False)
    r, _ = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                               "task_id": "etapa_x",
                               "data_referencia": "2026-08-03",
                               "cascata": True})
    assert r.status_code == 200
    b = r.json()
    assert b["corridas_substituidas"] == 0
    assert any("078" in a for a in b["avisos"])
    # A lista de reabertos tem de vir VAZIA — encontrado na prova viva do
    # fallback: ela vinha cheia junto com `corridas_substituidas: 0`, e o toast
    # do front (que conta esta lista) anunciaria "2 dependentes reabertos"
    # enquanto o aviso ao lado dizia que nenhum rodaria de novo.
    assert b["dependentes_reabertos"] == []


def test_rerun_manda_o_corpo_certo_ao_airflow(cliente):
    db = _DbRerun(corridas=[_corrida(_RUN_A)], grafo={"DEV_F10_A": []})
    r, af = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                                "task_id": "etapa_x",
                                "data_referencia": "2026-08-03"})
    url, corpo = af.posts[0]
    assert url == "/api/v1/dags/DEV_F10_A/clearTaskInstances"
    assert corpo == rr.corpo_clear(_RUN_A, "etapa_x")


def test_caminho_historico_de_logs_e_dashboard_nao_muda(cliente):
    """NÃO-REGRESSÃO: chamada com `execution_id` e sem `data_referencia` (o
    que o modal de Logs e o Dashboard mandam) continua resolvendo o dag_run
    pelo Airflow, com `_escolhe_dag_run` — sem passar pelo modo estrito."""
    db = _DbRerun(corridas=[])
    af = _ClientFake()

    async def _get(url, params=None):
        return _RespFake({"dag_runs": [
            {"dag_run_id": "scheduled__x", "logical_date": "2026-08-03T12:00:00+00:00",
             "state": "failed"}]})
    af.get = _get
    with patch("routers.execucoes.get_db_conn", return_value=db), \
         patch("routers.execucoes.get_airflow_client", return_value=af):
        r = cliente.post("/execucoes/rerun", json={
            "pipeline_name": "DEV_F10_A", "task_id": "etapa_x",
            "execution_id": "20260803T120000"})
    assert r.status_code == 200
    assert r.json()["dag_run_id"] == "scheduled__x"
    assert af.posts[0][1] == rr.corpo_clear("scheduled__x", "etapa_x")


def test_previa_mostra_as_duas_opcoes_com_os_afetados(cliente):
    """Decisão 1 na prática: a prévia devolve as etapas deste pipeline (do
    dry_run REAL do Airflow) e o fecho a jusante separado — é o material
    exato do modal."""
    db = _DbRerun(
        corridas=[_corrida(_RUN_A),
                  _corrida("dep__c", pipeline="DEV_F10_C")],
        grafo={"DEV_F10_A": ["DEV_F10_C", "DEV_F10_D"]})
    af = _ClientFake(task_instances=[{"task_id": "log_start_etapa_x"},
                                     {"task_id": "etapa_x"},
                                     {"task_id": "publish_dataset"}])
    with patch("routers.execucoes.get_db_conn", return_value=db), \
         patch("routers.execucoes.get_airflow_client", return_value=af):
        r = cliente.get("/pipelines/DEV_F10_A/rerun/previa"
                        "?task_id=etapa_x&data_referencia=2026-08-03")
    assert r.status_code == 200
    b = r.json()
    assert b["etapas"] == ["etapa_x"] and b["tasks_de_apoio"] == 2
    assert b["dag_run_id"] == _RUN_A
    assert b["cascata"]["dependentes"] == ["DEV_F10_C", "DEV_F10_D"]
    assert b["cascata"]["com_corrida"] == ["DEV_F10_C"]
    assert b["cascata"]["sem_corrida"] == ["DEV_F10_D"]
    assert b["cascata"]["disponivel"] is True
    # a prévia NÃO altera nada
    assert af.posts[0][1]["dry_run"] is True
    assert db.escritas == []


def test_previa_recusa_odate_ambiguo(cliente):
    db = _DbRerun(corridas=[_corrida(_RUN_A), _corrida(_RUN_B)])
    with patch("routers.execucoes.get_db_conn", return_value=db), \
         patch("routers.execucoes.get_airflow_client", return_value=_ClientFake()):
        r = cliente.get("/pipelines/DEV_F10_A/rerun/previa"
                        "?task_id=etapa_x&data_referencia=2026-08-03")
    assert r.status_code == 409
    assert r.json()["detail"]["erro"] == "corrida_ambigua"


# ═══════════════════════════════════════════════════════════════════════════
# 8. OS TRÊS DEFEITOS DA REVISÃO PRÉ-DEPLOY (correções de 2026-08-03)
#
#   1. a cascata liberava o NETO com dado velho — a terceira porta
#      (`liberado()`) não filtrava corrida substituída, e a variante das duas
#      corridas do pai deixava um SUCESSO sobrevivente liberando o filho;
#   2. deploy parcial "078 sim / dags não": a API afirmava uma cascata que o
#      motor deployado não cumpria;
#   3. o carimbo de EXECUTANDO não conferia rowcount, e rerun em DAG PAUSADA
#      deixava a corrida pendurada bloqueando todo dependente.
# ═══════════════════════════════════════════════════════════════════════════

# ── defeito 2: a API sabe se o dags/ deployado entende o carimbo ─────────────

def _escreve_modulo(tmp_path, corpo: str) -> Path:
    alvo = tmp_path / "utils"
    alvo.mkdir(parents=True, exist_ok=True)
    (alvo / "dependencias.py").write_text(corpo, encoding="utf-8")
    return alvo / "dependencias.py"


def test_capacidade_le_a_declaracao_do_modulo_do_motor(tmp_path):
    p = _escreve_modulo(tmp_path, 'CAPACIDADES = ("rerun_cascata_078",)\n')
    assert rr.capacidade_dags(p) == rr.CAP_OK


def test_capacidade_ausente_quando_o_dags_e_antigo(tmp_path):
    """dags/ anterior à fase: o arquivo existe, a declaração não."""
    p = _escreve_modulo(tmp_path, "def liberado(conn, p, d):\n    return True, []\n")
    assert rr.capacidade_dags(p) == rr.CAP_AUSENTE


def test_capacidade_nao_se_engana_com_comentario_ou_docstring(tmp_path):
    """A sonda é AST, não `in`: o texto que EXPLICA a capacidade aparece no
    módulo do motor em comentário e docstring. Um grep diria 'sim' para um
    dags/ que só fala do assunto."""
    p = _escreve_modulo(
        tmp_path,
        '"""fala de rerun_cascata_078 na docstring."""\n'
        "# rerun_cascata_078 em comentario\n"
        "OUTRA = ('rerun_cascata_078',)\n")
    assert rr.capacidade_dags(p) == rr.CAP_AUSENTE


def test_capacidade_desconhecida_quando_nao_da_para_ler(tmp_path):
    """Mount ausente / permissão: a resposta é DESCONHECIDA — e desconhecida
    NÃO vira 'pode'. É o inverso exato do defeito."""
    assert rr.capacidade_dags(tmp_path / "nao" / "existe.py") == rr.CAP_DESCONHECIDA


def test_capacidade_do_repo_de_verdade():
    """Fecha o contrato com o canônico: o dags/ DESTE repo declara."""
    assert rr.capacidade_dags(_ROOT / "dags/utils/dependencias.py") == rr.CAP_OK


def test_razao_separa_as_duas_metades_do_deploy(monkeypatch):
    """Banco sem a 078 e dags/ velho são consertos DIFERENTES (rodar migration
    × deployar dags/) — a razão tem de dizer qual."""
    cur_sem_078 = _CurGrafo({"A": []}, tem_078=False)
    assert rr.razao_cascata_indisponivel(cur_sem_078) == "migration_078_pendente"
    cur_ok = _CurGrafo({"A": []})
    monkeypatch.setattr(rr, "capacidade_dags", lambda *a, **k: rr.CAP_AUSENTE)
    assert rr.razao_cascata_indisponivel(cur_ok) == rr.CAP_AUSENTE
    monkeypatch.setattr(rr, "capacidade_dags", lambda *a, **k: rr.CAP_OK)
    assert rr.razao_cascata_indisponivel(cur_ok) is None


def test_sem_o_dags_novo_nada_e_carimbado(monkeypatch):
    """O coração do defeito 2: com a 078 no banco e o dags/ ANTIGO, carimbar
    seria aposentar corridas que ninguém vai reabrir — dependentes parados
    para sempre e uma resposta dizendo 'reabertos'."""
    monkeypatch.setattr(rr, "capacidade_dags", lambda *a, **k: rr.CAP_AUSENTE)
    cur = _CurGrafo({"A": ["C"], "C": []},
                    corridas={"c": [{"run_id": "r", "status": "SUCESSO"}]})
    assert rr.marcar_substituidas(cur, ["C"], _D, "DEV1") == 0
    assert not [e for e in cur.execs if "substituida_em = GETDATE()" in e[0]]


def test_cascata_com_dags_desatualizado_avisa_o_deploy_pendente(cliente, monkeypatch):
    """Ponta a ponta: a resposta não promete a cascata, a lista de reabertos
    vem vazia e o aviso nomeia o conserto certo (deploy de dags/, não
    migration)."""
    monkeypatch.setattr(rr, "capacidade_dags", lambda *a, **k: rr.CAP_AUSENTE)
    db = _DbRerun(corridas=[_corrida(_RUN_A),
                            _corrida("dep__c", pipeline="DEV_F10_C")],
                  grafo={"DEV_F10_A": ["DEV_F10_C"]})
    r, _ = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                               "task_id": "etapa_x",
                               "data_referencia": "2026-08-03",
                               "cascata": True})
    assert r.status_code == 200
    b = r.json()
    assert b["corridas_substituidas"] == 0
    assert b["dependentes_reabertos"] == []
    assert any("dags/" in a for a in b["avisos"]), b["avisos"]
    assert not [e for e in db.escritas if "substituida_em = GETDATE()" in e[0]]


def test_previa_diz_que_a_cascata_depende_do_deploy_do_dags(cliente, monkeypatch):
    monkeypatch.setattr(rr, "capacidade_dags", lambda *a, **k: rr.CAP_AUSENTE)
    db = _DbRerun(corridas=[_corrida(_RUN_A),
                            _corrida("dep__c", pipeline="DEV_F10_C")],
                  grafo={"DEV_F10_A": ["DEV_F10_C"]})
    with patch("routers.execucoes.get_db_conn", return_value=db), \
         patch("routers.execucoes.get_airflow_client", return_value=_ClientFake()):
        r = cliente.get("/pipelines/DEV_F10_A/rerun/previa"
                        "?task_id=etapa_x&data_referencia=2026-08-03")
    assert r.status_code == 200
    assert r.json()["cascata"]["disponivel"] is False
    assert r.json()["cascata"]["razao"] == rr.CAP_AUSENTE


# ── defeito 1 (variante): as OUTRAS corridas do pai no mesmo ODATE ───────────

def test_variante_duas_corridas_a_irma_e_aposentada(cliente):
    """Com dois runs do pai no ODATE, o operador escolhe UM (`dag_run_id`) e o
    carimbo de EXECUTANDO só toca o escolhido. O outro continuava dizendo
    SUCESSO — e liberação é EXISTS: UM sobrevivente basta para o filho partir
    com o dado velho. A corrida irmã é aposentada."""
    db = _DbRerun(corridas=[_corrida(_RUN_A), _corrida(_RUN_B)],
                  grafo={"DEV_F10_A": ["DEV_F10_C"]})
    r, _ = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                               "task_id": "etapa_x",
                               "dag_run_id": _RUN_A,
                               "data_referencia": "2026-08-03",
                               "cascata": True})
    assert r.status_code == 200
    assert r.json()["corridas_irmas_aposentadas"] == 1
    irmas = [e for e in db.escritas if "execution_id <> ?" in e[0]]
    assert len(irmas) == 1
    # a escolhida é preservada (é ela que está rodando de novo)
    assert irmas[0][1] == ("rerun:DEV1", "DEV_F10_A", date(2026, 8, 3), _RUN_A)
    # e a linha aposentada NÃO tem o status reescrito nem é apagada
    assert "status =" not in irmas[0][0].split("WHERE")[0]
    assert any("aposentadas" in a for a in r.json()["avisos"])


def test_variante_duas_corridas_vale_tambem_sem_cascata(cliente):
    """'Sem cascata' quer dizer *não reabro quem já rodou* — nunca *deixo uma
    corrida velha do próprio pipeline liberando quem ainda não rodou*. É a
    mesma proteção do carimbo de EXECUTANDO, que já é incondicional."""
    db = _DbRerun(corridas=[_corrida(_RUN_A), _corrida(_RUN_B)],
                  grafo={"DEV_F10_A": ["DEV_F10_C"]})
    r, _ = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                               "task_id": "etapa_x",
                               "dag_run_id": _RUN_A,
                               "data_referencia": "2026-08-03"})
    assert r.status_code == 200
    assert r.json()["corridas_irmas_aposentadas"] == 1


def test_corrida_unica_nao_tem_irma_a_aposentar(cliente):
    """Não-regressão do caso comum: um run só no dia → nada a aposentar e
    nenhum aviso a mais."""
    db = _DbRerun(corridas=[_corrida(_RUN_A)], grafo={"DEV_F10_A": []})
    r, _ = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                               "task_id": "etapa_x",
                               "data_referencia": "2026-08-03"})
    assert r.json()["corridas_irmas_aposentadas"] == 0
    assert r.json()["avisos"] == []


def test_irmas_nao_sao_aposentadas_sem_o_motor_que_le_o_carimbo(cliente, monkeypatch):
    """Mesma disciplina do defeito 2: sem as duas metades do deploy, carimbar
    só criaria corrida aposentada que ninguém lê."""
    monkeypatch.setattr(rr, "capacidade_dags", lambda *a, **k: rr.CAP_AUSENTE)
    db = _DbRerun(corridas=[_corrida(_RUN_A), _corrida(_RUN_B)],
                  grafo={"DEV_F10_A": []})
    r, _ = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                               "task_id": "etapa_x",
                               "dag_run_id": _RUN_A,
                               "data_referencia": "2026-08-03"})
    assert r.json()["corridas_irmas_aposentadas"] == 0
    assert not [e for e in db.escritas if "execution_id <> ?" in e[0]]


# ── defeito 3: rowcount do carimbo e DAG pausada ────────────────────────────

def test_carimbo_de_executando_sem_linha_casada_vira_aviso(cliente):
    """O UPDATE passava em silêncio: `execution_id` que não casa → a marca
    não acontece, e é ela que impede o filho de partir com o dado velho.
    Rowcount 0 agora é dito."""
    db = _DbRerun(corridas=[_corrida(_RUN_A)], grafo={"DEV_F10_A": []},
                  executando_rowcount=0)
    r, _ = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                               "task_id": "etapa_x",
                               "data_referencia": "2026-08-03"})
    assert r.status_code == 200
    assert any("em execução" in a for a in r.json()["avisos"]), r.json()["avisos"]


def test_rerun_em_dag_pausada_e_recusado_sem_limpar_nada(cliente):
    """Com a DAG pausada o clear é aceito, o run volta para QUEUED e NADA
    roda — e a corrida fica EXECUTANDO travando todo dependente (a classe do
    'órfão em RUNNING'). Recusar é o único desfecho honesto: nada é limpo,
    nada é carimbado, e a mensagem diz o conserto."""
    db = _DbRerun(corridas=[_corrida(_RUN_A)], grafo={"DEV_F10_A": []})
    af = _ClientFake(is_paused=True)
    r, af = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                                "task_id": "etapa_x",
                                "data_referencia": "2026-08-03",
                                "cascata": True}, af=af)
    assert r.status_code == 409
    assert r.json()["detail"]["erro"] == "dag_pausada"
    assert af.posts == []                      # nada foi limpo
    assert db.escritas == []                   # nada foi carimbado


def test_airflow_mudo_sobre_pausa_nao_bloqueia_o_gesto(cliente):
    """Não-regressão: `is_paused` indisponível (Airflow fora, 404) não pode
    derrubar o rerun histórico de Logs/Dashboard — só o SIM bloqueia."""
    db = _DbRerun(corridas=[_corrida(_RUN_A)], grafo={"DEV_F10_A": []})
    r, af = _post(cliente, db, {"pipeline_name": "DEV_F10_A",
                                "task_id": "etapa_x",
                                "data_referencia": "2026-08-03"},
                  af=_ClientFake(is_paused=None))
    assert r.status_code == 200 and len(af.posts) == 1


def test_previa_avisa_a_dag_pausada_antes_do_clique(cliente):
    """O modal não pode oferecer um botão que só pode dar 409."""
    db = _DbRerun(corridas=[_corrida(_RUN_A)], grafo={"DEV_F10_A": []})
    with patch("routers.execucoes.get_db_conn", return_value=db), \
         patch("routers.execucoes.get_airflow_client",
               return_value=_ClientFake(is_paused=True)):
        r = cliente.get("/pipelines/DEV_F10_A/rerun/previa"
                        "?task_id=etapa_x&data_referencia=2026-08-03")
    assert r.status_code == 200 and r.json()["dag_pausada"] is True
