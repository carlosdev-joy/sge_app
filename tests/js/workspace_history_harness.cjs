// Bancada pura da F4.2: patches diferenciais, histórico local de 50 passos,
// mescla por campo do inspector e atalhos. Executa os módulos REAIS de
// ui-react/src/lib (sucrase), sem React. Cada bloco foi escrito para falhar se a
// regra correspondente regredir (limite, gesto, ramo de refazer, segredo,
// conflito, campos desconhecidos, ordem dos ramos).
'use strict'
const fs = require('fs'), path = require('path'), assert = require('assert/strict')
const ROOT = path.resolve(__dirname, '../..'), { transform } = require(path.join(ROOT, 'ui-react/node_modules/sucrase'))
const cache = {}
function load(name) {
 if (cache[name]) return cache[name]
 const mod = { exports: {} }; cache[name] = mod.exports
 const code = transform(fs.readFileSync(path.join(ROOT, 'ui-react/src/lib', name + '.ts'), 'utf8'), { transforms: ['typescript', 'imports'] }).code
 new Function('require', 'module', 'exports', code)(id => id.startsWith('./') ? load(id.slice(2)) : require(id), mod, mod.exports)
 cache[name] = mod.exports; return mod.exports
}
const ws = load('workspace'), P = load('workspacePatch'), H = load('workspaceHistory'), I = load('workspaceInspector')
const D = load('workspaceDecision'), S = load('workspaceSpecialized'), L = load('workspaceLayout'), C = load('workspaceCatalog')
const clone = structuredClone, resultado = {}

// Fixture com os 11 tipos, campos desconhecidos em todos os níveis e referências protegidas.
const TIPOS = ['datastage', 'sql', 'python', 'shell', 'storedproc', 'http', 'decisao', 'aguarde', 'notificacao', 'email', 'valida_arquivo']
const special = { sql: { sql_json: '{"sql":"SELECT 1","on_error":"falhar","futuro":1}' }, decisao: { condition_json: JSON.stringify({ tipo: 'valor_sql', operador: '>', valor: '1', ramo_verdadeiro: ['n7'], ramo_falso: [], futuro: true }) }, aguarde: { aguarde_json: '{"politica":"todas_sucesso"}' } }
function fixture(extra = 0) {
 const nodes = TIPOS.map((type, i) => ({ id: `n${i}`, type, extension: { keep: i }, configuration: { legacyJob: { job_name: `n${i}`, job_type: type, job_command: `cmd ${i}`, execution_order: i + 1, especial: [null, { f: i }], ...(special[type] || {}) }, unknownConfig: { nested: [i] }, etl_pipeline_job_param: [{ param_name: 'protegido', param_type: 'Encrypted', secretReference: { id: i }, param_value: '***' }, { param_name: 'livre', param_value: String(i), futuro: 'p' }] } }))
 for (let i = 0; i < extra; i++) nodes.push({ id: `x${i}`, type: 'shell', configuration: { legacyJob: { job_name: `x${i}`, job_type: 'shell', job_command: `echo ${i}`, execution_order: 12 + i, payload: 'k'.repeat(200) }, etl_pipeline_job_param: [] } })
 return {
  definition: { schemaVersion: 1, identity: { pipelineName: 'P', displayName: 'Pipe', extraIdentity: { keep: true } }, metadata: { legacyPipeline: { pipeline_name: 'P', sla_minutos: 60, campo_desconhecido: { a: [1, null] } }, legacyTables: { etl_pipeline_param: [{ param_name: 'cifrado', param_type: 'Encrypted', secretReference: { id: 99 }, param_value: '***' }], tabela_desconhecida: [{ x: null }] }, workspaceLineageVersion: 1 }, nodes, edges: [{ source: 'n0', target: 'n1', unknown: 9 }, { source: 'n6', target: 'n7', branch: 'sim' }, { source: 'n1', target: 'n2' }], topoDesconhecido: { q: null } },
  layout: { schemaVersion: 1, nodes: Object.fromEntries(nodes.filter((_, i) => i !== 4).map((n, i) => [n.id, { x: i * 10, y: i * 5, extra: 'k' }])), custom: null },
 }
}
const at = (snap, id) => snap.definition.nodes.find(n => n.id === id)
const withNode = (snap, id, fn) => ({ ...snap, definition: { ...snap.definition, nodes: snap.definition.nodes.map(n => n.id === id ? fn(n) : n) } })

