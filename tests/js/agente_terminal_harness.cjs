// Lógica pura do agente Terminal (F1 da spec docs/spec-agente-terminal.md):
// executa `lib/terminalComando.ts` e `lib/terminalSimulado.ts` de verdade (sucrase).
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const root = path.resolve(__dirname, '../..')
const { transform } = require(path.join(root, 'ui-react/node_modules/sucrase'))
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'agente-terminal-'))
const tr = src => transform(src, { transforms: ['typescript', 'imports'], production: true }).code
for (const n of ['terminalComando', 'terminalSimulado']) {
  fs.writeFileSync(path.join(tmp, `${n}.js`), tr(fs.readFileSync(path.join(root, `ui-react/src/lib/${n}.ts`), 'utf8')))
}
const L = require(path.join(tmp, 'terminalComando.js'))
const S = require(path.join(tmp, 'terminalSimulado.js'))
const T0 = new Date('2026-11-04T10:00:00Z')

// segundosRestantes / estadoEfetivo
assert.equal(L.segundosRestantes('2026-11-04T10:01:30Z', T0), 90)
assert.equal(L.segundosRestantes('2026-11-04T09:59:00Z', T0), 0)
assert.equal(L.segundosRestantes(null, T0), 0)
assert.equal(L.segundosRestantes('lixo', T0), 0, 'data inválida = expirado, nunca NaN')
const prop = { cmd_id: 'a', comando: 'x', servidor: 's', classe: 'escrita', estado: 'proposto', expira_em: '2026-11-04T10:02:00Z' }
assert.equal(L.estadoEfetivo(prop, T0), 'proposto')
assert.equal(L.estadoEfetivo(prop, new Date('2026-11-04T10:02:00Z')), 'expirado', 'vencida vira expirada no relógio do front')
assert.equal(L.estadoEfetivo({ ...prop, estado: 'executado' }, new Date('2030-01-01')), 'executado')

// podeDecidir: só escrita + viva + com permissão
assert.equal(L.podeDecidir(prop, T0, true), true)
assert.equal(L.podeDecidir(prop, T0, false), false, 'sem recurso de escrita não decide')
assert.equal(L.podeDecidir({ ...prop, classe: 'leitura' }, T0, true), false)
assert.equal(L.podeDecidir({ ...prop, classe: 'proibido', estado: 'bloqueado' }, T0, true), false)
assert.equal(L.podeDecidir(prop, new Date('2026-11-04T10:05:00Z'), true), false, 'expirada não decide')

// relogio
assert.equal(L.relogio(105), '1:45')
assert.equal(L.relogio(5), '0:05')
assert.equal(L.relogio(-3), '0:00')

// limitarSaida
assert.deepEqual(L.limitarSaida('a\nb\nc', 40), { texto: 'a\nb\nc', ocultas: 0 })
assert.deepEqual(L.limitarSaida('a\nb\nc\nd', 2), { texto: 'a\nb', ocultas: 2 })
assert.deepEqual(L.limitarSaida('a\r\nb\r\n', 5), { texto: 'a\nb', ocultas: 0 })
assert.deepEqual(L.limitarSaida(null), { texto: '', ocultas: 0 })
assert.equal(L.limitarSaida(Array.from({ length: 100 }, (_, i) => i).join('\n')).ocultas, 60)

// aplicarComando: troca por cmd_id, ou acrescenta
const base = [{ id: '1', papel: 'usuario', texto: 'oi' }, { id: 'c-a', papel: 'comando', comando: prop }]
const novo = L.aplicarComando(base, { ...prop, estado: 'executado' })
assert.equal(novo.length, 2)
assert.equal(novo[1].comando.estado, 'executado')
assert.equal(base[1].comando.estado, 'proposto', 'não muta o original')
assert.equal(L.aplicarComando(base, { ...prop, cmd_id: 'b' }).length, 3)

// rastro
assert.equal(L.rastro({ ...prop, estado: 'executado', decidido_por: '123', decidido_em: '2026-11-04T14:05:09Z' }), 'executado por 123 às 14:05')
assert.equal(L.rastro({ ...prop, estado: 'recusado', decidido_por: '123' }), 'recusado por 123')
assert.equal(L.rastro({ ...prop, classe: 'leitura', estado: 'executado' }), 'executado')
assert.equal(L.rastro({ ...prop, classe: 'proibido', estado: 'bloqueado' }), 'bloqueado')

// duracaoCurta / entradaValida
assert.equal(L.duracaoCurta(850), '850 ms')
assert.equal(L.duracaoCurta(1840), '1,8 s')
assert.equal(L.duracaoCurta(null), '')
assert.equal(L.entradaValida('   '), false)
assert.equal(L.entradaValida('ls'), true)
assert.equal(L.entradaValida('x'.repeat(L.MAX_ENTRADA + 1)), false)

// simulador: cada cenário da spec existe e respeita as invariantes
const cmds = r => r.filter(m => m.papel === 'comando').map(m => m.comando)
let r = S.simularResposta('mostre o log', 'airflow', T0)
assert.equal(cmds(r)[0].classe, 'leitura'); assert.equal(cmds(r)[0].estado, 'executado')
r = S.simularResposta('cat .env por favor', 'airflow', T0)
assert.equal(cmds(r)[0].classe, 'proibido'); assert.equal(cmds(r)[0].estado, 'bloqueado')
r = S.simularResposta('reinicie a dag', 'airflow', T0)
assert.equal(cmds(r)[0].classe, 'escrita'); assert.equal(cmds(r)[0].estado, 'proposto')
assert.equal(L.segundosRestantes(cmds(r)[0].expira_em, T0), 120, 'proposta vale 2 min')
r = S.simularResposta('deu falha', 'airflow', T0)
assert.equal(cmds(r)[0].estado, 'falhou')
r = S.simularResposta('quero tudo', 'airflow', T0)
assert.equal(cmds(r)[0].truncada, true)
const ids = new Set(['a', 'b', 'c', 'd'].map(x => cmds(S.simularResposta(x, 's', T0))[0].cmd_id))
assert.equal(ids.size, 4, 'cmd_id único por comando')

// decisão simulada
const p = cmds(S.simularResposta('reinicie', 's', T0))[0]
const ok = S.simularDecisao(p, 'confirmar', '123', T0)
assert.equal(ok.estado, 'executado'); assert.equal(ok.decidido_por, '123'); assert.equal(ok.expira_em, null)
assert.equal(S.simularDecisao(p, 'recusar', '123', T0).estado, 'recusado')
assert.equal(S.simularDecisao(p, 'recusar', '123', T0).saida, undefined, 'recusar não produz saída')
assert.equal(p.estado, 'proposto', 'não muta a proposta')

console.log('ok')
