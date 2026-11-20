"""Contrato de leitura do PIO de 19/11/2026 (Cards 1–6) — o que mudou na API.

  1. **Endereço = AGÊNCIA.** Cards 1–3 deixam de ler `NOM_CIDADE`/`NOM_UF` (do segurado, que a
     extração não preenche mais) e passam a ler os cinco campos da agência. Nenhum SQL faz
     COALESCE entre os dois conceitos; `cidade`/`uf` saem vazios.
  2. **`CEP_AGENCIA` é `int`**: volta a oito posições na apresentação; ausência não vira CEP.
  3. **Foto antiga** (campos novos `NULL`) não quebra: campos vazios.
  4. **Card 4**: `DES_COD_SIT_CONTRATO` exposto como veio; nenhuma situação é filtrada no SQL.
  5. Cards 4–6 expõem nome/endereço/CEP da agência; as colunas e os nomes andam juntos.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app  # noqa: E402,F401

from routers import pio_card1, pio_card4, pio_card5, pio_card6  # noqa: E402
from tests import test_pio_card1_api as t1  # noqa: E402
from tests import test_pio_card4_api as t4  # noqa: E402

AGENCIA = ("NOM_AGENCIA", "DES_ENDERECO_AGENCIA", "NOM_CIDADE_AGENCIA", "SIG_UF_AGENCIA", "CEP_AGENCIA")


@pytest.mark.parametrize("valor,esperado", [
    (1310100, "01310-100"), (20040002, "20040-002"), ("01310100", "01310-100"),
    (None, ""), (0, ""), ("", ""), ("   ", ""), (123456789, ""),
])
def test_cep_int_volta_a_oito_posicoes_e_ausencia_nao_vira_cep(valor, esperado):
    assert pio_card1._cep(valor) == esperado


def test_cards_1_a_3_leem_a_agencia_e_nao_o_endereco_da_pessoa():
    for c in AGENCIA:
        assert c in pio_card1._COLUNAS_ITEM
    for c in ("NOM_CIDADE", "NOM_UF", "NOM_LOGRADOURO", "NOM_BAIRRO", "NUM_CEP"):
        assert c not in pio_card1._COLUNAS_ITEM
    for n in (1, 2, 3):
        fonte = (t1.RAIZ / "api" / "routers" / f"pio_card{n}.py").read_text(encoding="utf-8")
        codigo = "\n".join(l for l in fonte.splitlines() if not l.strip().startswith("#"))
        assert "COALESCE(f.NOM" not in codigo and "ISNULL(" not in codigo
        assert "NOLOCK" not in codigo.upper().replace("NÃO USAR NOLOCK", "")


def test_item_dos_cards_1_a_3_traz_agencia_e_deixa_cidade_uf_da_pessoa_vazios():
    assert len(t1._linha()) == len(pio_card1._COLUNAS_ITEM)
    i = pio_card1._item(t1._linha())
    assert i["cidade"] == "" and i["uf"] == ""
    assert i["nome_agencia"] == "AG TESTE"          # char(40) vem com espaços à direita
    assert i["endereco_agencia"] == "AV TESTE 100"
    assert i["cidade_agencia"] == "CIDADE AGENCIA" and i["uf_agencia"] == "SP"
    assert i["cep_agencia"] == "01310-100"


def test_foto_antiga_com_campos_novos_null_nao_quebra():
    linha = list(t1._linha())
    for c in AGENCIA:
        linha[pio_card1._COLUNAS_ITEM.index(c)] = None
    i = pio_card1._item(tuple(linha))
    assert [i[k] for k in ("nome_agencia", "endereco_agencia", "cidade_agencia", "uf_agencia", "cep_agencia")] == [""] * 5


def test_area_produto_de_20_caracteres_nao_e_cortada():
    linha = list(t1._linha())
    linha[pio_card1._COLUNAS_ITEM.index("AREA_PRODUTO")] = "PREVIDENCIA PRIVADA."
    assert pio_card1._item(tuple(linha))["area_produto"] == "PREVIDENCIA PRIVADA."


@pytest.mark.parametrize("cod,sub", [("0", "Pendente"), ("1", "Em Crítica"), ("9", "Recusada"), ("e", "Erro de Carga")])
def test_card4_expoe_codigo_e_descricao_como_vieram(cod, sub):
    assert len(t4._linha()) == len(pio_card4._COLUNAS_LISTA) == len(pio_card4._NOMES)
    i = pio_card4._item(t4._linha(cod=cod, sub=sub), t4.FOTO[0])
    assert i["sub_situacao"] == sub and i["cod_situacao"] == cod.upper()
    assert i["nome_agencia"] == "AG CENTRO" and i["cep_agencia"] == "20040-002"


def test_card4_nao_restringe_situacao_no_sql():
    fonte = (t1.RAIZ / "api" / "routers" / "pio_card4.py").read_text(encoding="utf-8")
    assert "DES_COD_SIT_CONTRATO IN" not in fonte and "DES_COD_SIT_CONTRATO =" not in fonte
    assert "NOM_SUB_SITUACAO IN" not in fonte and "NOM_SUB_SITUACAO =" not in fonte


@pytest.mark.parametrize("modulo", [pio_card4, pio_card5, pio_card6])
def test_cards_4_a_6_leem_nome_endereco_e_cep_da_agencia(modulo):
    assert len(modulo._COLUNAS_LISTA) == len(modulo._NOMES)
    for c in AGENCIA:
        assert c in modulo._NOMES
        assert any(c in col for col in modulo._COLUNAS_LISTA)
