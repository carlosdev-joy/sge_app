// Bancada da separação da fila — `lib/filaChamados.separarFila`.
//
// ⚠️ POR QUE ISTO, E NÃO `grep` NO `Chamados.tsx`
// O que esta fase entrega é uma RECUSA: a task com pai deixa de virar card. E
// recusa não aparece na tela — o que aparece é um card a menos. Um `grep` por
// `separarFila` ficaria verde com a chamada presente e a regra invertida
// (escondendo a órfã, ou escondendo o pai).
//
// Os cenários patológicos são o coração: órfã, string vazia (o que o sync
// grava de verdade), filho antes do pai na ordem, e a task cujo pai não está
// na fila. Sem eles, um agrupamento ingênuo passa verde e some com card em
// produção.
//
// Saída: um JSON só no stdout.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))

const fonte = fs.readFileSync(
  path.join(UI, 'src', 'lib', 'filaChamados.ts'), 'utf8')
const js = transform(fonte, { transforms: ['typescript', 'imports'] }).code

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'fila-'))
const arquivo = path.join(tmp, 'filaChamados.cjs')
fs.writeFileSync(arquivo, js)
const { separarFila } = require(arquivo)


const ritm = (id) => ({ sys_id: id, tipo: 'ritm', pai_sys_id: null })
const task = (id, pai) => ({ sys_id: id, tipo: 'task', pai_sys_id: pai })

const resumo = (r) => ({
  cards: r.cards.map(c => c.sys_id),
  filhas: Object.fromEntries(
    [...r.filhasPorPai.entries()].map(([k, v]) => [k, v.map(x => x.sys_id)])),
})

const cenarios = {
  // O caso comum: um pedido e sua tarefa → um card, uma filha.
  par_ritm_task: resumo(separarFila([ritm('R1'), task('T1', 'R1')])),

  // A ÓRFÃ CONTINUA CARD — pai_sys_id nulo.
  orfa_nula: resumo(separarFila([ritm('R1'), task('T9', null)])),

  // O sync grava '' quando o campo não vem da API. '' é ausência: tratar como
  // valor faria toda linha ter "pai" e a fila inteira sumiria.
  orfa_string_vazia: resumo(separarFila([ritm('R1'), task('T9', '')])),

  // Task cujo pai NÃO está na fila (pai encerrado, ou fora do grupo): ela sai
  // da lista de cards e vai para o índice sob um pai que ninguém renderiza.
  // O card some da tela — é o preço da regra, e o teste registra isso em vez
  // de fingir que não acontece.
  pai_fora_da_fila: resumo(separarFila([ritm('R1'), task('T2', 'R-INEXISTENTE')])),

  // Auto-referência: a task aponta para si mesma. Se ela saísse, seria filha
  // de si própria — sumiria da fila E das contas, sem nada avisar. Dado
  // corrompido tem de APARECER.
  auto_referencia: resumo(separarFila([ritm('R1'), task('T7', 'T7')])),

  // Ordem não importa: filho antes do pai dá o mesmo resultado.
  filho_antes_do_pai: resumo(separarFila([task('T1', 'R1'), ritm('R1')])),

  // Duas tarefas no mesmo pedido: um card, duas filhas, na ordem de chegada.
  duas_filhas: resumo(separarFila([ritm('R1'), task('T1', 'R1'), task('T2', 'R1')])),

  // Um RITM que por engano tivesse pai continua card: a regra recusa APENAS
  // quem é task. Sem isso, um dado torto tiraria pedidos da fila.
  ritm_com_pai_continua_card: resumo(separarFila([
    { sys_id: 'R2', tipo: 'ritm', pai_sys_id: 'R1' }, ritm('R1')])),

  // Incidente nunca tem pai e nunca sai.
  incidente: resumo(separarFila([{ sys_id: 'I1', tipo: 'incident', pai_sys_id: null }])),

  // A contagem que a tela mostra: 3 registros, 2 trabalhos.
  contagem: separarFila([ritm('R1'), task('T1', 'R1'), ritm('R2')]).cards.length,
}

fs.rmSync(tmp, { recursive: true, force: true })
process.stdout.write(JSON.stringify(cenarios))
