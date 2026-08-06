"""
F9 da spec `docs/spec-malha-execucao.md` — os COMPONENTES DE BASE (§9.9,
Decisões 71 e 75), provados RENDERIZADOS.

O que esta suíte guarda, e por que cada coisa é um teste
────────────────────────────────────────────────────────
1. **A barra passa a existir para quem usa leitor de tela.** O produto tinha
   quatro barras ad-hoc (`CopiaProgressoModal.tsx:125`, `Dashboard.tsx:448`,
   `PlanosAjuste.tsx:36`, `Admin.tsx:2064`) e NENHUMA com `role="progressbar"`,
   `aria-valuenow`, `aria-valuemax` ou `aria-label`: para o leitor de tela as
   quatro eram `div` vazias.

2. **O `aria-valuetext`, que é a metade da Decisão 56 que quase escapa.**
   `role="progressbar"` com `aria-valuenow=4` e `aria-valuemax=7` faz o leitor
   de tela CALCULAR e anunciar "57%" por conta própria. Seria o percentual de
   contagem de pipelines — proibido "em superfície nenhuma" — entrando pela
   porta da acessibilidade, invisível em qualquer inspeção visual. O
   `aria-valuetext` existe para calar esse cálculo, e por isso ele é testado
   como AUSÊNCIA de `%` em tudo que é lido.

3. **Barra cheia não é "concluída".** Corrida `ABERTA` com todos os membros OK
   ainda está fechando; a barra fecha, o vocabulário não muda. É teste de
   ausência das palavras `100%` e `concluída` — e note que `concluídos`, no
   masculino plural, é o vocabulário CORRETO da spec ("4 de 7 pipelines
   concluídos"): o que não pode aparecer é o feminino, que descreve a CORRIDA.

4. **A promoção do `Banner` preserva o original.** As classes dos três tons são
   comparadas byte a byte com as que estavam em
   `components/etapas/PainelExecucaoEtapas.tsx:252-268` — se a promoção mudar
   um par claro+escuro, quatro avisos que já estão em produção mudam de cor.

5. **`Agora (2)` não sai vermelho.** `Tabs` pintava TODO badge de vermelho.

── Como isto roda sem runner de JS ─────────────────────────────────────────
Mesma técnica de `test_malhas_f4_front.py`: o `sucrase` que o Vite já traz
transpila os `.tsx` do `src/` (transform JSX clássico apontando para um `__h`
nosso, que devolve a árvore como objeto puro), e o Node executa. Os três
componentes são funções de renderização sem hook e sem estado — é por isso que
dá para chamá-los direto.

⚠️ Um `grep` no fonte NÃO serviria aqui: ele casaria as letras `aria-valuenow`
dentro de um comentário. O que a fase entrega são atributos no nó, e nó só
existe renderizado.

Sem Node ou sem `node_modules` a suíte SALTA em vez de falhar — visível no
`-rs`, nunca silenciosa.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HARNESS = RAIZ / "tests" / "js" / "f9_base_harness.cjs"
UI = RAIZ / "ui-react" / "src" / "components" / "ui"
SUCRASE = RAIZ / "ui-react" / "node_modules" / "sucrase"

_MOTIVO_SALTO = ("front não instalado nesta máquina (node ≥ 18 ou "
                 "ui-react/node_modules/sucrase ausente) — os testes de "
                 "contrato do fonte continuam valendo")
_MAJOR_MINIMO = 18


def _node() -> str | None:
    caminho = shutil.which("node")
    if not caminho or not SUCRASE.is_dir():
        return None
    try:
        v = subprocess.run([caminho, "-v"], capture_output=True, text=True,
                           timeout=30).stdout.strip()
        return caminho if int(v.lstrip("v").split(".")[0]) >= _MAJOR_MINIMO \
            else None
    except Exception:      # noqa: BLE001 — sonda de ambiente degrada em salto
        return None


@pytest.fixture(scope="module")
def base() -> dict:
    node = _node()
    if node is None:
        pytest.skip(_MOTIVO_SALTO)
    r = subprocess.run([node, str(HARNESS)], capture_output=True, text=True,
                       cwd=str(RAIZ), timeout=120)
    assert r.returncode == 0, f"bancada do front falhou:\n{r.stderr}"
    return json.loads(r.stdout)


def _cenario(base: dict, nome: str) -> dict:
    """Cenário que levantou vira ESTE teste vermelho, não a suíte inteira.

    ⚠️ O sentinela é `__erro__`, e não `erro` como na bancada da F4: um dos
    TONS do `Banner` se chama `erro`, e o cenário que percorre os quatro tons
    publica um dicionário com essa chave. Foi a própria suíte que pegou — com o
    sentinela antigo ela acusava "o cenário levantou" em quatro testes que
    estavam certos."""
    dado = base[nome]
    assert "__erro__" not in dado, \
        f"{nome} levantou no front:\n{dado.get('__erro__')}"
    return dado


# ═══════ 1. os atributos que faltavam nas quatro barras do produto ══════════

def test_a_barra_tem_os_quatro_atributos_que_nenhuma_das_quatro_tinha(base):
    """Decisão 75, o aceite literal da F9: `role="progressbar"`,
    `aria-valuenow`, `aria-valuemax` e `aria-label` em pt-BR."""
    p = _cenario(base, "barra_da_corrida")["raiz"]["props"]
    assert p["role"] == "progressbar"
    assert p["aria-valuenow"] == 4
    assert p["aria-valuemin"] == 0
    assert p["aria-valuemax"] == 7
    assert p["aria-label"] == "progresso da corrida de 04/08 da malha CARGA_DIARIA"
    # pt-BR de verdade, com acentuação — não é "progress" nem "progresso" solto
    assert "corrida" in p["aria-label"]


def test_os_segmentos_nao_falam_sozinhos(base):
    """Sem `aria-hidden` nos pedaços, o leitor recitaria fragmentos soltos
    dentro de um `progressbar`. Quem fala pelo conjunto é o `aria-valuetext`;
    o `title` continua servindo o mouse."""
    d = _cenario(base, "barra_da_corrida")
    assert d["filhos_escondidos"] == ["true", "true", "true"]
    assert d["titles"] == ["4 concluídos", "2 em execução", "1 não rodam hoje"]
    # a barra não imprime NENHUM texto: ela é desenho + atributo
    assert d["texto_renderizado"] == []


def test_o_valuenow_e_o_x_do_x_de_y_e_nao_a_soma_dos_segmentos(base):
    """A prop é explícita de propósito. A soma dos segmentos (4 prontos + 2
    rodando + 1 dispensado) daria 7 de 7 — o leitor de tela contaria uma
    corrida terminada onde a tela mostra 4 de 7."""
    d = _cenario(base, "valuenow_nao_e_a_soma_dos_segmentos")
    assert d["soma_dos_segmentos"] == 7        # a armadilha existe...
    assert d["valuenow"] == 4                  # ...e o componente não cai nela
    assert d["valuemax"] == 7


# ═══════ 2. Decisão 56 — nenhum percentual de CONTAGEM, em lugar nenhum ═════

def test_o_leitor_de_tela_nao_anuncia_percentual(base):
    """A armadilha silenciosa desta fase.

    `role="progressbar"` + `aria-valuenow`/`aria-valuemax` faz NVDA e JAWS
    derivarem e anunciarem "57%" sozinhos. Seria exatamente o percentual de
    contagem de pipelines que a Decisão 56 proíbe — entrando por um canal que
    nenhuma inspeção visual pega. Quem cala esse cálculo é o `aria-valuetext`,
    e a prova é a ausência de `%` em tudo que é lido."""
    d = _cenario(base, "nada_de_percentual_no_que_e_lido")
    assert d["valuetext"], "sem aria-valuetext o leitor volta a calcular o %"
    lido = " | ".join([d["valuetext"], d["arialabel"], *d["titles"],
                       *d["texto_renderizado"], *d["props_lidas"].values()])
    assert "%" not in lido, f"percentual vazou para o que é lido: {lido}"
    assert "57" not in lido


def test_o_valuetext_padrao_lidera_pelo_x_de_y(base):
    """Sem `valorTexto` o componente monta o texto sozinho — e o default tem de
    ser tão honesto quanto o explícito: `x de y` primeiro (o número primário da
    Decisão 56), detalhe por segmento depois, `%` nunca."""
    t = _cenario(base, "valuetext_padrao_sai_dos_rotulos")["valuetext"]
    assert t.startswith("4 de 7")
    assert "%" not in t
    assert "concluídos" in t and "em execução" in t


# ═══════ 3. barra CHEIA não é "concluída" (aceite 2 da F9) ══════════════════

def test_barra_cheia_nao_diz_100_por_cento_nem_concluida(base):
    """Corrida `ABERTA` com todos os membros do snapshot resolvidos: a barra
    fecha (soma 100 de largura, que é CSS) e nem por isso o vocabulário muda —
    a corrida ainda está fechando.

    Teste de AUSÊNCIA. `concluídos`, masculino plural, é o vocabulário correto
    da spec para PIPELINES ("4 de 7 pipelines concluídos"); o que não pode
    aparecer é `concluída`, que descreve a CORRIDA, e `100%`."""
    d = _cenario(base, "barra_cheia_nao_diz_concluida")
    assert abs(d["soma_das_larguras"] - 100) < 1e-9   # o desenho fecha
    lido = d["tudo_que_se_le"]
    assert "100%" not in lido
    assert "%" not in lido
    # com e sem acento — "concluida" escrito torto continua sendo a palavra
    sem_acento = lido.lower().replace("í", "i")
    assert "concluída" not in lido and "concluida" not in sem_acento
    # o valuenow continua sendo 6, e não 7: um membro não rodou hoje
    assert d["valuenow"] == 6 and d["valuemax"] == 7


# ═══════ 4. as guardas de aritmética ════════════════════════════════════════

def test_total_zero_nao_vira_NaN_na_largura(base):
    """`total === 0` não é um modo com texto próprio (Decisão 71 — modo sem
    chamador não entra): é uma divisão que não pode acontecer. O trilho fica
    vazio, e `width: NaN%` nunca chega ao DOM."""
    d = _cenario(base, "total_zero_nao_gera_NaN")
    assert d["tem_nan"] is False
    assert d["larguras"] == ["0%", "0%", "0%"]


def test_segmento_maior_que_o_total_nao_estoura_o_trilho(base):
    d = _cenario(base, "segmento_maior_que_o_total_nao_estoura")
    assert d["largura"] == "100%"


def test_a_ordem_dos_segmentos_e_a_do_chamador(base):
    """§9.2: a composição tem ordem FIXA e ela nunca reordena entre refreshes.
    Quem fixa é o chamador; o componente não pode ter opinião — se ele
    ordenasse por conta própria, a barra mudaria de desenho a cada refetch."""
    d = _cenario(base, "a_ordem_e_a_do_array")
    assert d["chaves"] == ["1 não rodam hoje", "2 em execução", "4 concluídos"]


def test_so_o_segmento_marcado_anima_e_so_o_marcado_e_hachurado(base):
    """Decisão 75: `animate-pulse` semântico e escasso. §9.15/16: hachura
    significa UMA coisa — "não roda hoje"."""
    d = _cenario(base, "barra_da_corrida")
    assert [("animate-pulse" in c) for c in d["classes"]] == [False, True, False]
    assert d["hachurados"] == [False, False, True]


def test_as_duas_alturas_valem_para_trilho_e_segmento(base):
    """`xs` no card, `sm` no painel. A altura tem de descer para o segmento
    também: um filho com altura diferente do trilho deixa faixa vazia."""
    d = _cenario(base, "altura_muda_o_trilho_e_os_segmentos")
    assert "h-1.5" in d["xs"]["raiz"] and "h-1.5" in d["xs"]["seg"]
    assert "h-2.5" in d["sm"]["raiz"] and "h-2.5" in d["sm"]["seg"]


# ═══════ 5. ui/Banner — PROMOÇÃO, e não reescrita ═══════════════════════════

# As classes literais de `PainelExecucaoEtapas.tsx:252-268`, antes da promoção.
# Se a promoção mudar uma vírgula aqui, quatro avisos que já estão em produção
# no canvas de Etapas mudam de cor sem que ninguém tenha pedido.
CLASSES_ORIGINAIS = {
    "erro": "border-red-200 bg-red-50 text-red-700 "
            "dark:border-red-800 dark:bg-red-900/20 dark:text-red-300",
    "alerta": "border-amber-200 bg-amber-50 text-amber-700 "
              "dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400",
    "info": "border-blue-200 bg-blue-50 text-blue-800 "
            "dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-200",
}
ENVELOPE_ORIGINAL = "flex items-start gap-2 border-b px-3 py-2 text-[12px]"


@pytest.mark.parametrize("tom", sorted(CLASSES_ORIGINAIS))
def test_os_tres_tons_de_origem_saem_byte_a_byte(base, tom):
    d = _cenario(base, "banner_por_tom")[tom]
    assert d["props"]["className"] == f"{ENVELOPE_ORIGINAL} {CLASSES_ORIGINAIS[tom]}"


def test_o_tom_sucesso_entra_com_par_claro_e_escuro(base):
    """O único acréscimo de cor da promoção (§9.9). A regra da casa continua:
    nada de `bg-{hue}-900/20` sem o claro correspondente
    (docs/ui-temas-cores.md:63-82)."""
    cls = _cenario(base, "banner_por_tom")["sucesso"]["props"]["className"]
    for base_, escuro in (("border-green-200", "dark:border-green-800"),
                          ("bg-green-50", "dark:bg-green-900/20"),
                          ("text-green-700", "dark:text-green-300")):
        assert base_ in cls and escuro in cls


def test_sem_acao_a_arvore_e_a_mesma_de_antes(base):
    """`icone` + `<span>` cru, nesta ordem, e nada mais — a forma exata do
    original. O alinhamento da ação nova é feito por `ml-auto` NELA, e não
    mexendo no fluxo do texto, justamente para que este teste continue
    valendo."""
    d = _cenario(base, "banner_sem_acao_tem_a_forma_do_original")
    assert d["qtd_filhos"] == 2
    filhos = d["comojson"]["filhos"]
    assert filhos[0] == "ICONE"
    assert filhos[1]["tipo"] == "span"
    assert filhos[1]["props"] == {}          # o span do texto segue sem classe


def test_com_acao_ela_encosta_a_direita_sem_encolher(base):
    d = _cenario(base, "banner_com_acao_encosta_a_direita")
    assert d["qtd_filhos"] == 3
    acao = d["comojson"]["filhos"][2]
    assert "ml-auto" in acao["props"]["className"]
    assert "shrink-0" in acao["props"]["className"]


def test_o_icone_virou_opcional_e_a_ausencia_nao_quebra(base):
    """O original exigia `icone`; a versão de `ui/` não. Os quatro chamadores
    de hoje continuam passando — o que muda é que os banners da malha podem
    não ter."""
    d = _cenario(base, "banner_sem_icone_nao_quebra")
    assert d["texto"] == ["aviso sem icone"]
    assert len(d["comojson"]["filhos"]) == 1


def test_o_banner_local_saiu_do_painel_de_etapas(base):
    """Promoção é MOVER. Se a cópia local sobreviver, a duplicação que a
    Decisão 71 existe para matar continua de pé — só que agora com dois
    lugares para consertar."""
    fonte = (RAIZ / "ui-react" / "src" / "components" / "etapas"
             / "PainelExecucaoEtapas.tsx").read_text(encoding="utf-8")
    assert "function Banner(" not in fonte
    assert "from '../ui/Banner'" in fonte


# ═══════ 6. ui/Tabs — o `Agora (2)` que não pode sair vermelho ══════════════

def test_o_badge_neutro_nao_e_vermelho_e_o_de_alerta_continua_sendo(base):
    """Antes desta fase TODO badge de aba era vermelho (`Tabs.tsx:26-28`).
    `Agora (2)` — dois pipelines saudáveis rodando — sairia gritando "2
    problemas" às 3h."""
    neutro, alerta, _ = _cenario(base, "badge_por_tom")["classes"]
    assert "red" not in neutro, f"o badge neutro saiu vermelho: {neutro}"
    assert "bg-edge/60" in neutro and "text-dim" in neutro
    assert "bg-red-100" in alerta and "dark:bg-red-900/50" in alerta


def test_quem_nao_declara_tom_continua_vermelho(base):
    """O default é `alerta` DE PROPÓSITO. O único badge que existe hoje é
    "Erros e avisos" do DsConsole (`DsConsole.tsx:1012`), onde o número É o
    problema: mudar o padrão para neutro apagaria a cor de um contador de
    falhas sem ninguém ter pedido."""
    _, _, sem_tom = _cenario(base, "badge_por_tom")["classes"]
    assert "bg-red-100" in sem_tom


def test_badge_zero_continua_sem_aparecer(base):
    """Comportamento de hoje, preservado: `badge: 0` não desenha bolinha —
    "Vazia" sai sem contador, e não com um `0` cinza."""
    textos = _cenario(base, "badge_zero_nao_aparece")["textos"]
    assert textos == ["Agora2", "Travando2", "Eventos3", "Vazia"]
