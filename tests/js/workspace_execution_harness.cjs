// Bancada do contrato puro da Execução (F5 da UX do Pipeline): lib/workspaceExecution.ts
// executado como está (sucrase). Estados de etapa/ligação/corrida, frequência de
// consulta, frescor, anúncio, solicitação guiada e filtros do histórico.
'use strict'
const fs = require('fs'), path = require('path'), assert = require('assert/strict')
const root = path.resolve(__dirname, '../..')
const { transform } = require(root + '/ui-react/node_modules/sucrase')
const m = { exports: {} }
new Function('require', 'module', 'exports', transform(fs.readFileSync(root + '/ui-react/src/lib/workspaceExecution.ts', 'utf8'), { transforms: ['typescript', 'imports'] }).code)(require, m, m.exports)
const x = m.exports
const out = {}

// ── Identidade da leitura ───────────────────────────────────────────────────
assert.deepEqual(x.executionQueryKey('t', 'A/B %25 ç', '2026-10-10', 'r'), ['workspace-execution', 't', 'A/B %25 ç', '2026-10-10', 'r'])
assert.notDeepEqual(x.executionQueryKey('t1', 'a', '', ''), x.executionQueryKey('t2', 'a', '', ''), 'outra sessão, outra chave')
const caminho = new URL(x.executionRequestPath('A/B %25 ç', '2026-10-10', 'manual__a/b%#'), 'http://l')
assert.equal(caminho.pathname, '/workspace/executions'); assert.equal(caminho.searchParams.get('name'), 'A/B %25 ç'); assert.equal(caminho.searchParams.get('runId'), 'manual__a/b%#'); assert.equal(caminho.searchParams.get('date'), null, 'corrida explícita prevalece sobre a data')
assert.equal(new URL(x.executionRequestPath('p', '2026-10-10', ''), 'http://l').searchParams.get('date'), '2026-10-10')
assert.equal(new URL(x.executionRequestPath('p', '', ''), 'http://l').search, '?name=p')
assert(x.responseMatchesRun({ run_id: 'r1', dag_run_id: 'manual__r1' }, 'manual__r1')); assert(x.responseMatchesRun({ run_id: 'r1', dag_run_id: null }, 'r1')); assert(x.responseMatchesRun(null, ''))
assert(!x.responseMatchesRun({ run_id: 'r1', dag_run_id: 'manual__r1' }, 'manual__r2')); assert(!x.responseMatchesRun(undefined, 'r'))
// Resposta inteira cercada: pipeline exato (grafia pedida ou oficial do contexto), corrida e, sem corrida, data.
const resp = (o = {}) => ({ pipeline_name: 'Pipe_A', data_referencia: '2026-10-10', identidade: { run_id: 'r1', dag_run_id: 'manual__r1' }, ...o })
const pedidoA = (o = {}) => ({ names: ['Pipe_A'], date: '', runId: 'manual__r1', ...o })
assert(x.responseMatchesRequest(resp(), pedidoA()))
assert(!x.responseMatchesRequest(resp({ pipeline_name: 'Pipe_B' }), pedidoA()), 'mesmo run_id em outra DAG não é esta corrida')
assert(!x.responseMatchesRequest(resp({ pipeline_name: 'pipe_a' }), pedidoA()), 'grafia diferente sem confirmação do contexto')
assert(x.responseMatchesRequest(resp({ pipeline_name: 'PIPE_A' }), pedidoA({ names: ['pipe_a', 'PIPE_A'] })), 'grafia oficial informada pelo contexto')
assert(!x.responseMatchesRequest(resp({ pipeline_name: undefined }), pedidoA()), 'sem nome, sem confiança')
assert(!x.responseMatchesRequest(resp(), pedidoA({ runId: 'manual__r2' })))
assert(x.responseMatchesRequest(resp(), pedidoA({ runId: '', date: '2026-10-10' }))); assert(!x.responseMatchesRequest(resp(), pedidoA({ runId: '', date: '2026-10-09' })), 'data pedida diferente')
assert(x.responseMatchesRequest(resp({ data_referencia: null }), pedidoA({ runId: '', date: '2026-10-09' })), 'sem data na resposta, a data pedida não é contrariada')
assert(!x.responseMatchesRequest(undefined, pedidoA()))
// Intenção operacional: qualquer parte da identidade muda o escopo.
const esc = (o = {}) => x.operationScope({ token: 't', name: 'p', date: '2026-10-10', runId: 'r', stage: 'E', capabilities: [true, true], ...o })
for (const muda of [{ token: 'u' }, { name: 'q' }, { date: '2026-10-11' }, { runId: 's' }, { stage: 'F' }, { capabilities: [true, false] }, { token: null }]) assert.notEqual(esc(muda), esc(), JSON.stringify(muda))
assert.equal(esc(), esc()); assert.notEqual(x.operationScope({ token: 't', name: 'a|b', date: '', runId: 'c', capabilities: [] }), x.operationScope({ token: 't', name: 'a', date: '', runId: 'b|c', capabilities: [] }))
out.identidade = true

