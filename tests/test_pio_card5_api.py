"""GET /pio/card5/{resumo,propostas} — Card 5 (Emitidas, VG + AP) lendo a FOTO diária.

RITM0118510. Prende o que distingue o Card 5:
  1. Número do card = AGG (`SUM(QTD_CONTRATOS)`, `SUM(VLR_PREMIO_TOTAL)`); nunca a FAT.
  2. Unidade = contrato (SEGMENTO + NUM_SIVPF): lista com ordenação fechada nessa chave.
  3. Foto = `DTA_MOVIMENTO` + `LOTE_ID` do CTL `PUBLICADO`; sem GETDATE/MAX/DATEADD.
  4. Cor do selo (única regra, no backend): cancelada / suspensa / emitida.
  5. Motivo do cancelamento só com SIT_CONTRATO = 'Inativo'.
  6. Prêmio NULL ≠ zero; geografia da agência em campos próprios; CPF/CNPJ com zeros.
  7. Os outros cards e `pio.py` não mudam.
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
from routers.pio_card5 import tom_do_status  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
LOTE = "00000000-0000-4000-8000-0000000000a5"
FOTO = (date(2026, 11, 2), LOTE, datetime(2026, 11, 2, 7, 41, 30))


def _linha(id_foto=1, seg="VG", num=Decimal("1000000000001"), cod="3", sub="Integrada",
           sit="Ativo", motivo=None, canc=None, cpf=Decimal("1234567890"), tipo="PF",
           premio=Decimal("100.25"), tip_contato="Celular", ddd=11, fone=Decimal("912345678")):
    """Uma linha na ordem de `_NOMES`."""
    return (id_foto, seg, num, "CLIENTE FICTICIO", cpf, tipo, 316, Decimal("12345"),
            date(2026, 10, 16), date(2026, 10, 18), date(1980, 5, 10), "VIDA SIMULADA",
            "Vida em Grupo", premio, Decimal("50000.00"), "CIDADE AGENCIA", "RJ", sub, sit,
            cod, canc, motivo, "x@example.com", ddd, fone, tip_contato)


class Cursor:
    def __init__(self, foto=FOTO, agg=(814968, Decimal("492469590.63"), 553171, 814968),
                 total=814968, linhas=None, estoura=False):
        self.foto, self.agg, self.total = foto, agg, total
        self.linhas, self.estoura = linhas or [], estoura
        self.sqls: list[str] = []
        self.params: list = []
        self._ult = ""

    def execute(self, sql, params=None):
        if self.estoura:
            raise Exception("Invalid object name 'dbo.CTL_ORQ_CARD05_LOTE'")
        self.sqls.append(sql)
        self.params.append(params)
        self._ult = sql
        return self

    def fetchone(self):
        s = self._ult
        if "CTL_ORQ_CARD05_LOTE" in s:
            return self.foto
        if "FROM dbo.AGG_ORQ_CARD05_FOTO" in s:
            return self.agg if "VLR_PREMIO_TOTAL" in s else (self.agg[0],)
        if "COUNT_BIG(*) FROM dbo.FAT_ORQ_CARD05_FOTO" in s:
            return (self.total,)
        return None

    def fetchall(self):
        return self.linhas

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

    monkeypatch.setattr("routers.pio_card5.get_db_conn", _fabrica)
    monkeypatch.setattr("routers.pio_card1._hoje", lambda: date(2026, 11, 2))
    return estado


def _sql(banco) -> str:
    return " ".join(banco["cur"].sqls)


def test_resumo_le_o_agregado_e_nao_a_fato(cliente, banco):
    d = cliente.get("/pio/card5/resumo").json()
    assert "AGG_ORQ_CARD05_FOTO" in _sql(banco) and "FAT_ORQ_CARD05_FOTO" not in _sql(banco)
    assert d["quantidade"] == 814968 and d["premio_total"] == 492469590.63
    assert d["grupos"] == 553171 and d["referencia"] == "2026-11-02" and d["disponivel"]
    assert "SUM(QTD_CONTRATOS)" in _sql(banco) and "SUM(VLR_PREMIO_TOTAL)" in _sql(banco)


def test_premio_parcial_expoe_quantos_contratos_tem_valor(cliente, banco):
    banco["cur"] = Cursor(agg=(10, Decimal("500.00"), 3, 4))
    d = cliente.get("/pio/card5/resumo").json()
    assert d["quantidade"] == 10 and d["premios_informados"] == 4 and d["premio_total"] == 500.0
    assert "QTD_PREMIOS_INFORMADOS" in _sql(banco)


def test_premio_sem_nenhum_informado_e_desconhecido_nao_zero(cliente, banco):
    banco["cur"] = Cursor(agg=(10, None, 3, 0))
    assert cliente.get("/pio/card5/resumo").json()["premio_total"] is None
    banco["cur"] = Cursor(agg=(0, None, 0, 0))          # foto lida e vazia: zero de verdade
    d = cliente.get("/pio/card5/resumo").json()
    assert d["quantidade"] == 0 and d["premio_total"] == 0.0


@pytest.mark.parametrize("seg,cod,esperado", [
    ("VG", "3", "emitida"), ("VG", "B", "emitida"), ("VG", "C", "emitida"),
    ("VG", "7", "emitida"), ("VG", "8", "emitida"), ("VG", "9", "emitida"),
    ("VG", "6", "suspensa"), ("VG", "4", "cancelada"),
    ("AP", "0", "emitida"), ("AP", "2", "cancelada"),
    ("AP", "6", "emitida"), ("AP", "4", "emitida"),      # códigos de VG não valem em AP
    ("VG", "2", "emitida"), (None, None, "emitida"),
])
def test_tom_do_selo(seg, cod, esperado):
    assert tom_do_status(seg, cod) == esperado


def test_lista_traz_tom_e_situacao_real(cliente, banco):
    banco["cur"] = Cursor(linhas=[
        _linha(1, cod="3", sub="Integrada"),
        _linha(2, num=Decimal("2"), cod="6", sub="Cobertura Suspensa"),
        _linha(3, num=Decimal("3"), cod="4", sub="Cancelada após Aceitação", sit="Inativo",
               motivo="Cancelamento — Débito Automático", canc=date(2026, 10, 20)),
        _linha(4, seg="AP", num=Decimal("4"), cod="2", sub="Cancelado", sit="Inativo", motivo=None)])
    itens = cliente.get("/pio/card5/propostas").json()["itens"]
    assert [i["tom_status"] for i in itens] == ["emitida", "suspensa", "cancelada", "cancelada"]
    assert [i["sub_situacao"] for i in itens][1] == "Cobertura Suspensa"
    assert [i["segmento"] for i in itens] == ["VG", "VG", "VG", "AP"]


def test_motivo_so_com_contrato_inativo(cliente, banco):
    banco["cur"] = Cursor(linhas=[
        _linha(1, sit="Ativo", motivo="resíduo que não deve sair", canc=date(2026, 10, 20)),
        _linha(2, cod="4", sit="Inativo", motivo="Alteração de Causa", canc=date(2026, 10, 20)),
        _linha(3, seg="AP", cod="2", sit="Inativo", motivo=None)])
    a, b, c = cliente.get("/pio/card5/propostas").json()["itens"]
    assert (a["inativo"], a["motivo_cancelamento"], a["cancelamento"]) == (False, None, None)
    assert (b["inativo"], b["motivo_cancelamento"], b["cancelamento"]) == (True, "Alteração de Causa", "2026-10-20")
    assert (c["inativo"], c["motivo_cancelamento"]) == (True, None)      # sem motivo na origem


def test_ordenacao_fechada_na_chave_do_contrato_e_total_e_contagem_de_linhas(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha(1)])
    d = cliente.get("/pio/card5/propostas").json()
    sql = _sql(banco)
    assert "ORDER BY f.DTH_VENDA ASC, f.SEGMENTO ASC, f.NUM_SIVPF ASC" in sql
    assert d["total"] == 814968 and d["itens"][0]["dias_pendente"] == 0
    assert "SUM(f.VLR_CONTRATO)" not in sql and "SUM(VLR_CONTRATO)" not in sql


def test_toda_leitura_filtra_data_e_lote_e_nao_usa_relogio(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card5/resumo")
    cliente.get("/pio/card5/propostas")
    for sql in banco["cur"].sqls:
        if "AGG_ORQ" in sql or "FROM dbo.FAT_ORQ" in sql:
            assert "DTA_MOVIMENTO = ?" in sql and "LOTE_ID = ?" in sql
    todo = _sql(banco)
    assert "MAX(DTA_MOVIMENTO)" not in todo and "GETDATE" not in todo and "DATEADD" not in todo
    assert "STATUS = 'PUBLICADO'" in todo


def test_nao_le_tabelas_dos_outros_cards_nem_a_det_legada(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card5/resumo")
    cliente.get("/pio/card5/propostas")
    for proibido in ("CARD01", "CARD02", "CARD03", "CARD04", "PIO_PROPOSTA_EMITIDA_DET", "PIO_AGG"):
        assert proibido not in _sql(banco)


def test_geografia_documento_e_contato(cliente, banco):
    banco["cur"] = Cursor(linhas=[
        _linha(1, cpf=Decimal("1234567890"), tipo="PF"),
        _linha(2, cpf=Decimal("123456000199"), tipo="PJ", tip_contato="Fixo", ddd=21, fone=Decimal("22223333")),
        _linha(3, ddd=None, fone=Decimal("0"), premio=None)])
    a, b, c = cliente.get("/pio/card5/propostas").json()["itens"]
    assert a["uf"] == "" and a["cidade"] == "" and a["uf_agencia"] == "RJ"
    assert a["cpf"] == "01234567890" and b["cpf"] == "00123456000199"
    assert a["contato"]["celular"] == "(11) 91234-5678" and a["contato"]["residencial"] is None
    assert b["contato"]["residencial"] == "(21) 2222-3333" and b["contato"]["celular"] is None
    assert c["contato"]["celular"] is None and c["premio"] is None
    assert a["idade"] == 46 and a["emissao"] == "2026-10-18"


def test_sem_foto_publicada_e_disponivel_com_zero(cliente, banco):
    banco["cur"] = Cursor(foto=None)
    r = cliente.get("/pio/card5/resumo").json()
    assert r["disponivel"] is True and r["referencia"] is None and r["quantidade"] == 0
    p = cliente.get("/pio/card5/propostas").json()
    assert p["disponivel"] is True and p["itens"] == [] and p["total"] == 0


def test_tabela_ausente_e_indisponivel_nunca_zero(cliente, banco):
    banco["cur"] = Cursor(estoura=True)
    for rota in ("/pio/card5/resumo", "/pio/card5/propostas"):
        assert cliente.get(rota).json()["disponivel"] is False


def test_detalhe_fora_da_retencao_nao_e_erro(cliente, banco):
    banco["cur"] = Cursor(total=0, linhas=[])
    assert cliente.get("/pio/card5/propostas").json()["detalhe_disponivel"] is False
    assert cliente.get("/pio/card5/propostas?busca=zzz").json()["detalhe_disponivel"] is True


def test_foto_de_dia_anterior_marca_desatualizado(cliente, banco, monkeypatch):
    monkeypatch.setattr("routers.pio_card1._hoje", lambda: date(2026, 11, 3))
    d = cliente.get("/pio/card5/resumo").json()
    assert d["desatualizado"] is True and d["dias_defasagem"] == 1


def test_busca_e_parametrizada(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card5/propostas?modo=cpf&busca=123.456.789-01")
    sql = " ".join(s for s in banco["cur"].sqls if "ORDER BY" in s)
    assert "COD_CPF_CNPJ" in sql and "123.456" not in sql


def test_limite_maximo_e_validado(cliente, banco):
    assert cliente.get("/pio/card5/propostas?limite=201").status_code == 422
    assert cliente.get("/pio/card5/propostas?offset=-1").status_code == 422


def test_pio_py_nao_conhece_as_tabelas_novas_e_router_registrado():
    assert "ORQ_CARD05" not in (RAIZ / "api" / "routers" / "pio.py").read_text(encoding="utf-8")
    assert (RAIZ / "api" / "main.py").read_text(encoding="utf-8").count("pio_card5") == 2
