// Bancada do par da publicação no pedido de execução (EOC-F3, 2.22.2).
// Transpila ui-react/src/lib/workspaceExecution.ts como está (o arquivo só
// importa tipos) e confere o contrato puro: par fixado em campos próprios, fora
// de conf; par incompleto/malformado recusado; chaves reservadas fora dos
// parâmetros; o snapshot da corrida selecionada nunca vira publicação esperada.
// Executar: node tests/js/workspace_run_publication_harness.cjs
'use strict'
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '..', '..')
const ts = require(require.resolve('typescript', { paths: [path.join(root, 'ui-react')] }))
const source = fs.readFileSync(path.join(root, 'ui-react', 'src', 'lib', 'workspaceExecution.ts'), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } })
const loaded = { exports: {} }
new Function('module', 'exports', outputText)(loaded, loaded.exports)
const lib = loaded.exports

const RUN = 'workspace__0f8e2c1a-7b3d-4c5e-9a1b-2c3d4e5f6a7b'
const PAIR = Object.freeze({ versionId: '3f2504e0-4f89-11d3-9a0c-0305e82c3301', contentHash: 'ab'.repeat(32) })
const FORM = Object.freeze({ odate: '2026-10-13', logicalDate: '', extraConf: { lote: 7 } })

test('par confirmado vai em campos próprios; conf não leva metadado interno', () => {
 const built = lib.buildRunRequest(FORM, RUN, PAIR)
 assert.equal(built.ok, true)
 assert.deepEqual(built.body, { conf: { lote: 7, data_referencia: '2026-10-13' }, dag_run_id: RUN, expected_version_id: PAIR.versionId, expected_content_hash: PAIR.contentHash })
 for (const field of lib.RUN_PUBLICATION_FIELDS) assert.equal(Object.keys(built.body.conf).includes(field), false)
})

test('nova tentativa com o mesmo identificador e o mesmo par gera o mesmo corpo', () => {
 assert.equal(JSON.stringify(lib.buildRunRequest({ ...FORM }, RUN, { ...PAIR })), JSON.stringify(lib.buildRunRequest(FORM, RUN, PAIR)))
})

test('sem par confirmado o pedido sai sem os campos e o adaptador decide', () => {
 const built = lib.buildRunRequest(FORM, RUN, null)
 assert.equal(built.ok, true)
 for (const field of lib.RUN_PUBLICATION_FIELDS) assert.equal(field in built.body, false)
 assert.deepEqual(lib.buildRunRequest(FORM, RUN), built)
})

test('par incompleto ou malformado não vira pedido', () => {
 const bad = [
  { versionId: PAIR.versionId },
  { contentHash: PAIR.contentHash },
  { ...PAIR, versionId: `{${PAIR.versionId}}` },
  { ...PAIR, versionId: PAIR.versionId.replace(/-/g, '') },
  { ...PAIR, versionId: ` ${PAIR.versionId}` },
  { ...PAIR, contentHash: PAIR.contentHash.slice(1) },
  { ...PAIR, contentHash: `${PAIR.contentHash}0` },
  { ...PAIR, contentHash: 'g'.repeat(64) },
  { ...PAIR, contentHash: `${PAIR.contentHash.slice(1)}\n` },
  // Tamanho exato seguido de quebra de linha: `$` sem a flag m não aceita "\n" final.
  { ...PAIR, contentHash: `${PAIR.contentHash}\n` },
  { ...PAIR, versionId: `${PAIR.versionId}\n` },
  { ...PAIR, contentHash: `${PAIR.contentHash}\r\n` },
  { ...PAIR, versionId: 7 },
 ]
 for (const pair of bad) {
  assert.equal(lib.confirmedPublication(pair), null, JSON.stringify(pair))
  const built = lib.buildRunRequest(FORM, RUN, pair)
  assert.deepEqual([built.ok, built.field], [false, 'publication'], JSON.stringify(pair))
 }
})

test('contexto sem par confirmado (pendente ou fora do workspace) não produz par', () => {
 for (const published of [null, undefined, {}, { versionId: null, contentHash: null }, { versionId: PAIR.versionId, contentHash: null }]) assert.equal(lib.confirmedPublication(published), null)
 assert.deepEqual(lib.confirmedPublication({ definition: {}, layout: {}, readOnlyReasons: [], ...PAIR }), PAIR)
})

test('snapshot da corrida selecionada nunca vira publicação esperada', () => {
 // A leitura da execução devolve versionId e número da versão da corrida, sem hash.
 assert.equal(lib.confirmedPublication({ versionId: PAIR.versionId, number: 4, definition: {}, layout: {} }), null)
})

test('chaves reservadas não entram nos parâmetros da execução', () => {
 for (const field of lib.RUN_PUBLICATION_FIELDS) {
  assert.equal(lib.parseAdvancedConf(JSON.stringify({ [field]: PAIR.versionId, lote: 1 })).ok, false)
  const built = lib.buildRunRequest({ ...FORM, extraConf: { [field]: PAIR.versionId } }, RUN, PAIR)
  assert.deepEqual([built.ok, built.field], [false, 'conf'])
 }
})

test('mudança da publicação exibida é percebida; caixa do hexadecimal não', () => {
 assert.equal(lib.samePublication(PAIR, { versionId: PAIR.versionId.toUpperCase(), contentHash: PAIR.contentHash.toUpperCase() }), true)
 assert.equal(lib.samePublication(PAIR, { ...PAIR, contentHash: 'cd'.repeat(32) }), false)
 assert.equal(lib.samePublication(PAIR, { ...PAIR, versionId: '3f2504e0-4f89-11d3-9a0c-0305e82c3302' }), false)
 assert.equal(lib.samePublication(PAIR, null), false)
 assert.equal(lib.samePublication(null, PAIR), false)
 assert.equal(lib.samePublication(null, null), true)
})

test('a tela entrega ao diálogo o par da mesma publicação que desenha', () => {
 // Contrato de texto: desenho e par vêm do mesmo `data.published` do contexto, nunca do snapshot da corrida.
 const page = fs.readFileSync(path.join(root, 'ui-react', 'src', 'pages', 'PipelineWorkspace.tsx'), 'utf8')
 const operations = page.slice(page.indexOf('<WorkspaceOperations '), page.indexOf('/>', page.indexOf('<WorkspaceOperations ')))
 assert.match(operations, /definition=\{data\.published\.definition\}/)
 assert.match(operations, /publication=\{confirmedPublication\(data\.published\)\}/)
})

test('sessão ou corrida selecionada diferente mudam o escopo do pedido', () => {
 const base = { token: 't1', name: 'p', date: '2026-10-13', runId: 'r1', capabilities: [true] }
 const scope = lib.operationScope(base)
 assert.notEqual(lib.operationScope({ ...base, token: 't2' }), scope)
 assert.notEqual(lib.operationScope({ ...base, runId: 'r2' }), scope)
})