// ── 1. Patches: aplicar e inverter devolvem exatamente o estado, em toda operação elegível ──
const s0 = fixture()
const operacoes = {
 adicionar: s => ({ ...s, definition: { ...s.definition, nodes: [...s.definition.nodes, { id: 'shell_1', type: 'shell', configuration: { legacyJob: { job_name: 'shell_1' } } }] }, layout: { ...s.layout, nodes: { ...s.layout.nodes, shell_1: { x: 1, y: 2 } } } }),
 removerMeio: s => ws.removeWorkspaceNode(s.definition, s.layout, 'n3'),
 renomear: s => ws.renameWorkspaceNode(withNode(s, 'n2', n => ({ ...n, configuration: { ...n.configuration, etl_pipeline_job_param: [] } })).definition, s.layout, 'n2', 'n2_novo'),
 conectar: s => ({ ...s, definition: D.connectWorkspaceDecision(s.definition, 'n2', 'n5', null) }),
 ramoDecisao: s => ({ ...s, definition: D.connectWorkspaceDecision(s.definition, 'n6', 'n8', 'nao') }),
 casosSwitch: s => ({ ...s, definition: S.editDecisionCases(s.definition, 'n6', { type: 'mode', switch: true }) }),
 removerLigacao: s => ({ ...s, definition: D.removeWorkspaceEdges(s.definition, new Set(['1'])) }),
 organizar: s => ({ ...s, layout: L.arrangeWorkspace(s.definition, s.layout) }),
 arrastar: s => ({ ...s, layout: { ...s.layout, nodes: { ...s.layout.nodes, n0: { ...s.layout.nodes.n0, x: 400 } } } }),
 importar: s => ({ ...s, definition: C.importWorkspaceRows(s.definition, [{ name: 'imp_a', type: 'sql', command: '', parent: 'n0', branch: '' }, { name: 'imp_b', type: 'decisao', command: '', parent: '', branch: '' }]) }),
 ordenar: s => ({ ...s, definition: C.reorderWorkspaceExecution(s.definition, [...s.definition.nodes].reverse().map(n => n.id)) }),
 metadados: s => ({ ...s, definition: { ...s.definition, metadata: { ...s.definition.metadata, legacyPipeline: { ...s.definition.metadata.legacyPipeline, sla_minutos: 45, nova: null } } } }),
 configGui: s => withNode(s, 'n3', n => S.hasSpecializedFields(n.type) ? n : { ...n, configuration: { ...n.configuration, legacyJob: { ...n.configuration.legacyJob, job_command: 'novo', ssh_conn_id: 'ssh' } } }),
}
for (const [nome, op] of Object.entries(operacoes)) {
 const depois = op(clone(s0)), patch = P.diffPatch(s0, depois)
 assert(patch.length > 0, nome)
 assert.deepEqual(P.applyPatch(clone(s0), patch), { ok: true, value: depois }, `${nome}: aplicar`)
 const volta = P.applyPatch(depois, P.invertPatch(patch))
 assert.equal(volta.ok, true, `${nome}: inverter`); assert.deepEqual(volta.value, s0, `${nome}: estado exato`)
 // Diferencial: nada além do que mudou (nunca a definição inteira).
 assert(JSON.stringify(patch).length < JSON.stringify(s0).length / 2 || nome === 'ordenar' || nome === 'organizar', `${nome}: patch ${JSON.stringify(patch).length}`)
}
// Remover do meio guarda só a etapa removida (comparação por id), e a ordem volta igual.
const semN3 = operacoes.removerMeio(clone(s0)), pRem = P.diffPatch(s0, semN3)
assert.deepEqual(pRem.filter(op => op.t === 'del').map(op => op.id), ['n3'])
assert.deepEqual(P.applyPatch(semN3, P.invertPatch(pRem)).value.definition.nodes.map(n => n.id), s0.definition.nodes.map(n => n.id))
// Duas remoções não vizinhas num passo: desfazer devolve cada etapa à sua posição.
const semDuas = { ...s0, definition: { ...s0.definition, nodes: s0.definition.nodes.filter(n => !['n2', 'n7'].includes(n.id)) } }
assert.deepEqual(P.applyPatch(semDuas, P.invertPatch(P.diffPatch(s0, semDuas))).value.definition.nodes.map(n => n.id), s0.definition.nodes.map(n => n.id))
const comDuas = { ...s0, definition: { ...s0.definition, nodes: [{ id: 'novo_a', type: 'shell', configuration: {} }, ...s0.definition.nodes.slice(0, 5), { id: 'novo_b', type: 'sql', configuration: {} }, ...s0.definition.nodes.slice(5)] } }
assert.deepEqual(P.applyPatch(clone(s0), P.diffPatch(s0, comDuas)).value, comDuas)
// Organizar: posições ausentes voltam a não existir (layout exato, inclusive campos extras).
const org = operacoes.organizar(clone(s0)); assert(org.layout.nodes.n4, 'organizar cria posição'); assert(P.diffPatch(s0, org).every(op => op.path[0] === 'layout'), 'organizar só muda o layout'); assert.equal(P.applyPatch(org, P.invertPatch(P.diffPatch(s0, org))).value.layout.nodes.n4, undefined)
resultado.patches = Object.keys(operacoes).length

