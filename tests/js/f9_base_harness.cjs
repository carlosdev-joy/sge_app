// Banco de provas dos COMPONENTES DE BASE da F9 (spec-malha-execucao.md §9.9,
// Decisões 71 e 75) — `ui/Progress`, `ui/Banner` e o `badgeTom` de `ui/Tabs`.
//
// Por que RENDERIZAR, e não só ler o fonte
// ────────────────────────────────────────
// O que a F9 entrega aqui é um punhado de ATRIBUTOS. `role="progressbar"`,
// `aria-valuenow`, `aria-valuemax`, `aria-label` e `aria-valuetext` ou estão no
// nó que o navegador monta, ou não estão — e um `grep` no `.tsx` prova apenas
// que as letras aparecem em algum lugar do arquivo, inclusive num comentário.
// Pior: o atributo mais importante desta fase é o `aria-valuetext`, cuja razão
// de existir é NEGATIVA (sem ele o leitor de tela converte valuenow/valuemax em
// percentual sozinho, e "4 de 7" vira "57%" — o percentual de contagem que a
// Decisão 56 proíbe em toda superfície). Prova de ausência quer a árvore, não o
// texto do arquivo.
//
// Como isto roda sem runner de JS: mesma técnica de `f4_front_harness.cjs` — o
// `sucrase` que o Vite já traz transpila os `.tsx` do `src/`, byte a byte, com
// o transform JSX CLÁSSICO apontando para um `__h` nosso. Esse `__h` não é
// React: devolve a árvore como objeto puro. É o suficiente porque os três
// componentes são funções de renderização sem hook e sem estado — e é
// exatamente por isso que eles nasceram assim.
//
// Saída: um JSON só, no stdout, consumido por `tests/test_ui_base_f9.py`.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react', 'src', 'components', 'ui')
const { transform } = require(path.join(RAIZ, 'ui-react', 'node_modules', 'sucrase'))

const MODULOS = ['Progress.tsx', 'Banner.tsx', 'Tabs.tsx']

// ── transpilação ────────────────────────────────────────────────────────────
// `production: true` tira o `__self`/`__source` que o sucrase injeta em modo
// dev — eles poluiriam a árvore com props que o navegador não recebe.
function preparar(destino) {
  for (const arquivo of MODULOS) {
    const fonte = fs.readFileSync(path.join(UI, arquivo), 'utf8')
    const js = transform(fonte, {
      transforms: ['typescript', 'jsx'],
      jsxRuntime: 'classic',
      jsxPragma: '__h',
      jsxFragmentPragma: '__Frag',
      production: true,
      filePath: arquivo,
    }).code
    const preambulo = "import { __h, __Frag } from './jsx.mjs'\n"
    fs.writeFileSync(path.join(destino, arquivo.replace(/\.tsx$/, '.mjs')),
                     preambulo + js)
  }
  fs.writeFileSync(path.join(destino, 'jsx.mjs'), `
export const __Frag = 'fragmento'
export function __h(tipo, props, ...filhos) {
  return {
    tipo: typeof tipo === 'function' ? (tipo.name || 'anonimo') : tipo,
    props: props || {},
    filhos: filhos.flat(Infinity).filter(f => f !== null && f !== undefined
                                              && f !== false),
  }
}
`)
}

// ── utilidades de árvore ────────────────────────────────────────────────────
function todosOsNos(no, saida = []) {
  if (!no || typeof no !== 'object') return saida
  saida.push(no)
  for (const f of no.filhos || []) todosOsNos(f, saida)
  return saida
}

/** Todo o TEXTO que a árvore renderiza — é sobre ele que se prova ausência. */
function textoDe(no, partes = []) {
  if (no === null || no === undefined || typeof no === 'boolean') return partes
  if (typeof no !== 'object') { partes.push(String(no)); return partes }
  for (const f of no.filhos || []) textoDe(f, partes)
  return partes
}

/** Árvore serializável: só `tipo`, `props` escalares e filhos. */
function comoJson(no) {
  if (no === null || no === undefined || typeof no === 'boolean') return null
  if (typeof no !== 'object') return String(no)
  const props = {}
  for (const [k, v] of Object.entries(no.props)) {
    if (k === 'children') continue
    if (typeof v === 'function') { props[k] = '[funcao]'; continue }
    props[k] = v
  }
  return { tipo: no.tipo, props, filhos: (no.filhos || []).map(comoJson) }
}

