// Valores de exemplo da prévia do e-mail e a troca dos marcadores — as partes
// PURAS, exercitadas pela bancada tests/js/ds_params_harness.cjs.
//
// Os nomes e formatos espelham o que o operador do worker resolve em tempo de
// corrida (dags/utils/email_operator.py, `_mapa`): é isso que faz a prévia
// mostrar um e-mail parecido com o que chega, e não um rascunho genérico.

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
}

/** Mesma regra do backend: `{chave}` conhecida vira valor, desconhecida fica
 *  INTACTA — na prévia e no e-mail, um marcador errado aparece como está. */
export function interpolarExemplo(texto: string): string {
  return (texto ?? '').replace(/\{([a-z_]+)\}/g, (achado, chave: string) =>
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
  for (const [, chave] of (texto ?? '').matchAll(/\{([A-Za-z_]+)\}/g)) {
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
