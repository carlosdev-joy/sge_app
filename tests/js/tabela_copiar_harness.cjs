// Bancada da tabela de chamados e do botão de copiar o número.
//
// ⚠️ POR QUE RENDERIZA
// O que a F1 entrega é ALINHAMENTO: a célula vazia continua ocupando a coluna.
// Isso não se afirma lendo o `.tsx` — a lista antiga também "tinha" uma coluna
// de responsável no fonte; ela só sumia quando o prazo faltava. E o que a F2
// entrega é o comportamento do clique, inclusive quando a API do navegador não
// existe — que é o caso do próprio Node aqui.
//
// Saída: um JSON só no stdout.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const SRC = path.join(UI, 'src')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADAS = [
  'components/chamados/TabelaChamados.tsx',
  'components/chamados/NumeroChamado.tsx',
  'components/chamados/FiltroResponsaveis.tsx',
  'lib/copiar.ts',
  'lib/tabelaChamados.ts',
  'lib/filtroResponsaveis.ts',
  'lib/filtrosKanban.ts',
]

function resolverRelativo(deDir, especificador) {
  const base = path.resolve(deDir, especificador)
  for (const t of [base + '.tsx', base + '.ts',
                   path.join(base, 'index.tsx'), path.join(base, 'index.ts')]) {
    if (fs.existsSync(t)) return t
  }
  return null
}

function preparar(destino) {
  const feitos = new Set()
  const fila = ENTRADAS.map(e => path.join(SRC, e))
  while (fila.length) {
    const arquivo = fila.pop()
    if (feitos.has(arquivo)) continue
    feitos.add(arquivo)
    const fonte = fs.readFileSync(arquivo, 'utf8')
    const js = transform(fonte, {
      transforms: ['typescript', 'jsx', 'imports'],
      jsxRuntime: 'automatic', production: true, filePath: arquivo,
    }).code
    const rel = path.relative(SRC, arquivo).replace(/\.tsx?$/, '.js')
    const alvo = path.join(destino, rel)
    fs.mkdirSync(path.dirname(alvo), { recursive: true })
    fs.writeFileSync(alvo, js)
    for (const m of fonte.matchAll(/from\s*['"](\.[^'"]+)['"]/g)) {
      const dep = resolverRelativo(path.dirname(arquivo), m[1])
      if (dep) fila.push(dep)
    }
  }
}

function shims(destino) {
  const nm = path.join(destino, 'node_modules')
  const escrever = (pacote, arquivo, conteudo) => {
    const dir = path.join(nm, pacote)
    fs.mkdirSync(dir, { recursive: true })
    fs.writeFileSync(path.join(dir, arquivo), conteudo)
  }
  const caminhoMini = JSON.stringify(path.join(__dirname, 'minireact.cjs'))
  escrever('react', 'package.json', '{"name":"react","main":"index.js"}')
  escrever('react', 'index.js', `
const mini = require(${caminhoMini})
module.exports = Object.assign({}, mini.hooks, {
  createElement: mini.criar, Fragment: mini.FRAGMENT,
})
module.exports.default = module.exports
`)
  const runtime = `
const mini = require(${caminhoMini})
const jsx = (tipo, props, key) => ({ __el: true, tipo, props: props || {}, key })
module.exports = { jsx, jsxs: jsx, jsxDEV: jsx, Fragment: mini.FRAGMENT }
`
  escrever('react', 'jsx-runtime.js', runtime)
  escrever('react', 'jsx-dev-runtime.js', runtime)
  escrever('lucide-react', 'package.json',
    '{"name":"lucide-react","main":"index.js"}')
  escrever('lucide-react', 'index.js', `
module.exports = new Proxy({}, { get: (_, nome) => {
  if (nome === '__esModule') return true
  const Icone = () => ({ __el: true, tipo: 'svg',
    props: { 'data-icone': String(nome) } })
  Object.defineProperty(Icone, 'name', { value: String(nome) })
  return Icone
} })
`)
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'tabela-'))
preparar(tmp)
shims(tmp)
const { TabelaChamados } = require(path.join(tmp, 'components/chamados/TabelaChamados.js'))
const { NumeroChamado } = require(path.join(tmp, 'components/chamados/NumeroChamado.js'))
const { FiltroResponsaveis } = require(path.join(tmp, 'components/chamados/FiltroResponsaveis.js'))
const { copiarTexto } = require(path.join(tmp, 'lib/copiar.js'))
const alturas = require(path.join(tmp, 'lib/tabelaChamados.js'))
const fr = require(path.join(tmp, 'lib/filtroResponsaveis.js'))
const fk = require(path.join(tmp, 'lib/filtrosKanban.js'))

