// Exercita o listener real; o minireact das outras bancadas não executa useEffect.
// Não simula o navegador: o smoke do clipboard real é feito no DEV.
const fs = require('fs')
const path = require('path')
const vm = require('vm')
const assert = require('node:assert/strict')
const raiz = path.resolve(__dirname, '../..')
const { transform } = require(path.join(raiz, 'ui-react/node_modules/sucrase'))
const fonte = process.argv[2] || path.join(raiz, 'ui-react/src/components/utilitarios/FormEnviarArquivo.tsx')
let listener, cleanup, estado, modal, removido, seletor
const react = {
  useState(inicial) {
    const i = estado.length
    estado.push(inicial)
    return [inicial, valor => { estado[i] = valor }]
  },
  useRef: () => (seletor = { current: { value: 'local.png' } }),
  useEffect(efeito) { cleanup = efeito() },
}
const document = {
  querySelector: () => modal,
  addEventListener(tipo, fn) { assert.equal(tipo, 'paste'); listener = fn },
  removeEventListener(tipo, fn) { assert.equal(tipo, 'paste'); removido = fn === listener },
}
const contexto = {
  exports: {}, document,
  require(nome) {
    if (nome === 'react') return react
    if (nome === 'react/jsx-runtime') return { jsx: () => null, jsxs: () => null }
    // A bancada de envio existente cobre a renderização/validação do formulário.
    return new Proxy({}, {
      get: (_, chave) => chave === 'useNavegadorPastas' ? () => ({ disponivel: false }) : () => null,
    })
  },
}
vm.runInNewContext(transform(fs.readFileSync(fonte, 'utf8'), {
  transforms: ['typescript', 'jsx', 'imports'], jsxRuntime: 'automatic', production: true,
}).code, contexto)
function renderizar(props = {}) {
  listener = cleanup = undefined
  estado = []
  modal = null
  removido = false
  contexto.exports.FormEnviarArquivo({
    servidores: [], raizesPorServidor: {}, extensoes: ['png'], tetoKb: 1024,
    podeGravar: true, enviando: false, ...props,
  })
}
function colar(items, defaultPrevented = false) {
  assert.equal(typeof listener, 'function', 'A aba precisa registrar o listener de paste')
  let prevenido = false
  listener({ defaultPrevented, clipboardData: { items }, preventDefault() { prevenido = true } })
  return prevenido
}
const imagem = { name: 'image.png', size: 100, type: 'image/png' }
const item = { kind: 'file', type: 'image/png', getAsFile: () => imagem }
renderizar()
assert.equal(colar([{ kind: 'string', type: 'text/plain' }, item]), true)
assert.equal(estado[3], imagem)
assert.equal(estado[2], 'image.png')
assert.equal(seletor.current.value, '')
cleanup()
assert.equal(removido, true)

for (const items of [[], [{ kind: 'string', type: 'text/plain' }], [{ kind: 'file', type: 'application/pdf' }], [{ ...item, getAsFile: () => null }]]) {
  renderizar()
  assert.equal(colar(items), false)
  assert.equal(estado[3], null)
}
renderizar()
modal = {}
assert.equal(colar([item]), false)
assert.equal(estado[3], null)
renderizar()
assert.equal(colar([item], true), false)
assert.equal(estado[3], null)
for (const props of [{ podeGravar: false }, { enviando: true }]) {
  renderizar(props)
  assert.equal(listener, undefined)
}
renderizar()
colar([item])
const outra = { ...imagem, name: 'outro.png' }
colar([{ ...item, getAsFile: () => outra }])
assert.equal(estado[3], outra)
assert.equal(estado[2], 'outro.png')
console.log('OK: imagem, texto, modal, clipboard vazio, permissões, envio e limpeza do listener.')
