// Valores de exemplo da prévia do e-mail e a troca dos marcadores — as partes
// PURAS, exercitadas pela bancada tests/js/ds_params_harness.cjs.
//
// Os nomes e formatos espelham o que o operador do worker resolve em tempo de
// corrida (dags/utils/email_operator.py, `_mapa`): é isso que faz a prévia
// mostrar um e-mail parecido com o que chega, e não um rascunho genérico.

/** Tabela de exemplo da prévia — espelha `tabela_html` (dags/utils/sql_node.py).
 *
 *  ⚠️ As duas precisam produzir o MESMO markup para os mesmos dados: a prévia é
 *  o que a pessoa aprova antes de salvar, e um estilo diferente aqui faria a
 *  tela prometer um aviso que não é o que chega. O teste cruzado roda os mesmos
 *  dados nos dois lados e compara. */
export function tabelaExemploHtml(): string {
  return tabelaHtml({
    columns: ['Produto', 'Sanções'],
    rows: [['ACIDO ACETILSALICILICO 100MG', '3'], ['DIPIRONA 500MG', '1']],
    total: 2, truncado: false, havia_mais: false, colunas_ocultas: 0,
  })
}

export interface TabelaSql {
  columns: string[]
  rows: (string | number | boolean | null)[][]
  total: number
  truncado: boolean
  havia_mais: boolean
  colunas_ocultas: number
}

const _BORDA = '#E2E8F0'
const _CABECALHO = '#F8FAFC'
const _TINTA = '#1E293B'
const _TINTA_FRACA = '#64748B'

