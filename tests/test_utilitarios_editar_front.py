"""Tela Utilitários › Criar/editar arquivo (F5 da spec docs/spec-utilitarios-arquivos.md) — o front.

  1. **Bancada renderizada** (`tests/js/utilitarios_editar_harness.cjs`): o
     formulário e o modal rodam no React mínimo da casa e a bancada CLICA —
     Gravar só com pedido válido; quem não pode gravar vê o editor desabilitado
     com a explicação; Carregar existente preenche o editor e troca a
     codificação para a detectada; € em Latin-1 desliga o Gravar nomeando a
     linha; Ctrl+Enter grava; o modal abre em "gravando", vira resultado com
     "Ver arquivo", ou o pedido de confirmação do 409 com o que será
     substituído. Sem Node ou sem `node_modules`, SALTA.
  2. **Anti-drift** por leitura do fonte, sem Node: a página tem as duas abas,
     chama `/utilitarios/arquivo/gravar`, guarda a troca de aba com texto não
     gravado, e a confirmação de sobrescrever reenvia com `sobrescrever: true`.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "utilitarios_editar_harness.cjs"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"
PAGINA = RAIZ / "ui-react" / "src" / "pages" / "Utilitarios.tsx"
FORM = RAIZ / "ui-react" / "src" / "components" / "utilitarios" / "FormEditarArquivo.tsx"


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


def _sem_comentarios(fonte: str) -> str:
    fonte = re.sub(r"/\*.*?\*/", "", fonte, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", linha) for linha in fonte.splitlines())


# ═══════════ 1. funções puras ══════════════════════════════════════════════

def test_nome_extensao_e_caminho(cen):
    p = cen["puras"]
    assert p["nomeCompleto"] == "carga.txt"
    assert p["separar"] == [{"nome": "carga.2026", "extensao": "txt"}, {"nome": "semext", "extensao": ""},
                            {"nome": ".oculto", "extensao": ""}]
    assert p["pastaENome"] == [{"diretorio": "/dados/bi/2026", "nome": "x.txt"}, {"diretorio": "/", "nome": "x.txt"},
                               {"diretorio": "", "nome": "x.txt"}]


def test_aviso_do_nome_base(cen):
    a = cen["puras"]["avisoNomeBase"]
    assert a["vazio"] is None and a["ok"] is None and a["noLimite"] is None
    assert a["barra"] and a["controle"] == "Sem caracteres de controle."
    assert "215" in a["longo"]


def test_latin1_linhas_bytes_extensao(cen):
    p = cen["puras"]
    assert p["foraDoLatin1"][0] is None
    assert p["foraDoLatin1"][1] == {"linha": 2, "posicao": 11, "char": "€"}
    assert p["foraDoLatin1"][2] == {"linha": 2, "posicao": 2, "char": "😀"}
    assert p["contarLinhas"] == [0, 1, 2, 2]
    assert p["contarBytes"] == [6, 4]              # "ação": 6 bytes em UTF-8, 4 em Latin-1
    assert p["extensaoValida"] == [True, False, True]   # "TXT" vale: a função normaliza a caixa


def test_gravacao_pronta(cen):
    assert cen["puras"]["pronta"] == {"ok": True, "semPermissao": False, "fora": False, "extRuim": False,
                                      "latin1Fora": False, "latin1Ok": True, "vazioOk": True}


def test_erro_de_gravacao_le_o_409_com_o_que_existe(cen):
    e = cen["puras"]["erroGravacao"]
    assert e["conflito"] == {"status": 409, "mensagem": "O arquivo já existe. Confirme para gravar por cima.",
                             "existente": {"tamanho_bytes": 27, "modificado_em": "2026-09-03 07:06:00"}}
    assert e["string"] == {"status": 422, "mensagem": "Extensão 'sh' não liberada"}
    assert e["rede"] == {"status": None, "mensagem": "Não foi possível falar com a API."}
    assert cen["puras"]["resumo"] == ["arquivo sobrescrito", "27 B", "2 linhas", "codificação utf-8",
                                      "sha256 abcdef012345…", "cópia de segurança em /x.bak-1", "0,2 s"]


# ═══════════ 2. formulário ═════════════════════════════════════════════════

def test_formulario_comeca_desligado_com_a_primeira_extensao_e_utf8(cen):
    f = cen["form"]
    assert f["inicio"] == {"gravar": True, "carregar": True, "extensao": "txt", "codificacao": "utf-8",
                           "contador": "0 linhas · 0 bytes (utf-8)"}
    assert f["semConteudo"] == {"gravar": False, "carregar": False}   # conteúdo vazio é gravável


def test_nome_com_extensao_colada_separa(cen):
    assert cen["form"]["nomeComExtensao"] == {"nome": "consulta", "extensao": "sql"}
    assert cen["form"]["nomeComExtensaoMaiuscula"] == {"nome": "CONSULTA", "extensao": "sql"}


def test_enter_num_campo_nao_grava(cen):
    # Submissão implícita do <form> (Enter em Pasta/Nome): NÃO cria arquivo.
    assert cen["form"]["enterNoCampo"] == 0


def test_sujo_vive_na_pagina_e_sobrevive_a_primeira_gravacao(cen):
    f = cen["form"]
    assert f["botaoGravar"] == 2                                 # Ctrl+Enter e o botão
    assert f["aposGravar"] == {"contador": "2 linhas · 29 bytes (utf-8)", "sujoPagina": False}   # "ação" 6 + "€" 3 bytes
    assert f["aposGravarDigitou"]["sujoPagina"] is True
    assert f["aposGravarDigitou"]["contador"].endswith("· não gravado")
    assert f["aposGravarDigitou"]["avisos"][-1] is True and f["aposGravarDigitou"]["avisos"].count(True) >= 2


def test_extensoes_que_chegam_depois_entram_sem_estado_preso(cen):
    e = cen["extensoesTarde"]
    assert e["antes"] == {"extensao": "", "gravar": True, "aviso": ["sem-extensoes"]}
    assert e["depois"] == {"extensao": "txt", "gravar": False, "aviso": []}   # `txt` é o padrão quando liberada


def test_carregar_existente_preenche_e_troca_a_codificacao(cen):
    c = cen["form"]["carregou"]
    assert c["pedido"] == [{"servidor": "datastage", "diretorio": "/dados/param", "nome": "parametros.param"}]
    assert c["conteudo"] == "DESCRICAO=ação\n"
    assert c["codificacao"] == "latin-1"
    assert c["contador"] == "1 linha · 15 bytes (latin-1)"


def test_euro_em_latin1_desliga_e_avisa_em_utf8_volta(cen):
    f = cen["form"]
    assert f["euroLatin1"]["gravar"] is True and f["euroLatin1"]["aviso"] is True
    assert "não gravado" in f["euroLatin1"]["contador"]
    assert f["euroUtf8"] == {"gravar": False, "aviso": False}


def test_ctrl_enter_grava_e_enter_sozinho_nao(cen):
    f = cen["form"]
    assert f["ctrlEnter"] == [{"servidor": "datastage", "diretorio": "/dados/param", "nome": "parametros", "extensao": "param",
                               "conteudo": "DESCRICAO=ação\nVALOR=10€\n", "codificacao": "utf-8", "sobrescrever": False}]
    assert f["enterSozinho"] == 1
    assert f["extRuim"]["gravar"] is True


def test_sem_permissao_e_sem_extensoes(cen):
    assert cen["formSemPermissao"] == {"aviso": ["sem-permissao"], "editorDesabilitado": True, "gravar": True}
    assert cen["formSemExtensoes"] == {"aviso": ["sem-extensoes"], "gravar": True}
    assert cen["formCarregarFalhou"] == {"conteudo": "meu texto"}


# ═══════════ 3. modal ══════════════════════════════════════════════════════

def test_modal_gravando_existe_pronto_erro(cen):
    m = cen["modal"]
    assert m["gravando"] == {"caminho": "/dados/bi/2026/prova.txt", "spinner": 1, "sobrescrever": 0, "fechou": 1}
    assert m["existe"] == {"mensagem": True, "tamanho": True, "data": True, "fechar": 0, "ver": 0,
                           "sobrescreveu": 1, "cancelou": 1}
    assert m["pronto"]["caminho"] == "/dados/bi/2026/prova.txt"
    assert "arquivo sobrescrito" in m["pronto"]["resumo"] and "cópia de segurança" in m["pronto"]["resumo"]
    assert m["pronto"]["sobrescrever"] == 0 and m["pronto"]["ver"] == ["/dados/bi/2026/prova.txt"]
    assert m["erro"] == {"mensagem": True, "atributo": 413, "sobrescrever": 0}
    assert m["fechado"] == 0


# ═══════════ 4. anti-drift (sem Node) ══════════════════════════════════════

def test_pagina_tem_as_duas_abas_e_o_fluxo_de_gravar():
    pagina = _sem_comentarios(PAGINA.read_text(encoding="utf-8"))
    assert "id: 'editar'" in pagina and "label: 'Criar/editar arquivo'" in pagina
    assert "/utilitarios/arquivo/gravar" in pagina
    assert "sobrescrever: true" in pagina, "a confirmação reenvia o mesmo pedido com sobrescrever"
    assert "alterações não gravadas" in pagina or "não gravad" in pagina, "troca de aba com texto não gravado pede confirmação"
    assert "chega na F" not in pagina


def test_formulario_grava_por_ctrl_enter_e_nao_por_enter():
    fonte = _sem_comentarios(FORM.read_text(encoding="utf-8"))
    assert "e.ctrlKey || e.metaKey) && e.key === 'Enter'" in fonte
    assert 'type="submit"' not in fonte, "Enter num campo submeteria o form e gravaria um arquivo vazio"
    assert "useState(false)" not in fonte, "`sujo` é da página (prop), não estado espelhado no formulário"


def test_pagina_ve_o_gravado_pelo_caminho_digitado_e_nao_reseta_a_mutation():
    pagina = _sem_comentarios(PAGINA.read_text(encoding="utf-8"))
    assert "nomeArquivoCompleto(pedidoG.nome, pedidoG.extensao)" in pagina, "Ver arquivo usa o pedido lexical (raiz symlink)"
    assert "gravacao.reset()" not in pagina, "fechar o modal não pode religar o Gravar com pedido em voo"
    assert "refetchOnWindowFocus: false" in pagina
    assert "config-desatualizada" in pagina, "refetch que falha vira aviso, não página de erro"
    assert "sujo={sujo}" in pagina
