"""
Testes da entidade Malha — F7 da spec de dependências (api/routers/malhas.py).

Padrão de test_finalizacao.py: TestClient do conftest, get_db_conn mockado em
routers.malhas e autenticação sobrescrita via dependency_overrides — nenhum
teste toca rede ou banco.

O dublê aqui é ESTATAL (FakeDb): etl_malha/etl_malha_pipeline em dicts com a
semântica case-insensitive da colação do SQL Server. Assim os fluxos compostos
(criar → renomear → detalhar) exercitam o SQL real do router de ponta a ponta,
em vez de listas de fetchone decoradas por teste.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# Replica o mock de pyodbc do conftest (garante o import de api.main mesmo se
# este arquivo for coletado antes do conftest configurar o ambiente).
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, get_current_user


# ── dublê estatal do banco ───────────────────────────────────────────────────

_AGORA = datetime(2026, 8, 2, 10, 0, 0)


class FakeDb:
    """etl_malha + etl_malha_pipeline em memória, com chaves case-insensitive
    (a colação do SQL Server é CI — 'Fechamento' e 'FECHAMENTO' colidem).

    com_074=False (default, mesmo padrão do com_073 da F5) simula o banco SEM a
    coluna etl_malha.orientacao: o guard COL_LENGTH devolve NULL, a API degrada
    para 'horizontal' e qualquer UPDATE da coluna nesse estado LEVANTA no dublê
    (chegar lá é bug de degradação).

    com_agenda=False (default) simula o banco SEM etl_malha.agendamento_json /
    etl_pipeline.agenda_no e SEM as tabelas de execução/dependência da 067:
    os agregados do card (última execução, filtro de dependentes, agendamento
    próprio da malha) degradam sem quebrar a lista — tocar essas tabelas nesse
    estado LEVANTA aqui, como no com_tabelas.

    `nos_inicio` modela o MÍNIMO da 075 que a lista precisa: quais malhas têm
    nó Início e qual raiz está ASSINADA por ele (etl_pipeline.agenda_no). É o
    que separa agendamento VIGENTE de agendamento apenas guardado — o desenho
    completo (etl_malha_no/aresta) continua sendo assunto do dublê da F10."""

    def __init__(self, pipelines=None, com_tabelas=True, com_074=False,
                 com_agenda=False, com_067=False, execucoes=None,
                 dependencias=None, nos_inicio=None):
        # pipelines: {grafia_oficial: {"active": 1, "criticidade": "Alta",
        #                              "schedule_type": "daily", "jobs": 3,
        #                              "schedule_hour": 6, ...}}
        self.pipelines = pipelines or {}
        self.com_tabelas = com_tabelas
        self.com_074 = com_074
        self.com_agenda = com_agenda
        self.com_067 = com_067
        # execucoes: [{"pipeline", "status", "inicio", "criado_em"}] — a ordem
        # da lista é a de INSERÇÃO (o desempate por id DESC do SQL real).
        self.execucoes: list[dict] = list(execucoes or [])
        # dependencias: [(pipeline_dependente, depende_de)] — as linhas da 067.
        self.dependencias: list = [tuple(d) for d in (dependencias or ())]
        # nos_inicio: {malha: [pipelines com agenda_no apontando p/ o Início]}
        # — lista VAZIA = Início desenhado mas sem nenhuma raiz assinada.
        self.nos_inicio: dict = dict(nos_inicio or {})
        self.malhas: dict[str, dict] = {}   # grafia_oficial -> linha
        self.membros: list[dict] = []       # {"malha", "pipeline", "layout_x", "layout_y"}
        self.commits = 0

    # chave CI
    def _malha_key(self, nome):
        for k in self.malhas:
            if k.casefold() == (nome or "").casefold():
                return k
        return None

    def _pipeline_key(self, nome):
        for k in self.pipelines:
            if k.casefold() == (nome or "").casefold():
                return k
        return None

    def cursor(self):
        return FakeCur(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


class FakeCur:
    def __init__(self, db: FakeDb):
        self.db = db
        self._rows: list[tuple] = []
        self.rowcount = -1
        self.description = []

    def close(self):
        pass

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        self._rows = []
        self.rowcount = -1

        if "OBJECT_ID('dbo.etl_malha'" in s:
            self._rows = [(1, 1)] if db.com_tabelas else [(None, None)]
            return
        # Guard das colunas de agendamento da 075 (agendamento_json/agenda_no).
        # Tem de vir ANTES do guard da 074 — o prefixo COL_LENGTH é o mesmo.
        # O nome do flag é `com_agenda` (o mesmo da F13) e não `com_075`: as
        # subclasses da F10 já usam com_075 para as TABELAS de nó/aresta.
        if "COL_LENGTH('dbo.etl_malha', 'agendamento_json')" in s:
            self._rows = [(8, 4)] if (db.com_tabelas and db.com_agenda) \
                else [(None, None)]
            return
        # Guard de LEITURA do carimbo da 073 (publicação pendente): sem a
        # coluna o membro sai do detalhe sem a chave `publicacao_pendente`.
        # `com_073` só existe nas subclasses que modelam o carimbo (F8+) —
        # aqui o default é "não tem", como no banco anterior à migration.
        if "COL_LENGTH('dbo.etl_pipeline', 'dag_config_pendente_em')" in s:
            self._rows = [(8,)] if getattr(db, "com_073", False) else [(None,)]
            return
        # Colunas da 081 (virada + equalização da MALHA) e a hora_virada do
        # PIPELINE (067) — guards independentes, como no router.
        if "COL_LENGTH('dbo.etl_malha', 'hora_virada')" in s:
            self._rows = [(5, 1)] if getattr(db, "com_081", False) else [(None, None)]
            return
        if "COL_LENGTH('dbo.etl_pipeline', 'hora_virada')" in s:
            self._rows = [(5,)] if getattr(db, "com_virada_pipe", False) else [(None,)]
            return
        # Coluna do LIMITE DE SEGURANCA por malha (085/F7). Guard PROPRIO no
        # router — a 085 cria a tabela da corrida e esta coluna em blocos
        # separados —, entao guard proprio aqui tambem. Tem de vir ANTES do
        # catch-all da 074 abaixo, que casa qualquer COL_LENGTH de etl_malha.
        if "COL_LENGTH('dbo.etl_malha', 'teto_horas')" in s:
            self._rows = [(4,)] if getattr(db, "com_085", False) else [(None,)]
            return
        # Guard da coluna orientacao (074): COL_LENGTH devolve NULL para coluna
        # ausente sem estourar — inclusive sem a própria tabela.
        if "COL_LENGTH('dbo.etl_malha'" in s:
            self._rows = [(12,)] if (db.com_tabelas and db.com_074) else [(None,)]
            return
        # Sonda da 085 (corrida de malha) — `tabela_085_presente`. Default
        # AUSENTE: o banco desta suíte é o de antes da migration, e é isso que
        # exercita a degradação (o rename não carimba corrida nenhuma e a
        # resposta sai byte a byte igual à de antes da F3). Tem de vir antes do
        # guard de `com_tabelas` abaixo, que barra tudo que cita `etl_malha`.
        if "OBJECT_ID('dbo.etl_malha_execucao'" in s:
            self._rows = ([(1, 1, 8)] if getattr(db, "com_085", False)
                          else [(None, None, None)])
            return
        # Tabelas da 075: existem exatamente quando as COLUNAS de agendamento
        # existem (vieram na mesma migration). O desenho em si não é modelado
        # aqui — só o Início e a assinatura agenda_no, via nos_inicio.
        if "OBJECT_ID('dbo.etl_malha_no'" in s:
            self._rows = [(1, 1)] if db.com_agenda else [(None, None)]
            return
        if s.startswith("SELECT DISTINCT n.malha_name FROM dbo.etl_malha_no n"):
            if not db.com_agenda:
                raise RuntimeError("Invalid object name 'dbo.etl_malha_no'")
            # Só entra quem tem Início COM raiz assinada: Início sem raiz (lista
            # vazia) é agendamento guardado, não vigente.
            self._rows = [(m,) for m, raizes in sorted(db.nos_inicio.items())
                          if raizes]
            return
        # Guards das tabelas da 067 (dependência e execução) — os agregados do
        # card degradam sem elas, e tocá-las nesse estado é bug de degradação.
        if "OBJECT_ID('dbo.etl_pipeline_dependencia'" in s:
            self._rows = [(1,)] if db.com_067 else [(None,)]
            return
        if "OBJECT_ID('dbo.etl_pipeline_execucao'" in s:
            self._rows = [(1, 1)] if db.com_067 else [(None, None)]
            return
        if not db.com_067 and ("etl_pipeline_dependencia" in s
                               or "etl_pipeline_execucao" in s):
            raise RuntimeError("Invalid object name 'dbo.etl_pipeline_execucao'")
        # A checagem única do router precisa impedir QUALQUER toque nas
        # tabelas quando elas não existem — chegar aqui é bug de degradação.
        if not db.com_tabelas and "etl_malha" in s:
            raise RuntimeError("Invalid object name 'dbo.etl_malha'")

        # ── agregados do card da lista (etapas · gatilho · última execução) ──
        if s.startswith("SELECT DISTINCT pipeline_name FROM dbo.etl_pipeline_dependencia"):
            self._rows = [(p,) for p in sorted({d[0] for d in db.dependencias})]
            return
        if s.startswith("SELECT pipeline_name, depende_de FROM dbo.etl_pipeline_dependencia"):
            self._rows = sorted(db.dependencias)
            return
        if "CROSS APPLY" in s and "etl_pipeline_execucao" in s:
            # TOP 1 por pipeline MEMBRO, por COALESCE(inicio, criado_em),
            # desempatando pela ordem de inserção (o id DESC real). A
            # composição por malha é do router, em Python.
            membros_pipes = {m["pipeline"].casefold() for m in db.membros}
            melhor: dict[str, tuple] = {}
            for i, e in enumerate(db.execucoes):
                pk = str(e["pipeline"]).casefold()
                if pk not in membros_pipes:
                    continue
                momento = e.get("inicio") or e["criado_em"]
                atual = melhor.get(pk)
                if atual is None or (momento, i) > (atual[0], atual[1]):
                    melhor[pk] = (momento, i, e)
            self._rows = [(v[2]["pipeline"], v[2]["status"], v[0])
                          for _, v in sorted(melhor.items())]
            return

        # ── SELECTs em etl_malha ────────────────────────────────────────────
        if s.startswith("SELECT malha_name FROM dbo.etl_malha WHERE"):
            k = db._malha_key(params[0])
            self._rows = [(k,)] if k else []
            return
        if s.startswith("SELECT malha_name, descricao"):
            # Com a 074 o router pede a coluna extra; sem ela o SQL é o de
            # sempre — o dublê espelha as DUAS formas. Idem agendamento_json
            # (075), aditivo só na listagem.
            tem_orientacao = ", orientacao" in s
            tem_agendamento = ", agendamento_json" in s
            tem_081 = ", hora_virada, CAST(equalizar_data AS INT)" in s
            tem_teto = ", teto_horas" in s

            def linha(k):
                m = db.malhas[k]
                cols = [k, m["descricao"], m["ativo"], m["criado_em"],
                        m["criado_por"], m["atualizado_em"]]
                if tem_orientacao:
                    cols.append(m.get("orientacao", "horizontal"))
                if tem_agendamento:
                    cols.append(m.get("agendamento_json"))
                if tem_081:
                    cols.append(m.get("hora_virada"))
                    cols.append(int(m.get("equalizar_data") or 0))
                if tem_teto:
                    cols.append(m.get("teto_horas"))
                return tuple(cols)
            if "WHERE malha_name = ?" in s:
                k = db._malha_key(params[0])
                self._rows = [linha(k)] if k else []
            else:  # listagem ORDER BY malha_name
                self._rows = [linha(k) for k in sorted(db.malhas)]
            return

        # ── membros (JOIN com etl_pipeline) ─────────────────────────────────
        if "FROM dbo.etl_malha_pipeline mp JOIN dbo.etl_pipeline p" in s:
            if "WHERE mp.malha_name = ?" in s:   # detalhe
                k = db._malha_key(params[0])
                out = []
                for m in db.membros:
                    if k and m["malha"].casefold() == k.casefold():
                        pk = db._pipeline_key(m["pipeline"])
                        if pk is None:
                            continue  # pipeline excluído: o JOIN o faz sumir
                        p = db.pipelines[pk]
                        # dag_criada é fixa; agenda_no (075) e o carimbo da
                        # 073 são ADITIVOS — o dublê espelha as três formas
                        # do SQL, como faz com orientacao/agendamento_json.
                        cols = [pk, p.get("active", 1),
                                p.get("criticidade") or "Media",
                                p.get("schedule_type"),
                                m["layout_x"], m["layout_y"],
                                int(p.get("dag_criada") or 0)]
                        if "p.agenda_no" in s:
                            cols.append(p.get("agenda_no"))
                        if "p.dag_config_pendente_em" in s:
                            # o dublê guarda o 0/1 equivalente ao carimbo
                            # (convenção do FakeDb da F8): 0/ausente = sem
                            # carimbo, e o router só testa "is not None".
                            cols.append(p.get("dag_config_pendente") or None)
                        out.append(tuple(cols))
                self._rows = sorted(out)
            else:                                 # agregados da listagem
                out = []
                for m in db.membros:
                    pk = db._pipeline_key(m["pipeline"])
                    if pk is None:
                        continue
                    p = db.pipelines[pk]
                    # A listagem pede as etapas (COUNT correlacionado em
                    # etl_pipeline_job) e as colunas de cron do membro — os
                    # insumos de qtd_etapas e do gatilho derivado.
                    out.append((db._malha_key(m["malha"]), p.get("active", 1),
                                p.get("criticidade") or "Media",
                                p.get("jobs", 0), pk,
                                p.get("schedule_type"),
                                p.get("schedule_hour"),
                                p.get("schedule_minute"),
                                p.get("schedule_dow"),
                                p.get("schedule_dom"),
                                p.get("horarios_especificos"),
                                p.get("dias_semana"),
                                p.get("dias_horarios_mes"),
                                p.get("somente_dias_uteis", 0),
                                p.get("calendario_nome"),
                                p.get("hora_virada")))
                self._rows = out
            return

        # ── SELECTs auxiliares ──────────────────────────────────────────────
        if s.startswith("SELECT pipeline_name FROM dbo.etl_pipeline WHERE"):
            k = db._pipeline_key(params[0])
            self._rows = [(k,)] if k else []
            return
        if s.startswith("SELECT 1 FROM dbo.etl_malha_pipeline"):
            self._rows = [(1,)] if any(
                m["malha"].casefold() == params[0].casefold()
                and m["pipeline"].casefold() == params[1].casefold()
                for m in db.membros) else []
            return

        # ── escrita em etl_malha ────────────────────────────────────────────
        if s.startswith("INSERT INTO dbo.etl_malha (") and " SELECT ?" in s:
            novo, atual = params
            k = db._malha_key(atual)
            if db._malha_key(novo):
                raise RuntimeError("Violation of PRIMARY KEY constraint 'PK_etl_malha'")
            velho = db.malhas[k]
            db.malhas[novo] = {**velho, "atualizado_em": _AGORA}
            return
        if s.startswith("INSERT INTO dbo.etl_malha ("):
            nome, descricao, criado_por = params
            if db._malha_key(nome):
                raise RuntimeError("Violation of PRIMARY KEY constraint 'PK_etl_malha'")
            # orientacao nasce no DEFAULT da 074 ('horizontal') — presente no
            # dict mesmo sem a coluna: só o SELECT com a 074 a devolve.
            db.malhas[nome] = {"descricao": descricao, "ativo": 1,
                               "criado_em": _AGORA, "criado_por": criado_por,
                               "atualizado_em": None, "orientacao": "horizontal"}
            return
        if s.startswith("UPDATE dbo.etl_malha SET malha_name"):
            novo, atual = params
            k = db._malha_key(atual)
            db.malhas[novo] = {**db.malhas.pop(k), "atualizado_em": _AGORA}
            return
        if s.startswith("UPDATE dbo.etl_malha SET descricao"):
            k = db._malha_key(params[1])
            db.malhas[k].update(descricao=params[0], atualizado_em=_AGORA)
            return
        if s.startswith("UPDATE dbo.etl_malha SET ativo"):
            k = db._malha_key(params[1])
            db.malhas[k].update(ativo=params[0], atualizado_em=_AGORA)
            return
        if s.startswith("UPDATE dbo.etl_malha SET orientacao"):
            # O guard COL_LENGTH tem de impedir o UPDATE sem a 074 — chegar
            # aqui nesse estado é bug de degradação.
            if not db.com_074:
                raise RuntimeError("Invalid column name 'orientacao'")
            k = db._malha_key(params[1])
            db.malhas[k].update(orientacao=params[0], atualizado_em=_AGORA)
            return
        if s.startswith("UPDATE dbo.etl_malha SET teto_horas"):
            # Mesmo contrato do orientacao: sem a coluna, o guard do router tem
            # de impedir o UPDATE — chegar aqui sem a 085 é bug de degradação.
            if not getattr(db, "com_085", False):
                raise RuntimeError("Invalid column name 'teto_horas'")
            k = db._malha_key(params[1])
            db.malhas[k].update(teto_horas=params[0], atualizado_em=_AGORA)
            return
        if s.startswith("DELETE FROM dbo.etl_malha WHERE"):
            k = db._malha_key(params[0])
            if k:
                db.malhas.pop(k)
                db.membros = [m for m in db.membros            # ON DELETE CASCADE
                              if m["malha"].casefold() != k.casefold()]
            return

        # ── escrita em etl_malha_pipeline ───────────────────────────────────
        if s.startswith("INSERT INTO dbo.etl_malha_pipeline"):
            db.membros.append({"malha": params[0], "pipeline": params[1],
                               "layout_x": None, "layout_y": None})
            return
        if s.startswith("UPDATE dbo.etl_malha_pipeline SET malha_name"):
            novo, atual = params
            for m in db.membros:
                if m["malha"].casefold() == atual.casefold():
                    m["malha"] = novo
            return
        if s.startswith("DELETE FROM dbo.etl_malha_pipeline"):
            antes = len(db.membros)
            db.membros = [m for m in db.membros
                          if not (m["malha"].casefold() == params[0].casefold()
                                  and m["pipeline"].casefold() == params[1].casefold())]
            self.rowcount = antes - len(db.membros)
            return

        raise AssertionError(f"SQL não previsto pelo dublê: {s[:120]}")


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_editor(app):
    """Usuário com acao_editar (quem constrói malhas)."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EDITAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_consulta(app):
    """Usuário autenticado SEM acao_editar (só leitura)."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "USER1", "perfil": "consulta", "permissoes": ["tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch_db(db):
    return patch("routers.malhas.get_db_conn", return_value=db)


_PIPES = {
    "PIPE_VENDAS":  {"active": 1, "criticidade": "Alta",    "schedule_type": "daily"},
    "PIPE_ESTOQUE": {"active": 0, "criticidade": "Baixa",   "schedule_type": "on_demand"},
    "PIPE_FISCAL":  {"active": 1, "criticidade": "Critica", "schedule_type": "daily"},
    "PIPE_SEM_CRIT": {"active": 1, "criticidade": None,     "schedule_type": "weekly"},
}

# Pipelines dos agregados do CARD (etapas · gatilho · última execução): as
# etapas em `jobs` (o COUNT de etl_pipeline_job) e as colunas de cron reais.
_PIPES_CARD = {
    # Duas raízes no MESMO cron diário das 06:00 — o caso "06:00 (2 pipelines)"
    "P_RAIZ_A":    {"active": 1, "criticidade": "Alta", "jobs": 4,
                    "schedule_type": "daily", "schedule_hour": 6,
                    "schedule_minute": 0},
    "P_RAIZ_B":    {"active": 1, "criticidade": "Media", "jobs": 3,
                    "schedule_type": "daily", "schedule_hour": 6,
                    "schedule_minute": 0},
    # Raiz mais tarde: cria o caso "horários distintos"
    "P_RAIZ_TARDE": {"active": 1, "criticidade": "Baixa", "jobs": 2,
                     "schedule_type": "daily", "schedule_hour": 22,
                     "schedule_minute": 30},
    # Dependente: TEM cron gravado, mas o gerador o troca por schedule=None —
    # não pode contar como gatilho da malha.
    "P_FILHO":     {"active": 1, "criticidade": "Alta", "jobs": 3,
                    "schedule_type": "daily", "schedule_hour": 8,
                    "schedule_minute": 0},
    # Sob demanda de verdade
    "P_MANUAL":    {"active": 0, "criticidade": "Baixa", "jobs": 1,
                    "schedule_type": "on_demand", "schedule_hour": 6,
                    "schedule_minute": 0},
    # INATIVO com cron mais cedo: DAG pausada no Airflow (a tela de pipelines
    # sincroniza) e a SP de geração filtra active=1 — não dispara nada.
    "P_INATIVO_CEDO": {"active": 0, "criticidade": "Alta", "jobs": 2,
                       "schedule_type": "daily", "schedule_hour": 4,
                       "schedule_minute": 0},
    # Cron com qualificadores (dias úteis + calendário + virada)
    "P_RAIZ_UTEIS": {"active": 1, "criticidade": "Media", "jobs": 1,
                     "schedule_type": "daily", "schedule_hour": 6,
                     "schedule_minute": 0, "somente_dias_uteis": 1,
                     "calendario_nome": "BR", "hora_virada": "21:00"},
    # Fora de qualquer malha — as etapas dele NÃO podem entrar na conta
    "P_DE_FORA":   {"active": 1, "criticidade": "Critica", "jobs": 99,
                    "schedule_type": "daily", "schedule_hour": 5,
                    "schedule_minute": 0},
}


# ── registro do router e auth ────────────────────────────────────────────────

def test_router_malhas_registrado(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    for p in ("/malhas", "/malhas/{malha_name}",
              "/malhas/{malha_name}/pipelines",
              "/malhas/{malha_name}/pipelines/{pipeline_name}"):
        assert p in paths, f"rota {p} não registrada em api/main.py"


def test_sem_auth_401(client):
    assert client.get("/malhas").status_code == 401
    assert client.post("/malhas", json={"malha_name": "X"}).status_code == 401


def test_escrita_exige_acao_editar_403(client, auth_consulta):
    """Perfil de consulta vê a lista, mas não cria/edita malha."""
    db = FakeDb()
    with _patch_db(db):
        assert client.get("/malhas").status_code == 200
        assert client.post("/malhas", json={"malha_name": "X"}).status_code == 403
        assert client.patch("/malhas/X", json={"ativo": 0}).status_code == 403
    assert db.malhas == {}


# ── criação ──────────────────────────────────────────────────────────────────

def test_criar_malha_grava_criado_por(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        r = client.post("/malhas", json={"malha_name": "Fechamento Diario",
                                         "descricao": "  ondas do fechamento  "})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "malha_name": "Fechamento Diario"}
    assert db.malhas["Fechamento Diario"]["criado_por"] == "DEV1"
    assert db.malhas["Fechamento Diario"]["descricao"] == "ondas do fechamento"
    assert db.commits == 1


def test_criar_nome_vazio_422(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        r = client.post("/malhas", json={"malha_name": "   "})
    assert r.status_code == 422
    assert "malha_name" in r.json()["detail"]


def test_criar_duplicada_case_insensitive_422(client, auth_editor):
    """A colação do banco é CI: 'FECHAMENTO' duplicaria 'Fechamento' — o 422
    precisa vir da pré-validação, com a grafia registrada, não do PK."""
    db = FakeDb()
    with _patch_db(db):
        assert client.post("/malhas", json={"malha_name": "Fechamento"}).status_code == 200
        r = client.post("/malhas", json={"malha_name": "FECHAMENTO"})
    assert r.status_code == 422
    assert "'Fechamento'" in r.json()["detail"]
    assert list(db.malhas) == ["Fechamento"]


# ── membros ──────────────────────────────────────────────────────────────────

def test_membro_pipeline_inexistente_422(client, auth_editor):
    """422 com o NOME antes de a FK estourar — o erro útil diz qual foi o typo."""
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        r = client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_FANTASMA"})
    assert r.status_code == 422
    assert "PIPE_FANTASMA" in r.json()["detail"]
    assert db.membros == []


def test_membro_grafia_divergente_e_canonizado(client, auth_editor):
    """Mesma regra da PR #236: grava-se a grafia REGISTRADA em etl_pipeline,
    nunca a digitada — dicts Python são case-sensitive e o membro 'sumiria'."""
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        r = client.post("/malhas/m1/pipelines", json={"pipeline_name": "pipe_vendas"})
    assert r.status_code == 200
    assert r.json()["pipeline_name"] == "PIPE_VENDAS"
    assert db.membros == [{"malha": "M1", "pipeline": "PIPE_VENDAS",
                           "layout_x": None, "layout_y": None}]


def test_adicionar_membro_e_idempotente(client, auth_editor):
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        r1 = client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_VENDAS"})
        r2 = client.post("/malhas/M1/pipelines", json={"pipeline_name": "Pipe_Vendas"})
    assert r1.status_code == 200 and r1.json()["ja_membro"] is False
    assert r2.status_code == 200 and r2.json()["ja_membro"] is True
    assert len(db.membros) == 1


def test_adicionar_membro_em_malha_inexistente_404(client, auth_editor):
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        r = client.post("/malhas/NAO_EXISTE/pipelines",
                        json={"pipeline_name": "PIPE_VENDAS"})
    assert r.status_code == 404


def test_remover_membro_e_404_de_nao_membro(client, auth_editor):
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_VENDAS"})
        ok = client.delete("/malhas/M1/pipelines/pipe_vendas")
        de_novo = client.delete("/malhas/M1/pipelines/PIPE_VENDAS")
    assert ok.status_code == 200
    assert db.membros == []
    assert de_novo.status_code == 404
    assert "não é membro" in de_novo.json()["detail"]


# ── rename ───────────────────────────────────────────────────────────────────

def test_rename_atualiza_a_tabela_filha(client, auth_editor):
    """A FK da 070 é cascade de DELETE, não de UPDATE: renomear tem de migrar
    os membros na MESMA transação — senão a malha nova nasce vazia."""
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_VENDAS"})
        client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_FISCAL"})
        r = client.patch("/malhas/M1", json={"novo_nome": "MALHA_FECHAMENTO"})
        detalhe = client.get("/malhas/MALHA_FECHAMENTO")
        antiga = client.get("/malhas/M1")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "malha_name": "MALHA_FECHAMENTO", "renomeada": True}
    assert detalhe.status_code == 200
    assert [m["pipeline_name"] for m in detalhe.json()["membros"]] == \
        ["PIPE_FISCAL", "PIPE_VENDAS"]
    assert antiga.status_code == 404
    # criado_em/criado_por sobrevivem ao rename (a linha é migrada, não recriada)
    assert db.malhas["MALHA_FECHAMENTO"]["criado_por"] == "DEV1"


def test_rename_para_nome_de_outra_malha_422(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        client.post("/malhas", json={"malha_name": "M2"})
        r = client.patch("/malhas/M1", json={"novo_nome": "m2"})
    assert r.status_code == 422
    assert "'M2'" in r.json()["detail"]
    assert set(db.malhas) == {"M1", "M2"}


def test_rename_so_de_caixa_nao_estoura_o_pk(client, auth_editor):
    """'m1' → 'M1' é o MESMO valor para a colação CI: o caminho
    insert/migra/apaga colidiria no PK; aqui tem de ser UPDATE direto."""
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "malha_diaria"})
        client.post("/malhas/malha_diaria/pipelines",
                    json={"pipeline_name": "PIPE_VENDAS"})
        r = client.patch("/malhas/malha_diaria", json={"novo_nome": "MALHA_DIARIA"})
    assert r.status_code == 200
    assert list(db.malhas) == ["MALHA_DIARIA"]
    assert db.membros[0]["malha"] == "MALHA_DIARIA"


def test_patch_malha_inexistente_404(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        r = client.patch("/malhas/NAO_EXISTE", json={"descricao": "x"})
    assert r.status_code == 404


def test_patch_descricao_e_ativo(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1", "descricao": "antiga"})
        r = client.patch("/malhas/M1", json={"descricao": "nova", "ativo": 0})
    assert r.status_code == 200
    assert db.malhas["M1"]["descricao"] == "nova"
    assert db.malhas["M1"]["ativo"] == 0


# ── listagem e agregados ─────────────────────────────────────────────────────

def test_lista_agrega_qtds_e_criticidade_mais_alta(client, auth_editor):
    """Critica > Alta > Media > Baixa; qtd_ativos conta só active=1; malha sem
    membros não inventa criticidade."""
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "CHEIA"})
        for p in ("PIPE_VENDAS", "PIPE_ESTOQUE", "PIPE_FISCAL"):
            client.post("/malhas/CHEIA/pipelines", json={"pipeline_name": p})
        client.post("/malhas", json={"malha_name": "VAZIA"})
        r = client.get("/malhas")
    assert r.status_code == 200
    cheia, vazia = r.json()["malhas"]        # ordenadas por nome
    assert cheia["malha_name"] == "CHEIA"
    assert cheia["qtd_pipelines"] == 3
    assert cheia["qtd_ativos"] == 2
    assert cheia["criticidade"] == "Critica"
    assert vazia == {**vazia, "malha_name": "VAZIA", "qtd_pipelines": 0,
                     "qtd_ativos": 0, "criticidade": None}


def test_criticidade_nula_conta_como_media(client, auth_editor):
    """ISNULL(criticidade,'Media') do banco + fallback do agregador: pipeline
    sem criticidade não derruba nem rebaixa a conta."""
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_SEM_CRIT"})
        client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_ESTOQUE"})
        r = client.get("/malhas")
    assert r.json()["malhas"][0]["criticidade"] == "Media"


def test_detalhe_traz_membros_com_layout(client, auth_editor):
    db = FakeDb(pipelines=_PIPES)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "M1"})
        client.post("/malhas/M1/pipelines", json={"pipeline_name": "PIPE_VENDAS"})
        r = client.get("/malhas/m1")     # grafia divergente resolve pela CI
    assert r.status_code == 200
    body = r.json()
    assert body["malha_name"] == "M1"
    assert body["qtd_pipelines"] == 1 and body["qtd_ativos"] == 1
    # dag_criada acompanha o membro desde a republicação da malha; sem a 073
    # (este FakeDb) NÃO existe chave publicacao_pendente — a tela não inventa
    # "está em dia" quando o banco não tem o carimbo.
    assert body["membros"] == [{
        "pipeline_name": "PIPE_VENDAS", "active": 1, "criticidade": "Alta",
        "schedule_type": "daily", "layout_x": None, "layout_y": None,
        "dag_criada": 0,
    }]


def test_detalhe_malha_inexistente_404(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        r = client.get("/malhas/NAO_EXISTE")
    assert r.status_code == 404


# ── agregados do card: etapas · última execução · gatilho ────────────────────
# Os três campos que o operador lê no card da tela Malha. São ADITIVOS no
# contrato (front antigo ignora) e cada um degrada sozinho — os testes cobrem
# tanto o cálculo quanto o deploy parcial.

def _montar(client, malha, pipelines):
    client.post("/malhas", json={"malha_name": malha})
    for p in pipelines:
        client.post(f"/malhas/{malha}/pipelines", json={"pipeline_name": p})


def test_qtd_etapas_soma_so_os_membros(client, auth_editor):
    """'4 pipelines, 10 etapas': a soma é das linhas de etl_pipeline_job dos
    MEMBROS — pipeline de fora da malha (com 99 jobs) não entra na conta."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True)
    with _patch_db(db):
        _montar(client, "M1", ["P_RAIZ_A", "P_RAIZ_B", "P_MANUAL"])
        _montar(client, "M2", ["P_RAIZ_A"])
        r = client.get("/malhas")
    m1, m2 = r.json()["malhas"]
    assert (m1["qtd_pipelines"], m1["qtd_etapas"]) == (3, 4 + 3 + 1)
    assert (m2["qtd_pipelines"], m2["qtd_etapas"]) == (1, 4)