// ── 2. Histórico: limite, no-op, ramo de refazer, seleção ───────────────────
const passo = (h, a, b, extra = {}) => H.recordHistory(h, a, b, { label: 'passo', now: 0, ...extra })
let h = H.emptyHistory(), estado = clone(s0); const estados = [estado]
for (let i = 1; i <= 51; i++) { const prox = withNode(estado, 'n0', n => ({ ...n, displayName: `v${i}` })); h = passo(h, estado, prox); estado = prox; estados.push(estado) }
assert.equal(h.past.length, 50, 'no máximo 50 passos')
assert.equal(H.recordHistory(h, estado, estado, { label: 'nada', now: 1 }), h, 'sem mudança não ocupa passo')
assert.equal(H.recordHistory(h, estado, clone(estado), { label: 'clone', now: 1 }), h, 'cópia igual também não')
let atual = estado
for (let i = 0; i < 50; i++) { const r = H.undoHistory(h, atual); assert.equal(r.ok, true); h = r.history; atual = r.state }
assert.equal(H.undoHistory(h, atual), null, 'o 51º passo antigo saiu do histórico')
assert.deepEqual(atual, estados[1], 'desfazer 50 vezes volta ao estado após a primeira alteração')
let r = H.redoHistory(h, atual); h = r.history; atual = r.state; assert.deepEqual(atual, estados[2])
assert.equal(h.future.length, 49)
const ramo = withNode(atual, 'n1', n => ({ ...n, displayName: 'novo ramo' }))
h = passo(h, atual, ramo); atual = ramo
assert.equal(h.future.length, 0, 'nova alteração invalida o refazer'); assert.equal(H.redoHistory(h, atual), null)
assert.deepEqual(H.historyLabels(h), { undo: 'passo', redo: null })
// Seleção do passo e conflito: estado alterado fora do histórico não é sobrescrito.
let hs = passo(H.emptyHistory(), s0, operacoes.adicionar(clone(s0)), { label: 'Adicionar etapa', select: { before: 'n1', after: 'shell_1' } })
const undoSel = H.undoHistory(hs, operacoes.adicionar(clone(s0))); assert.deepEqual(undoSel.entry.select, { before: 'n1', after: 'shell_1' })
const fora = withNode(operacoes.adicionar(clone(s0)), 'shell_1', n => ({ ...n, configuration: { legacyJob: { job_name: 'mudou' } } }))
const conflito = H.undoHistory(hs, fora)
assert.equal(conflito.ok, false); assert.deepEqual(conflito.history, H.emptyHistory(), 'histórico reiniciado sem alterar o rascunho')
resultado.historico = { limite: 50, noOp: 0, redoInvalidado: true, conflito: 'recusado' }