// ── Estado da etapa ─────────────────────────────────────────────────────────
const step = (status, extra = {}) => ({ job_name: 'E', task_id: 'E', status, attempt: status ? 1 : null, tentativas: [], total_tentativas: status ? 1 : 0, no_desenho: true, sem_execucao: !status, status_code: null, ...extra })
const kind = (s, p, live = true) => x.nodeRunState(s, p, live)
assert.equal(kind(step('SUCCESS')).kind, 'success'); assert.equal(kind(step('SUCCESS')).label, 'Concluída'); assert.equal(kind(step('success')).kind, 'success')
assert.equal(kind(step('FAILED', { status_code: '3' })).detail, 'Código 3')
assert.equal(kind(step('SKIPPED')).kind, 'skipped'); assert.equal(kind(step('SKIPPED')).animate, false)
assert.deepEqual([kind(step('RUNNING')).label, kind(step('RUNNING')).animate], ['Executando', true])
assert.deepEqual([kind(step('RUNNING'), undefined, false).label, kind(step('RUNNING'), undefined, false).animate], ['Último registro: executando', false], 'sem telemetria ativa, sem indicador')
for (const raw of ['UP_FOR_RETRY', 'QUEUED', 'UPSTREAM_FAILED', 'WARNING']) { const s = kind(step(raw)); assert.equal(s.kind, 'unknown'); assert.equal(s.label, `Estado ${raw}`); assert.equal(s.animate, false) }
assert.equal(kind(undefined).kind, 'none'); assert.equal(kind(step(null)).label, 'Sem telemetria'); assert.equal(kind(step(null, { no_desenho: false })).detail, 'Etapa fora do desenho exibido')
assert.equal(x.NO_TELEMETRY.kind, 'none'); assert.equal(x.NO_TELEMETRY.animate, false)
// Pausa: marcada não muda o estado; em espera no portão é estado próprio; resolvida não conta.
const pausa = (estado, aguardando = null, parado = null) => ({ job_name: 'e', estado, aguardando_desde: aguardando, parado_min: parado })
assert.deepEqual([kind(step(null), pausa('PENDENTE')).kind, kind(step(null), pausa('PENDENTE')).pauseMarked], ['none', true])
assert.deepEqual([kind(step('RUNNING'), pausa('PENDENTE')).kind, kind(step('RUNNING'), pausa('PENDENTE')).pauseMarked], ['running', true])
const gate = kind(step(null), pausa('PENDENTE', '2026-10-10 10:00:00', 12)); assert.deepEqual([gate.kind, gate.label, gate.animate, gate.pauseMarked], ['gate', 'Em espera no portão', false, false]); assert.match(gate.detail, /12 min/)
assert.equal(kind(step(null), pausa('LIBERADA', '2026-10-10')).kind, 'none'); assert.equal(kind(step(null), pausa('CANCELADA')).pauseMarked, false)
// Uma linha por etapa: em empate vence a tentativa mais recente; chave sem caixa.
const overlay = x.runOverlay([step('FAILED', { job_name: 'Carga', attempt: 1 }), step('SUCCESS', { job_name: 'carga', attempt: 2 }), step('FAILED', { job_name: 'CARGA', attempt: 1 })], [pausa('PENDENTE'), { ...pausa('PENDENTE'), job_name: 'outra' }], true)
assert.equal(x.runStateFor(overlay, 'CARGA').kind, 'success'); assert.equal(x.runStateFor(overlay, 'outra').pauseMarked, true); assert.equal(x.runStateFor(null, 'x'), null)
out.etapa = ['success', 'failed', 'skipped', 'running', 'unknown', 'none', 'gate', 'pauseMarked']

