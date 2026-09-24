// C2 da spec ferramenta-banco: executa de verdade (sucrase) o realce de SQL,
// as funções de banco de `lib/agentes.ts` e a linguagem do bloco de código em
// `lib/markdownLlm.ts`.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const root = path.resolve(__dirname, '../..')
const { transform } = require(path.join(root, 'ui-react/node_modules/sucrase'))
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'agentes-banco-'))
const carregar = nome => {
  const fonte = fs.readFileSync(path.join(root, `ui-react/src/lib/${nome}.ts`), 'utf8')
  const dest = path.join(tmp, `${nome}.js`)
  fs.writeFileSync(dest, transform(fonte, { transforms: ['typescript', 'imports'], production: true }).code)
  return require(dest)
}
try {
  const realce = carregar('sqlRealce')
  const lib = carregar('agentes')
  const md = carregar('markdownLlm')

  // ── realce: juntar os tokens devolve a entrada EXATA ──
  const amostras = [
    "SELECT TOP 3 p.nome, COUNT(*) AS adesoes\nFROM dbo.adesao a JOIN dbo.plano p ON p.id = a.plano_id\n"
      + "WHERE a.data >= '2026-01-01' GROUP BY p.nome ORDER BY 2 DESC",
    "SELECT N'ação', 'it''s', [minha coluna], \"x\"\"y\", 0xFF, 1.5e-3 -- fim\n/* bloco */ FROM t",
    "SELECT 'sem fim", "/* sem fim", "[sem fim", '', '   \t\n', 'select @x, #t, ##g, $y',
    'SELECT 1DELETE', 'SELECT ação FROM tabela_ç',
  ]
  for (const sql of amostras) {
    assert.equal(realce.tokensSql(sql).map(t => t.texto).join(''), sql, JSON.stringify(sql))
  }
  const tipos = sql => realce.tokensSql(sql).filter(t => t.tipo !== 'outro').map(t => `${t.tipo}:${t.texto}`)
  assert.deepEqual(tipos("select nome from t where x = 'a -- b' and n > 10 -- c"), [
    'palavra:select', 'nome:nome', 'palavra:from', 'nome:t', 'palavra:where', 'nome:x', "texto:'a -- b'",
    'palavra:and', 'nome:n', 'numero:10', 'comentario:-- c'])
  assert.deepEqual(tipos("N'x' [select] \"from\" count(*)"), ["texto:N'x'", 'nome:[select]', 'nome:"from"', 'palavra:count'])
  assert.deepEqual(tipos('coluna_N1 N1'), ['nome:coluna_N1', 'nome:N1'], "N sem aspas não é literal")
  assert.deepEqual(tipos('SELECT 1e5, 0x1F, 12'), ['palavra:SELECT', 'numero:1e5', 'numero:0x1F', 'numero:12'])
  assert.deepEqual(tipos('t1.c2'), ['nome:t1', 'nome:c2'], 'dígito colado a nome não é número')

  // ── rodapé ──
  assert.equal(realce.resumoConsulta({ linhas: 3, ms: 812 }), '3 linhas · 812 ms')
  assert.equal(realce.resumoConsulta({ linhas: 1, ms: 1500 }), '1 linha · 1,5 s')
  assert.equal(realce.resumoConsulta({ linhas: 100, havia_mais: true }), '100+ linhas (havia mais)')
  assert.equal(realce.resumoConsulta({}), '')

  // ── consultas executadas: só as que RODARAM, com o SQL intacto ──
  const arts = [
    { ferramenta: 'banco_estrutura', args: { conexao: 'dw', banco: 'PREV' }, banco: { conexao: 'dw', banco: 'PREV', linhas: 4, ms: 9 } },
    { ferramenta: 'banco_consulta', args: { conexao: 'dw', banco: 'PREV', sql: 'SELECT 1' }, banco: { conexao: 'dw', banco: 'PREV', linhas: 1, ms: 5 } },
    { ferramenta: 'banco_consulta', args: { sql: 'DELETE FROM t' }, banco: { conexao: 'dw', banco: 'PREV', recusada: true } },
    { ferramenta: 'banco_consulta', args: { sql: 'SELECT * FROM nao' }, banco: { conexao: 'dw', banco: 'PREV', erro: true }, falhou: 'banco_objeto_inexistente' },
    { ferramenta: 'banco_consulta', args: { sql: 'SELECT 2' }, recusada: 'fora_do_agente' },
    { ferramenta: 'dsjob', args: { comando: 'ljobs' } },
  ]
  assert.deepEqual(lib.consultasExecutadas(arts), [{ sql: 'SELECT 1', meta: arts[1].banco }])
  assert.deepEqual(lib.consultasExecutadas(undefined), [])
  assert.equal(lib.rotuloDoArtefato(arts[1]), 'banco dw/PREV')
  assert.equal(lib.rotuloDoArtefato(arts[0]), 'estrutura do banco dw/PREV')
  assert.equal(lib.rotuloDoArtefato(arts[5]), 'DataStage ao vivo')
  assert.equal(lib.rotuloDoArtefato({ ferramenta: 'nova' }), 'nova')

  // ── pares ──
  const a = { conexao: 'dw', banco: 'PREV' }
  assert.ok(lib.mesmoPar(a, { conexao: 'dw', banco: 'prev' }), 'banco sem diferenciar maiúsculas')
  assert.ok(!lib.mesmoPar(a, { conexao: 'DW', banco: 'PREV' }), 'conexão pelo nome exato')
  assert.deepEqual(lib.alternarPar([], a), [a])
  assert.deepEqual(lib.alternarPar([a], { conexao: 'dw', banco: 'prev' }), [])
  assert.equal(lib.usaBanco(['base']), false)
  assert.equal(lib.usaBanco(['banco_consulta']), true)

  // ── normalização com a allowlist inteira (DataStage + banco) ──
  const ALLOW = ['resolver_projeto', 'base', 'dsx_consulta', 'dsjob', 'isx_extrair', 'banco_estrutura', 'banco_consulta']
  assert.deepEqual(lib.normalizarFerramentas(['banco_consulta', 'banco_estrutura'], ALLOW), ['banco_estrutura', 'banco_consulta'])
  assert.deepEqual(lib.normalizarFerramentas(['banco_consulta', 'base'], ALLOW), ['resolver_projeto', 'base', 'banco_consulta'])

  // ── problemas: banco sem par; por perfil vale com banco ──
  const base = { id: 'assistente', nome: 'A', descricao: 'd', acesso: 'perfil', perfis: ['desenvolvedor'],
                 ferramentas: ['banco_estrutura', 'banco_consulta'], prompt: 'p', motivo: 'criação', bancos: [a], mascarar_dados: true }
  const op = { criacao: true, ferramentasServidor: ['dsx_consulta', 'dsjob', 'isx_extrair'], perfisProibidos: ['consulta'] }
  assert.deepEqual(lib.problemasDoAgente(base, op), [])
  assert.match(lib.problemasDoAgente({ ...base, bancos: [] }, op).join(' | '), /ao menos um banco/)
  assert.deepEqual(lib.problemasDoAgente({ ...base, ferramentas: [], bancos: [] }, op), [])

  // ── markdown: a linguagem do bloco é guardada (e só quando existe) ──
  const blocos = md.parseMarkdown('Veja:\n```sql\nSELECT 1\n```\n```\ncru\n```\n``` SQL extra\nx\n```')
  assert.deepEqual(blocos.filter(b => b.tipo === 'codigo'), [
    { tipo: 'codigo', texto: 'SELECT 1', linguagem: 'sql' },
    { tipo: 'codigo', texto: 'cru' },
    { tipo: 'codigo', texto: 'x', linguagem: 'sql' },
  ])

  // ── projeto e textos do chat conforme as ferramentas ──
  assert.equal(lib.semProjetoDataStage({ ferramentas: [] }), true, 'só conversa')
  assert.equal(lib.semProjetoDataStage({ ferramentas: ['banco_consulta'] }), true, 'só banco')
  assert.equal(lib.semProjetoDataStage({ ferramentas: ['banco_consulta', 'base'] }), false)
  assert.equal(lib.semProjetoDataStage({}), false, 'API antiga = DataStage')
  assert.match(lib.textosDoChat(undefined).convite, /DataStage/)
  assert.match(lib.textosDoChat(['resolver_projeto', 'base', 'banco_consulta']).convite, /DataStage/)
  assert.match(lib.textosDoChat(['banco_estrutura', 'banco_consulta']).convite, /bancos liberados/)
  assert.doesNotMatch(lib.textosDoChat(['banco_consulta']).placeholder, /job/)
  assert.equal(lib.textosDoChat([]).exemplo, null)

  // ── galeria de agentes ──
  assert.deepEqual(lib.capacidadesDoAgente({}), ['datastage'], 'API antiga = DataStage')
  assert.deepEqual(lib.capacidadesDoAgente({ ferramentas: [] }), ['conversa'])
  assert.deepEqual(lib.capacidadesDoAgente({ ferramentas: ['banco_consulta'] }), ['banco'])
  assert.deepEqual(lib.capacidadesDoAgente({ ferramentas: ['resolver_projeto', 'base', 'banco_estrutura'] }),
                   ['datastage', 'banco'])
  const ags = [
    { id: 'datastage', nome: 'Mapeamento DataStage', descricao: 'Explica fluxos e lineage' },
    { id: 'analista_dw', nome: 'Analista do DW', descricao: 'Responde sobre adesões', ferramentas: ['banco_consulta'] },
    { id: 'padroes', nome: 'Padrões de código', descricao: 'Tira dúvidas de convenções', ferramentas: [] },
  ]
  assert.deepEqual(lib.filtrarAgentes(ags, '').map(a => a.id), ['datastage', 'analista_dw', 'padroes'])
  assert.deepEqual(lib.filtrarAgentes(ags, 'ADESOES').map(a => a.id), ['analista_dw'], 'sem acento nem caixa')
  assert.deepEqual(lib.filtrarAgentes(ags, 'banco').map(a => a.id), ['analista_dw'], 'pela capacidade')
  assert.deepEqual(lib.filtrarAgentes(ags, 'padroes conv').map(a => a.id), ['padroes'], 'todas as palavras')
  assert.deepEqual(lib.filtrarAgentes(ags, 'xyz'), [])
  assert.deepEqual(lib.filtrarAgentes(ags, 'datastage').map(a => a.id), ['datastage'], 'ordem do catálogo')
  const ultimo = lib.chaveDoUltimoAgente(' cvp123 ')
  assert.ok(ultimo.startsWith(lib.PREFIXO_CONVERSA_AGENTE), 'o logout apaga junto')
  for (const id of ['abc', 'ultimo', 'a_ultimo', 'x_1']) {
    assert.notEqual(lib.chaveDaConversa(id, 'CVP123'), ultimo, `colide com o agente ${id}`)
  }

  console.log('ok')
} finally {
  fs.rmSync(tmp, { recursive: true, force: true })
}