def test_qtd_etapas_de_malha_sem_membros_e_zero(client, auth_editor):
    """Malha vazia: zero etapas, sem execução e sem gatilho inventado."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True)
    with _patch_db(db):
        client.post("/malhas", json={"malha_name": "VAZIA"})
        r = client.get("/malhas")
    vazia = r.json()["malhas"][0]
    assert vazia["qtd_etapas"] == 0
    assert vazia["ultima_execucao"] is None
    assert vazia["gatilho"]["origem"] == "nenhum"
    assert vazia["gatilho"]["resumo"] == "sob demanda"


def test_ultima_execucao_e_a_mais_recente_entre_os_membros(client, auth_editor):
    """A corrida mais recente entre os MEMBROS, por início — não a última
    inserida nem a de maior data_referencia."""
    db = FakeDb(
        pipelines=_PIPES_CARD, com_067=True,
        execucoes=[
            {"pipeline": "P_RAIZ_A", "status": "SUCESSO",
             "inicio": datetime(2026, 8, 3, 6, 0, 12),
             "criado_em": datetime(2026, 8, 3, 6, 0, 0)},
            {"pipeline": "P_RAIZ_B", "status": "FALHA",
             "inicio": datetime(2026, 8, 3, 6, 15, 40),
             "criado_em": datetime(2026, 8, 3, 6, 15, 0)},
            # Inserida DEPOIS, mas começou ANTES: não pode vencer.
            {"pipeline": "P_RAIZ_A", "status": "SUCESSO",
             "inicio": datetime(2026, 8, 2, 6, 0, 5),
             "criado_em": datetime(2026, 8, 2, 6, 0, 0)},
            # De um pipeline que NÃO é membro: nunca aparece.
            {"pipeline": "P_DE_FORA", "status": "SUCESSO",
             "inicio": datetime(2026, 8, 3, 23, 59, 0),
             "criado_em": datetime(2026, 8, 3, 23, 59, 0)},
        ])
    with _patch_db(db):
        _montar(client, "M1", ["P_RAIZ_A", "P_RAIZ_B"])
        r = client.get("/malhas")
    assert r.json()["malhas"][0]["ultima_execucao"] == {
        "em": "2026-08-03 06:15:40", "status": "FALHA",
        "pipeline": "P_RAIZ_B"}


def test_ultima_execucao_de_corrida_que_nao_partiu_usa_criado_em(client, auth_editor):
    """AGUARDANDO_DEPENDENCIA tem inicio NULL: o registro existe e é o mais
    recente — some-lo seria esconder do operador que a malha foi acionada."""
    db = FakeDb(
        pipelines=_PIPES_CARD, com_067=True,
        execucoes=[
            {"pipeline": "P_RAIZ_A", "status": "SUCESSO",
             "inicio": datetime(2026, 8, 3, 6, 0, 0),
             "criado_em": datetime(2026, 8, 3, 6, 0, 0)},
            {"pipeline": "P_FILHO", "status": "AGUARDANDO_DEPENDENCIA",
             "inicio": None, "criado_em": datetime(2026, 8, 3, 6, 1, 30)},
        ])
    with _patch_db(db):
        _montar(client, "M1", ["P_RAIZ_A", "P_FILHO"])
        r = client.get("/malhas")
    assert r.json()["malhas"][0]["ultima_execucao"] == {
        "em": "2026-08-03 06:01:30", "status": "AGUARDANDO_DEPENDENCIA",
        "pipeline": "P_FILHO"}


def test_malha_sem_execucao_devolve_null(client, auth_editor):
    """Sem corrida registrada, `null` — a tela diz 'sem execução registrada'
    em vez de inventar uma data."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True)
    with _patch_db(db):
        _montar(client, "M1", ["P_RAIZ_A"])
        r = client.get("/malhas")
    assert r.json()["malhas"][0]["ultima_execucao"] is None