// ── Ligações ────────────────────────────────────────────────────────────────
const s = status => x.nodeRunState(step(status), undefined, true)
assert.equal(x.edgeRunState(s('SUCCESS'), s('RUNNING')), 'observed'); assert.equal(x.edgeRunState(s('SUCCESS'), s('SUCCESS')), 'observed'); assert.equal(x.edgeRunState(s('SUCCESS'), s('FAILED')), 'observed')
assert.equal(x.edgeRunState(s('FAILED'), s('FAILED')), 'unknown', 'falha nas duas pontas não prova caminho (diferente do ehTerminalOk legado)')
assert.equal(x.edgeRunState(s('SUCCESS'), s(null)), 'unknown'); assert.equal(x.edgeRunState(null, null), 'unknown'); assert.equal(x.edgeRunState(s('RUNNING'), s('RUNNING')), 'unknown')
assert.equal(x.edgeRunState(s('SUCCESS'), s('SKIPPED')), 'skipped'); assert.equal(x.edgeRunState(s('SKIPPED'), s(null)), 'skipped')
assert.equal(x.workspaceEdgeId({ source: 'a', target: 'b' }), '["a","b",null]'); assert.equal(x.workspaceEdgeId({ source: 'a', target: 'b', branch: 'sim' }), '["a","b","sim"]')
out.ligacoes = ['observed', 'skipped', 'unknown']

// ── Corrida: Solicitado ≠ Em fila ≠ Executando ──────────────────────────────
const fase = (corrida, identity = { run_id: 'w', dag_run_id: 'w' }, requested = null, runId = 'w') => x.runPhase({ name: 'p', runId, requested, identity, corrida })
const pedido = { name: 'p', runId: 'w', state: 'queued' }
assert.equal(fase(null, { run_id: 'w', dag_run_id: 'w' }, pedido), 'requested')
assert.equal(fase(null, { run_id: 'w', dag_run_id: 'w' }, { ...pedido, name: 'outro' }), 'unknown', 'pedido de outro pipeline não vale')
assert.equal(fase({ status: 'AGUARDANDO' }, null, pedido), 'requested', 'sem identidade confirmada não adota a situação')
assert.equal(fase({ status: 'AGUARDANDO' }, { run_id: 'w', dag_run_id: 'w' }, pedido), 'queued')
assert.equal(fase({ status: 'AGUARDANDO_DEPENDENCIA' }), 'waiting'); assert.equal(fase({ status: 'EXECUTANDO' }), 'running'); assert.equal(fase({ status: 'RUNNING' }), 'running')
assert.equal(fase({ status: 'SUCESSO' }), 'success'); assert.equal(fase({ status: 'FALHA' }), 'failed'); assert.equal(fase({ status: 'PULADO' }), 'skipped'); assert.equal(fase({ status: 'NAO_LIBEROU' }), 'not-released'); assert.equal(fase({ status: 'XPTO' }), 'unknown')
assert.equal(fase({ status: 'SUCESSO' }, { run_id: 'r1', dag_run_id: 'manual__r1' }, null, 'manual__r2'), 'unknown', 'resposta de outra corrida não define a situação')
assert.equal(fase(null, { run_id: null, dag_run_id: null }, null, ''), 'none')
assert.deepEqual(['none', 'requested', 'queued', 'waiting', 'running', 'success', 'failed', 'skipped', 'not-released', 'unknown'].filter(x.activePhase), ['requested', 'queued', 'waiting', 'running'])
assert.equal(new Set(Object.values(x.RUN_PHASE_LABEL)).size, Object.keys(x.RUN_PHASE_LABEL).length, 'rótulos distintos')
out.corrida = ['Solicitado', 'Em fila', 'Executando']

// ── Frequência de consulta (orçamento) ──────────────────────────────────────
const FASES = ['none', 'requested', 'queued', 'waiting', 'running', 'success', 'failed', 'skipped', 'not-released', 'unknown']
assert.equal(x.EXECUTION_POLL.targetMeasured, false, 'sem medição registrada, o alvo de 5 s não está ativo')
for (const phase of FASES) {
 assert.equal(x.executionPollInterval({ visible: false, shown: true, phase }), false, `aba oculta: ${phase}`)
 assert.equal(x.executionPollInterval({ visible: true, shown: false, phase }), false, `destino oculto: ${phase}`)
 assert.equal(x.executionPollInterval({ visible: true, shown: true, phase }), 30_000, `sem medição nunca abaixo de 30 s: ${phase}`)
}
assert.equal(x.executionPollInterval({ visible: true, shown: true, phase: 'running', measured: true }), 5_000)
assert.equal(x.executionPollInterval({ visible: true, shown: true, phase: 'success', measured: true }), 30_000, 'corrida encerrada não acelera')
out.consulta = { semMedicao: 30000, comMedicaoAtiva: 5000, oculta: false }

