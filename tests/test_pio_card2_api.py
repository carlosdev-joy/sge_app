"""GET /pio/card2/resumo e /propostas — o Card 2 lendo a FOTO diária.

O que estes testes prendem (Card 2 (Pendentes de Pagamento)):

  1. **O número do card sai do AGREGADO e a lista, da FATO** — o resumo nunca
     encosta na FAT (varrer o detalhe a cada requisição era o que se queria evitar)
     e a lista nunca lê o AGG nem a DET legada `PIO_PROPOSTA_PEND_PGTO_DET`.
  2. **Uma foto = DTA_MOVIMENTO + LOTE_ID**, resolvidos pelo CTL `PUBLICADO`. Nenhum
     SQL soma datas, usa `MAX(DTA_MOVIMENTO)` em AGG/FAT, `GETDATE()` ou D-30.
  3. **Quantidade = SUM(QTD_REGISTROS)**; prêmio somado em `Decimal` (centavos).
  4. **Contato**: NULL, vazio, espaços e `0` são ausência; telefone `int` não quebra.
  5. **Detalhe indisponível ≠ erro** (retenção: fato 24 meses, agregado 36).
  6. **Os outros sete cards não mudam**: `pio.py` segue sem referência às tabelas
     novas e os testes de `test_pio_api.py` passam sem alteração.

Nada toca banco: cursor dublê e `get_db_conn` substituído.
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
from routers import pio_card1, pio_card2  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
LOTE = "00000000-0000-4000-8000-0000000000a1"
FOTO = (date(2026, 10, 27), LOTE, datetime(2026, 10, 27, 7, 41, 30))


def _linha(id_foto=1, proposta="SIM01", premio=Decimal("100.25"), ddd_cel=11,
           cel=912345678, ddd_res=None, res=None, email="validacao@example.com",
           venda=date(2026, 10, 20), nasc=date(1980, 5, 10), assinatura="CO"):
    """Uma linha na ordem de `_COLUNAS_ITEM`."""
    return (id_foto, proposta, 9000000 + id_foto, "CLIENTE FICTICIO", None, "0001",
            "M000001", venda, nasc, "Vida Simulado", "Vida", premio,
            Decimal("50000.00"), Decimal("4000"), "Cidade Teste", "SP",
            "AT", assinatura, "N", ddd_res, res, ddd_cel, cel, email, 7)


class Cursor:
    """Responde por TABELA consultada e registra o SQL — é assim que o teste
    prova qual tabela cada endpoint lê."""

    def __init__(self, foto=FOTO, agg=(3, Decimal("600.00"), 2), fat_total=3,
                 linhas=None, estoura=False):
        self.foto, self.agg, self.fat_total = foto, agg, fat_total
        self.linhas = linhas if linhas is not None else []
        self.estoura = estoura
        self.sqls: list[str] = []
        self.params: list = []
        self._ult = ""

    def execute(self, sql, params=None):
        if self.estoura:
            raise Exception("Invalid object name 'dbo.CTL_ORQ_CARD02_LOTE'")
        self.sqls.append(sql)
        self.params.append(params)
        self._ult = sql
        return self

    def fetchone(self):
        s = self._ult
        if "CTL_ORQ_CARD02_LOTE" in s:
            return self.foto
        if "FROM dbo.AGG_ORQ_CARD02_FOTO" in s:
            return self.agg
        if "COUNT_BIG(*) FROM dbo.FAT_ORQ_CARD02_FOTO" in s:
            return (self.fat_total,)
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

    monkeypatch.setattr("routers.pio_card2.get_db_conn", _fabrica)
    monkeypatch.setattr("routers.pio_card1._hoje", lambda: date(2026, 10, 27))
    return estado


# ═══════════ 1. qual tabela cada endpoint lê ════════════════════════════════

def test_resumo_le_o_agregado_e_nao_varre_a_fato(cliente, banco):
    d = cliente.get("/pio/card2/resumo").json()
    sql = " ".join(banco["cur"].sqls)
    assert "AGG_ORQ_CARD02_FOTO" in sql
    assert "FAT_ORQ_CARD02_FOTO" not in sql
    assert "PIO_AGG" not in sql and "PIO_PROPOSTA_PEND_PGTO_DET" not in sql
    assert d["premio_total"] == 600.0 and d["quantidade"] == 3 and d["grupos"] == 2


def test_lista_le_a_fato_e_nunca_a_det_legada(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha(1), _linha(2)], fat_total=3)
    cliente.get("/pio/card2/propostas")
    sql = " ".join(banco["cur"].sqls)
    assert "FAT_ORQ_CARD02_FOTO" in sql
    assert "PIO_PROPOSTA_PEND_PGTO_DET" not in sql and "PIO_AGG" not in sql


# ═══════════ 2. a foto: data + lote, sem relógio ════════════════════════════

def test_toda_leitura_filtra_data_e_lote(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card2/resumo")
    cliente.get("/pio/card2/propostas")
    for sql, params in zip(banco["cur"].sqls, banco["cur"].params):
        if "AGG_ORQ" in sql or "FROM dbo.FAT_ORQ" in sql:
            assert "DTA_MOVIMENTO = ?" in sql and "LOTE_ID = ?" in sql
            assert params[0] == FOTO[0] and params[1] == LOTE


def test_foto_vem_do_ctl_publicado_sem_max_nem_relogio(cliente, banco):
    cliente.get("/pio/card2/resumo")
    cliente.get("/pio/card2/propostas")
    todo = " ".join(banco["cur"].sqls).upper()
    assert "STATUS = 'PUBLICADO'" in todo
    assert "MAX(" not in todo and "GETDATE" not in todo and "DATEADD" not in todo


def test_data_pedida_vai_por_parametro(cliente, banco):
    cliente.get("/pio/card2/resumo?data=2026-10-26")
    ctl = next(i for i, s in enumerate(banco["cur"].sqls) if "CTL_ORQ" in s)
    assert banco["cur"].params[ctl] == [date(2026, 10, 26)]
    assert cliente.get("/pio/card2/resumo?data=26/10").status_code == 422


def test_dias_pendente_medidos_na_data_da_foto(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card2/propostas")
    lista = next(s for s in banco["cur"].sqls if "OFFSET" in s)
    assert "DATEDIFF(day, f.DTH_VENDA, f.DTA_MOVIMENTO)" in lista


def test_foto_antiga_e_sinalizada_como_desatualizada(cliente, banco):
    banco["cur"] = Cursor(foto=(date(2026, 10, 25), LOTE, datetime(2026, 10, 25, 7, 40)))
    d = cliente.get("/pio/card2/resumo").json()
    assert d["desatualizado"] is True and d["dias_defasagem"] == 2
    assert d["referencia"] == "2026-10-25"


def test_foto_de_hoje_nao_e_desatualizada(cliente, banco):
    assert cliente.get("/pio/card2/resumo").json()["desatualizado"] is False


# ═══════════ 3. conciliação: quantidade, prêmio, centavos ═══════════════════

def test_quantidade_do_card_e_o_total_da_lista(cliente, banco):
    resumo = cliente.get("/pio/card2/resumo").json()
    lista = cliente.get("/pio/card2/propostas").json()
    assert resumo["quantidade"] == lista["total"] == 3
    assert resumo["referencia"] == lista["referencia"]
    assert resumo["lote_id"] == lista["lote_id"] == LOTE


def test_premio_soma_em_decimal_sem_erro_de_centavo(cliente, banco):
    # 0.1 + 0.2 em float dá 0.30000000000000004; o agregado chega em Decimal.
    banco["cur"] = Cursor(agg=(2, Decimal("0.30"), 1))
    assert cliente.get("/pio/card2/resumo").json()["premio_total"] == 0.3


def test_foto_sem_pendencia_e_zero_de_verdade_nao_indisponivel(cliente, banco):
    banco["cur"] = Cursor(agg=(0, None, 0))
    d = cliente.get("/pio/card2/resumo").json()
    assert d["disponivel"] is True and d["quantidade"] == 0 and d["premio_total"] == 0.0


def test_sem_foto_publicada_nao_inventa_numero(cliente, banco):
    banco["cur"] = Cursor(foto=None)
    d = cliente.get("/pio/card2/resumo").json()
    assert d["disponivel"] is True and d["referencia"] is None
    assert d["premio_total"] is None and d["quantidade"] == 0


def test_tabela_ausente_vira_indisponivel_nao_500(cliente, banco):
    banco["cur"] = Cursor(estoura=True)
    for rota in ("/pio/card2/resumo", "/pio/card2/propostas"):
        r = cliente.get(rota)
        assert r.status_code == 200 and r.json()["disponivel"] is False


# ═══════════ 4. contatos ═════════════════════════════════════════════════════

def test_telefone_int_nao_quebra_e_formata():
    assert pio_card1._telefone(11, 912345678) == "(11) 91234-5678"
    assert pio_card1._telefone(41, 33221100) == "(41) 3322-1100"
    assert pio_card1._telefone(None, 33221100) == "3322-1100"


@pytest.mark.parametrize("ddd,num", [(None, None), (0, 0), (11, 0), (11, None), ("", "  ")])
def test_telefone_ausente(ddd, num):
    assert pio_card1._telefone(ddd, num) is None


@pytest.mark.parametrize("valor", [None, "", "   "])
def test_texto_vazio_e_ausencia_nunca_a_palavra_none(valor):
    assert pio_card1._texto(valor) is None


def test_contatos_ausentes_chegam_null_e_nao_texto(cliente, banco):
    banco["cur"] = Cursor(linhas=[
        _linha(1),
        _linha(2, ddd_cel=None, cel=None, email=None),
        _linha(3, ddd_cel=0, cel=0, ddd_res=0, res=0, email="   "),
    ])
    itens = cliente.get("/pio/card2/propostas").json()["itens"]
    assert itens[0]["contato"] == {"email": "validacao@example.com",
                                   "celular": "(11) 91234-5678", "residencial": None}
    for item in itens[1:]:
        assert item["contato"] == {"email": None, "celular": None, "residencial": None}
    assert "None" not in str(itens[1]["contato"]).replace("None,", "").replace("None}", "")


# ═══════════ 5. lista: ordem, duplicata, retenção, idade ════════════════════

def test_ordenacao_termina_em_id_foto_e_duplicata_mantem_linhas(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha(5, "SIM01"), _linha(6, "SIM01")], fat_total=2)
    d = cliente.get("/pio/card2/propostas").json()
    lista = next(s for s in banco["cur"].sqls if "OFFSET" in s)
    assert "ORDER BY f.DTH_VENDA ASC, f.COD_PROPOSTA ASC, f.ID_FOTO ASC" in lista
    assert [i["id_foto"] for i in d["itens"]] == [5, 6]       # chave única p/ o React
    assert d["total"] == 2


def test_detalhe_antigo_indisponivel_e_explicado_nao_erro(cliente, banco):
    banco["cur"] = Cursor(fat_total=0, agg=(1098, Decimal("680155.27"), 475), linhas=[])
    d = cliente.get("/pio/card2/propostas").json()
    assert d["disponivel"] is True and d["detalhe_disponivel"] is False
    assert d["itens"] == []


def test_busca_sem_resultado_nao_vira_detalhe_indisponivel(cliente, banco):
    banco["cur"] = Cursor(fat_total=0, agg=(3, Decimal("600.00"), 2), linhas=[])
    d = cliente.get("/pio/card2/propostas?busca=xyz&modo=proposta").json()
    assert d["detalhe_disponivel"] is True and d["total"] == 0


def test_busca_entra_por_parametro_nunca_concatenada(cliente, banco):
    banco["cur"] = Cursor(linhas=[])
    cliente.get("/pio/card2/propostas?busca=1'; DROP TABLE x;--&modo=proposta")
    todo = " ".join(banco["cur"].sqls)
    assert "DROP" not in todo
    assert any("%DROPTABLEx%" in str(p) or "%1%" in str(p) for p in banco["cur"].params if p)


def test_idade_e_a_da_data_da_foto():
    assert pio_card1._idade(date(1980, 10, 28), date(2026, 10, 27)) == 45   # ainda não fez
    assert pio_card1._idade(date(1980, 10, 27), date(2026, 10, 27)) == 46
    assert pio_card1._idade(None, date(2026, 10, 27)) is None


def test_item_traz_status_da_foto_sem_inventar_historico(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    item = cliente.get("/pio/card2/propostas").json()["itens"][0]
    assert (item["situacao"], item["assinatura"], item["pago"]) == ("AT", "CO", "N")
    assert "historico" not in item and "eventos" not in item


# ═══════════ 6. permissão e isolamento dos outros cards ═════════════════════

def test_sem_permissao_403(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "U2", "perfil": "visitante", "permissoes": []}
    try:
        c = TestClient(app)
        assert c.get("/pio/card2/resumo").status_code == 403
        assert c.get("/pio/card2/propostas").status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_router_legado_e_card1_nao_conhecem_as_tabelas_do_card2():
    for nome in ("pio.py", "pio_card1.py"):
        fonte = (RAIZ / "api" / "routers" / nome).read_text(encoding="utf-8")
        assert "ORQ_CARD02" not in fonte


def test_card2_nao_le_as_tabelas_do_card1():
    fonte = (RAIZ / "api" / "routers" / "pio_card2.py").read_text(encoding="utf-8")
    assert "ORQ_CARD01" not in fonte


def test_lote_nao_publicado_nunca_e_consultado_como_foto(cliente, banco):
    cliente.get("/pio/card2/resumo")
    ctl = next(s for s in banco["cur"].sqls if "CTL_ORQ_CARD02_LOTE" in s)
    assert "STATUS = 'PUBLICADO'" in ctl


def test_filtro_da_carga_nao_e_reaplicado_na_leitura(cliente, banco):
    banco["cur"] = Cursor(linhas=[_linha()])
    cliente.get("/pio/card2/resumo")
    cliente.get("/pio/card2/propostas")
    todo = " ".join(banco["cur"].sqls)
    for proibido in ("STA_ASSINATURA =", "STA_ASSINATURA IN", "STA_PAGO =", "NOT IN", "GETDATE", "DATEADD"):
        assert proibido not in todo


def test_router_novo_usa_placeholder_interrogacao():
    fonte = (RAIZ / "api" / "routers" / "pio_card2.py").read_text(encoding="utf-8")
    # o `%s` do logging é de `log.warning`, não de SQL
    sem_log = [l for l in fonte.splitlines() if "log.warning" not in l]
    assert "%s" not in "\n".join(sem_log)
