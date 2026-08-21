// Markdown mínimo das respostas dos assistentes (Diego/Lari/Léo).
//
// O modelo responde em Markdown por conta própria — o system prompt nem pede.
// A bolha mostrava isso com `whitespace-pre-wrap`, então o operador lia
// `## Status Principais`, `**Emitida**` e tabelas em cano (`| a | b |`) como
// texto cru; o PDF exportava o mesmo texto cru.
//
// Este módulo faz UMA leitura do Markdown e devolve blocos tipados. Quem
// desenha são dois consumidores — a bolha (JSX, em MensagemMarkdown.tsx) e o
// PDF (jsPDF, em ChatAssistant.tsx). Um parser só, porque dois parsers voltam
// a divergir: a tela mostraria a tabela e o PDF continuaria com os canos.
//
// É deliberadamente PARCIAL. Cobre o que o modelo emite de fato — títulos,
// negrito/itálico/código, listas, tabelas, régua e blocos de código — e nada
// de HTML embutido, imagem ou link de referência. Nada aqui produz HTML: o
// texto vem de um LLM, e construir elementos React (em vez de
// dangerouslySetInnerHTML) é o que mantém a resposta como DADO, nunca markup.
//
// Limitações conhecidas, ditas para não parecerem descuido:
//   • **lista aninhada é achatada** — a indentação some antes do casamento, e
//     um recorte de dois níveis do modelo lê-se como um nível só. Nada se
//     perde do texto, só a hierarquia;
//   • uma frase com cano logo abaixo de uma tabela, SEM linha em branco entre
//     elas, é absorvida como linha da tabela. É o que o GFM também faz.

export type PedacoInline = {
  texto: string
  negrito?: boolean
  italico?: boolean
  codigo?: boolean
}

export type BlocoMd =
  | { tipo: 'titulo'; nivel: 1 | 2 | 3; partes: PedacoInline[] }
  | { tipo: 'paragrafo'; partes: PedacoInline[] }
  | { tipo: 'lista'; ordenada: boolean; itens: PedacoInline[][] }
  | { tipo: 'tabela'; cabecalho: PedacoInline[][]; linhas: PedacoInline[][][] }
  | { tipo: 'separador' }
  | { tipo: 'codigo'; texto: string }

// ── Inline ──────────────────────────────────────────────────────────────────
// `**negrito**`, `*itálico*`/`_itálico_` e `` `código` ``. Uma passada só, com
// alternativas na mesma expressão: rodar uma regex por marcação faria a de
// itálico morder o miolo do negrito (`**a**` tem `*a*` dentro).
//
// Três coisas que a expressão precisa acertar, e cada uma custou um teste:
//
//   • a ordem — `\*\*` ANTES de `\*`, senão o negrito nunca casa;
//
//   • o miolo do negrito aceita asterisco solto (`(?:[^*]|\*(?!\*))`), porque
//     `**a *b* c**` é comum na resposta do modelo. Com `[^*]+` ali, o negrito
//     inteiro deixava de casar e o operador via os asteriscos crus;
//
//   • ⚠️ **`_` no meio de palavra NÃO é ênfase.** Sem a borda exigida abaixo,
//     `NUM_CPF_CNPJ` era lido como `NUM` + itálico + `CNPJ` e chegava na tela
//     como **`NUMCPFCNPJ`** — com os underscores apagados. O mesmo com
//     `SEQSSDVIDA6SINISTRO_carga_diaria`. Estes assistentes falam de coluna,
//     job e pipeline o tempo todo, então esse era o caso COMUM, e corrompia a
//     bolha e o PDF juntos. A regra é a do GFM: `_` só abre/fecha ênfase
//     quando não está entre caracteres de palavra.
//
//     O `*` tem a borda mais frouxa (o GFM permite `a*b*c`), mas ganhou a
//     recusa de espaço logo depois da abertura: sem ela, `2 * 3 = 6 e 4 * 5`
//     virava itálico do miolo e perdia os dois asteriscos.
const NEGRITO = String.raw`\*\*(?:[^*]|\*(?!\*))+\*\*`
const NEGRITO_ = String.raw`(?<![A-Za-z0-9])__(?:[^_]|_(?!_))+__(?![A-Za-z0-9])`
const ITALICO = String.raw`\*(?![\s*])[^*\n]*[^\s*]\*|\*[^\s*]\*`
const ITALICO_ = String.raw`(?<![A-Za-z0-9])_(?![\s_])[^_\n]*[^\s_]_(?![A-Za-z0-9])`
const CODIGO = String.raw`\`[^\`\n]+\``
const INLINE = new RegExp(
  `(${NEGRITO}|${NEGRITO_}|${ITALICO}|${ITALICO_}|${CODIGO})`)