// ── Frescor ─────────────────────────────────────────────────────────────────
const fr = (o) => x.executionFreshness({ hasData: true, isError: false, isFetching: false, dataUpdatedAt: 10, errorUpdatedAt: 0, ...o })
assert.equal(fr({}), 'live'); assert.equal(fr({ isFetching: true }), 'refreshing'); assert.equal(fr({ isError: true, errorUpdatedAt: 11 }), 'unavailable'); assert.equal(fr({ isError: true, errorUpdatedAt: 5 }), 'live', 'erro antigo superado por dado novo')
assert.equal(fr({ hasData: false }), 'loading'); assert.equal(fr({ hasData: false, isError: true }), 'unavailable')
assert.equal(x.clockLabel(0), '—'); assert.match(x.clockLabel(Date.UTC(2026, 9, 10, 12, 3, 4)), /^\d\d:\d\d:\d\d$/)
out.frescor = true

// ── Fonte do desenho ────────────────────────────────────────────────────────
assert.equal(x.drawingSource(true, 4), 'snapshot'); assert.equal(x.drawingSource(true, null), 'published-fallback'); assert.equal(x.drawingSource(false, undefined), 'published')
assert.equal(x.drawingSource(true, 4, true), 'published-unconfirmed', 'versão de resposta não confirmada não vira snapshot'); assert.match(x.drawingSourceLabel('published-unconfirmed', 4), /não confirmada.*publicada atual.*sem estados/)
assert.match(x.drawingSourceLabel('published-fallback', null), /sem versão vinculada.*publicada atual.*pode diferir/)
assert.doesNotMatch(Object.values({ a: x.drawingSourceLabel('snapshot', 4), b: x.drawingSourceLabel('published', null), c: x.drawingSourceLabel('published-fallback', null) }).join(' '), /rascunho/i)
const def = { nodes: [{ id: 'A' }, { id: 'B' }, { id: 'C' }, { id: 'D' }], edges: [{ source: 'A', target: 'B' }, { source: 'A', target: 'C' }, { source: 'B', target: 'D' }, { source: 'C', target: 'D', branch: 'nao' }] }
assert.deepEqual(x.stepsOutsideDrawing(def, [step('SUCCESS', { job_name: 'a' }), step('SUCCESS', { job_name: 'Z' }), step(null, { job_name: 'Y' })]), ['Z'], 'só as executadas fora do desenho, sem caixa')
const cont = x.runCounts(x.runOverlay([step('SUCCESS', { job_name: 'A' }), step('RUNNING', { job_name: 'B' }), step('SKIPPED', { job_name: 'C' })], [{ ...pausa('PENDENTE'), job_name: 'D' }], true), def)
assert.deepEqual(cont, { total: 4, success: 1, failed: 0, running: 1, skipped: 1, none: 1, unknown: 0, gate: 0, pauseMarked: 1 })
assert.equal(x.completionLabel(cont), '1 de 4 etapas concluídas'); assert.equal(x.completionLabel({ ...cont, total: 1 }), '1 de 1 etapa concluída')
out.fonte = true

// ── Dependências ────────────────────────────────────────────────────────────
assert.deepEqual(x.stageNeighbors(def, 'D'), { before: ['B', 'C'], after: [] })
const ambos = x.stageChain(def, 'B', 'ambos'); assert.deepEqual([...ambos.nodes].sort(), ['A', 'B', 'D']); assert.deepEqual([ambos.before, ambos.after], [1, 1])
assert.deepEqual([...x.stageChain(def, 'D', 'tras').nodes].sort(), ['A', 'B', 'C', 'D']); assert(x.stageChain(def, 'D', 'tras').edges.has('["C","D","nao"]'))
assert.equal(x.stageChain(def, 'A', 'frente').after, 3); assert.equal(x.stageChain(def, 'A', 'tras').before, 0); assert.equal(x.stageChain(def, 'nao-existe', 'ambos'), null)
assert.equal(x.stageChain({ nodes: [{ id: 'a' }, { id: 'b' }], edges: [{ source: 'a', target: 'b' }, { source: 'b', target: 'a' }] }, 'a', 'ambos').before, 1, 'ciclo não infla nem trava')
out.dependencias = true

