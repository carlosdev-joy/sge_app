// Bancada do detalhe do chamado — `lib/chamadoDetalhe`.
//
// ⚠️ POR QUE ISTO
// Data de nota errada no histórico é pior que nota sem data: ela AFIRMA. E
// tamanho de anexo que diz "0 B" faz alguém não baixar um arquivo que existe.
//
// Saída: um JSON só no stdout.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const UI = path.join(RAIZ, 'ui-react')
const { transform } = require(path.join(UI, 'node_modules', 'sucrase'))

const fonte = fs.readFileSync(
  path.join(UI, 'src', 'lib', 'chamadoDetalhe.ts'), 'utf8')
const js = transform(fonte, { transforms: ['typescript', 'imports'] }).code

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'det-'))
const arquivo = path.join(tmp, 'chamadoDetalhe.cjs')
fs.writeFileSync(arquivo, js)
const L = require(arquivo)

const cenarios = {
  // ── data e hora da nota ───────────────────────────────────────────────────
  // O formato que a API manda de verdade.
  nota_com_hora:   L.dataHoraDaNota('2026-08-28 11:43:30'),
  nota_iso:        L.dataHoraDaNota('2026-08-28T11:43:30'),
  // ISO com Z: `new Date` leria como UTC e, à noite em Brasília, mostraria o
  // dia anterior — uma nota datada errado no histórico afirma o que não foi.
  nota_iso_utc:    L.dataHoraDaNota('2026-08-28T23:30:00Z'),
  nota_so_data:    L.dataHoraDaNota('2026-08-28'),
  nota_nula:       L.dataHoraDaNota(null),
  // Formato desconhecido volta CRU: "Invalid Date" faria o operador achar que
  // o chamado está corrompido.
  nota_estranha:   L.dataHoraDaNota('ontem à tarde'),

  // ── tamanho do anexo ──────────────────────────────────────────────────────
  bytes:           L.tamanhoLegivel(500),
  kb:              L.tamanhoLegivel(2048),
  mb:              L.tamanhoLegivel(3 * 1024 * 1024),
  // O ServiceNow manda 0 quando não sabe o tamanho. "0 B" pareceria arquivo
  // vazio — que é outra coisa, e levaria alguém a não baixar.
  zero:            L.tamanhoLegivel(0),
  sem_tamanho:     L.tamanhoLegivel(null),

  // ── o tipo da nota ────────────────────────────────────────────────────────
  // A distinção não é decorativa: uma fica entre a equipe, a outra o
  // solicitante lê.
  nota_interna:    L.rotuloDaNota('work_notes'),
  nota_publica:    L.rotuloDaNota('comments'),
  nota_sem_tipo:   L.rotuloDaNota(null),
  nota_tipo_novo:  L.rotuloDaNota('additional_comments'),
}

fs.rmSync(tmp, { recursive: true, force: true })
process.stdout.write(JSON.stringify(cenarios))
