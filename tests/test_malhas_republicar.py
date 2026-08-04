"""
Testes da republicação da malha (POST /malhas/{m}/republicar).

O gesto: com a malha aberta, republicar as DAGs de TODOS os pipelines
vinculados, para que passem a valer os vínculos recém-desenhados. NENHUM
executor novo — é a marcação `dag_criada=0` do "Publicar DAGs" do Admin,
restrita ao escopo da malha, mais UMA execução da etl_dag_factory (a mesma do
botão por pipeline), aqui dublada.

Por que UMA execução e não uma por membro: disparada com `pipeline_name`, a
factory gera TODOS os pendentes e FALHA se o alvo pedido já foi marcado como
criado por um run irmão — N runs concorrentes pelo mesmo lote produziriam
FAILED de corrida no log da factory sem nenhuma DAG a mais ou a menos.

Cobrem: rota registrada; 401/403 (acao_executar, a permissão do publicar);
503 sem a 070; 404 malha; 422 sem membros / todos inativos; dry_run listando
alvos + ignorados + avisos SEM tocar banco nem Airflow; write marcando só os
ATIVOS e disparando UM run com o conf de auditoria; membro inativo ignorado
com motivo (nunca sumindo); reversão da marcação quando o Airflow recusa ou a
rede cai (meia-operação anunciaria "DAG não publicada" para DAG viva); fila
do reconciliador só para quem ainda não tem DAG; e o detalhe da malha
trazendo dag_criada/publicacao_pendente (com degradação sem a 073).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Replica o mock de pyodbc do conftest (garante o import de api.main mesmo se
# este arquivo for coletado antes do conftest configurar o ambiente).
if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import — ver test_copias.py)

from deps import PERM_EDITAR, PERM_EXECUTAR, get_current_user
from tests.test_malhas_f10 import FakeCur as FakeCurF10, FakeDb as FakeDbF10
from tests.test_malhas_f10 import _monta_malha
from tests.test_malhas_f15 import FakeAirflowClient as FakeAirflowPost
from tests.test_malhas_f15 import _RespostaAirflow, _patch_airflow


class FakeAirflowClient(FakeAirflowPost):
    """O dublê de POST da F15 + o GET /dags/{id} que a republicação usa para
    saber quem JÁ tem DAG lá (o cadastro não serve: `dag_criada` fica 0
    durante toda a regeneração). `dags` = nomes existentes; `get_explode`
    simula Airflow fora do ar SÓ na consulta."""

    def __init__(self, dags=(), get_explode=False, **kw):
        super().__init__(**kw)
        self.dags = set(dags)
        self.get_explode = get_explode
        self.gets: list[str] = []

    async def get(self, url, **_kw):
        pname = url.split("/api/v1/dags/")[1].split("/")[0]
        self.gets.append(pname)
        if self.get_explode:
            raise RuntimeError("Airflow indisponível (teste)")
        if pname in self.dags:
            return _RespostaAirflow(payload={"dag_id": pname})
        return _RespostaAirflow(status=404, texto="not found")


# ── dublê: F10 + o que a republicação lê/escreve ────────────────────────────

class FakeDb(FakeDbF10):
    """FakeDb da F10 com o carimbo da 073 ligado por padrão (a republicação
    existe por causa dele) e o COUNT de pendentes de FORA da malha."""

    def __init__(self, pipelines=None, com_tabelas=True, com_067=True,
                 com_073=True, com_075=True):
        super().__init__(pipelines=pipelines, com_tabelas=com_tabelas,
                         com_067=com_067, com_073=com_073, com_075=com_075)

    def cursor(self):
        return FakeCur(self)


class FakeCur(FakeCurF10):
    def execute(self, sql, params=()):  # noqa: C901 — dispatcher de dublê
        db = self.db
        s = " ".join(str(sql).split())
        params = tuple(params)

        # Guard de leitura do carimbo (073).
        if "COL_LENGTH('dbo.etl_pipeline', 'dag_config_pendente_em')" in s:
            self._rows = [(8,)] if db.com_073 else [(None,)]
            self.rowcount = -1
            return
        # Fotografia dos membros do endpoint de republicação (assinatura
        # PRÓPRIA — vem antes do handler do detalhe, que casa o mesmo JOIN).
        if s.startswith("SELECT p.pipeline_name, CAST(p.active AS INT), "
                        "CAST(ISNULL(p.dag_criada, 0) AS INT)"):
            k = db._malha_key(params[0])
            out = []
            for m in db.membros:
                if k and m["malha"].casefold() == k.casefold():
                    pk = db._pipeline_key(m["pipeline"])
                    if pk is None:
                        continue
                    p = db.pipelines[pk]
                    linha = [pk, int(p.get("active") or 0),
                             int(p.get("dag_criada") or 0)]
                    if "p.dag_config_pendente_em" in s:
                        linha.append(p.get("dag_config_pendente") or None)
                    out.append(tuple(linha))
            self._rows = sorted(out)
            self.rowcount = -1
            return
        # Pendentes de FORA da malha (o efeito colateral que o modal diz).
        if s.startswith("SELECT COUNT(*) FROM dbo.etl_pipeline p "
                        "WHERE p.active = 1"):
            k = db._malha_key(params[0])
            dentro = {m["pipeline"].casefold() for m in db.membros
                      if k and m["malha"].casefold() == k.casefold()}
            self._rows = [(sum(1 for nome, p in db.pipelines.items()
                               if int(p.get("active") or 0) == 1
                               and int(p.get("dag_criada") or 0) == 0
                               and nome.casefold() not in dentro),)]
            self.rowcount = -1
            return
        # Marcação / reversão em lote (IN com N placeholders).
        if s.startswith("UPDATE dbo.etl_pipeline SET dag_criada = 0") \
                or s.startswith("UPDATE dbo.etl_pipeline SET dag_criada = 1"):
            novo = 0 if "dag_criada = 0" in s else 1
            n = 0
            for nome in params:
                k = db._pipeline_key(nome)
                if k is not None:
                    db.pipelines[k]["dag_criada"] = novo
                    n += 1
            self.rowcount = n
            return

        super().execute(sql, params)


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_operador(app):
    """Editor + executor: monta a malha E republica (republicar é publicação,
    a mesma acao_executar do botão por pipeline)."""
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "OPER1", "perfil": "operador",
        "permissoes": [PERM_EDITAR, PERM_EXECUTAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_sem_executar(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "DEV1", "perfil": "desenvolvedor",
        "permissoes": [PERM_EDITAR, "tela_malha"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _patch_db(db):
    return patch("routers.malhas.get_db_conn", return_value=db)


def _pipes():
    base = {"criticidade": "Media", "schedule_type": "daily",
            "depends_on": None}
    return {
        # publicado e com o carimbo aceso (o caso que motiva o botão)
        "PIPE_A": {**base, "active": 1, "dag_criada": 1, "dag_config_pendente": 1},
        # publicado e em dia
        "PIPE_B": {**base, "active": 1, "dag_criada": 1},
        # ativo mas sem DAG no Airflow: primeira publicação
        "PIPE_NOVO": {**base, "active": 1, "dag_criada": 0},
        # inativo: o gerador não o aceita
        "PIPE_OFF": {**base, "active": 0, "dag_criada": 1},
        # fora da malha e pendente: entra no mesmo lote da factory
        "PIPE_FORA": {**base, "active": 1, "dag_criada": 0},
    }


def _republicar(client, malha, body=None):
    return client.post(f"/malhas/{malha}/republicar", json=body or {})


def _monta(client, nome="M1", membros=("PIPE_A", "PIPE_B", "PIPE_NOVO", "PIPE_OFF")):
    _monta_malha(client, nome, list(membros))


# ── registro da rota e permissões ───────────────────────────────────────────

def test_rota_registrada(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "/malhas/{malha_name}/republicar" in r.json().get("paths", {})


def test_sem_auth_401(client):
    assert _republicar(client, "M1").status_code == 401


def test_sem_acao_executar_403(client, auth_sem_executar):
    """Republicar é PUBLICAÇÃO: exige acao_executar, como o botão por
    pipeline — editor sem ela recebe 403."""
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        assert _republicar(client, "M1").status_code == 403


# ── degradação e validações ─────────────────────────────────────────────────

def test_sem_070_503(client, auth_operador):
    db = FakeDb(pipelines=_pipes(), com_tabelas=False)
    with _patch_db(db):
        r = _republicar(client, "M1")
    assert r.status_code == 503
    assert "070" in r.json()["detail"]


def test_malha_inexistente_404(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        r = _republicar(client, "NAO_EXISTE")
    assert r.status_code == 404


def test_malha_sem_membros_422(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), _patch_airflow(fake):
        _monta_malha(client, "VAZIA", [])
        r = _republicar(client, "VAZIA")
    assert r.status_code == 422
    assert "não tem pipelines vinculados" in r.json()["detail"]
    assert fake.chamadas == []


def test_todos_inativos_422(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), _patch_airflow(fake):
        _monta(client, "SO_OFF", ["PIPE_OFF"])
        r = _republicar(client, "SO_OFF")
    assert r.status_code == 422
    assert "inativos" in r.json()["detail"]
    assert fake.chamadas == []
    # nada foi marcado: o pipeline inativo continua publicado
    assert db.pipelines["PIPE_OFF"]["dag_criada"] == 1


# ── dry_run: diz o que fará, sem fazer ──────────────────────────────────────

def test_dry_run_lista_alvos_ignorados_e_avisos(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient(dags=["PIPE_A", "PIPE_B"])   # PIPE_NOVO ainda não
    with _patch_db(db), _patch_airflow(fake):
        _monta(client)
        r = _republicar(client, "M1", {"dry_run": True})
    assert r.status_code == 200
    body = r.json()
    assert [p["pipeline"] for p in body["pipelines"]] == [
        "PIPE_A", "PIPE_B", "PIPE_NOVO"]
    assert body["ignorados"] == [{
        "pipeline": "PIPE_OFF",
        "motivo": "pipeline inativo — o gerador de DAGs só considera "
                  "pipelines ativos; ative-o e republique para que ele "
                  "receba os vínculos"}]
    # o carimbo do membro chega na fotografia (é o que o botão conta)
    assert [p["publicacao_pendente"] for p in body["pipelines"]] == [
        True, False, False]
    # a existência da DAG vem do AIRFLOW, não do cadastro
    assert [p["dag_no_airflow"] for p in body["pipelines"]] == [True, True, False]
    # PIPE_FORA está pendente e não é membro: o efeito colateral é DITO
    assert body["pendentes_de_fora"] == 1
    assert any("fora desta malha" in a["mensagem"] for a in body["avisos"])
    assert any("PRIMEIRA versão" in a["mensagem"] and "PIPE_NOVO" in a["mensagem"]
               for a in body["avisos"])
    # nada foi tocado
    assert fake.chamadas == []
    assert db.pipelines["PIPE_A"]["dag_criada"] == 1
    assert db.pipelines["PIPE_B"]["dag_criada"] == 1


def test_dry_run_com_airflow_fora_nao_promete_primeira_versao(client, auth_operador):
    """Sem resposta do Airflow o endpoint não pode dizer que a DAG não existe:
    `dag_no_airflow` vem null e o aviso de primeira versão não é emitido."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient(get_explode=True)
    with _patch_db(db), _patch_airflow(fake):
        _monta(client)
        r = _republicar(client, "M1", {"dry_run": True})
    assert r.status_code == 200
    body = r.json()
    assert all(p["dag_no_airflow"] is None for p in body["pipelines"])
    assert not any("PRIMEIRA versão" in a["mensagem"] for a in body["avisos"])