export function inline(texto: string): PedacoInline[] {
  const partes: PedacoInline[] = []
  for (const pedaco of texto.split(INLINE)) {
    if (!pedaco) continue
    if (pedaco.length > 4 && (pedaco.startsWith('**') || pedaco.startsWith('__'))
        && (pedaco.endsWith('**') || pedaco.endsWith('__'))) {
      // O miolo volta para cá: `**a *b* c**` tem itálico DENTRO do negrito, e
      // marcar o pedaço inteiro de uma vez perderia o de dentro (ou deixaria
      // os asteriscos aparecendo). A recursão termina sempre — o miolo é
      // estritamente menor que o pedaço.
      for (const parte of inline(pedaco.slice(2, -2))) {
        partes.push({ ...parte, negrito: true })
      }
    } else if (pedaco.length > 2 && pedaco.startsWith('`') && pedaco.endsWith('`')) {
      partes.push({ texto: pedaco.slice(1, -1), codigo: true })
    } else if (pedaco.length > 2
               && (pedaco.startsWith('*') || pedaco.startsWith('_'))
               && (pedaco.endsWith('*') || pedaco.endsWith('_'))) {
      partes.push({ texto: pedaco.slice(1, -1), italico: true })
    } else {
      partes.push({ texto: pedaco })
    }
  }
  // Texto vazio ainda precisa de um pedaço: quem desenha conta os pedaços para
  // saber se há linha, e uma lista vazia sumiria com a linha em branco.
  return partes.length ? partes : [{ texto: '' }]
}

/** O texto puro de uma sequência inline — o que o PDF mede e desenha. */
export function textoDe(partes: PedacoInline[]): string {
  return partes.map(p => p.texto).join('')
}

// ── Tabela ──────────────────────────────────────────────────────────────────
// O separador (`|---|:--:|`) é o que confirma que a linha anterior era
// cabeçalho: sem ele, um texto com cano viraria tabela de uma coluna só.
//
// ⚠️ Não basta o separador PARECER um: ele precisa ter o MESMO número de
// células que o cabeçalho — é a regra do GFM, e é ela que impede o caso
// `"Total | 10"` seguido de `"---"` (uma régua!) de virar tabela. Sem a
// contagem, a régua era engolida e a frase virava um cabeçalho de duas
// colunas.
const SEPARADOR_TABELA = /^\|?[\s:|-]*-[\s:|-]*\|?$/

function ehLinhaTabela(linha: string): boolean {
  return linha.includes('|') && linha.trim().length > 1
}

function ehSeparadorDe(linha: string, colunas: number): boolean {
  const t = linha.trim()
  return SEPARADOR_TABELA.test(t) && t.includes('-')
    && celulas(t).length === colunas
}

function celulas(linha: string): string[] {
  let t = linha.trim()
  if (t.startsWith('|')) t = t.slice(1)
  if (t.endsWith('|')) t = t.slice(0, -1)
  return t.split('|').map(c => c.trim())
}

// ── Blocos ──────────────────────────────────────────────────────────────────
const TITULO = /^(#{1,6})\s+(.*)$/
// Régua: três ou mais do mesmo sinal, sozinhos na linha. `\s*` no fim casaria
// a quebra de linha e comeria a linha seguinte — aqui a string já vem sem ela.
const REGUA = /^(-{3,}|_{3,}|\*{3,})$/
const ITEM_LISTA = /^[-*+]\s+(.*)$/
const ITEM_NUMERADO = /^\d+[.)]\s+(.*)$/

