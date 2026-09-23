// A2 + BK-1 da spec admin: executa `lib/agentes.ts` de verdade (sucrase) e
// prende as funções puras do editor de prompt e do histórico de versões.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const root = path.resolve(__dirname, '../..')
const { transform } = require(path.join(root, 'ui-react/node_modules/sucrase'))
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'agentes-prompt-'))
try {
  const fonte = fs.readFileSync(path.join(root, 'ui-react/src/lib/agentes.ts'), 'utf8')
  const dest = path.join(tmp, 'agentes.js')
  fs.writeFileSync(dest, transform(fonte, { transforms: ['typescript', 'imports'], production: true }).code)
  const lib = require(dest)

  // motivo: mesma régua do backend (UTF-16 — String.length do JS já é UTF-16)
  assert.equal(lib.motivoValido('ab'), false)
  assert.equal(lib.motivoValido('  abc  '), true)
  assert.equal(lib.motivoValido('x'.repeat(200)), true)
  assert.equal(lib.motivoValido('x'.repeat(201)), false)
  assert.equal(lib.motivoValido('😀'.repeat(100)), true, '100 emojis = 200 unidades UTF-16')
  assert.equal(lib.motivoValido('😀'.repeat(101)), false, '101 emojis = 202 unidades — o backend recusa')

  // duração da vigência
  assert.equal(lib.duracaoDaVigencia(null), '—')
  assert.equal(lib.duracaoDaVigencia(undefined), '—')
  assert.equal(lib.duracaoDaVigencia(-5), '—')
  assert.equal(lib.duracaoDaVigencia(30), 'menos de 1 min')
  assert.equal(lib.duracaoDaVigencia(60 * 45), '45 min')
  assert.equal(lib.duracaoDaVigencia(3600 * 2), '2 h')
  assert.equal(lib.duracaoDaVigencia(3600 * 3 + 60 * 20), '3 h 20 min')
  assert.equal(lib.duracaoDaVigencia(86400 * 2), '2 d')
  assert.equal(lib.duracaoDaVigencia(86400 * 2 + 3600 * 4 + 59), '2 d 4 h')

  // tempo médio de resposta
  assert.equal(lib.tempoMedio(null), '—')
  assert.equal(lib.tempoMedio(850), '850 ms')
  assert.equal(lib.tempoMedio(12400), '12,4 s')

  // data do BANCO, sem conversão de fuso (o banco está em BRT)
  assert.equal(lib.dataHoraCurta('2026-09-23 14:02:59'), '23/09/2026 14:02')
  assert.equal(lib.dataHoraCurta('2026-09-23T08:05:00'), '23/09/2026 08:05')
  assert.equal(lib.dataHoraCurta(null), '—')
  assert.equal(lib.dataHoraCurta('lixo'), '—')

  console.log('ok')
} finally {
  fs.rmSync(tmp, { recursive: true, force: true })
}
