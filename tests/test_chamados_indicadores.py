"""GET /chamados/indicadores — os agregados da aba da gestão.

O que estes testes prendem:

  1. **Faixa sem chamado vem com 0 EXPLÍCITO, e na ordem fixa.** Um buraco no
     gráfico faria "nenhum chamado velho" parecer "não medi isso" — e as duas
     leituras levam a decisões opostas.
  2. **A série de 14 dias tem 14 pontos**, inclusive os dias sem movimento:
     dia sem encerramento é um zero dito, não uma lacuna (critério de aceite
     explícito da spec).
  3. **O denominador viaja junto.** A regra da casa é que nenhuma superfície
     mostre "%" sem o "x de y" ao lado; a tela só monta essa frase se
     `total_ativos` chegar.
  4. **O corte do top-N é DITO.** Mostrar 10 responsáveis e calar que havia 15
     faria a soma do gráfico não bater com a fila, sem nada na tela explicando.
  5. **Degrada sem a migration** em vez de estourar 500.

Nada toca banco: cursor dublê roteando por trecho de SQL.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app  # noqa: E402

from deps import get_current_user  # noqa: E402
from routers.chamados import DIAS_FLUXO, FAIXAS_AGING, TOPO_RESPONSAVEIS  # noqa: E402

HOJE = _dt.date(2026, 8, 13)


class CursorFalso:
    """Roteia cada SELECT do endpoint pelo trecho de SQL que o identifica."""

    def __init__(self, aging=None, tipo_estado=None, entradas=None,
                 saidas=None, carga=None, total=0, explode=False):
        self.dados = {
            "aging": aging or [], "tipo_estado": tipo_estado or [],
            "entradas": entradas or [], "saidas": saidas or [],
            "carga": carga or [],
        }
        self.total = total
        self.explode = explode
        self._alvo = None

    def execute(self, sql, params=None):
        if self.explode:
            raise RuntimeError("Invalid object name 'dbo.etl_chamado'")
        if "END AS faixa" in sql:
            self._alvo = "aging"
        elif "GROUP BY tipo, estado_kanban" in sql:
            self._alvo = "tipo_estado"
        elif "CAST(aberto_em AS DATE)" in sql:
            self._alvo = "entradas"
        elif "CAST(encerrado_em AS DATE)" in sql:
            self._alvo = "saidas"
        elif "atribuido_a" in sql:
            self._alvo = "carga"
        elif "SELECT CAST(GETDATE() AS DATE)" in sql:
            self._alvo = "hoje"
        elif "COUNT(*) FROM dbo.etl_chamado WHERE ativo = 1" in sql:
            self._alvo = "total"
        return self

    def fetchall(self):
        return list(self.dados.get(self._alvo, []))

    def fetchone(self):
        if self._alvo == "hoje":
            return (HOJE,)
        return (self.total,)

    def close(self):
        pass


@pytest.fixture
def cliente():
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "U1", "perfil": "operador", "permissoes": ["tela_chamados"]}
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def banco(monkeypatch):
    estado = {"cur": CursorFalso()}

    def _fabrica():
        conn = MagicMock()
        conn.cursor.return_value = estado["cur"]
        return conn

    monkeypatch.setattr("routers.chamados.get_db_conn", _fabrica)
    return estado


# ═══════════ 1. aging: zero explícito, ordem fixa ═══════════════════════════

def test_faixa_sem_chamado_vem_com_zero_explicito(cliente, banco):
    """Buraco no gráfico faria 'nenhum velho' parecer 'não medi isso'."""
    banco["cur"] = CursorFalso(aging=[("0-3 dias", 5)], total=5)
    d = cliente.get("/chamados/indicadores").json()
    assert len(d["aging"]) == len(FAIXAS_AGING)
    por_faixa = {a["faixa"]: a["total"] for a in d["aging"]}
    assert por_faixa["0-3 dias"] == 5
    assert por_faixa["mais de 14 dias"] == 0, "faixa vazia precisa aparecer com 0"


def test_aging_mantem_a_ordem_das_faixas(cliente, banco):
    """Ordem embaralhada faria a leitura 'está piorando?' exigir esforço."""
    banco["cur"] = CursorFalso(aging=[("mais de 14 dias", 2), ("0-3 dias", 7)], total=9)
    d = cliente.get("/chamados/indicadores").json()
    assert [a["faixa"] for a in d["aging"]] == [nome for nome, _i, _f in FAIXAS_AGING]


# ═══════════ 2. a série de 14 dias não tem buraco ═══════════════════════════

def test_fluxo_traz_todos_os_dias_mesmo_sem_movimento(cliente, banco):
    banco["cur"] = CursorFalso(entradas=[(_dt.date(2026, 8, 13), 3)],
                               saidas=[(_dt.date(2026, 8, 12), 1)])
    d = cliente.get("/chamados/indicadores").json()
    assert len(d["fluxo"]) == DIAS_FLUXO
    por_dia = {x["dia"]: x for x in d["fluxo"]}
    assert por_dia["2026-08-13"]["entradas"] == 3
    assert por_dia["2026-08-13"]["saidas"] == 0, "dia sem saída é ZERO dito"
    assert por_dia["2026-08-12"]["saidas"] == 1
    # nenhum dia pode faltar nem vir nulo
    assert all(isinstance(x["entradas"], int) and isinstance(x["saidas"], int)
               for x in d["fluxo"])


def test_fluxo_vem_em_ordem_cronologica(cliente, banco):
    banco["cur"] = CursorFalso()
    dias = [x["dia"] for x in cliente.get("/chamados/indicadores").json()["fluxo"]]
    assert dias == sorted(dias), "a linha do tempo precisa ir do mais antigo ao hoje"
    assert dias[-1] == "2026-08-13"


# ═══════════ 3. o denominador viaja junto ═══════════════════════════════════

def test_total_ativos_acompanha_os_agregados(cliente, banco):
    """Sem o denominador a tela não consegue escrever 'x de y (z%)'."""
    banco["cur"] = CursorFalso(aging=[("0-3 dias", 4)], total=12)
    d = cliente.get("/chamados/indicadores").json()
    assert d["total_ativos"] == 12


# ═══════════ 4. o corte do top-N é dito ═════════════════════════════════════

def test_corte_de_responsaveis_e_declarado(cliente, banco):
    """Calar o corte faria a soma do gráfico não bater com a fila."""
    muitos = [(f"Pessoa {i:02d}", 20 - i) for i in range(TOPO_RESPONSAVEIS + 5)]
    banco["cur"] = CursorFalso(carga=muitos, total=sum(v for _n, v in muitos))
    d = cliente.get("/chamados/indicadores").json()
    assert len(d["carga"]) == TOPO_RESPONSAVEIS
    assert d["responsaveis_ocultos"] == 5


def test_sem_corte_nao_inventa_ocultos(cliente, banco):
    banco["cur"] = CursorFalso(carga=[("Fulano", 3), ("Beltrana", 1)], total=4)
    d = cliente.get("/chamados/indicadores").json()
    assert d["responsaveis_ocultos"] == 0
    assert d["carga"][0]["responsavel"] == "Fulano"


# ═══════════ 5. tipo × estado ═══════════════════════════════════════════════

def test_tipo_estado_traz_todas_as_colunas_do_kanban(cliente, banco):
    """A grade da tela é desenhada a partir daqui — faltar coluna some com ela."""
    banco["cur"] = CursorFalso(tipo_estado=[("incident", "novo", 2)], total=2)
    d = cliente.get("/chamados/indicadores").json()
    assert d["tipo_estado"]["estados"] == ["novo", "andamento", "aguardando",
                                           "resolvido", "outros"]
    assert d["tipo_estado"]["tipos"] == ["incident"]
    assert d["tipo_estado"]["celulas"] == [
        {"tipo": "incident", "estado": "novo", "total": 2}]


def test_tipo_estado_sem_dado_nao_inventa_tipo(cliente, banco):
    banco["cur"] = CursorFalso()
    d = cliente.get("/chamados/indicadores").json()
    assert d["tipo_estado"]["tipos"] == []
    assert d["tipo_estado"]["celulas"] == []


# ═══════════ 6. degradação ══════════════════════════════════════════════════

def test_sem_a_migration_avisa_em_vez_de_estourar(cliente, banco):
    banco["cur"] = CursorFalso(explode=True)
    r = cliente.get("/chamados/indicadores")
    assert r.status_code == 200
    d = r.json()
    assert d["migration_ausente"] is True
    assert d["aging"] == [] and d["fluxo"] == [] and d["total_ativos"] == 0


def test_indicadores_exigem_autenticacao():
    with TestClient(app) as anonimo:
        assert anonimo.get("/chamados/indicadores").status_code in (401, 403)
