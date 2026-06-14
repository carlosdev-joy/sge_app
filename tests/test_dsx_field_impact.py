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


def _matched(r) -> list[dict]:
    return [c for job in r["jobs"] for oc in job["ocorrencias"] for c in oc["matched_columns"]]


def test_busca_like_eh_case_insensitive_e_substring(engine: DSXEngine):
    if not _has("seq_geral"):
        pytest.skip("seq_geral.dsx ausente")
    # 'cnpj' (minúsculo, parcial) deve casar colunas como 'codCpfCnpj'
    r = engine.buscar_campo("seq_geral", "cnpj")
    assert r.get("sucesso") is True
    assert r["total_jobs_impactados"] >= 1
    cols = _matched(r)
    # matched_columns agora são dicts com nome e datatype
    assert all(isinstance(c, dict) and "name" in c and "type_name" in c for c in cols)
    assert any("cnpj" in c["name"].lower() for c in cols)


def test_datatype_extraido_e_filtro_nao_texto(engine: DSXEngine):
    if not _has("seq_geral"):
        pytest.skip("seq_geral.dsx ausente")
    # codCpfCnpj é BIGINT no seq_geral → aparece no filtro "≠ texto" e some no "só texto".
    nao_texto = engine.buscar_campo("seq_geral", "cnpj", tipos=["VARCHAR", "CHAR"], excluir=True)
    so_texto = engine.buscar_campo("seq_geral", "cnpj", tipos=["VARCHAR", "CHAR"], excluir=False)
    tipos_nt = {c["type_name"] for c in _matched(nao_texto)}
    assert "BIGINT" in tipos_nt
    assert "VARCHAR" not in tipos_nt and "CHAR" not in tipos_nt
    # No filtro "só texto", nenhuma coluna pode ser não-texto
    for c in _matched(so_texto):
        assert c["type_name"] in ("VARCHAR", "CHAR")


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
                assert c["name"].lower() == "cnpj"


def test_ignora_pastas_de_backup_por_padrao(engine: DSXEngine):
    if not _has("BI_CVP"):
        pytest.skip("BI_CVP.dsx ausente")
    # BI_CVP tem 1 job em \\Jobs\\Projetos\\Coberturas\\bckp
    padrao = engine.buscar_campo("BI_CVP", "cobertura")                    # ignora bkp
    com_bkp = engine.buscar_campo("BI_CVP", "cobertura", incluir_bkp=True)  # inclui
    assert padrao["jobs_bkp_ignorados"] >= 1
    assert com_bkp["jobs_bkp_ignorados"] == 0
    assert padrao["total_jobs_impactados"] < com_bkp["total_jobs_impactados"]
    # nenhum job retornado por padrão pode estar em categoria de backup
    for job in padrao["jobs"]:
        assert "bkp" not in (job.get("category") or "").lower()


def test_is_backup_category():
    assert DSXEngine._is_backup_category("\\\\Jobs\\\\Projetos\\\\Coberturas\\\\bckp")
    assert DSXEngine._is_backup_category("\\\\Jobs\\\\BACKUP\\\\X")
    assert not DSXEngine._is_backup_category("\\\\Jobs\\\\Projetos\\\\Coberturas")


def test_ignora_jobs_copia_por_padrao(engine: DSXEngine):
    if not _has("BI_CVP"):
        pytest.skip("BI_CVP.dsx ausente")
    # BI_CVP tem o job CopyOfBiCVP_CoberturasUnificadas_001
    padrao = engine.buscar_campo("BI_CVP", "cobertura")                     # ignora bkp + copy
    com_copy = engine.buscar_campo("BI_CVP", "cobertura", incluir_copy=True)
    assert padrao["jobs_copy_ignorados"] >= 1
    assert com_copy["jobs_copy_ignorados"] == 0
    assert padrao["total_jobs_impactados"] < com_copy["total_jobs_impactados"]
    for job in padrao["jobs"]:
        assert "copyof" not in job["job_name"].lower()


def test_is_copy_job():
    assert DSXEngine._is_copy_job("CopyOfBiCVP_CoberturasUnificadas_001")
    assert DSXEngine._is_copy_job("Copy of Algo")
    assert not DSXEngine._is_copy_job("BiCVP_CoberturasUnificadas_001")


def test_busca_por_tabela(engine: DSXEngine):
    if not _has("BI_CVP"):
        pytest.skip("BI_CVP.dsx ausente")
    r = engine.buscar_campo("BI_CVP", "CONTRATO", alvo="tabela")
    assert r["alvo"] == "tabela"
    assert r["total_jobs_impactados"] >= 1
    objs = [o for job in r["jobs"] for oc in job["ocorrencias"] for o in oc["matched_objs"]]
    assert objs and all("contrato" in o.lower() for o in objs)
    # na busca por tabela não há colunas casadas
    assert all(not oc["matched_columns"] for job in r["jobs"] for oc in job["ocorrencias"])


def test_busca_por_arquivo(engine: DSXEngine):
    if not _has("BI_CVP"):
        pytest.skip("BI_CVP.dsx ausente")
    r = engine.buscar_campo("BI_CVP", "COBERTURA", alvo="arquivo")
    assert r["alvo"] == "arquivo"
    objs = [o for job in r["jobs"] for oc in job["ocorrencias"] for o in oc["matched_objs"]]
    assert any(o.upper().startswith("DS_") for o in objs)


def test_termo_vazio_retorna_erro(engine: DSXEngine):
    r = engine.buscar_campo("seq_geral", "   ")
    assert "erro" in r


def test_dsx_inexistente_retorna_erro(engine: DSXEngine):
    r = engine.buscar_campo("__nao_existe__", "cpf")
    assert "erro" in r