async function main() {
  const destino = fs.mkdtempSync(path.join(os.tmpdir(), 'f9base-'))
  preparar(destino)
  const P = await import(path.join(destino, 'Progress.mjs'))
  const B = await import(path.join(destino, 'Banner.mjs'))
  const T = await import(path.join(destino, 'Tabs.mjs'))

  const saida = {}
  // ⚠️ O sentinela é `__erro__`, e não `erro` como na bancada da F4: um dos
  // TONS do Banner se chama `erro`, e o cenário `banner_por_tom` publica um
  // objeto com essa chave. Com o sentinela antigo, quatro testes verdes viravam
  // "o cenário levantou" — o teste acusando exceção onde havia só um nome igual.
  const cenario = (nome, fn) => {
    try { saida[nome] = fn() } catch (e) {
      saida[nome] = { __erro__: String((e && e.stack) || e) }
    }
  }

  // Os segmentos na ordem FIXA do §9.2: verde · azul · hachurado · vazio.
  const segmentos = (ok, vivo, disp) => ([
    { chave: 'ok', valor: ok, cor: 'bg-green-500 dark:bg-green-500',
      rotulo: 'concluídos' },
    { chave: 'vivo', valor: vivo, cor: 'bg-blue-500 dark:bg-blue-400',
      rotulo: 'em execução', animado: true },
    { chave: 'dispensado', valor: disp, cor: '', rotulo: 'não rodam hoje',
      hachurado: true },
  ])

  const barra = (over) => P.Progress(Object.assign({
    segmentos: segmentos(4, 2, 1),
    total: 7,
    valorAtual: 4,
    ariaLabel: 'progresso da corrida de 04/08 da malha CARGA_DIARIA',
    altura: 'xs',
  }, over))

  // ══ Decisão 75 — a barra passa a existir para quem usa leitor de tela ════
  cenario('barra_da_corrida', () => {
    const raiz = barra({})
    const nos = todosOsNos(raiz)
    return {
      raiz: comoJson(raiz),
      // Os segmentos são desenho: quem fala pelo conjunto é o valuetext.
      filhos_escondidos: nos.slice(1).map(n => n.props['aria-hidden']),
      larguras: nos.slice(1).map(n => n.props.style.width),
      classes: nos.slice(1).map(n => n.props.className),
      hachurados: nos.slice(1).map(n => !!n.props.style.backgroundImage),
      titles: nos.slice(1).map(n => n.props.title),
      texto_renderizado: textoDe(raiz),
    }
  })

  // ══ Decisão 56 — nenhum percentual de CONTAGEM, em superfície nenhuma ════
  cenario('nada_de_percentual_no_que_e_lido', () => {
    const raiz = barra({})
    // O `%` legítimo vive só em `style.width` (é CSS, não é o que se lê).
    const props_lidas = {}
    for (const [k, v] of Object.entries(raiz.props)) {
      if (k === 'style' || k === 'className' || typeof v !== 'string') continue
      props_lidas[k] = v
    }
    return {
      valuetext: raiz.props['aria-valuetext'],
      arialabel: raiz.props['aria-label'],
      props_lidas,
      titles: todosOsNos(raiz).slice(1).map(n => n.props.title),
      texto_renderizado: textoDe(raiz),
    }
  })

  // ══ o valuetext PADRÃO — montado dos rótulos, e nunca um percentual ══════
  cenario('valuetext_padrao_sai_dos_rotulos', () => {
    const raiz = barra({ valorTexto: undefined })
    return { valuetext: raiz.props['aria-valuetext'] }
  })

  // ══ barra CHEIA não é "concluída" (F9, aceite 2) ═════════════════════════
  cenario('barra_cheia_nao_diz_concluida', () => {
    // 6 prontos + 1 dispensado = os 7 do snapshot. A barra fecha, e o estado
    // da corrida continua sendo ABERTA — quem escreve a frase é o chamador.
    const raiz = barra({ segmentos: segmentos(6, 0, 1), valorAtual: 6 })
    const nos = todosOsNos(raiz)
    return {
      valuetext: raiz.props['aria-valuetext'],
      valuenow: raiz.props['aria-valuenow'],
      valuemax: raiz.props['aria-valuemax'],
      soma_das_larguras: nos.slice(1)
        .reduce((s, n) => s + parseFloat(n.props.style.width), 0),
      tudo_que_se_le: [raiz.props['aria-valuetext'], raiz.props['aria-label'],
                       ...nos.slice(1).map(n => n.props.title),
                       ...textoDe(raiz)].join(' | '),
    }
  })

  // ══ o valuenow é o `x` do `x de y`, e não a soma dos segmentos ═══════════
  cenario('valuenow_nao_e_a_soma_dos_segmentos', () => {
    const raiz = barra({})
    const soma = segmentos(4, 2, 1).reduce((s, x) => s + x.valor, 0)
    return {
      valuenow: raiz.props['aria-valuenow'],
      valuemax: raiz.props['aria-valuemax'],
      soma_dos_segmentos: soma,
    }
  })

  // ══ guarda de NaN — `total = 0` não é um modo, é uma divisão proibida ════
  cenario('total_zero_nao_gera_NaN', () => {
    const raiz = barra({ total: 0, valorAtual: 0,
                         segmentos: segmentos(0, 0, 0) })
    const larguras = todosOsNos(raiz).slice(1).map(n => n.props.style.width)
    return { larguras, tem_nan: larguras.some(w => /NaN/.test(w)) }
  })

  // ══ segmento fora da faixa não vaza para fora do trilho ═════════════════
  cenario('segmento_maior_que_o_total_nao_estoura', () => {
    const raiz = barra({ segmentos: [{ chave: 'ok', valor: 99, cor: 'bg-green-500',
                                       rotulo: 'concluídos' }], valorAtual: 99 })
    return { largura: todosOsNos(raiz)[1].props.style.width }
  })

  // ══ a ordem é do CHAMADOR: o componente nunca reordena (§9.2) ═══════════
  cenario('a_ordem_e_a_do_array', () => {
    const invertido = segmentos(4, 2, 1).slice().reverse()
    const raiz = barra({ segmentos: invertido })
    return { chaves: todosOsNos(raiz).slice(1).map(n => n.props.title) }
  })

  cenario('altura_muda_o_trilho_e_os_segmentos', () => {
    const cartao = barra({ altura: 'xs' })
    const painel = barra({ altura: 'sm' })
    return {
      xs: { raiz: cartao.props.className,
            seg: todosOsNos(cartao)[1].props.className },
      sm: { raiz: painel.props.className,
            seg: todosOsNos(painel)[1].props.className },
    }
  })

  // ══ ui/Banner — PROMOÇÃO: os três tons de origem, byte a byte ═══════════
  cenario('banner_por_tom', () => {
    const out = {}
    for (const tom of ['info', 'alerta', 'erro', 'sucesso']) {
      const raiz = B.Banner({ tom, icone: 'ICONE', children: 'texto do aviso' })
      out[tom] = comoJson(raiz)
    }
    return out
  })

  cenario('banner_sem_acao_tem_a_forma_do_original', () => {
    const raiz = B.Banner({ tom: 'info', icone: 'ICONE', children: 'aviso' })
    return { comojson: comoJson(raiz), qtd_filhos: raiz.filhos.length }
  })

  cenario('banner_com_acao_encosta_a_direita', () => {
    const raiz = B.Banner({ tom: 'alerta', icone: 'ICONE', acao: 'BOTAO',
                            children: 'aviso' })
    return { comojson: comoJson(raiz), qtd_filhos: raiz.filhos.length }
  })

  cenario('banner_sem_icone_nao_quebra', () => {
    const raiz = B.Banner({ tom: 'erro', children: 'aviso sem icone' })
    return { comojson: comoJson(raiz), texto: textoDe(raiz) }
  })

  // ══ ui/Tabs — `badgeTom` (o "Agora (2)" que não pode sair vermelho) ═════
  const abas = (over) => T.Tabs({
    tabs: [
      { id: 'agora', label: 'Agora', badge: 2, badgeTom: 'neutro' },
      { id: 'travando', label: 'Travando', badge: 2, badgeTom: 'alerta' },
      { id: 'eventos', label: 'Eventos', badge: 3 },   // sem tom = como hoje
      { id: 'vazia', label: 'Vazia', badge: 0 },
    ],
    active: 'agora',
    onChange: () => {},
    ...over,
  })

  cenario('badge_por_tom', () => {
    const nos = todosOsNos(abas({}))
    const badges = nos.filter(n => n.tipo === 'span'
      && String(n.props.className || '').includes('rounded-full'))
    return {
      qtd: badges.length,
      classes: badges.map(n => n.props.className),
      textos: badges.map(n => textoDe(n).join('')),
    }
  })

  cenario('badge_zero_nao_aparece', () => {
    const nos = todosOsNos(abas({}))
    return { textos: nos.filter(n => n.tipo === 'button')
      .map(n => textoDe(n).join('')) }
  })

  process.stdout.write(JSON.stringify(saida))
  fs.rmSync(destino, { recursive: true, force: true })
}

main().catch(e => {
  process.stderr.write(String((e && e.stack) || e))
  process.exit(1)
})
