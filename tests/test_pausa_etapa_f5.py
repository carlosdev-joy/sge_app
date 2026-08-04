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


# ═══════════════════════════════════════════════════════════════════════════
# 9. O PORTÃO DA DAG PUBLICADA — a segunda metade do deploy da F5
#
# ⚠️ **DEFEITO ENCONTRADO NA REVISÃO ADVERSARIAL PRÉ-DEPLOY (2026-08-03).**
# A API conferia banco, desenho e telemetria e criava a pausa — sem nunca
# perguntar se a DAG PUBLICADA tem o portão. O portão não é migration nem
# módulo importado em runtime: é uma linha EMITIDA no fonte gerado de cada
# DAG (`etl_dag_factory`, no `log_start`), e só existe depois do `force_all`.
# Estado do dev que provou o buraco: banco com a 079 aplicada e ZERO das 5
# DAGs geradas contendo `_espera.portao` → "Pausar aqui" respondia 200,
# a tela pintava "pausa marcada" e o pipeline passava DIRETO.
#
# Os testes abaixo falham no `main` de hoje.
# ═══════════════════════════════════════════════════════════════════════════

_FONTE_COM_PORTAO = (
    "def log_start(job_name, task_key, **context):\n"
    "    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)\n"
    "    if _espera is not None:\n"
    "        _espera.portao(hook, PIPELINE_NAME, job_name, execution_id)\n"
)
_FONTE_SEM_PORTAO = (
    "def log_start(job_name, task_key, **context):\n"
    "    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)\n"
    "    _exec_telemetry(hook, execution_id, job_name, task_key, 'RUNNING')\n"
)


def _gera_dag(raiz, projeto, dominio, pipeline, fonte):
    destino = raiz / "generated" / projeto / dominio
    destino.mkdir(parents=True, exist_ok=True)
    alvo = destino / f"{pipeline}.py"
    alvo.write_text(fonte, encoding="utf-8")
    return alvo


def test_caminho_da_dag_gerada_e_o_mesmo_que_a_factory_monta():
    """Amarração com `etl_dag_factory`: se o layout de `generated/` mudar lá,
    a sonda passa a olhar para o lugar errado e diria "sem portão" para toda
    DAG do mundo. O fonte da factory é a fonte da verdade."""
    import os as _os
    from pathlib import Path as _Path
    fonte = (_Path(__file__).parent.parent
             / "dags/etl_dag_factory.py").read_text(encoding="utf-8")
    assert 'os.path.join(output_root, "generated", project, domain)' in fonte
    assert 'f"{pname}.py"' in fonte
    _os.environ["DAGS_FOLDER"] = "/opt/airflow/dags"
    caminho = esp.caminho_dag_gerada("PROJ", "DOM", "PIPE")
    assert str(caminho) == "/opt/airflow/dags/generated/PROJ/DOM/PIPE.py"


def test_marca_do_portao_e_a_que_a_factory_emite():
    """A sonda procura `_espera.portao(` — a MESMA chamada que a factory
    escreve dentro do `log_start`. Mudar uma sem a outra é o defeito."""
    from pathlib import Path as _Path
    fonte = (_Path(__file__).parent.parent
             / "dags/etl_dag_factory.py").read_text(encoding="utf-8")
    assert esp.MARCA_PORTAO in fonte


def test_portao_presente_ausente_e_desconhecido(tmp_path):
    """Três estados HONESTOS, e só o do meio é uma acusação."""
    com = _gera_dag(tmp_path, "P", "D", "COM_PORTAO", _FONTE_COM_PORTAO)
    sem = _gera_dag(tmp_path, "P", "D", "SEM_PORTAO", _FONTE_SEM_PORTAO)
    assert esp.portao_no_arquivo(com) == esp.PORTAO_OK
    assert esp.portao_no_arquivo(sem) == esp.PORTAO_AUSENTE
    assert esp.portao_no_arquivo(tmp_path / "nao_existe.py") == esp.PORTAO_DESCONHECIDO
    assert esp.portao_no_arquivo(None) == esp.PORTAO_DESCONHECIDO


