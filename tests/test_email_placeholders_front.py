"""Catálogo do seletor e inserção real na bancada local, sem envio de e-mail."""
import ast
import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def seletor():
    node = shutil.which("node")
    if not node or not (RAIZ / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("front não instalado nesta máquina")
    resultado = subprocess.run(
        [node, str(RAIZ / "tests/js/email_placeholders_harness.cjs")],
        capture_output=True, text=True, cwd=RAIZ, timeout=60,
    )
    assert resultado.returncode == 0, resultado.stderr
    return json.loads(resultado.stdout)


def test_seletor_insere_na_selecao_e_restaura_cursor_e_foco(seletor):
    assert seletor["ok"]


def test_catalogo_corresponde_ao_mapa_do_operador(seletor):
    # Lê a árvore do runtime sem importar Airflow ou fazer conexões.
    arvore = ast.parse((RAIZ / "dags/utils/email_operator.py").read_text())
    mapa = next(no for no in ast.walk(arvore) if isinstance(no, ast.FunctionDef) and no.name == "_mapa")
    retorno = next(no for no in mapa.body if isinstance(no, ast.Return))
    assert isinstance(retorno.value, ast.Dict)
    chaves = {ast.literal_eval(chave) for chave in retorno.value.keys}
    assert set(seletor["catalogoAnexo"]) == chaves - {"data", "inicio"}
    assert set(seletor["catalogoCorpo"]) == chaves | {"tabela"}


@pytest.mark.parametrize("marcador,valor,esperado", [
    ("odate", "20260911", "/dados/saida/rel_20260911.csv"),
    ("data", "11/09/2026 14:30", None),
    ("inicio", "11/09/2026 14:02", None),
])
def test_data_no_anexo_precisa_resolver_para_nome_valido(marcador, valor, esperado):
    import importlib.util

    spec = importlib.util.spec_from_file_location("email_envio_picker_contract", RAIZ / "dags/utils/email_envio.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    nome = worker.interpolar(f"rel_{{{marcador}}}.csv", {marcador: valor})
    assert worker.caminho_do_anexo("/dados/saida", nome, ["/dados/saida"]) == esperado
