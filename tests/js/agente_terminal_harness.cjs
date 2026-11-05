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
{ const hora = new Date('2026-11-04T14:05:09Z').toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  assert.equal(L.rastro({ ...prop, estado: 'executado', decidido_por: '123', decidido_em: '2026-11-04T14:05:09Z' }), `executado por 123 às ${hora}`, 'horário LOCAL, não o UTC do ISO') }
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

// ── F5: resposta REAL → mensagens ──
let n = 0
const id = () => `x${++n}`
const resp = {
  texto: 'Pronto.',
  artefatos: [
    { ferramenta: 'resolver_projeto', args: { projeto: 'BI' } },
    { ferramenta: 'dsjob', args: { comando: 'jobinfo', job_name: 'J1' } },
    { ferramenta: 'banco_consulta', args: { sql: 'SELECT 1' }, banco: { conexao: 'dw', banco: 'PREV', linhas: 3 } },
    { ferramenta: 'servidor_exec', args: { comando: 'ls /opt' }, comando_executado: { cmd_id: 'a', comando: 'ls /opt', servidor: 'airflow', classe: 'leitura', estado: 'executado', saida: 'x', codigo_saida: 0, duracao_ms: 5, truncada: false, interrompido: false, notas: ['[n1]'] } },
    { ferramenta: 'servidor_exec', args: { comando: 'touch /opt/a' }, proposta_comando: { cmd_id: 'b', hash: 'h1', comando: 'touch /opt/a', servidor: 'airflow', motivo: 'm', segundos_restantes: 90 } },
    { ferramenta: 'servidor_exec', args: { comando: 'x' }, recusada: 'fora_do_agente' },
    { ferramenta: 'dsjob', args: { comando: 'ljobs' }, repetida: true },
  ],
}
const msgs = L.mensagensDaResposta(resp, T0, id)
assert.deepEqual(msgs.map(m => m.papel), ['nota', 'nota', 'comando', 'comando', 'assistente'], 'ordem: consultas, comandos e o texto por último; recusada/repetida não viram bloco')
assert.equal(msgs[0].detalhe, 'dsjob jobinfo J1')
assert.equal(msgs[1].sql, 'SELECT 1') ; assert.ok(msgs[1].detalhe.includes('dw/PREV') && msgs[1].detalhe.includes('3 linha'))
assert.equal(msgs[2].comando.estado, 'executado') ; assert.deepEqual(msgs[2].comando.notas, ['[n1]'])
const proposta5 = msgs[3].comando
assert.equal(proposta5.estado, "proposto") ; assert.equal(proposta5.hash, "h1") ; assert.equal(proposta5.classe, "escrita")
assert.equal(L.segundosRestantes(proposta5.expira_em, T0), 90, 'o prazo vira expira_em no relógio do navegador')
assert.equal(L.podeDecidir(proposta5, T0, true), true)
assert.equal(L.mensagensDaResposta({ texto: '  ', artefatos: [] }, T0, id).length, 0)
assert.equal(L.mensagensDaResposta({ texto: 'oi' }, T0, id).length, 1, 'sem artefatos não quebra')

// comandoDaProposta: prazo inválido = expirado, nunca NaN
for (const s of [null, undefined, -5, NaN, Infinity, 'x']) {
  const c = L.comandoDaProposta({ cmd_id: 'z', hash: 'h', comando: 'c', servidor: 's', segundos_restantes: s }, T0)
  assert.equal(L.estadoEfetivo(c, T0), 'expirado', String(s))
}

// reidratar: o servidor é a verdade
const atual = { ...proposta5 }
let r2 = L.reidratar(atual, { cmd_id: 'b', comando: 'touch /opt/a', servidor: 'airflow', classe: 'escrita', estado: 'executado', decidido_por: 'DEV1', saida_resumo: 'ok', codigo_saida: 0, duracao_ms: 9 }, T0)
assert.equal(r2.estado, 'executado') ; assert.equal(r2.expira_em, null) ; assert.equal(r2.saida, 'ok') ; assert.equal(r2.decidido_por, 'DEV1')
r2 = L.reidratar(atual, { cmd_id: 'b', comando: 'touch /opt/a', servidor: 'airflow', classe: 'escrita', estado: 'proposto', segundos_restantes: 30, hash: 'h2' }, T0)
assert.equal(L.segundosRestantes(r2.expira_em, T0), 30) ; assert.equal(r2.hash, 'h2', 'reaberta: o hash vem do servidor')

// textoDoErroDeDecisao: códigos conhecidos e o 503 que permite tentar de novo
assert.ok(L.textoDoErroDeDecisao('servidor_ocupado_ou_indisponivel').texto.includes('NÃO foi executado'))
assert.ok(L.textoDoErroDeDecisao('falha_na_execucao').texto.includes('PODE ter sido executado'))
assert.equal(L.textoDoErroDeDecisao('agente_escrita_desligada').reidratar, false)
assert.equal(L.textoDoErroDeDecisao('ja_decidido').reidratar, true)
assert.ok(L.textoDoErroDeDecisao(undefined).texto.length > 0)
assert.equal(L.linhasDoComando('a\nb\nc'), 3) ; assert.equal(L.linhasDoComando(''), 1)

// substituirComando: troca o card pelo cmd_id e NUNCA acrescenta (decisão em voo depois de "Nova conversa")
{
  const base = [{ papel: 'usuario', texto: 'oi' }, { papel: 'comando', comando: { ...proposta5, cmd_id: 'x1', estado: 'proposto' } }]
  const trocado = L.substituirComando(base, { ...proposta5, cmd_id: 'x1', estado: 'executado' })
  assert.equal(trocado.length, 2) ; assert.equal(trocado[1].comando.estado, 'executado') ; assert.equal(base[1].comando.estado, 'proposto', 'imutável')
  const ausente = L.substituirComando(base, { ...proposta5, cmd_id: 'outro', estado: 'executado' })
  assert.equal(ausente, base, 'cmd_id ausente: a lista volta intacta (mesma referência)')
  assert.deepEqual(L.substituirComando([], { ...proposta5, cmd_id: 'x1' }), [])
}

console.log('ok')