// ── 3. Gestos: arraste vira um passo; digitação agrupada com pausa ──────────
let g = H.emptyHistory(), gs = clone(s0)
for (let i = 1; i <= 20; i++) {
 const prox = { ...gs, layout: { ...gs.layout, nodes: { ...gs.layout.nodes, n4: { x: i, y: i * 2 }, n0: { ...gs.layout.nodes.n0, x: 100 + i }, n1: { ...gs.layout.nodes.n1, y: 50 + i } } } }
 g = H.recordHistory(g, gs, prox, { label: 'Mover etapas', group: 'arrastar:0', now: i * 16 }); gs = prox
}
g = H.sealHistory(g)
assert.equal(g.past.length, 1, '20 eventos de um arraste com três etapas = 1 passo')
const voltaArraste = H.undoHistory(g, gs); assert.deepEqual(voltaArraste.state, s0, 'arraste volta exato (posição ausente some)')
const novoGesto = H.recordHistory(g, gs, { ...gs, layout: { ...gs.layout, nodes: { ...gs.layout.nodes, n0: { x: 0, y: 0 } } } }, { label: 'Mover etapas', group: 'arrastar:0', now: 999 })
assert.equal(novoGesto.past.length, 2, 'gesto encerrado não recebe o próximo')
let t = H.emptyHistory(), ts = clone(s0)
const digitar = (texto, now, field = 'displayName', id = 'n5') => { const prox = withNode(ts, id, n => ({ ...n, [field]: texto })); t = H.recordHistory(t, ts, prox, { label: 'Editar', group: `campo:${id}:${field}`, window: H.TEXT_GROUP_MS, now }); ts = prox }
'abcdef'.split('').forEach((_, i) => digitar('abcdef'.slice(0, i + 1), 100 + i * 100))
assert.equal(t.past.length, 1, 'digitação contínua = 1 passo'); assert.equal(t.past[0].ops.length, 1, 'passo guarda só antes/depois do campo')
digitar('abcdefg', 100 + 5 * 100 + H.TEXT_GROUP_MS + 1); assert.equal(t.past.length, 2, 'pausa longa abre outro passo')
digitar('outro', 3000, 'extra'); assert.equal(t.past.length, 3, 'outro campo, outro passo')
const antes = clone(ts); digitar('outro!', 3100, 'extra'); digitar('outro', 3200, 'extra')
assert.equal(t.past.length, 3); assert.deepEqual(ts, antes)
digitar('x', 3300, 'displayName', 'n9')
const semCampo = { ...ts, definition: { ...ts.definition, nodes: ts.definition.nodes.map(n => { if (n.id !== 'n9') return n; const { displayName: _, ...resto } = n; return resto }) } }
t = H.recordHistory(t, ts, semCampo, { label: 'Editar', group: 'campo:n9:displayName', window: H.TEXT_GROUP_MS, now: 3400 }); ts = semCampo
assert.equal(t.past.length, 3, 'digitar e apagar de volta não deixa passo vazio')
resultado.gestos = { arraste: 1, multisselecao: 3, digitacao: 1, pausa: 2 }