// ── Anúncio ─────────────────────────────────────────────────────────────────
const a1 = x.selectedStageAnnouncement('E', s('RUNNING')), a2 = x.selectedStageAnnouncement('E', s('RUNNING')), a3 = x.selectedStageAnnouncement('E', s('SUCCESS'))
assert.equal(a1.key, a2.key, 'consulta igual, sem novo anúncio'); assert.notEqual(a1.key, a3.key); assert.equal(a3.message, 'Etapa E: Concluída, tentativa 1')
assert.notEqual(x.selectedStageAnnouncement('F', s('RUNNING')).key, a1.key, 'outra etapa anuncia'); assert.equal(x.selectedStageAnnouncement('', s('RUNNING')), null)
out.anuncio = true

// ── Solicitação guiada ──────────────────────────────────────────────────────
const RUN = 'workspace__0f8fad5b-d9cb-469f-a165-70867728950e'
const form = (o = {}) => ({ odate: '', logicalDate: '', extraConf: {}, ...o })
assert.deepEqual(x.buildRunRequest(form(), RUN), { ok: true, body: { conf: {}, dag_run_id: RUN } })
assert.deepEqual(x.buildRunRequest(form({ odate: '2026-10-10', logicalDate: '2026-10-10T08:30' }), RUN).body, { conf: { data_referencia: '2026-10-10' }, dag_run_id: RUN, logical_date: '2026-10-10T08:30:00Z' })
assert.equal(x.buildRunRequest(form({ logicalDate: '2026-10-10T08:30:15' }), RUN).body.logical_date, '2026-10-10T08:30:15Z')
for (const odate of ['2026-02-30', '10/10/2026', '2026-1-1', 'hoje']) assert.equal(x.buildRunRequest(form({ odate }), RUN).field, 'odate', odate)
for (const logicalDate of ['2026-10-10', '2026-10-10T24:00', '2026-13-01T00:00', 'x']) assert.equal(x.buildRunRequest(form({ logicalDate }), RUN).field, 'logicalDate', logicalDate)
for (const runId of ['', 'manual__x', 'workspace__nao-uuid']) assert.equal(x.buildRunRequest(form(), runId).field, 'runId', runId)
assert.deepEqual(x.buildRunRequest(form({ odate: '2026-10-10', extraConf: { x: { y: [1] } } }), RUN).body.conf, { x: { y: [1] }, data_referencia: '2026-10-10' }, 'chaves existentes preservadas')
assert.equal(x.buildRunRequest(form({ extraConf: { grande: 'a'.repeat(70_000) } }), RUN).field, 'conf', 'limite de 64 KiB do adaptador')
assert.deepEqual(Object.keys(x.buildRunRequest(form({ odate: '2026-10-10', logicalDate: '2026-10-10T00:00' }), RUN).body).sort(), ['conf', 'dag_run_id', 'logical_date'], 'só os campos aceitos pelo adaptador')
assert.equal(x.parseAdvancedConf('{').ok, false); assert.equal(x.parseAdvancedConf('[]').ok, false); assert.equal(x.parseAdvancedConf('null').ok, false); assert.equal(x.parseAdvancedConf('{"data_referencia": 5}').ok, false)
assert.deepEqual(x.parseAdvancedConf('{"a": {"b": null}, "data_referencia": "2026-10-11"}'), { ok: true, odate: '2026-10-11', extraConf: { a: { b: null } } })
assert.deepEqual(x.parseAdvancedConf(''), { ok: true, odate: '', extraConf: {} })
const texto = x.advancedConfText({ odate: '2026-10-11', extraConf: { a: 1 } }); assert.deepEqual(JSON.parse(texto), { a: 1, data_referencia: '2026-10-11' }); assert.deepEqual(x.parseAdvancedConf(texto), { ok: true, odate: '2026-10-11', extraConf: { a: 1 } })
assert(x.validOperationalDate('2024-02-29')); assert(!x.validOperationalDate('2026-02-29'))
out.solicitacao = { semJson: true, validacoes: ['odate', 'logicalDate', 'runId', 'conf'], preserva: true }

