"""GET /pio/card6/{resumo,propostas,motivos} — Card 6 (Rejeitadas, VG) lendo a FOTO diária.

RITM0118511. Prende o que distingue o Card 6 (unidade = CERTIFICADO; FAT = uma linha por motivo):
  1. Número do card = AGG (`SUM(QTD_CONTRATOS)`, `SUM(VLR_PREMIO_TOTAL)`); nunca a FAT.
  2. Lista agrupa por `NUM_SIVPF`; total = `COUNT(DISTINCT NUM_SIVPF)`; nenhum SQL soma `VLR_CONTRATO`.
  3. Foto = `DTA_MOVIMENTO` + `LOTE_ID` do CTL `PUBLICADO`; sem GETDATE/MAX/DATEADD.
  4. Prêmio NULL ≠ zero; prêmio parcial exposto; geografia da agência em campos próprios.
  5. Sem "dias" ao lado de Rejeitada (dias_pendente = 0); declínio e dias da quitação ao declínio.
  6. Motivos: parametrizados por certificado + foto; sem dados pessoais.
Nada toca banco: cursor dublê.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app  # noqa: E402

from deps import get_current_user  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
LOTE = "00000000-0000-4000-8000-0000000000a6"
FOTO = (date(2026, 11, 2), LOTE, datetime(2026, 11, 2, 7, 41, 30))


def _linha(id_foto=1, cert=Decimal("1000000000001"), cpf=Decimal("1234567890"), tipo="PF",
           motivos=4, premio=Decimal("100.25"), dias=12, declinio=date(2026, 10, 20),
           ddd_cel=11, cel=Decimal("912345678"), email="x@example.com"):
    """Uma linha na ordem de `_COLUNAS_LISTA`."""
    return (id_foto, cert, "CLIENTE FICTICIO", cpf, tipo, 316, Decimal("12345"),
            date(2026, 10, 1), date(1980, 5, 10), "VIDA SIMULADA", "Vida em Grupo",
            premio, Decimal("50000.00"), "CIDADE AGENCIA", "RJ", "Não Aceita",
            motivos, date(2026, 10, 8), declinio, dias, email, None, None, ddd_cel, cel)


class Cursor:
    def __init__(self, foto=FOTO, agg=(2087, Decimal("940842.79"), 1730, 7638, 2087), total=2087,
                 linhas=None, motivos=None, estoura=False):
        self.foto, self.agg, self.total = foto, agg, total
        self.linhas, self.motivos, self.estoura = linhas or [], motivos or [], estoura
        self.sqls: list[str] = []
        self.params: list = []
        self._ult = ""

    def execute(self, sql, params=None):
        if self.estoura:
            raise Exception("Invalid object name 'dbo.CTL_ORQ_CARD06_LOTE'")
        self.sqls.append(sql)
        self.params.append(params)
        self._ult = sql
        return self

    def fetchone(self):
        s = self._ult
        if "CTL_ORQ_CARD06_LOTE" in s:
            return self.foto
        if "FROM dbo.AGG_ORQ_CARD06_FOTO" in s:
            return self.agg if "VLR_PREMIO_TOTAL" in s else (self.agg[0],)
        if "COUNT(DISTINCT f.NUM_SIVPF)" in s:
            return (self.total,)
        return None

    def fetchall(self):
        return self.motivos if "COD_MSG_CRITICA" in self._ult and "GROUP BY" not in self._ult else self.linhas

    def close(self):
        pass


@pytest.fixture
def cliente():
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "U1", "perfil": "operador", "permissoes": ["tela_caixa_seguro"]}
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def banco(monkeypatch):
    estado = {"cur": Cursor()}

    def _fabrica():
        conn = MagicMock()
        conn.cursor.return_value = estado["cur"]
        return conn

    monkeypatch.setattr("routers.pio_card6.get_db_conn", _fabrica)
    monkeypatch.setattr("routers.pio_card1._hoje", lambda: date(2026, 11, 2))
    return estado


def _sql(banco) -> str:
    return " ".join(banco["cur"].sqls)


def test_resumo_le_o_agregado_e_nao_a_fato(cliente, banco):
    d = cliente.get("/pio/card6/resumo").json()
    assert "AGG_ORQ_CARD06_FOTO" in _sql(banco) and "FAT_ORQ_CARD06_FOTO" not in _sql(banco)
    assert d["quantidade"] == 2087 and d["premio_total"] == 940842.79
    assert d["motivos"] == 7638 and d["grupos"] == 1730 and d["premios_informados"] == 2087
    assert d["referencia"] == "2026-11-02" and d["disponivel"] and not d["desatualizado"]
    assert "SUM(QTD_CONTRATOS)" in _sql(banco) and "SUM(VLR_PREMIO_TOTAL)" in _sql(banco)


def test_premio_sem_nenhum_informado_e_desconhecido_nao_zero(cliente, banco):
    banco["cur"] = Cursor(agg=(10, None, 3, 40, 0))
    assert cliente.get("/pio/card6/resumo").json()["premio_total"] is None
    banco["cur"] = Cursor(agg=(0, None, 0, 0, 0))
    d = cliente.get("/pio/card6/resumo").json()
    assert d["quantidade"] == 0 and d["premio_total"] == 0.0
    banco["cur"] = Cursor(agg=(10, Decimal("500"), 3, 40, 4))
    assert cliente.get("/pio/card6/resumo").json()["premios_informados"] == 4     # parcial


def test_lista_agrupa_por_certificado_e_total_e_distinto(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha(1), _linha(2, cert=Decimal("1000000000002"))])
    d = cliente.get("/pio/card6/propostas").json()
    sql = _sql(banco)
    assert "GROUP BY f.NUM_SIVPF" in sql and "COUNT(DISTINCT f.NUM_SIVPF)" in sql
    assert d["total"] == 2087 and len(d["itens"]) == 2
    assert [i["proposta"] for i in d["itens"]] == ["1000000000001", "1000000000002"]
    i = d["itens"][0]
    assert i["motivos"] == 4 and i["sub_situacao"] == "Não Aceita" and i["premio"] == 100.25


def test_sem_dias_ao_lado_de_rejeitada_e_declinio_por_certificado(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha(), _linha(2, dias=None, declinio=None)])
    a, b = cliente.get("/pio/card6/propostas").json()["itens"]
    assert a["dias_pendente"] == 0 and b["dias_pendente"] == 0
    assert a["declinio"] == "2026-10-20" and a["dias_venda_declinio"] == 12 and a["quitacao"] == "2026-10-08"
    assert b["declinio"] is None and b["dias_venda_declinio"] is None


def test_nenhum_sql_soma_o_premio_por_linha_nem_conta_linhas_como_contratos(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card6/resumo")
    cliente.get("/pio/card6/propostas")
    cliente.get("/pio/card6/motivos?certificado=1000000000001")
    sql = _sql(banco)
    assert "SUM(f.VLR_CONTRATO)" not in sql and "SUM(VLR_CONTRATO)" not in sql
    assert "COUNT_BIG(*) FROM dbo.FAT" not in sql


def test_toda_leitura_filtra_data_e_lote_e_nao_usa_relogio(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card6/resumo")
    cliente.get("/pio/card6/propostas")
    cliente.get("/pio/card6/motivos?certificado=1000000000001")
    for sql in banco["cur"].sqls:
        if "AGG_ORQ" in sql or "FROM dbo.FAT_ORQ" in sql:
            assert "DTA_MOVIMENTO = ?" in sql and "LOTE_ID = ?" in sql
    todo = _sql(banco)
    assert "MAX(DTA_MOVIMENTO)" not in todo and "GETDATE" not in todo and "DATEADD" not in todo
    assert "STATUS = 'PUBLICADO'" in todo


def test_nao_le_tabelas_dos_outros_cards_nem_a_det_legada(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card6/resumo")
    cliente.get("/pio/card6/propostas")
    for proibido in ("CARD01", "CARD02", "CARD03", "CARD04", "CARD05", "PIO_PROPOSTA_REJEITADA_DET", "PIO_AGG"):
        assert proibido not in _sql(banco)


def test_geografia_documento_e_contato(cliente, banco):
    banco["cur"] = Cursor(linhas=[
        _linha(1, cpf=Decimal("1234567890"), tipo="PF"),
        _linha(2, cpf=Decimal("123456000199"), tipo="PJ"),
        _linha(3, ddd_cel=None, cel=Decimal("0"), email="   ", premio=None)])
    a, b, c = cliente.get("/pio/card6/propostas").json()["itens"]
    assert a["uf"] == "" and a["cidade"] == "" and a["uf_agencia"] == "RJ" and a["cidade_agencia"] == "CIDADE AGENCIA"
    assert a["cpf"] == "01234567890" and b["cpf"] == "00123456000199"
    assert a["contato"]["celular"] == "(11) 91234-5678"
    assert c["contato"] == {"email": None, "celular": None, "residencial": None} and c["premio"] is None
    assert a["idade"] == 46


def test_sem_foto_publicada_e_disponivel_com_zero(cliente, banco):
    banco["cur"] = Cursor(foto=None)
    r = cliente.get("/pio/card6/resumo").json()
    assert r["disponivel"] is True and r["referencia"] is None and r["quantidade"] == 0
    p = cliente.get("/pio/card6/propostas").json()
    assert p["disponivel"] is True and p["itens"] == [] and p["total"] == 0


def test_tabela_ausente_e_indisponivel_nunca_zero(cliente, banco):
    banco["cur"] = Cursor(estoura=True)
    for rota in ("/pio/card6/resumo", "/pio/card6/propostas", "/pio/card6/motivos?certificado=1"):
        assert cliente.get(rota).json()["disponivel"] is False


def test_detalhe_fora_da_retencao_nao_e_erro(cliente, banco):
    banco["cur"] = Cursor(total=0, linhas=[])
    assert cliente.get("/pio/card6/propostas").json()["detalhe_disponivel"] is False
    assert cliente.get("/pio/card6/propostas?busca=zzz").json()["detalhe_disponivel"] is True


def test_foto_de_dia_anterior_marca_desatualizado(cliente, banco, monkeypatch):
    monkeypatch.setattr("routers.pio_card1._hoje", lambda: date(2026, 11, 3))
    d = cliente.get("/pio/card6/resumo").json()
    assert d["desatualizado"] is True and d["dias_defasagem"] == 1


def test_busca_e_parametrizada(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card6/propostas?modo=cpf&busca=123.456.789-01")
    sql = " ".join(s for s in banco["cur"].sqls if "GROUP BY" in s)
    assert "COD_CPF_CNPJ" in sql and "123.456" not in sql


def test_motivos_do_certificado_vao_por_parametro_e_sem_dados_pessoais(cliente, banco):
    banco["cur"] = Cursor(motivos=[(52, "Falta documento", "compl", date(2026, 10, 28)),
                                   (7, "  ", None, None)])
    d = cliente.get("/pio/card6/motivos?certificado=1000000000001").json()
    sql = [s for s in banco["cur"].sqls if "NUM_SIVPF = ?" in s]
    assert sql and banco["cur"].params[banco["cur"].sqls.index(sql[0])][-1] == 1000000000001
    assert d["itens"][0] == {"codigo": 52, "descricao": "Falta documento", "complemento": "compl",
                             "data_motivo": "2026-10-28"}
    assert d["itens"][1] == {"codigo": 7, "descricao": "", "complemento": "", "data_motivo": None}
    assert "NOM_PESSOA" not in sql[0] and "COD_CPF" not in sql[0]
    assert cliente.get("/pio/card6/motivos").status_code == 422
    assert cliente.get("/pio/card6/motivos?certificado=abc").status_code == 422


def test_limite_maximo_e_validado(cliente, banco):
    assert cliente.get("/pio/card6/propostas?limite=201").status_code == 422
    assert cliente.get("/pio/card6/propostas?offset=-1").status_code == 422


def test_pio_py_nao_conhece_as_tabelas_novas_e_router_registrado():
    assert "ORQ_CARD06" not in (RAIZ / "api" / "routers" / "pio.py").read_text(encoding="utf-8")
    assert (RAIZ / "api" / "main.py").read_text(encoding="utf-8").count("pio_card6") == 2
