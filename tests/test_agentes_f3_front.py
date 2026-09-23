"""Tela `/agentes` (F3 da spec docs/spec-agentes-datastage.md) — o que o
fonte do front precisa garantir.

Leitura por regex sobre o TypeScript, como `test_rbac_recursos_admin.py` já
faz: o repo não tem runtime de teste para React, e o que prendemos aqui são
propriedades estáticas do fonte — se uma delas cair, a tela quebra de um
jeito que nenhum teste de Python de API pegaria.

O que cada bloco prende, e por quê:

  1. **A rota existe de fato** — `lib/nav.ts` já declarava o item `/agentes`
     desde a F1, mas sem `PAGE_ELEMENT` em `App.tsx` clicar nele caía no
     catch-all (`HomeRedirect`), ou seja: menu que não leva a lugar nenhum.

  2. **Critério 3 — `sem_cadastro` × `gateway_indisponivel`**: só o primeiro
     mostra o texto configurável de "peça seu cadastro". Mandar alguém abrir
     chamado de cadastro porque a REDE caiu é despachar para a fila errada.
     A API já não devolve o texto nesse caso (test_agentes_f3_api.py); aqui
     prendemos o outro lado — o componente também decide pela AÇÃO do estado,
     não por "veio texto, então mostro".

  3. **Critério 4 — acessibilidade e tokens**: `aria-live="polite"` na lista
     de mensagens (a resposta é anunciada sem roubar o foco de quem digita) e
     nenhuma cor de superfície fora dos tokens `canvas/panel/edge/ink/dim`.
     Cor utilitária solta (`bg-yellow-50`) fica ilegível no escuro — é a
     lição que `docs/ui-temas-cores.md` registra.

  4. **Critério 6 — CSS que já mordeu este projeto**: `overflow-hidden` em
     ancestral de `sticky` mata o sticky em silêncio, e `*/` dentro de
     comentário CSS quebra o lightningcss no build.

  5. **A armadilha do `user_perm_set`**: ele SUBSTITUI a lista inteira de
     permissões extras. A aba do Admin tem de ler as atuais e reenviar o
     conjunto — mandar só o recurso do agente apagaria as outras permissões
     extras do usuário, em silêncio.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FRONT = RAIZ / "ui-react" / "src"

PAGINA = FRONT / "pages" / "Agentes.tsx"
CHAT = FRONT / "components" / "agentes" / "ChatAgente.tsx"
AVISO = FRONT / "components" / "agentes" / "AvisoSonda.tsx"
GRAFO = FRONT / "components" / "agentes" / "GrafoJobAgente.tsx"
LIB = FRONT / "lib" / "agentes.ts"
ADMIN_TAB = FRONT / "components" / "admin" / "AgentesTab.tsx"
APP = FRONT / "App.tsx"
ADMIN = FRONT / "pages" / "Admin.tsx"

ARQUIVOS_DA_TELA = [PAGINA, CHAT, AVISO, GRAFO,
                    FRONT / "components" / "agentes" / "IndicadorProjeto.tsx",
                    FRONT / "components" / "agentes" / "MarkdownAgente.tsx"]


def ler(p: Path) -> str:
    assert p.exists(), f"arquivo da F3 não existe: {p.relative_to(RAIZ)}"
    return p.read_text(encoding="utf-8")


def codigo(p: Path) -> str:
    """O fonte SEM comentários — as regras abaixo falam do que o componente
    FAZ, não do que ele explica. Estes arquivos documentam no cabeçalho
    justamente o que evitam (`overflow-hidden`, as cores fixas da bolha do
    Caixa), e um teste que lesse o comentário acusaria o contrário do que
    está escrito nele.

    Só linhas de comentário INTEIRAS e blocos `/* */`: um `//` no meio de uma
    linha poderia ser `https://`, e recortar ali comeria código de verdade."""
    fonte = re.sub(r"/\*.*?\*/", " ", ler(p), flags=re.S)
    return "\n".join(l for l in fonte.splitlines() if not l.strip().startswith("//"))


# ═══════════ 1. a rota existe ════════════════════════════════════════════

def test_rota_agentes_registrada_no_app():
    fonte = ler(APP)
    assert re.search(r"import\s+Agentes\s+from\s+'\./pages/Agentes'", fonte), \
        "App.tsx não importa a página Agentes"
    assert re.search(r"'/agentes':\s*<Agentes\s*/>", fonte), \
        "App.tsx não tem PAGE_ELEMENT['/agentes'] — o item do menu cairia no catch-all"


def test_item_do_menu_continua_pedindo_tela_agentes():
    nav = ler(FRONT / "lib" / "nav.ts")
    assert re.search(r"to:\s*'/agentes'[^}]*perm:\s*'tela_agentes'", nav), \
        "o item /agentes precisa continuar exigindo tela_agentes"


def test_aba_do_admin_registrada():
    fonte = ler(ADMIN)
    assert "import { AgentesTab }" in fonte
    assert re.search(r"\{\s*id:\s*'agentes',\s*label:\s*'Agentes'\s*\}", fonte), \
        "a aba 'agentes' não está em ADMIN_GROUPS"
    assert re.search(r"tab\s*===\s*'agentes'\s*&&\s*<AgentesTab\s*/>", fonte), \
        "a aba 'agentes' não é renderizada"


# ═══════════ 2. critério 3 — cadastro × gateway indisponível ═════════════

def test_apenas_sem_cadastro_tem_acao_de_cadastro():
    """Na tabela SONDA, `acao: 'cadastro'` é o que libera o texto do Admin.
    Se outro estado ganhasse essa ação, o aviso de cadastro apareceria onde
    não deve."""
    lib = ler(LIB)
    estados_com_cadastro = re.findall(r"^\s{2}(\w+):\s*\{[^}]*?acao:\s*'cadastro'",
                                      lib, re.M | re.S)
    assert estados_com_cadastro == ["sem_cadastro"], \
        f"só sem_cadastro pode ter acao 'cadastro'; achei {estados_com_cadastro}"


def test_gateway_indisponivel_nao_fala_em_cadastro():
    lib = ler(LIB)
    bloco = re.search(r"gateway_indisponivel:\s*\{(.*?)\n  \},", lib, re.S)
    assert bloco, "estado gateway_indisponivel sumiu de SONDA"
    texto = bloco.group(1).lower()
    assert "não é preciso solicitar cadastro" in texto, \
        "o texto de gateway_indisponivel deve dizer explicitamente que não é caso de cadastro"
    assert "bloqueia: true" in texto, "gateway indisponível precisa bloquear a conversa"


def test_aviso_usa_o_texto_do_admin_so_na_acao_de_cadastro():
    """O componente decide pela AÇÃO, não por 'veio texto na resposta'."""
    fonte = ler(AVISO)
    assert re.search(r"info\.acao\s*===\s*'cadastro'\s*\n?\s*\?\s*\(cadastroTexto", fonte), \
        "AvisoSonda deve usar `cadastroTexto` apenas quando info.acao === 'cadastro'"


# ═══════════ 3. critério 4 — acessibilidade e tokens ═════════════════════

def test_chat_anuncia_a_resposta_sem_roubar_o_foco():
    fonte = ler(CHAT)
    assert 'aria-live="polite"' in fonte, "a lista de mensagens precisa de aria-live polite"
    assert "aria-busy={enviando}" in fonte
    # O foco volta ao campo quando a resposta chega (enviando: true -> false).
    assert "campoRef.current?.focus()" in fonte


def test_campo_e_botao_do_chat_tem_rotulo_acessivel():
    fonte = ler(CHAT)
    assert 'aria-label="Sua pergunta"' in fonte
    assert 'aria-label="Enviar pergunta"' in fonte


# Cor de superfície fora dos tokens: `bg-`/`text-`/`border-` com uma cor
# nomeada do Tailwind e SEM par `dark:` logo em seguida. O azul da marca
# (#1A5FA8) é exceção conhecida do projeto e sempre aparece com par dark.
_COR_UTIL = re.compile(r"\b(bg|text|border)-(slate|gray|zinc|neutral|stone|white|black)"
                       r"(-\d{2,3})?\b")


def test_tela_nao_usa_cor_de_superficie_fora_dos_tokens():
    for arq in ARQUIVOS_DA_TELA:
        fonte = codigo(arq)
        # `text-white` é aceito DENTRO da bolha azul da marca (contraste sobre
        # #1A5FA8); qualquer outra cor de superfície tem de ser token.
        achados = [m.group(0) for m in _COR_UTIL.finditer(fonte)
                   if m.group(0) != "text-white"]
        assert not achados, f"{arq.name}: cor fora dos tokens: {sorted(set(achados))}"


def test_acentos_de_tom_do_aviso_tem_par_claro_escuro():
    """As cores de TOM (âmbar/vermelho/verde) são permitidas, mas nunca sem o
    par `dark:` — senão o aviso some no tema escuro."""
    fonte = ler(AVISO)
    for m in re.finditer(r"'([^']*?(amber|red|emerald)[^']*?)'", fonte):
        trecho = m.group(1)
        claras = re.findall(r"(?<!dark:)\b(?:border-l|text)-(?:amber|red|emerald)-\d{3}", trecho)
        escuras = re.findall(r"dark:(?:border-l|text)-(?:amber|red|emerald)-\d{3}", trecho)
        assert len(escuras) >= len(claras), f"tom sem par dark: {trecho}"


# ═══════════ 4. critério 6 — CSS que já mordeu este projeto ══════════════

def test_sem_overflow_hidden_na_tela_do_agente():
    """`overflow-hidden` em ancestral mata `position: sticky` em silêncio —
    o chat rola numa caixa própria (`overflow-y-auto`), e nenhum container
    acima dela pode esconder o overflow."""
    for arq in ARQUIVOS_DA_TELA:
        fonte = codigo(arq)
        assert "overflow-hidden" not in fonte, \
            f"{arq.name}: overflow-hidden pode matar o sticky do cabeçalho"


def test_sem_fim_de_comentario_css_dentro_de_comentario():
    """`*/` dentro de um comentário CSS quebra o lightningcss no build."""
    for arq in ARQUIVOS_DA_TELA + [ADMIN_TAB, LIB]:
        fonte = ler(arq)
        for linha in fonte.splitlines():
            if linha.strip().startswith("//"):
                continue
            assert linha.count("*/") <= 1, f"{arq.name}: '*/' repetido em {linha.strip()[:60]}"


# ═══════════ 5. a armadilha do user_perm_set ═════════════════════════════

def test_admin_le_as_permissoes_atuais_antes_de_conceder():
    """`user_perm_set` substitui a lista inteira: conceder um agente mandando
    só `[recurso]` apagaria as outras permissões extras do usuário."""
    fonte = ler(ADMIN_TAB)
    assert "perms.data?.permissoes?.[matricula]" in fonte, \
        "a aba precisa ler as permissões ATUAIS antes de reenviar"
    assert re.search(r"adminPost\('user_perm_set',\s*\{\s*matricula,\s*permissoes:\s*\[\.\.\.atuais\]",
                     fonte), "user_perm_set deve receber o conjunto completo, não só o recurso novo"


def test_admin_so_oferece_perfis_elegiveis_vindos_do_backend():
    """A lista de quem pode receber o agente vem de `perfis_elegiveis` da
    API — nunca de uma lista repetida à mão no front (ver
    tests/test_rbac_recursos_admin.py para o preço dessa duplicação)."""
    fonte = ler(ADMIN_TAB)
    assert "ag.perfis_elegiveis.includes(u.perfil)" in fonte
    assert "'desenvolvedor'" not in fonte, \
        "perfil elegível não pode estar escrito à mão na aba — vem do backend"


# ═══════════ 6. grafo: reaproveita o da Governança ═══════════════════════

def test_grafo_reaproveita_o_componente_da_governanca():
    """Critério 5 da F3: o grafo é o MESMO da Governança, alimentado pelo
    mesmo endpoint de banco — nada de um segundo desenho para manter."""
    fonte = ler(GRAFO)
    assert "from '../governanca/isx/GrafoIsx'" in fonte
    assert "/lineage/isx/job?pipeline_name=" in fonte
    # `key` no GrafoIsx: sem ele o fitView não roda de novo ao trocar de job.
    assert re.search(r"<GrafoIsx\s+key=", fonte), \
        "GrafoIsx precisa de key por job, senão herda o zoom do job anterior"
