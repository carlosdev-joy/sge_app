"""Port das melhorias feitas em produção em 22/09/2026 (branch
`feat/agente-datastage-melhorias`, commit d3696c1) sobre o código das F4–F6.

A branch não é mergeada (partiu de base antiga e traria a F3 de volta); cada
melhoria entra aqui e fica presa por teste, porque o próximo deploy SOBRESCREVE
o `agentes.py` de produção — sem o port, elas sumiriam de lá.

  1. `isx_engine._API_CAMINHO_RE` aceita `+` (espaço codificado pela API REST).
  2. `_limpar_children`: o modelo recebe só o `job_name` dos filhos e não recebe
     os `CJobActivity` — sem mexer no resultado que alimenta fatos/lineage.
  3. `_resolver_matriculas`: nome de quem criou/alterou; caixa ignorada, nome em
     branco não vira "None", e a falha da consulta não derruba a extração.
  4. O prompt reescrito, mesclado com F5/F6.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

if "pyodbc" not in sys.modules:
    sys.modules["pyodbc"] = MagicMock()
os.environ.setdefault("MSSQL_CONN_STR", "__mock__")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

from services import agentes as svc  # noqa: E402
from services import agentes_ferramentas as af  # noqa: E402
from services import ia_provedor  # noqa: E402
from utils import isx_engine  # noqa: E402


# ═══════════ 1. regex de caminho da API REST ══════════════════════════════

@pytest.mark.parametrize("caminho", ["folders/04.+ODS/contents", "folders/00.+ControleCarga",
                                     "jobdesigns/Jobs%2F04.+ODS%2FJobX"])
def test_caminho_com_espaco_codificado_como_mais_e_aceito(caminho):
    assert isx_engine._caminho_api_valido(caminho) == caminho


@pytest.mark.parametrize("caminho", ["https://outro/folders/x", "folders/a/b/c", "outro/x", "folders/a:b",
                                     "folders/..", "folders/..+x/contents"])
def test_caminho_fora_do_escopo_continua_recusado(caminho):
    assert isx_engine._caminho_api_valido(caminho) is None


# ═══════════ 2. _limpar_children ══════════════════════════════════════════

def test_limpar_children_tira_activity_e_cjobactivity():
    payload = {
        "children": [{"job_name": "SsdPrs_Ods_00_ext", "activity": "Ods_00_ext"}, {"activity": "sem_job"}, "x"],
        "stages": [{"stage_name": "Ods_00_ext", "stage_type_raw": "CJobActivity"},
                   {"stage_name": "Junta", "stage_type_raw": "CSequencer"}],
    }
    svc._limpar_children(payload)
    assert payload["children"] == [{"job_name": "SsdPrs_Ods_00_ext"}]
    assert [s["stage_name"] for s in payload["stages"]] == ["Junta"]


def test_limpar_children_nao_mexe_no_resultado_original():
    resultado = {"children": [{"job_name": "J", "activity": "A"}],
                 "stages": [{"stage_type_raw": "CJobActivity"}]}
    payload = dict(resultado)
    svc._limpar_children(payload)
    assert resultado["children"][0]["activity"] == "A" and len(resultado["stages"]) == 1


def test_limpar_children_tolera_payload_sem_os_campos():
    payload = {"stages": None}
    svc._limpar_children(payload)
    assert payload == {"stages": None}


# ═══════════ 3. _resolver_matriculas ══════════════════════════════════════

class _CurNomes:
    def __init__(self, nomes):
        self.nomes = nomes
        self.params = None

    def execute(self, sql, params):
        self.params = list(params)
        self._rows = [(m, self.nomes[m]) for m in params if m in self.nomes]

    def fetchall(self):
        return self._rows


def test_resolve_nome_ignorando_a_caixa():
    payload = {"created_by": "cvp12345", "modified_by": "CVP999"}
    cur = _CurNomes({"CVP12345": "Maria Souza"})
    svc._resolver_matriculas(cur, payload)
    assert payload == {"created_by": "Maria Souza (cvp12345)", "modified_by": "CVP999"}
    assert cur.params == ["CVP12345", "CVP999"]


def test_nome_em_branco_nao_vira_none():
    payload = {"created_by": "CVP1"}
    svc._resolver_matriculas(_CurNomes({"CVP1": ""}), payload)
    assert payload["created_by"] == "CVP1"


def test_sem_matricula_nao_consulta():
    cur = _CurNomes({})
    svc._resolver_matriculas(cur, {"created_by": "", "modified_by": None})
    assert cur.params is None


class _ISXErro(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status, self.detail = status, detail


class _Provedor:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    async def __call__(self, cfg, sistema, historico, identidade=None, campo_identidade=None):
        self.chamadas.append({"sistema": sistema, "historico": list(historico)})
        return self.respostas.pop(0), "modelo-teste"


def _abrir_que_explode():
    class _C:
        def execute(self, *a, **k):
            raise RuntimeError("banco fora")

        def fetchall(self):
            return []

        def commit(self):
            pass

        def close(self):
            pass
    return _C(), _C()


@pytest.mark.asyncio
async def test_falha_ao_resolver_nomes_nao_derruba_a_extracao(monkeypatch):
    async def _executor(fn, *args, teto):
        return fn(*args)
    monkeypatch.setattr(af, "isx_no_executor", _executor)
    monkeypatch.setattr(af.lineage_isx, "config", lambda: "CFG")
    monkeypatch.setattr(af, "projeto_tem_dsx", lambda nome: False)
    monkeypatch.setattr(af.lineage_isx, "extrair", lambda *a: (
        {"last_modified": "x"},
        {"created_by": "CVP1", "stages": [{"stage_name": "Junta", "stage_type_raw": "CSequencer"},
                                          {"stage_name": "Ods_00", "stage_type_raw": "CJobActivity"}],
         "children": [{"job_name": "SsdPrs_Ods_00_ext", "activity": "Ods_00"}]}, False))
    provedor = _Provedor(['```json\n{"ferramenta": "isx_extrair", "args": {"job_name": "SeqX"}}\n```', "pronto"])
    monkeypatch.setattr(ia_provedor, "chat_conversa", provedor)
    r = await svc.conversar(_abrir_que_explode, mensagens=[{"role": "user", "content": "filhos da SeqX?"}],
                            projeto_atual="BI_CVP", provedor_cfg={}, identidade="cvp-x", campo_identidade=None,
                            ssh_max=10, acao_editar=True, matricula="DEV1")
    assert r["status"] == "ok"
    dado = provedor.chamadas[1]["historico"][-1]["content"]
    assert "SsdPrs_Ods_00_ext" in dado and "Junta" in dado
    assert '"activity"' not in dado and "CJobActivity" not in dado
    assert '"created_by": "CVP1"' in dado


# ═══════════ 4. o prompt mesclado ═════════════════════════════════════════

def test_prompt_traz_o_que_foi_validado_em_producao_e_o_que_a_f5_f6_acrescentaram():
    p = svc._prompt_sistema("BI_CVP")
    for trecho in ("## Armadilhas conhecidas", "SEQUENCE", "PARALLEL", "ParameterSets", "`children`",
                   "jobinfo", "Nunca invente informação",
                   "interpretacao_aprovada", '"propostas"', '"aprendizados"', "curador"):
        assert trecho in p, trecho
    for cmd in af.ALLOWLIST_DSJOB:
        assert cmd in p


def test_prompt_nao_manda_usar_activity_que_nao_chega_mais_ao_modelo():
    assert "activity" not in svc._prompt_sistema("BI_CVP").replace("CJobActivity", "")
