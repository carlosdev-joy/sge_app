"""Aba "Job DataStage" da Governança (F4 da spec docs/spec-lineage-isx.md) — o front.

  1. **Bancada renderizada** (`tests/js/lineage_isx_harness.cjs`): os componentes de
     apresentação rodam no React mínimo da casa e a bancada CLICA — a lista mostra o
     estado e o botão Extrair só com acao_editar (Atualizar = force); o cabeçalho diz
     cache × extraído agora e mostra o erro da última tentativa; a sequence lista os
     filhos e só oferece Extrair ao que está no pipeline; a tabela seleciona; o painel
     do stage mostra SQL, colunas, expressões, APT colapsado e `#PSet.X#` como badge.
     O leiaute do grafo (puro) é conferido em camadas. Sem Node ou sem `node_modules`,
     SALTA.
  2. **Anti-drift** por leitura do fonte, sem Node: a aba está nos dois lugares da
     Governança, o container chama os endpoints da F2/F3, cores sempre em par
     claro/escuro (docs/ui-temas-cores.md), `type="button"` em todo botão, o grafo
     importa o CSS do xyflow, e o painel do stage é o Sheet.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "lineage_isx_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"
SRC = RAIZ / "ui-react" / "src"
ISX = SRC / "components" / "governanca" / "isx"
GOVERNANCA = SRC / "pages" / "Governanca.tsx"
LIB = SRC / "lib" / "lineageIsx.ts"


def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True, timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= 18 else None
    except Exception:  # noqa: BLE001
        return None


@pytest.fixture(scope="module")
def cen() -> dict:
    node = _node()
    if node is None:
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True, cwd=str(RAIZ), timeout=180)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


# ═══════════ 1. puras ═════════════════════════════════════════════════════════

def test_direcao_e_leiaute_em_camadas(cen):
    p = cen["puras"]
    assert p["direcaoDe"] == ["origem", "origem", "destino", "destino", "transformacao", "transformacao"]
    lei = p["leiaute"]
    assert lei["camadas"] == 3
    por = {n[0]: n for n in lei["nos"]}
    assert por["DM_119_INFO"][1:3] == [0, "origem"] and por["TrfNlist"][1:3] == [1, "transformacao"]
    assert por["DST_FTP_NLIST"][1:3] == [2, "destino"]
    # sem aresta: cai na coluna da direção (destino = última camada ligada)
    assert por["TB_DEST"][1] == 2 and por["Misterio"][1] == 2
    assert por["TrfNlist"][3] == 260 and por["DM_119_INFO"][3] == 0          # x = camada × 260
    # aresta duplicada some; alvo inexistente some
    assert lei["arestas"] == [["DM_119_INFO", "LnkNlist", "TrfNlist"], ["TrfNlist", "LnkDadosNlist", "DST_FTP_NLIST"]]
    assert dict(p["isolados"]) == {"DM_119_INFO": 0, "TrfNlist": 1, "DST_FTP_NLIST": 2, "TB_DEST": 2, "Misterio": 2}
    assert p["ciclo"]["camadas"] >= 1 and len(p["ciclo"]["nos"]) == 2             # ciclo não trava


def test_parametros_resumo_rotulos_e_erros(cen):
    p = cen["puras"]
    assert p["partes"][0] == [{"tipo": "parametro", "valor": "PSetSsdVida.ParmDirDst"}, {"tipo": "texto", "valor": "DST_FTP_NLIST.ds"}]
    assert p["partes"][1] == [{"tipo": "texto", "valor": "dbo.TB"}] and p["partes"][2] == []
    assert [x["tipo"] for x in p["partes"][3]] == ["parametro", "texto", "parametro"]
    assert p["ehParametro"] == [True, False, False, False]
    assert p["resumo"] == ["Ssd", "—", "DST_FTP_NLIST.ds", "DSN_STG · dbo.TB_DESTINO", "—"]
    assert p["rotulo"][0] == {"texto": "não extraído", "tom": "neutral"}
    assert p["rotulo"][1] == {"texto": "extraído em 2026-09-08 01:00:00", "tom": "success"}
    assert p["rotulo"][2]["tom"] == "warning" and p["rotulo"][3]["tom"] == "error" and "não encontrado" in p["rotulo"][3]["texto"]
    e = p["erro"]
    assert "acao_editar" in e[0]["mensagem"] and e[1]["mensagem"] == "O job X não está mapeado no pipeline P"
    assert "não respondeu" in e[2]["mensagem"] and e[3]["mensagem"] == "O istool falhou ao exportar o job"
    assert e[4] == {"status": None, "mensagem": "Não foi possível falar com a API."}
    assert "60 s" in e[5]["mensagem"] and "andamento" in e[6]["mensagem"]
    assert p["frases"] == ["Lote em andamento (queued)…", "3 job(s): 2 extraído(s), 0 em cache, 1 com erro em 4.2 s",
                           "O lote falhou antes de extrair — veja a DAG no Airflow.", "2 job(s): 0 extraído(s), 2 em cache"]
    assert p["formatos"] == ["217 ms", "4,2 s", "1,6 KB", "3,0 MB", ""]
    assert p["base"] == ["NLIST.ds", "y.txt", ""]


# ═══════════ 2. lista de jobs ═════════════════════════════════════════════════

def test_lista_estado_e_botoes_por_permissao(cen):
    li = cen["lista"]
    assert li["itens"] == ["SsdVidaDimePessoa02Ftp", "SeqSsdVidaDime", "JobRaiz", "http_saude"]
    assert li["selecionado"] == ["SsdVidaDimePessoa02Ftp"]
    # badge curto + detalhe (data · quem) truncado com title
    assert "extraído" in li["textos"][0] and "2026-09-08 01:00:00" in li["textos"][0] and "C012345" in li["textos"][0]
    assert "não extraído" in li["textos"][1]
    assert "erro" in li["textos"][2] and "Job não encontrado" in li["textos"][2] and "dag:etl_lineage_extract_isx" in li["textos"][2]
    assert "não é job DataStage" in li["textos"][3]
    # Atualizar (force) para quem já tem; Extrair para quem não tem; nó http não tem botão
    assert li["botoes"] == [["Atualizar", "1", False], ["Extrair", "0", False], ["Extrair", "0", False]]
    assert li["chamadasExtrair"] == [["SsdVidaDimePessoa02Ftp", True], ["SeqSsdVidaDime", False]]
    assert li["chamadasSelecionar"] == ["SeqSsdVidaDime"]
    assert li["semPermissaoBotoes"] == 0
    assert li["ocupada"] == [["Atualizar", True], ["Extraindo…", True], ["Extrair", True]]
    assert li["vazia"] == 1


# ═══════════ 3. cabeçalho ═════════════════════════════════════════════════════

def test_cabecalho_cache_extraido_erro_e_descricao(cen):
    c = cen["cabecalho"]
    assert c["badgeCache"] == 1 and c["badgeExtraido"] == 1 and c["soBanco"] == 0
    assert "SsdVidaDimePessoa02Ftp" in c["texto"] and "BI_VIDA" in c["texto"] and "217 ms" in c["texto"] and "1,6 KB" in c["texto"]
    assert "ETL de amostra" in c["texto"]
    assert c["erro"].startswith("O istool falhou") and "última extração que deu certo" in c["erro"]
    assert c["descricaoLongaAntes"] == 0 and c["descricaoLongaDepois"] == 1
    assert "Misterio (PxAlienStage)" in c["naoReconhecidos"]


# ═══════════ 4. sequence ══════════════════════════════════════════════════════

def test_filhos_da_sequence_so_extraem_o_que_esta_no_pipeline(cen):
    f = cen["filhos"]
    assert f["mapeados"] == [["SsdVidaDimePessoa02Ftp", "1"], ["JobDeOutroPipeline", "0"]]   # comparação sem caixa
    assert f["verFilho"] == 1 and f["extrairFilho"] == 1
    assert "fora deste pipeline" in f["texto"]
    # o nome que sai é o da LISTA (grafia do pipeline), não o do XML da sequence
    assert f["sel"] == ["ssdvidadimepessoa02ftp"] and f["ext"] == ["ssdvidadimepessoa02ftp"]
    assert f["vazio"] == 1 and f["semPermissao"] == 0


# ═══════════ 5. tabela e painel do stage ══════════════════════════════════════

def test_tabela_seleciona_e_resume(cen):
    t = cen["tabela"]
    assert t["linhas"] == ["DM_119_INFO", "TrfNlist", "DST_FTP_NLIST", "TB_DEST", "Misterio"]
    assert t["selecionada"] == ["TrfNlist"] and t["sel"] == ["DST_FTP_NLIST"]
    assert "Origem" in t["textos"][0] and "Ssd" in t["textos"][0] and "1 saída" in t["textos"][0]
    assert "Transformação" in t["textos"][1] and "2 saída · 1 entrada" in t["textos"][1]
    assert "Destino" in t["textos"][2] and "DST_FTP_NLIST.ds" in t["textos"][2]


def test_painel_do_stage_sql_colunas_expressoes_apt_e_parametro(cen):
    s = cen["stage"]
    assert s["origem"]["sql"].startswith("select distinct") and "DM_003_PROPOSTA" in s["origem"]["sql"]
    assert s["origem"]["banco"] == "Ssd" and s["origem"]["colunasSaida"] == ["saida"]
    assert s["trf"]["expressoes"] == ["IND_PESSOA_NLIST", "CHAVE_NLIST"] and s["trf"]["sql"] == 0
    assert s["trf"]["aptAntes"] == 0 and s["trf"]["aptDepois"].startswith("mainloop")      # colapsado até clicar
    assert s["trf"]["colunas"] == ["saida", "entrada"]
    assert s["destino"]["parametros"] == ["PSetSsdVida.ParmDirDst"] and "DST_FTP_NLIST.ds" in s["destino"]["arquivo"]
    assert s["destino"]["colunas"] == ["entrada"]
    assert s["textoSoParametro"]["badges"] == ["PSetSsdVida.ParmDbNameSsd"] and "runtime" in s["textoSoParametro"]["titulo"]
    assert s["textoVazio"] == "—"


# ═══════════ 6. anti-drift ════════════════════════════════════════════════════

def test_aba_nos_dois_lugares_da_governanca():
    fonte = GOVERNANCA.read_text(encoding="utf-8")
    assert "{ id: 'isx', label: 'Job DataStage' }" in fonte
    assert "{tab === 'isx' && <PainelJobIsx pipeline={pipeline} setPipeline={setPipeline} />}" in fonte
    assert "import { PainelJobIsx } from '../components/governanca/isx/PainelJobIsx'" in fonte


def test_container_chama_os_endpoints_isx():
    fonte = (ISX / "PainelJobIsx.tsx").read_text(encoding="utf-8")
    for trecho in ("/lineage/isx/pipeline?pipeline_name=", "/lineage/isx/job?pipeline_name=", "'/lineage/isx/extrair'",
                   "'/lineage/isx/lote'", "/lineage/isx/lote/${", "acao_editar", "isAdmin", "erroIsx("):
        assert trecho in fonte, trecho
    assert "refetchInterval" in fonte and "force: forcar" in fonte


def test_container_guarda_as_correcoes_da_revisao_adversarial():
    """Cada linha é um achado da revisão adversarial da F4 — se sumir, o bug volta."""
    fonte = (ISX / "PainelJobIsx.tsx").read_text(encoding="utf-8")
    # 1. grafo remonta por job: o fitView roda de novo ao trocar de job com detalhe em cache
    assert "<GrafoIsx key={job.job_name}" in fonte
    # 2. Extrair/Atualizar fixa a seleção ANTES do resultado (falha não pula para outro job)
    assert re.search(r"onMutate: \(\{ job \}\) => \{[^}]*setJobEscolhido\(job\)", fonte)
    # 4. falha da extração invalida também o detalhe do job (a API registra a tentativa)
    onerror = fonte[fonte.index("onError: (e, { job })"):fonte.index("onSettled")]
    assert "queryKey: ['isx-job', pipeline, job]" in onerror
    # 6. erro ao consultar o lote para o polling, aparece na tela e libera o botão
    assert "q.state.status === 'error'" in fonte and "run.isError" in fonte
    assert "|| run.isError" in fonte
    # 7. sem flicker: "ainda não foi extraído" só sem detalhe carregado
    assert "!jobAtual.isx && !extraindo && !job &&" in fonte
    # 8. trocar de pipeline zera o lote acompanhado
    bloco = fonte[fonte.index("if (pipeline !== pipelineAnterior)"):fonte.index("const { data: pipeList }")]
    assert "setRunId(null)" in bloco
    # 5. Controls/Background do xyflow seguem o tema (mesmo hook do FluxoEditor)
    grafo = (ISX / "GrafoIsx.tsx").read_text(encoding="utf-8")
    assert "useColorMode" in grafo and "colorMode={colorMode}" in grafo
    # 9. a frase "dados abaixo" só quando há stages para mostrar
    cab = (ISX / "CabecalhoJobIsx.tsx").read_text(encoding="utf-8")
    assert "job.stages.length > 0" in cab and "dados abaixo são da última extração" in cab


# Anti-padrões de docs/ui-temas-cores.md §3: fundo/borda escuros e texto claro como
# classe BASE (sem `dark:`). Fundo -50/-100, texto -700/-800 e borda -200/-300 são o
# lado claro dos pares canônicos e continuam permitidos.
_BASE_PROIBIDA = re.compile(r"(?<![:\w/-])(?:bg-[a-z]+-(?:900|800)(?:/\d+)?|text-[a-z]+-(?:300|200)|border-[a-z]+-(?:900|800))\b")


def test_cores_sempre_em_par_claro_escuro_e_botoes_com_type():
    for arquivo in sorted(ISX.glob("*.tsx")) + [LIB]:
        fonte = arquivo.read_text(encoding="utf-8")
        for m in _BASE_PROIBIDA.finditer(fonte):
            antes = fonte[max(0, m.start() - 5):m.start()]
            linha = fonte[fonte.rfind("\n", 0, m.start()) + 1:fonte.find("\n", m.end())]
            if "bg-gray-950" in linha:
                continue   # superfície sempre escura (SQL/APT) — exceção do §4 de docs/ui-temas-cores.md
            assert antes.endswith("dark:"), f"{arquivo.name}: classe base {m.group(0)!r} sem par dark: (docs/ui-temas-cores.md)"
        if arquivo.suffix == ".tsx":
            # todo <button> nativo tem type="button" (o <Button> da casa também recebe o type por prop)
            assert fonte.count("<button") <= fonte.count('type="button"'), f"{arquivo.name}: botão sem type=\"button\""
    grafo = (ISX / "GrafoIsx.tsx").read_text(encoding="utf-8")
    assert "import '@xyflow/react/dist/style.css'" in grafo and "leiaute(" in grafo
    painel = (ISX / "PainelStageIsx.tsx").read_text(encoding="utf-8")
    assert "<Sheet " in painel and "ConteudoStageIsx" in painel
    # o SQL e o APT são superfícies sempre escuras (exceção documentada)
    conteudo = (ISX / "ConteudoStageIsx.tsx").read_text(encoding="utf-8")
    assert conteudo.count("bg-gray-950 text-gray-200") == 2