def test_gatilho_do_agendamento_proprio_da_malha(client, auth_editor):
    """Malha com agendamento próprio VIGENTE (F13 — Início desenhado e raiz
    assinada): o resumo sai do MESMO _resumo_agendamento do nó Início — a
    lista não pode contradizer o diagrama."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True, com_agenda=True,
                nos_inicio={"M1": ["P_RAIZ_A"]})
    with _patch_db(db):
        _montar(client, "M1", ["P_RAIZ_A", "P_RAIZ_TARDE"])
        db.malhas["M1"]["agendamento_json"] = (
            '{"schedule_type": "daily", "schedule_hour": 7, '
            '"schedule_minute": 30}')
        r = client.get("/malhas")
    m1 = r.json()["malhas"][0]
    g = m1["gatilho"]
    assert g["origem"] == "malha"
    assert g["resumo"] == "diário 07:30"
    assert g["horario"] == "07:30"
    assert g["agendamento"]["schedule_hour"] == 7
    assert m1["agendamento_guardado"] is False


def test_agendamento_sem_inicio_nao_vira_gatilho(client, auth_editor):
    """GRAVE da revisão: excluir o nó Início desliga TODAS as raízes
    (on_demand) mas PRESERVA agendamento_json de propósito (§7.3/Decisão 10).
    Anunciar esse horário no card seria mentira — e permanente, porque não há
    rota para limpar o agendamento. A precedência tem de cair para os membros;
    aqui todos ficaram on_demand, então o card diz 'sob demanda' e sinaliza
    que existe agendamento guardado."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True, com_agenda=True,
                nos_inicio={})           # Início excluído: nenhum nó sobrou
    with _patch_db(db):
        _montar(client, "M1", ["P_MANUAL"])
        db.malhas["M1"]["agendamento_json"] = (
            '{"schedule_type": "daily", "schedule_hour": 7, '
            '"schedule_minute": 30}')
        r = client.get("/malhas")
    m1 = r.json()["malhas"][0]
    assert m1["gatilho"]["origem"] == "nenhum"
    assert m1["gatilho"]["resumo"] == "sob demanda"
    assert m1["gatilho"]["horario"] is None
    assert m1["agendamento_guardado"] is True