// ── Histórico ───────────────────────────────────────────────────────────────
const F = x.EMPTY_HISTORY_FILTERS
const hp = new URL(x.runHistoryPath('A/B %25 ç', { ...F, from: '2026-10-01', to: '2026-10-10', status: 'FALHA', version: '4', page: 2 }), 'http://l')
assert.equal(hp.pathname, '/pipeline-run-history'); assert.deepEqual(Object.fromEntries(hp.searchParams), { pipeline_name: 'A/B %25 ç', limit: '25', offset: '50', date_from: '2026-10-01', date_to: '2026-10-10', status: 'FALHA', version: '4' })
assert.deepEqual(Object.fromEntries(new URL(x.runHistoryPath('p', F), 'http://l').searchParams), { pipeline_name: 'p', limit: '25', offset: '0' }, 'filtros vazios não vão')
assert.equal(x.runHistoryIssue(F), null); assert.match(x.runHistoryIssue({ ...F, from: '2026-10-11', to: '2026-10-10' }), /anterior/); assert.match(x.runHistoryIssue({ ...F, version: '0' }), /versão/); assert.match(x.runHistoryIssue({ ...F, status: 'DROP' }), /Situação/); assert.match(x.runHistoryIssue({ ...F, from: '2026-02-30' }), /inicial/)
assert.deepEqual(x.RUN_HISTORY_STATUSES.map(([id]) => id).filter(Boolean).sort(), ['AGUARDANDO_DEPENDENCIA', 'EXECUTANDO', 'FALHA', 'NAO_LIBEROU', 'PULADO', 'SUCESSO'], 'mesma lista fechada do adaptador')
assert.deepEqual(x.historyPages({ total: 0, limit: 25, offset: 0 }), { current: 1, count: 1 }); assert.deepEqual(x.historyPages({ total: 51, limit: 25, offset: 50 }), { current: 3, count: 3 }); assert.deepEqual(x.historyPages({ total: 10_000, limit: 100, offset: 9_900 }), { current: 100, count: 100 })
assert.equal(x.runStatusPhase('SUCESSO'), 'success'); assert.equal(x.runStatusPhase(null), 'unknown')
out.historico = { filtros: ['data', 'situação', 'versão'], paginacao: true }

// ── Canvas compartilhado: Enter na etapa e movimento reduzido ───────────────
const ma = { exports: {} }
new Function('require', 'module', 'exports', transform(fs.readFileSync(root + '/ui-react/src/lib/workspaceCanvasA11y.ts', 'utf8'), { transforms: ['typescript', 'imports'] }).code)(require, ma, ma.exports)
const a = ma.exports
const media = reduce => q => ({ matches: reduce && q === '(prefers-reduced-motion: reduce)' })
assert.equal(a.fitViewDuration(media(true)), 0, 'movimento reduzido: reenquadra sem animação')
assert.equal(a.fitViewDuration(media(false)), 200); assert.equal(a.fitViewDuration(null), 200); assert.equal(a.fitViewDuration(() => { throw new Error('sem matchMedia') }), 200)
const tecla = (o = {}) => ({ key: 'Enter', repeat: false, isComposing: false, ctrlKey: false, altKey: false, metaKey: false, shiftKey: false, defaultPrevented: false, ...o })
const alvo = (classes, id) => ({ classList: { contains: c => classes.includes(c) }, getAttribute: n => n === 'data-id' ? id : null })
const etapaFocada = alvo(['react-flow__node', 'react-flow__node-workspace', 'selectable'], 'Carga'), conhecida = id => id === 'Carga'
assert.equal(a.nodeForEnter(tecla(), etapaFocada, conhecida, false), 'Carga')
for (const o of [{ key: ' ' }, { key: 'Escape' }, { key: 'Delete' }, { ctrlKey: true }, { altKey: true }, { metaKey: true }, { shiftKey: true }, { repeat: true }, { isComposing: true }, { defaultPrevented: true }]) assert.equal(a.nodeForEnter(tecla(o), etapaFocada, conhecida, false), null, JSON.stringify(o))
assert.equal(a.nodeForEnter(tecla(), etapaFocada, conhecida, true), null, 'diálogo aberto: a tecla é dele')
assert.equal(a.nodeForEnter(tecla(), alvo(['react-flow__controls-button'], null), conhecida, false), null, 'controle dentro do canvas')
assert.equal(a.nodeForEnter(tecla(), alvo(['nodrag'], 'Carga'), conhecida, false), null, 'elemento dentro da etapa não é a etapa')
assert.equal(a.nodeForEnter(tecla(), alvo(['react-flow__node'], 'Fantasma'), conhecida, false), null, 'etapa fora do desenho exibido')
assert.equal(a.nodeForEnter(tecla(), null, conhecida, false), null)
out.canvasA11y = { enter: true, reduzido: 0 }

console.log(JSON.stringify({ ...out, passed: true }))
