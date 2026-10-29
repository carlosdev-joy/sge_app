"""GET /pio/card4/{resumo,propostas,pendencias} — Card 4 (críticas) lendo a FOTO diária.

Prende o que distingue o Card 4 dos outros (a unidade é o CERTIFICADO):

  1. Número do card = AGG (`SUM(QTD_CONTRATOS)`, `SUM(VLR_PREMIO_TOTAL)`); nunca a FAT.
  2. A lista agrupa por `NUM_SIVPF` e o total é `COUNT(DISTINCT NUM_SIVPF)`; nenhum SQL
     soma `VLR_CONTRATO` nem usa `COUNT(*)` como quantidade de contratos.
  3. Foto = `DTA_MOVIMENTO` + `LOTE_ID` do CTL `PUBLICADO`; sem GETDATE/D-30/MAX.
  4. Geografia da AGÊNCIA fica em `uf_agencia`/`cidade_agencia`; `uf`/`cidade` vazios.
  5. CPF/CNPJ numérico recupera zeros à esquerda (PF 11, PJ 14); contato ausente = None.
  6. Pendências: parametrizadas por certificado + foto; tabela ausente ≠ zero.
  7. Os outros cards não mudam.
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
LOTE = "00000000-0000-4000-8000-0000000000a4"
FOTO = (date(2026, 10, 29), LOTE, datetime(2026, 10, 29, 7, 41, 30))


def _linha(id_foto=1, cert=Decimal("1000000000001"), cpf=Decimal("1234567890"), tipo="PF",
           criticas=2, quitacao=None, ddd_cel=11, cel=Decimal("912345678"), email="x@example.com"):
    """Uma linha na ordem de `_COLUNAS_LISTA`."""
    return (id_foto, cert, "CLIENTE FICTICIO", cpf, tipo, 316, Decimal("12345"),
            date(2026, 10, 16), date(1980, 5, 10), "VIDA SIMULADA", "Vida em Grupo",
            Decimal("100.25"), Decimal("50000.00"), "CIDADE AGENCIA", "RJ",
            "Em Crítica", criticas, quitacao, email, None, None, ddd_cel, cel)


class Cursor:
    def __init__(self, foto=FOTO, agg=(407, Decimal("528747.15"), 386, 628), total=407,
                 linhas=None, pend=None, estoura=False):
        self.foto, self.agg, self.total = foto, agg, total
        self.linhas, self.pend, self.estoura = linhas or [], pend or [], estoura
        self.sqls: list[str] = []
        self.params: list = []
        self._ult = ""

    def execute(self, sql, params=None):
        if self.estoura:
            raise Exception("Invalid object name 'dbo.CTL_ORQ_CARD04_LOTE'")
        self.sqls.append(sql)
        self.params.append(params)
        self._ult = sql
        return self

    def fetchone(self):
        s = self._ult
        if "CTL_ORQ_CARD04_LOTE" in s:
            return self.foto
        if "FROM dbo.AGG_ORQ_CARD04_FOTO" in s:
            return self.agg if "VLR_PREMIO_TOTAL" in s else (self.agg[0],)
        if "COUNT(DISTINCT f.NUM_SIVPF)" in s:
            return (self.total,)
        return None

    def fetchall(self):
        return self.pend if "COD_MSG_CRITICA" in self._ult and "GROUP BY" not in self._ult else self.linhas

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

    monkeypatch.setattr("routers.pio_card4.get_db_conn", _fabrica)
    monkeypatch.setattr("routers.pio_card1._hoje", lambda: date(2026, 10, 29))
    return estado


def _sql(banco) -> str:
    return " ".join(banco["cur"].sqls)


def test_resumo_le_o_agregado_e_nao_a_fato(cliente, banco):
    d = cliente.get("/pio/card4/resumo").json()
    assert "AGG_ORQ_CARD04_FOTO" in _sql(banco) and "FAT_ORQ_CARD04_FOTO" not in _sql(banco)
    assert d["quantidade"] == 407 and d["premio_total"] == 528747.15
    assert d["criticas"] == 628 and d["grupos"] == 386
    assert d["referencia"] == "2026-10-29" and d["disponivel"] and not d["desatualizado"]
    assert "SUM(QTD_CONTRATOS)" in _sql(banco) and "SUM(VLR_PREMIO_TOTAL)" in _sql(banco)


def test_lista_agrupa_por_certificado_e_total_e_distinto(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha(1), _linha(2, cert=Decimal("1000000000002"))])
    d = cliente.get("/pio/card4/propostas").json()
    sql = _sql(banco)
    assert "GROUP BY f.NUM_SIVPF" in sql and "COUNT(DISTINCT f.NUM_SIVPF)" in sql
    assert d["total"] == 407 and len(d["itens"]) == 2
    assert [i["proposta"] for i in d["itens"]] == ["1000000000001", "1000000000002"]
    assert d["itens"][0]["criticas"] == 2 and d["itens"][0]["sub_situacao"] == "Em Crítica"
    assert d["itens"][0]["premio"] == 100.25      # uma vez, não × nº de críticas


def test_nenhum_sql_soma_o_premio_por_linha_nem_conta_linhas_como_contratos(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card4/resumo")
    cliente.get("/pio/card4/propostas")
    cliente.get("/pio/card4/pendencias?certificado=1000000000001")
    sql = _sql(banco)
    assert "SUM(f.VLR_CONTRATO)" not in sql and "SUM(VLR_CONTRATO)" not in sql
    assert "COUNT_BIG(*) FROM dbo.FAT" not in sql


def test_toda_leitura_filtra_data_e_lote_e_nao_usa_relogio(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card4/resumo")
    cliente.get("/pio/card4/propostas")
    cliente.get("/pio/card4/pendencias?certificado=1000000000001")
    for sql in banco["cur"].sqls:
        if "AGG_ORQ" in sql or "FROM dbo.FAT_ORQ" in sql:
            assert "DTA_MOVIMENTO = ?" in sql and "LOTE_ID = ?" in sql
    todo = _sql(banco)
    assert "MAX(DTA_MOVIMENTO)" not in todo
    assert "GETDATE" not in todo and "DATEADD" not in todo
    assert "STATUS = 'PUBLICADO'" in todo


def test_nao_le_tabelas_dos_outros_cards_nem_a_det_legada(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card4/resumo")
    cliente.get("/pio/card4/propostas")
    todo = _sql(banco)
    for proibido in ("CARD01", "CARD02", "CARD03", "PIO_PROPOSTA_CRITICA_DET", "PIO_AGG"):
        assert proibido not in todo


def test_geografia_da_agencia_fica_em_campos_proprios(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    i = cliente.get("/pio/card4/propostas").json()["itens"][0]
    assert i["uf"] == "" and i["cidade"] == ""
    assert i["uf_agencia"] == "RJ" and i["cidade_agencia"] == "CIDADE AGENCIA"


def test_documento_recupera_zeros_a_esquerda_pf_11_pj_14(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha(1, cpf=Decimal("1234567890"), tipo="PF"),
                                  _linha(2, cpf=Decimal("123456000199"), tipo="PJ")])
    itens = cliente.get("/pio/card4/propostas").json()["itens"]
    assert itens[0]["cpf"] == "01234567890" and itens[1]["cpf"] == "00123456000199"


def test_contato_ausente_e_quitacao_e_datas(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha(1, ddd_cel=None, cel=Decimal("0"), email="   ",
                                         quitacao=date(2026, 10, 20))])
    i = cliente.get("/pio/card4/propostas").json()["itens"][0]
    assert i["contato"] == {"email": None, "celular": None, "residencial": None}
    assert i["quitacao"] == "2026-10-20" and i["data_venda"] == "2026-10-16"
    assert i["dias_pendente"] == 13 and i["idade"] == 46
    assert i["matricula"] == "12345" and i["agencia"] == "316"


def test_sem_foto_publicada_e_disponivel_com_zero(cliente, banco):
    banco["cur"] = Cursor(foto=None)
    r = cliente.get("/pio/card4/resumo").json()
    assert r["disponivel"] is True and r["referencia"] is None and r["quantidade"] == 0
    p = cliente.get("/pio/card4/propostas").json()
    assert p["disponivel"] is True and p["itens"] == [] and p["total"] == 0


def test_tabela_ausente_e_indisponivel_nunca_zero(cliente, banco):
    banco["cur"] = Cursor(estoura=True)
    for rota in ("/pio/card4/resumo", "/pio/card4/propostas", "/pio/card4/pendencias?certificado=1"):
        assert cliente.get(rota).json()["disponivel"] is False


def test_detalhe_fora_da_retencao_nao_e_erro(cliente, banco):
    banco["cur"] = Cursor(total=0, linhas=[])
    d = cliente.get("/pio/card4/propostas").json()
    assert d["total"] == 0 and d["detalhe_disponivel"] is False       # AGG tem 407
    assert cliente.get("/pio/card4/propostas?busca=zzz").json()["detalhe_disponivel"] is True


def test_foto_de_dia_anterior_marca_desatualizado(cliente, banco, monkeypatch):
    monkeypatch.setattr("routers.pio_card1._hoje", lambda: date(2026, 10, 30))
    d = cliente.get("/pio/card4/resumo").json()
    assert d["desatualizado"] is True and d["dias_defasagem"] == 1


def test_busca_e_parametrizada_e_usa_as_colunas_do_card4(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card4/propostas?modo=cpf&busca=123.456.789-01")
    sql = " ".join(s for s in banco["cur"].sqls if "GROUP BY" in s)
    assert "COD_CPF_CNPJ" in sql and "123.456" not in sql      # valor só por parâmetro
    cliente.get("/pio/card4/propostas?modo=proposta&busca=1000")
    assert "f.NUM_SIVPF" in " ".join(banco["cur"].sqls)


def test_pendencias_do_certificado_vao_por_parametro(cliente, banco):
    banco["cur"] = Cursor(pend=[(52, "Falta documento", "compl", date(2026, 10, 28),
                                 Decimal("50000"), Decimal("100.25"))])
    d = cliente.get("/pio/card4/pendencias?certificado=1000000000001").json()
    sql = [s for s in banco["cur"].sqls if "NUM_SIVPF = ?" in s]
    assert sql and banco["cur"].params[banco["cur"].sqls.index(sql[0])][-1] == 1000000000001
    assert d["itens"] == [{"codigo": 52, "descricao": "Falta documento", "complemento": "compl",
                           "data_critica": "2026-10-28", "imp_segurada": 50000.0, "premio": 100.25}]
    assert "NOM_PESSOA" not in sql[0] and "COD_CPF" not in sql[0]
    assert cliente.get("/pio/card4/pendencias").status_code == 422
    assert cliente.get("/pio/card4/pendencias?certificado=abc").status_code == 422


def test_limite_maximo_e_validado(cliente, banco):
    assert cliente.get("/pio/card4/propostas?limite=201").status_code == 422
    assert cliente.get("/pio/card4/propostas?offset=-1").status_code == 422


def test_pio_py_nao_conhece_as_tabelas_novas():
    assert "ORQ_CARD04" not in (RAIZ / "api" / "routers" / "pio.py").read_text(encoding="utf-8")



def test_busca_por_documento_exibido_com_zero_a_esquerda_acha_o_numerico(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card4/propostas?modo=cpf&busca=012.345.678-90")
    idx = next(i for i, s in enumerate(banco["cur"].sqls) if "GROUP BY" in s)
    assert "%1234567890%" in banco["cur"].params[idx]
    cliente.get("/pio/card4/propostas?modo=agencia&busca=0316")      # agência não é afetada
    idx = [i for i, s in enumerate(banco["cur"].sqls) if "GROUP BY" in s][-1]
    assert "0316" in banco["cur"].params[idx]