const el = (tipo, props) => mini.criar(tipo, props)
const achar = (tela, atributo) =>
  tela.achar(n => n.props && n.props[atributo] !== undefined)

// ── memória falsa, para provar que a largura escolhida é LEMBRADA ───────────
const memoria = new Map()
globalThis.localStorage = {
  getItem: k => (memoria.has(k) ? memoria.get(k) : null),
  setItem: (k, v) => memoria.set(k, String(v)),
}

// ── 1. a tabela ────────────────────────────────────────────────────────────
// ⚠️ A coluna OPCIONAL (prazo) vem ANTES do responsável, de propósito. Com ela
// por último, perder a célula não desloca ninguém e o teste de alinhamento
// passaria verde com o defeito de pé — foi o que a primeira sabotagem mostrou.
// Aqui, perder a célula do prazo empurra o responsável para a coluna do prazo:
// exatamente a queixa que originou a fase.
const COLUNAS = [
  { chave: 'numero', rotulo: 'Chamado', largura: 160, minima: 120,
    conteudo: c => c.numero, titulo: c => c.numero },
  { chave: 'prazo', rotulo: 'Prazo', largura: 110, minima: 80,
    conteudo: c => c.prazo || null, titulo: c => c.prazo || '' },
  { chave: 'responsavel', rotulo: 'Responsável', largura: 190, minima: 100,
    conteudo: c => c.atribuido_a || 'sem responsável',
    titulo: c => c.atribuido_a || 'sem responsável' },
]

// A posição do responsável — a coluna cuja constância a fase inteira promete.
const COL_RESPONSAVEL = 2

const ITENS = [
  // A linha do defeito: SEM prazo. Na lista antiga, o responsável escorregava
  // para a posição do prazo.
  { sys_id: 'a', numero: 'RITM0000001', atribuido_a: 'Cristiane Gomes de Moura',
    prazo: null },
  { sys_id: 'b', numero: 'RITM0000002', atribuido_a: 'Carlos Henrique', prazo: '02/09/2026' },
  { sys_id: 'c', numero: 'RITM0000003', atribuido_a: null, prazo: '03/09/2026' },
]

function montarTabela(id) {
  return mini.montar(el(TabelaChamados, {
    id, colunas: COLUNAS, itens: ITENS, chaveDe: c => c.sys_id,
    vazio: 'Nenhum chamado nesta categoria.',
  }))
}

const larguraDasCols = (tela) =>
  tela.achar(n => n.tag === 'col').map(n => (n.props.style || {}).width)

const textoDe = (no) => typeof no === 'string' ? no
  : (no.filhos || []).map(textoDe).join('')

function olharTabela(tela) {
  const linhas = tela.achar(n => n.tag === 'tr')
  // A primeira `tr` é o cabeçalho; as demais são as linhas de dados.
  const corpo = linhas.slice(1)
  return {
    cabecalhos: tela.achar(n => n.tag === 'th').map(n => textoDe(n).trim()),
    // Quantas células cada linha tem. Igual ao número de colunas, SEMPRE.
    celulasPorLinha: corpo.map(l => l.filhos.filter(f => f.tag === 'td').length),
    // O que está NA COLUNA DO RESPONSÁVEL, linha a linha — por posição, que é
    // como o olho lê uma tabela.
    responsavelNaColuna: corpo.map(l => {
      const td = l.filhos.filter(f => f.tag === 'td')[COL_RESPONSAVEL]
      return td ? textoDe(td).trim() : null
    }),
    tituloDaCelula: corpo.map(l => {
      const td = l.filhos.filter(f => f.tag === 'td')[COL_RESPONSAVEL]
      return td ? (td.props.title || null) : null
    }),
    larguras: larguraDasCols(tela),
  }
}

const tela1 = montarTabela('bancada')
const antes = olharTabela(tela1)