def test_nome_invalido_como_dag_id_fica_de_fora(client, auth_operador):
    """Nome que não é dag_id válido nunca vira DAG — mandá-lo no conf faria a
    factory cobrar um alvo que ela não consegue gerar. Sai em `ignorados`."""
    pipes = _pipes()
    pipes["PIPE COM ESPAÇO"] = {"criticidade": "Media", "schedule_type": "daily",
                                "depends_on": None, "active": 1, "dag_criada": 1}
    db = FakeDb(pipelines=pipes)
    fake = FakeAirflowClient(dags=["PIPE_A"])
    with _patch_db(db), _patch_airflow(fake), \
            patch("routers.malhas.enqueue_dag_pendente"):
        _monta(client, "MX", ["PIPE_A", "PIPE COM ESPAÇO"])
        r = _republicar(client, "MX")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["republicados"] == ["PIPE_A"]
    assert [i["pipeline"] for i in body["ignorados"]] == ["PIPE COM ESPAÇO"]
    assert "dag_id" in body["ignorados"][0]["motivo"]
    # e o nome inválido não é consultado no Airflow nem marcado no cadastro
    assert "PIPE COM ESPAÇO" not in fake.gets
    assert db.pipelines["PIPE COM ESPAÇO"]["dag_criada"] == 1


