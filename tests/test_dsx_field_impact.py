"""
Testes da busca de impacto por campo (DSXEngine.buscar_campo / listar_jobs).

Varre os arquivos .dsx versionados na raiz do repositório. Pula automaticamente
se os arquivos não estiverem presentes — não depende de Airflow nem de banco.

Roda como:
    pytest tests/test_dsx_field_impact.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DAGS = ROOT / "dags"
if str(DAGS) not in sys.path:
    sys.path.insert(0, str(DAGS))

from utils.dsx_engine import DSXEngine  # noqa: E402


@pytest.fixture(scope="module")
def engine() -> DSXEngine:
    return DSXEngine(diretorio_base=str(ROOT))


def _has(project: str) -> bool:
    return (ROOT / f"{project}.dsx").exists()


def test_listar_dsx_inclui_arquivos_do_repo(engine: DSXEngine):
    disponiveis = engine.listar_dsx()
    assert isinstance(disponiveis, list)
    for proj in ("BI_CVP", "seq_geral"):
        if _has(proj):
            assert proj in disponiveis


def test_listar_jobs_retorna_lista(engine: DSXEngine):
    if not _has("BI_CVP"):
        pytest.skip("BI_CVP.dsx ausente")
    r = engine.listar_jobs("BI_CVP")
    assert r.get("sucesso") is True
    assert isinstance(r["jobs"], list) and len(r["jobs"]) > 0


def test_busca_like_eh_case_insensitive_e_substring(engine: DSXEngine):
    if not _has("seq_geral"):
        pytest.skip("seq_geral.dsx ausente")
    # 'cnpj' (minúsculo, parcial) deve casar colunas como 'codCpfCnpj'
    r = engine.buscar_campo("seq_geral", "cnpj")
    assert r.get("sucesso") is True
    assert r["total_jobs_impactados"] >= 1
    matched = [
        c
        for job in r["jobs"]
        for oc in job["ocorrencias"]
        for c in oc["matched_columns"]
    ]
    assert any("cnpj" in c.lower() for c in matched)


def test_busca_exata_nao_casa_substring(engine: DSXEngine):
    if not _has("seq_geral"):
        pytest.skip("seq_geral.dsx ausente")
    # Com exato=True, o termo parcial 'cnpj' não pode casar 'codCpfCnpj'.
    like = engine.buscar_campo("seq_geral", "cnpj", exato=False)
    exato = engine.buscar_campo("seq_geral", "cnpj", exato=True)
    assert exato["total_ocorrencias"] <= like["total_ocorrencias"]
    for job in exato["jobs"]:
        for oc in job["ocorrencias"]:
            for c in oc["matched_columns"]:
                assert c.lower() == "cnpj"


def test_termo_vazio_retorna_erro(engine: DSXEngine):
    r = engine.buscar_campo("seq_geral", "   ")
    assert "erro" in r


def test_dsx_inexistente_retorna_erro(engine: DSXEngine):
    r = engine.buscar_campo("__nao_existe__", "cpf")
    assert "erro" in r