// Arrasta a alça da coluna "Responsável" 60px para a direita.
const alca = achar(tela1, 'data-alca').find(n => n.props['data-alca'] === 'responsavel')
tela1.disparar(alca, 'onPointerDown', { clientX: 300, pointerId: 1 })
tela1.disparar(alca, 'onPointerMove', { clientX: 360, pointerId: 1 })
const durante = larguraDasCols(tela1)
tela1.disparar(alca, 'onPointerUp', { clientX: 360, pointerId: 1 })

// Arrasta MUITO para a esquerda: tem de parar na largura mínima.
tela1.disparar(alca, 'onPointerDown', { clientX: 360, pointerId: 1 })
tela1.disparar(alca, 'onPointerMove', { clientX: -900, pointerId: 1 })
const noPiso = larguraDasCols(tela1)
tela1.disparar(alca, 'onPointerUp', { clientX: -900, pointerId: 1 })

// Uma tabela NOVA com o mesmo id tem de nascer com a largura salva.
const tela2 = montarTabela('bancada')
// …e outra, com id diferente, tem de nascer no padrão.
const tela3 = montarTabela('outra-tabela')

const vazia = mini.montar(el(TabelaChamados, {
  id: 'vazia', colunas: COLUNAS, itens: [], chaveDe: c => c.sys_id,
  vazio: 'Nenhum chamado nesta categoria.',
}))

// ── 2. o botão de copiar ───────────────────────────────────────────────────
// ⚠️ `globalThis.navigator` é um GETTER sem setter no Node 22: `globalThis.
// navigator = x` falha EM SILÊNCIO (o módulo não roda em strict mode). A
// primeira versão desta bancada media o navigator do Node em vez do dublê, e
// os três cenários de cópia davam o mesmo resultado — parecendo concordância.
function porNavigator(valor) {
  if (valor === undefined) {
    Object.defineProperty(globalThis, 'navigator',
      { value: undefined, configurable: true, writable: true })
  } else {
    Object.defineProperty(globalThis, 'navigator',
      { value: valor, configurable: true, writable: true })
  }
}

async function copiar(ambiente) {
  porNavigator(ambiente)
  const escritos = []
  if (ambiente && ambiente.clipboard) ambiente.clipboard.__escritos = escritos

  const tela = mini.montar(el(NumeroChamado, { numero: 'RITM0103367' }))
  const botao = achar(tela, 'data-copiar')[0]
  const antesDoClique = {
    temBotao: !!botao,
    ajuda: botao ? botao.props.title : '',
    etiqueta: botao ? botao.props['aria-label'] : '',
    avisoAntes: achar(tela, 'data-aviso').length > 0,
  }
  tela.clicar(botao)
  await new Promise(r => setImmediate(r))
  tela.sincronizar()
  const aviso = achar(tela, 'data-aviso')[0]
  return Object.assign(antesDoClique, {
    texto: tela.texto,
    temAviso: !!aviso,
    aviso: aviso ? textoDe(aviso).trim() : null,
    // O ícone vira um "check" quando deu certo — confirmação também no ícone.
    icone: tela.achar(n => n.tag === 'svg').map(n => n.props['data-icone']),
    escritos,
  })
}

// ── 3. as funções puras ────────────────────────────────────────────────────
const puras = {
  piso: alturas.novaLargura(150, -900, 100),
  cresce: alturas.novaLargura(150, 60),
  pisoPadrao: alturas.novaLargura(150, -900),
  // Preferência salva que não corresponde mais às colunas de hoje.
  salvasParciais: alturas.larguraDasColunas(COLUNAS, { responsavel: 260, sumida: 999 }),
  salvasInvalidas: alturas.larguraDasColunas(COLUNAS,
    { numero: 'muito', responsavel: -5, prazo: NaN }),
  salvasAusentes: alturas.larguraDasColunas(COLUNAS, null),
  // Salva abaixo do mínimo: sobe para o mínimo em vez de virar coluna sumida.
  salvaAbaixoDoMinimo: alturas.larguraDasColunas(COLUNAS, { responsavel: 10 }),
}

// ── 4. paginação ───────────────────────────────────────────────────────────
const MUITOS = Array.from({ length: 25 }, (_, i) => ({
  sys_id: `s${i}`, numero: `RITM${String(i).padStart(7, '0')}`,
  atribuido_a: `Pessoa ${i}`, prazo: null,
}))

