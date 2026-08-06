// Banco de provas do FRONT da F12 (spec-malha-execucao.md §9.5, Decisão 64):
// a DURAÇÃO TÍPICA por membro — o número que decide "posso esperar".
//
// Mesma técnica e mesmas razões do `f10_painel_harness.cjs`: o repo não tem
// runner de JS e acrescentar um traria dependência de REDE a um produto que faz
// deploy offline com wheels. O `sucrase` que o Vite já traz transpila os
// módulos PUROS e o Node executa o código do `src/`, byte a byte.
//
// O que esta bancada prova — e são os aceites LITERAIS da fase:
//
//   • membro com 23 execuções → `típico 18 min (n=23)`, os dois números no
//     MESMO texto (é assim que o `n` nunca aparece sozinho);
//   • membro com 3 execuções → o servidor não manda o item, e aqui não sobra
//     nada: só o decorrido, sem "típico" e sem `n`;
//   • membro rodando há 41 min com p50 de 18 → `⚠ 2x`, com o múltiplo
//     TRUNCADO (2,3× é `2x`, não `3x`);
//   • a ponte de CAIXA entre `execucoes[]` (grafia oficial) e `tipicos[]`
//     (grafia do snapshot) — o GOTCHA que já quebrou pipeline em produção,
//     aqui na forma silenciosa de um número que some da linha.
//
// Saída: um JSON só, no stdout. Cada cenário é embrulhado em try/catch e
// publica `{ erro }` em vez de derrubar o processo — um cenário que levanta tem
// de virar UM teste vermelho, não a suíte inteira.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const SRC = path.join(RAIZ, 'ui-react', 'src', 'components', 'malhas')
const { transform } = require(path.join(RAIZ, 'ui-react', 'node_modules', 'sucrase'))

const MODULOS = ['tempoCorrida.ts', 'duracaoTipica.ts']

function preparar(destino) {
  for (const arquivo of MODULOS) {
    const fonte = fs.readFileSync(path.join(SRC, arquivo), 'utf8')
    const js = transform(fonte, { transforms: ['typescript'], filePath: arquivo })
      .code
      .replace(/from\s*'\.\/([A-Za-z0-9_]+)'/g, "from './$1.mjs'")
    fs.writeFileSync(path.join(destino, arquivo.replace(/\.ts$/, '.mjs')), js)
  }
}

/** Um item de `tipicos.itens` — o formato que o servidor manda (segundos). */
const item = (pipeline, p50_seg, n) => ({ pipeline, p50_seg, n })

