"""POST /caixa/uso/acesso|presenca e GET /caixa/uso/resumo — uso do módulo Busca & Vendas.

Spec docs/spec-uso-busca-vendas.md. O que estes testes prendem:

  1. **A matrícula vem do token.** Corpo com `matricula` é ignorado.
  2. **Registro fechado de rotas**: rota fora do módulo/registro não toca o banco; o
     `:status` do Acompanhamento vira `detalhe`; e `ROTAS` bate com as rotas
     `caixa-seguro/*` do App.tsx (rota nova sem entrada = tela nunca medida, sem erro).
  3. **Dedupe no servidor** (30 min) numa instrução só (`INSERT … WHERE NOT EXISTS`).
  4. **Medir nunca quebra a tela**: falha de banco nos POSTs devolve 200 `registrado:false`.
  5. **Leitura só com `caixa_seguro_uso`** (ter `tela_caixa_seguro` não basta); 422 para
     período/data inválidos; 503 nomeando a migration quando a tabela não existe.
  6. **O resumo cobre o período inteiro**: série sem buracos (24 horas / dias do mês / 12
     meses) e janela [início, fim) correta na virada de mês e de ano.

Nada toca banco: cursor dublê e `get_db_conn` substituído.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app  # noqa: E402

from deps import get_current_user  # noqa: E402
from routers import caixa_uso  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
APP_TSX = RAIZ / "ui-react" / "src" / "App.tsx"


class Cursor:
    """Registra SQL/params e responde conforme a consulta feita."""

    def __init__(self, rowcount=1, estoura=False, kpis=(10, 3), balde=None, telas=None,
                 ranking=None, tela_top=None, primeiro=datetime(2026, 10, 28, 8, 0),
                 online=None):
        self.rowcount = rowcount
        self.estoura = estoura
        self.kpis = kpis
        self.balde = balde or []
        self.telas = telas or []
        self.ranking = ranking or []
        self.tela_top = tela_top or []
        self.primeiro = primeiro
        self.online = online or []
        self.sqls: list[str] = []
        self.params: list = []
        self._ult = ""

    def execute(self, sql, params=None):
        if self.estoura:
            raise Exception("Invalid object name 'dbo.etl_uso_evento'")
        self._ult = " ".join(sql.split())
        self.sqls.append(self._ult)
        self.params.append(params)
        return self

    def fetchone(self):
        s = self._ult
        if s.startswith("SELECT COUNT(*), COUNT(DISTINCT matricula)"):
            return self.kpis
        if s.startswith("SELECT MIN(ocorrido_em)"):
            return (self.primeiro,)
        if s.startswith("SELECT COUNT(*) FROM dbo.etl_uso_presenca"):
            return (len(self.online),)
        return None

    def fetchall(self):
        s = self._ult
        if "ROW_NUMBER()" in s:
            return self.tela_top
        if s.startswith("SELECT TOP (50) e.matricula"):
            return self.ranking
        if s.startswith("SELECT rota, MAX(tela)"):
            return self.telas
        if "FROM dbo.etl_uso_presenca p" in s:
            return self.online
        return self.balde

    def close(self):
        pass


def _usuario(*permissoes, matricula="U1"):
    return {"matricula": matricula, "perfil": "operador", "permissoes": list(permissoes)}


@pytest.fixture
def como():
    """Fábrica de cliente autenticado com as permissões dadas."""
    def _como(*permissoes, matricula="U1"):
        app.dependency_overrides[get_current_user] = lambda: _usuario(*permissoes, matricula=matricula)
        return TestClient(app)
    yield _como
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def banco(monkeypatch):
    estado = {"cur": Cursor()}

    def _fabrica():
        conn = MagicMock()
        conn.cursor.return_value = estado["cur"]
        return conn

    monkeypatch.setattr("routers.caixa_uso.get_db_conn", _fabrica)
    monkeypatch.setattr("routers.caixa_uso.hoje_brasilia", lambda: date(2026, 10, 28))
    return estado


# ═══════════ 1. registro fechado de rotas ═══════════════════════════════════

@pytest.mark.parametrize("bruta,esperado", [
    ("/caixa-seguro", ("/caixa-seguro", "Consulta de Propostas", None)),
    ("/caixa-seguro/", ("/caixa-seguro", "Consulta de Propostas", None)),
    ("/caixa-seguro/acompanhamento", ("/caixa-seguro/acompanhamento", "Monitoramento Tático de Emissão", None)),
    ("/caixa-seguro/acompanhamento/pending_signature",
     ("/caixa-seguro/acompanhamento/:status", "Acompanhamento por status", "pending_signature")),
    ("/caixa-seguro/portabilidades", ("/caixa-seguro/portabilidades", "Portabilidades", None)),
    ("/caixa-seguro/ia-operacional", ("/caixa-seguro/ia-operacional", "Painel de IA Operacional", None)),
    ("/caixa-seguro/uso", ("/caixa-seguro/uso", "Uso do módulo", None)),
])
def test_rotas_do_registro_resolvem(bruta, esperado):
    assert tuple(caixa_uso.resolver_rota(bruta)) == esperado


@pytest.mark.parametrize("bruta", [
    "", "/", "/admin", "/dashboard", "/caixa-seguro-x", "/caixa-seguro/desconhecida",
    "/caixa-seguro/acompanhamento/Maiuscula", "/caixa-seguro/acompanhamento/a/b",
    "/caixa-seguro/acompanhamento/aaa", "/caixa-seguro/acompanhamento/pending_signature_x",
    "/caixa-seguro/acompanhamento/" + "a" * 41, "/caixa-seguro?x=1", "x" * 201,
    "/caixa-seguro/../admin",
])
def test_rota_fora_do_registro_nao_resolve(bruta):
    assert caixa_uso.resolver_rota(bruta) is None


def test_registro_bate_com_as_rotas_do_modulo_no_app_tsx():
    """Rota nova em /caixa-seguro/* sem entrada em ROTAS = tela nunca medida, sem erro."""
    fonte = APP_TSX.read_text(encoding="utf-8")
    do_app = set(re.findall(r'path="(caixa-seguro[^"]*)"\s*element=\{\s*<RequirePerm', fonte))
    assert do_app, "nenhuma rota do módulo lida do App.tsx — a regex ficou para trás"
    do_registro = {r.canonica.lstrip("/") for r in caixa_uso.ROTAS}
    assert do_app == do_registro, (
        f"só no App.tsx: {sorted(do_app - do_registro)} · só no registro: {sorted(do_registro - do_app)}")


# ═══════════ 2. acesso ══════════════════════════════════════════════════════

def test_acesso_usa_a_matricula_do_token_e_ignora_o_corpo(como, banco):
    r = como("tela_caixa_seguro", matricula="REAL1").post(
        "/caixa/uso/acesso", json={"rota": "/caixa-seguro", "matricula": "FORJADA"})
    assert r.status_code == 200 and r.json() == {"registrado": True}
    params = banco["cur"].params[0]
    assert params[0] == "REAL1" and "FORJADA" not in params


def test_acesso_grava_rota_canonica_tela_e_detalhe(como, banco):
    como("tela_caixa_seguro").post(
        "/caixa/uso/acesso", json={"rota": "/caixa-seguro/acompanhamento/declined"})
    p = banco["cur"].params[0]
    assert p[:5] == ["U1", "busca_vendas", "/caixa-seguro/acompanhamento/:status",
                     "Acompanhamento por status", "declined"]


def test_acesso_dedupe_numa_instrucao_so_com_janela_de_30_min(como, banco):
    como("tela_caixa_seguro").post("/caixa/uso/acesso", json={"rota": "/caixa-seguro"})
    sql = banco["cur"].sqls[0]
    assert sql.startswith("INSERT INTO dbo.etl_uso_evento") and "WHERE NOT EXISTS" in sql
    assert "ISNULL(detalhe, '') = ISNULL(CAST(? AS VARCHAR(40)), '')" in sql
    assert "matricula = CAST(? AS VARCHAR(20))" in sql and "rota = CAST(? AS VARCHAR(120))" in sql
    # A janela de 30 min é o que impede a duplicata: sem ela, o NOT EXISTS nunca barra.
    assert "ocorrido_em > DATEADD(MINUTE, ?, GETDATE())" in sql
    assert banco["cur"].params[0][-1] == -30


def test_acesso_repetido_na_janela_nao_grava_de_novo(como, banco):
    banco["cur"] = Cursor(rowcount=0)
    r = como("tela_caixa_seguro").post("/caixa/uso/acesso", json={"rota": "/caixa-seguro"})
    assert r.json() == {"registrado": False}


def test_rota_desconhecida_nao_toca_o_banco(como, banco):
    r = como("tela_caixa_seguro").post("/caixa/uso/acesso", json={"rota": "/admin"})
    assert r.status_code == 200 and r.json()["registrado"] is False
    assert banco["cur"].sqls == []


def test_acesso_exige_a_permissao_do_modulo(como, banco):
    assert como("tela_dashboard").post("/caixa/uso/acesso", json={"rota": "/caixa-seguro"}).status_code == 403
    assert banco["cur"].sqls == []


def test_medir_nunca_quebra_a_tela_quando_o_banco_falha(como, banco):
    banco["cur"] = Cursor(estoura=True)
    c = como("tela_caixa_seguro")
    for caminho in ("/caixa/uso/acesso", "/caixa/uso/presenca"):
        r = c.post(caminho, json={"rota": "/caixa-seguro"})
        assert r.status_code == 200 and r.json()["registrado"] is False


# ═══════════ 3. presença ════════════════════════════════════════════════════

def test_presenca_faz_merge_de_uma_linha_por_matricula(como, banco):
    r = como("tela_caixa_seguro", matricula="P9").post(
        "/caixa/uso/presenca", json={"rota": "/caixa-seguro/portabilidades"})
    assert r.json() == {"registrado": True}
    assert banco["cur"].sqls[0].startswith("MERGE dbo.etl_uso_presenca")
    assert banco["cur"].params[0] == ["P9", "/caixa-seguro/portabilidades", "/caixa-seguro/portabilidades"]


# ═══════════ 4. leitura ═════════════════════════════════════════════════════

def test_resumo_exige_caixa_seguro_uso_e_o_acesso_ao_modulo_nao_basta(como, banco):
    assert como("tela_caixa_seguro").get("/caixa/uso/resumo").status_code == 403
    assert como("caixa_seguro_uso").get("/caixa/uso/resumo").status_code == 200
    assert como("tela_caixa_seguro").get("/caixa/uso/resumo").status_code == 403


@pytest.mark.parametrize("qs", ["periodo=semana", "periodo=dia&referencia=28-10-2026",
                                "periodo=dia&referencia=2026-13-40", "referencia=amanha"])
def test_resumo_rejeita_periodo_e_data_invalidos(como, banco, qs):
    r = como("caixa_seguro_uso").get(f"/caixa/uso/resumo?{qs}")
    assert r.status_code == 422 and banco["cur"].sqls == []


def test_resumo_sem_tabela_devolve_503_nomeando_a_migration(como, banco):
    banco["cur"] = Cursor(estoura=True)
    r = como("caixa_seguro_uso").get("/caixa/uso/resumo")
    assert r.status_code == 503 and "141" in r.json()["detail"]


def test_resumo_contrato_completo(como, banco):
    banco["cur"] = Cursor(
        kpis=(205, 15),
        balde=[(9, 27, 12), (16, 28, 13)],
        telas=[("/caixa-seguro", "Consulta de Propostas", 86, 15),
               ("/caixa-seguro/uso", "Uso do módulo", 6, 4)],
        ranking=[("C1", "Ana", "Souza", 49, 1, datetime(2026, 10, 28, 8, 10)),
                 ("C2", None, None, 33, 1, datetime(2026, 10, 28, 9, 14))],
        tela_top=[("C1", "Consulta de Propostas")],
        online=[("C1", "Ana", "Souza")])
    d = como("caixa_seguro_uso").get("/caixa/uso/resumo?periodo=dia&referencia=2026-10-28").json()
    assert d["online_agora"] == 1 and d["usuarios_online"] == ["Ana Souza"]
    assert d["primeiro_registro"] == "2026-10-28"
    assert d["periodo"] == {"inicio": "2026-10-28", "fim": "2026-10-28", "granularidade": "hora"}
    assert d["kpis"] == {"usuarios": 15, "acessos": 205, "acessos_por_usuario": 13.7}
    assert len(d["serie"]) == 24 and d["serie"][9] == {"rotulo": "09h", "acessos": 27, "usuarios": 12}
    assert d["serie"][0] == {"rotulo": "00h", "acessos": 0, "usuarios": 0}
    assert d["por_tela"][0] == {"tela": "Consulta de Propostas", "rota": "/caixa-seguro",
                                "acessos": 86, "usuarios": 15}
    assert d["ranking"][0] == {"matricula": "C1", "nome": "Ana Souza", "acessos": 49, "dias_ativos": 1,
                               "ultimo_acesso": "2026-10-28T08:10:00", "tela_top": "Consulta de Propostas"}
    # Sem nome cadastrado, mostra a matrícula (nunca "None").
    assert d["ranking"][1]["nome"] == "C2" and d["ranking"][1]["tela_top"] == ""


def test_resumo_sem_acesso_nao_divide_por_zero(como, banco):
    banco["cur"] = Cursor(kpis=(0, 0), primeiro=None)
    d = como("caixa_seguro_uso").get("/caixa/uso/resumo").json()
    assert d["kpis"] == {"usuarios": 0, "acessos": 0, "acessos_por_usuario": 0.0}
    assert d["primeiro_registro"] is None and d["ranking"] == [] and d["por_tela"] == []


@pytest.mark.parametrize("periodo,ref,gran,qtd,primeiro_rotulo,ultimo_rotulo", [
    ("dia", "2026-10-28", "hora", 24, "00h", "23h"),
    ("mes", "2026-10-28", "dia", 31, "01", "31"),
    ("mes", "2026-02-10", "dia", 28, "01", "28"),
    ("ano", "2026-10-28", "mes", 12, "jan", "dez"),
])
def test_serie_cobre_o_periodo_inteiro(como, banco, periodo, ref, gran, qtd, primeiro_rotulo, ultimo_rotulo):
    d = como("caixa_seguro_uso").get(f"/caixa/uso/resumo?periodo={periodo}&referencia={ref}").json()
    assert d["periodo"]["granularidade"] == gran and len(d["serie"]) == qtd
    assert d["serie"][0]["rotulo"] == primeiro_rotulo and d["serie"][-1]["rotulo"] == ultimo_rotulo


@pytest.mark.parametrize("periodo,ref,ini,fim", [
    ("dia", date(2026, 12, 31), datetime(2026, 12, 31), datetime(2027, 1, 1)),
    ("mes", date(2026, 12, 15), datetime(2026, 12, 1), datetime(2027, 1, 1)),
    ("mes", date(2026, 2, 10), datetime(2026, 2, 1), datetime(2026, 3, 1)),
    ("ano", date(2026, 6, 1), datetime(2026, 1, 1), datetime(2027, 1, 1)),
])
def test_janela_e_semiaberta_e_vira_mes_e_ano(periodo, ref, ini, fim):
    j = caixa_uso.janela_do_periodo(periodo, ref)
    assert (j.inicio, j.fim) == (ini, fim)


def test_consultas_do_periodo_recebem_os_limites_como_parametro(como, banco):
    como("caixa_seguro_uso").get("/caixa/uso/resumo?periodo=mes&referencia=2026-10-28")
    limites = [datetime(2026, 10, 1), datetime(2026, 11, 1)]
    do_periodo = [p for s, p in zip(banco["cur"].sqls, banco["cur"].params)
                  if "ocorrido_em >= ? AND" in s]
    assert len(do_periodo) == 5 and all(p == limites for p in do_periodo)


def test_online_independe_do_periodo_e_usa_janela_de_10_min(como, banco):
    como("caixa_seguro_uso").get("/caixa/uso/resumo?periodo=ano&referencia=2020-01-01")
    presenca = [(s, p) for s, p in zip(banco["cur"].sqls, banco["cur"].params) if "etl_uso_presenca" in s]
    assert len(presenca) == 2 and all(p == [-10] for _, p in presenca)


def test_status_do_acompanhamento_e_allowlist_igual_ao_workflow_ts():
    """O `detalhe` aceito = os StatusWorkflow do front; inventar um status não grava linha."""
    fonte = (RAIZ / "ui-react" / "src" / "caixa" / "lib" / "workflow.ts").read_text(encoding="utf-8")
    uniao = re.search(r"export type StatusWorkflow\s*=(.*?);", fonte, re.S).group(1)
    do_front = set(re.findall(r'"([a-z_]+)"', uniao))
    assert do_front and do_front == set(caixa_uso.STATUS_ACOMPANHAMENTO)


def test_status_inventado_nao_toca_o_banco(como, banco):
    r = como("tela_caixa_seguro").post(
        "/caixa/uso/acesso", json={"rota": "/caixa-seguro/acompanhamento/inventado"})
    assert r.json()["registrado"] is False and banco["cur"].sqls == []


@pytest.mark.parametrize("ref", ["9999-12-31", "0001-01-01", "1999-12-31", "2101-01-01"])
def test_referencia_fora_do_intervalo_e_422_e_nao_503(como, banco, ref):
    r = como("caixa_seguro_uso").get(f"/caixa/uso/resumo?periodo=ano&referencia={ref}")
    assert r.status_code == 422 and banco["cur"].sqls == []