function montarPaginada(itens, porPagina) {
  return mini.montar(el(TabelaChamados, {
    id: 'paginada', colunas: COLUNAS, itens, chaveDe: c => c.sys_id,
    vazio: 'vazio', porPagina,
  }))
}

const numerosNaTela = (tela) => tela.achar(n => n.tag === 'tr').slice(1)
  .map(l => textoDe(l.filhos.filter(f => f.tag === 'td')[0]).trim())

const regua = (tela) => {
  const anterior = achar(tela, 'data-pagina-anterior')[0]
  const proxima = achar(tela, 'data-pagina-proxima')[0]
  return {
    temRegua: !!anterior && !!proxima,
    texto: tela.texto,
    linhas: numerosNaTela(tela).length,
    primeiro: numerosNaTela(tela)[0] || null,
    anteriorDesligado: anterior ? !!anterior.props.disabled : null,
    proximaDesligada: proxima ? !!proxima.props.disabled : null,
  }
}

const p1 = montarPaginada(MUITOS, 10)
const pagina1 = regua(p1)
p1.clicar(achar(p1, 'data-pagina-proxima')[0])
const pagina2 = regua(p1)
p1.clicar(achar(p1, 'data-pagina-proxima')[0])
const pagina3 = regua(p1)

// A lista ENCOLHE debaixo do estado (o usuário filtrou): a página 3 não existe
// mais, e obedecê-la renderizaria uma tabela vazia.
const p2 = montarPaginada(MUITOS, 10)
p2.clicar(achar(p2, 'data-pagina-proxima')[0])
p2.clicar(achar(p2, 'data-pagina-proxima')[0])
const encolheu = regua(mini.montar(el(TabelaChamados, {
  id: 'paginada', colunas: COLUNAS, itens: MUITOS.slice(0, 4),
  chaveDe: c => c.sys_id, vazio: 'vazio', porPagina: 10,
})))

// ── 5. o filtro de responsáveis, com marcação múltipla ─────────────────────
const OPCOES = [
  { nome: 'Ana', total: 12 }, { nome: 'Bruno', total: 7 },
  { nome: 'sem responsável', total: 3 },
]

// A caixa começa FECHADA: abrir é o primeiro gesto, como na tela.
function abrir(escolhidos, opcoes = OPCOES) {
  const mudancas = []
  const tela = mini.montar(el(FiltroResponsaveis, {
    opcoes, escolhidos, totalGeral: 22,
    aoMudar: (nomes) => mudancas.push(nomes),
  }))
  const fechada = achar(tela, 'data-caixa').length === 0
  tela.clicar(achar(tela, 'data-gatilho')[0])
  return { tela, mudancas, comecaFechada: fechada }
}

const estaAberta = (tela) => achar(tela, 'data-caixa').length > 0

function filtro(escolhidos) {
  const { tela, mudancas, comecaFechada } = abrir(escolhidos)
  const caixas = achar(tela, 'data-opcao')
  const marcar = (nome) => {
    const linha = caixas.find(n => n.props['data-opcao'] === nome)
    const caixa = linha.filhos.find(f => f.tag === 'input')
    caixa.props.onChange({ target: { checked: !caixa.props.checked } })
    return mudancas[mudancas.length - 1]
  }
  return {
    comecaFechada,
    // Só o PRIMEIRO span do gatilho: o `textoDe` do botão inteiro colaria o
    // resumo com o número do contador ao lado ("Ana1").
    resumo: textoDe(achar(tela, 'data-gatilho')[0]
      .filhos.find(f => f.tag === 'span')).trim(),
    contagem: achar(tela, 'data-contagem').length
      ? textoDe(achar(tela, 'data-contagem')[0]).trim() : null,
    opcoes: caixas.map(n => n.props['data-opcao']),
    marcadas: caixas.filter(n => n.filhos.some(f => f.tag === 'input' && f.props.checked))
      .map(n => n.props['data-opcao']),
    aoMarcarAna: marcar('Ana'),
    aoMarcarSemDono: marcar('sem responsável'),
    aoLimpar: (() => {
      tela.clicar(achar(tela, 'data-limpar')[0])
      return mudancas[mudancas.length - 1]
    })(),
  }
}