def test_cadastro_incompleto_nunca_vira_acusacao():
    """Não saber montar o caminho não é prova de que falta portão — é dúvida.
    (E segmento com `..` não vira travessia de diretório.)"""
    assert esp.caminho_dag_gerada("", "D", "P") is None
    assert esp.caminho_dag_gerada("../etc", "D", "P") is None
    assert esp.caminho_dag_gerada("P", "D", "pipe/../../x") is None
    assert esp.estado_portao(_Cur(erro=RuntimeError("db fora")), "P") \
        == esp.PORTAO_DESCONHECIDO


def test_cache_do_portao_invalida_ao_republicar(tmp_path):
    """Republicar o pipeline tem de mudar a resposta na hora — o cache é por
    (mtime, tamanho), como o de `rerun.capacidade_dags`."""
    import os as _os
    alvo = _gera_dag(tmp_path, "P", "D", "PIPE", _FONTE_SEM_PORTAO)
    assert esp.portao_no_arquivo(alvo) == esp.PORTAO_AUSENTE
    alvo.write_text(_FONTE_COM_PORTAO, encoding="utf-8")
    st = alvo.stat()
    _os.utime(alvo, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    assert esp.portao_no_arquivo(alvo) == esp.PORTAO_OK


def test_estado_portao_le_projeto_e_dominio_do_cadastro(tmp_path, monkeypatch):
    monkeypatch.setenv("DAGS_FOLDER", str(tmp_path))
    _gera_dag(tmp_path, "PROJ", "DOM", "PIPE", _FONTE_COM_PORTAO)

    class _CurCad(_Cur):
        def execute(self, sql, params=()):
            s = " ".join(str(sql).split())
            if s.startswith("SELECT project_name, domain"):
                self._rows = [("PROJ", "DOM")]
                self.sqls.append((s, params))
                return
            return super().execute(sql, params)

    assert esp.estado_portao(_CurCad(), "PIPE") == esp.PORTAO_OK


# ── o gesto: a API RECUSA em vez de prometer ────────────────────────────────

def test_criar_pausa_recusa_pipeline_sem_portao(E):
    """A DECISÃO desta correção, no código: sem portão a pausa **não é
    criada**. Criar com aviso deixaria uma pausa pendente para sempre, que
    ninguém libera (não há o que liberar) e que vira ruído no canvas."""
    import inspect
    src = inspect.getsource(E.criar_pausa)
    assert "estado_portao" in src
    assert "PORTAO_AUSENTE" in src
    # a recusa vem ANTES de qualquer escrita
    assert src.index("PORTAO_AUSENTE") < src.index("espera_svc.criar(")


def test_portao_desconhecido_cria_mas_avisa(E):
    """O único ponto em que este gesto se afasta do `rerun`: lá o desconhecido
    bloqueia a cascata (o gesto principal sobrevive); aqui ele É o gesto."""
    import inspect
    src = inspect.getsource(E.criar_pausa)
    assert "PORTAO_DESCONHECIDO" in src and "avisos.insert(0" in src


def test_estado_do_portao_viaja_no_payload_da_execucao(E):
    """A tela avisa ANTES do clique — descobrir pela recusa é pior."""
    import inspect
    assert '"portao": portao' in inspect.getsource(E.get_pipeline_execucao)
    assert '"portao": portao' in inspect.getsource(E.listar_pausas)


def test_mensagem_do_portao_diz_o_conserto():
    """Frase acionável, no idioma do operador: o que aconteceu E o que fazer
    (o mesmo contrato do AVISO_CASCATA_INDISPONIVEL da F4)."""
    for estado in (esp.PORTAO_AUSENTE, esp.PORTAO_DESCONHECIDO):
        frase = esp.MENSAGEM_PORTAO[estado]
        assert "epublique" in frase or "publicar" in frase
        assert len(frase) > 80


# ── a prova de comportamento: o POST de verdade, ponta a ponta ──────────────

_RUN = "manual__2026-08-03T12:49:24+00:00"


class _DbPausa:
    """Banco de mentira do endpoint de pausa: cadastro, corrida, desenho e as
    escritas. `portao` decide o que o disco (mockado) responde."""

    def __init__(self, *, projeto="PROJ", dominio="DOM"):
        self.projeto = projeto
        self.dominio = dominio
        self.escritas = []
        self._cur = None

    def cursor(self):
        self._cur = _CurPausa(self)
        return self._cur

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _CurPausa:
    def __init__(self, db):
        self.db = db
        self._rows = []
        self.rowcount = 0

    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        s = " ".join(str(sql).split())
        self._rows = []
        self.rowcount = 0
        if s.startswith("SELECT pipeline_name FROM dbo.etl_pipeline WHERE"):
            self._rows = [("DEV_F10_A",)]
        elif s.startswith("SELECT project_name, domain FROM dbo.etl_pipeline"):
            self._rows = [(self.db.projeto, self.db.dominio)]
        elif s.startswith("SELECT config_value FROM dbo.etl_app_config"):
            self._rows = [("00:00",)]
        elif s.startswith("SELECT OBJECT_ID('dbo.etl_pipeline_execucao'"):
            self._rows = [(1,)]
        elif s.startswith("SELECT OBJECT_ID('dbo.etl_etapa_pausa'"):
            self._rows = [(1,)]
        elif s.startswith("SELECT data_referencia, status, inicio, fim, "
                          "disparado_por, motivo FROM dbo.etl_pipeline_execucao"):
            self._rows = [(_D, "EXECUTANDO", None, None, "manual", None)]
        elif s.startswith("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS"):
            self._rows = [("job_name",), ("job_type",), ("execution_order",),
                          ("depends_on_jobs",)]
        elif s.startswith("SELECT job_name, ISNULL(job_type"):
            self._rows = [("etapa_x", "http", 1, None)]
        elif s.startswith("SELECT job_name FROM dbo.etl_job_execution"):
            self._rows = []                      # nenhuma etapa iniciou
        elif s.startswith("SELECT sla_minutos"):
            self._rows = [(None,)]
        elif s.startswith("SELECT TOP (1) id FROM dbo.etl_etapa_pausa"):
            self._rows = [(77,)]
        elif s.startswith("INSERT INTO dbo.etl_etapa_pausa"):
            self.db.escritas.append((s, params))
            self.rowcount = 1
        elif s.startswith("INSERT INTO dbo.etl_pipeline_audit"):
            self.db.escritas.append((s, params))
            self.rowcount = 1
        elif s.startswith("SELECT id, job_name, task_id, estado"):
            self._rows = []
        else:
            raise AssertionError(f"SQL não previsto no dublê: {s[:140]}")

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


@pytest.fixture
def cliente_exec(client, app):
    from deps import PERM_EXECUTAR, get_current_user
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EXECUTAR, "tela_malha"],
    }
    yield client
    app.dependency_overrides.pop(get_current_user, None)