async function main() {
  const destino = fs.mkdtempSync(path.join(os.tmpdir(), 'f12tipicos-'))
  preparar(destino)
  const D = await import(path.join(destino, 'duracaoTipica.mjs'))
  const T = await import(path.join(destino, 'tempoCorrida.mjs'))

  const saida = {}
  const cenario = (nome, fn) => {
    try {
      saida[nome] = fn()
    } catch (e) {
      saida[nome] = { erro: String((e && e.stack) || e) }
    }
  }

  // O payload como ele chega: o piso `n ≥ 5` JÁ foi aplicado no servidor, então
  // `CARGA_E` (3 execuções) simplesmente não está na lista.
  const tipicos = {
    piso_n: 5, janela_dias: 90, limite_execucoes: 30,
    membros: 4, com_historico: 3, completo: false,
    itens: [
      item('CARGA_B', 1080, 23),   // 18 min
      item('CARGA_D', 1080, 23),
      item('CARGA_RAPIDA', 20, 7), // 20 s — "menos de 1 min", nunca "0 min"
    ],
  }

  // ══ o aceite literal: `há 12 min · típico 18 min (n=23)` ═════════════════
  cenario('linha_do_aceite', () => {
    const mapa = D.mapaTipicos(tipicos)
    const t = D.tipicoDe(mapa, 'CARGA_B')
    return {
      // A linha inteira, montada como o painel a monta.
      texto: `há ${T.textoDuracao(12)} · ${D.textoTipico(t)}`,
      tipico: D.textoTipico(t),
      // 12 min sobre 18 não é atípico: nada de âmbar.
      marca: D.marcaAtipica(12, t),
    }
  })

  // ══ o piso é DURO: sem amostra não sai número, e o `n` não sobra sozinho ══
  cenario('piso_duro', () => {
    const mapa = D.mapaTipicos(tipicos)
    return {
      // `CARGA_E` tem 3 execuções — o servidor não a manda, e aqui ela é
      // `undefined`. A linha some INTEIRA (não vira "típico —", não vira n=3).
      ausente: D.tipicoDe(mapa, 'CARGA_E') ?? null,
      texto_ausente: D.textoTipico(D.tipicoDe(mapa, 'CARGA_E')),
      texto_nulo: D.textoTipico(null),
      texto_indefinido: D.textoTipico(undefined),
      marca_sem_tipico: D.marcaAtipica(41, undefined),
      // Bloco inteiro ausente (API anterior à fase, erro de leitura): o mapa
      // nasce vazio e nada quebra.
      mapa_sem_bloco: D.mapaTipicos(null).size,
      mapa_indefinido: D.mapaTipicos(undefined).size,
      mapa_vazio: D.mapaTipicos({ itens: [] }).size,
    }
  })

  // ══ a marca âmbar `⚠ 2x` — e a fronteira exata dela ══════════════════════
  cenario('marca_atipica', () => {
    const t = D.tipicoDe(D.mapaTipicos(tipicos), 'CARGA_D')
    return {
      // O aceite: 41 min com p50 de 18 → 2,3×, truncado em `2x`.
      quarenta_e_um: D.marcaAtipica(41, t),
      // Fronteira: exatamente 2× acende; um minuto abaixo, não.
      exatamente_2x: D.marcaAtipica(36, t),
      quase_2x: D.marcaAtipica(35, t),
      tres_vezes: D.marcaAtipica(60, t),
      // Sem decorrido apurado não há comparação — e ausência não vira alerta.
      sem_decorrido: D.marcaAtipica(null, t),
      indefinido: D.marcaAtipica(undefined, t),
      // O `title` da marca, que precisa dizer o FATO sem prometer o futuro.
      titulo: D.tituloAtipico(t),
      fator: D.FATOR_ATIPICO,
    }
  })

  // ══ arredondamento: o típico em minutos, e o caso de menos de 1 min ══════
  cenario('arredondamento', () => {
    const mapa = D.mapaTipicos(tipicos)
    return {
      rapido: D.textoTipico(D.tipicoDe(mapa, 'CARGA_RAPIDA')),
      minutos_rapido: D.minutosTipicos(D.tipicoDe(mapa, 'CARGA_RAPIDA')),
      // 1016 s = 16,9 min → 17 min (arredonda, não trunca: o típico não é um
      // relógio correndo, é uma medida).
      dezessete: D.textoTipico(item('X', 1016, 30)),
      // 90 min vira o formato compacto do card.
      hora_e_meia: D.textoTipico(item('X', 5400, 9)),
      // Lixo no payload não vira "0 min" nem "NaN": some.
      zero: D.textoTipico(item('X', 0, 30)),
      negativo: D.textoTipico(item('X', -5, 30)),
      nulo: D.minutosTipicos(item('X', null, 30)),
    }
  })

  // ══ a ponte de CAIXA — o número não pode sumir por causa da grafia ═══════
  cenario('ponte_de_caixa', () => {
    // `tipicos[]` vem do SNAPSHOT (a grafia do dia da abertura) e
    // `execucoes[]` da grafia OFICIAL de `etl_pipeline`. As duas divergirem em
    // caixa é o GOTCHA que já quebrou pipeline em produção.
    const mapa = D.mapaTipicos({ itens: [item('Carga_B', 1080, 23)] })
    return {
      oficial: D.textoTipico(D.tipicoDe(mapa, 'CARGA_B')),
      minusculo: D.textoTipico(D.tipicoDe(mapa, 'carga_b')),
      com_espaco: D.textoTipico(D.tipicoDe(mapa, '  CARGA_B ')),
      outro: D.textoTipico(D.tipicoDe(mapa, 'CARGA_C')),
    }
  })

  process.stdout.write(JSON.stringify(saida))
  fs.rmSync(destino, { recursive: true, force: true })
}

main().catch(e => {
  process.stderr.write(String((e && e.stack) || e))
  process.exit(1)
})