// ── 6. os filtros do kanban ────────────────────────────────────────────────
const card = (extra) => Object.assign({
  numero: 'RITM0000001', tipo: 'ritm', titulo: 'Carga diária',
  estado_origem: null, atribuido_a: 'Ana', prioridade: '3 - Moderado',
  categoria_diaadia: '',
}, extra)
const task = (extra) => card(Object.assign(
  { numero: 'SCTASK0000009', tipo: 'task' }, extra))

const F = (extra) => Object.assign({}, fk.SEM_FILTRO, extra)
const casa = (c, filhas, f) => fk.casaFiltros(c, filhas, f)

const kanban = {
  tipos_do_seletor: fk.tiposDisponiveis([
    card({}), card({ tipo: 'incident' }), task({}), card({ tipo: 'ritm' }),
  ]),
  tipos_sem_cards: fk.tiposDisponiveis([]),
  // categoria
  cat_diaadia_acha: casa(card({ categoria_diaadia: 'dia a dia' }), [],
                         F({ categoria: 'dia a dia' })),
  cat_diaadia_recusa_iniciativa: casa(card({ categoria_diaadia: 'iniciativa' }), [],
                                      F({ categoria: 'dia a dia' })),
  cat_sem_marcacao_acha: casa(card({ categoria_diaadia: '' }), [],
                              F({ categoria: fk.SEM_MARCACAO })),
  cat_sem_marcacao_recusa_marcado: casa(card({ categoria_diaadia: 'iniciativa' }), [],
                                        F({ categoria: fk.SEM_MARCACAO })),
  // ⚠️ a categoria é do CARD: casar pela filha traria card sem badge nenhum
  cat_nao_casa_pela_filha: casa(card({ categoria_diaadia: '' }),
                                [task({ categoria_diaadia: 'iniciativa' })],
                                F({ categoria: 'iniciativa' })),
  // sem atribuição
  sem_dono_acha: casa(card({ atribuido_a: null }), [], F({ responsavel: fk.SEM_ATRIBUICAO })),
  sem_dono_recusa_atribuido: casa(card({ atribuido_a: 'Ana' }), [],
                                  F({ responsavel: fk.SEM_ATRIBUICAO })),
  // ⚠️ card COM dono e task SEM dono não é "sem atribuição"
  sem_dono_ignora_filha: casa(card({ atribuido_a: 'Ana' }), [task({ atribuido_a: null })],
                              F({ responsavel: fk.SEM_ATRIBUICAO })),
  sem_dono_aceita_vazio: casa(card({ atribuido_a: '  ' }), [],
                              F({ responsavel: fk.SEM_ATRIBUICAO })),
  // responsável nomeado: casa pela FILHA também
  resp_pela_filha: casa(card({ atribuido_a: 'Ana' }), [task({ atribuido_a: 'Bruno' })],
                        F({ responsavel: 'Bruno' })),
  // busca alcança o número da task
  busca_pela_filha: casa(card({}), [task({ numero: 'SCTASK0105181' })],
                         F({ busca: 'sctask01051' })),
  // tipo é do CARD, não da filha
  tipo_nao_casa_pela_filha: casa(card({ tipo: 'ritm' }), [task({})], F({ tipo: 'task' })),
  tipo_do_card: casa(card({ tipo: 'incident' }), [], F({ tipo: 'incident' })),
  // combinação: os filtros se somam (E), não se substituem
  combinado_ok: casa(card({ categoria_diaadia: 'iniciativa', atribuido_a: 'Ana' }), [],
                     F({ categoria: 'iniciativa', responsavel: 'Ana' })),
  combinado_recusa: casa(card({ categoria_diaadia: 'iniciativa', atribuido_a: 'Bruno' }), [],
                         F({ categoria: 'iniciativa', responsavel: 'Ana' })),
  sem_filtro_passa_tudo: casa(card({ atribuido_a: null, categoria_diaadia: '' }), [], F({})),
  // ── incidente: destaque e topo da fila ──────────────────────────────────
  destaca_incidente_novo: fk.destacaIncidente({ tipo: 'incident', estado_kanban: 'novo' }),
  destaca_incidente_andamento: fk.destacaIncidente({ tipo: 'incident', estado_kanban: 'andamento' }),
  destaca_incidente_aguardando: fk.destacaIncidente({ tipo: 'incident', estado_kanban: 'aguardando' }),
  // ⚠️ perde o destaque ao terminar: alarme sobre trabalho FEITO não pede ação
  destaca_incidente_resolvido: fk.destacaIncidente({ tipo: 'incident', estado_kanban: 'resolvido' }),
  destaca_incidente_encerrado: fk.destacaIncidente({ tipo: 'incident', estado_kanban: 'encerrado' }),
  destaca_ritm: fk.destacaIncidente({ tipo: 'ritm', estado_kanban: 'novo' }),
  destaca_task: fk.destacaIncidente({ tipo: 'task', estado_kanban: 'novo' }),

  ordem_incidente_sobe: fk.ordenarColuna([
    { numero: 'R1', tipo: 'ritm', estado_kanban: 'novo' },
    { numero: 'R2', tipo: 'ritm', estado_kanban: 'novo' },
    { numero: 'I1', tipo: 'incident', estado_kanban: 'novo' },
    { numero: 'R3', tipo: 'ritm', estado_kanban: 'novo' },
  ]).map(c => c.numero),
  // Estável: dentro de cada grupo, a ordem do servidor é preservada.
  ordem_estavel: fk.ordenarColuna([
    { numero: 'R1', tipo: 'ritm', estado_kanban: 'novo' },
    { numero: 'I1', tipo: 'incident', estado_kanban: 'novo' },
    { numero: 'R2', tipo: 'ritm', estado_kanban: 'novo' },
    { numero: 'I2', tipo: 'incident', estado_kanban: 'novo' },
    { numero: 'R3', tipo: 'ritm', estado_kanban: 'novo' },
  ]).map(c => c.numero),
  // Na coluna de resolvidos o incidente NÃO sobe: ele já terminou.
  ordem_resolvido_nao_sobe: fk.ordenarColuna([
    { numero: 'R1', tipo: 'ritm', estado_kanban: 'resolvido' },
    { numero: 'I1', tipo: 'incident', estado_kanban: 'resolvido' },
    { numero: 'R2', tipo: 'ritm', estado_kanban: 'resolvido' },
  ]).map(c => c.numero),
  ordem_vazia: fk.ordenarColuna([]).length,
  // Não muda a lista recebida: mutar o array do `useMemo` faria a fila mudar
  // de ordem entre renderizações sem nada tê-la reordenado.
  ordem_nao_muta: (() => {
    const original = [
      { numero: 'R1', tipo: 'ritm', estado_kanban: 'novo' },
      { numero: 'I1', tipo: 'incident', estado_kanban: 'novo' },
    ]
    fk.ordenarColuna(original)
    return original.map(c => c.numero)
  })(),

  ativo_vazio: fk.algumFiltroAtivo(F({})),
  ativo_com_categoria: fk.algumFiltroAtivo(F({ categoria: fk.SEM_MARCACAO })),
}

