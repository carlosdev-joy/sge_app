"""
F5 da spec de operação no nível de etapa (docs/spec-operacao-nivel-etapa.md):
**etapa em espera** — pausa em runtime, liberação, cancelamento e teto com
alerta (§5 Bloco C; decisão 3 do §7: "RUNTIME primeiro", C2).

O que estes testes guardam, em ordem de importância:

  • **o limite honesto do §5** — só pausa etapa que AINDA NÃO INICIOU, e isso
    é verificado no servidor (409 com a lista do que dá para pausar), não só
    explicado na tela;
  • **a ordem do cancelamento** — falha o DagRun no Airflow PRIMEIRO; se o
    Airflow recusar, a pausa continua PENDENTE e a etapa segue segura. O
    inverso abriria o portão para uma execução que ninguém cancelou;
  • **atomicidade das transições** — liberar/cancelar/expirar carregam
    `AND estado='PENDENTE'`; quem chega segundo recebe 409, nunca um sucesso
    mentiroso;
  • **degradação sem a 079** — a tela responde "indisponível", o payload de
    execução volta com `pausas: []` e nada quebra;
  • **placeholder por árvore** — `?` aqui (pyodbc), `%s` em dags/ (pymssql).

Dublês locais; nada toca rede nem banco.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from services import espera as esp

_D = date(2026, 8, 3)


class _Cur:
    """Cursor pyodbc de mentira, roteado por prefixo de SQL."""

    def __init__(self, *, tem_tabela=True, iniciadas=(), pausas=(),
                 teto_cfg="240", sla=None, rowcount=1, erro=None, linha=None):
        self.tem_tabela = tem_tabela
        self.iniciadas = list(iniciadas)
        self.pausas = list(pausas)
        self.teto_cfg = teto_cfg
        self.sla = sla
        self.rowcount = rowcount
        self.erro = erro
        self.linha = linha
        self.sqls: list = []
        self._rows: list = []

    def execute(self, sql, params=()):
        s = " ".join(str(sql).split())
        self.sqls.append((s, params))
        if s.startswith("SELECT OBJECT_ID('dbo.etl_etapa_pausa'"):
            self._rows = [(1 if self.tem_tabela else None,)]
            return
        if self.erro:
            raise self.erro
        if "FROM dbo.etl_app_config" in s:
            self._rows = [(self.teto_cfg,)] if self.teto_cfg is not None else []
        elif "FROM dbo.etl_job_execution" in s:
            self._rows = [(j,) for j in self.iniciadas]
        elif "sla_minutos" in s:
            self._rows = [(self.sla,)]
        elif s.startswith("SELECT TOP (1) id FROM dbo.etl_etapa_pausa"):
            self._rows = [(77,)]
        elif s.startswith("SELECT id, pipeline_name"):
            self._rows = [self.linha] if self.linha else []
        elif "FROM dbo.etl_etapa_pausa" in s:
            self._rows = list(self.pausas)
        else:
            self._rows = []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


# ═══════════════════════════════════════════════════════════════════════════
# 1. O LIMITE HONESTO — só etapa que ainda não iniciou
# ═══════════════════════════════════════════════════════════════════════════

def test_etapas_iniciadas_sao_as_que_tem_linha_de_execucao():
    """Ter linha em etl_job_execution significa que o log_start RODOU — o
    portão daquela etapa já ficou para trás, em RUNNING, SUCCESS ou FAILED."""
    cur = _Cur(iniciadas=["ExtraiDS", "RodaProc"])
    assert esp.etapas_iniciadas(cur, "PIPE", "TS") == {"extraids", "rodaproc"}


def test_etapas_iniciadas_compara_por_casefold():
    """Colação CI do banco × dict case-sensitive do Python (PR #236)."""
    cur = _Cur(iniciadas=["ExTrAiDs"])
    assert "extraids" in esp.etapas_iniciadas(cur, "PIPE", "TS")


def test_etapas_iniciadas_filtra_pela_corrida_e_pelo_pipeline():
    cur = _Cur(iniciadas=[])
    esp.etapas_iniciadas(cur, "PIPE", "20260803T060000")
    sql, params = cur.sqls[-1]
    assert "execution_id = ? AND pipeline = ?" in sql
    assert params == ("20260803T060000", "PIPE")


# ═══════════════════════════════════════════════════════════════════════════
# 2. CRIAÇÃO — INSERT condicional, teto na linha
# ═══════════════════════════════════════════════════════════════════════════

def test_criar_e_condicional_para_nao_duplicar_pendente():
    """Duas abas clicando "Pausar" produzem UMA pausa e nenhum 500 — o único
    filtrado da 079 é a rede, não o fluxo de controle."""
    cur = _Cur()
    esp.criar(cur, pipeline="P", execution_id="TS", job_name="J", task_id="J",
              run_id="r1", data_ref=_D, motivo="conferir", teto=60, usuario="M1")
    sql = cur.sqls[0][0]
    assert "WHERE NOT EXISTS" in sql and "estado = 'PENDENTE'" in sql


def test_criar_devolve_zero_quando_ja_havia_pendente():
    cur = _Cur(rowcount=0)
    assert esp.criar(cur, pipeline="P", execution_id="TS", job_name="J",
                     task_id="J", run_id=None, data_ref=_D, motivo=None,
                     teto=60, usuario="M1") == 0


def test_criar_usa_placeholder_de_pyodbc():
    """Árvore api/ usa `?`; `%s` aqui daria "Incorrect syntax near '?'" — ou,
    pior, gravação zero com a task verde (o gotcha registrado do projeto)."""
    cur = _Cur()
    esp.criar(cur, pipeline="P", execution_id="TS", job_name="J", task_id="J",
              run_id=None, data_ref=_D, motivo=None, teto=60, usuario="M1")
    sql = cur.sqls[0][0]
    assert "%s" not in sql and sql.count("?") == 12


@pytest.mark.parametrize("bruto,esperado", [
    (None, 240), ("", 240), ("abc", 240), (0, 240), (99999999, 240),
    (30, 30), ("45", 45),
])
def test_normaliza_teto(bruto, esperado):
    assert esp.normaliza_teto(bruto, 240) == esperado


def test_teto_padrao_vem_do_app_config():
    assert esp.teto_padrao(_Cur(teto_cfg="90")) == 90


def test_teto_padrao_absurdo_cai_no_default():
    assert esp.teto_padrao(_Cur(teto_cfg="0")) == esp.TETO_PADRAO_MIN
    assert esp.teto_padrao(_Cur(teto_cfg="lixo")) == esp.TETO_PADRAO_MIN


# ═══════════════════════════════════════════════════════════════════════════
# 3. TRANSIÇÕES ATÔMICAS
# ═══════════════════════════════════════════════════════════════════════════

def test_resolver_exige_estado_pendente():
    cur = _Cur(rowcount=1)
    assert esp.resolver(cur, 7, "LIBERADA", "M1", "ok") is True
    assert "WHERE id = ? AND estado = 'PENDENTE'" in cur.sqls[-1][0]


def test_resolver_perdeu_a_corrida_devolve_false():
    """O teto estourou no mesmo instante: quem chegou depois não sobrescreve
    o carimbo de quem chegou antes."""
    assert esp.resolver(_Cur(rowcount=0), 7, "LIBERADA", "M1", None) is False


# ═══════════════════════════════════════════════════════════════════════════
# 4. DEGRADAÇÃO SEM A 079
# ═══════════════════════════════════════════════════════════════════════════

def test_tem_tabela_falso_sem_a_migration():
    assert esp.tem_tabela(_Cur(tem_tabela=False)) is False


def test_listar_devolve_vazio_sem_a_migration():
    assert esp.listar(_Cur(tem_tabela=False), "P", "TS") == []


def test_listar_engole_erro_de_consulta():
    assert esp.listar(_Cur(erro=RuntimeError("timeout")), "P", "TS") == []


def test_listar_traz_tambem_as_resolvidas():
    """Histórico faz parte da resposta: "quem liberou e quando" é metade do
    valor do gesto (§5)."""
    linhas = [(1, "J", "J", "LIBERADA", "m", "o", 60, "M1", None, None, None,
               3, "M2", None, None, _D, None)]
    p = esp.listar(_Cur(pausas=linhas), "P", "TS")[0]
    assert p["estado"] == "LIBERADA" and p["resolvido_por"] == "M2"


# ═══════════════════════════════════════════════════════════════════════════
# 5. EVENTO E AUDITORIA
# ═══════════════════════════════════════════════════════════════════════════

def test_evento_reusa_a_tabela_da_guardia_com_a_mesma_dedupe():
    """Nenhum canal novo: o alerta entra em etl_dependencia_evento e a fila do
    Teams da guardiã o drena sem uma linha de mudança lá."""
    cur = _Cur()
    assert esp.gravar_evento(cur, "P", _D, esp.EVENTO_LIBERADA, "detalhe") is True
    sql = cur.sqls[-1][0]
    assert "dbo.etl_dependencia_evento" in sql and "WHERE NOT EXISTS" in sql


def test_evento_sem_data_nao_grava():
    assert esp.gravar_evento(_Cur(), "P", None, "X", "d") is False


def test_evento_que_falha_nao_derruba_o_gesto():
    assert esp.gravar_evento(_Cur(erro=RuntimeError("x")), "P", _D, "X", "d") is False


def test_auditoria_grava_uma_linha_por_gesto():
    cur = _Cur()
    assert esp.registrar_auditoria(cur, "P", "M1", "liberar",
                                   {"pausa_id": 7, "job_name": "J"}) is True
    sql, params = cur.sqls[-1]
    assert "dbo.etl_pipeline_audit" in sql
    assert params[2] == esp.CAMPO_AUDIT
    assert '"gesto": "liberar"' in params[4]


def test_auditoria_nunca_levanta():
    assert esp.registrar_auditoria(_Cur(erro=RuntimeError("x")), "P", "M1",
                                   "pausar", {}) is False


# ═══════════════════════════════════════════════════════════════════════════
# 6. AVISO HONESTO DO dagrun_timeout
# ═══════════════════════════════════════════════════════════════════════════

def test_avisa_quando_o_sla_e_menor_que_o_teto():
    """Pipeline com SLA gera DAG com dagrun_timeout: uma espera até o teto
    pode ser morta pelo Airflow antes, e por outro motivo."""
    avisos = esp.avisos_da_pausa(_Cur(sla=60), "P", 240)
    assert avisos and "dagrun_timeout" in avisos[0]


def test_nao_avisa_sem_sla():
    assert esp.avisos_da_pausa(_Cur(sla=None), "P", 240) == []


def test_nao_avisa_com_sla_folgado():
    assert esp.avisos_da_pausa(_Cur(sla=600), "P", 240) == []


# ═══════════════════════════════════════════════════════════════════════════
# 7. O ROUTER — formato e a ordem do cancelamento
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def E():
    import routers.execucoes as _e
    return _e


def test_pausa_json_serializa_datas(E):
    from datetime import datetime as dt
    saida = E._pausa_json({"data_referencia": _D,
                           "solicitado_em": dt(2026, 8, 3, 9, 30, 0),
                           "aguardando_desde": None, "ultima_verificacao": None,
                           "resolvido_em": None, "alertado_em": None})
    assert saida["data_referencia"] == "2026-08-03"
    assert saida["solicitado_em"].startswith("2026-08-03")


def test_cancelar_falha_o_dagrun_antes_de_marcar(E):
    """⛔ A ORDEM É A GARANTIA. O corpo do endpoint chama o Airflow (PATCH
    state=failed) e só chama `resolver(... CANCELADA)` depois — e devolve 502
    sem tocar na linha quando o Airflow recusa."""
    import inspect
    src = inspect.getsource(E.cancelar_pausa)
    assert src.index('json={"state": "failed"}') < src.index('"CANCELADA"')
    assert src.index("status_code=502") < src.index('"CANCELADA"')


def test_liberar_nao_toca_no_airflow(E):
    """A task está em up_for_reschedule e volta sozinha — é o que o modo
    reschedule compra. Mexer no Airflow aqui seria efeito colateral gratuito."""
    import inspect
    src = inspect.getsource(E.liberar_pausa)
    assert "get_airflow_client" not in src and "clearTaskInstances" not in src


def test_endpoints_de_gesto_exigem_perm_executar(E):
    import inspect
    for fn in (E.criar_pausa, E.liberar_pausa, E.cancelar_pausa):
        assert "require_perm(PERM_EXECUTAR)" in inspect.getsource(fn)


def test_listagem_e_leitura_e_exige_so_login(E):
    """Quem só olha precisa enxergar que o processo está parado e por quê."""
    import inspect
    src = inspect.getsource(E.listar_pausas)
    assinatura = src.split('"""')[0]
    assert "get_current_user" in assinatura and "PERM_EXECUTAR" not in assinatura


def test_execucao_embute_as_pausas(E):
    """O canvas pinta "em espera" no MESMO ciclo em que pinta o status."""
    import inspect
    src = inspect.getsource(E.get_pipeline_execucao)
    assert '"pausas": pausas' in src


def test_rotas_registradas():
    # FastAPI novo embrulha os routers incluídos em _IncludedRouter — as rotas
    # de verdade estão no `original_router` de cada um.
    caminhos = set()
    for r in _app.routes:
        if hasattr(r, "path"):
            caminhos.add(r.path)
        for sub in getattr(getattr(r, "original_router", None), "routes", []):
            caminhos.add(getattr(sub, "path", None))
    assert "/execucoes/pausas" in caminhos
    assert "/execucoes/pausas/{pausa_id}/liberar" in caminhos
    assert "/execucoes/pausas/{pausa_id}/cancelar" in caminhos
    assert "/pipelines/{pipeline_name}/pausas" in caminhos


# ═══════════════════════════════════════════════════════════════════════════
# 8. A MIGRATION 079
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def sql_079():
    from pathlib import Path
    return (Path(__file__).parent.parent
            / "sql/migrations/079_etapa_pausa.sql").read_text(encoding="utf-8")


def test_migration_e_idempotente(sql_079):
    """Etapa 6c do deploy roda tudo de novo a cada deploy: nenhum CREATE pode
    estourar na segunda passada."""
    assert "IF OBJECT_ID('dbo.etl_etapa_pausa', 'U') IS NULL" in sql_079
    assert sql_079.count("IF NOT EXISTS (SELECT 1 FROM sys.indexes") == 2
    assert "IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config" in sql_079


def test_unico_e_filtrado_por_pendente(sql_079):
    """No máximo uma pendente por (execução, etapa) — e quantas resolvidas
    forem precisas, porque o histórico é a auditoria."""
    assert "CREATE UNIQUE INDEX ux_etapa_pausa_pendente" in sql_079
    assert "WHERE estado = 'PENDENTE'" in sql_079


def test_migration_confere_por_select(sql_079):
    """sql/migrate.py descarta PRINT (D40) — a conferência tem de ser SELECT."""
    assert sql_079.rstrip().endswith("GO")
    assert "AS tabela_pausa" in sql_079


# ═══════════════════════════════════════════════════════════════════════════
# 9. OS DOIS DEFEITOS QUE A PROVA VIVA ENCONTROU NO CANCELAMENTO
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("ts,esperado", [
    ("20260803T221651", "2026-08-03"),
    ("20260803", "2026-08-03"),
    ("lixo", None), ("", None), (None, None),
])
def test_data_do_execution_id(ts, esperado):
    """Resgate do ODATE pelo ts_nodash — pausar segundos após disparar a
    corrida pega a janela em que a 067 ainda não tem a linha, e a pausa nascia
    sem data (medido no dev). Sem data, o evento não é gravado e o painel não
    fica sabendo do gesto."""
    d = esp.data_do_execution_id(ts)
    assert (d.isoformat() if d else None) == esperado


def test_cancelar_fecha_a_corrida_como_falha():
    """⛔ O "órfão em RUNNING". Cancelar pelo Airflow marca as tasks não
    terminadas como SKIPPED — inclusive `registrar_falha` (ONE_FAILED), que é
    quem grava FALHA na 067. Medido: DagRun failed e corrida EXECUTANDO para
    sempre. Quem cancela é quem fecha."""
    cur = _Cur(rowcount=1)
    assert esp.fechar_corrida_cancelada(cur, "P", "run1", "M1") is True
    sql, params = cur.sqls[-1]
    assert "SET status = 'FALHA'" in sql
    assert "AND status NOT IN ('SUCESSO', 'FALHA')" in sql   # não rebaixa terminal
    assert "cancelada" in params[0]


def test_fechar_corrida_nunca_levanta():
    assert esp.fechar_corrida_cancelada(_Cur(erro=RuntimeError("x")), "P", "r", "M") is False


def test_cancelar_fecha_a_corrida_no_endpoint(E):
    import inspect
    src = inspect.getsource(E.cancelar_pausa)
    assert "fechar_corrida_cancelada" in src
    # e o fecho vem DEPOIS do PATCH no Airflow, junto do resto do registro
    assert src.index('json={"state": "failed"}') < src.index("fechar_corrida_cancelada")


def test_ambiguidade_fala_do_gesto_certo(E):
    """Prova de UI: com 2 corridas no ODATE, quem clicou em PAUSAR recebia uma
    mensagem falando em "reexecutar" (a resolução é compartilhada com a F4).
    O `gesto` conserta isso sem mexer no texto que a F4 já entregava."""
    import inspect
    src = inspect.getsource(E._resolve_alvo_rerun)
    assert 'gesto: str = "reexecutar"' in src
    assert 'gesto != "reexecutar"' in src
    assert 'gesto="pausar"' in inspect.getsource(E.criar_pausa)
