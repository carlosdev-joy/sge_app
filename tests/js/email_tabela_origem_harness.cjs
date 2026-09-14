// Executa o helper TypeScript real, sem React, Airflow, banco ou envio de e-mail.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const Module = require('node:module')
const root = path.resolve(__dirname, '../..')
const { transform } = require(path.join(root, 'ui-react/node_modules/sucrase'))
const source = path.join(root, 'ui-react/src/lib/emailTabelaOrigem.ts')
const compiled = new Module(source)
compiled._compile(transform(fs.readFileSync(source, 'utf8'), { transforms: ['typescript', 'imports'] }).code, source)
const { sqlDiretosDoEmail: sql, avisosTabelaEmail: avisos } = compiled.exports
const nodes = [
  { id: 'SQL_1', type: 'sql', data: { name: 'TITULO_DIFERENTE' } },
  { id: 'sql.nome-2', type: 'sql' }, { id: 'Decisao', type: 'decisao' },
  { id: 'Email', type: 'email' }, { id: 'Job', type: 'etapa' },
]
const link = (source, target = 'Email') => ({ source, target })
assert.deepEqual(sql('Email', nodes, []), [])
assert.deepEqual(sql('Email', nodes, [link('SQL_1')]), ['SQL_1'])
assert.deepEqual(sql('Email', nodes, [
  { ...link('SQL_1'), data: { branch: true } },
  { ...link('sql.nome-2'), data: { branch: 'sim' } },
]), [])
assert.deepEqual(sql('Email', nodes, [{ ...link('SQL_1'), data: { branch: false } }]), ['SQL_1'])
assert.deepEqual(sql('Email', nodes, [link('sql.nome-2'), link('SQL_1'), link('SQL_1'), link('Job'), link('REMOVIDO'), link('SQL_1', 'OutroEmail')]), ['sql.nome-2', 'SQL_1'])
assert.deepEqual(sql('Email', nodes, [link('SQL_1', 'Decisao'), link('Decisao')]), [])
assert.deepEqual(avisos('Sem tabela {linhas} {Tabela} {TABELA:SQL_1}', []), [])
assert.equal(avisos('{tabela}', []).length, 1)
assert.deepEqual(avisos('{tabela} {tabela:SQL_1}', ['SQL_1']), [])
assert.equal(avisos('{tabela}', ['SQL_1', 'sql.nome-2']).length, 1)
assert.deepEqual(avisos('{tabela}', ['SQL_1', 'SQL_1']), [])
assert.deepEqual(avisos('{tabela:sql.nome-2}', ['SQL_1', 'sql.nome-2']), [])
assert.equal(avisos('{tabela:sql_1}', ['SQL_1']).length, 1)
assert.equal(avisos('{tabela:REMOVIDO} {tabela:REMOVIDO}', ['SQL_1']).length, 1)
assert.equal(avisos('{tabela} {tabela:REMOVIDO} {tabela:SQL_1}', ['SQL_1', 'sql.nome-2']).length, 2)
assert.equal(avisos('{tabela} {tabela:REMOVIDO}', []).length, 2)
// Renomear e religar atualiza as origens e denuncia o marcador antigo sem reescrevê-lo.
const renamed = nodes.map(node => node.id === 'SQL_1' ? { ...node, id: 'SQL_novo' } : node)
const texto = '{tabela:SQL_1}'
assert.deepEqual(sql('Email', renamed, [link('SQL_novo')]), ['SQL_novo'])
assert.equal(avisos(texto, sql('Email', renamed, [link('SQL_novo')])).length, 1)
assert.equal(avisos(texto, sql('Email', nodes, [link('SQL_1', 'Decisao'), link('Decisao')])).length, 1)
assert.deepEqual(avisos(texto, sql('Email', nodes, [link('SQL_1')])), [])
assert.equal(texto, '{tabela:SQL_1}')
// A análise reconhece exatamente os qualificadores aceitos pelo runtime.
for (const nome of ['', 'nome com espaço', 'á', 'a'.repeat(129)]) {
  assert.deepEqual(avisos(`{tabela:${nome}}`, []), [])
}
assert.equal(avisos(`{tabela:${'a'.repeat(128)}}`, []).length, 1)
// O runtime atual remove estes prefixos ao procurar a origem; não são nomes
// proibidos pela validação, por isso o painel orienta sem bloquear a edição.
for (const nome of ['log_end_SQL', 'log_start_SQL']) {
  for (const marcador of ['{tabela}', `{tabela:${nome}}`, `{tabela} {tabela:${nome}}`]) {
    const resultado = avisos(marcador, [nome, nome])
    assert.equal(resultado.length, 1)
    assert(resultado[0].includes(`pode não localizar a tabela de ${nome}`))
    assert(resultado[0].includes('republique o fluxo'))
  }
  assert.deepEqual(avisos('{linhas} {Tabela}', [nome]), [])
  assert.deepEqual(avisos('{tabela:SQL_OUTRO}', [nome, 'SQL_OUTRO']), [])
  const ausente = avisos(`{tabela:${nome}}`, ['SQL_OUTRO'])
  assert.equal(ausente.length, 1)
  assert(!ausente[0].includes('prefixo'))
}
for (const nome of ['LOG_END_SQL', 'Log_start_SQL', 'sql_log_end_X', 'log_end', 'log_start']) {
  assert.deepEqual(avisos(`{tabela} {tabela:${nome}}`, [nome]), [])
}
console.log(JSON.stringify({ ok: true, scenarios: ['zero', 'um', 'dois', 'intermediario', 'rename', 'reconnect', 'case', 'mistura', 'dedup', 'runtime-regex'] }))