function escaparCelula(valor: string | number | boolean | null): string {
  if (valor === null || valor === '') return `<span style="color:${_TINTA_FRACA};">—</span>`
  return String(valor).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function avisoDeCorte(t: TabelaSql): string {
  const mostradas = (t.rows ?? []).length
  const partes: string[] = []
  if (t.havia_mais) partes.push(`mostrando ${mostradas} de mais de ${String(t.total).replace(/\B(?=(\d{3})+(?!\d))/g, '.')} linhas`)
  else if (t.truncado) partes.push(`mostrando ${mostradas} de ${t.total} linhas`)
  if (t.colunas_ocultas) partes.push(`${t.colunas_ocultas} coluna${t.colunas_ocultas > 1 ? 's' : ''} não cabem no aviso`)
  return partes.join(' · ')
}

/** Espelho de `tabela_html` do worker — ver a nota em `tabelaExemploHtml`. */
export function tabelaHtml(t: TabelaSql): string {
  const colunas = t.columns ?? []
  const linhas = t.rows ?? []
  if (!colunas.length) return `<div style="color:${_TINTA_FRACA};font-size:12px;">(sem resultado)</div>`

  const th = colunas.map(c =>
    `<th align="left" style="padding:8px 12px;border-bottom:1px solid ${_BORDA};`
    + `color:${_TINTA_FRACA};font-size:11px;font-weight:600;text-transform:uppercase;`
    + `letter-spacing:0.5px;">${escaparCelula(c)}</th>`).join('')

  const corpo = linhas.map((linha, i) => {
    const fundo = i % 2 ? ` bgcolor="${_CABECALHO}"` : ''
    const tds = linha.map(v =>
      `<td style="padding:8px 12px;border-bottom:1px solid ${_BORDA};`
      + `color:${_TINTA};font-size:13px;">${escaparCelula(v)}</td>`).join('')
    return `<tr${fundo}>${tds}</tr>`
  })
  if (!linhas.length) {
    corpo.push(`<tr><td colspan="${colunas.length}" style="padding:10px 12px;`
      + `color:${_TINTA_FRACA};font-size:12px;">A consulta não devolveu linhas.</td></tr>`)
  }

  const aviso = avisoDeCorte(t)
  const rodape = aviso
    ? `<tr><td colspan="${colunas.length}" style="padding:8px 12px;`
      + `color:${_TINTA_FRACA};font-size:11px;">${aviso}</td></tr>`
    : ''

  return '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
    + `style="width:100%;border:1px solid ${_BORDA};border-radius:8px;`
    + 'border-collapse:collapse;font-family:Segoe UI,Helvetica,Arial,sans-serif;">'
    + `<tr bgcolor="${_CABECALHO}">${th}</tr>` + corpo.join('') + rodape + '</table>'
}

/** Um valor por marcador que o operador resolve. */
export const VALORES_EXEMPLO: Record<string, string> = {
  pipeline: 'CARGA_VIDA',
  job: 'AVISA_EQUIPE',
  data: '11/09/2026 14:30',
  // AAAAMMDD, como o DataStage recebe no -param: é a data de REFERÊNCIA da
  // corrida, que num fluxo diário não é a de hoje.
  odate: '20260911',
  linhas: '4.200',
  status: 'SUCCESS',
  inicio: '11/09/2026 14:02',
  duracao: '00:28:11',
  execution_id: '20260911T140200',
  // `{tabela}` — o resultado do nó SQL a montante (F5). Na corrida, o operador
  // renderiza a tabela de verdade; aqui vale um exemplo com a MESMA aparência,
  // para a prévia mostrar como o aviso fica e não um espaço vazio.
  tabela: tabelaExemploHtml(),
}

/** Mesma regra do backend: `{chave}` conhecida vira valor, desconhecida fica
 *  INTACTA — na prévia e no e-mail, um marcador errado aparece como está. */
export function interpolarExemplo(texto: string): string {
  // `{tabela:NO_SQL}` (com qualificador) também resolve na prévia: ela mostra a
  // MESMA tabela de exemplo, porque na tela não há corrida para saber qual nó
  // trouxe o quê — o que importa é ver como o aviso fica com uma tabela dentro.
  return (texto ?? '').replace(/\{([a-z_]+)(?::[A-Za-z0-9_-]{1,128})?\}/g, (achado, chave: string) =>
    Object.prototype.hasOwnProperty.call(VALORES_EXEMPLO, chave)
      ? VALORES_EXEMPLO[chave]
      : achado)
}

/** Marcadores usados no texto que o operador NÃO conhece. Alimenta o aviso do
 *  painel: é o erro de digitação que só apareceria no e-mail já enviado.
 *
 *  Pega dois casos:
 *  - nome inexistente (`{linas}`);
 *  - **caixa errada** (`{ODATE}`, `{Pipeline}`) — o erro mais provável de todos,
 *    e que passaria calado, porque o backend só resolve minúsculas. */
export function marcadoresDesconhecidos(texto: string): string[] {
  const achados: string[] = []
  for (const [, chave] of (texto ?? '').matchAll(/\{([A-Za-z_]+)(?::[A-Za-z0-9_-]{1,128})?\}/g)) {
    const conhecido = Object.prototype.hasOwnProperty.call(VALORES_EXEMPLO, chave)
    if (!conhecido && !achados.includes(chave)) achados.push(chave)
  }
  return achados
}

/** O mesmo aviso, dito de um jeito que ajuda: marcador só com a caixa errada
 *  ganha a sugestão pronta. */
export function dicaDoMarcador(chave: string): string | null {
  const minusculo = chave.toLowerCase()
  if (chave !== minusculo && Object.prototype.hasOwnProperty.call(VALORES_EXEMPLO, minusculo)) {
    return `{${minusculo}}`
  }
  return null
}

/** O documento que vai para o iframe.
 *
 *  Corpo que já É um documento (tem `<html>` ou `<body>`) entra INTEIRO, sem
 *  moldura nossa: embrulhá-lo faria o navegador descartar os atributos do
 *  `<body>` do modelo — o `style` com o fundo, entre eles — e a prévia mentiria
 *  justamente sobre o que promete mostrar. É o caso dos modelos institucionais.
 */
export function montarDocumento(conteudo: string, html: boolean): string {
  // `a{pointer-events:none}`: sem isso, clicar num link do corpo navega a
  // própria prévia para fora e ela vira uma página de erro, sem botão de volta.
  const trava = '<style>a{pointer-events:none;}</style>'

  if (html && /<(html|body)\b/i.test(conteudo)) {
    return /<\/head>/i.test(conteudo)
      ? conteudo.replace(/<\/head>/i, `${trava}</head>`)
      : `${trava}${conteudo}`
  }

  const corpoHtml = html
    ? conteudo
    : `<pre style="margin:0;font:13px/1.6 Segoe UI,Helvetica,Arial,sans-serif;white-space:pre-wrap;word-break:break-word;">${escapar(conteudo)}</pre>`
  return '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
    + `<meta name="color-scheme" content="light">${trava}</head>`
    + `<body style="margin:0;background:#ffffff;color:#111111;">${corpoHtml}</body></html>`
}

/** `<` e `&` viram entidade: no modo texto puro nada do corpo pode virar marcação. */
function escapar(texto: string): string {
  return texto.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