// ── 4. Segredos: referência nova reinicia; valor aberto nunca entra ─────────
const PLAIN = 'segredo-em-claro-123'
const comNova = withNode(s0, 'n0', n => ({ ...n, configuration: { ...n.configuration, etl_pipeline_job_param: [...n.configuration.etl_pipeline_job_param, { param_name: 'novo', param_type: 'Encrypted', param_value: '***', secretReference: { secretId: 'abc' } }] } }))
let hz = passo(H.emptyHistory(), s0, withNode(s0, 'n1', n => ({ ...n, displayName: 'antes' })))
hz = passo(hz, s0, comNova); assert.deepEqual([hz.past.length, hz.reset], [0, 'protected'], 'referência protegida nova reinicia o histórico')
const trocaRef = withNode(s0, 'n0', n => ({ ...n, configuration: { ...n.configuration, etl_pipeline_job_param: n.configuration.etl_pipeline_job_param.map(p => p.param_type ? { ...p, secretReference: { secretId: 'outro' } } : p) } }))
assert.equal(passo(H.emptyHistory(), s0, trocaRef).reset, 'protected', 'alterar valor protegido também')
const globalNova = { ...s0, definition: ws.setPipelineParameters(s0.definition, [...ws.pipelineParameters(s0.definition), { param_name: 'g', param_type: 'Encrypted', param_value: '***', secretReference: { secretId: 'g' } }]) }
assert.equal(passo(H.emptyHistory(), s0, globalNova).reset, 'protected', 'parâmetro global protegido')
const exposto = withNode(s0, 'n2', n => ({ ...n, configuration: { ...n.configuration, etl_pipeline_job_param: n.configuration.etl_pipeline_job_param.map(p => p.param_type ? { ...p, param_value: PLAIN } : p) } }))
const hx = passo(H.emptyHistory(), s0, exposto); assert.equal(hx.reset, 'protected'); assert(!JSON.stringify(hx).includes(PLAIN), 'valor aberto fora do histórico')
// Remover referência existente é local: desfazer devolve a mesma referência mascarada.
const semProtegido = withNode(s0, 'n0', n => ({ ...n, configuration: { ...n.configuration, etl_pipeline_job_param: n.configuration.etl_pipeline_job_param.filter(p => !p.param_type) } }))
const hr = passo(H.emptyHistory(), s0, semProtegido); assert.equal(hr.past.length, 1)
assert.deepEqual(H.undoHistory(hr, semProtegido).state, s0)
// Remover etapa com referência e desfazer também (mascarada, mesma referência).
const hn = passo(H.emptyHistory(), s0, semN3); assert.deepEqual(H.undoHistory(hn, semN3).state, s0)
assert(!JSON.stringify(hn).includes(PLAIN))
// Estado anterior com valor protegido aberto (rascunho legado sintético, mesma
// referência): mascarar, remover o parâmetro, remover a etapa ou editar outra
// coisa não grava o valor de antes; o histórico recomeça vazio, sem refazer.
const SENTINELA = 'SENTINELA_SINTETICA_F42_ANTES'
const aberto = withNode(s0, 'n2', n => ({ ...n, configuration: { ...n.configuration, etl_pipeline_job_param: n.configuration.etl_pipeline_job_param.map(p => p.param_type ? { ...p, param_value: SENTINELA } : p) } }))
assert.equal(H.exposesProtectedValue(aberto.definition), true)
const comPassos = H.undoHistory(passo(passo(H.emptyHistory(), s0, withNode(s0, 'n1', n => ({ ...n, displayName: 'a' }))), withNode(s0, 'n1', n => ({ ...n, displayName: 'a' })), withNode(s0, 'n1', n => ({ ...n, displayName: 'b' }))), withNode(s0, 'n1', n => ({ ...n, displayName: 'b' }))).history
assert.deepEqual([comPassos.past.length, comPassos.future.length], [1, 1])
const saidasDoAberto = {
 mascarar: s0,
 removerParametro: withNode(aberto, 'n2', n => ({ ...n, configuration: { ...n.configuration, etl_pipeline_job_param: n.configuration.etl_pipeline_job_param.filter(p => !p.param_type) } })),
 removerEtapa: { ...aberto, definition: ws.removeWorkspaceNode(aberto.definition, aberto.layout, 'n2').definition, layout: ws.removeWorkspaceNode(aberto.definition, aberto.layout, 'n2').layout },
 editarOutraEtapa: withNode(aberto, 'n5', n => ({ ...n, displayName: 'outra' })),
}
for (const [nome, depois] of Object.entries(saidasDoAberto)) {
 if (nome !== 'editarOutraEtapa') assert(!JSON.stringify(depois).includes(SENTINELA), `${nome}: só o antes tem o valor`)
 assert(P.diffPatch(aberto, depois).length, `${nome}: há alteração a registrar`)
 const h = passo(comPassos, aberto, depois)
 assert.deepEqual([h.past.length, h.future.length, h.reset], [0, 0, 'protected'], `${nome}: histórico recomeça`)
 assert(!JSON.stringify(h).includes(SENTINELA), `${nome}: valor de antes fora do histórico`)
 assert.equal(H.undoHistory(h, depois), null, `${nome}: nada a desfazer`)
}
// A verificação vem antes de juntar com o passo de digitação em curso.
const digitando = passo(H.emptyHistory(), s0, withNode(s0, 'n2', n => ({ ...n, displayName: 'x' })), { group: 'campo:n2:displayName', window: H.TEXT_GROUP_MS })
const hDigitando = passo(digitando, withNode(aberto, 'n2', n => ({ ...n, displayName: 'x' })), withNode(s0, 'n2', n => ({ ...n, displayName: 'xy' })), { group: 'campo:n2:displayName', window: H.TEXT_GROUP_MS })
assert.deepEqual([hDigitando.past.length, hDigitando.reset], [0, 'protected']); assert(!JSON.stringify(hDigitando).includes(SENTINELA))
// Parâmetro global aberto em qualquer das duas listas (tabelas legadas ou parameters).
const globalAberto = rows => rows.map(p => p.param_type ? { ...p, param_value: SENTINELA } : p)
const naTabela = { ...s0, definition: { ...s0.definition, metadata: { ...s0.definition.metadata, legacyTables: { ...s0.definition.metadata.legacyTables, etl_pipeline_param: globalAberto(s0.definition.metadata.legacyTables.etl_pipeline_param) } } } }
const emParameters = { ...s0, definition: { ...s0.definition, parameters: globalAberto(s0.definition.metadata.legacyTables.etl_pipeline_param) } }
for (const [nome, antes] of [['legacyTables', naTabela], ['parameters', emParameters]]) {
 assert.equal(H.exposesProtectedValue(antes.definition), true, nome)
 const h = passo(comPassos, antes, s0); assert.equal(h.reset, 'protected', nome); assert(!JSON.stringify(h).includes(SENTINELA), nome)
}
resultado.segredos = { novaReferencia: 'reinicia', valorAberto: 'fora', valorAbertoAntes: Object.keys(saidasDoAberto).length + 3, remocaoLocal: 'desfaz' }

