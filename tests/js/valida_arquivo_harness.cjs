const fs = require('fs')
const path = require('path')
const assert = require('assert')
const root = path.resolve(__dirname, '../..')
const { transform } = require(path.join(root, 'ui-react/node_modules/sucrase'))
global.crypto = require('crypto').webcrypto
const output = { exports: {} }
const js = transform(fs.readFileSync(path.join(root, 'ui-react/src/lib/validaArquivo.ts'), 'utf8'), { transforms: ['typescript', 'imports'] }).code
new Function('module', 'exports', js)(output, output.exports)
const v = output.exports
const cfg = v.novaValidacao(); cfg.ssh_conn_id = 'SSH'; cfg.entradas[0].alvo = 'A'
const nodes = [{ id: 'V', type: 'valida_arquivo', position: { x: 0, y: 0 }, data: { name: 'V', valida_arquivo: cfg } },
  { id: 'A', type: 'etapa', position: { x: 100, y: 0 }, data: { name: 'A', type: 'shell' } }]
const edges = [{ id: 'V-A', source: 'V', target: 'A' }]
const copy = () => JSON.parse(JSON.stringify(nodes))
let after = copy(); after[0].data.valida_arquivo.entradas[0].arquivo = 'novo.csv'; after[0].data.valida_arquivo.revisao = 2
assert.equal(v.exigePublicacaoValida(nodes, after, edges, edges), false)
for (const change of [n => n[0].data.valida_arquivo.ssh_conn_id = 'OUTRO', n => n[0].data.valida_arquivo.entradas[0].alvo = 'B', n => n[0].data.valida_arquivo.entradas.push(v.novaEntrada()), n => n[1].data.command = 'novo']) {
  after = copy(); change(after); assert.equal(v.exigePublicacaoValida(nodes, after, edges, edges), true)
}
assert.equal(v.exigePublicacaoValida(nodes, nodes, edges, []), true)
const renamed = v.renomearAlvo(nodes[0], 'A', 'B')
assert.equal(renamed.data.valida_arquivo.entradas[0].alvo, 'B')
assert.equal(nodes[0].data.valida_arquivo.entradas[0].alvo, 'A')
assert.equal(v.grafoValidacao(nodes, edges)[1].depends_on_jobs[0], 'V')
const second = v.novaEntrada(); assert.notEqual(second.entrada_id, cfg.entradas[0].entrada_id)
const ordered = v.ordenarEntradas([second, cfg.entradas[0]])
assert.equal(ordered[1].entrada_id, cfg.entradas[0].entrada_id); assert.equal(ordered[1].ordem, 1)
console.log(JSON.stringify({ publicacao: true, renomear: true, ordem: true, grafo: true }))