def test_dry_run_avisa_067_pendente(client, auth_operador):
    """Sem a 067 a DAG sai publicada, mas pode sair SEM as ligações da malha —
    exatamente o que o operador quis publicar. Aviso forte antes do gesto."""
    db = FakeDb(pipelines=_pipes(), com_067=False)
    with _patch_db(db):
        _monta(client, "M067", ["PIPE_A", "PIPE_B"])
        r = _republicar(client, "M067", {"dry_run": True})
    assert r.status_code == 200
    fortes = [a for a in r.json()["avisos"] if a["nivel"] == "forte"]
    assert any("067" in a["mensagem"] for a in fortes)


# ── write ───────────────────────────────────────────────────────────────────

def test_republica_manda_os_ativos_num_run_so(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient(dags=["PIPE_A", "PIPE_B"])
    with _patch_db(db), _patch_airflow(fake), \
            patch("routers.malhas.enqueue_dag_pendente") as enq:
        _monta(client)
        r = _republicar(client, "M1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["republicados"] == ["PIPE_A", "PIPE_B", "PIPE_NOVO"]
    # UMA execução da factory, com os ALVOS no conf + rótulo de escopo e
    # auditoria
    assert len(fake.chamadas) == 1
    chamada = fake.chamadas[0]
    assert chamada["dag_id"] == "etl_dag_factory"
    conf = chamada["body"]["conf"]
    assert conf["pipelines"] == ["PIPE_A", "PIPE_B", "PIPE_NOVO"]
    assert conf["escopo_rotulo"] == "Malha M1"
    assert conf["requested_by"] == "malha:M1 (OPER1)"
    assert chamada["body"]["dag_run_id"] == body["dag_run_id"]
    # o inativo NÃO vai no lote nem é liberado
    assert "PIPE_OFF" not in conf["pipelines"]
    assert db.pipelines["PIPE_OFF"]["dag_criada"] == 1
    # os alvos ficam pendentes de geração — é o que faz o gesto funcionar
    # mesmo com a factory ANTIGA (que ignora conf["pipelines"])
    assert db.pipelines["PIPE_A"]["dag_criada"] == 0
    assert db.pipelines["PIPE_B"]["dag_criada"] == 0
    # TODOS entram na fila; quem já tem DAG entra em modo VERIFICAÇÃO (só
    # cobra erro de importação), quem não tem entra como ativação
    chamadas_enq = {c.args[0]: c.args for c in enq.call_args_list}
    assert set(chamadas_enq) == {"PIPE_A", "PIPE_B", "PIPE_NOVO"}
    assert chamadas_enq["PIPE_A"][4] is True     # modo_verificacao
    assert chamadas_enq["PIPE_B"][4] is True
    assert chamadas_enq["PIPE_NOVO"][4] is False
    assert chamadas_enq["PIPE_NOVO"][1] is False  # desired_paused


def test_membro_inativo_vem_como_ignorado_no_write(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient()
    with _patch_db(db), _patch_airflow(fake), \
            patch("routers.malhas.enqueue_dag_pendente"):
        _monta(client)
        r = _republicar(client, "M1")
    assert [i["pipeline"] for i in r.json()["ignorados"]] == ["PIPE_OFF"]


def test_airflow_recusa_502_e_desfaz_a_marcacao(client, auth_operador):
    """502 com o cadastro de volta ao que era: sem run a caminho, deixar os
    pipelines marcados anunciaria 'DAG não publicada' para DAG viva."""
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient(dags=["PIPE_A", "PIPE_B"],
                             falhas={"etl_dag_factory": 500})
    with _patch_db(db), _patch_airflow(fake), \
            patch("routers.malhas.enqueue_dag_pendente") as enq:
        _monta(client)
        r = _republicar(client, "M1")
    assert r.status_code == 502
    assert db.pipelines["PIPE_A"]["dag_criada"] == 1
    assert db.pipelines["PIPE_B"]["dag_criada"] == 1
    # quem já era pendente CONTINUA pendente (desfazer não inventa estado)
    assert db.pipelines["PIPE_NOVO"]["dag_criada"] == 0
    # sem run, ninguém entra na fila
    assert enq.call_args_list == []


def test_airflow_inacessivel_502_e_desfaz_a_marcacao(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    fake = FakeAirflowClient(dags=["PIPE_A", "PIPE_B"],
                             explodir=["etl_dag_factory"])
    with _patch_db(db), _patch_airflow(fake), \
            patch("routers.malhas.enqueue_dag_pendente"):
        _monta(client)
        r = _republicar(client, "M1")
    assert r.status_code == 502
    assert "gerador de DAGs" in r.json()["detail"]
    assert db.pipelines["PIPE_A"]["dag_criada"] == 1
    assert db.pipelines["PIPE_NOVO"]["dag_criada"] == 0


# ── detalhe da malha: o insumo do botão ─────────────────────────────────────

def test_detalhe_traz_dag_criada_e_publicacao_pendente(client, auth_operador):
    db = FakeDb(pipelines=_pipes())
    with _patch_db(db):
        _monta(client)
        r = client.get("/malhas/M1")
    assert r.status_code == 200
    membros = {m["pipeline_name"]: m for m in r.json()["membros"]}
    assert membros["PIPE_A"]["publicacao_pendente"] is True
    assert membros["PIPE_B"]["publicacao_pendente"] is False
    assert membros["PIPE_NOVO"]["dag_criada"] == 0
    assert membros["PIPE_A"]["dag_criada"] == 1


def test_detalhe_sem_073_nao_promete_estar_em_dia(client, auth_operador):
    """Sem o carimbo no banco a chave nem vem — a tela não pode desenhar
    'publicação em dia' a partir de um dado que não existe."""
    db = FakeDb(pipelines=_pipes(), com_073=False)
    with _patch_db(db):
        _monta(client)
        r = client.get("/malhas/M1")
    assert r.status_code == 200
    for m in r.json()["membros"]:
        assert "publicacao_pendente" not in m
        assert "dag_criada" in m
