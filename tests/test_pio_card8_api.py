"""GET /pio/card8/{resumo,propostas} — Card 8 (Sensibilizações = último movimento Vida) lendo a FOTO.

RITM0118664. Prende o que distingue o Card 8:
  1. Número do card = AGG (SUM(QTD_CONTRATOS), SUM(VLR_SENSIBILIZADO_TOTAL)); total da lista TAMBÉM da AGG
     (a FAT tem ~6,5 milhões de linhas: nenhum COUNT na FAT) e ordenação pelo índice único, nunca por data.
  2. Política de retenção 02/11: FAT só hoje, D-1 e D-2. Mais antiga ou sem linhas do lote = detalhe
     EXPIRADO (`detalhe_disponivel=false`), nunca "zero propostas"; o total da AGG segue válido.
  3. Foto = `DTA_MOVIMENTO` + `LOTE_ID` do CTL `PUBLICADO`; sem GETDATE/MAX/DATEADD no SQL.
  4. Status: NULL = "Sem status"; 3 bytes NUL = "Código não identificado" (nunca rótulo vazio).
  5. Movimento × proposta são estados diferentes; "Sensibilizar" só pela equivalência declarada.
  6. Sem dados do segurado, COD_USUARIO, COD_ERRO nem endereço da agência na resposta.
Nada toca banco: cursor dublê.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
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
from routers.pio_card8 import (  # noqa: E402
    _COLUNAS_LISTA, _NOMES, EQUIVALENTES, SEM_CODIGO, SEM_STATUS, _codigo, _legivel, pode_sensibilizar,
)
from routers.pio_card8 import _item as _item_de  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
LOTE = "00000000-0000-4000-8000-0000000000a8"
FOTO = (date(2026, 11, 2), LOTE, datetime(2026, 11, 2, 7, 41, 30))
AGG = (6540472, Decimal("9532334215.69"), 2345267, 6493, 5926362)      # qtd, valor, grupos, informados, status
NUL3 = "\x00\x00\x00"


def _linha(id_foto=1, proposta=Decimal("123456789"), ident=Decimal("777000111"), empresa=1, linha="VG",
           status="ENV", desc="Enviada", atual="S", desc_atual="Enviado", valor=Decimal("120.40"),
           motivo="Sem Motivo", mov=date(2026, 10, 30), envio=date(2026, 10, 31)):
    """Uma linha na ordem de `_NOMES`."""
    return (id_foto, proposta, ident, empresa, linha, "VIDA SIMULADA", mov, status, desc, 0, motivo, valor, "S",
            envio, date(2026, 11, 1), date(2025, 12, 1), atual, desc_atual, Decimal("12345"), 316, "AGENCIA",
            "RJ", "CIDADE")


class Cursor:
    def __init__(self, foto=FOTO, agg=AGG, existe=True, linhas=None, estoura=False):
        self.foto, self.agg, self.existe = foto, agg, existe
        self.linhas, self.estoura = linhas or [], estoura
        self.sqls: list[str] = []
        self.params: list = []
        self._ult = ""

    def execute(self, sql, params=None):
        if self.estoura:
            raise Exception("Invalid object name 'dbo.CTL_ORQ_CARD08_LOTE'")
        self.sqls.append(sql)
        self.params.append(params)
        self._ult = sql
        return self

    def fetchone(self):
        s = self._ult
        if "CTL_ORQ_CARD08_LOTE" in s:
            return self.foto
        if "SELECT TOP 1 1 FROM dbo.FAT_ORQ_CARD08_FOTO" in s:
            return (1,) if self.existe else None
        if "FROM dbo.AGG_ORQ_CARD08_FOTO" in s:
            return self.agg if "VLR_SENSIBILIZADO_TOTAL" in s else (self.agg[0],)
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

    monkeypatch.setattr("routers.pio_card8.get_db_conn", _fabrica)
    monkeypatch.setattr("routers.pio_card1._hoje", lambda: date(2026, 11, 2))
    return estado


def _sql(banco) -> str:
    return " ".join(banco["cur"].sqls)


def test_resumo_le_o_agregado_e_nao_a_fato(cliente, banco):
    d = cliente.get("/pio/card8/resumo").json()
    assert "AGG_ORQ_CARD08_FOTO" in _sql(banco) and "FAT_ORQ_CARD08_FOTO" not in _sql(banco)
    assert d["quantidade"] == 6540472 and d["premio_total"] == 9532334215.69 and d["grupos"] == 2345267
    assert d["premios_informados"] == 6493 and d["sem_status"] == 6540472 - 5926362
    assert d["referencia"] == "2026-11-02" and d["disponivel"] and not d["desatualizado"]
    assert "SUM(QTD_CONTRATOS)" in _sql(banco) and "SUM(VLR_SENSIBILIZADO_TOTAL)" in _sql(banco)


def test_valor_desconhecido_nao_e_zero_e_negativo_e_preservado(cliente, banco):
    banco["cur"] = Cursor(agg=(10, None, 3, 0, 10))
    assert cliente.get("/pio/card8/resumo").json()["premio_total"] is None
    banco["cur"] = Cursor(agg=(0, None, 0, 0, 0))
    d = cliente.get("/pio/card8/resumo").json()
    assert d["quantidade"] == 0 and d["premio_total"] == 0.0
    banco["cur"] = Cursor(agg=(5, Decimal("-40.00"), 2, 5, 5))
    assert cliente.get("/pio/card8/resumo").json()["premio_total"] == -40.0


def test_total_da_lista_vem_da_agregada_e_nao_conta_a_fato(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    d = cliente.get("/pio/card8/propostas").json()
    sql = _sql(banco)
    assert d["total"] == 6540472 and len(d["itens"]) == 1
    assert "COUNT_BIG" not in sql and "COUNT(" not in sql.replace("COUNT_BIG(*)", "")
    assert "SUM(QTD_CONTRATOS)" in sql


def test_lista_ordena_pelo_indice_unico_e_nunca_por_data(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    d = cliente.get("/pio/card8/propostas").json()
    sql = _sql(banco)
    assert "ORDER BY f.COD_EMPRESA_SIVPF ASC, f.NUM_IDENTIFICACAO_SIVPF ASC" in sql
    assert "ORDER BY f.DATA_ULTIMO_MOVIMENTO" not in sql and "ORDER BY f.DATA" not in sql
    assert d["ordem"] == "identificacao"


@pytest.mark.parametrize("foto_dia,hoje,existe,esperado", [
    (date(2026, 11, 2), date(2026, 11, 2), True, True),     # hoje
    (date(2026, 10, 31), date(2026, 11, 2), True, True),    # D-2 inclusivo
    (date(2026, 10, 30), date(2026, 11, 2), True, False),   # D-3: expirou
    (date(2026, 11, 2), date(2026, 11, 2), False, False),   # recente, mas lote sem linhas na FAT
])
def test_politica_de_retencao_da_fat_detalhe_expirado_nao_e_zero(cliente, banco, monkeypatch, foto_dia, hoje, existe, esperado):
    monkeypatch.setattr("routers.pio_card1._hoje", lambda: hoje)
    banco["cur"] = Cursor(foto=(foto_dia, LOTE, datetime(2026, 11, 2, 7, 41)), existe=existe, linhas=[_linha()])
    d = cliente.get("/pio/card8/propostas").json()
    assert d["detalhe_disponivel"] is esperado and d["total"] == 6540472       # o total da AGG segue válido
    assert bool(d["itens"]) is esperado
    if not esperado:
        assert "OFFSET" not in _sql(banco), "sem detalhe a lista da FAT de 6,5 milhões de linhas nem é lida"
        if foto_dia < hoje - timedelta(days=2):
            assert "FAT_ORQ_CARD08_FOTO" not in _sql(banco), "foto expirada: nem a existência na FAT é consultada"


def test_agregada_vazia_nao_e_detalhe_expirado(cliente, banco):
    banco["cur"] = Cursor(agg=(0, None, 0, 0, 0), existe=False)
    d = cliente.get("/pio/card8/propostas").json()
    assert d["total"] == 0 and d["detalhe_disponivel"] is True and d["itens"] == []


def test_toda_leitura_filtra_data_e_lote_e_nao_usa_relogio_no_sql(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card8/resumo")
    cliente.get("/pio/card8/propostas")
    for sql in banco["cur"].sqls:
        if "AGG_ORQ" in sql or "FROM dbo.FAT_ORQ" in sql:
            assert "DTA_MOVIMENTO = ?" in sql and "LOTE_ID = ?" in sql
    todo = _sql(banco)
    assert "MAX(DTA_MOVIMENTO)" not in todo and "GETDATE" not in todo and "DATEADD" not in todo
    assert "STATUS = 'PUBLICADO'" in todo


def test_nao_le_tabelas_dos_outros_cards(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card8/resumo")
    cliente.get("/pio/card8/propostas")
    for proibido in ("CARD01", "CARD02", "CARD03", "CARD04", "CARD05", "CARD06", "CARD07", "PIO_PROPOSTA_SENSIBILIZACAO_DET", "PIO_AGG", "STG_"):
        assert proibido not in _sql(banco)


def test_item_numero_e_a_proposta_e_sem_ela_a_identificacao(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha(1), _linha(2, proposta=None, ident=Decimal("42"), linha="AP")])
    a, b = cliente.get("/pio/card8/propostas").json()["itens"]
    assert a["proposta"] == "123456789" and a["nome"] == "Vida em Grupo" and a["dias_pendente"] == 0
    assert b["proposta"] == "42" and b["nome"] == "Acidentes Pessoais"
    z = _item_de(_linha(3, proposta=Decimal("0"), ident=Decimal("99")))
    assert z["proposta"] == "99"                                   # 0 é placeholder, não número de proposta
    assert a["premio"] == 120.4 and a["uf_agencia"] == "RJ" and a["data_venda"] == "2025-12-01"
    assert a["sensibilizacao"]["identificacao"] == "777000111" and a["sensibilizacao"]["data_envio"] == "2026-10-31"
    assert a["sensibilizacao"]["status_movimento"] == "Enviada" and a["sensibilizacao"]["status_atual"] == "Enviado"


@pytest.mark.parametrize("bruto,esperado", [
    (None, None), ("", None), ("   ", None), (NUL3, SEM_CODIGO), ("\x00", SEM_CODIGO),
    ("Emitida", "Emitida"), (" Em\x00 Analise ", "Em Analise"), ("EMT", "EMT"),
])
def test_codigos_de_controle_nunca_viram_rotulo_vazio(bruto, esperado):
    assert _legivel(bruto) == esperado


def test_status_nulo_e_nul_viram_rotulos_legiveis_na_lista(cliente, banco):
    banco["cur"] = Cursor(linhas=[
        _linha(1, status=None, desc=None), _linha(2, status=NUL3, desc=NUL3), _linha(3, status="XYZ", desc="XYZ"),
        _linha(4, status="CAN", desc=None)])
    itens = cliente.get("/pio/card8/propostas").json()["itens"]
    mov = [i["sensibilizacao"]["status_movimento"] for i in itens]
    assert mov == [SEM_STATUS, SEM_CODIGO, "XYZ", "CAN"]
    assert all(m.strip() for m in mov)
    assert itens[1]["sensibilizacao"]["status_movimento_codigo"] == ""           # NUL não vira código comparável


def test_equivalencia_declarada_e_unica_e_cobre_o_que_o_usuario_definiu():
    assert EQUIVALENTES == {"S": frozenset({"ENV"}), "R": frozenset({"EMT", "PAI"})}


@pytest.mark.parametrize("atual,mov,esperado", [
    ("S", "ENV", False), ("s", " env ", False), ("R", "EMT", False), ("R", "PAI", False),     # equivalentes: não habilita
    ("S", "EMT", True), ("R", "ENV", True), ("S", "CAN", True),                                # diferem: habilita
    ("N", "ENV", True), ("N", None, True), ("P", "EMT", True),                                # não cobertas habilitam
    ("S", None, True), ("S", NUL3, True), (None, "ENV", True), ("R", "XYZ", True),             # sem status/desconhecido habilita
])
def test_botao_sensibilizar_habilita_quando_o_status_difere_do_ultimo_movimento(atual, mov, esperado):
    assert pode_sensibilizar(atual, mov) is esperado
    assert _codigo(NUL3) == ""


def test_item_traz_pode_sensibilizar(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha(1, status="ENV", atual="S"), _linha(2, status="CAN", atual="S")])
    a, b = cliente.get("/pio/card8/propostas").json()["itens"]
    assert a["sensibilizacao"]["pode_sensibilizar"] is False and b["sensibilizacao"]["pode_sensibilizar"] is True


def test_nao_expoe_usuario_erro_endereco_nem_dado_do_segurado(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    d = cliente.get("/pio/card8/propostas").json()
    sql = _sql(banco)
    for proibido in ("COD_USUARIO", "COD_ERRO", "DES_ENDERECO_AGENCIA", "CEP_AGENCIA", "NOM_PESSOA", "COD_CPF"):
        assert proibido not in sql, proibido
    texto = str(d).lower()
    for proibido in ("cod_usuario", "cod_erro", "endereco", "cpf"):
        assert proibido not in texto.replace("cpf': ''", ""), proibido


def test_sem_foto_publicada_e_disponivel_com_zero(cliente, banco):
    banco["cur"] = Cursor(foto=None)
    r = cliente.get("/pio/card8/resumo").json()
    assert r["disponivel"] is True and r["referencia"] is None and r["quantidade"] == 0
    p = cliente.get("/pio/card8/propostas").json()
    assert p["disponivel"] is True and p["itens"] == [] and p["total"] == 0


def test_tabela_ausente_e_indisponivel_nunca_zero(cliente, banco):
    banco["cur"] = Cursor(estoura=True)
    for rota in ("/pio/card8/resumo", "/pio/card8/propostas"):
        assert cliente.get(rota).json()["disponivel"] is False


def test_foto_de_dia_anterior_marca_desatualizado(cliente, banco, monkeypatch):
    monkeypatch.setattr("routers.pio_card1._hoje", lambda: date(2026, 11, 3))
    d = cliente.get("/pio/card8/resumo").json()
    assert d["desatualizado"] is True and d["dias_defasagem"] == 1


def test_colunas_da_lista_e_nomes_andam_juntos():
    assert len(_COLUNAS_LISTA) == len(_NOMES) == len(_linha())


def test_limite_maximo_e_validado(cliente, banco):
    assert cliente.get("/pio/card8/propostas?limite=201").status_code == 422
    assert cliente.get("/pio/card8/propostas?offset=-1").status_code == 422


def test_pio_py_nao_conhece_as_tabelas_novas_e_router_registrado():
    assert "ORQ_CARD08" not in (RAIZ / "api" / "routers" / "pio.py").read_text(encoding="utf-8")
    assert (RAIZ / "api" / "main.py").read_text(encoding="utf-8").count("pio_card8") == 2
