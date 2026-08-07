// Banco de provas do FRONT da F10 (spec-malha-execucao.md §9.5/§9.6/§9.9).
//
// Mesma técnica e mesmas razões do `f4_front_harness.cjs`: o repo não tem
// runner de JS (`ui-react/package.json` tem `dev`, `build` e `lint`, e mais
// nada) e acrescentar um significaria acrescentar dependência de REDE a um
// produto que faz deploy offline com wheels. O `sucrase` que o Vite já traz
// transpila os módulos PUROS e o Node executa o código do `src/`, byte a byte.
//
// O que esta bancada prova, e por que nenhuma delas cabe no pytest sozinho:
//
//   • **Decisão 62** — a aba com que o painel abre é derivada da SAÚDE. É uma
//     função pura, e a alternativa (afirmar sobre o JSX do editor) provaria
//     que a chamada existe, não que ela responde certo;
//   • **Decisão 63** — o raio de alcance vira texto, e "não apurei" (`null`)
//     tem de sumir da tela em vez de virar "0 parados atrás". A distinção
//     entre ausência e zero é justamente o defeito que a fase evita;
//   • **Decisão 66/3** — o banner de aviso preso mede a carência entre DOIS
//     carimbos do BANCO. Com o desvio de 3 h medido no dev, a implementação
//     ingênua (`Date.now() − criado_em`) nunca acenderia o banner — e é
//     exatamente esse contraste que a bancada publica;
//   • **Decisão 61** — o próximo gatilho deixa de ser só um texto e passa a
//     ter INSTANTE, que é o que permite escrever "parte em 2h50 (01:00)".
//
// Saída: um JSON só, no stdout. Cada cenário é embrulhado em try/catch e
// publica `{ erro }` em vez de derrubar o processo — um cenário que levanta
// tem de virar UM teste vermelho, não a suíte inteira.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const SRC = path.join(RAIZ, 'ui-react', 'src', 'components', 'malhas')
const { transform } = require(path.join(RAIZ, 'ui-react', 'node_modules', 'sucrase'))

// `historicoCorridas.ts` entra porque `statusExecucao` passou a importá-lo
// na F12 (o histórico factual mora num módulo puro próprio) — sem ele o Node
// não resolve o import e a bancada inteira morre no arranque.
const MODULOS = ['tempoCorrida.ts', 'historicoCorridas.ts',
                 'statusExecucao.ts', 'proximaExecucao.ts']