def test_agendamento_com_inicio_sem_raiz_assinada_nao_vira_gatilho(client, auth_editor):
    """Mesma mentira pelo outro caminho: agendamento salvo ANTES de o Início
    ser ligado a qualquer raiz. O nó existe, mas ninguém carrega o cron."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True, com_agenda=True,
                nos_inicio={"M1": []})   # Início desenhado, nenhuma raiz assinada
    with _patch_db(db):
        _montar(client, "M1", ["P_MANUAL"])
        db.malhas["M1"]["agendamento_json"] = '{"schedule_type": "daily"}'
        r = client.get("/malhas")
    m1 = r.json()["malhas"][0]
    assert m1["gatilho"]["resumo"] == "sob demanda"
    assert m1["agendamento_guardado"] is True


def test_agendamento_inerte_nao_atropela_o_gatilho_dos_membros(client, auth_editor):
    """Com agendamento guardado E membros em cron, quem manda são os MEMBROS:
    é o que realmente dispara. A flag continua avisando do agendamento
    guardado, sem virar horário."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True, com_agenda=True,
                nos_inicio={})
    with _patch_db(db):
        _montar(client, "M1", ["P_RAIZ_A", "P_RAIZ_B"])
        db.malhas["M1"]["agendamento_json"] = (
            '{"schedule_type": "daily", "schedule_hour": 23, '
            '"schedule_minute": 0}')
        r = client.get("/malhas")
    m1 = r.json()["malhas"][0]
    assert m1["gatilho"]["origem"] == "membros"
    assert m1["gatilho"]["resumo"] == "diário 06:00 (2 pipelines)"
    assert m1["agendamento_guardado"] is True


