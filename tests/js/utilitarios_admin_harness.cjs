// Bancada da aba Admin › Utilitários (spec docs/spec-utilitarios-arquivos.md, F2).
//
// ⚠️ POR QUE RENDERIZA
// O que a F2 promete é COMPORTAMENTO: o Incluir fica desligado enquanto o
// caminho é inválido, a raiz inativa aparece esmaecida e com "Reativar", o
// Testar chama o servidor com o id certo, a exclusão de extensão só acontece
// depois da confirmação, `sh` pede uma confirmação a mais, e o campo só limpa
// quando o SERVIDOR aceitou (um 409 mantém o que o admin digitou). Nada disso
// se afirma lendo o `.tsx`: a string do aviso existe no fonte mesmo que o ramo
// nunca renderize. Então os três componentes de apresentação rodam aqui,
// byte a byte como estão no `src/`, no React mínimo da casa (minireact.cjs),
// e a bancada clica neles.
//
// O container (UtilitariosTab, react-query) fica de fora: é rede, e a prova
// dele é o tsc + o build + a tela no DEV.
//
// ⚠️ Handlers de submit são ASSÍNCRONOS (esperam o pai dizer se o servidor
// aceitou): depois de cada `submeter` a bancada cede um tick e chama
// `sincronizar()` — sem isso ela olharia a tela cedo demais.
//
// Saída: um JSON só no stdout, lido por tests/test_utilitarios_admin_front.py.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const SRC = path.join(UI, 'src')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADAS = [
  'components/admin/UtilitariosRaizes.tsx',
  'components/admin/UtilitariosExtensoes.tsx',
  'components/admin/UtilitariosLimites.tsx',
  'lib/utilitariosAdmin.ts',
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
  // Além dos hooks do minireact: `forwardRef` (Input/Switch são forwardRef —
  // o nome é preservado para o caminho de estado ficar estável) e `useId`
  // (Input/Select ligam label↔campo; o valor em si não entra em aceite nenhum).
  escrever('react', 'index.js', `
const mini = require(${caminhoMini})
function forwardRef(render) {
  const C = (props) => render(props, null)
  Object.defineProperty(C, 'name', { value: render.name || 'forwardRef' })
  return C
}
module.exports = Object.assign({}, mini.hooks, {
  createElement: mini.criar, Fragment: mini.FRAGMENT,
  forwardRef, useId: () => 'orq-id',
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
  escrever('lucide-react', 'package.json', '{"name":"lucide-react","main":"index.js"}')
  escrever('lucide-react', 'index.js', `
module.exports = new Proxy({}, { get: (_, nome) => {
  if (nome === '__esModule') return true
  const Icone = () => ({ __el: true, tipo: 'svg', props: { 'data-icone': String(nome) } })
  Object.defineProperty(Icone, 'name', { value: String(nome) })
  return Icone
} })
`)
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'utilitarios-admin-'))
preparar(tmp)
shims(tmp)
const { UtilitariosRaizes } = require(path.join(tmp, 'components/admin/UtilitariosRaizes.js'))
const { UtilitariosExtensoes } = require(path.join(tmp, 'components/admin/UtilitariosExtensoes.js'))
const { UtilitariosLimites } = require(path.join(tmp, 'components/admin/UtilitariosLimites.js'))
const puras = require(path.join(tmp, 'lib/utilitariosAdmin.js'))

const el = (tipo, props) => mini.criar(tipo, props)
const porAcao = (tela, acao) => tela.achar(n => n.props && n.props['data-acao'] === acao)
const porAttr = (tela, attr) => tela.achar(n => n.props && n.props[attr] !== undefined)
const textoDe = (no) => typeof no === 'string' ? no
  : (no.filhos || []).map(textoDe).join(' ').replace(/\s+/g, ' ').trim()
const inputs = (tela) => tela.achar(n => n.tag === 'input')
const digitar = (tela, input, value) => tela.disparar(input, 'onChange', { target: { value } })
const tick = () => new Promise(r => setImmediate(r))
// Submit assíncrono: dispara, cede um tick para o `await` do handler e re-renderiza.
async function submeter(tela, form) {
  tela.disparar(form, 'onSubmit', {})
  await tick(); await tick()
  tela.sincronizar()
}
async function clicarAsync(tela, no) {
  tela.clicar(no)
  await tick(); await tick()
  tela.sincronizar()
}

const saida = {}

// ── 1. funções puras ───────────────────────────────────────────────────────
saida.puras = {
  avisoRaiz: {
    vazio: puras.avisoRaiz(''),
    relativa: puras.avisoRaiz('dados/bi'),
    barra: puras.avisoRaiz('/'),
    duplaBarra: puras.avisoRaiz('//'),
    sistema: puras.avisoRaiz('/etc/ssh'),
    sistemaPorDoisPontos: puras.avisoRaiz('/dados/../usr/x'),
    longa: puras.avisoRaiz('/' + 'a'.repeat(801)),
    ok: puras.avisoRaiz('/dados//bi/'),
    okSob: puras.avisoRaiz('/opt/IBM/InformationServer/Server/Projects'),
  },
  normalizarCaminhoLexical: {
    duplas: puras.normalizarCaminhoLexical('//dados//bi/./x/'),
    doisPontos: puras.normalizarCaminhoLexical('/dados/bi/../../etc'),
    acima: puras.normalizarCaminhoLexical('/../etc'),
  },
  normalizarExtensao: {
    vazia: puras.normalizarExtensao('  '),
    pontoMaiuscula: puras.normalizarExtensao(' .SH '),
    invalida: puras.normalizarExtensao('a.b'),
    longa: puras.normalizarExtensao('x'.repeat(16)),
    ok: puras.normalizarExtensao('properties'),
  },
  pedeConfirmacao: { sh: puras.extensaoPedeConfirmacao('sh'), txt: puras.extensaoPedeConfirmacao('txt') },
  tomDoTeste: {
    naoExiste: puras.tomDoTeste({ existe: false, eh_pasta: false, legivel: false, caminho_real: null }).tom,
    arquivo: puras.tomDoTeste({ existe: true, eh_pasta: false, legivel: false, caminho_real: '/x' }).tom,
    ilegivel: puras.tomDoTeste({ existe: true, eh_pasta: true, legivel: false, caminho_real: '/x' }).tom,
    semPermissao: puras.tomDoTeste({ existe: true, eh_pasta: null, legivel: false, caminho_real: null }).tom,
    ok: puras.tomDoTeste({ existe: true, eh_pasta: true, legivel: true, caminho_real: '/x' }).tom,
  },
  tetoValido: {
    ok: puras.tetoValido(' 2048 '), zero: puras.tetoValido('0'), acima: puras.tetoValido('16385'),
    max: puras.tetoValido('16384'), texto: puras.tetoValido('abc'), decimal: puras.tetoValido('2.5'),
  },
  mensagemErro: {
    string: puras.mensagemErro({ message: 'Raiz já cadastrada', status: 409, detail: 'Raiz já cadastrada' }, 'padrão'),
    lista: puras.mensagemErro({ message: '422 Unprocessable', status: 422,
      detail: [{ msg: 'Input should be less than or equal to 2147483647' }] }, 'padrão'),
    generico: puras.mensagemErro({ message: '500 Internal Server Error', status: 500 }, 'padrão'),
    nada: puras.mensagemErro(null, 'padrão'),
  },
  migrationPendente: {
    sim: puras.migrationPendente({ status: 503, message: 'Utilitários indisponíveis: migration 105 pendente' }),
    outro503: puras.migrationPendente({ status: 503, message: 'Servidor não configurado' }),
    n404: puras.migrationPendente({ status: 404, message: 'migration 105' }),
  },
}

// ── 2. raízes ──────────────────────────────────────────────────────────────
const SERVIDORES = [{ id: 'datastage', label: 'Servidor DataStage', configurado: true }]
const RAIZES = [
  { id: 1, servidor: 'datastage', caminho: '/dados/bi', ativo: true, criado_por: 'ADMIN', criado_em: '2026-09-03 10:00:00' },
  { id: 2, servidor: 'datastage', caminho: '/dados/velha', ativo: false, criado_por: 'ADMIN', criado_em: null },
]

function montarRaizes(props) {
  const chamadas = { incluir: [], testar: [], ativar: [], editar: [] }
  const tela = mini.montar(el(UtilitariosRaizes, Object.assign({
    servidores: SERVIDORES, raizes: RAIZES, testes: {}, testandoId: null, incluindo: false,
    // O pai "aceitou": devolve true — é o que autoriza o componente a limpar o campo.
    onIncluir: (s, c) => { chamadas.incluir.push([s, c]); return true },
    onTestar: (id) => chamadas.testar.push(id),
    onAtivar: (id, ativo) => chamadas.ativar.push([id, ativo]),
    onEditar: (id, c) => { chamadas.editar.push([id, c]); return true },
  }, props)))
  return { tela, chamadas }
}
const campoEdicao = (tela) => inputs(tela).find(n => n.props['data-campo'] === 'caminho')
const teclar = (tela, no, key) => tela.disparar(no, 'onKeyDown', { key })
const campoRaiz = (tela) => inputs(tela).find(n => n.props.placeholder && n.props.placeholder.startsWith('/opt'))
const formRaiz = (tela) => porAttr(tela, 'data-form').find(n => n.props['data-form'] === 'incluir-raiz')

async function raizes() {
  const { tela, chamadas } = montarRaizes({})
  const linhas = porAttr(tela, 'data-raiz')
  const r = {
    linhas: linhas.length,
    inativas: linhas.filter(n => n.props['data-inativa'] === '1').map(n => n.props['data-raiz']),
    estados: linhas.map(l => textoDe(l).includes('inativa') ? 'inativa' : (textoDe(l).includes('ativa') ? 'ativa' : '?')),
    acoesLinha1: porAcao(tela, 'desativar').length + '/' + porAcao(tela, 'reativar').length,
    vazio: porAttr(tela, 'data-vazio').length,
  }
  // Testar e (des)ativar chamam o pai com o id certo.
  tela.clicar(porAcao(tela, 'testar')[0])
  tela.clicar(porAcao(tela, 'desativar')[0])
  tela.clicar(porAcao(tela, 'reativar')[0])
  r.chamadas = chamadas
  // Formulário: inválido desliga o botão; válido chama e limpa o campo.
  // ⚠️ Nós são RE-ACHADOS antes de cada gesto: o `onSubmit` de um render antigo
  // fecha sobre o estado antigo (campo vazio) e submeteria "nada".
  const botao = () => porAcao(tela, 'incluir-raiz')[0]
  r.botaoVazio = !!botao().props.disabled
  digitar(tela, campoRaiz(tela), 'dados/bi')
  r.relativa = { desligado: !!botao().props.disabled, aviso: tela.texto.includes('caminho absoluto') }
  digitar(tela, campoRaiz(tela), '/etc/x')
  r.sistema = { desligado: !!botao().props.disabled, aviso: tela.texto.includes('pasta do sistema') }
  digitar(tela, campoRaiz(tela), '/')
  r.barra = { desligado: !!botao().props.disabled }
  digitar(tela, campoRaiz(tela), '  /dados//param/ ')
  r.valida = { desligado: !!botao().props.disabled }
  await submeter(tela, formRaiz(tela))
  r.aposSubmit = { incluir: chamadas.incluir, campo: campoRaiz(tela).props.value }
  // Com o pai ocupado (incluindo), o botão fica desligado mesmo com caminho válido.
  const ocupado = montarRaizes({ incluindo: true }).tela
  digitar(ocupado, campoRaiz(ocupado), '/dados/x')
  r.ocupadoDesligado = !!porAcao(ocupado, 'incluir-raiz')[0].props.disabled
  // O servidor recusou (409): o campo MANTÉM o que foi digitado.
  const recusa = montarRaizes({ onIncluir: () => false }).tela
  digitar(recusa, campoRaiz(recusa), '/dados/bi')
  await submeter(recusa, formRaiz(recusa))
  r.falhaMantemCampo = campoRaiz(recusa).props.value
  saida.raizes = r

  // ── editar o caminho na linha ────────────────────────────────────────────
  {
    const { tela: t, chamadas: c } = montarRaizes({})
    const e = { antes: { campo: !!campoEdicao(t), editar: porAcao(t, 'editar').length } }
    t.clicar(porAcao(t, 'editar')[0])                       // lápis da 1ª raiz (/dados/bi)
    e.aberto = {
      valorInicial: campoEdicao(t).props.value,
      salvarDesligadoSemMudanca: !!porAcao(t, 'salvar-caminho')[0].props.disabled,
      linhaMarcada: porAttr(t, 'data-editando').map(n => n.props['data-raiz']),
      acoesNormaisSomem: porAcao(t, 'testar').length,       // só a 2ª linha continua com Testar
    }
    digitar(t, campoEdicao(t), '/etc/x')
    e.invalido = { desligado: !!porAcao(t, 'salvar-caminho')[0].props.disabled, aviso: t.texto.includes('pasta do sistema') }
    digitar(t, campoEdicao(t), '/opt/totalseg-pwa')
    e.valido = { desligado: !!porAcao(t, 'salvar-caminho')[0].props.disabled }
    teclar(t, campoEdicao(t), 'Enter')                      // Enter salva
    await tick(); await tick(); t.sincronizar()
    e.aposEnter = { editar: c.editar, campo: !!campoEdicao(t) }
    // Esc cancela sem chamar o pai.
    t.clicar(porAcao(t, 'editar')[0])
    digitar(t, campoEdicao(t), '/dados/outro')
    teclar(t, campoEdicao(t), 'Escape')
    e.aposEsc = { editar: c.editar, campo: !!campoEdicao(t) }
    // Cancelar pelo botão idem.
    t.clicar(porAcao(t, 'editar')[0])
    t.clicar(porAcao(t, 'cancelar-caminho')[0])
    e.aposCancelar = { campo: !!campoEdicao(t) }
    // `/dados/bi/` não é mudança de `/dados/bi`: Salvar continua desligado.
    t.clicar(porAcao(t, 'editar')[0])
    digitar(t, campoEdicao(t), '/dados/bi/')
    e.barraFinalNaoMuda = !!porAcao(t, 'salvar-caminho')[0].props.disabled
    t.clicar(porAcao(t, 'cancelar-caminho')[0])
    // Com um teste em andamento o lápis fica desligado (o resultado seria do caminho antigo).
    const testando = montarRaizes({ testandoId: 2 }).tela
    e.lapisDesligadoTestando = porAcao(testando, 'editar').map(n => !!n.props.disabled)
    // O servidor recusou (409 "já existe outra raiz"): a linha continua em edição com o texto.
    const { tela: t2 } = montarRaizes({ onEditar: () => false })
    t2.clicar(porAcao(t2, 'editar')[0])
    digitar(t2, campoEdicao(t2), '/dados/param')
    t2.clicar(porAcao(t2, 'salvar-caminho')[0])
    await tick(); await tick(); t2.sincronizar()
    e.recusaMantem = { campo: campoEdicao(t2) ? campoEdicao(t2).props.value : null }
    saida.editarRaiz = e
  }

  // Resultado do Testar aparece na linha de baixo, com o tom certo.
  const comTestes = montarRaizes({ testes: {
    1: { existe: true, eh_pasta: true, legivel: true, caminho_real: '/u01/dados/bi', detalhe: 'é um link para /u01/dados/bi; existe e é legível pelo usuário SSH', duracao_ms: 120 },
    2: { existe: false, eh_pasta: false, legivel: false, caminho_real: null, detalhe: 'a pasta não existe no servidor' },
  } }).tela
  saida.raizesTeste = {
    linhas: porAttr(comTestes, 'data-teste').map(n => ({ id: n.props['data-teste'], tom: n.props['data-tom'], texto: textoDe(n) })),
  }
  const vazio = mini.montar(el(UtilitariosRaizes, {
    servidores: SERVIDORES, raizes: [], testes: {}, testandoId: null, incluindo: false,
    onIncluir() { return true }, onTestar() {}, onAtivar() {},
  }))
  saida.raizesVazio = porAttr(vazio, 'data-vazio').map(n => n.props['data-vazio'])
  // Servidor não configurado: o select avisa.
  const semSsh = mini.montar(el(UtilitariosRaizes, {
    servidores: [{ id: 'datastage', label: 'Servidor DataStage', configurado: false }],
    raizes: [], testes: {}, testandoId: null, incluindo: false, onIncluir() { return true }, onTestar() {}, onAtivar() {},
  }))
  saida.raizesSemSsh = semSsh.texto.includes('não configurado')
  // Testando: o botão de testar das OUTRAS linhas fica desligado (uma conexão por vez).
  const testando = montarRaizes({ testandoId: 1 }).tela
  saida.raizesTestando = porAcao(testando, 'testar').map(n => !!n.props.disabled)
}

// ── 3. extensões ───────────────────────────────────────────────────────────
function montarExtensoes(extensoes, props) {
  const chamadas = { incluir: [], excluir: [] }
  const tela = mini.montar(el(UtilitariosExtensoes, Object.assign({
    extensoes, incluindo: false,
    onIncluir: (e) => { chamadas.incluir.push(e); return true },
    onExcluir: (e) => chamadas.excluir.push(e),
  }, props)))
  return { tela, chamadas }
}
const campoExt = (tela) => inputs(tela).find(n => n.props.placeholder === 'txt')
const formExt = (tela) => porAttr(tela, 'data-form').find(n => n.props['data-form'] === 'incluir-extensao')

async function extensoes() {
  const { tela, chamadas } = montarExtensoes(['txt', 'sql'])
  const r = { chips: porAttr(tela, 'data-extensao').map(n => n.props['data-extensao']) }
  // Excluir exige confirmação: antes do confirmar, nada; depois, o pai é chamado.
  tela.clicar(porAcao(tela, 'excluir')[0])
  r.antesDeConfirmar = { excluir: chamadas.excluir.slice(), modal: porAcao(tela, 'confirmar-exclusao').length }
  tela.clicar(porAcao(tela, 'confirmar-exclusao')[0])
  r.aposConfirmar = { excluir: chamadas.excluir.slice(), modal: porAcao(tela, 'confirmar-exclusao').length }
  // Incluir normaliza (" .CSV " → csv) e limpa o campo.
  digitar(tela, campoExt(tela), ' .CSV ')
  await submeter(tela, formExt(tela))
  r.csv = { incluir: chamadas.incluir.slice(), campo: campoExt(tela).props.value }
  // Inválida e repetida: aviso no campo, pai não chamado.
  digitar(tela, campoExt(tela), 'a.b')
  await submeter(tela, formExt(tela))
  r.invalida = { incluir: chamadas.incluir.slice(), aviso: tela.texto.includes('Só letras minúsculas') }
  digitar(tela, campoExt(tela), 'sql')
  await submeter(tela, formExt(tela))
  r.repetida = { incluir: chamadas.incluir.slice(), aviso: tela.texto.includes('já está na lista') }
  // `sh` pede confirmação a mais.
  digitar(tela, campoExt(tela), 'sh')
  await submeter(tela, formExt(tela))
  r.shAntes = { incluir: chamadas.incluir.slice(), modal: porAcao(tela, 'confirmar-script').length,
                aviso: tela.texto.includes('scripts') }
  await clicarAsync(tela, porAcao(tela, 'confirmar-script')[0])
  r.shDepois = { incluir: chamadas.incluir.slice(), modal: porAcao(tela, 'confirmar-script').length, campo: campoExt(tela).props.value }
  // O servidor recusou: o campo mantém o texto.
  const recusa = montarExtensoes(['txt'], { onIncluir: () => false }).tela
  digitar(recusa, campoExt(recusa), 'csv')
  await submeter(recusa, formExt(recusa))
  r.falhaMantemCampo = campoExt(recusa).props.value
  saida.extensoes = r
  saida.extensoesVazio = porAttr(montarExtensoes([]).tela, 'data-vazio').map(n => n.props['data-vazio'])
}

// ── 4. limites ─────────────────────────────────────────────────────────────
function montarLimites(props) {
  const chamadas = []
  const tela = mini.montar(el(UtilitariosLimites, Object.assign({
    tamanhoMaxKb: 2048, backup: true, salvando: false,
    onSalvar: (t, b) => chamadas.push([t, b]),
  }, props)))
  return { tela, chamadas }
}

async function limites() {
  const { tela, chamadas } = montarLimites({})
  const form = () => porAttr(tela, 'data-form').find(n => n.props['data-form'] === 'limites')
  const teto = () => inputs(tela).find(n => n.props.inputMode === 'numeric')
  const chave = () => inputs(tela).find(n => n.props.role === 'switch')
  const botao = () => porAcao(tela, 'salvar-limites')[0]
  const r = { semMudanca: !!botao().props.disabled, valorInicial: teto().props.value, chaveInicial: !!chave().props.checked }
  digitar(tela, teto(), '4096')
  r.mudou = !!botao().props.disabled
  await submeter(tela, form())
  r.salvou = chamadas.slice()
  digitar(tela, teto(), 'abc')
  r.invalido = { desligado: !!botao().props.disabled, aviso: tela.texto.includes('Inteiro entre 1 e 16384') }
  await submeter(tela, form())
  r.invalidoNaoSalva = chamadas.length
  digitar(tela, teto(), '2048')
  tela.disparar(chave(), 'onChange', { target: { checked: false } })
  r.soChave = !!botao().props.disabled
  await submeter(tela, form())
  r.salvouChave = chamadas.slice()
  saida.limites = r
}

;(async () => {
  try {
    await raizes()
    await extensoes()
    await limites()
    process.stdout.write(JSON.stringify(saida))
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true })
  }
})().catch(e => { console.error(e); process.exit(1) })
