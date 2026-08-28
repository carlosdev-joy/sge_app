// Bancada dos cálculos do painel de chamados — `lib/dashboardChamados`.
//
// ⚠️ POR QUE ISTO
// Aritmética de data erra em silêncio: o cartão mostra "faltam 2 dias" para
// quem venceu ontem, e o número é plausível demais para alguém desconfiar.
//
// A data de "hoje" é INJETADA em todos os casos. Sem isso, o teste passaria
// hoje e falharia amanhã, que é a pior forma de teste de data.
//
// Saída: um JSON só no stdout.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))

const fonte = fs.readFileSync(
  path.join(UI, 'src', 'lib', 'dashboardChamados.ts'), 'utf8')
const js = transform(fonte, { transforms: ['typescript', 'imports'] }).code

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dash-'))
const arquivo = path.join(tmp, 'dashboardChamados.cjs')
fs.writeFileSync(arquivo, js)
const L = require(arquivo)

const HOJE = new Date(2026, 7, 28)          // 28/08/2026, meia-noite local
const c = (extra) => Object.assign(
  { sys_id: 'x', numero: 'RITM1', titulo: 't', atribuido_a: null,
    estado_kanban: 'novo', prazo: null, aberto_em: null, url: null,
    sla_vencido: null, tipo_demanda: null, atribuido_a_email: null,
    encerrado_em: null, atualizado_em: null }, extra)

const cenarios = {
  // ── dias até o prazo ──────────────────────────────────────────────────────
  venceu_ontem:        L.diasAteOPrazo('2026-08-27', HOJE),
  vence_hoje:          L.diasAteOPrazo('2026-08-28', HOJE),
  vence_amanha:        L.diasAteOPrazo('2026-08-29', HOJE),
  // hora do dia NÃO decide: prazo de hoje às 09:00 não está atrasado às 14:00
  hoje_com_hora:       L.diasAteOPrazo('2026-08-28 09:00:00', HOJE),
  sem_prazo:           L.diasAteOPrazo(null, HOJE),
  prazo_vazio:         L.diasAteOPrazo('', HOJE),
  prazo_ilegivel:      L.diasAteOPrazo('não é data', HOJE),

  // ── o prazo em palavras ───────────────────────────────────────────────────
  rotulo_atrasado:     L.rotuloDoPrazo('2026-08-25', HOJE),
  rotulo_hoje:         L.rotuloDoPrazo('2026-08-28', HOJE),
  rotulo_no_prazo:     L.rotuloDoPrazo('2026-09-02', HOJE),
  rotulo_sem_prazo:    L.rotuloDoPrazo(null, HOJE),

  // ── a data do prazo, para conferir a olho ────────────────────────────────
  // O formato que a API manda de verdade: "2026-08-28 11:43:30".
  data_com_hora:       L.dataDoPrazo('2026-08-28 11:43:30'),
  data_so_dia:         L.dataDoPrazo('2026-08-28'),
  // ISO com Z: `new Date` leria como UTC e, à noite no fuso de Brasília,
  // devolveria o DIA ANTERIOR. A leitura textual não cai nisso.
  data_iso_utc:        L.dataDoPrazo('2026-08-28T23:30:00Z'),
  data_nula:           L.dataDoPrazo(null),
  data_vazia:          L.dataDoPrazo(''),
  data_ilegivel:       L.dataDoPrazo('em breve'),

  // ── quem mostra prazo ─────────────────────────────────────────────────────
  mostra_novo:         L.mostraPrazo('novo'),
  mostra_aguardando:   L.mostraPrazo('aguardando'),
  mostra_resolvido:    L.mostraPrazo('resolvido'),
  mostra_encerrado:    L.mostraPrazo('encerrado'),

  // ── fatias ────────────────────────────────────────────────────────────────
  responsavel: L.contaPorResponsavel([
    c({ atribuido_a: 'Fulano' }), c({ atribuido_a: '   ' }), c({}),
  ]).map(f => [f.rotulo, f.valor]),

  prazo: L.contaPorPrazo([
    c({ prazo: '2026-08-30' }),   // dentro
    c({ prazo: '2026-08-28' }),   // vence hoje → ainda dentro
    c({ prazo: '2026-08-20' }),   // fora
    c({}),                        // sem prazo
  ], HOJE).map(f => [f.rotulo, f.valor]),

  // ── a data do fim, e o quanto ela é afirmação ────────────────────────────
  fim_exato: L.dataDoFim({ encerrado_em: '2026-08-27 10:00:00',
                           atualizado_em: '2026-08-28 12:00:00' }),
  // O caso REAL: resolvido no ServiceNow não preenche closed_at. Dos 21
  // resolvidos ativos no dev, ZERO tinham `encerrado_em`.
  fim_aproximado: L.dataDoFim({ encerrado_em: null,
                                atualizado_em: '2026-08-28 12:35:28' }),
  fim_sem_data: L.dataDoFim({ encerrado_em: null, atualizado_em: null }),

  // ── leitura dos blocos da resposta ────────────────────────────────────────
  bloco_ok: (() => {
    const b = L.bloco({ backlog: { label: 'Demandas Backlog', cor: 'amber',
                                   total: 3, chamados: [c({})] } }, 'backlog')
    return [b.label, b.cor, b.total, b.chamados.length]
  })(),
  bloco_ausente:  L.bloco({}, 'backlog'),
  bloco_resposta_indefinida: L.bloco(undefined, 'backlog'),
  // O painel de produção lia `d.backlog` como NÚMERO. Se a resposta vier
  // assim, isto devolve null em vez de deixar um número virar "bloco".
  bloco_numero:   L.bloco({ backlog: 7 }, 'backlog'),
  bloco_sem_lista: (() => {
    const b = L.bloco({ backlog: { total: 2 } }, 'backlog')
    return [b.label, b.cor, b.chamados.length]
  })(),
}

fs.rmSync(tmp, { recursive: true, force: true })
process.stdout.write(JSON.stringify(cenarios))
