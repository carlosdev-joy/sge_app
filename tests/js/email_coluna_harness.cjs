// `{coluna:…}` na tela (spec docs/spec-email-coluna-sql.md): seletor real,
// prévia, avisos do grafo e catálogo — sem React de verdade, banco ou envio.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const root = path.resolve(__dirname, '../..')
const { transform } = require(path.join(root, 'ui-react/node_modules/sucrase'))
const mini = require('./minireact.cjs')
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'email-coluna-'))
function write(file, text) {
  const dest = path.join(tmp, file)
  fs.mkdirSync(path.dirname(dest), { recursive: true })
  fs.writeFileSync(dest, text)
}
try {
  for (const file of ['lib/emailPlaceholders.ts', 'lib/emailTabelaOrigem.ts', 'components/etapas/EmailPlaceholderPicker.tsx',
    'components/etapas/fluxoTypes.ts', 'components/etapas/previaEmailDados.ts']) {
    write(file.replace(/\.tsx?$/, '.js'), transform(fs.readFileSync(path.join(root, 'ui-react/src', file), 'utf8'), {
      transforms: ['typescript', 'jsx', 'imports'], jsxRuntime: 'automatic', production: true,
    }).code)
  }
  write('node_modules/react/index.js', `module.exports = require(${JSON.stringify(path.join(__dirname, 'minireact.cjs'))}).hooks`)
  write('node_modules/react/jsx-runtime.js', `exports.jsx = exports.jsxs = (tipo, props) => ({ __el: true, tipo, props });`)
  write('components/ui/Input.js', `const mini = require(${JSON.stringify(path.join(__dirname, 'minireact.cjs'))}); exports.Select = props => mini.criar('select', props); exports.Input = props => mini.criar('input', props);`)
  write('components/ui/Button.js', `const mini = require(${JSON.stringify(path.join(__dirname, 'minireact.cjs'))}); exports.Button = props => mini.criar('button', props);`)
  const helper = require(path.join(tmp, 'lib/emailPlaceholders.js'))
  const { avisosColunaEmail: avisos } = require(path.join(tmp, 'lib/emailTabelaOrigem.js'))
  const previa = require(path.join(tmp, 'components/etapas/previaEmailDados.js'))
  const { EmailPlaceholderPicker } = require(path.join(tmp, 'components/etapas/EmailPlaceholderPicker.js'))

  // Catálogo: `coluna` sozinho não resolve — não vira item da lista.
  for (const campo of ['assunto', 'corpo', 'anexo']) assert(!helper.emailPlaceholderCatalogo(campo).some(p => p.nome === 'coluna'))
  assert.equal(helper.marcadorDeColuna('total'), 'coluna:total')
  assert.equal(helper.marcadorDeColuna('total', 'A.B'), 'coluna:A.B.total')
  for (const alias of ['', 'a-b', 'a.b', 'á', 'a'.repeat(65)]) assert.equal(helper.marcadorDeColuna(alias), null)
  assert.equal(helper.marcadorDeColuna('x', 'nó'), null)
  assert.equal(helper.marcadorDeColuna('a'.repeat(64), 'n'.repeat(64)), null) // 129 > 128

  // Prévia: mostra o alias; sem qualificador ou alias inválido fica literal.
  assert.equal(previa.interpolarExemplo('<b>{coluna:total}</b> {coluna:SQL_1.mes} {coluna:A.B.x}'), '<b>‹total›</b> ‹mes› ‹x›')
  assert.equal(previa.interpolarExemplo('{coluna} {coluna:a-b} {coluna:X.}', false), '{coluna} {coluna:a-b} {coluna:X.}')
  assert.deepEqual(previa.marcadoresDesconhecidos('{coluna:total} {coluna:S.x}'), [])
  assert.deepEqual(previa.marcadoresDesconhecidos('{Coluna:total}'), ['Coluna'])

  // Avisos contra o grafo.
  assert.deepEqual(avisos('{coluna:total} {coluna:SQL_1.mes}', ['SQL_1']), [])
  assert.deepEqual(avisos('sem marcador {tabela}', []), [])
  assert.equal(avisos('{coluna}', ['SQL_1']).length, 1)
  assert.match(avisos('{coluna:total}', [])[0], /não há SQL ligado/)
  assert.match(avisos('{coluna:total}', ['A', 'B'])[0], /\{coluna:NOME_DO_NO\.total\}/)
  assert.deepEqual(avisos('{coluna:A.total}', ['A', 'B']), [])
  assert.match(avisos('{coluna:OUTRO.total}', ['SQL_1'])[0], /"OUTRO"/)
  assert.deepEqual(avisos('{coluna:sql.nome-2.total}', ['sql.nome-2']), [])
  assert.match(avisos('{coluna:a-b}', ['S'])[0], /alias válido/)
  assert.match(avisos('{coluna:x}', ['log_end_S'])[0], /prefixo log_end_/)
  assert.equal(avisos('{coluna:x} {coluna:x}', ['A', 'B']).length, 1)

  // Seletor real.
  global.requestAnimationFrame = cb => cb()
  function montar(props) {
    let escrito
    const target = { selectionStart: 1, selectionEnd: 1, focus() {}, setSelectionRange(a, b) { this.selectionStart = a; this.selectionEnd = b } }
    const tela = mini.montar(mini.criar(EmailPlaceholderPicker, { targetRef: { current: target }, value: 'AB', onChange: v => { escrito = v }, ...props }))
    return { tela, target, lido: () => escrito }
  }
  const selects = tela => tela.achar(n => n.tag === 'select')
  const inputs = tela => tela.achar(n => n.tag === 'input')
  // Anexo não oferece a coluna.
  assert(!montar({ campo: 'anexo' }).tela.achar(n => n.tag === 'option').some(n => n.props.value === 'coluna:informar'))
  // Um SQL ligado: forma curta.
  {
    const { tela, target, lido } = montar({ campo: 'corpo', sqlNames: ['SQL_1'], allowCustomSqlName: false })
    tela.disparar(selects(tela)[0], 'onChange', { target: { value: 'coluna:informar' } })
    assert(tela.botoes('Inserir')[0].props.disabled)
    tela.disparar(inputs(tela)[0], 'onChange', { target: { value: 'to tal' } })
    assert(tela.botoes('Inserir')[0].props.disabled)
    assert(inputs(tela)[0].props.error)
    tela.disparar(inputs(tela)[0], 'onChange', { target: { value: 'total' } })
    tela.clicar(tela.botoes('Inserir')[0])
    assert.equal(lido(), 'A{coluna:total}B')
    assert.equal(target.selectionStart, 15)
  }
  // Dois SQL: só libera depois de escolher o nó.
  {
    const { tela, lido } = montar({ campo: 'assunto', sqlNames: ['SQL_1', 'SQL_2'], allowCustomSqlName: false })
    tela.disparar(selects(tela)[0], 'onChange', { target: { value: 'coluna:informar' } })
    tela.disparar(inputs(tela)[0], 'onChange', { target: { value: 'mes' } })
    assert(tela.botoes('Inserir')[0].props.disabled)
    tela.disparar(selects(tela)[1], 'onChange', { target: { value: 'SQL_2' } })
    assert(!tela.botoes('Inserir')[0].props.disabled)
    tela.clicar(tela.botoes('Inserir')[0])
    assert.equal(lido(), 'A{coluna:SQL_2.mes}B')
  }
  // Modelo do Admin (fluxo desconhecido): nó opcional em campo livre.
  {
    const { tela, lido } = montar({ campo: 'corpo' })
    tela.disparar(selects(tela)[0], 'onChange', { target: { value: 'coluna:informar' } })
    tela.disparar(inputs(tela)[0], 'onChange', { target: { value: 'total' } })
    tela.disparar(inputs(tela)[1], 'onChange', { target: { value: 'nó ruim' } })
    assert(tela.botoes('Inserir')[0].props.disabled)
    tela.disparar(inputs(tela)[1], 'onChange', { target: { value: 'CONSULTA.1' } })
    tela.clicar(tela.botoes('Inserir')[0])
    assert.equal(lido(), 'A{coluna:CONSULTA.1.total}B')
  }
  console.log(JSON.stringify({ ok: true }))
} finally {
  fs.rmSync(tmp, { recursive: true, force: true })
}