def test_gatilho_dos_membros_traz_os_qualificadores(client, auth_editor):
    """MENOR da revisão: o resumo derivado dos membros usa o MESMO schema de
    campos do agendamento da malha — 'só dias úteis'/'calendário X'/'virada'
    entram nos dois. Duas verdades para o mesmo campo é contradição na tela."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True)
    with _patch_db(db):
        _montar(client, "M1", ["P_RAIZ_UTEIS"])
        r = client.get("/malhas")
    g = r.json()["malhas"][0]["gatilho"]
    assert g["resumo"] == ("diário 06:00 · só dias úteis · calendário BR "
                           "· virada 21:00 (1 pipeline)")


def test_gatilho_derivado_dos_membros_com_cron(client, auth_editor):
    """Sem agendamento próprio, o gatilho vem dos membros que disparam
    sozinhos — mesmo cron nos dois: resumo completo + quantidade."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True)
    with _patch_db(db):
        _montar(client, "M1", ["P_RAIZ_A", "P_RAIZ_B", "P_MANUAL"])
        r = client.get("/malhas")
    g = r.json()["malhas"][0]["gatilho"]
    assert g["origem"] == "membros"
    assert g["resumo"] == "diário 06:00 (2 pipelines)"
    assert g["horario"] == "06:00"
    assert g["qtd_pipelines"] == 2          # P_MANUAL é on_demand: fora
    assert [d["pipeline"] for d in g["detalhes"]] == ["P_RAIZ_A", "P_RAIZ_B"]