function preparar(destino) {
  const icones = new Set()
  for (const arquivo of MODULOS) {
    const fonte = fs.readFileSync(path.join(SRC, arquivo), 'utf8')
    let js = transform(fonte, {
      transforms: ['typescript'],
      filePath: arquivo,
    }).code
    const usados = /import\s*\{([^}]+)\}\s*from\s*['"]lucide-react['"]/.exec(js)
    if (usados) {
      for (const nome of usados[1].split(',')) {
        const limpo = nome.trim()
        if (limpo) icones.add(limpo)
      }
    }
    js = js
      .replace(/from\s*['"]lucide-react['"]/g, "from './lucide.mjs'")
      .replace(/from\s*'\.\/([A-Za-z0-9_]+)'/g, "from './$1.mjs'")
    fs.writeFileSync(path.join(destino, arquivo.replace(/\.ts$/, '.mjs')), js)
  }
  const stub = [...icones].map(n => `export const ${n} = 'icone:${n}'`).join('\n')
  fs.writeFileSync(path.join(destino, 'lucide.mjs'), stub + '\n')
}

// Os dois relógios, com o desvio MEDIDO no dev: o navegador marca 10:59, o
// SQL Server responde 13:59.
const LOCAL = Date.parse('2026-08-05T10:59:00Z')
const APURADO_BANCO = '2026-08-05 13:59:20'

function corrida(over) {
  return Object.assign({
    id: 1, malha_name: 'M1', data_referencia: '2026-08-05', sequencia: 1,
    status: 'ABERTA', aberta_em: '2026-08-05 01:10:00', fechada_em: null,
    fechada_por: null, origem: 'inicio', aberta_por: 'inicio:#1',
    ancora_pipeline: null, modo_fechamento: null, teto_em: null,
    tentativas: 1, reaberta_em: null, reaberta_por: null, motivo: null,
    saude: 'OK', decorrido_min: 42, apurado_em: APURADO_BANCO,
    membros_total: 7, membros_ok: 2, membros_vivos: 2, membros_dispensados: 0,
    membros_travados: 0, membros_fora_do_odate: 0, membros_inativos: 0,
    pendentes: [], ultimo_movimento_em: '2026-08-05 13:56:00',
    sem_sinal_min: 3,
  }, over)
}

async function main() {
  const destino = fs.mkdtempSync(path.join(os.tmpdir(), 'f10painel-'))
  preparar(destino)
  const S = await import(path.join(destino, 'statusExecucao.mjs'))
  const P = await import(path.join(destino, 'proximaExecucao.mjs'))

  const saida = {}
  const cenario = (nome, fn) => {
    try {
      saida[nome] = fn()
    } catch (e) {
      saida[nome] = { erro: String((e && e.stack) || e) }
    }
  }

  // ══ Decisão 62 — a aba inicial é derivada da SAÚDE ═══════════════════════
  cenario('aba_inicial_por_saude', () => {
    const out = {}
    for (const saude of ['OK', 'COM_FALHA', 'ATRASADA', 'SEM_PROGRESSO', null]) {
      out[`ABERTA:${saude}`] = S.abaInicialDaCorrida(corrida({ saude }))
    }
    for (const status of ['CONCLUIDA', 'FALHA', 'EXPIRADA', 'CANCELADA',
                          'SEM_TRABALHO', 'ABORTADA']) {
      // Corrida FECHADA: a saúde nem existe (§6.1), e mesmo que viesse suja do
      // banco ela não pode mandar numa corrida que já acabou.
      out[status] = S.abaInicialDaCorrida(
        corrida({ status, saude: 'COM_FALHA' }))
    }
    out['sem_corrida'] = S.abaInicialDaCorrida(null)
    out['indefinida'] = S.abaInicialDaCorrida(undefined)
    return out
  })

  // ══ Decisão 63 — o RAIO DE ALCANCE em texto ══════════════════════════════
  cenario('raio_de_alcance', () => ({
    // `null` = "não apurei" (grafo indisponível). A frase some INTEIRA: dizer
    // "0 parados atrás" seria publicar ausência de medida como medida.
    nao_apurado: S.textoAlcance({ pipeline: 'A', classe: 'falhou', desde: null,
                                  faltante: null, alcance: null }),
    ausente: S.textoAlcance({ pipeline: 'A', classe: 'falhou', desde: null,
                              faltante: null }),
    zero: S.textoAlcance({ pipeline: 'A', classe: 'falhou', desde: null,
                           faltante: null, alcance: 0, alcance_alta: 0 }),
    um: S.textoAlcance({ pipeline: 'A', classe: 'falhou', desde: null,
                         faltante: null, alcance: 1, alcance_alta: 0 }),
    muitos: S.textoAlcance({ pipeline: 'A', classe: 'falhou', desde: null,
                             faltante: null, alcance: 18, alcance_alta: 0 }),
    // O segundo número é o que muda a resposta: 18 atrás sem nenhum crítico
    // espera o horário comercial; 2 com um `ALTA` no meio, não.
    com_alta: S.textoAlcance({ pipeline: 'A', classe: 'falhou', desde: null,
                               faltante: null, alcance: 2, alcance_alta: 1 }),
  }))

  // ══ Decisão 66/3 — o aviso preso na fila do Teams ════════════════════════
  const ev = (tipo, criado_em, notificado_em) => (
    notificado_em === undefined
      ? { tipo, criado_em, mensagem: null }
      : { tipo, criado_em, mensagem: null, notificado_em })

  cenario('aviso_preso_na_fila', () => ({
    carencia_min: S.CARENCIA_FILA_AVISO_MIN,
    // A guardiã drena a fila o cada ciclo de 5 min: um evento de 3 min atrás
    // NÃO é banner — seria o alarme falso que a Decisão 26 proíbe.
    recente: S.avisoPresoNaFila(
      [ev('MALHA_FALHOU', '2026-08-05 13:56:00', null)], APURADO_BANCO),
    // 52 min na fila: ninguém foi avisado, e o plantão não sabe desta malha.
    preso: S.avisoPresoNaFila(
      [ev('MALHA_FALHOU', '2026-08-05 13:07:00', null)], APURADO_BANCO),
    // Já avisado: nada a dizer.
    avisado: S.avisoPresoNaFila(
      [ev('MALHA_FALHOU', '2026-08-05 13:07:00', '2026-08-05 13:08:00')],
      APURADO_BANCO),
    // Chave AUSENTE = o banco não tem a coluna. "Não perguntei" nunca vira
    // acusação: senão TODA malha de um banco antigo acenderia vermelho.
    coluna_ausente: S.avisoPresoNaFila(
      [ev('MALHA_FALHOU', '2026-08-05 13:07:00')], APURADO_BANCO),
    // Sucesso é opt-in e "sem trabalho" nem vira card (Decisão 48): nenhum dos
    // dois pendurado na fila é notícia.
    conclusao_na_fila: S.avisoPresoNaFila(
      [ev('MALHA_CONCLUIDA', '2026-08-05 13:07:00', null),
       ev('MALHA_SEM_TRABALHO', '2026-08-05 13:07:00', null)], APURADO_BANCO),
    // Vários: o banner conta todos e diz DESDE QUANDO pelo mais antigo.
    varios: S.avisoPresoNaFila(
      [ev('MALHA_ATRASADA', '2026-08-05 13:20:00', null),
       ev('MALHA_FALHOU', '2026-08-05 13:07:00', null),
       ev('MALHA_CONCLUIDA', '2026-08-05 12:00:00', null)], APURADO_BANCO),
    // Sem `apurado_em` não há relógio do banco para comparar: sem certeza,
    // sem banner.
    sem_apurado: S.avisoPresoNaFila(
      [ev('MALHA_FALHOU', '2026-08-05 13:07:00', null)], null),
    // ⚠️ O contraste que prova a armadilha: a conta INGÊNUA (relógio local
    // contra carimbo do banco) dá NEGATIVO com o desvio de 3 h — o evento
    // pareceria do futuro e o banner nunca acenderia.
    ingenuo_min: Math.round(
      (LOCAL - Date.parse('2026-08-05T13:07:00Z')) / 60_000),
  }))

  // ══ Decisão 61 — o próximo gatilho tem INSTANTE, não só texto ════════════
  cenario('proximo_gatilho', () => {
    const agora = new Date(2026, 7, 5, 22, 10)      // 05/08 22:10, hora local
    const diario = P.proximaExecucao(
      { schedule_type: 'daily', schedule_hour: 1, schedule_minute: 0 }, agora)
    return {
      texto: diario.texto,
      // 2h50 até 01:00 do dia seguinte — a conta que a faixa escreve.
      falta_min: Math.round((diario.quando.getTime() - agora.getTime()) / 60_000),
      hora: diario.hora,
      // Cadência sem instante: o texto continua honesto e o instante é `null`
      // em vez de um horário inventado.
      hourly: P.proximaExecucao({ schedule_type: 'hourly', schedule_minute: 30 },
                                agora),
      // Sob demanda não tem próxima partida — e a linha da faixa some.
      sob_demanda: P.proximaExecucao({ schedule_type: 'on_demand' }, agora),
      sem_agendamento: P.proximaExecucao(null, agora),
      // O texto de sempre (F15) não mudou de forma.
      texto_legado: P.proximaExecucaoTexto(
        { schedule_type: 'daily', schedule_hour: 1, schedule_minute: 0 }, agora),
    }
  })

  // ══ §9.9 — as classes que entram na aba `Travando` (Decisão 54) ══════════
  cenario('classes_travadas', () => ({
    falhou: S.CLASSES_TRAVADAS.has('falhou'),
    orfa: S.CLASSES_TRAVADAS.has('orfa'),
    nao_liberou: S.CLASSES_TRAVADAS.has('nao_liberou'),
    // `nao_partiu` FICA DE FORA: às 01:10 ele é o estado normal de todo membro
    // de toda corrida recém-aberta.
    nao_partiu: S.CLASSES_TRAVADAS.has('nao_partiu'),
    rotulos: S.ROTULO_PENDENCIA,
  }))

  process.stdout.write(JSON.stringify(saida))
  fs.rmSync(destino, { recursive: true, force: true })
}

main().catch(e => {
  process.stderr.write(String((e && e.stack) || e))
  process.exit(1)
})
