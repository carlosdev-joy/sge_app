"""GET /pio/card7/{resumo,propostas,devolucao} — Card 7 (Devolução de Prêmio, VG + AP) lendo a FOTO.

RITM0118567. Prende o que distingue o Card 7:
  1. Número do card = AGG, soma dos 3 sub-cards (realizada/andamento/pendente), todos os status.
  2. Classificação em UM lugar (`_bucket`): mesmas regras na AGG e na FAT; desconhecido = pendente.
  3. Lista de UM sub-card: filtra data+lote+bucket; chave VG certificado / AP bilhete; sem banco.
  4. Dados bancários só em `/devolucao`, parametrizados por segmento + número + foto.
  5. Foto = `DTA_MOVIMENTO` + `LOTE_ID` do CTL `PUBLICADO`; sem GETDATE/MAX/DATEADD.
  6. Valor NULL ≠ zero; geografia só UF da agência; contato inexistente na foto.
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
from routers.pio_card7 import _COLUNAS_LISTA, _NOMES, _bucket  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
LOTE = "00000000-0000-4000-8000-0000000000a7"
FOTO = (date(2026, 11, 2), LOTE, datetime(2026, 11, 2, 7, 41, 30))
# (bucket, contratos, valor, valores informados, grupos) como o GROUP BY devolve
AGG = [("realizada", 4198, Decimal("913997.41"), 4198, 3000), ("andamento", 150, Decimal("30000.00"), 150, 100),
       ("pendente", 1675, Decimal("115629.79"), 39, 1512)]


def _linha(id_foto=1, seg="VG", cert=Decimal("1000000000001"), bilhete=None, cpf=Decimal("1234567890"),
           tipo="PF", valor=Decimal("250.50"), cod="1", des="Devolvido", ret="Crédito Efetivado",
           dia=date(2026, 10, 20)):
    """Uma linha na ordem de `_NOMES`."""
    return (id_foto, seg, cert, bilhete, "CLIENTE FICTICIO", cpf, tipo, 316, Decimal("12345"),
            date(2026, 10, 1), date(1980, 5, 10), "VIDA SIMULADA", "RJ", valor, cod, des, ret, dia,
            date(2026, 10, 15))


DETALHE = (Decimal("250.50"), "1", "Devolvido", "Crédito Efetivado", date(2026, 10, 20), date(2026, 10, 21), 1,
           104, 316, 13, Decimal("123456"), 7, "DEBITO", "VG", "1", "realizada")


class Cursor:
    def __init__(self, foto=FOTO, agg=AGG, total=6023, linhas=None, detalhe=DETALHE, estoura=False):
        self.foto, self.agg, self.total = foto, agg, total
        self.linhas, self.detalhe, self.estoura = linhas or [], detalhe, estoura
        self.sqls: list[str] = []
        self.params: list = []
        self._ult = ""

    def execute(self, sql, params=None):
        if self.estoura:
            raise Exception("Invalid object name 'dbo.CTL_ORQ_CARD07_LOTE'")
        self.sqls.append(sql)
        self.params.append(params)
        self._ult = sql
        return self

    def fetchone(self):
        s = self._ult
        if "CTL_ORQ_CARD07_LOTE" in s:
            return self.foto
        if "f.NUM_CONTA_DEBITO" in s:
            return self.detalhe
        if "COUNT_BIG(*) FROM dbo.FAT_ORQ_CARD07_FOTO" in s:
            return (self.total,)
        if "FROM dbo.AGG_ORQ_CARD07_FOTO" in s:
            return (sum(a[1] for a in self.agg),)
        return None

    def fetchall(self):
        if "GROUP BY" in self._ult and "AGG_ORQ_CARD07_FOTO" in self._ult:
            return self.agg
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

    monkeypatch.setattr("routers.pio_card7.get_db_conn", _fabrica)
    monkeypatch.setattr("routers.pio_card1._hoje", lambda: date(2026, 11, 2))
    return estado


def _sql(banco) -> str:
    return " ".join(banco["cur"].sqls)


def test_resumo_le_o_agregado_e_os_tres_subcards_somam_o_card(cliente, banco):
    d = cliente.get("/pio/card7/resumo").json()
    assert "AGG_ORQ_CARD07_FOTO" in _sql(banco) and "FAT_ORQ_CARD07_FOTO" not in _sql(banco)
    ps = d["por_situacao"]
    assert ps["realizada"] == {"quantidade": 4198, "valor": 913997.41, "valores_informados": 4198}
    assert ps["andamento"]["quantidade"] == 150 and ps["pendente"]["quantidade"] == 1675
    assert d["quantidade"] == 6023 == sum(b["quantidade"] for b in ps.values())
    assert d["premio_total"] == round(sum(b["valor"] for b in ps.values()), 2) == 1059627.20
    assert d["referencia"] == "2026-11-02" and d["disponivel"] and not d["desatualizado"]
    assert "SUM(VLR_DEVOLUCAO_TOTAL)" in _sql(banco) and "SUM(QTD_CONTRATOS)" in _sql(banco)


def test_valor_desconhecido_nao_e_zero(cliente, banco):
    banco["cur"] = Cursor(agg=[("pendente", 10, None, 0, 4)])
    d = cliente.get("/pio/card7/resumo").json()
    assert d["por_situacao"]["pendente"]["valor"] is None and d["premio_total"] is None
    assert d["por_situacao"]["realizada"] == {"quantidade": 0, "valor": None, "valores_informados": 0}
    banco["cur"] = Cursor(agg=[])
    d = cliente.get("/pio/card7/resumo").json()
    assert d["quantidade"] == 0 and d["premio_total"] == 0.0


@pytest.mark.parametrize("seg,cod,des,esperado", [
    ("VG", "1", "Devolvido", "realizada"), ("VG", "F", "Finalizado", "realizada"), ("AP", "2", "Devolvido / Creditado", "realizada"),
    ("VG", "3", "Enviado / Aguard. Retorno", "andamento"), ("VG", "7", "Reprogramado", "andamento"),
    ("VG", "8", "Processando", "andamento"), ("VG", "8", "Cancelado", "pendente"),
    ("VG", "0", "Pendente", "pendente"), ("VG", "2", "Retornado com Pendência", "pendente"),
    ("VG", None, "Sem Movimento", "pendente"), ("AP", None, "Sem Movimento", "pendente"),
    ("AP", "1", "x", "pendente"), ("AP", "3", "x", "pendente"), ("VG", "Z", "?", "pendente"),
])
def test_regra_dos_subcards_executa_o_case_de_verdade(seg, cod, des, esperado):
    """Executa o CASE gerado por `_bucket` num SQL de verdade (SQLite aceita esta sintaxe), em vez
    de reescrever a regra em Python. AGG e FAT usam a MESMA expressão, só muda o prefixo."""
    import sqlite3
    assert _bucket("f.").replace("f.", "") == _bucket()
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE f (SEGMENTO TEXT, COD_SIT_MOVIMENTO TEXT, DES_SIT_MOVIMENTO TEXT)")
    con.execute("INSERT INTO f VALUES (?, ?, ?)", (seg, cod, des))
    assert con.execute(f"SELECT {_bucket('f.')} FROM f").fetchone()[0] == esperado


def test_lista_de_um_subcard_filtra_foto_e_bucket_e_nao_traz_banco(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha(1), _linha(2, seg="AP", cert=None, bilhete=Decimal("77"), cod="2")])
    d = cliente.get("/pio/card7/propostas?situacao=realizada").json()
    sql = _sql(banco)
    assert "DTA_MOVIMENTO = ?" in sql and "LOTE_ID = ?" in sql and "ELSE 'pendente' END = ?" in sql
    assert banco["cur"].params[-1][2] == "realizada"                       # bucket por parâmetro
    assert d["total"] == 6023 and d["situacao"] == "realizada" and len(d["itens"]) == 2
    vg, ap = d["itens"]
    assert vg["proposta"] == "1000000000001" and vg["segmento"] == "VG"
    assert ap["proposta"] == "77" and ap["segmento"] == "AP"               # AP = bilhete
    assert vg["premio"] == 250.5 and vg["dias_pendente"] == 0 and vg["uf_agencia"] == "RJ" and vg["idade"] == 46
    assert vg["devolucao"]["status"] == "Devolvido" and vg["devolucao"]["data_movimento"] == "2026-10-20"
    for proibido in ("NUM_CONTA_DEBITO", "DIG_CONTA_DEBITO", "OPE_CONTA_DEBITO", "COD_BANCO", "COD_AGENCIA_MOV"):
        assert proibido not in sql, "dado bancário não pode sair na lista"
        assert proibido.lower() not in str(d).lower()


def test_situacao_invalida_ou_ausente_e_recusada(cliente, banco):
    assert cliente.get("/pio/card7/propostas").status_code == 422
    assert cliente.get("/pio/card7/propostas?situacao=todas").status_code == 422
    assert cliente.get("/pio/card7/propostas?situacao=pendente' OR 1=1--").status_code == 422


def test_ordenacao_fechada_na_chave_do_contrato(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card7/propostas?situacao=pendente")
    assert "ORDER BY f.DTH_VENDA ASC, f.SEGMENTO ASC, f.NUM_SIVPF ASC, f.NUM_BILHETE_TITULO ASC, f.ID_FOTO ASC" in _sql(banco)


def test_toda_leitura_filtra_data_e_lote_e_nao_usa_relogio(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card7/resumo")
    cliente.get("/pio/card7/propostas?situacao=andamento")
    cliente.get("/pio/card7/devolucao?segmento=VG&numero=1000000000001")
    for sql in banco["cur"].sqls:
        if "AGG_ORQ" in sql or "FROM dbo.FAT_ORQ" in sql:
            assert "DTA_MOVIMENTO = ?" in sql and "LOTE_ID = ?" in sql
    todo = _sql(banco)
    assert "MAX(DTA_MOVIMENTO)" not in todo and "GETDATE" not in todo and "DATEADD" not in todo
    assert "STATUS = 'PUBLICADO'" in todo


def test_nao_le_tabelas_dos_outros_cards(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card7/resumo")
    cliente.get("/pio/card7/propostas?situacao=realizada")
    for proibido in ("CARD01", "CARD02", "CARD03", "CARD04", "CARD05", "CARD06", "PIO_PROPOSTA_DEVOL_PREMIO_DET", "PIO_AGG"):
        assert proibido not in _sql(banco)


def test_devolucao_do_contrato_e_parametrizada_por_segmento_e_numero(cliente, banco):
    d = cliente.get("/pio/card7/devolucao?segmento=VG&numero=1000000000001").json()
    sql = [s for s in banco["cur"].sqls if "f.NUM_CONTA_DEBITO" in s][0]
    params = banco["cur"].params[banco["cur"].sqls.index(sql)]
    assert "f.NUM_SIVPF = ?" in sql and "f.SEGMENTO = ?" in sql and params[-2:] == ["VG", 1000000000001]
    dv = d["devolucao"]
    assert d["encontrado"] and dv["valor"] == 250.5 and dv["situacao"] == "realizada"
    assert (dv["banco"], dv["agencia"], dv["operacao"], dv["conta"], dv["digito_conta"]) == ("104", "316", "13", "123456", "7")
    assert dv["data_movimento"] == "2026-10-20" and dv["status"] == "Devolvido"
    # AP usa o bilhete
    cliente.get("/pio/card7/devolucao?segmento=AP&numero=77")
    assert "f.NUM_BILHETE_TITULO = ?" in " ".join(banco["cur"].sqls)


def test_devolucao_campos_ausentes_vem_nulos_e_contrato_fora_da_foto(cliente, banco):
    banco["cur"] = Cursor(detalhe=(None, None, None, None, None, None, None, None, None, None, None, None, None, "AP", None, "pendente"))
    dv = cliente.get("/pio/card7/devolucao?segmento=AP&numero=77").json()["devolucao"]
    assert dv["valor"] is None and dv["banco"] is None and dv["conta"] is None and dv["operacao"] is None
    assert dv["status"] == "Sem Movimento" and dv["situacao"] == "pendente"
    banco["cur"] = Cursor(detalhe=None)
    d = cliente.get("/pio/card7/devolucao?segmento=VG&numero=5").json()
    assert d["disponivel"] is True and d["encontrado"] is False and d["devolucao"] is None
    assert cliente.get("/pio/card7/devolucao?segmento=XX&numero=5").status_code == 422
    assert cliente.get("/pio/card7/devolucao?segmento=VG").status_code == 422


def test_sem_foto_publicada_e_disponivel_com_zero(cliente, banco):
    banco["cur"] = Cursor(foto=None)
    r = cliente.get("/pio/card7/resumo").json()
    assert r["disponivel"] is True and r["referencia"] is None and r["quantidade"] == 0
    p = cliente.get("/pio/card7/propostas?situacao=realizada").json()
    assert p["disponivel"] is True and p["itens"] == [] and p["total"] == 0


def test_tabela_ausente_e_indisponivel_nunca_zero(cliente, banco):
    banco["cur"] = Cursor(estoura=True)
    for rota in ("/pio/card7/resumo", "/pio/card7/propostas?situacao=realizada", "/pio/card7/devolucao?segmento=VG&numero=1"):
        assert cliente.get(rota).json()["disponivel"] is False


def test_detalhe_fora_da_retencao_nao_e_erro(cliente, banco):
    banco["cur"] = Cursor(total=0, linhas=[])
    assert cliente.get("/pio/card7/propostas?situacao=realizada").json()["detalhe_disponivel"] is False
    assert cliente.get("/pio/card7/propostas?situacao=realizada&busca=zzz").json()["detalhe_disponivel"] is True


def test_foto_de_dia_anterior_marca_desatualizado(cliente, banco, monkeypatch):
    monkeypatch.setattr("routers.pio_card1._hoje", lambda: date(2026, 11, 3))
    d = cliente.get("/pio/card7/resumo").json()
    assert d["desatualizado"] is True and d["dias_defasagem"] == 1


def test_colunas_da_lista_e_nomes_andam_juntos():
    assert len(_COLUNAS_LISTA) == len(_NOMES) == len(_linha())


def test_limite_maximo_e_validado(cliente, banco):
    assert cliente.get("/pio/card7/propostas?situacao=realizada&limite=201").status_code == 422
    assert cliente.get("/pio/card7/propostas?situacao=realizada&offset=-1").status_code == 422


def test_pio_py_nao_conhece_as_tabelas_novas_e_router_registrado():
    assert "ORQ_CARD07" not in (RAIZ / "api" / "routers" / "pio.py").read_text(encoding="utf-8")
    assert (RAIZ / "api" / "main.py").read_text(encoding="utf-8").count("pio_card7") == 2
