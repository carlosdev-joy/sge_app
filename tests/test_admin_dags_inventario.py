"""GET /admin/dags/inventario — o inventário das DAGs de SISTEMA no Admin.

O catálogo (funcionalidade/frequência pt-BR) mora em `routers.admin` como
documentação viva; o Airflow entra como fonte do ESTADO ao vivo. O que estes
testes prendem:

  1. **O catálogo não pode driftar dos arquivos**: todo `.py` de DAG na raiz
     de `dags/` tem entrada no catálogo, e toda entrada tem arquivo. É o teste
     que grita quando alguém cria (ou apaga) uma DAG de sistema e esquece o
     inventário — a tela mostraria "não catalogada" (ou uma DAG fantasma) e o
     Admin leria um inventário desatualizado como se fosse completo.
  2. **A degradação é dita**: Airflow fora do ar → `airflow_disponivel: false`
     e `presente_no_airflow: null` ("não sei"), NUNCA `false` ("ausente") — o
     inventário não pode inventar drift que não mediu.
  3. **O cruzamento com o Airflow**: pausada aparece pausada; catalogada
     ausente aparece ausente; DAG de sistema desconhecida entra como "não
     catalogada"; DAG de pipeline (fileloc em `generated/`) fica FORA.

Padrão de `test_admin_conexoes.py`: TestClient do conftest, `get_airflow_client`
stubado em `routers.admin`, auth via `dependency_overrides`. Nada toca rede.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401  (ordem de import)

from deps import PERM_ADMIN, get_current_user
from routers.admin import CATALOGO_DAGS, CATEGORIAS_DAGS

RAIZ = Path(__file__).resolve().parents[1]
DAGS_DIR = RAIZ / "dags"

# Arquivos de dags/ que NÃO são DAGs de sistema: pacotes auxiliares e o script
# usado como job_command do wizard (não define DAG nenhuma).
FORA_DO_INVENTARIO = {"orquestra_teste"}


def _arquivos_de_dag() -> set[str]:
    return {
        p.stem for p in DAGS_DIR.glob("*.py")
        if p.stem not in FORA_DO_INVENTARIO and not p.stem.startswith("__")
    }


# ═══════════ 1. o catálogo × os arquivos — o teste anti-drift ═══════════════

def test_toda_dag_de_sistema_esta_no_catalogo():
    """DAG nova sem entrada no catálogo apareceria "não catalogada" na tela —
    o inventário desatualizado com cara de completo."""
    faltam = _arquivos_de_dag() - set(CATALOGO_DAGS)
    assert not faltam, (
        f"DAGs de sistema sem entrada no CATALOGO_DAGS (routers/admin.py): "
        f"{sorted(faltam)} — cadastre funcionalidade/frequência/categoria")


def test_toda_entrada_do_catalogo_tem_arquivo():
    """Entrada órfã = DAG apagada que continuaria listada como 'ausente no
    Airflow' para sempre — drift inventado pelo próprio inventário."""
    orfas = set(CATALOGO_DAGS) - _arquivos_de_dag()
    assert not orfas, f"Entradas do catálogo sem arquivo em dags/: {sorted(orfas)}"


def test_toda_entrada_e_completa_e_com_categoria_valida():
    for dag_id, cat in CATALOGO_DAGS.items():
        assert cat.get("funcionalidade"), f"{dag_id}: sem funcionalidade"
        assert cat.get("frequencia"), f"{dag_id}: sem frequência"
        assert cat.get("categoria") in CATEGORIAS_DAGS, \
            f"{dag_id}: categoria '{cat.get('categoria')}' fora de CATEGORIAS_DAGS"


# ═══════════ 2. o endpoint — stubs no molde do test_admin_conexoes ══════════

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAirflowOk:
    """Uma página de /api/v1/dags com os 4 casos do cruzamento."""

    def __init__(self, dags):
        self._dags = dags

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kw):
        assert url == "/api/v1/dags"
        return _FakeResp({"dags": self._dags,
                          "total_entries": len(self._dags)})


class _FakeAirflowFora:
    async def __aenter__(self):
        raise RuntimeError("connection refused")

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def auth_admin(app):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "ADMIN1", "perfil": "admin", "permissoes": [PERM_ADMIN],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


def test_airflow_fora_degrada_dizendo(client, auth_admin):
    """`airflow_disponivel: false` + `presente_no_airflow: null` — "não sei"
    nunca vira "ausente"."""
    with patch("routers.admin.get_airflow_client",
               return_value=_FakeAirflowFora()):
        r = client.get("/admin/dags/inventario")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["airflow_disponivel"] is False
    assert corpo["total"] == len(CATALOGO_DAGS)
    assert all(d["presente_no_airflow"] is None for d in corpo["dags"])
    assert all(d["pausada"] is None for d in corpo["dags"])


def test_cruzamento_com_o_airflow(client, auth_admin):
    vivas = [
        # catalogada, PAUSADA, com cron real divergente do texto curado
        {"dag_id": "etl_dependencia_guardia", "is_paused": True,
         "fileloc": "/opt/airflow/dags/etl_dependencia_guardia.py",
         "schedule_interval": {"__type": "CronExpression",
                               "value": "*/2 * * * *"}},
        # catalogada, ativa, sem agendamento (sob demanda)
        {"dag_id": "etl_dag_factory", "is_paused": False,
         "fileloc": "/opt/airflow/dags/etl_dag_factory.py",
         "schedule_interval": None},
        # DAG de PIPELINE (gerada) — fica FORA do inventário de sistema
        {"dag_id": "carga_vida_diaria", "is_paused": False,
         "fileloc": "/opt/airflow/dags/generated/carga_vida_diaria.py",
         "schedule_interval": None},
        # DAG de sistema DESCONHECIDA — entra como "não catalogada"
        {"dag_id": "zumbi_dag", "is_paused": False,
         "fileloc": "/opt/airflow/dags/zumbi_dag.py",
         "description": "sobra de um experimento",
         "schedule_interval": None},
    ]
    with patch("routers.admin.get_airflow_client",
               return_value=_FakeAirflowOk(vivas)):
        r = client.get("/admin/dags/inventario")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["airflow_disponivel"] is True
    por_id = {d["dag_id"]: d for d in corpo["dags"]}

    assert "carga_vida_diaria" not in por_id, \
        "DAG gerada pela fábrica vazou para o inventário de sistema"

    guardia = por_id["etl_dependencia_guardia"]
    assert guardia["presente_no_airflow"] is True
    assert guardia["pausada"] is True
    # O cron REAL vem junto do texto curado — é o que deixa o drift visível.
    assert guardia["agendamento"] == "*/2 * * * *"

    zumbi = por_id["zumbi_dag"]
    assert zumbi["catalogada"] is False
    assert zumbi["categoria"] == "não catalogada"
    assert zumbi["funcionalidade"] == "sobra de um experimento"

    # Catalogada que o Airflow NÃO devolveu: ausente de verdade (medido).
    ausente = por_id["etl_performance_monitor"]
    assert ausente["presente_no_airflow"] is False
    assert ausente["pausada"] is None

    # Ordem: as categorias saem na ordem de exibição; "não catalogada" fecha.
    categorias = [d["categoria"] for d in corpo["dags"]]
    assert categorias == sorted(
        categorias, key=lambda c: CATEGORIAS_DAGS.index(c))
    assert categorias[-1] == "não catalogada"


def test_exige_admin(client):
    r = client.get("/admin/dags/inventario")
    assert r.status_code in (401, 403), r.text
