// Um React MÍNIMO — o suficiente para RENDERIZAR e CLICAR nos componentes da
// malha, e nada além disso.
//
// ── Por que ele existe (e por que não é "mais um runner") ───────────────────
// O repo não tem runner de JS: `ui-react/package.json` tem `dev`, `build` e
// `lint`, e acrescentar um significaria trazer dependência de REDE a um produto
// que faz deploy OFFLINE com wheels. O que já existe na casa (o
// `f4_front_harness.cjs`) transpila com o `sucrase` que o Vite traz e executa
// os módulos PUROS no Node — e é ótimo para funções puras.
//
// Só que METADE do aceite desta fase não mora em função pura: `Encerrar
// corrida…` existe em toda corrida ABERTA?, a confirmação diz que os pipelines
// CONTINUAM rodando?, o badge de `Agora` é neutro?, a barra de limite some sem
// `teto_horas`? Todas essas são perguntas sobre o que a tela RENDERIZA. Provar
// isso com `grep` no `.tsx` é exatamente o modo de falso verde que a F7 pagou:
// afirmar a MENSAGEM em vez do COMPORTAMENTO — o teste fica verde porque a
// string existe no arquivo, mesmo que ela esteja num ramo que nunca renderiza.
//
// `react-dom/server` sozinho não resolve: ele renderiza, mas não CLICA, e a
// confirmação do encerramento só existe depois do clique (estado interno
// `confirmando`). Sem jsdom no `node_modules` (não há, e instalar seria rede),
// o caminho honesto é este: ~150 linhas que rodam o componente REAL, byte a
// byte como está no `src/`, com hooks de verdade e um laço de re-render.
//
// ── O que ele NÃO é ────────────────────────────────────────────────────────
// Não é React. Não há reconciliação por `key`, `useEffect` não roda (efeito é
// browser, e nenhum aceite desta fase depende de um), não há portal nem
// contexto. Se um componente passar a depender de qualquer um deles, o teste
// QUEBRA em vez de mentir — que é o comportamento certo para uma bancada.
'use strict'

const FRAGMENT = Symbol.for('mini.fragment')

// Estado por caminho de componente. O caminho é estável entre renders porque
// os cenários são determinísticos (mesma árvore, mesma ordem): é o que permite
// o `useState` sobreviver ao re-render disparado por um clique.
let estados = new Map()
let caminho = []
let indiceHook = 0
let sujo = false

function celulas() {
  const chave = caminho.join('/')
  let c = estados.get(chave)
  if (!c) { c = []; estados.set(chave, c) }
  return c
}

function useState(inicial) {
  const c = celulas()
  const i = indiceHook++
  if (!(i in c)) c[i] = typeof inicial === 'function' ? inicial() : inicial
  const chave = caminho.join('/')
  const set = (v) => {
    const atual = estados.get(chave)
    const novo = typeof v === 'function' ? v(atual[i]) : v
    if (!Object.is(novo, atual[i])) { atual[i] = novo; sujo = true }
  }
  return [c[i], set]
}

function useRef(inicial) {
  const c = celulas()
  const i = indiceHook++
  if (!(i in c)) c[i] = { current: inicial }
  return c[i]
}

function useMemo(fn, deps) {
  const c = celulas()
  const i = indiceHook++
  const anterior = c[i]
  if (anterior && deps && anterior.deps && deps.length === anterior.deps.length
      && deps.every((d, k) => Object.is(d, anterior.deps[k]))) {
    return anterior.valor
  }
  const valor = fn()
  c[i] = { valor, deps }
  return valor
}

const useCallback = (fn, deps) => useMemo(() => fn, deps)
const useEffect = () => {}          // efeito é browser; nenhum aceite depende
const useLayoutEffect = () => {}

function criar(tipo, props, ...filhos) {
  const p = Object.assign({}, props)
  if (filhos.length) p.children = filhos.length === 1 ? filhos[0] : filhos
  return { __el: true, tipo, props: p }
}

// ── O render ───────────────────────────────────────────────────────────────
// Devolve uma árvore de nós de HOST (`{tag, props, filhos}`) — os componentes
// já foram executados. Texto vira string. `null`/`false` somem, como no React.
function renderizar(no, trilha) {
  if (no === null || no === undefined || no === false || no === true) return []
  if (typeof no === 'string' || typeof no === 'number') return [String(no)]
  if (Array.isArray(no)) {
    return no.flatMap((f, i) => renderizar(f, trilha.concat(`#${i}`)))
  }
  if (!no.__el) return []
  const { tipo, props } = no
  if (tipo === FRAGMENT) return renderizar(props.children, trilha)
  if (typeof tipo === 'function') {
    const nome = tipo.name || 'anon'
    const meu = trilha.concat(nome)
    const trilhaAnterior = caminho
    const hookAnterior = indiceHook
    caminho = meu
    indiceHook = 0
    let saida
    try {
      saida = tipo(props)
    } finally {
      caminho = trilhaAnterior
      indiceHook = hookAnterior
    }
    return renderizar(saida, meu)
  }
  // Host: preserva os handlers (é o que permite CLICAR) e desce nos filhos.
  const filhos = renderizar(props.children, trilha.concat(String(tipo)))
  return [{ tag: String(tipo), props, filhos }]
}

/** Monta uma árvore e devolve um punhado de sondas. O `clicar` re-renderiza
 *  enquanto houver estado sujo — o mesmo laço que o React faz por baixo. */
function montar(elemento) {
  estados = new Map()
  let arvore = renderizar(elemento, [])
  const refazer = () => { sujo = false; arvore = renderizar(elemento, []) }

  const todos = () => {
    const out = []
    const anda = (n) => {
      if (typeof n === 'string') { out.push(n); return }
      out.push(n)
      n.filhos.forEach(anda)
    }
    arvore.forEach(anda)
    return out
  }
  const texto = (n) => {
    if (typeof n === 'string') return n
    // Junta com espaço: no DOM real dois `<span>` irmãos não colam as palavras,
    // e uma régua que colasse acharia frases que a tela não mostra.
    return n.filhos.map(texto).join(' ').replace(/\s+/g, ' ').trim()
  }
  const api = {
    /** Todo o texto visível da tela, normalizado. */
    get texto() {
      return arvore.map(texto).join(' ').replace(/\s+/g, ' ').trim()
    },
    /** Nós de host que casam com o predicado. */
    achar(pred) {
      return todos().filter(n => typeof n !== 'string' && pred(n))
    },
    /** Botões, pelo texto que eles mostram. */
    botoes(rotulo) {
      return api.achar(n => n.tag === 'button'
        && (rotulo === undefined || texto(n).includes(rotulo)))
    },
    porPapel(papel) {
      return api.achar(n => n.props.role === papel)
    },
    clicar(no) {
      if (!no || !no.props.onClick) throw new Error('nó sem onClick')
      no.props.onClick({ target: {}, stopPropagation() {}, preventDefault() {} })
      let voltas = 0
      while (sujo && voltas++ < 20) refazer()
      return api
    },
  }
  return api
}

module.exports = {
  FRAGMENT, montar,
  hooks: { useState, useRef, useMemo, useCallback, useEffect, useLayoutEffect },
  criar,
}