async function principal() {
  const cenarios = {
    paginacao: { pagina1, pagina2, pagina3, encolheu,
      desligada: regua(montarPaginada(MUITOS, 0)),
      curta: regua(montarPaginada(MUITOS.slice(0, 4), 10)),
      fatias: {
        primeira: alturas.fatiar(25, 0, 10),
        ultima: alturas.fatiar(25, 2, 10),
        alem_do_fim: alturas.fatiar(25, 9, 10),
        negativa: alturas.fatiar(25, -3, 10),
        vazia: alturas.fatiar(0, 0, 10),
        exata: alturas.fatiar(20, 1, 10),
      },
    },
    filtro_responsaveis: {
      nenhum: filtro([]),
      um: filtro(['Ana']),
      dois: filtro(['Ana', 'Bruno']),
      tres: filtro(['Ana', 'Bruno', 'sem responsável']),
      vazio: (() => {
        const { tela } = abrir([], [])
        return { texto: tela.texto }
      })(),
      // ⚠️ O DEFEITO RELATADO: a caixa ficava aberta sobre a tela e só sumia
      // com um recarregamento — que levava o filtro junto.
      fechamento: (() => {
        // Clica SE o nó existir. Sem esta guarda, a ausência do fundo derruba
        // a bancada inteira com "nó sem onClick", e a suíte reporta um erro de
        // infraestrutura no lugar do defeito que ela deveria nomear.
        const clicarSeHouver = (tela, marca) => {
          const no = achar(tela, marca)[0]
          if (no) tela.clicar(no)
          return !!no
        }

        const fundo = abrir(['Ana'])
        const achouFundo = clicarSeHouver(fundo.tela, 'data-fundo')

        const esc = abrir(['Ana'])
        const raiz = esc.tela.achar(n => n.props && n.props.onKeyDown)[0]
        esc.tela.disparar(raiz, 'onKeyDown', { key: 'Escape' })

        const outraTecla = abrir(['Ana'])
        outraTecla.tela.disparar(
          outraTecla.tela.achar(n => n.props && n.props.onKeyDown)[0],
          'onKeyDown', { key: 'a' })

        const botao = abrir(['Ana'])
        const achouFechar = clicarSeHouver(botao.tela, 'data-fechar')

        const gatilho = abrir(['Ana'])
        gatilho.tela.clicar(achar(gatilho.tela, 'data-gatilho')[0])

        // Marcar NÃO fecha: o filtro é de múltipla escolha, e fechar a cada
        // marca obrigaria a reabrir para cada nome.
        const marcando = abrir(['Ana'])
        const linha = achar(marcando.tela, 'data-opcao')
          .find(n => n.props['data-opcao'] === 'Bruno')
        const caixa = linha.filhos.find(f => f.tag === 'input')
        caixa.props.onChange({ target: { checked: true } })
        marcando.tela.sincronizar()

        return {
          temFundo: achouFundo,
          temBotaoFechar: achouFechar,
          depoisDoFundo: estaAberta(fundo.tela),
          depoisDoEsc: estaAberta(esc.tela),
          depoisDeOutraTecla: estaAberta(outraTecla.tela),
          depoisDoBotaoFechar: estaAberta(botao.tela),
          depoisDoGatilhoDeNovo: estaAberta(gatilho.tela),
          aoMarcarContinuaAberta: estaAberta(marcando.tela),
        }
      })(),
      puras: {
        url_vazia: fr.urlIndicadores([]),
        url_um: fr.urlIndicadores(['Ana']),
        url_dois: fr.urlIndicadores(['Ana', 'Bruno']),
        url_acentuada: fr.urlIndicadores(['sem responsável']),
        url_ignora_brancos: fr.urlIndicadores(['  ', 'Ana ']),
        resumo_nenhum: fr.resumoDoFiltro([], 42),
        resumo_um: fr.resumoDoFiltro(['Ana'], 42),
        resumo_dois: fr.resumoDoFiltro(['Ana', 'Bruno'], 42),
        resumo_tres: fr.resumoDoFiltro(['Ana', 'Bruno', 'Caio'], 42),
        aviso_nenhum: fr.avisoDoFiltro([]),
        aviso_um: fr.avisoDoFiltro(['Ana']),
        aviso_tres: fr.avisoDoFiltro(['Ana', 'Bruno', 'Caio']),
        alternar_marca: fr.alternar(['Ana'], 'Bruno'),
        alternar_desmarca: fr.alternar(['Ana', 'Bruno'], 'Ana'),
      },
    },
    kanban,
    tabela: {
      antes,
      depoisDeArrastar: durante,
      noPiso,
      lembrada: larguraDasCols(tela2),
      outroId: larguraDasCols(tela3),
      vazia: { texto: vazia.texto, temTabela: vazia.achar(n => n.tag === 'table').length > 0 },
    },
    // A área de transferência funciona.
    copia_ok: await copiar({ clipboard: {
      writeText: async function (t) { this.__escritos.push(t) },
    } }),
    // A API existe mas RECUSA (permissão, contexto inseguro) e não há
    // `document` para o caminho legado: a tela pede o Ctrl+C.
    copia_recusada: await copiar({ clipboard: {
      writeText: async () => { throw new Error('NotAllowedError') },
    } }),
    // Nem `navigator.clipboard` existe — o caso do http sem TLS.
    copia_sem_api: await copiar(undefined),
    puras,
    // A função de cópia, olhada direto, com o ambiente injetado.
    direto: {
      vazio: await copiarTexto('   '),
      legadoSalva: await copiarTexto('RITM1', { escrever: undefined, legado: () => true }),
      legadoFalha: await copiarTexto('RITM1', { escrever: undefined, legado: () => false }),
      apiOk: await copiarTexto('RITM1', { escrever: async () => {}, legado: () => false }),
    },
  }
  fs.rmSync(tmp, { recursive: true, force: true })
  process.stdout.write(JSON.stringify(cenarios))
}

principal()
