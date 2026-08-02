"""
Testes da F5 da retomada — cadastro e visão de dependências
(docs/retomada-f5-desenho.md · aceitação D26–D35 de docs/retomada-aceitacao.md).

Grupos do §10 do desenho cobertos AQUI:
  1. Round-trip D26 (register grava → GET devolve; body parcial não zera nada;
     o body REAL do InactivateModal preserva janela E tabela 067);
  2. Parcialidade de `depends_on` (Decisão 2): ausente = não toca; presente
     vazio = remoção explícita; presente = replace-all com dedup (D27);
  3. `trigger_por_dependencia` ausente → valor preservado (Decisão 3);
  5. GET /pipelines/dependencias/estado (contrato §4.3);
  7. Preview do factory (dependente → cron-string + warning; recusa sem 067);
  8. Flag dag_config_pendente no register (Decisão 6) + migration 073 +
     reconciliador zera;
  9. Auditoria (os 3 em AUDIT_FIELDS; _write_audit pula chave ausente).

O grupo 4 (paridade D29) vive em tests/test_dependencias_f5_paridade.py e o
grupo 6/8-malhas em tests/test_dependencias_f5_malhas.py.

Dublê ESTATAL do banco (padrão test_malhas*): etl_pipeline/etl_pipeline_dependencia
em dicts, com um avaliador genérico de SELECT/UPDATE para o register e o GET
reais serem exercitados de ponta a ponta — sem listas de fetchone por teste.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Replica o mock de pyodbc do conftest (garante o import de api.main mesmo se
# este arquivo for coletado antes do conftest configurar o ambiente).
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, get_current_user

_ROOT = Path(__file__).parent.parent


# ── dublê estatal de etl_pipeline p/ routers.pipelines ───────────────────────

_COLS_INFO = {
    # INFORMATION_SCHEMA.COLUMNS → presença por coluna-sentinela
    "runbook_md": True, "calendario_nome": True, "horarios_especificos": True,
    "dias_horarios_mes": True, "motivo_inativacao": True,
}


def _linha_pipeline(**over):
    """Linha completa de etl_pipeline no formato que o GET devolve (aliases)."""
    base = {
        "pipeline_name": "PIPE_A", "project_name": "BI_CVP", "domain": "GERAL",
        "tags": "ETL", "scheduled_time": "06:00:00", "schedule_type": "daily",
        "schedule_hour": 6, "schedule_minute": 0, "schedule_dow": 1,
        "schedule_dom": 1, "active": 1, "dag_criada": 0,
        "envia_msg_inicio": 1, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "depends_on": None, "dag_start_date": None, "descricao": "desc",
        "criticidade": "Media", "sla_minutos": None, "ambiente": "PROD",
        "max_active_runs": 1, "retries_count": 1, "retry_delay_seconds": 300,
        "pool_name": None, "runbook_md": None, "calendario_nome": None,
        "somente_dias_uteis": 0, "trigger_por_dependencia": 0,
        "horarios_especificos": None, "dias_semana": None,
        "dias_horarios_mes": None, "motivo_inativacao": None,
        "inativado_por": None, "inativado_em": None,
        "hora_virada": None, "nao_iniciar_antes": None,
        # 073 reescrita (achado 2 — TOCTOU): carimbo DATETIME2, não bit.
        "hora_limite_dependencia": None, "dag_config_pendente_em": None,
        "last_execution": None, "created_at": None, "updated_at": None,
    }
    base.update(over)
    return base


def _split_cols(sel: str) -> list:
    """Divide a lista de SELECT respeitando parênteses (CONVERT/CAST/ISNULL)."""
    out, depth, cur = [], 0, []
    for ch in sel:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return out


def _alias(expr: str) -> str:
    up = expr.upper()
    if " AS " in up:
        return expr[up.rindex(" AS ") + 4:].strip()
    return expr.split(".")[-1].strip()


def _valor(row: dict, expr: str):
    """Avalia uma expressão de coluna sobre a linha-dict (aliases)."""
    a = _alias(expr)
    up = " ".join(expr.upper().split())
    v = row.get(a)
    if up.startswith("NULL"):
        return None
    # booleano derivado do carimbo da 073 (contrato do front preservado)
    if "CASE WHEN DAG_CONFIG_PENDENTE_EM IS NOT NULL" in up:
        return 1 if row.get("dag_config_pendente_em") is not None else 0
    if "CONVERT(VARCHAR(5)" in up:
        return str(v)[:5] if v is not None else None
    if up.startswith("ISNULL(") and v is None:
        default = expr[expr.rindex(",") + 1:expr.rindex(")")].strip().strip("'")
        return int(default) if default.isdigit() else default
    return v


class FakePipeDb:
    """etl_pipeline + 067 + execuções/eventos + audit em memória (chave CI)."""

    def __init__(self, pipelines=None, com_067=True, com_073=True, config=None):
        self.pipelines: dict[str, dict] = pipelines or {}
        self.com_067 = com_067
        self.com_073 = com_073
        self.config = config or {}
        self.dependencias: list[dict] = []   # {"pipeline", "depende_de"}
        self.execucoes: list[dict] = []      # {"pipeline","data_referencia","status","inicio","fim","disparado_por","motivo","execution_id"}
        self.eventos: list[dict] = []        # {"pipeline","data_referencia","tipo","detalhe","detectado_em"}
        self.audit: list[tuple] = []         # (field, old, new)
        self.commits = 0

    def _key(self, nome):
        for k in self.pipelines:
            if k.casefold() == str(nome or "").casefold():
                return k
        return None

    def cursor(self):
        return FakePipeCur(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


class FakePipeCur:
    def __init__(self, db: FakePipeDb):
        self.db = db
        self._rows: list[tuple] = []
        self.rowcount = -1
        self.description: list[tuple] = []

    def close(self):
        pass

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    # ── dispatcher ──────────────────────────────────────────────────────────
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        self._rows = []
        self.rowcount = -1
        params = tuple(params)

        # tabelas/colunas presentes
        if "OBJECT_ID('dbo.etl_pipeline_dependencia'" in s:
            self._rows = [(1,)] if db.com_067 else [(None,)]
            return
        if "INFORMATION_SCHEMA.COLUMNS" in s:
            if "'hora_virada'" in s:
                self._rows = [(1 if db.com_067 else 0,)]
            elif "'dag_config_pendente_em'" in s:
                self._rows = [(1 if db.com_073 else 0,)]
            else:
                self._rows = [(1,)]
            return
        if not db.com_067 and ("etl_pipeline_dependencia" in s
                               or "etl_pipeline_execucao" in s
                               or "etl_dependencia_evento" in s):
            raise RuntimeError("Invalid object name (migration 067 ausente)")

        # projetos válidos
        if s.startswith("SELECT project_name FROM dbo.etl_project"):
            self._rows = [("BI_CVP",), ("BI_VIDA",)]
            return
        # config (virada global)
        if s.startswith("SELECT config_value FROM dbo.etl_app_config"):
            self._rows = ([(db.config[params[0]],)] if params[0] in db.config else [])
            return

        # etl_pipeline_dependencia
        if s.startswith("SELECT d.pipeline_name, d.depende_de, CONVERT(VARCHAR(5), p.hora_virada"):
            out = []
            for d in db.dependencias:
                k = db._key(d["pipeline"])
                if k is None or int(db.pipelines[k].get("active") or 0) != 1:
                    continue
                p = db.pipelines[k]
                out.append((k, d["depende_de"],
                            (str(p["hora_virada"])[:5] if p.get("hora_virada") else None),
                            (str(p["nao_iniciar_antes"])[:5] if p.get("nao_iniciar_antes") else None),
                            (str(p["hora_limite_dependencia"])[:5] if p.get("hora_limite_dependencia") else None)))
            self._rows = sorted(out)
            return
        if s.startswith("SELECT dd.depende_de FROM dbo.etl_pipeline_dependencia dd") \
                and "NOT EXISTS" in s:
            # o predicado do PORT — avaliado DE VERDADE sobre o estado
            pipeline, data_ref = params
            falt = []
            for d in db.dependencias:
                if d["pipeline"].casefold() != str(pipeline).casefold():
                    continue
                tem_sucesso = any(
                    e["pipeline"].casefold() == d["depende_de"].casefold()
                    and e["data_referencia"] == data_ref and e["status"] == "SUCESSO"
                    for e in db.execucoes)
                if not tem_sucesso:
                    falt.append((d["depende_de"],))
            self._rows = falt
            return
        if s.startswith("SELECT depende_de FROM dbo.etl_pipeline_dependencia"):
            self._rows = [(d["depende_de"],) for d in db.dependencias
                          if d["pipeline"].casefold() == str(params[0] or "").casefold()]
            return
        if s.startswith("DELETE FROM dbo.etl_pipeline_dependencia"):
            antes = len(db.dependencias)
            db.dependencias = [d for d in db.dependencias
                               if d["pipeline"].casefold() != str(params[0] or "").casefold()]
            self.rowcount = antes - len(db.dependencias)
            return
        if s.startswith("INSERT INTO dbo.etl_pipeline_dependencia"):
            db.dependencias.append({"pipeline": params[0], "depende_de": params[1]})
            return

        # execuções / eventos (estado F5)
        if s.startswith("SELECT pipeline_name, status, inicio, fim, disparado_por, motivo, execution_id"):
            self._rows = [(e["pipeline"], e["status"], e["inicio"], e["fim"],
                           e["disparado_por"], e["motivo"], e["execution_id"])
                          for e in db.execucoes if e["data_referencia"] == params[0]]
            return
        if s.startswith("SELECT pipeline_name, tipo, detalhe, detectado_em"):
            self._rows = [(e["pipeline"], e["tipo"], e["detalhe"], e["detectado_em"])
                          for e in db.eventos if e["data_referencia"] == params[0]]
            return

        # etl_pipeline — leitura
        if s.startswith("SELECT COUNT(*) FROM dbo.etl_pipeline"):
            self._rows = [(len(db.pipelines),)]
            return
        if s.startswith("SELECT 1 FROM dbo.etl_pipeline WHERE"):
            self._rows = [(1,)] if db._key(params[0]) else []
            return
        if s.startswith("SELECT pipeline_name FROM dbo.etl_pipeline WHERE"):
            k = db._key(params[0])
            self._rows = [(k,)] if k else []
            return
        if s.startswith("SELECT depends_on FROM dbo.etl_pipeline WHERE"):
            k = db._key(params[0])
            self._rows = [(db.pipelines[k].get("depends_on"),)] if k else []
            return
        if s.startswith("SELECT CAST(active AS INT) FROM dbo.etl_pipeline"):
            k = db._key(params[0])
            self._rows = [(int(db.pipelines[k].get("active") or 0),)] if k else []
            return
        if s.startswith("SELECT active,"):        # _read_pipeline_record
            if not db.com_067 and "hora_virada" in s:
                raise RuntimeError("Invalid column name 'hora_virada'")
            k = db._key(params[0])
            sel = s[len("SELECT "):s.index(" FROM ")]
            exprs = _split_cols(sel)
            self.description = [(_alias(e),) for e in exprs]
            if k is None:
                self._rows = []
                return
            row = db.pipelines[k]
            valores = []
            for e in exprs:
                a = _alias(e)
                v = row.get(a)
                if "CONVERT(VARCHAR(8)" in e.upper() and v is not None:
                    v = str(v)[:8]
                valores.append(v)
            self._rows = [tuple(valores)]
            return
        if s.startswith("SELECT pipeline_name, project_name, domain, tags,"):
            # data_sql do list_pipelines — avaliador genérico por alias
            sel = s[len("SELECT "):s.index(" FROM ")]
            exprs = _split_cols(sel)
            out = []
            for k in sorted(db.pipelines):
                row = db.pipelines[k]
                out.append(tuple(_valor(row, e) for e in exprs))
            self._rows = out
            return

        # etl_pipeline — escrita
        if s.startswith("EXEC dbo.sp_etl_pipeline_upsert"):
            (nome, horario, stype, sh, sm, sdow, sdom, active,
             ei, ef, ee, dagc, projeto, dominio, tags) = params
            k = db._key(nome)
            if k is None:
                db.pipelines[nome] = _linha_pipeline(pipeline_name=nome)
                k = nome
            db.pipelines[k].update(
                scheduled_time=horario, schedule_type=stype, schedule_hour=sh,
                schedule_minute=sm, schedule_dow=sdow, schedule_dom=sdom,
                active=active, envia_msg_inicio=ei, envia_msg_fim=ef,
                envia_msg_erro=ee, dag_criada=dagc, project_name=projeto,
                domain=dominio, tags=tags)
            return
        if s.startswith("UPDATE dbo.etl_pipeline SET"):
            self._update_pipeline(s, params)
            return

        # auditoria
        if s.startswith("INSERT INTO dbo.etl_pipeline_audit"):
            db.audit.append((params[2], params[3], params[4]))
            return

        raise AssertionError(f"SQL não previsto pelo dublê: {s[:140]}")

    def _update_pipeline(self, s, params):
        db = self.db
        set_part = s[len("UPDATE dbo.etl_pipeline SET "):s.index(" WHERE ")]
        where = s[s.index(" WHERE "):]
        cols = []
        for token in _split_cols(set_part):
            nome, _, valor = token.partition("=")
            cols.append((nome.strip(), valor.strip()))
        if not db.com_073 and any(n == "dag_config_pendente_em" for n, _ in cols):
            raise RuntimeError("Invalid column name 'dag_config_pendente_em'")
        if not db.com_067 and any(n in ("hora_virada", "nao_iniciar_antes",
                                        "hora_limite_dependencia") for n, _ in cols):
            raise RuntimeError("Invalid column name (migration 067 ausente)")
        pname = params[-1] if params else None
        k = db._key(pname)
        if k is None:
            self.rowcount = 0
            return
        row = db.pipelines[k]
        if "dag_criada = 1" in where and int(row.get("dag_criada") or 0) != 1:
            self.rowcount = 0
            return
        i = 0
        for nome, valor in cols:
            if valor == "?":
                row[nome] = params[i]
                i += 1
            elif valor == "NULL":
                row[nome] = None
            elif valor.isdigit():
                row[nome] = int(valor)
            elif valor.upper() == "GETDATE()" and nome == "dag_config_pendente_em":
                row[nome] = datetime.now()   # carimbo da 073 (achado 2)
            # updated_at=GETDATE() e afins: ignorados
        self.rowcount = 1


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_editor(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EDITAR, "tela_pipelines"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch_db(db):
    return patch("routers.pipelines.get_db_conn", return_value=db)


async def _sem_airflow(dag_id, paused):
    return {"attempted": False, "exists": None, "is_paused": None, "error": None}


def _patch_airflow():
    return patch("routers.pipelines._sync_airflow_pause", new=_sem_airflow)


def _body_registro(**over):
    """Body COMPLETO do wizard (chaves de janela e depends_on presentes)."""
    body = {
        "pipeline_name": "PIPE_A", "project_name": "BI_CVP", "domain": "GERAL",
        "tags": "ETL", "descricao": "desc", "active": 1,
        "scheduled_time": "06:00:00", "schedule_type": "daily",
        "schedule_hour": 6, "schedule_minute": 0, "schedule_dow": 1,
        "schedule_dom": 1, "envia_msg_inicio": 1, "envia_msg_fim": 1,
        "envia_msg_erro": 1, "dag_criada": 0, "criticidade": "Media",
        "ambiente": "PROD", "max_active_runs": 1, "retries_count": 1,
        "retry_delay_seconds": 300, "changed_by": "DEV1",
        "depends_on": None,
        "hora_virada": "", "nao_iniciar_antes": "", "hora_limite_dependencia": "",
    }
    body.update(over)
    return body


def _db_com_pais():
    return FakePipeDb(pipelines={
        "PIPE_A": _linha_pipeline(pipeline_name="PIPE_A"),
        "PAI_X": _linha_pipeline(pipeline_name="PAI_X"),
        "PAI_Y": _linha_pipeline(pipeline_name="PAI_Y"),
    })


# ═══════════════ 1. Round-trip D26 (register ↔ GET) ═════════════════════════

def test_register_grava_e_get_devolve_os_tres(client, auth_editor):
    db = _db_com_pais()
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=_body_registro(
            hora_virada="20:00", nao_iniciar_antes="08:00",
            hora_limite_dependencia="11:30", depends_on="PAI_X"))
        assert r.status_code == 200
        g = client.get("/pipelines?limit=100")
    assert db.pipelines["PIPE_A"]["hora_virada"] == "20:00:00"
    assert db.pipelines["PIPE_A"]["nao_iniciar_antes"] == "08:00:00"
    assert db.pipelines["PIPE_A"]["hora_limite_dependencia"] == "11:30:00"
    rec = next(p for p in g.json()["data"] if p["pipeline_name"] == "PIPE_A")
    # GET devolve 'HH:MM' — a metade que faltava do round-trip (D26)
    assert rec["hora_virada"] == "20:00"
    assert rec["nao_iniciar_antes"] == "08:00"
    assert rec["hora_limite_dependencia"] == "11:30"
    assert rec["dag_config_pendente"] == 0


def test_body_parcial_nao_zera_janela_nem_dependencias(client, auth_editor):
    """Chaves AUSENTES = "não mexa": editar só a descrição preserva os três da
    janela E a tabela 067 E o CSV — a classe C1 morta por contrato."""
    db = _db_com_pais()
    db.pipelines["PIPE_A"].update(hora_virada="20:00:00",
                                  nao_iniciar_antes="08:00:00",
                                  hora_limite_dependencia="11:30:00",
                                  depends_on="PAI_X")
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    body = _body_registro(descricao="nova descrição")
    for chave in ("depends_on", "hora_virada", "nao_iniciar_antes",
                  "hora_limite_dependencia"):
        body.pop(chave)
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=body)
    assert r.status_code == 200
    assert db.pipelines["PIPE_A"]["hora_virada"] == "20:00:00"
    assert db.pipelines["PIPE_A"]["nao_iniciar_antes"] == "08:00:00"
    assert db.pipelines["PIPE_A"]["hora_limite_dependencia"] == "11:30:00"
    assert db.pipelines["PIPE_A"]["depends_on"] == "PAI_X"
    assert db.dependencias == [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]


def test_body_do_inactivate_modal_real_nao_zera_nada(client, auth_editor):
    """O body LITERAL do InactivateModal (PipelineModals.tsx) — sem depends_on,
    sem janela, sem trigger E sem os 5 da agenda rica (achado 3): inativar não
    zera NADA e NÃO liga a pendência de publicação (o teste-régua do D26)."""
    db = _db_com_pais()
    db.pipelines["PIPE_A"].update(hora_virada="20:00:00",
                                  nao_iniciar_antes="08:00:00",
                                  hora_limite_dependencia="11:30:00",
                                  depends_on="PAI_X,PAI_Y",
                                  trigger_por_dependencia=1,
                                  # agenda rica (achado 3): o wipe que a flag
                                  # da 073 passou a expor
                                  horarios_especificos="06:00,12:00",
                                  dias_semana="1,3,5",
                                  calendario_nome="FERIADOS_B3",
                                  somente_dias_uteis=1,
                                  dias_horarios_mes='[{"dia": 5, "horarios": ["09:00"]}]',
                                  dag_criada=1)
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"},
                       {"pipeline": "PIPE_A", "depende_de": "PAI_Y"}]
    body = {   # espelho do mutationFn do InactivateModal
        "motivo_inativacao": "aguardando correção da origem",
        "pipeline_name": "PIPE_A", "scheduled_time": "06:00:00",
        "schedule_type": "daily", "schedule_hour": 6, "schedule_minute": 0,
        "schedule_dow": 1, "schedule_dom": 1, "active": 0,
        "envia_msg_inicio": 1, "envia_msg_fim": 1, "envia_msg_erro": 1,
        "project_name": "BI_CVP", "domain": "GERAL", "tags": "ETL",
        "dag_criada": 1, "descricao": "desc", "criticidade": "Media",
        "sla_minutos": None, "ambiente": "PROD", "max_active_runs": 1,
        "retries_count": 1, "retry_delay_seconds": 300, "pool_name": None,
        "runbook_md": None, "dag_start_date": None, "changed_by": "DEV1",
    }
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=body)
    assert r.status_code == 200
    p = db.pipelines["PIPE_A"]
    assert p["active"] == 0                        # o gesto pedido aconteceu
    assert p["hora_virada"] == "20:00:00"          # …e NADA alheio foi zerado
    assert p["nao_iniciar_antes"] == "08:00:00"
    assert p["hora_limite_dependencia"] == "11:30:00"
    assert p["depends_on"] == "PAI_X,PAI_Y"
    assert p["trigger_por_dependencia"] == 1
    assert len(db.dependencias) == 2
    # os 5 da agenda rica intactos (achado 3)
    assert p["horarios_especificos"] == "06:00,12:00"
    assert p["dias_semana"] == "1,3,5"
    assert p["calendario_nome"] == "FERIADOS_B3"
    assert p["somente_dias_uteis"] == 1
    assert p["dias_horarios_mes"] == '[{"dia": 5, "horarios": ["09:00"]}]'
    # e a pendência de publicação NÃO ligou (nada que afeta a DAG mudou)
    assert p["dag_config_pendente_em"] is None


def test_inactivate_de_monthly_days_times_preserva_e_nao_422(client, auth_editor):
    """Antes do achado 3, inativar um pipeline 'monthly_days_times' dava 422
    ("dias_horarios_mes é obrigatório") porque o body do modal não traz a
    chave — agora o valor EFETIVO vem do banco e o gesto passa."""
    db = _db_com_pais()
    db.pipelines["PIPE_A"].update(
        schedule_type="monthly_days_times",
        dias_horarios_mes='[{"dia": 5, "horarios": ["09:00"]}]')
    body = {
        "motivo_inativacao": "pausa de safra", "pipeline_name": "PIPE_A",
        "scheduled_time": "09:00:00", "schedule_type": "monthly_days_times",
        "schedule_hour": 9, "schedule_minute": 0, "schedule_dow": 1,
        "schedule_dom": 1, "active": 0, "envia_msg_inicio": 1,
        "envia_msg_fim": 1, "envia_msg_erro": 1, "project_name": "BI_CVP",
        "domain": "GERAL", "tags": "ETL", "dag_criada": 0,
        "descricao": "desc", "criticidade": "Media", "sla_minutos": None,
        "ambiente": "PROD", "max_active_runs": 1, "retries_count": 1,
        "retry_delay_seconds": 300, "pool_name": None, "runbook_md": None,
        "dag_start_date": None, "changed_by": "DEV1",
    }
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=body)
    assert r.status_code == 200
    assert db.pipelines["PIPE_A"]["dias_horarios_mes"] == '[{"dia": 5, "horarios": ["09:00"]}]'


def test_monthly_days_times_sem_chave_e_sem_valor_vigente_422(client, auth_editor):
    """A parcialidade do achado 3 NÃO afrouxa a criação: pipeline novo (ou sem
    valor vigente) com 'monthly_days_times' e chave ausente segue 422."""
    db = _db_com_pais()
    body = _body_registro(pipeline_name="PIPE_NOVO",
                          schedule_type="monthly_days_times")
    assert "dias_horarios_mes" not in body
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=body)
    assert r.status_code == 422
    assert "dias_horarios_mes" in r.json()["detail"]
    assert "PIPE_NOVO" not in db.pipelines


def test_agenda_rica_ausente_preserva_os_cinco(client, auth_editor):
    """Achado 3: chave AUSENTE = preserva — para CADA um dos 5 campos de
    agenda rica (o wipe do InactivateModal, morto na raiz)."""
    db = _db_com_pais()
    db.pipelines["PIPE_A"].update(horarios_especificos="06:00,12:00",
                                  dias_semana="1,3,5",
                                  calendario_nome="FERIADOS_B3",
                                  somente_dias_uteis=1,
                                  dias_horarios_mes='[{"dia": 5, "horarios": ["09:00"]}]')
    body = _body_registro(descricao="só cadastro")
    for chave in ("horarios_especificos", "dias_semana", "calendario_nome",
                  "somente_dias_uteis", "dias_horarios_mes"):
        assert chave not in body
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=body)
    assert r.status_code == 200
    p = db.pipelines["PIPE_A"]
    assert p["horarios_especificos"] == "06:00,12:00"
    assert p["dias_semana"] == "1,3,5"
    assert p["calendario_nome"] == "FERIADOS_B3"
    assert p["somente_dias_uteis"] == 1
    assert p["dias_horarios_mes"] == '[{"dia": 5, "horarios": ["09:00"]}]'


def test_agenda_rica_presente_continua_gravando_e_vazio_limpa(client, auth_editor):
    """Compat do fluxo normal: o PipelineFormModal SEMPRE envia as 5 chaves
    (base do buildSchedulePayload) — presente grava, null/'' limpa de verdade."""
    db = _db_com_pais()
    db.pipelines["PIPE_A"].update(horarios_especificos="06:00,12:00",
                                  dias_semana="1,3", calendario_nome="CAL",
                                  somente_dias_uteis=1,
                                  dias_horarios_mes='[{"dia": 5, "horarios": ["09:00"]}]')
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=_body_registro(
            horarios_especificos=None, dias_semana=None, calendario_nome=None,
            somente_dias_uteis=0, dias_horarios_mes=None))
    assert r.status_code == 200
    p = db.pipelines["PIPE_A"]
    assert p["horarios_especificos"] is None
    assert p["dias_semana"] is None
    assert p["calendario_nome"] is None
    assert p["somente_dias_uteis"] == 0
    assert p["dias_horarios_mes"] is None


def test_hora_vazia_vira_null_e_invalida_vira_null_com_aviso(client, auth_editor):
    """D35: '' → NULL ('sem regra' ≠ 'regra às 00:00'); inválida → NULL SEM
    recusar o cadastro, mas com aviso no payload — nunca silêncio."""
    db = _db_com_pais()
    db.pipelines["PIPE_A"].update(hora_virada="20:00:00")
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=_body_registro(
            hora_virada="", nao_iniciar_antes="25:99", hora_limite_dependencia="lixo"))
    assert r.status_code == 200
    assert db.pipelines["PIPE_A"]["hora_virada"] is None
    assert db.pipelines["PIPE_A"]["nao_iniciar_antes"] is None
    assert db.pipelines["PIPE_A"]["hora_limite_dependencia"] is None
    avisos = r.json()["avisos"]
    assert len(avisos) == 2
    assert any("nao_iniciar_antes" in a for a in avisos)
    assert any("hora_limite_dependencia" in a for a in avisos)


def test_normalizacao_hhmm_para_hhmmss(client, auth_editor):
    db = _db_com_pais()
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=_body_registro(
            hora_virada="8:5", nao_iniciar_antes="23:59:30"))
    assert r.status_code == 200
    assert r.json()["avisos"] == []
    assert db.pipelines["PIPE_A"]["hora_virada"] == "08:05:00"
    assert db.pipelines["PIPE_A"]["nao_iniciar_antes"] == "23:59:30"


def test_get_degrada_janela_e_flag_para_null_sem_067_073(client, auth_editor):
    """Deploy parcial: sem as colunas, o GET devolve NULL (o front não
    renderiza) — nunca um 500."""
    db = FakePipeDb(pipelines={"PIPE_A": _linha_pipeline(hora_virada="20:00:00")},
                    com_067=False, com_073=False)
    with _patch_db(db):
        g = client.get("/pipelines?limit=100")
    assert g.status_code == 200
    rec = g.json()["data"][0]
    assert rec["hora_virada"] is None
    assert rec["nao_iniciar_antes"] is None
    assert rec["hora_limite_dependencia"] is None
    assert rec["dag_config_pendente"] is None


def test_register_janela_degrada_sem_067(client, auth_editor):
    """Chave presente sem a coluna: try/except com log, cadastro segue (risco
    'Deploy parcial: API F5 sem a 067' do desenho §8)."""
    db = FakePipeDb(pipelines={"PIPE_A": _linha_pipeline()},
                    com_067=False, com_073=False)
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register",
                        json=_body_registro(hora_virada="20:00"))
    assert r.status_code == 200


# ═══════════════ 2. Parcialidade de depends_on (Decisão 2) ══════════════════

def test_depends_on_ausente_nao_toca_tabela_nem_csv(client, auth_editor):
    db = _db_com_pais()
    db.pipelines["PIPE_A"]["depends_on"] = "PAI_X"
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    body = _body_registro()
    body.pop("depends_on")
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=body)
    assert r.status_code == 200
    assert db.dependencias == [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    assert db.pipelines["PIPE_A"]["depends_on"] == "PAI_X"


def test_depends_on_presente_vazio_e_remocao_explicita(client, auth_editor):
    db = _db_com_pais()
    db.pipelines["PIPE_A"]["depends_on"] = "PAI_X"
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=_body_registro(depends_on=""))
    assert r.status_code == 200
    assert db.dependencias == []
    assert db.pipelines["PIPE_A"]["depends_on"] is None


def test_depends_on_presente_replace_all_com_dedup_e_canonizacao(client, auth_editor):
    """D27 não-regressão: 'pai_x, PAI_X ,pai_y' → dedup CI + grafia canonizada
    pela registrada em etl_pipeline."""
    db = _db_com_pais()
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register",
                        json=_body_registro(depends_on="pai_x, PAI_X ,pai_y"))
    assert r.status_code == 200
    assert db.dependencias == [{"pipeline": "PIPE_A", "depende_de": "PAI_X"},
                               {"pipeline": "PIPE_A", "depende_de": "PAI_Y"}]
    assert db.pipelines["PIPE_A"]["depends_on"] == "pai_x,pai_y"


def test_depends_on_inexistente_422_nao_grava(client, auth_editor):
    db = _db_com_pais()
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register",
                        json=_body_registro(depends_on="FANTASMA"))
    assert r.status_code == 422
    assert "'FANTASMA'" in r.json()["detail"]
    assert db.dependencias == [] and db.commits == 0


# ═══════════════ 3. trigger_por_dependencia (Decisão 3) ═════════════════════

def test_trigger_ausente_preserva_valor_atual(client, auth_editor):
    """Zerar aqui, num deploy API-antes-de-dags/, ressuscitava o sensor na
    regeneração (QA1/QA2) — chave ausente preserva."""
    db = _db_com_pais()
    db.pipelines["PIPE_A"]["trigger_por_dependencia"] = 1
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=_body_registro())
    assert r.status_code == 200
    assert db.pipelines["PIPE_A"]["trigger_por_dependencia"] == 1


def test_trigger_presente_continua_gravando(client, auth_editor):
    """Compat: import CSV/scripts que enviam a chave de propósito seguem valendo."""
    db = _db_com_pais()
    db.pipelines["PIPE_A"]["trigger_por_dependencia"] = 1
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register",
                        json=_body_registro(trigger_por_dependencia=0))
    assert r.status_code == 200
    assert db.pipelines["PIPE_A"]["trigger_por_dependencia"] == 0


# ═══════════════ 5. GET /pipelines/dependencias/estado (§4.3) ═══════════════

_D = date(2026, 8, 1)


def _exec(pipeline, status, data_ref=_D, inicio=None, execution_id="run_1", **over):
    e = {"pipeline": pipeline, "data_referencia": data_ref, "status": status,
         "inicio": inicio, "fim": None, "disparado_por": None, "motivo": None,
         "execution_id": execution_id}
    e.update(over)
    return e


def test_rota_estado_registrada(client):
    r = client.get("/openapi.json")
    assert "/pipelines/dependencias/estado" in r.json().get("paths", {})


def test_estado_sem_auth_401(client):
    assert client.get("/pipelines/dependencias/estado").status_code == 401


def test_estado_data_malformada_422(client, auth_editor):
    db = _db_com_pais()
    with _patch_db(db):
        for ruim in ("01/08/2026", "2026-13-01", "hoje"):
            r = client.get(f"/pipelines/dependencias/estado?data_referencia={ruim}")
            assert r.status_code == 422, ruim
            assert "YYYY-MM-DD" in r.json()["detail"]


def test_estado_degrada_sem_067(client, auth_editor):
    db = FakePipeDb(pipelines={"PIPE_A": _linha_pipeline()}, com_067=False)
    with _patch_db(db):
        r = client.get("/pipelines/dependencias/estado?data_referencia=2026-08-01")
    assert r.status_code == 200
    body = r.json()
    assert body["data"] == []
    assert body["migration_067_pendente"] is True


def test_estado_pulado_intercalado_com_sucesso_libera(client, auth_editor):
    """O caso que o endpoint da 1ª F5 ERRAVA (B2/D14): PULADO mais recente não
    mascara o SUCESSO do dia — liberado pelo EXISTS do port, com o PULADO
    aparecendo como status de EXIBIÇÃO do predecessor."""
    db = _db_com_pais()
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    db.execucoes = [
        _exec("PAI_X", "SUCESSO", inicio=datetime(2026, 8, 1, 6, 0), execution_id="run_06"),
        _exec("PAI_X", "PULADO", inicio=datetime(2026, 8, 1, 12, 0), execution_id="run_12"),
    ]
    with _patch_db(db):
        r = client.get("/pipelines/dependencias/estado?data_referencia=2026-08-01")
    assert r.status_code == 200
    item = r.json()["data"][0]
    assert item["pipeline_name"] == "PIPE_A"
    assert item["liberado"] is True
    assert item["faltantes"] == []
    assert item["predecessores"] == [
        {"nome": "PAI_X", "status": "PULADO", "sucesso_na_data": True}]


def test_estado_faltantes_e_o_motivo_legivel(client, auth_editor):
    db = _db_com_pais()
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"},
                       {"pipeline": "PIPE_A", "depende_de": "PAI_Y"}]
    db.execucoes = [
        _exec("PAI_X", "SUCESSO", inicio=datetime(2026, 8, 1, 6, 0)),
        _exec("PAI_Y", "FALHA", inicio=datetime(2026, 8, 1, 7, 0)),
        _exec("PIPE_A", "AGUARDANDO_DEPENDENCIA", execution_id="dep__run"),
    ]
    with _patch_db(db):
        r = client.get("/pipelines/dependencias/estado?data_referencia=2026-08-01")
    item = r.json()["data"][0]
    assert item["liberado"] is False
    assert item["faltantes"] == ["PAI_Y"]
    assert item["corrida"]["status"] == "AGUARDANDO_DEPENDENCIA"
    assert item["corrida"]["execution_id"] == "dep__run"


def test_estado_corrida_pela_regra_f9_empate_por_execution_id(client, auth_editor):
    db = _db_com_pais()
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    inicio = datetime(2026, 8, 1, 6, 0)
    db.execucoes = [
        _exec("PIPE_A", "FALHA", inicio=inicio, execution_id="run_1"),
        _exec("PIPE_A", "EXECUTANDO", inicio=inicio, execution_id="run_2"),
    ]
    with _patch_db(db):
        r = client.get("/pipelines/dependencias/estado?data_referencia=2026-08-01")
    assert r.json()["data"][0]["corrida"]["status"] == "EXECUTANDO"


def test_estado_sucesso_em_outra_data_nao_libera(client, auth_editor):
    db = _db_com_pais()
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    db.execucoes = [_exec("PAI_X", "SUCESSO", data_ref=date(2026, 7, 31),
                          inicio=datetime(2026, 7, 31, 6, 0))]
    with _patch_db(db):
        r = client.get("/pipelines/dependencias/estado?data_referencia=2026-08-01")
    item = r.json()["data"][0]
    assert item["liberado"] is False and item["faltantes"] == ["PAI_X"]


def test_estado_eventos_e_janela(client, auth_editor):
    db = _db_com_pais()
    db.pipelines["PIPE_A"].update(hora_virada="20:00:00",
                                  nao_iniciar_antes="08:00:00",
                                  hora_limite_dependencia="11:00:00")
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    db.eventos = [{"pipeline": "PIPE_A", "data_referencia": _D,
                   "tipo": "JANELA_ESTOUROU", "detalhe": "limite 11:00",
                   "detectado_em": datetime(2026, 8, 1, 11, 5)},
                  {"pipeline": "PIPE_A", "data_referencia": date(2026, 7, 31),
                   "tipo": "JANELA_ESTOUROU", "detalhe": "outra data: não aparece",
                   "detectado_em": datetime(2026, 7, 31, 11, 5)}]
    with _patch_db(db):
        r = client.get("/pipelines/dependencias/estado?data_referencia=2026-08-01")
    item = r.json()["data"][0]
    assert item["janela"] == {"hora_virada": "20:00", "nao_iniciar_antes": "08:00",
                              "hora_limite_dependencia": "11:00"}
    assert item["eventos"] == [{"tipo": "JANELA_ESTOUROU", "detalhe": "limite 11:00",
                                "detectado_em": "2026-08-01 11:05:00"}]


def test_estado_so_dependentes_ativos_entram(client, auth_editor):
    db = _db_com_pais()
    db.pipelines["PIPE_A"]["active"] = 0
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    with _patch_db(db):
        r = client.get("/pipelines/dependencias/estado?data_referencia=2026-08-01")
    assert r.json()["data"] == []


def test_estado_sem_data_usa_odate_da_virada_global(client, auth_editor):
    """Mesma regra/aproximação do F9: 23:30 com virada global 20:00 → 01/08."""
    db = _db_com_pais()
    db.config = {"dependencia_hora_virada": "20:00"}
    db.dependencias = [{"pipeline": "PIPE_A", "depende_de": "PAI_X"}]
    with _patch_db(db), patch("routers.pipelines._agora",
                              return_value=datetime(2026, 7, 31, 23, 30)):
        r = client.get("/pipelines/dependencias/estado")
    assert r.json()["data_referencia"] == "2026-08-01"


# ═══════════════ 7. Preview do factory (§6) ═════════════════════════════════

_PREVIEW_COLS = (
    "pipeline_name", "project_name", "domain", "tags", "scheduled_time",
    "schedule_type", "schedule_hour", "schedule_minute", "schedule_dow",
    "schedule_dom", "horarios_especificos", "dias_semana", "somente_dias_uteis",
    "envia_msg_inicio", "envia_msg_fim", "envia_msg_erro", "depends_on",
    "calendario_nome", "retries_count", "retry_delay_seconds",
    "max_active_runs", "pool_name", "criticidade", "sla_minutos", "ambiente",
    "runbook_md", "ssh_conn_id", "dag_criada",
)


class FakeFactoryDb:
    def __init__(self, pipeline, deps_067=None, com_067=True):
        self.pipeline = pipeline          # dict por nome de coluna
        self.deps_067 = deps_067 or []    # linhas da tabela 067
        self.com_067 = com_067

    def cursor(self):
        return FakeFactoryCur(self)

    def close(self):
        pass


class FakeFactoryCur:
    def __init__(self, db):
        self.db = db
        self._rows = []

    def close(self):
        pass

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def execute(self, sql, params=()):
        s = " ".join(str(sql).split())
        self._rows = []
        if "trigger_por_dependencia" in s:
            raise AssertionError("trigger_por_dependencia saiu do SELECT do preview (F5 §6)")
        if s.startswith("SELECT pipeline_name, project_name"):
            self._rows = [tuple(self.db.pipeline.get(c) for c in _PREVIEW_COLS)]
            return
        if "etl_pipeline_dependencia" in s:
            if not self.db.com_067:
                raise RuntimeError("Invalid object name 'dbo.etl_pipeline_dependencia'")
            self._rows = [(d,) for d in self.db.deps_067]
            return
        if "etl_pipeline_job" in s:
            self._rows = [("JOB_1", 1, "python", "mod.run", None, 0)]
            return
        raise AssertionError(f"SQL não previsto pelo dublê do preview: {s[:120]}")


def _pipeline_preview(**over):
    base = {c: None for c in _PREVIEW_COLS}
    base.update(pipeline_name="PIPE_A", project_name="BI_CVP", domain="GERAL",
                scheduled_time="06:00:00", schedule_type="daily",
                schedule_hour=6, schedule_minute=0, somente_dias_uteis=0,
                envia_msg_inicio=1, envia_msg_fim=1, envia_msg_erro=1,
                retries_count=1, retry_delay_seconds=300, max_active_runs=1,
                criticidade="Media", ambiente="PROD", dag_criada=1)
    base.update(over)
    return base


def _preview(client, db):
    with patch("routers.factory.get_db_conn", return_value=db), \
            patch("routers.factory.recheck_geradas"):
        return client.get("/factory/preview?pipeline_name=PIPE_A")


def test_preview_dependente_cron_string_e_warning(client, auth_editor):
    db = FakeFactoryDb(_pipeline_preview(), deps_067=["PAI_X", "PAI_Y"])
    r = _preview(client, db)
    assert r.status_code == 200
    body = r.json()
    assert body["cron"] == "(sem agendamento — disparo pelos predecessores: PAI_X, PAI_Y)"
    assert body["depends_on"] == "PAI_X,PAI_Y"
    assert "trigger_dep" not in body
    assert any("schedule=None" in w for w in body["warnings"])


def test_preview_csv_sem_067_warning_de_recusa(client, auth_editor):
    """Dependência que só existe no CSV, sem a tabela: o preview espelha a
    recusa ruidosa do factory (F3 Decisão 6) em vez de prometer geração."""
    db = FakeFactoryDb(_pipeline_preview(depends_on="PAI_X"), com_067=False)
    r = _preview(client, db)
    assert r.status_code == 200
    body = r.json()
    assert "disparo pelos predecessores: PAI_X" in body["cron"]
    assert any("migration 067 ausente" in w and "recusada" in w
               for w in body["warnings"])


def test_preview_sem_dependencia_resposta_intacta(client, auth_editor):
    """Sem dependência o preview responde como sempre (cron intacto byte a
    byte; nenhum warning novo) — só a chave trigger_dep saiu, por decisão
    registrada no desenho (§6)."""
    db = FakeFactoryDb(_pipeline_preview())
    r = _preview(client, db)
    assert r.status_code == 200
    body = r.json()
    assert body["cron"] == "0 6 * * *"
    assert body["warnings"] == []
    assert body["depends_on"] is None
    assert "trigger_dep" not in body


# ═══════════════ 8. Flag dag_config_pendente (Decisão 6) ════════════════════
# 073 reescrita (achado 2): "ligar" = gravar o carimbo GETDATE() em
# dag_config_pendente_em; "desligada" = NULL. O GET segue expondo o booleano.

def test_register_mudanca_de_agendamento_liga_flag_com_carimbo(client, auth_editor):
    db = _db_com_pais()
    db.pipelines["PIPE_A"].update(dag_criada=1)
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=_body_registro(
            dag_criada=1, schedule_hour=9, scheduled_time="09:00:00"))
        g = client.get("/pipelines?limit=100")
    assert r.status_code == 200
    carimbo = db.pipelines["PIPE_A"]["dag_config_pendente_em"]
    assert isinstance(carimbo, datetime)      # QUANDO a pendência nasceu
    rec = next(p for p in g.json()["data"] if p["pipeline_name"] == "PIPE_A")
    assert rec["dag_config_pendente"] == 1    # contrato booleano do front


def test_register_mudanca_so_de_descricao_nao_liga_flag(client, auth_editor):
    db = _db_com_pais()
    db.pipelines["PIPE_A"].update(dag_criada=1)
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=_body_registro(
            dag_criada=1, descricao="descrição nova"))
    assert r.status_code == 200
    assert db.pipelines["PIPE_A"]["dag_config_pendente_em"] is None


def test_register_mudanca_so_de_sla_liga_flag(client, auth_editor):
    """Achado 1 da revisão: sla_minutos vira dagrun_timeout no gerador —
    editar SÓ o SLA deixa a DAG publicada para trás e TEM que ligar a flag."""
    db = _db_com_pais()
    db.pipelines["PIPE_A"].update(dag_criada=1, sla_minutos=60)
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=_body_registro(
            dag_criada=1, sla_minutos=90))
    assert r.status_code == 200
    assert db.pipelines["PIPE_A"]["dag_config_pendente_em"] is not None


def test_register_sla_igual_nao_liga_flag(client, auth_editor):
    db = _db_com_pais()
    db.pipelines["PIPE_A"].update(dag_criada=1, sla_minutos=60)
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=_body_registro(
            dag_criada=1, sla_minutos=60))
    assert r.status_code == 200
    assert db.pipelines["PIPE_A"]["dag_config_pendente_em"] is None


def test_register_dag_nunca_criada_nao_liga_flag(client, auth_editor):
    db = _db_com_pais()
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=_body_registro(
            schedule_hour=9, scheduled_time="09:00:00"))
    assert r.status_code == 200
    assert db.pipelines["PIPE_A"]["dag_config_pendente_em"] is None


def test_register_flag_degrada_sem_073(client, auth_editor):
    db = _db_com_pais()
    db.com_073 = False
    db.pipelines["PIPE_A"].update(dag_criada=1)
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=_body_registro(
            dag_criada=1, schedule_hour=9, scheduled_time="09:00:00"))
    assert r.status_code == 200           # comportamento = hoje, sem erro
    assert db.pipelines["PIPE_A"]["dag_config_pendente_em"] is None


def test_janela_mudada_liga_flag(client, auth_editor):
    db = _db_com_pais()
    db.pipelines["PIPE_A"].update(dag_criada=1)
    with _patch_db(db), _patch_airflow():
        r = client.post("/pipelines/register", json=_body_registro(
            dag_criada=1, hora_virada="20:00"))
    assert r.status_code == 200
    assert db.pipelines["PIPE_A"]["dag_config_pendente_em"] is not None


class _CurLog:
    """Cursor-dublê que loga (sql, params) e aplica o clear CONDICIONAL da 073
    sobre um estado {pipeline: carimbo|None} — simula o `<=` do SQL Server."""

    def __init__(self, log, flags):
        self.log = log
        self.flags = flags

    def execute(self, sql, params=()):
        s = " ".join(str(sql).split())
        self.log.append((s, tuple(params)))
        if s.startswith("UPDATE dbo.etl_pipeline SET dag_config_pendente_em = NULL"):
            nome, inicio = params
            atual = self.flags.get(nome)
            if atual is not None and atual <= inicio:
                self.flags[nome] = None

    def fetchone(self):
        return None

    def close(self):
        pass


class _ConnLog:
    def __init__(self, log, flags):
        self.log = log
        self.flags = flags

    def cursor(self):
        return _CurLog(self.log, self.flags)

    def commit(self):
        pass

    def close(self):
        pass


def _finaliza_ok(monkeypatch, criado_em, flags):
    import services.dag_reconcile as dr
    executados: list = []
    monkeypatch.setattr(dr, "get_db_conn", lambda: _ConnLog(executados, flags))
    monkeypatch.setattr(dr, "add_notificacao", lambda *a, **k: None)
    dr._finalize({"id": 1, "pipeline_name": "PIPE_A", "matricula": "DEV1",
                  "desired_paused": False, "idade_s": 5, "dag_run_id": None,
                  "criado_em": criado_em},
                 found=True, import_trace=None)
    return executados


def test_reconciliador_zera_flag_ao_concluir(monkeypatch):
    """_finalize (found=True, sem import error) limpa a pendência no MESMO
    passo em que notifica (Decisão 6) — clear condicionado ao carimbo <=
    início da publicação (criado_em de etl_dag_pendente; achado 2)."""
    inicio = datetime(2026, 8, 1, 10, 0, 0)
    flags = {"PIPE_A": datetime(2026, 8, 1, 9, 55, 0)}   # ligada ANTES do início
    executados = _finaliza_ok(monkeypatch, inicio, flags)
    assert any("SET dag_config_pendente_em = NULL" in s
               and "dag_config_pendente_em <= ?" in s
               and p == ("PIPE_A", inicio)
               for s, p in executados)
    assert flags["PIPE_A"] is None                       # pendência velha limpa


def test_reconciliador_toctou_edicao_em_voo_sobrevive(monkeypatch):
    """O TOCTOU do achado 2: publicação INICIADA em t0; operador edita com a
    publicação em voo (carimbo t1 > t0); a publicação conclui e o clear usa
    <= t0 → a pendência NOVA sobrevive (a DAG publicada não a contém)."""
    t0 = datetime(2026, 8, 1, 10, 0, 0)                  # início da publicação
    t1 = datetime(2026, 8, 1, 10, 2, 0)                  # edição DURANTE o voo
    flags = {"PIPE_A": t1}
    _finaliza_ok(monkeypatch, t0, flags)
    assert flags["PIPE_A"] == t1                         # flag sobrevive


def test_reconciliador_sem_inicio_nao_limpa(monkeypatch):
    """Defensivo: sem criado_em não há como saber a foto publicada — NÃO limpa
    (falso-pendente é recuperável; pendência escondida não é)."""
    flags = {"PIPE_A": datetime(2026, 8, 1, 9, 0, 0)}
    executados = _finaliza_ok(monkeypatch, None, flags)
    assert not any("dag_config_pendente_em" in s for s, _ in executados)
    assert flags["PIPE_A"] is not None


def test_reconciliador_nao_zera_em_timeout(monkeypatch):
    import services.dag_reconcile as dr
    executados: list = []

    class Cur:
        def execute(self, sql, params=()):
            executados.append(" ".join(str(sql).split()))

        def fetchone(self):
            return None

        def close(self):
            pass

    class Conn:
        def cursor(self):
            return Cur()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(dr, "get_db_conn", lambda: Conn())
    monkeypatch.setattr(dr, "add_notificacao", lambda *a, **k: None)
    dr._finalize({"id": 1, "pipeline_name": "PIPE_A", "matricula": "DEV1",
                  "desired_paused": False, "idade_s": 10 ** 6, "dag_run_id": None},
                 found=False, import_trace=None)
    assert not any("dag_config_pendente" in s for s in executados)


# ═══════════════ 8b. Migration 073 ══════════════════════════════════════════

def test_migration_073_idempotente_por_guard():
    """Sem SQL Server no CI, a idempotência é garantida POR CONSTRUÇÃO: 073
    reescrita (achado 2 — TOCTOU) em três estados — nova já existe (skip),
    BIT antiga do dev (converte + dropa), nada (ADD)."""
    sql = (_ROOT / "sql/migrations/073_dag_config_pendente.sql").read_text(encoding="utf-8")
    # estado 1/3: ADD da nova atrás de COL_LENGTH IS NULL, com ELSE
    assert "IF COL_LENGTH('dbo.etl_pipeline', 'dag_config_pendente_em') IS NULL" in sql
    assert "ADD dag_config_pendente_em DATETIME2 NULL" in sql
    assert "ELSE" in sql
    # estado 2: conversão da BIT antiga (aplicada só no dev) — guardada por
    # COL_LENGTH + checagem de tipo em sys.columns, bit=1 vira carimbo, e a
    # coluna morta sai via SQL dinâmico (compilação dos runs seguintes)
    assert "IF COL_LENGTH('dbo.etl_pipeline', 'dag_config_pendente') IS NOT NULL" in sql
    assert "t.name = 'bit'" in sql
    assert "sp_executesql" in sql
    assert "WHERE dag_config_pendente = 1" in sql
    assert "AND dag_config_pendente_em IS NULL" in sql
    assert "DROP CONSTRAINT DF_etl_pipeline_dag_config_pendente" in sql
    assert "DROP COLUMN dag_config_pendente" in sql


# ═══════════════ 9. Auditoria ═══════════════════════════════════════════════

def test_os_tres_da_janela_estao_em_audit_fields():
    from routers import pipelines as pipes
    for campo in ("hora_virada", "nao_iniciar_antes", "hora_limite_dependencia"):
        assert campo in pipes.AUDIT_FIELDS


def test_write_audit_pula_chave_ausente():
    """Body parcial não pode auditar 'valor → vazio' falso."""
    from routers import pipelines as pipes
    cur = MagicMock()
    old = {"hora_virada": "20:00:00", "descricao": "a"}
    pipes._write_audit(cur, "P", "DEV1", old, {"descricao": "b"})
    campos = [c.args[1][2] for c in cur.execute.call_args_list]
    assert campos == ["descricao"]


def test_audit_registra_mudanca_de_janela(client, auth_editor):
    db = _db_com_pais()
    with _patch_db(db), _patch_airflow():
        client.post("/pipelines/register", json=_body_registro(hora_virada="20:00"))
    assert ("hora_virada", "", "20:00:00") in [
        (f, str(o or ""), str(n or "")) for f, o, n in db.audit]


# ═══════════════ CAMPOS_QUE_AFETAM_DAG — contrato do desenho §7.2 ═══════════

def test_campos_que_afetam_dag_sao_os_do_desenho():
    from routers import pipelines as pipes
    assert set(pipes.CAMPOS_QUE_AFETAM_DAG) == {
        "scheduled_time", "schedule_type", "schedule_hour", "schedule_minute",
        "schedule_dow", "schedule_dom", "horarios_especificos", "dias_semana",
        "dias_horarios_mes", "somente_dias_uteis", "calendario_nome",
        "hora_virada", "nao_iniciar_antes", "hora_limite_dependencia",
        "retries_count", "retry_delay_seconds", "max_active_runs", "pool_name",
        "envia_msg_inicio", "envia_msg_fim", "envia_msg_erro",
        "ambiente", "criticidade", "dag_start_date",
        # achado 1 da revisão: o gerador emite dagrun_timeout=timedelta(
        # minutes=sla) — SLA não é cadastro puro.
        "sla_minutos",
    }
