"""Ajustes feitos em produção em 23/09/2026 (commits 3bf0565, 4347a25, e69b367 e 951b399 da branch
`feat/agente-datastage-melhorias`), portado para o próximo deploy não o
desfazer:

  • `MAX_RODADAS_FERRAMENTA` 3 → 4: resolver_projeto → (uma intermediária) →
    isx_extrair → resposta cabe numa pergunta;
  • prompt: para os filhos de uma sequence, ir DIRETO ao isx_extrair (sem
    dsjob antes, que gastava uma rodada e não traz os filhos).

A 4ª rodada não afrouxa o teto de tempo: o orçamento de 240 s é por RELÓGIO.
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

from services import agentes as svc  # noqa: E402
from services import agentes_ferramentas as af  # noqa: E402
from services import ia_provedor  # noqa: E402


def test_quatro_rodadas_de_ferramenta_por_pergunta():
    assert svc.MAX_RODADAS_FERRAMENTA == 4


def test_prompt_nao_manda_dsjob_antes_nos_filhos_de_sequence():
    # 3bf0565 dizia "vá DIRETO ao isx_extrair"; 4347a25 trocou por "DSX
    # primeiro, depois ISX" — o que se mantém é: nada de dsjob antes.
    p = svc._prompt_sistema("BI_PRESTAMISTA")
    assert "NÃO chame dsjob" in p


@pytest.mark.asyncio
async def test_quarta_rodada_ainda_respeita_o_teto_de_tempo(monkeypatch):
    """Com o relógio além do orçamento, a rodada para — por mais rodadas que
    o limite de contagem ainda permitisse."""
    agora = {"t": 0.0}
    monkeypatch.setattr(svc.time, "monotonic", lambda: agora["t"])
    monkeypatch.setattr(af, "projeto_tem_dsx", lambda n: False)
    chamadas = []

    async def _provedor(cfg, sistema, historico, identidade=None, campo_identidade=None):
        chamadas.append(1)
        agora["t"] += 100  # cada ida ao gateway "leva" 100 s
        return '```json\n' + json.dumps({"ferramenta": "base", "args": {"job_name": "J"}}) + '\n```', "m"
    monkeypatch.setattr(ia_provedor, "chat_conversa", _provedor)
    monkeypatch.setattr(af, "ferramenta_base", lambda cur, p, j: {"encontrado": False})

    def _abrir():
        c = MagicMock()
        c.fetchall.return_value = []
        return c, c
    r = await svc.conversar(_abrir, mensagens=[{"role": "user", "content": "oi"}], projeto_atual="P",
                            provedor_cfg={}, identidade="x", campo_identidade=None, ssh_max=10)
    assert r["status"] == "tempo_esgotado"
    assert len(chamadas) < svc.MAX_RODADAS_FERRAMENTA + 1


# ═══════════ 4347a25 (produção) + filhos de sequence como fatos ═══════════

def test_prompt_filhos_de_sequence_direto_no_isx_ao_vivo():
    """Decisão de produção (e69b367, revertendo o 4347a25): o DSX é retrato e
    pode ter menos jobs — para os filhos, sempre o ISX ao vivo."""
    p = svc._prompt_sistema("BI_PRESTAMISTA")
    assert "vá DIRETO ao isx_extrair ao vivo" in p and "NÃO use dsx_consulta antes" in p
    assert "NÃO chame dsjob" in p
    assert "informe-o — grava a lineage completa" in p


def test_prompt_proibe_sequence_como_pipeline_name():
    """951b399: pipeline_name=<a própria sequence> dava 404."""
    assert "NUNCA use a própria sequence como pipeline_name" in svc._prompt_sistema("BI_PRESTAMISTA")


def test_prompt_proibe_inventar_eco_tardio():
    """951b399: o modelo inventava que um resultado era de "chamada anterior"."""
    p = svc._prompt_sistema("BI_PRESTAMISTA")
    assert 'Nunca diga que um resultado é "eco tardio"' in p
    assert "diga quantos itens\n  a ferramenta retornou agora" in p


def test_prompt_nao_diz_que_nada_persiste_sem_pipeline():
    """Depois da F5, o ISX fora de pipeline grava FATOS (a `base` devolve) —
    o texto de produção "NÃO persiste no banco" descrevia a F3."""
    p = svc._prompt_sistema("BI_PRESTAMISTA")
    assert "NÃO persiste no banco" not in p
    assert 'os filhos de uma sequence aparecem como fatos "lineage" com chave "filho:NOME_DO_JOB"' in p


def test_filhos_da_sequence_viram_fatos():
    from services import agentes_conhecimento as ac
    fatos = ac.fatos_do_isx({"children": [
        {"job_name": "SsdPrs_Ods_00_ext", "activity": "AtividadeVisual"}, {"activity": "sem_job"}, "x",
        {"job_name": "SsdPrs_Ods_01_ext"}]})
    assert [(f["tipo"], f["chave"]) for f in fatos] == [
        ("lineage", "filho:SsdPrs_Ods_00_ext"), ("lineage", "filho:SsdPrs_Ods_01_ext")]
    assert "AtividadeVisual" not in json.dumps(fatos)  # o nome da atividade não vira fato


def test_filho_que_sai_da_sequence_fica_obsoleto():
    from services import agentes_conhecimento as ac
    from tests._banco_agentes_f5 import BancoF5
    banco = BancoF5()

    def _gravar(filhos):
        ac.gravar_fatos(banco, banco.cursor(), ds_project="BI_PRESTAMISTA", job_name="SeqSsdPrs", pipeline_name=None,
                        origem="isx", fatos=ac.fatos_do_isx({"children": [{"job_name": f} for f in filhos]}),
                        evidencia="isx", ds_last_modified="d", matricula="DEV1")
    _gravar(["A", "B", "C"])
    _gravar(["A", "C"])
    assert sorted(f["chave"] for f in banco.vigentes()) == ["filho:A", "filho:C"]



# ═══════════ o DSX lista os filhos de verdade (revisão do 4347a25) ═════════

def _motor_real():
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(raiz / "dags"))
    from utils.dsx_engine import DSXEngine
    m = DSXEngine()
    m.diretorio_base = str(raiz / "dsx")
    return m


def test_dsx_real_lista_os_filhos_da_sequence():
    """`dsx/seq_geral.dsx` (arquivo real do repo): a sequence chama 4 jobs.
    O `DSXEngine.extrair` sozinho devolvia `dados=[]` para ela."""
    m = _motor_real()
    seq = next(j for j in m.listar_jobs("seq_geral")["jobs"] if j.startswith("Seq_"))
    assert af.filhos_de_sequence_no_dsx(m, "seq_geral", seq) == [
        "BiCvp_BaseCobranca_00_ext_Parcelas_Pagas", "BiCvp_BaseCobranca_01_ins_Parcelas_Pagas",
        "BiCvp_BaseCobranca_02_ext_Parcelas_Clientes", "BiCvp_BaseCobranca_03_ins_Parcelas_Clientes"]


@pytest.mark.parametrize("projeto,job", [("seq_geral", "BiCvp_BaseCobranca_00_ext_Parcelas_Pagas"),
                                         ("seq_geral", "Nao_Existe"), ("arquivo_ausente", "X")])
def test_sem_filhos_devolve_vazio_sem_levantar(projeto, job):
    assert af.filhos_de_sequence_no_dsx(_motor_real(), projeto, job) == []


@pytest.mark.asyncio
async def test_dsx_consulta_extrair_devolve_children(monkeypatch):
    m = _motor_real()
    seq = next(j for j in m.listar_jobs("seq_geral")["jobs"] if j.startswith("Seq_"))
    monkeypatch.setattr(af, "_dsx_engine_cls", lambda: (lambda: m))
    r = await af.ferramenta_dsx_consulta("seq_geral", "extrair", {"job_name": seq})
    assert r["sucesso"] and len(r["children"]) == 4
    assert r["dsx_arquivo"] == "seq_geral.dsx" and r["dsx_data"]


def test_filhos_do_dsx_viram_fatos():
    from services import agentes_conhecimento as ac
    fatos = ac.fatos_do_dsx({"sucesso": True, "dados": [], "children": [{"job_name": "A"}, {"job_name": "B"}]})
    assert [(f["tipo"], f["chave"]) for f in fatos] == [("lineage", "filho:A"), ("lineage", "filho:B")]



def test_eco_tardio_admite_so_o_que_a_ferramenta_informou():
    """Revisão: "nunca diga já calculado" contradizia `cache_hit: true` e a
    guarda de reexecução ("não repeti") — a exceção é só o que a ferramenta
    disse, nunca uma explicação inventada."""
    p = svc._prompt_sistema("BI_PRESTAMISTA")
    assert '"cache_hit": true (a extração veio do cache)' in p and '"não\n  repeti"' in p



def test_prompt_proibe_arvore_de_sub_sequences_sem_dados():
    """5526de5 (produção): não descer recursivamente inventando a árvore."""
    p = svc._prompt_sistema("BI_PRESTAMISTA")
    assert "NUNCA monte árvore hierárquica de sub-sequences sem ter extraído cada nível" in p
    assert "Inventar estrutura de árvore a partir de nomes é alucinação" in p
