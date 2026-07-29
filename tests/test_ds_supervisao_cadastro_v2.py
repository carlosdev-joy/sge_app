"""
Ajustes do cadastro da supervisão (migration 063):
descrição obrigatória e mensagem por tipo de alerta.

Por que a descrição virou obrigatória: é o rótulo que dá contexto ao alerta no
painel e no card do Teams. Vazia, o aviso chega dizendo só o nome técnico do job.

Por que a variável desconhecida é recusada no salvamento: escrever
'{tolerancia_min}' achando que existe só se descobre quando o card chega ao
canal com o texto cru — tarde demais.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
from api.main import app as _app  # noqa: F401,E402

from routers.ds_supervisao import (  # noqa: E402
    TIPOS_MENSAGEM, _descricao_obrigatoria, _salvar_mensagens, _validar_mensagens,
)


# ── Descrição obrigatória ───────────────────────────────────────────────────

@pytest.mark.parametrize("valor", [None, "", "   ", "\t\n"])
def test_descricao_vazia_e_recusada(valor):
    with pytest.raises(HTTPException) as exc:
        _descricao_obrigatoria(valor)
    assert exc.value.status_code == 422
    assert "descrição" in exc.value.detail.lower()


def test_descricao_valida_e_normalizada():
    assert _descricao_obrigatoria("  Carga diária de vida  ") == "Carga diária de vida"


def test_descricao_muito_longa_e_truncada_no_limite_da_coluna():
    assert len(_descricao_obrigatoria("x" * 900)) == 400


# ── Mensagens por tipo ──────────────────────────────────────────────────────

def test_mensagens_ausentes_viram_dicionario_vazio():
    assert _validar_mensagens(None) == {}


def test_mensagens_precisa_ser_objeto():
    with pytest.raises(HTTPException) as exc:
        _validar_mensagens(["texto"])
    assert exc.value.status_code == 422


def test_tipo_desconhecido_e_recusado():
    with pytest.raises(HTTPException) as exc:
        _validar_mensagens({"QUALQUER": "texto"})
    assert exc.value.status_code == 422
    assert "QUALQUER" in exc.value.detail


def test_todos_os_tipos_previstos_sao_aceitos():
    entrada = {tipo: "Aviso de {job} em {data}" for tipo in TIPOS_MENSAGEM}
    assert set(_validar_mensagens(entrada)) == set(TIPOS_MENSAGEM)


def test_mensagem_com_variavel_valida_passa():
    limpo = _validar_mensagens({"ATRASO": "{job} não iniciou até {limite} ({tolerancia} min)"})
    assert limpo["ATRASO"].startswith("{job} não iniciou")


def test_variavel_inexistente_e_recusada_com_o_nome_no_erro():
    with pytest.raises(HTTPException) as exc:
        _validar_mensagens({"ATRASO": "{job} atrasou {tolerancia_min}"})
    assert exc.value.status_code == 422
    assert "{tolerancia_min}" in exc.value.detail


def test_texto_vazio_marca_volta_ao_padrao():
    # String vazia não é "sem mudança": é o pedido explícito de voltar ao padrão.
    assert _validar_mensagens({"ATRASO": "   "}) == {"ATRASO": ""}


def test_mensagem_gigante_e_truncada_no_limite_da_coluna():
    limpo = _validar_mensagens({"ABORTOU": "y" * 5000})
    assert len(limpo["ABORTOU"]) == 2000


# ── Persistência ────────────────────────────────────────────────────────────

class CursorFalso:
    def __init__(self, rowcount=1):
        self.sqls: list[tuple[str, tuple]] = []
        self.rowcount = rowcount

    def execute(self, sql, params=()):
        self.sqls.append((" ".join(sql.split()), tuple(params)))


def test_texto_vazio_apaga_a_linha_em_vez_de_gravar_vazio():
    cur = CursorFalso()
    _salvar_mensagens(cur, 7, {"ATRASO": ""})
    sql, params = cur.sqls[0]
    assert sql.startswith("DELETE FROM dbo.etl_ds_supervisao_mensagem")
    assert params == (7, "ATRASO")


def test_mensagem_existente_e_atualizada_sem_duplicar():
    cur = CursorFalso(rowcount=1)          # UPDATE encontrou a linha
    _salvar_mensagens(cur, 7, {"ATRASO": "novo texto"})
    assert len(cur.sqls) == 1
    assert cur.sqls[0][0].startswith("UPDATE dbo.etl_ds_supervisao_mensagem")


def test_mensagem_nova_cai_no_insert_depois_do_update_vazio():
    cur = CursorFalso(rowcount=0)          # UPDATE não achou nada
    _salvar_mensagens(cur, 7, {"ATRASO": "texto"})
    assert len(cur.sqls) == 2
    assert "INSERT INTO dbo.etl_ds_supervisao_mensagem" in cur.sqls[1][0]


def test_api_usa_placeholder_do_pyodbc_e_nao_o_do_pymssql():
    """O dialeto da API é o OPOSTO do da DAG — e isso é correto.

    A API fala com o banco por **pyodbc** (`?`); a DAG, pelo MsSqlHook do
    Airflow, que usa **pymssql** (`%s`). Trocar aqui por simetria com a DAG
    quebraria a API. Este teste existe para que a correção de um lado não
    "conserte" o outro por engano.
    """
    import inspect
    import re

    from routers import ds_supervisao

    fonte = inspect.getsource(ds_supervisao)
    # Placeholder do pymssql em contexto de SQL não deve aparecer aqui.
    suspeitas = [
        linha.strip() for linha in fonte.split("\n")
        if '"' in linha
        and re.search(r"\b(WHERE|VALUES|SET|AND)\b", linha)
        and re.search(r"=\s*%s|VALUES\s*\(%s|,\s*%s", linha)
    ]
    assert not suspeitas, (
        "Router usando '%s' (pymssql). A API é pyodbc → use '?':\n" + "\n".join(suspeitas))


def test_template_id_saiu_do_contrato():
    # A mensagem por tipo substituiu o template único do catálogo (migration 063).
    import inspect

    from routers import ds_supervisao

    fonte = inspect.getsource(ds_supervisao)
    assert "template_id" not in fonte
