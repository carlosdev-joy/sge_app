// Bancada da EOC-F3 L3: as 8 agendas pelo formulário legado e pelo workspace.
//
// Executa o código REAL do src/ (sucrase + minireact; carregador copiado de
// pipeline_index_harness.cjs):
//  1. Legado: `defaultForm`, `schedCfg` e `buildSchedulePayload` recortados de
//     PipelineFormModal.tsx, avaliados com o pipelineUtils real. É o body que o
//     modal envia ao POST /pipelines/register.
//  2. Workspace: WorkspaceScheduleFields montado e operado pelos controles
//     (tipo, horário, dia, janela, dias do mês, checkboxes). O valor final é o
//     legacyPipeline que o rascunho guarda e a publicação projeta.
//  3. hourly_n: janelas iguais nos dois lados → listas de `hourlyTimes`.
//  4. Leitura de cadastro existente: o tipo que cada tela mostra para a
//     mesma linha de etl_pipeline (pipelineToForm × kind do workspace).
//
// Saída: um JSON na última linha. O pytest compara cron e constantes da DAG.
'use strict'
const fs = require('fs'), os = require('os'), path = require('path'), assert = require('assert/strict')
const RAIZ = path.resolve(__dirname, '..', '..'), SRC = path.join(RAIZ, 'ui-react', 'src')
const { transform } = require(path.join(RAIZ, 'ui-react', 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADAS = ['components/workspace/WorkspacePipelineFields.tsx', 'components/pipelines/pipelineUtils.ts']
// Campos da casa viram nós de host com o rótulo à vista; o que se testa é o valor emitido.
const campo = tag => `p => { const { label, ajuda, hint, error, children, ...rest } = p; return jsx(${JSON.stringify(tag)}, Object.assign({}, rest, { 'data-rotulo': label, children })) }`
const DUBLES = {
 'lib/api.ts': 'exports.apiFetch = async () => ({})',
 'components/ui/Input.tsx': `const { jsx } = require('react/jsx-runtime'); exports.Input = ${campo('input')}; exports.Select = ${campo('select')}; exports.Textarea = ${campo('textarea')}`,
 'components/ui/Button.tsx': `const { jsx } = require('react/jsx-runtime'); exports.Button = p => jsx('button', p)`,
}
function resolver(de, esp) {
 const base = path.resolve(de, esp)
 for (const alvo of [base + '.tsx', base + '.ts', path.join(base, 'index.tsx'), path.join(base, 'index.ts')]) if (fs.existsSync(alvo)) return alvo
 return null
}
function preparar(destino) {
 const feitos = new Set(), fila = ENTRADAS.map(e => path.join(SRC, e))
 while (fila.length) {
  const arquivo = fila.pop(); if (feitos.has(arquivo)) continue; feitos.add(arquivo)
  const rel = path.relative(SRC, arquivo), alvo = path.join(destino, rel.replace(/\.tsx?$/, '.js'))
  fs.mkdirSync(path.dirname(alvo), { recursive: true })
  if (DUBLES[rel]) { fs.writeFileSync(alvo, DUBLES[rel]); continue }
  const fonte = fs.readFileSync(arquivo, 'utf8')
  fs.writeFileSync(alvo, transform(fonte, { transforms: ['typescript', 'jsx', 'imports'], jsxRuntime: 'automatic', production: true, filePath: arquivo }).code)
  for (const m of fonte.matchAll(/^\s*import\s+(?!type\s)[^;'"]*?from\s*['"](\.[^'"]+)['"]/gm)) {
   const dep = resolver(path.dirname(arquivo), m[1]); if (dep) fila.push(dep)
  }
 }
}
function shims(destino) {
 const escrever = (pacote, arquivo, conteudo) => { const dir = path.join(destino, 'node_modules', pacote); fs.mkdirSync(dir, { recursive: true }); fs.writeFileSync(path.join(dir, arquivo), conteudo) }
 const pacote = (nome, conteudo) => { escrever(nome, 'package.json', JSON.stringify({ name: nome, main: 'index.js' })); escrever(nome, 'index.js', conteudo) }
 const MINI = JSON.stringify(path.join(__dirname, 'minireact.cjs'))
 // Efeitos rodam aqui (na minireact são no-op): uma leitura que reescrevesse o valor
 // por efeito tem de aparecer em `intacto`. Fila descarregada por `operar`.
 pacote('react', `const mini = require(${MINI}); let seq = 0; const efeitos = []
const efeito = (fn, deps) => { const r = mini.hooks.useRef(null); if (!deps || !r.current || deps.length !== r.current.length || deps.some((d, i) => !Object.is(d, r.current[i]))) { r.current = deps || null; efeitos.push(fn) } }
module.exports = Object.assign({}, mini.hooks, { useEffect: efeito, useLayoutEffect: efeito, __efeitos: efeitos, createElement: mini.criar, Fragment: mini.FRAGMENT, forwardRef: r => p => r(p, null), useId: () => { const r = mini.hooks.useRef(null); if (r.current === null) r.current = 'orq-' + (++seq); return r.current } })
module.exports.default = module.exports`)
 const runtime = `const mini = require(${MINI}); const jsx = (tipo, props, key) => ({ __el: true, tipo, props: props || {}, key }); module.exports = { jsx, jsxs: jsx, jsxDEV: jsx, Fragment: mini.FRAGMENT }`
 escrever('react', 'jsx-runtime.js', runtime)
 pacote('@tanstack/react-query', 'exports.useQuery = () => ({ data: undefined, isPending: false, isError: false, refetch() {} })')
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'eoc-f3-agendas-'))
preparar(tmp); shims(tmp)
const req = rel => require(path.join(tmp, rel))
const utils = req('components/pipelines/pipelineUtils.js'), { WorkspaceScheduleFields } = req('components/workspace/WorkspacePipelineFields.js')
const React = req('node_modules/react/index.js'), { jsx } = req('node_modules/react/jsx-runtime.js')

// ── Legado: trechos reais do modal ───────────────────────────────────────────
const modal = fs.readFileSync(path.join(SRC, 'components/pipelines/PipelineFormModal.tsx'), 'utf8')
const recorte = re => { const m = modal.match(re); assert(m, 'trecho do PipelineFormModal não encontrado: ' + re); return m[0] }
const trechos = [
 recorte(/^const defaultForm = \(\): FormState => \(\{[\s\S]*?\n\}\)\n/m),
 recorte(/^function pipelineToForm\(p: Pipeline\): FormState \{[\s\S]*?\n\}\n/m),
 recorte(/^ {2}const schedCfg: ScheduleConfig = \{[\s\S]*?\n {2}\}\n/m),
 recorte(/^ {2}function buildSchedulePayload\(\) \{[\s\S]*?\n {2}\}\n/m),
].map(t => transform(t, { transforms: ['typescript'] }).code)
const nomes = ['hourlyTimes', 'parseCustomTimes', 'serializeMonthDaysTimes', 'parseMonthDaysTimes']
const legadoFn = new Function('form', ...nomes, trechos.join('\n') + '\nreturn buildSchedulePayload()')
const reabrirFn = new Function('form', 'linha', ...nomes, trechos.slice(0, 2).join('\n') + '\nreturn pipelineToForm(linha)')
const comUtils = fn => (...args) => fn(...args, ...nomes.map(n => utils[n]))
const formPadrao = new Function(trechos[0] + '\nreturn defaultForm()')
const legado = over => comUtils(legadoFn)(Object.assign(formPadrao(), over))
const reabrir = linha => comUtils(reabrirFn)(null, linha)

// ── Workspace: componente real, controlado pelo pai como no editor ──────────
function operar(inicial, passos) {
 const estado = { chamadas: 0 }
 function Pai() { const [value, setValue] = React.useState(inicial); estado.value = value; return jsx(WorkspaceScheduleFields, { value, editable: true, onChange: next => { estado.chamadas++; setValue(next) } }) }
 const tela = mini.montar(jsx(Pai, {})).sincronizar()
 const efeitos = () => { for (let volta = 0; React.__efeitos.length && volta < 20; volta++) { React.__efeitos.splice(0).forEach(f => f()); tela.sincronizar() } }
 efeitos()
 const rotulado = (tag, rotulo) => { const [n] = tela.achar(x => x.tag === tag && x.props['data-rotulo'] === rotulo); assert(n, `${tag} "${rotulo}" ausente`); return n }
 const caixa = rotulo => { const [l] = tela.achar(x => x.tag === 'label' && x.filhos.includes(rotulo)); assert(l, `checkbox "${rotulo}" ausente`); return l.filhos.find(f => typeof f !== 'string' && f.tag === 'input') }
 for (const [acao, alvo, valor] of passos) {
  if (acao === 'select') tela.disparar(rotulado('select', alvo), 'onChange', { target: { value: valor } })
  else if (acao === 'input') tela.disparar(rotulado('input', alvo), 'onChange', { target: { value: valor } })
  else if (acao === 'marcar') tela.disparar(caixa(alvo), 'onChange', { target: { checked: valor } })
  else if (acao === 'botao') tela.clicar(tela.botoes(alvo)[0])
  else throw new Error('ação desconhecida ' + acao)
  efeitos()
 }
 const visivel = rotulo => { const [n] = tela.achar(x => x.tag === 'input' && x.props['data-rotulo'] === rotulo); return n ? n.props.value : null }
 return { value: estado.value, tipo: rotulado('select', 'Tipo de agendamento').props.value, texto: tela.texto, chamadas: estado.chamadas,
  horario: visivel('Horário da agenda'), horarios: visivel('Horários de execução') }
}

// Rascunho novo nasce sob demanda (lib/workspace.ts:62); o usuário escolhe a agenda.
const NOVO = { pipeline_name: 'PIPE_A', schedule_type: 'on_demand', active: 1 }
const TIPO = 'Tipo de agendamento'
const CENARIOS = {
 daily: [{ schedule_type: 'daily', schedule_hour: 9, schedule_minute: 30 }, [['select', TIPO, 'daily'], ['input', 'Horário da agenda', '09:30']]],
 daily_meia_noite: [{ schedule_type: 'daily', schedule_hour: 0, schedule_minute: 0 }, [['select', TIPO, 'daily'], ['input', 'Horário da agenda', '00:00']]],
 daily_23_59: [{ schedule_type: 'daily', schedule_hour: 23, schedule_minute: 59 }, [['select', TIPO, 'daily'], ['input', 'Horário da agenda', '23:59']]],
 weekly_domingo: [{ schedule_type: 'weekly', schedule_hour: 7, schedule_minute: 5, schedule_dow: 0, somente_dias_uteis: true, calendario_nome: 'FERIADOS_B3' },
  [['select', TIPO, 'weekly'], ['input', 'Horário da agenda', '07:05'], ['select', 'Dia da semana', '0'], ['marcar', 'Somente dias úteis', true], ['select', 'Calendário de feriados', 'FERIADOS_B3']]],
 weekly_sabado: [{ schedule_type: 'weekly', schedule_hour: 18, schedule_minute: 0, schedule_dow: 6 }, [['select', TIPO, 'weekly'], ['input', 'Horário da agenda', '18:00'], ['select', 'Dia da semana', '6']]],
 monthly_1: [{ schedule_type: 'monthly', schedule_hour: 6, schedule_minute: 0, schedule_dom: 1 }, [['select', TIPO, 'monthly'], ['input', 'Horário da agenda', '06:00']]],
 monthly_28: [{ schedule_type: 'monthly', schedule_hour: 2, schedule_minute: 15, schedule_dom: 28 }, [['select', TIPO, 'monthly'], ['input', 'Horário da agenda', '02:15'], ['input', 'Dia do mês (1–28)', '28']]],
 biweekly_13: [{ schedule_type: 'biweekly', schedule_hour: 5, schedule_minute: 45, schedule_dom: 13 }, [['select', TIPO, 'biweekly'], ['input', 'Horário da agenda', '05:45'], ['input', 'Dia da primeira quinzena (1–13)', '13']]],
 custom: [{ schedule_type: 'custom', schedule_custom_times: '14:30, 9:05', schedule_weekdays: [5, 1, 3] },
  [['select', TIPO, 'custom'], ['input', 'Horários de execução', '14:30, 9:05'], ['marcar', 'Sex', true], ['marcar', 'Seg', true], ['marcar', 'Qua', true]]],
 monthly_days_times: [{ schedule_type: 'monthly_days_times', schedule_month_days: [{ dia: 5, horariosRaw: '09:00' }, { dia: 15, horariosRaw: '06:30, 18:00' }] },
  [['select', TIPO, 'monthly_days_times'], ['input', 'Dia do mês 1', '5'], ['input', 'Horários do dia 1', '09:00'], ['botao', 'Adicionar dia e horários'], ['input', 'Dia do mês 2', '15'], ['input', 'Horários do dia 2', '06:30, 18:00']]],
 // Ordem e grafia livres: o workspace guarda o texto digitado, o legado normaliza.
 monthly_days_times_fora_de_ordem: [{ schedule_type: 'monthly_days_times', schedule_month_days: [{ dia: 15, horariosRaw: '18:00, 6:30' }, { dia: 5, horariosRaw: '09:00' }] },
  [['select', TIPO, 'monthly_days_times'], ['input', 'Dia do mês 1', '15'], ['input', 'Horários do dia 1', '18:00, 6:30'], ['botao', 'Adicionar dia e horários'], ['input', 'Dia do mês 2', '5'], ['input', 'Horários do dia 2', '09:00']]],
 custom_repetido: [{ schedule_type: 'custom', schedule_custom_times: '09:00, 9:00, 08:00', schedule_weekdays: [1] },
  [['select', TIPO, 'custom'], ['input', 'Horários de execução', '09:00, 9:00, 08:00'], ['marcar', 'Seg', true]]],
 on_demand: [{ schedule_type: 'on_demand', schedule_hour: 10, schedule_minute: 15 }, [['select', TIPO, 'custom'], ['input', 'Horários de execução', '10:15'], ['select', TIPO, 'on_demand']]],
}
const resultado = { cenarios: {}, hourly: [], leitura: {} }
for (const [nome, [form, passos]] of Object.entries(CENARIOS)) {
 const ws = operar(NOVO, passos)
 resultado.cenarios[nome] = { legado: legado(form), workspace: ws.value, tipoWorkspace: ws.tipo }
}

// hourly_n: (a cada N, início, fim, minuto). O último caso tem janela invertida.
const JANELAS = [[2, 8, 18, 0], [3, 0, 23, 15], [1, 0, 23, 45], [5, 22, 23, 0], [23, 0, 23, 59], [4, 7, 7, 30], [2, 18, 8, 0]]
for (const [intervalo, inicio, fim, minuto] of JANELAS) {
 const form ={ schedule_type: 'hourly_n', schedule_interval_hours: intervalo, schedule_start_hour: inicio, schedule_end_hour: fim, schedule_minute: minuto }
 const ws = operar(NOVO, [['select', TIPO, 'hourly_n'], ['input', 'A cada quantas horas?', String(intervalo)], ['input', 'Hora final', String(fim)], ['input', 'Hora inicial', String(inicio)], ['input', 'Minuto', String(minuto)]])
 const cfg = { type: 'hourly_n', hour: 6, dow: 1, dom: 1, customTimes: '', weekdays: [], businessDaysOnly: false, intervalH: intervalo, startH: inicio, endH: fim, minute: minuto }
 resultado.hourly.push({ janela: [intervalo, inicio, fim, minuto], lista: utils.hourlyTimes(cfg), legado: legado(form), workspace: ws.value, tipoWorkspace: ws.tipo })
}

// Mesma linha de etl_pipeline aberta pelas duas telas (sem edição). `intacto`: a
// leitura não chama onChange e o valor continua byte a byte o da linha.
const LINHAS = {
 tipo_nulo: { pipeline_name: 'PIPE_A', schedule_type: null, scheduled_time: '06:00:00', schedule_hour: 6, schedule_minute: 0 },
 tipo_nulo_sem_horario: { pipeline_name: 'PIPE_A', schedule_type: null, scheduled_time: null },
 tipo_vazio: { pipeline_name: 'PIPE_A', schedule_type: '', scheduled_time: '07:15:00' },
 tipo_ausente: { pipeline_name: 'PIPE_A', scheduled_time: '06:00:00' },
 daily_com_horarios: { pipeline_name: 'PIPE_A', schedule_type: 'daily', scheduled_time: '06:00:00', horarios_especificos: '09:00,14:00' },
 nulo_com_horarios: { pipeline_name: 'PIPE_A', schedule_type: null, scheduled_time: '06:00:00', horarios_especificos: '09:00,14:00', dias_semana: '1,3' },
 weekly_com_horarios: { pipeline_name: 'PIPE_A', schedule_type: 'weekly', scheduled_time: '06:00:00', schedule_dow: 3, horarios_especificos: '08:30' },
 daily_horarios_em_branco: { pipeline_name: 'PIPE_A', schedule_type: 'daily', scheduled_time: '06:00:00', horarios_especificos: '  ' },
 daily_horarios_ilegiveis: { pipeline_name: 'PIPE_A', schedule_type: 'daily', scheduled_time: '06:00:00', horarios_especificos: 'manha, 9:' },
 daily_com_dias_do_mes: { pipeline_name: 'PIPE_A', schedule_type: 'daily', scheduled_time: '06:00:00', dias_horarios_mes: '[{"dia": 5, "horarios": ["09:00"]}]' },
 on_demand: { pipeline_name: 'PIPE_A', schedule_type: 'on_demand', scheduled_time: '06:00:00' },
 on_demand_com_horarios: { pipeline_name: 'PIPE_A', schedule_type: 'on_demand', scheduled_time: '06:00:00', horarios_especificos: '09:00' },
 custom: { pipeline_name: 'PIPE_A', schedule_type: 'custom', scheduled_time: '09:00:00', horarios_especificos: '09:00,14:00' },
}
for (const [nome, linha] of Object.entries(LINHAS)) {
 const ws = operar(linha, [])
 resultado.leitura[nome] = { linha, legado: reabrir(linha).schedule_type, workspace: ws.tipo, semDisparo: ws.texto.includes('sem disparo automático'),
  horario: ws.horario, horarios: ws.horarios, intacto: ws.chamadas === 0 && JSON.stringify(ws.value) === JSON.stringify(linha) }
}
// R2 editado pelo campo que a tela mostra: muda só o que o campo grava.
try {
 const r2 = operar(LINHAS.daily_com_horarios, [['input', 'Horários de execução', '10:00, 15:30']])
 resultado.leitura_editada = { value: r2.value, tipo: r2.tipo }
} catch (e) { resultado.leitura_editada = { erro: e.message } }
// Regra pura usada também pelo resumo "Agenda" da página do workspace.
const { effectiveScheduleType } = req('lib/workspace.js')
resultado.regra = typeof effectiveScheduleType === 'function' ? Object.fromEntries(Object.entries(LINHAS).map(([nome, linha]) => [nome, effectiveScheduleType(linha)])) : null
fs.rmSync(tmp, { recursive: true, force: true })
console.log(JSON.stringify(resultado))
