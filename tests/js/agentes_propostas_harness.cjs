// F5 dos agentes: executa `lib/agentes.ts` de verdade (transpilado com sucrase)
// e prende as funções puras que a tela usa ao decidir uma proposta.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const root = path.resolve(__dirname, '../..')
const { transform } = require(path.join(root, 'ui-react/node_modules/sucrase'))
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'agentes-propostas-'))
try {
  const fonte = fs.readFileSync(path.join(root, 'ui-react/src/lib/agentes.ts'), 'utf8')
  const dest = path.join(tmp, 'agentes.js')
  fs.writeFileSync(dest, transform(fonte, { transforms: ['typescript', 'imports'], production: true }).code)
  const lib = require(dest)

  const proposta = (id, estado = 'pendente') => ({
    id, ds_project: 'BI_CVP', job_name: 'JobX', tipo: 'lineage', chave: `c${id}`, valor: 'v',
    evidencia: 'e', motivo: null, estado, criada_em: null, decidida_por: null, decidida_em: null, fato_id: null,
  })
  const mensagens = [
    { id: 'u1', papel: 'user', texto: 'oi' },
    { id: 'a1', papel: 'assistant', texto: 'r', propostas: [proposta(1), proposta(2)] },
    { id: 'a2', papel: 'assistant', texto: 'r2' },
  ]

  // troca só a proposta decidida, na mensagem certa, sem mutar a original
  const depois = lib.aplicarDecisao(mensagens, { ...proposta(2), estado: 'aprovada', decidida_por: 'DEV1' })
  assert.notEqual(depois, mensagens)
  assert.equal(depois[1].propostas[0].estado, 'pendente')
  assert.equal(depois[1].propostas[1].estado, 'aprovada')
  assert.equal(depois[1].propostas[1].decidida_por, 'DEV1')
  assert.equal(mensagens[1].propostas[1].estado, 'pendente', 'não pode mutar o estado anterior do React')
  assert.equal(depois[0], mensagens[0], 'mensagem sem a proposta é a MESMA referência')
  assert.equal(depois[2], mensagens[2])

  // proposta que não está na tela (a conversa mudou): mesma referência —
  // é o sinal para a página NÃO regravar o localStorage
  assert.equal(lib.aplicarDecisao(mensagens, proposta(99)), mensagens)
  assert.equal(lib.aplicarDecisao([], proposta(1)).length, 0)

  // valor: string direto, objeto como JSON legível, nada levanta
  assert.equal(lib.valorDaProposta('carrega clientes'), 'carrega clientes')
  assert.equal(lib.valorDaProposta({ a: 1 }), '{\n  "a": 1\n}')
  const ciclo = {}; ciclo.eu = ciclo
  assert.equal(typeof lib.valorDaProposta(ciclo), 'string')
  assert.equal(lib.valorDaProposta(undefined), '')

  // rótulos cobrem todos os tipos e estados do backend
  for (const t of ['stage', 'parametro', 'tabela', 'campo', 'lineage', 'descricao']) assert(lib.TIPOS_PROPOSTA[t], t)
  for (const e of ['pendente', 'aprovada', 'recusada', 'expirada']) assert(lib.ESTADO_PROPOSTA[e], e)
  console.log('ok')
} finally {
  fs.rmSync(tmp, { recursive: true, force: true })
}
