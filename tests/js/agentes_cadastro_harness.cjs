// B3 da spec admin: executa `lib/agentes.ts` de verdade (sucrase) e prende as
// funções puras do cadastro de agentes — as que antecipam na tela o que o
// backend recusaria (422).
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const root = path.resolve(__dirname, '../..')
const { transform } = require(path.join(root, 'ui-react/node_modules/sucrase'))
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'agentes-cadastro-'))
try {
  const fonte = fs.readFileSync(path.join(root, 'ui-react/src/lib/agentes.ts'), 'utf8')
  const dest = path.join(tmp, 'agentes.js')
  fs.writeFileSync(dest, transform(fonte, { transforms: ['typescript', 'imports'], production: true }).code)
  const lib = require(dest)
  const ALLOW = ['resolver_projeto', 'base', 'dsx_consulta', 'dsjob', 'isx_extrair']
  const SERVIDOR = ['dsx_consulta', 'dsjob', 'isx_extrair']

  // só conversa: só quando a API manda a lista E ela está vazia
  assert.equal(lib.ehSoConversa({ ferramentas: [] }), true)
  assert.equal(lib.ehSoConversa({ ferramentas: ['base'] }), false)
  assert.equal(lib.ehSoConversa({}), false, 'API anterior à Fase B (sem o campo) = DataStage, com tudo')

  // normalização igual à do backend
  assert.deepEqual(lib.normalizarFerramentas(['base'], ALLOW), ['resolver_projeto', 'base'])
  assert.deepEqual(lib.normalizarFerramentas(['isx_extrair', 'base', 'rm_rf'], ALLOW), ['resolver_projeto', 'base', 'isx_extrair'])
  assert.deepEqual(lib.normalizarFerramentas([], ALLOW), [])
  assert.deepEqual(lib.normalizarFerramentas(['resolver_projeto'], ALLOW), ['resolver_projeto'])

  // id
  for (const ok of ['assistente', 'abc', 'a_1', 'x'.repeat(30)]) assert.ok(lib.RE_ID_AGENTE.test(ok), ok)
  for (const ruim of ['ab', 'A_b', '1abc', 'com-hifen', 'x'.repeat(31), 'abc\n']) assert.ok(!lib.RE_ID_AGENTE.test(ruim), JSON.stringify(ruim))
  for (const r of ['datastage', 'admin', 'catalogo', 'status', 'conversas', 'propostas', 'aprendizados', 'curador', 'foo_curador']) {
    assert.ok(lib.idReservado(r), r)
  }
  assert.ok(!lib.idReservado('assistente'))

  // problemas antecipados
  const base = { id: 'assistente', nome: 'Assistente', descricao: 'd', acesso: 'manual', perfis: ['desenvolvedor'],
                 ferramentas: [], prompt: 'p', motivo: 'criação' }
  const op = { criacao: true, ferramentasServidor: SERVIDOR, perfisProibidos: ['consulta'] }
  assert.deepEqual(lib.problemasDoAgente(base, op), [])
  const com = (mud, o = op) => lib.problemasDoAgente({ ...base, ...mud }, o).join(' | ')
  assert.match(com({ id: 'datastage' }), /reservado/)
  assert.match(com({ id: 'X' }), /Id:/)
  assert.match(com({ perfis: [] }), /ao menos um perfil/)
  assert.match(com({ perfis: ['desenvolvedor', 'consulta'] }), /consulta não pode/)
  assert.match(com({ acesso: 'perfil', ferramentas: ['resolver_projeto', 'dsjob'] }), /servidor \(dsjob\)/)
  assert.equal(com({ acesso: 'perfil', ferramentas: ['resolver_projeto', 'base'] }), '')
  assert.match(com({ prompt: '  ' }), /prompt inicial/)
  assert.match(com({ motivo: 'x' }), /motivo/)
  assert.match(com({ nome: 'x'.repeat(101) }), /100/)
  // edição: sem id, prompt e motivo
  assert.deepEqual(lib.problemasDoAgente({ ...base, id: '', prompt: '', motivo: '' }, { ...op, criacao: false }), [])

  // grant de agente para perfil que não pode usá-lo (modal de permissões extras)
  const ags = [
    { nome: 'Mapeamento DataStage', recurso: 'agente_datastage', recurso_curador: 'agente_curador', perfis: ['desenvolvedor'] },
    { nome: 'Assistente', recurso: 'agente_assistente', recurso_curador: null, perfis: ['analista', 'desenvolvedor'] },
  ]
  assert.equal(lib.agenteInelegivel('agente_datastage', 'desenvolvedor', ags), null)
  assert.equal(lib.agenteInelegivel('agente_datastage', 'operador', ags), 'Mapeamento DataStage')
  assert.equal(lib.agenteInelegivel('agente_curador', 'analista', ags), 'Mapeamento DataStage', 'curador segue o perfil do agente')
  assert.equal(lib.agenteInelegivel('agente_assistente', 'analista', ags), null)
  assert.equal(lib.agenteInelegivel('agente_assistente', 'consulta', ags), 'Assistente')
  assert.equal(lib.agenteInelegivel('agente_datastage', 'admin', ags), null, 'admin usa tudo')
  assert.equal(lib.agenteInelegivel('tela_jobs', 'operador', ags), null, 'recurso que não é de agente')
  assert.equal(lib.agenteInelegivel('agente_datastage', 'operador', []), null, 'lista ainda não carregou: sem sinal')

  console.log('ok')
} finally {
  fs.rmSync(tmp, { recursive: true, force: true })
}