def _post_pausa(cliente, db, monkeypatch, portao):
    from unittest.mock import patch as _patch
    import services.espera as _esp
    monkeypatch.setattr(_esp, "estado_portao", lambda cur, p: portao)
    with _patch("routers.execucoes.get_db_conn", return_value=db):
        return cliente.post("/execucoes/pausas", json={
            "pipeline_name": "DEV_F10_A", "job_name": "etapa_x",
            "dag_run_id": _RUN})


def test_POST_pausa_recusa_quando_a_dag_publicada_nao_tem_portao(
        cliente_exec, monkeypatch):
    """⛔ **O defeito, em uma linha.** Antes desta correção este POST devolvia
    `200 {"ok": true}`, a tela pintava "pausa marcada" e a execução passava
    direto. Agora é 409 com o conserto — e NADA é gravado."""
    db = _DbPausa()
    r = _post_pausa(cliente_exec, db, monkeypatch, esp.PORTAO_AUSENTE)
    assert r.status_code == 409
    det = r.json()["detail"]
    assert det["erro"] == "dag_sem_portao"
    assert "republique" in det["mensagem"].lower()
    assert db.escritas == []          # nenhuma pausa, nenhuma auditoria


def test_POST_pausa_com_portao_ok_cria_normalmente(cliente_exec, monkeypatch):
    """Não-regressão: com o portão publicado o gesto é o de sempre."""
    db = _DbPausa()
    r = _post_pausa(cliente_exec, db, monkeypatch, esp.PORTAO_OK)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["ok"] is True and corpo["portao"] == "ok"
    assert any(s.startswith("INSERT INTO dbo.etl_etapa_pausa")
               for s, _ in db.escritas)


def test_POST_pausa_com_portao_desconhecido_cria_com_aviso_forte(
        cliente_exec, monkeypatch):
    db = _DbPausa()
    r = _post_pausa(cliente_exec, db, monkeypatch, esp.PORTAO_DESCONHECIDO)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["portao"] == "portao_desconhecido"
    assert corpo["avisos"] and "portão de espera" in corpo["avisos"][0]
