// Bancada do rodapé do card do kanban — `components/chamados/RodapeCard`.
//
// ⚠️ POR QUE ISTO RENDERIZA, E NÃO LÊ O FONTE
// A primeira versão deste teste procurava `{vivo &&` no `.tsx` — e passou
// VERDE com o defeito de pé, porque o arquivo tinha DUAS ocorrências e
// sabotar uma deixava a outra satisfazendo a busca. O que esta fase entrega é
// uma AUSÊNCIA (o alarme some no card resolvido), e ausência só se afirma
// olhando o que foi renderizado.
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

const ENTRADA = 'components/chamados/RodapeCard.tsx'

function resolverRelativo(deDir, especificador) {
  const base = path.resolve(deDir, especificador)
  for (const t of [base + '.tsx', base + '.ts',
                   path.join(base, 'index.tsx'), path.join(base, 'index.ts')]) {
    if (fs.existsSync(t)) return t
  }
  return null
}

// Transpila a entrada e tudo que ela importa por caminho RELATIVO.
function preparar(destino) {
  const feitos = new Set()
  const fila = [path.join(SRC, ENTRADA)]
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
  // ⚠️ `jsx(tipo, props, key)` monta o nó DIRETO, sem passar por `criar`: o
  // `criar` trata os filhos como argumentos variádicos, e o jsx-runtime já
  // manda `children` DENTRO de props. Chamá-lo aqui punha a `key` no lugar
  // dos filhos, e a árvore renderizava vazia — sem erro nenhum.
  const runtime = `
const mini = require(${caminhoMini})
const jsx = (tipo, props, key) => ({ __el: true, tipo, props: props || {}, key })
module.exports = { jsx, jsxs: jsx, jsxDEV: jsx, Fragment: mini.FRAGMENT }
`
  escrever('react', 'jsx-runtime.js', runtime)
  escrever('react', 'jsx-dev-runtime.js', runtime)
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'rodape-'))
preparar(tmp)
shims(tmp)
const { RodapeCard } = require(path.join(tmp, 'components/chamados/RodapeCard.js'))

// Os mesmos ajudantes que a tela passa — copiados de `pages/Chamados.tsx`.
const textoIdade = (d) => d === null ? 'sem data de abertura'
  : d <= 0 ? 'aberto hoje' : d === 1 ? 'aberto há 1 dia' : `parado há ${d} dias`
const faixaIdade = (d) => d === null ? { classe: '', rotulo: '' }
  : d > 7 ? { classe: 'vermelho', rotulo: 'parado' }
  : d > 3 ? { classe: 'ambar', rotulo: 'atenção' } : { classe: '', rotulo: '' }

const el = (tipo, props) => mini.criar(tipo, props)
const montar = (c) => mini.montar(el(RodapeCard, { c, textoIdade, faixaIdade }))
const chamado = (extra) => Object.assign(
  { estado_kanban: 'novo', atribuido_a: 'Fulano', demandante: null,
    idade_dias: 12, prazo: '2026-09-02 10:00:00' }, extra)

const olhar = (tela) => ({
  texto: tela.texto,
  temIdade: tela.achar(n => n.props && n.props['data-idade'] !== undefined).length > 0,
  temPrazo: tela.achar(n => n.props && n.props['data-prazo'] !== undefined).length > 0,
})

const cenarios = {
  // Card VIVO e velho: o alarme faz sentido — é o que pede priorização.
  novo_parado:      olhar(montar(chamado({ estado_kanban: 'novo' }))),
  andamento:        olhar(montar(chamado({ estado_kanban: 'andamento' }))),
  aguardando:       olhar(montar(chamado({ estado_kanban: 'aguardando' }))),

  // O defeito apontado: "atenção 7d" num card RESOLVIDO. Alarme sobre
  // trabalho FEITO, que não pede ação nenhuma.
  resolvido:        olhar(montar(chamado({ estado_kanban: 'resolvido' }))),
  encerrado:        olhar(montar(chamado({ estado_kanban: 'encerrado' }))),

  // Sem prazo: a linha do prazo não aparece — e a idade continua.
  sem_prazo:        olhar(montar(chamado({ prazo: null }))),

  // Sem responsável: o rodapé DIZ isso em vez de ficar em branco.
  sem_responsavel:  olhar(montar(chamado({ atribuido_a: null }))),
}

fs.rmSync(tmp, { recursive: true, force: true })
process.stdout.write(JSON.stringify(cenarios))