export function parseMarkdown(fonte: string): BlocoMd[] {
  const linhas = (fonte ?? '').replace(/\r\n?/g, '\n').split('\n')
  const blocos: BlocoMd[] = []
  let paragrafo: string[] = []

  const fecharParagrafo = () => {
    if (!paragrafo.length) return
    blocos.push({ tipo: 'paragrafo', partes: inline(paragrafo.join(' ')) })
    paragrafo = []
  }

  for (let i = 0; i < linhas.length; i++) {
    const bruta = linhas[i]
    const linha = bruta.trim()

    // Bloco de código: tudo lá dentro é literal, inclusive o que pareceria
    // título ou tabela.
    if (linha.startsWith('```')) {
      fecharParagrafo()
      const corpo: string[] = []
      i++
      while (i < linhas.length && !linhas[i].trim().startsWith('```')) {
        corpo.push(linhas[i]); i++
      }
      blocos.push({ tipo: 'codigo', texto: corpo.join('\n') })
      continue
    }

    if (!linha) { fecharParagrafo(); continue }

    if (REGUA.test(linha)) {
      fecharParagrafo()
      blocos.push({ tipo: 'separador' })
      continue
    }

    const titulo = TITULO.exec(linha)
    if (titulo) {
      fecharParagrafo()
      // Acima de h3 tudo vira h3: numa bolha de 384px, seis tamanhos de
      // título não se distinguem — e o modelo desce até `####` sem critério.
      const nivel = Math.min(titulo[1].length, 3) as 1 | 2 | 3
      blocos.push({ tipo: 'titulo', nivel, partes: inline(titulo[2].trim()) })
      continue
    }

    // Tabela: precisa da linha separadora logo abaixo, com o MESMO número de
    // células do cabeçalho (ver `ehSeparadorDe`).
    if (ehLinhaTabela(linha) && i + 1 < linhas.length
        && ehSeparadorDe(linhas[i + 1], celulas(linha).length)) {
      fecharParagrafo()
      const cabecalho = celulas(linha).map(inline)
      const cru: string[][] = []
      i += 2
      while (i < linhas.length && ehLinhaTabela(linhas[i].trim())) {
        cru.push(celulas(linhas[i]))
        i++
      }
      // O modelo erra a contagem de células nos DOIS sentidos, e as duas
      // formas de errar apagariam dado sem ninguém notar: linha curta some da
      // tabela, linha longa perde a última célula. Então a tabela cresce até
      // caber a maior linha, e as curtas são completadas com vazio.
      const colunas = Math.max(cabecalho.length, ...cru.map(l => l.length), 1)
      while (cabecalho.length < colunas) cabecalho.push(inline(''))
      const corpo: PedacoInline[][][] = []
      for (const cols of cru) {
        while (cols.length < colunas) cols.push('')
        corpo.push(cols.map(inline))
      }
      i-- // o laço de fora avança; o `while` acima já parou na linha seguinte
      blocos.push({ tipo: 'tabela', cabecalho, linhas: corpo })
      continue
    }

    const item = ITEM_LISTA.exec(linha)
    const numerado = ITEM_NUMERADO.exec(linha)
    if (item || numerado) {
      fecharParagrafo()
      const ordenada = !item
      const anterior = blocos[blocos.length - 1]
      const conteudo = inline((item ? item[1] : numerado![1]).trim())
      if (anterior && anterior.tipo === 'lista' && anterior.ordenada === ordenada) {
        anterior.itens.push(conteudo)
      } else {
        blocos.push({ tipo: 'lista', ordenada, itens: [conteudo] })
      }
      continue
    }

    paragrafo.push(linha)
  }
  fecharParagrafo()
  return blocos
}

// ── Texto para o PDF ────────────────────────────────────────────────────────
// jsPDF com as fontes padrão escreve em WinAnsi. Emoji é fora dela, e cada um
// virava lixo no PDF exportado — foi assim que "📋" saiu como "Ø=ÜË" e "✅"
// como "'L". Embutir uma fonte com emoji custaria megabytes no bundle para
// desenhar decoração, então o emoji SAI do PDF (a tela continua mostrando).
//
// Alguns símbolos comuns viram equivalente ASCII antes do corte, porque estes
// carregam significado: uma seta perdida muda a frase.
const TROCAS: Array<[RegExp, string]> = [
  [/[→⇒➡]/g, '->'],
  [/[←⇐⬅]/g, '<-'],
  [/[✓✔✅]/g, '[ok]'],
  [/[✗✘❌]/g, '[x]'],
  [/[↳▸►➤]/g, '>'],
  [/…/g, '...'],
  // Espaços "especiais" que o modelo intercala (NBSP e os finos). Escritos por
  // código de propósito: como literais eles são invisíveis no diff — e o
  // eslint recusa (no-irregular-whitespace), com razão.
  [/[\u00A0\u2007\u2009\u202F]/g, ' '],
]

// O que a WinAnsi tem além do latin-1 (posições 0x80–0x9F). Sem esta lista, um
// corte "acima de U+00FF" levaria junto o travessão e as aspas curvas — que
// HOJE saem certos no PDF e são o que o modelo mais usa.
const WINANSI_EXTRA = '€‚ƒ„†‡ˆ‰Š'
  + '‹ŒŽ‘’“”•–—˜'
  + '™š›œžŸ'

/** Texto seguro para as fontes padrão do jsPDF — sem emoji, sem lixo.
 *
 * `preservarEspacos` desliga a faxina de espaços. Bloco de código PRECISA
 * dela desligada: a normalização existe só para fechar o buraco que o emoji
 * removido deixa, e num `def f():\n    return 1` ela comia a indentação —
 * o código saía do PDF desalinhado, que para código é sair errado.
 */
export function textoParaPdf(texto: string, preservarEspacos = false): string {
  let saida = texto ?? ''
  for (const [de, para] of TROCAS) saida = saida.replace(de, para)
  // O que sobrou fora da WinAnsi sai. Some o caractere, não a frase — e some
  // de VERDADE, em vez de virar dois bytes ilegíveis no meio da palavra.
  let limpo = ''
  for (const ch of saida) {
    if (ch <= 'ÿ' || WINANSI_EXTRA.includes(ch)) limpo += ch
  }
  if (preservarEspacos) return limpo
  // Emoji removido costuma deixar espaço duplo e espaço antes de pontuação.
  return limpo.replace(/[^\S\n]{2,}/g, ' ').replace(/[^\S\n]+([,.;:!?])/g, '$1').trim()
}