// ── 5. Mescla por campo do inspector ────────────────────────────────────────
const base = at(s0, 'n3')
const formulario = { ...base, configuration: { ...base.configuration, legacyJob: { ...base.configuration.legacyJob, job_command: 'novo comando' } } }
// Outro campo da mesma etapa, outra etapa e metadados mudaram depois que o formulário abriu.
let vivo = withNode(s0, 'n3', n => ({ ...n, displayName: 'Nome novo', configuration: { ...n.configuration, legacyJob: { ...n.configuration.legacyJob, ssh_conn_id: 'ssh_b' } } }))
vivo = withNode(vivo, 'n4', n => ({ ...n, displayName: 'outra' }))
vivo = { ...vivo, definition: { ...vivo.definition, metadata: { ...vivo.definition.metadata, legacyPipeline: { ...vivo.definition.metadata.legacyPipeline, sla_minutos: 5 } } } }
let m = P.mergeNodePatch(vivo.definition, base, formulario)
assert.equal(m.ok, true); const n3 = m.value.nodes.find(n => n.id === 'n3')
assert.deepEqual([n3.displayName, n3.configuration.legacyJob.ssh_conn_id, n3.configuration.legacyJob.job_command], ['Nome novo', 'ssh_b', 'novo comando'])
assert.equal(m.value.nodes.find(n => n.id === 'n4').displayName, 'outra'); assert.equal(m.value.metadata.legacyPipeline.sla_minutos, 5)
assert.deepEqual(n3.configuration.unknownConfig, base.configuration.unknownConfig); assert.deepEqual(n3.extension, base.extension)
// Save clona o rascunho: identidade nova, conteúdo igual — aplicar continua legítimo.
assert.equal(P.mergeNodePatch(clone(vivo.definition), base, formulario).ok, true)
// Mesmo campo alterado fora (ex.: desfazer), etapa removida ou renomeada: conflito explícito.
const mesmoCampo = withNode(vivo, 'n3', n => ({ ...n, configuration: { ...n.configuration, legacyJob: { ...n.configuration.legacyJob, job_command: 'outro' } } }))
for (const [nome, def] of [['mesmo campo', mesmoCampo.definition], ['removida', ws.removeWorkspaceNode(vivo.definition, vivo.layout, 'n3').definition], ['renomeada', ws.renameWorkspaceNode(withNode(vivo, 'n3', n => ({ ...n, configuration: { ...n.configuration, etl_pipeline_job_param: [] } })).definition, vivo.layout, 'n3', 'n3b').definition]]) {
 const c = P.mergeNodePatch(def, base, formulario); assert.equal(c.ok, false, nome); assert.match(c.message, /Nada foi aplicado/)
}
assert.equal(P.mergeNodePatch(vivo.definition, base, { ...formulario, id: 'x' }).ok, false, 'formulário não renomeia')
// Decisão: o painel muda casos e ramos sobre a sua base; uma ligação nova no canvas continua.
const baseDef = s0.definition
const staged = S.editDecisionCases(clone(baseDef), 'n6', { type: 'mode', switch: true })
const comLigacao = { ...baseDef, edges: [...baseDef.edges, { source: 'n9', target: 'n10', novo: true }] }
const md = P.mergeDefinitionPatch(comLigacao, baseDef, staged)
assert.equal(md.ok, true)
assert.deepEqual(md.value.edges, [...staged.edges, { source: 'n9', target: 'n10', novo: true }])
assert.equal(S.specializedConfiguration(md.value.nodes.find(n => n.id === 'n6')).casos[0].nome, 'caso_1')
assert.equal(P.mergeDefinitionPatch({ ...baseDef, edges: baseDef.edges.filter(e => e.target !== 'n7') }, baseDef, staged).ok, false, 'ramo removido no canvas: conflito')
// Aguarde: ligar pontas soltas que o canvas já ligou (duplicada) ou que formariam ciclo é recusado.
const pontas = S.attachLooseEnds(clone(baseDef), 'n7', ['n5'])
assert.equal(P.mergeDefinitionPatch(baseDef, baseDef, pontas).ok, true)
const jaLigada = { ...baseDef, edges: [...baseDef.edges, { source: 'n5', target: 'n7' }] }
const dup = P.mergeDefinitionPatch(jaLigada, baseDef, pontas); assert.equal(dup.ok, false); assert.match(dup.message, /repetida/)
const ciclo = { ...baseDef, edges: [...baseDef.edges, { source: 'n7', target: 'n5' }] }
const cic = P.mergeDefinitionPatch(ciclo, baseDef, pontas); assert.equal(cic.ok, false); assert.match(cic.message, /ciclo/)
resultado.mescla = { outroCampo: 'mantido', clone: 'aplica', conflitos: 3, ramos: 'remapeados', duplicada: 'recusada', ciclo: 'recusado' }

