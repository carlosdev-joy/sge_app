// Regressões de inserção e catálogo; executa o componente real na bancada local.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const root = path.resolve(__dirname, '../..')
const { transform } = require(path.join(root, 'ui-react/node_modules/sucrase'))
const mini = require('./minireact.cjs')
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'email-picker-'))
function write(file, text) {
  const dest = path.join(tmp, file)
  fs.mkdirSync(path.dirname(dest), { recursive: true })
  fs.writeFileSync(dest, text)
}
try {
  for (const file of ['lib/emailPlaceholders.ts', 'components/etapas/EmailPlaceholderPicker.tsx', 'components/etapas/fluxoTypes.ts', 'components/etapas/previaEmailDados.ts']) {
    write(file.replace(/\.tsx?$/, '.js'), transform(fs.readFileSync(path.join(root, 'ui-react/src', file), 'utf8'), {
      transforms: ['typescript', 'jsx', 'imports'], jsxRuntime: 'automatic', production: true,
    }).code)
  }
  write('node_modules/react/index.js', `module.exports = require(${JSON.stringify(path.join(__dirname, 'minireact.cjs'))}).hooks`)
  write('node_modules/react/jsx-runtime.js', `exports.jsx = exports.jsxs = (tipo, props) => ({ __el: true, tipo, props });`)
  write('components/ui/Input.js', `const mini = require(${JSON.stringify(path.join(__dirname, 'minireact.cjs'))}); exports.Select = props => mini.criar('select', props); exports.Input = props => mini.criar('input', props);`)
  write('components/ui/Button.js', `const mini = require(${JSON.stringify(path.join(__dirname, 'minireact.cjs'))}); exports.Button = props => mini.criar('button', props);`)
  const helper = require(path.join(tmp, 'lib/emailPlaceholders.js'))
  const { EmailPlaceholderPicker } = require(path.join(tmp, 'components/etapas/EmailPlaceholderPicker.js'))
  assert.equal(helper.emailPlaceholderCatalogo('anexo').length, 7)
  assert(!helper.emailPlaceholderCatalogo('anexo').some(p => ['data', 'inicio'].includes(p.nome)))
  assert(!helper.emailPlaceholderCatalogo('anexo').some(p => p.nome.startsWith('tabela')))
  assert.equal(helper.emailPlaceholderCatalogo('corpo').length, 10)
  assert.equal(helper.emailPlaceholderCatalogo('assunto').find(p => p.nome === 'tabela').exemplo, '2 linhas × 2 colunas')
  for (const name of ['SQL_1', 'sql.nome-2', 'a'.repeat(128)]) assert(helper.nomeSqlParaPlaceholderValido(name))
  for (const name of ['', ' ', 'á', 'a/b', 'a'.repeat(129), 'sql\n']) assert(!helper.nomeSqlParaPlaceholderValido(name))
  let raf
  global.requestAnimationFrame = cb => { raf = cb }
  let calls = 0
  for (const campo of ['assunto', 'corpo', 'anexo']) {
    let written
    const target = { selectionStart: 4, selectionEnd: 8, focus() { calls++ }, setSelectionRange(a, b) { this.selectionStart = a; this.selectionEnd = b } }
    const screen = mini.montar(mini.criar(EmailPlaceholderPicker, { campo, targetRef: { current: target }, value: 'ABC XXXX Z', onChange: value => { written = value } }))
    screen.disparar(screen.achar(n => n.tag === 'select')[0], 'onChange', { target: { value: 'odate' } })
    screen.clicar(screen.botoes('Inserir')[0])
    assert.equal(written, 'ABC {odate} Z')
    raf()
    assert.equal(target.selectionStart, 11)
    assert.equal(target.selectionEnd, 11)
    if (campo === 'anexo') assert(!screen.achar(n => n.tag === 'option').some(n => n.props.value.startsWith('tabela')))
  }
  assert.equal(calls, 3)
  let written
  const target = { selectionStart: 1, selectionEnd: 1, focus() {}, setSelectionRange() {} }
  const screen = mini.montar(mini.criar(EmailPlaceholderPicker, { campo: 'corpo', targetRef: { current: target }, value: 'AB', onChange: value => { written = value } }))
  screen.disparar(screen.achar(n => n.tag === 'select')[0], 'onChange', { target: { value: 'tabela:informar nome' } })
  assert(screen.botoes('Inserir')[0].props.disabled)
  screen.disparar(screen.achar(n => n.tag === 'input')[0], 'onChange', { target: { value: 'SQL errado' } })
  assert(screen.botoes('Inserir')[0].props.disabled)
  screen.disparar(screen.achar(n => n.tag === 'input')[0], 'onChange', { target: { value: 'SQL_1' } })
  assert(!screen.botoes('Inserir')[0].props.disabled)
  screen.clicar(screen.botoes('Inserir')[0])
  assert.equal(written, 'A{tabela:SQL_1}B')
  console.log(JSON.stringify({ ok: true, catalogoAnexo: helper.emailPlaceholderCatalogo('anexo').map(p => p.nome),
    catalogoCorpo: helper.emailPlaceholderCatalogo('corpo').map(p => p.nome),
    cenarios: ['catalogo', 'qualificador', 'selecao', 'cursor', 'foco', 'anexo'] }))
} finally {
  fs.rmSync(tmp, { recursive: true, force: true })
}