def test_gatilho_com_horarios_distintos_mostra_o_mais_cedo(client, auth_editor):
    """Horários diferentes: o card mostra o MAIS CEDO e avisa que há outros —
    esconder os outros faria o operador achar que tudo parte às 06:00."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True)
    with _patch_db(db):
        _montar(client, "M1", ["P_RAIZ_A", "P_RAIZ_TARDE"])
        r = client.get("/malhas")
    g = r.json()["malhas"][0]["gatilho"]
    assert g["resumo"] == "06:00 · +1 horário"
    assert g["horario"] == "06:00"
    assert g["horarios"] == ["06:00", "22:30"]
    assert g["qtd_pipelines"] == 2


def test_gatilho_ignora_membro_inativo(client, auth_editor):
    """GRAVE da revisão: membro INATIVO com cron mais cedo tem a DAG PAUSADA
    no Airflow e é filtrado pela SP de geração (active=1) — ele não dispara.
    Contá-lo faria o card anunciar 04:00 numa malha que só começa às 06:00, e
    uma malha 100% inativa anunciaria horário que nunca roda."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True)
    with _patch_db(db):
        _montar(client, "M1", ["P_RAIZ_A", "P_INATIVO_CEDO"])
        _montar(client, "M2", ["P_INATIVO_CEDO"])
        r = client.get("/malhas")
    m1, m2 = r.json()["malhas"]
    assert m1["gatilho"]["resumo"] == "diário 06:00 (1 pipeline)"
    assert m1["gatilho"]["horario"] == "06:00"     # nunca 04:00
    assert [d["pipeline"] for d in m1["gatilho"]["detalhes"]] == ["P_RAIZ_A"]
    # Malha só de inativos: nada dispara — 'sob demanda' é a verdade.
    assert m2["gatilho"]["origem"] == "nenhum"
    assert m2["gatilho"]["resumo"] == "sob demanda"