// ── 6. Memória limitada com 300 etapas ──────────────────────────────────────
const grande = fixture(289), tamanho = JSON.stringify(grande).length
let hg = H.emptyHistory(), sg = grande; const t0 = Date.now()
for (let i = 0; i < 60; i++) { const prox = { ...sg, layout: { ...sg.layout, nodes: { ...sg.layout.nodes, [`x${i}`]: { x: i, y: i } } } }; hg = passo(hg, sg, prox, { now: i }); sg = prox }
const rem = ws.removeWorkspaceNode(sg.definition, sg.layout, 'x100'); hg = passo(hg, sg, rem); sg = rem
const ren = ws.renameWorkspaceNode(sg.definition, sg.layout, 'x5', 'x5_novo'); hg = passo(hg, sg, ren); sg = ren
const ms = Date.now() - t0
assert.equal(grande.definition.nodes.length, 300); assert.equal(hg.past.length, 50)
const memoria = JSON.stringify(hg).length
// 50 passos ocupam menos que 1/5 de UMA cópia do rascunho (50 cópias seriam 50×).
assert(memoria < tamanho * 0.2, `histórico ${memoria} B vs uma cópia ${tamanho} B`)
assert(hg.past.every(e => JSON.stringify(e).length < 2000), 'cada passo guarda só o que mudou')
assert(ms < 4000, `tempo ${ms} ms`)
resultado.memoria = { etapas: 300, passos: 50, menorQueUmQuintoDeUmaCopia: true }

// ── 7. Subseção do diagnóstico, JSON protegido e atalhos ────────────────────
assert.deepEqual(['configuration', 'parameters', 'job_command', 'campo_futuro', 'execution_order', 'displayName', 'etl_job_lineage'].map(I.inspectorSectionFor), ['configuracao', 'configuracao', 'configuracao', 'configuracao', 'etapa', 'etapa', 'lineage'])
assert.equal(I.diagnosticFieldLabel('configuration'), 'configuração da etapa'); assert.equal(I.diagnosticFieldLabel('xyz'), 'xyz')
const cfg = at(s0, 'n0').configuration
assert.equal(I.protectedRowsUnchanged(cfg, clone(cfg)), true)
assert.equal(I.protectedRowsUnchanged(cfg, { ...cfg, etl_pipeline_job_param: cfg.etl_pipeline_job_param.map(p => p.param_type ? { ...p, param_value: PLAIN } : p) }), false)
assert.equal(I.protectedRowsUnchanged(cfg, { ...cfg, etl_pipeline_job_param: [...cfg.etl_pipeline_job_param, { param_name: 'z', param_type: 'encrypted', param_value: 'x' }] }), false)
assert.equal(I.protectedRowsUnchanged(cfg, { ...cfg, etl_pipeline_job_param: cfg.etl_pipeline_job_param.filter(p => !p.param_type) }), false)
assert.equal(I.protectedRowsUnchanged(cfg, { ...cfg, etl_pipeline_job_param: cfg.etl_pipeline_job_param.map(p => p.param_type ? p : { ...p, param_value: 'livre' }) }), true)
const ev = (key, mods = {}) => ({ key, ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, isComposing: false, defaultPrevented: false, ...mods })
const ctx = { active: true, textTarget: false, dialogOpen: false }
assert.equal(I.historyShortcut(ev('z', { ctrlKey: true }), ctx), 'undo'); assert.equal(I.historyShortcut(ev('Z', { metaKey: true }), ctx), 'undo')
assert.equal(I.historyShortcut(ev('z', { ctrlKey: true, shiftKey: true }), ctx), 'redo'); assert.equal(I.historyShortcut(ev('y', { ctrlKey: true }), ctx), 'redo')
for (const [e, c] of [[ev('z'), ctx], [ev('y', { metaKey: true }), ctx], [ev('z', { ctrlKey: true, altKey: true }), ctx], [ev('z', { ctrlKey: true, isComposing: true }), ctx], [ev('z', { ctrlKey: true, defaultPrevented: true }), ctx], [ev('z', { ctrlKey: true }), { ...ctx, textTarget: true }], [ev('z', { ctrlKey: true }), { ...ctx, dialogOpen: true }], [ev('z', { ctrlKey: true }), { ...ctx, active: false }]]) assert.equal(I.historyShortcut(e, c), null, JSON.stringify([e, c]))
resultado.atalhos = { desfazer: 2, refazer: 2, ignorados: 8 }

