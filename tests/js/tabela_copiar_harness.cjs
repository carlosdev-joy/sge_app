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
  'lib/copiar.ts',
  'lib/tabelaChamados.ts',
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
const { copiarTexto } = require(path.join(tmp, 'lib/copiar.js'))
const alturas = require(path.join(tmp, 'lib/tabelaChamados.js'))

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

async function principal() {
  const cenarios = {
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