def test_gatilho_ignora_membro_com_dependencia(client, auth_editor):
    """Dependente tem cron gravado, mas o gerador o troca por schedule=None:
    contá-lo como gatilho seria mentira. Malha só de dependentes → sob
    demanda."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True,
                dependencias=[("P_FILHO", "P_RAIZ_A")])
    with _patch_db(db):
        _montar(client, "M1", ["P_FILHO"])
        _montar(client, "M2", ["P_RAIZ_A", "P_FILHO"])
        r = client.get("/malhas")
    m1, m2 = r.json()["malhas"]
    assert m1["gatilho"]["origem"] == "nenhum"
    assert m1["gatilho"]["resumo"] == "sob demanda"
    assert m2["gatilho"]["resumo"] == "diário 06:00 (1 pipeline)"
    assert [d["pipeline"] for d in m2["gatilho"]["detalhes"]] == ["P_RAIZ_A"]


def test_gatilho_sob_demanda_quando_ninguem_dispara_sozinho(client, auth_editor):
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True)
    with _patch_db(db):
        _montar(client, "M1", ["P_MANUAL"])
        r = client.get("/malhas")
    g = r.json()["malhas"][0]["gatilho"]
    assert g == {"origem": "nenhum", "resumo": "sob demanda", "horario": None,
                 "qtd_pipelines": 0, "horarios": [], "detalhes": [],
                 "agendamento": None}


# ── degradação dos agregados (deploy parcial) ────────────────────────────────

def test_sem_075_gatilho_cai_nos_membros(client, auth_editor):
    """Sem a coluna agendamento_json (075 pendente), o agendamento próprio da
    malha é ilegível — o gatilho degrada para a derivação dos membros e a
    lista continua de pé (o dublê LEVANTA se a coluna for lida)."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=True, com_agenda=False)
    with _patch_db(db):
        _montar(client, "M1", ["P_RAIZ_A", "P_RAIZ_B"])
        db.malhas["M1"]["agendamento_json"] = '{"schedule_type": "daily"}'
        r = client.get("/malhas")
    assert r.status_code == 200
    g = r.json()["malhas"][0]["gatilho"]
    assert g["origem"] == "membros"
    assert g["resumo"] == "diário 06:00 (2 pipelines)"


