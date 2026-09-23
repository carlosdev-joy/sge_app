"""Tela do prompt com versões (A2 + BK-1 de docs/spec-agentes-admin.md).

As funções puras rodam DE VERDADE pelo harness `tests/js/agentes_prompt_harness.cjs`.
O resto é leitura do fonte, como os outros testes de front dos agentes (o repo
não tem runtime de teste para React). O que se prende, e por quê:

  1. **A seção entra NO FIM da aba** — sem reordenar o que já existe (regra do
     projeto: não mudar a ordem da tela sem pedido).
  2. **Toda gravação carrega `versao_base`** — sem ela o 409 de outro admin
     não existe e uma gravação passa por cima da outra.
  3. **409 não perde o texto digitado** — vai para "Seu texto".
  4. **Motivo obrigatório** e **parte fixa só leitura**.
  5. **Histórico mostra a vigência (BK-1)** — vigente de/até, duração,
     respostas, tempo médio — com os campos que o backend manda.
  6. **Tokens de cor, sem `overflow-hidden`**, e `lib/agentes.ts` sem import.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_agentes_f3_front import _COR_UTIL, _TOM_PERMITIDO, codigo

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / "ui-react" / "src"
PROMPT = FRONT / "components" / "admin" / "PromptAgente.tsx"
ABA = FRONT / "components" / "admin" / "AgentesTab.tsx"
LIB = FRONT / "lib" / "agentes.ts"
ROUTER = RAIZ / "api" / "routers" / "agentes.py"


def test_funcoes_puras_rodam_no_node():
    node = shutil.which("node")
    if not node or not (RAIZ / "ui-react/node_modules/sucrase").is_dir():
        pytest.skip("front não instalado nesta máquina")
    r = subprocess.run([node, str(RAIZ / "tests/js/agentes_prompt_harness.cjs")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr or r.stdout
    assert r.stdout.strip() == "ok"


# ═══════════ 1. posição na aba ════════════════════════════════════════════

def test_secao_do_prompt_entra_no_fim_da_aba_sem_reordenar():
    fonte = codigo(ABA)
    assert "import { PromptAgente } from './PromptAgente'" in fonte
    i_prompt = fonte.index("<PromptAgente")
    # tudo o que já existia vem antes, na mesma ordem
    ordem = [fonte.index(t) for t in ("Interruptores", "Gateway e limites", "Quem pode usar", "Curadores")]
    assert ordem == sorted(ordem) and ordem[-1] < i_prompt
    assert fonte[i_prompt:].count("</section>") == 0, "nada da aba antiga pode vir depois do prompt"


# ═══════════ 2–4. contrato com a API ═════════════════════════════════════

def test_gravar_manda_a_versao_em_que_o_rascunho_comecou():
    """Revisão adversarial da A2: com `versao_base: ativa.versao`, um refetch
    (foco da janela, invalidação) trocava a base por baixo do rascunho e a
    gravação feita sobre a v3 passava por cima da v4 de outro admin, sem 409."""
    fonte = codigo(PROMPT)
    assert "versao_base: baseDoRascunho ?? ativa.versao" in fonte
    assert "versao_base: ativa.versao })" not in fonte.split("salvar.mutate(")[1].split(")}")[0]
    # a base é fixada ao COMEÇAR a editar, e o editor só muda por `editar`
    assert re.search(r"if \(rascunho === null\) setBaseDoRascunho\(ativa\.versao\)", fonte)
    assert "onChange={e => editar(e.target.value)}" in fonte
    assert "onChange={e => setRascunho(" not in fonte
    # e o aviso aparece antes do clique
    assert "desatualizado = rascunho !== null && baseDoRascunho !== null && baseDoRascunho !== ativa.versao" in fonte


def test_restaurar_manda_a_versao_em_uso():
    """Restaurar não depende do rascunho: a base é a versão em uso que a
    pessoa está vendo quando confirma."""
    fonte = codigo(PROMPT)
    assert re.search(r"restaurar\.mutate\(\{ versao: restaurando\.versao, motivo: restaurando\.motivo,\s*"
                     r"versao_base: ativa\.versao \}\)", fonte)
    assert "method: 'PUT'" in fonte and "`${base}/restaurar`" in fonte


def test_conflito_guarda_o_texto_digitado():
    fonte = codigo(PROMPT)
    assert "codigoDoErro(e) === 'prompt_mudou'" in fonte
    assert "tratarErro(e, 'Não foi possível gravar a versão', v.texto)" in fonte
    bloco = fonte[fonte.index("if (textoDigitado !== null) {"):]
    assert bloco.index("setSeuTexto(textoDigitado)") < bloco.index("setRascunho(null)")
    assert "data-agentes-prompt-seu-texto" in fonte


def test_editor_travado_enquanto_grava():
    assert "readOnly={salvar.isPending}" in codigo(PROMPT)


def test_restauracao_propria_nao_culpa_outro_admin():
    fonte = codigo(PROMPT)
    assert "if (rascunho !== null) setMinhaRestauracao(r.ativa.versao)" in fonte
    assert "minhaRestauracao === ativa.versao" in fonte


def test_copiar_usa_o_helper_que_funciona_em_http_e_nao_mente():
    fonte = codigo(PROMPT)
    assert "import { copyToClipboard } from '../../lib/clipboard'" in fonte
    assert "navigator.clipboard" not in fonte
    assert re.search(r"if \(await copyToClipboard\(seuTexto\)\) toast\.success\('Texto copiado'\)\s*"
                     r"else toast\.error\(", fonte)


def test_motivo_obrigatorio_para_gravar_e_restaurar():
    fonte = codigo(PROMPT)
    assert "motivoValido(motivo, limites.motivo_min, limites.motivo_max)" in fonte
    assert "motivoValido(restaurando.motivo, limites.motivo_min, limites.motivo_max)" in fonte
    assert "disabled={!podeSalvar}" in fonte


def test_parte_fixa_e_so_leitura():
    fonte = codigo(PROMPT)
    bloco = fonte[fonte.index("data-agentes-prompt-parte-fixa"):fonte.index("data-agentes-prompt-historico")]
    assert "<pre" in bloco and "<textarea" not in bloco.lower() and "<Textarea" not in bloco
    assert "parte_fixa.antes" in bloco and "parte_fixa.depois" in bloco


# ═══════════ 5. BK-1 no histórico ═════════════════════════════════════════

def test_historico_mostra_a_vigencia_de_cada_versao():
    fonte = codigo(PROMPT)
    for coluna in ("Vigente de", "Até", "Duração", "Respostas", "Tempo médio", "Por", "Motivo"):
        assert f">{coluna}</th>" in fonte, coluna
    for uso in ("dataHoraCurta(v.vigente_de)", "dataHoraCurta(v.vigente_ate)", "duracaoDaVigencia(v.duracao_s)",
                "v.respostas", "tempoMedio(v.duracao_media_ms)"):
        assert uso in fonte, uso
    assert "retencao_dias" in fonte  # a nota da retenção sai do backend, não de um número fixo


def _campos_da_interface(nome: str) -> set[str]:
    bloco = re.search(rf"export interface {nome}[^{{]*\{{(.*?)\n\}}", codigo(LIB), re.S).group(1)
    return set(re.findall(r"^\s*(\w+)\??:", bloco, re.M))


def test_tipos_do_front_espelham_o_que_o_backend_manda():
    fonte = ROUTER.read_text(encoding="utf-8")
    item = re.search(r"def _versao_para_api.*?item = \{(.*?)\}", fonte, re.S).group(1)
    chaves = set(re.findall(r'"(\w+)":', item)) | {"texto"}
    bk1 = re.search(r'item\.update\(\{(.*?)\}\)', fonte, re.S).group(1)
    chaves |= set(re.findall(r'"(\w+)":', bk1))
    assert chaves == _campos_da_interface("VersaoPrompt")
    assert {"agente", "ativa", "versoes", "agora", "retencao_dias"} == _campos_da_interface("VersoesPromptResposta")


# ═══════════ 6. estilo e isolamento do lib ════════════════════════════════

def test_prompt_usa_so_os_tokens_de_cor():
    fonte = codigo(PROMPT)
    achados = [m.group(0) for m in _COR_UTIL.finditer(fonte) if not _TOM_PERMITIDO.fullmatch(m.group(0))]
    assert not achados, f"cor fora dos tokens: {sorted(set(achados))}"
    assert "overflow-hidden" not in fonte


def test_lib_agentes_continua_sem_import():
    """Os harnesses Node executam `lib/agentes.ts` sozinho — um import quebra
    todos (foi o que aconteceu com `lib/api.ts` na F7)."""
    assert not re.search(r"^\s*import\s", LIB.read_text(encoding="utf-8"), re.M)