// ── 8. Foco depois de desfazer/refazer no último passo ──────────────────────
// O botão acionado (com foco) fica desabilitado; o navegador manda o foco ao body.
const el = nome => ({ nome }), body = el('body'), undo = el('undo'), redo = el('redo'), canvas = el('canvas'), campo = el('campo')
const foco = (over = {}) => { const off = new Set(over.off ?? ['undo']); return I.historyFocusTarget({ trigger: undo, active: body, body, undo, redo, canvas, disabled: e => off.has(e.nome), visible: true, dialogOpen: false, ...over }) }
assert.equal(foco(), redo, 'último desfazer: foco no Refazer')
assert.equal(foco({ active: undo }), redo, 'foco ainda no botão desabilitado')
assert.equal(foco({ active: null }), redo)
assert.equal(foco({ trigger: redo, active: body, off: ['redo'] }), undo, 'último refazer: foco no Desfazer (simétrico)')
assert.equal(foco({ off: ['undo', 'redo'] }), canvas, 'sem botão habilitado: canvas')
assert.equal(foco({ off: ['undo', 'redo'], canvas: null }), null)
for (const [over, motivo] of [[{ off: [] }, 'botão continua habilitado'], [{ trigger: canvas }, 'atalho com foco no canvas'], [{ trigger: campo, off: ['undo', 'campo'] }, 'campo de texto'], [{ trigger: null }, 'sem viagem'], [{ active: campo }, 'usuário moveu o foco'], [{ dialogOpen: true }, 'diálogo aberto'], [{ visible: false }, 'Montagem oculta/focada']]) assert.equal(foco(over), null, motivo)
resultado.focoHistorico = { restaurados: 6, preservados: 7 }

// ── 9. Foco do diagnóstico com o formulário carregado ───────────────────────
// SQL em edição: o Nome vem antes e é somente leitura; a chave conhecida vai à
// Conexão MSSQL, não ao primeiro campo nem ao JSON.
const ctl = (nome, field, editable = true) => ({ element: el(nome), field, editable })
const secao = el('secao'), nomeSql = ctl('nome', null, false), select = ctl('select', 'sql_json.sql'), conexao = ctl('conexao', 'sql_json.mssql_conn_id'), exibicao = ctl('exibicao', 'displayName')
const alvo = (field, controls, outside = [exibicao]) => I.diagnosticFocusTarget(field, secao, controls, outside).nome
assert.equal(alvo('sql_json.mssql_conn_id', [nomeSql, select, conexao]), 'conexao', 'chave conhecida: controle do campo')
assert.equal(alvo('sql_json.futuro', [nomeSql, select, conexao]), 'select', 'chave desconhecida: primeiro editável, pulando o Nome somente leitura')
assert.equal(alvo('sql_json.mssql_conn_id', [nomeSql, select, ctl('conexao', 'sql_json.mssql_conn_id', false)]), 'select', 'campo conhecido desabilitado não recebe foco de edição')
assert.equal(alvo('displayName', [ctl('ordem', 'execution_order')]), 'exibicao', 'nome para exibição fora da subseção')
assert.equal(alvo('execution_order', [ctl('id', null, false), ctl('ordem', 'execution_order')]), 'ordem')
assert.equal(alvo('etl_job_lineage', [ctl('l1', null), ctl('l2', null)]), 'l1', 'lineage: primeiro campo da subseção')
assert.equal(alvo('campo_futuro', [], [exibicao]), 'secao', 'o nome de fora não é fallback de campo desconhecido')
assert.equal(alvo('sql_json.mssql_conn_id', [nomeSql, ctl('select', 'sql_json.sql', false), ctl('conexao', 'sql_json.mssql_conn_id', false)], [ctl('exibicao', 'displayName', false)]), 'secao', 'modo consulta: fica na subseção')
assert.equal(alvo('displayName', [], [ctl('exibicao', 'displayName', false)]), 'secao')
const gatilho = el('gatilho'), pode = (over = {}) => I.diagnosticFocusAllowed({ active: gatilho, body, trigger: gatilho, visible: true, dialogOpen: false, ...over })
for (const over of [{}, { active: body }, { active: null }]) assert.equal(pode(over), true, JSON.stringify(over))
for (const [over, motivo] of [[{ active: campo }, 'usuário moveu o foco (outra aba, subseção ou campo)'], [{ active: canvas }, 'nova seleção no canvas'], [{ visible: false }, 'inspector ou subseção oculta'], [{ dialogOpen: true }, 'diálogo aberto']]) assert.equal(pode(over), false, motivo)
resultado.focoDiagnostico = { alvos: 9, permitidos: 3, preservados: 4 }

console.log(JSON.stringify({ ...resultado, passed: true }))