def test_sem_067_lista_sem_ultima_execucao_mas_com_etapas(client, auth_editor):
    """Sem as tabelas da 067 não há execução para ler nem como saber quem é
    dependente: `ultima_execucao` fica null, o gatilho sai do schedule_type
    sozinho e etapas/contagens seguem valendo — nunca 500."""
    db = FakeDb(pipelines=_PIPES_CARD, com_067=False)
    with _patch_db(db):
        _montar(client, "M1", ["P_RAIZ_A", "P_FILHO"])
        r = client.get("/malhas")
    assert r.status_code == 200
    m1 = r.json()["malhas"][0]
    assert m1["ultima_execucao"] is None
    assert m1["qtd_etapas"] == 4 + 3
    assert m1["gatilho"]["qtd_pipelines"] == 2   # sem a 067, ninguém é filho


# ── degradação sem a migration 070 ───────────────────────────────────────────

def test_sem_tabelas_lista_degrada_para_vazio(client, auth_editor):
    """Deploy parcial (API nova, migration 070 pendente): a tela lista vazio,
    sem stack trace — o dublê LEVANTA se qualquer query tocar as tabelas."""
    db = FakeDb(com_tabelas=False)
    with _patch_db(db):
        r = client.get("/malhas")
    assert r.status_code == 200
    assert r.json() == {"malhas": [], "migration_pendente": True}


def test_sem_tabelas_escrita_da_erro_claro(client, auth_editor):
    """Escrita sem as tabelas: 503 com instrução em pt-BR, nunca 500 cru."""
    db = FakeDb(com_tabelas=False)
    with _patch_db(db):
        r_post = client.post("/malhas", json={"malha_name": "M1"})
        r_membro = client.post("/malhas/M1/pipelines",
                               json={"pipeline_name": "PIPE_VENDAS"})
        r_patch = client.patch("/malhas/M1", json={"ativo": 0})
        r_del = client.delete("/malhas/M1/pipelines/PIPE_VENDAS")
        r_detalhe = client.get("/malhas/M1")
    for r in (r_post, r_membro, r_patch, r_del, r_detalhe):
        assert r.status_code == 503
        assert "migration 070" in r.json()["detail"]
    assert db.commits == 0


# ── nome com '/' fica inendereçável no path (achado da revisão adversarial) ──

def test_nome_com_barra_recusado_na_criacao(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        r = client.post("/malhas", json={"malha_name": "Fechamento/Diario"})
    assert r.status_code == 422
    assert "/" in r.json()["detail"]
    assert list(db.malhas) == []


def test_nome_com_barra_recusado_no_rename(client, auth_editor):
    db = FakeDb()
    with _patch_db(db):
        assert client.post("/malhas", json={"malha_name": "MALHA_OK"}).status_code == 200
        r = client.patch("/malhas/MALHA_OK", json={"novo_nome": "a/b"})
    assert r.status_code == 422
    assert "/" in r.json()["detail"]
    assert list(db.malhas) == ["MALHA_OK"]
