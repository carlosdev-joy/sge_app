// Banco de provas do FRONT da F12 — o HISTÓRICO FACTUAL (Decisão 68), a
// AUDITORIA na tela (Decisão 67) e o PERCENTUAL DE TEMPO (Decisão 56b).
//
// Mesma técnica e mesmas razões do `f9_card_harness.cjs`: o repo não tem runner
// de JS e acrescentar um traria dependência de REDE a um produto que faz deploy
// offline com wheels. O `sucrase` que o Vite já traz transpila os módulos do
// `src/` e o Node executa o código byte a byte como ele está lá.
//
// Por que RENDERIZAR e não só chamar as funções puras: metade dos aceites desta
// fase é afirmação de AUSÊNCIA — "com zero corridas fechadas, NENHUMA frase
// desta fase é renderizada". Ausência se prova sobre a árvore inteira, incluindo
// `title` e `aria-*`, que é justamente por onde um texto escapa sem ninguém ver.
//
// O que esta bancada prova:
//
//   • **dia 1** (`historico` ausente): nem "falhou", nem "corrida anterior",
//     nem "%" — e nada quebra. `n = 0` é ausência, nunca "0%";
//   • `falhou 2 das últimas 7 corridas`, com o denominador vindo do SERVIDOR;
//   • `SEM_TRABALHO` numa TERÇA atípica → ÂMBAR + a frase; no SÁBADO, a MESMA
//     malha continua cinza e MUDA (o alarme de sábado que a Decisão 26 proíbe);
//   • auditoria (Decisão 67) no card, na faixa e no `title` do bloco da faixa:
//     quem encerrou, com que motivo, por qual porta e quem reabriu;
//   • Decisão 44: `origem = 'implicita'` → o card diz `sem nó Início`;
//   • Decisão 56b, regra a regra: `≈`, o sufixo "do tempo típico", o piso de
//     `n ≥ 5` em TODOS os membros, o `Math.floor` com teto em 99, a ausência
//     total em corrida terminal, o `≈ 140%` da ATRASADA — e o fato de o `x de
//     y` continuar sendo o PRIMEIRO número da linha.
//
// Saída: um JSON só, no stdout. Cada cenário é embrulhado em try/catch e
// publica `__erro__` em vez de derrubar o processo — um cenário que levanta tem
// de virar UM teste vermelho, não a suíte inteira.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const SRC = path.join(RAIZ, 'ui-react', 'src')
const { transform } = require(path.join(RAIZ, 'ui-react', 'node_modules', 'sucrase'))

const MODULOS = [
  ['components/malhas/tempoCorrida.ts', 'tempoCorrida'],
  ['components/malhas/historicoCorridas.ts', 'historicoCorridas'],
  ['components/malhas/duracaoTipica.ts', 'duracaoTipica'],
  ['components/malhas/statusExecucao.ts', 'statusExecucao'],
  ['components/malhas/CorridaBadge.tsx', 'CorridaBadge'],
  ['components/malhas/CorridaProgresso.tsx', 'CorridaProgresso'],
  ['components/ui/Progress.tsx', 'Progress'],
]

function preparar(destino) {
  const icones = new Set()
  for (const [relativo, nome] of MODULOS) {
    const fonte = fs.readFileSync(path.join(SRC, relativo), 'utf8')
    let js = transform(fonte, {
      transforms: ['typescript', 'jsx'],
      jsxRuntime: 'classic',
      jsxPragma: '__h',
      jsxFragmentPragma: '__Frag',
      production: true,
      filePath: relativo,
    }).code
    const usados = /import\s*\{([^}]+)\}\s*from\s*['"]lucide-react['"]/.exec(js)
    if (usados) {
      for (const bruto of usados[1].split(',')) {
        const limpo = bruto.trim()
        if (limpo) icones.add(limpo)
      }
    }
    js = js
      .replace(/from\s*['"]lucide-react['"]/g, "from './lucide.mjs'")
      .replace(/from\s*'\.\.\/ui\/([A-Za-z0-9_]+)'/g, "from './$1.mjs'")
      .replace(/from\s*'\.\/([A-Za-z0-9_]+)'/g, "from './$1.mjs'")
    const preambulo = relativo.endsWith('.tsx')
      ? "import { __h, __Frag } from './jsx.mjs'\n" : ''
    fs.writeFileSync(path.join(destino, nome + '.mjs'), preambulo + js)
  }
  const stub = [...icones].map(n => `export const ${n} = 'icone:${n}'`).join('\n')
  fs.writeFileSync(path.join(destino, 'lucide.mjs'), stub + '\n')
  fs.writeFileSync(path.join(destino, 'jsx.mjs'), `
export const __Frag = 'fragmento'
export function __h(tipo, props, ...filhos) {
  return {
    tipo: typeof tipo === 'function' ? (tipo.name || 'anonimo') : tipo,
    props: props || {},
    filhos: filhos.flat(Infinity).filter(f => f !== null && f !== undefined
                                              && f !== false),
  }
}
`)
}

// ── utilidades de árvore (as mesmas do `f9_card_harness`) ───────────────────
function todosOsNos(no, saida = []) {
  if (!no || typeof no !== 'object') return saida
  saida.push(no)
  for (const f of no.filhos || []) todosOsNos(f, saida)
  return saida
}

function textoDe(no, partes = []) {
  if (no === null || no === undefined || typeof no === 'boolean') return partes
  if (typeof no !== 'object') { partes.push(String(no)); return partes }
  for (const f of no.filhos || []) textoDe(f, partes)
  return partes
}

/** Texto + TUDO que é lido por quem não enxerga a tela. É sobre este conjunto
 *  que se prova AUSÊNCIA — `title` e `aria-valuetext` inclusive. */
function tudoQueSeLe(raiz) {
  const partes = textoDe(raiz)
  for (const no of todosOsNos(raiz)) {
    for (const [k, v] of Object.entries(no.props || {})) {
      if (typeof v !== 'string') continue
      if (k === 'title' || k.startsWith('aria-')) partes.push(v)
    }
  }
  return partes.join(' | ')
}

function classes(raiz) {
  return todosOsNos(raiz)
    .map(n => (typeof n.props.className === 'string' ? n.props.className : ''))
    .join(' ')
}

// ── os dois relógios, com o desvio MEDIDO no dev (banco 3h à frente) ────────
const LOCAL = Date.parse('2026-08-05T10:59:00Z')
const APURADO_BANCO = '2026-08-05 13:59:20'
const TEMPO = { respostaEm: LOCAL, agora: LOCAL }

function corrida(over) {
  return Object.assign({
    id: 10, malha_name: 'M1', data_referencia: '2026-08-05', sequencia: 1,
    status: 'ABERTA', aberta_em: '2026-08-05 01:10:00', fechada_em: null,
    fechada_por: null, origem: 'inicio', aberta_por: 'inicio:#1',
    ancora_pipeline: null, modo_fechamento: 'quiescencia', teto_em: null,
    tentativas: 1, reaberta_em: null, reaberta_por: null, motivo: null,
    saude: 'OK', decorrido_min: 42, apurado_em: APURADO_BANCO,
    membros_total: 7, membros_ok: 4, membros_vivos: 2, membros_dispensados: 1,
    membros_travados: 0, membros_fora_do_odate: 0, membros_inativos: 0,
    pendentes: [], ultimo_movimento_em: '2026-08-05 13:56:00',
    sem_sinal_min: 3, quiescencia_min: 15, quiescencia_ate: null,
  }, over)
}

/** O bloco `historico` como o servidor o entrega. */
function historico(over) {
  return Object.assign({
    janela: 7, consideradas: 7, falhou: 2,
    anterior: {
      id: 9, data_referencia: '2026-08-04', sequencia: 1, status: 'CONCLUIDA',
      aberta_em: '2026-08-04 01:10:00', fechada_em: '2026-08-04 04:02:00',
    },
  }, over)
}

/** Um item de `tipicos.itens` — segundos, como o servidor manda. */
const item = (pipeline, p50_seg, n) => ({ pipeline, p50_seg, n })

/** `tipicos` com `completo` derivado do próprio conteúdo, para nenhum cenário
 *  poder mentir que tem histórico completo sem ter. */
function tipicos(itens, membros) {
  const total = membros === undefined ? itens.length : membros
  return {
    piso_n: 5, janela_dias: 90, limite_execucoes: 30,
    membros: total, com_historico: itens.length,
    completo: itens.length === total, itens,
  }
}

const exec = (pipeline_name, status, inicio) => ({ pipeline_name, status, inicio })

async function main() {
  const destino = fs.mkdtempSync(path.join(os.tmpdir(), 'f12hist-'))
  preparar(destino)
  const S = await import(path.join(destino, 'statusExecucao.mjs'))
  const H = await import(path.join(destino, 'historicoCorridas.mjs'))
  const D = await import(path.join(destino, 'duracaoTipica.mjs'))
  const Badge = await import(path.join(destino, 'CorridaBadge.mjs'))
  const Prog = await import(path.join(destino, 'CorridaProgresso.mjs'))

  const saida = {}
  const cenario = (nome, fn) => {
    try { saida[nome] = fn() } catch (e) {
      saida[nome] = { __erro__: String((e && e.stack) || e) }
    }
  }

  // ══ ACEITE — DIA 1: histórico ZERO, e NADA desta fase na tela ════════════
  cenario('dia_1_sem_historico', () => {
    const c = corrida()
    // `undefined` é como a chave chega quando o servidor não a manda.
    const r = S.resumoCorrida(c, TEMPO, 7, undefined)
    const raizCard = Prog.CorridaProgresso({ resumo: r, variante: 'card' })
    const raizBadge = Badge.CorridaBadge({ corrida: c, diaAtipico: !!r.diaAtipico })
    return {
      historico_falhas: r.historicoFalhas,
      anterior: r.anterior,
      dia_atipico: r.diaAtipico,
      // O percentual também some: sem `tipicos` não há o que ponderar.
      percentual: D.percentualTempoTipico({
        tipicos: undefined, execucoes: [], status: c.status, saude: c.saude,
        apuradoEm: c.apurado_em, respostaEm: LOCAL, agoraLocal: LOCAL,
      }),
      lido_card: tudoQueSeLe(raizCard),
      lido_badge: tudoQueSeLe(raizBadge),
      titulo: r.titulo,
      // A prova de que a ausência não é "quebrou": o card continua contando.
      contagem: r.contagem,
    }
  })

  // ══ ACEITE — `falhou 2 das últimas 7 corridas` ═══════════════════════════
  cenario('falhou_2_de_7', () => {
    const r = S.resumoCorrida(corrida(), TEMPO, 7, historico())
    return { frase: r.historicoFalhas, anterior: r.anterior, titulo: r.titulo }
  })

  cenario('sem_falha_nenhuma_cala', () => {
    // 7 corridas, zero falhas: NENHUMA linha. Em 40 cards, uma frase dizendo
    // que está tudo como sempre esteve é ruído — o histórico só fala quando
    // tem notícia.
    const r = S.resumoCorrida(corrida(), TEMPO, 7, historico({ falhou: 0 }))
    return { frase: r.historicoFalhas, anterior: r.anterior }
  })

  cenario('malha_nova_denominador_do_servidor', () => {
    // Malha de 3 semanas: 4 corridas existiram, e é `4` que a frase diz —
    // nunca "das últimas 7", que inventaria três madrugadas.
    const r = S.resumoCorrida(corrida(), TEMPO, 7,
                              historico({ consideradas: 4, falhou: 1 }))
    return { frase: r.historicoFalhas }
  })

  cenario('uma_corrida_so_no_singular', () => {
    const r = S.resumoCorrida(corrida(), TEMPO, 7,
                              historico({ consideradas: 1, falhou: 1 }))
    return { frase: r.historicoFalhas }
  })

  // ══ ACEITE — SEM_TRABALHO: terça ÂMBAR × sábado CINZA e MUDO ════════════
  const semTrabalho = (dia) => corrida({
    status: 'SEM_TRABALHO', saude: null, data_referencia: dia,
    membros_ok: 0, membros_vivos: 0, membros_dispensados: 7,
    // Os dois carimbos do MESMO dia: `aberta_em` do default é 05/08, e
    // deixá-lo produziria um intervalo de 72h no tooltip do sábado — o dublê
    // mentindo sobre o cenário, não o módulo.
    aberta_em: `${dia} 01:10:00`,
    fechada_em: `${dia} 01:15:00`, fechada_por: 'guardia',
    motivo: 'nenhum membro roda hoje (regra de dia)',
  })

  cenario('terca_atipica_vira_ambar', () => {
    // 2026-08-04 é uma TERÇA. As últimas 4 terças tiveram trabalho.
    const c = semTrabalho('2026-08-04')
    const h = historico({
      dia_semana: { exigidas: 4, encontradas: 4, com_trabalho: 4,
                    atipico: true },
    })
    const r = S.resumoCorrida(c, TEMPO, 7, h)
    const raizBadge = Badge.CorridaBadge({ corrida: c, diaAtipico: !!r.diaAtipico })
    const raizProg = Prog.CorridaProgresso({ resumo: r, variante: 'card' })
    return {
      frase: r.diaAtipico,
      faixa: r.faixa,
      chip: r.estilo.chip,
      dot: r.estilo.dot,
      rotulo: r.estilo.rotulo,
      classes_badge: classes(raizBadge),
      lido_badge: tudoQueSeLe(raizBadge),
      // A barra continua NÃO existindo (Decisão 57): âmbar não ressuscita
      // uma barra que não tem o que preencher.
      barra: todosOsNos(raizProg).some(n => n.tipo === 'Progress'),
      nada_previsto: r.nadaPrevisto,
      titulo: r.titulo,
    }
  })

  cenario('sabado_legitimo_fica_cinza_e_mudo', () => {
    // 2026-08-08 é um SÁBADO, e as últimas 4 também não tiveram trabalho.
    const c = semTrabalho('2026-08-08')
    const h = historico({
      dia_semana: { exigidas: 4, encontradas: 4, com_trabalho: 0,
                    atipico: false },
    })
    const r = S.resumoCorrida(c, TEMPO, 7, h)
    const raizBadge = Badge.CorridaBadge({ corrida: c, diaAtipico: !!r.diaAtipico })
    return {
      frase: r.diaAtipico,
      faixa: r.faixa,
      chip: r.estilo.chip,
      classes_badge: classes(raizBadge),
      lido_badge: tudoQueSeLe(raizBadge),
      titulo: r.titulo,
    }
  })

  cenario('tres_tercas_nao_bastam', () => {
    // O servidor exige QUATRO ocorrências: com três, `atipico` é `false` e a
    // tela não afirma nada. Uma frase com número errado é pior que silêncio.
    const r = S.resumoCorrida(semTrabalho('2026-08-04'), TEMPO, 7, historico({
      dia_semana: { exigidas: 4, encontradas: 3, com_trabalho: 3,
                    atipico: false },
    }))
    return { frase: r.diaAtipico, faixa: r.faixa }
  })

  cenario('nome_do_dia_da_semana', () => ({
    terca: H.diaDaSemana('2026-08-04'),
    sabado: H.diaDaSemana('2026-08-08'),
    domingo: H.diaDaSemana('2026-08-09'),
    // ⚠️ O fuso: `new Date('2026-08-04')` lido em hora local (UTC−3) devolve
    // 03/08 e a terça viraria segunda. Este cenário é o que trava isso.
    quarta: H.diaDaSemana('2026-08-05'),
    sem_data: H.diaDaSemana(null),
  }))

  // ══ ACEITE — auditoria completa (Decisão 67) ═════════════════════════════
  const cancelada = corrida({
    status: 'CANCELADA', saude: null, fechada_em: '2026-08-05 05:20:00',
    fechada_por: 'manual:C123456',
    motivo: 'encerrada por C123456: carga do dia 03 remarcada para a tarde',
    tentativas: 2, reaberta_em: '2026-08-05 03:00:00',
    reaberta_por: 'manual:C999999',
  })

  cenario('cancelada_diz_quem_e_por_que', () => {
    const r = S.resumoCorrida(cancelada, TEMPO, 7, historico())
    return {
      encerramento: r.encerramento,
      motivo: r.motivo,
      reaberta: r.reaberta,
      origem: r.origemCurta,
      contagem: r.contagem,
      titulo: r.titulo,
    }
  })

  cenario('fechada_pelo_monitor_nao_transcreve_o_motor', () => {
    // Fechador AUTOMÁTICO: o `motivo` dele é o texto do motor ("3 pipeline(s)
    // sem concluir: …"), vocabulário de máquina que a Decisão 74 mantém fora
    // da interface. O card cala; a história dele é a aba de eventos.
    const r = S.resumoCorrida(corrida({
      status: 'FALHA', saude: null, fechada_em: '2026-08-05 04:02:00',
      fechada_por: 'guardia',
      motivo: '3 pipeline(s) sem concluir: CARGA_A (falhou), CARGA_C (nao_liberou)',
    }), TEMPO, 7, historico())
    return { encerramento: r.encerramento, motivo: r.motivo, titulo: r.titulo }
  })

  cenario('origem_implicita_diz_sem_no_inicio', () => {
    const r = S.resumoCorrida(corrida({
      origem: 'implicita', aberta_por: 'implicita:CARGA_C',
      ancora_pipeline: 'CARGA_C',
    }), TEMPO, 7, historico())
    return { origem: r.origemCurta, diagnostico: r.diagnostico }
  })

  cenario('origem_manual_nomeia_quem_disparou', () => {
    const r = S.resumoCorrida(corrida({
      origem: 'manual', aberta_por: 'manual:C123456',
    }), TEMPO, 7, historico())
    return { origem: r.origemCurta, diagnostico: r.diagnostico }
  })

  cenario('origem_agendada_cala', () => {
    const r = S.resumoCorrida(corrida(), TEMPO, 7, historico())
    return { origem: r.origemCurta }
  })

  // ══ ACEITE — o `title` do bloco da faixa (Decisões 42/67/68) ════════════
  const rotulo = (s) => S.estiloCorrida(s).rotulo

  cenario('titulo_do_bloco_com_travado', () => H.tituloDoBloco({
    id: 9, malha_name: 'M1', data_referencia: '2026-08-04', sequencia: 1,
    status: 'FALHA', aberta_em: '2026-08-04 01:10:00',
    fechada_em: '2026-08-04 03:51:00', fechada_por: 'guardia',
    origem: 'inicio', aberta_por: 'inicio:#1', ancora_pipeline: null,
    modo_fechamento: 'quiescencia', teto_em: null, tentativas: 1,
    reaberta_em: null, reaberta_por: null, motivo: null,
    travou: { pipeline: 'CARGA_A', classe: 'falhou' },
  }, rotulo, S.quemFez))

  cenario('titulo_do_bloco_com_auditoria', () => H.tituloDoBloco(
    Object.assign({}, cancelada, {
      travou: { pipeline: 'CARGA_B', classe: 'nao_liberou' },
    }), rotulo, S.quemFez))

  cenario('titulo_do_bloco_sem_travou_apurado', () => H.tituloDoBloco({
    id: 8, malha_name: 'M1', data_referencia: '2026-08-03', sequencia: 2,
    status: 'CONCLUIDA', aberta_em: '2026-08-03 01:10:00',
    fechada_em: '2026-08-03 03:51:00', fechada_por: 'guardia',
    origem: 'inicio', aberta_por: 'inicio:#1', ancora_pipeline: null,
    modo_fechamento: 'quiescencia', teto_em: null, tentativas: 1,
    reaberta_em: null, reaberta_por: null, motivo: null, travou: null,
  }, rotulo, S.quemFez))

  // ══ ACEITE — Decisão 56b: o percentual de TEMPO ═════════════════════════
  //
  // O desenho da própria spec: malha de 6 em que o último leva 3h e os cinco
  // primeiros 5 min cada. Aos 25 min, `5 de 6` é 83% dos PIPELINES e 12% do
  // TRABALHO — e é 12% que o número tem de dizer.
  const SEIS = [
    item('A', 300, 23), item('B', 300, 23), item('C', 300, 23),
    item('D', 300, 23), item('E', 300, 23), item('F', 10800, 23),
  ]
  const pct = (over) => D.percentualTempoTipico(Object.assign({
    tipicos: tipicos(SEIS), execucoes: [], status: 'ABERTA', saude: 'OK',
    apuradoEm: APURADO_BANCO, respostaEm: LOCAL, agoraLocal: LOCAL,
  }, over))

  cenario('cinco_de_seis_nao_e_83_por_cento', () => {
    const r = pct({
      execucoes: [
        exec('A', 'SUCESSO', null), exec('B', 'SUCESSO', null),
        exec('C', 'SUCESSO', null), exec('D', 'SUCESSO', null),
        exec('E', 'SUCESSO', null),
        // O pesado começou há 0 min (o carimbo é o próprio `apurado_em`).
        exec('F', 'EXECUTANDO', APURADO_BANCO),
      ],
    })
    return r
  })

  cenario('membro_em_execucao_nao_passa_da_propria_fatia', () => {
    // `F` já roda há 6h — o dobro do típico dele. Sem o teto por membro, a
    // fatia dele sozinha estouraria o denominador e o número diria "progresso"
    // onde há atraso. Com a corrida em `OK`, ele entra por 3h (a própria
    // fatia) e o total fecha em 100 — que o teto de 99 segura.
    const r = pct({
      execucoes: [exec('F', 'EXECUTANDO', '2026-08-05 07:59:20')],
    })
    return r
  })

  cenario('atrasada_passa_de_cem', () => {
    // MESMO cenário, com a corrida ATRASADA: agora o número diz a verdade que
    // o operador precisa ver, e truncar em 100 esconderia justamente isso.
    const r = pct({
      saude: 'ATRASADA',
      execucoes: [
        exec('A', 'SUCESSO', null), exec('B', 'SUCESSO', null),
        exec('C', 'SUCESSO', null), exec('D', 'SUCESSO', null),
        exec('E', 'SUCESSO', null),
        exec('F', 'EXECUTANDO', '2026-08-05 07:59:20'),   // 6h de execução
      ],
    })
    return r
  })

  cenario('teto_em_99_enquanto_nao_terminou', () => {
    // TODOS concluídos e a corrida ainda ABERTA (o estado "fechando"): 100%
    // com a corrida aberta é a palavra "pronto" dita por um número.
    const r = pct({
      execucoes: SEIS.map(i => exec(i.pipeline, 'SUCESSO', null)),
    })
    return r
  })

  cenario('esperando_dependencia_nao_acumula', () => {
    // `C` está esperando há 3h. Fila não é trabalho: contá-la faria o número
    // subir enquanto nada acontece.
    const r = pct({
      execucoes: [exec('C', 'AGUARDANDO_DEPENDENCIA', '2026-08-05 10:59:20')],
    })
    return r
  })

  cenario('falha_e_pulado_somam_zero', () => {
    const r = pct({
      execucoes: [exec('A', 'FALHA', '2026-08-05 13:00:00'),
                  exec('B', 'PULADO', null)],
    })
    return r
  })

  cenario('um_membro_sem_amostra_apaga_o_numero', () => {
    // O piso é do CONJUNTO (Decisão 56b): 5 de 6 membros com histórico e o
    // percentual some por completo — não é estimado, não é "com ressalva".
    const r = D.percentualTempoTipico({
      tipicos: tipicos(SEIS.slice(0, 5), 6),
      execucoes: SEIS.map(i => exec(i.pipeline, 'SUCESSO', null)),
      status: 'ABERTA', saude: 'OK', apuradoEm: APURADO_BANCO,
      respostaEm: LOCAL, agoraLocal: LOCAL,
    })
    return { resultado: r, completo: tipicos(SEIS.slice(0, 5), 6).completo }
  })

  cenario('corrida_terminal_nao_tem_percentual', () => ({
    concluida: pct({ status: 'CONCLUIDA', saude: null,
                     execucoes: SEIS.map(i => exec(i.pipeline, 'SUCESSO', null)) }),
    falha: pct({ status: 'FALHA', saude: null, execucoes: [] }),
    sem_trabalho: pct({ status: 'SEM_TRABALHO', saude: null, execucoes: [] }),
  }))

  cenario('relogio_do_banco_mais_o_local', () => {
    // Decisão 60, aplicada ao percentual: o decorrido do membro vivo é
    // `inicio → apurado_em` (os DOIS do BANCO, subtraídos entre si) MAIS o que
    // passou no relógio LOCAL desde a resposta. Com o navegador 3h atrás — o
    // desvio medido no dev —, um `Date.now() − inicio` daria NEGATIVO e o
    // número nasceria em 0% a madrugada inteira.
    //
    // 1h de execução sobre uma fatia de 3h, num total de 12.300 s → 29%. Dez
    // minutos depois, sem resposta nova, ele ANDA (34%): é isso que faz o
    // painel não congelar entre refetches.
    const execucoes = [exec('F', 'EXECUTANDO', '2026-08-05 12:59:20')] // 1h
    const noInstante = D.percentualTempoTipico({
      tipicos: tipicos(SEIS), execucoes, status: 'ABERTA', saude: 'OK',
      apuradoEm: APURADO_BANCO, respostaEm: LOCAL, agoraLocal: LOCAL,
    })
    // 10 min depois no relógio LOCAL, sem resposta nova do servidor.
    const dezMinDepois = D.percentualTempoTipico({
      tipicos: tipicos(SEIS), execucoes, status: 'ABERTA', saude: 'OK',
      apuradoEm: APURADO_BANCO, respostaEm: LOCAL,
      agoraLocal: LOCAL + 10 * 60_000,
    })
    return { no_instante: noInstante, dez_min_depois: dezMinDepois }
  })

  // ══ ACEITE — o `x de y` continua PRIMÁRIO, o `%` é o SEGUNDO ════════════
  cenario('percentual_e_o_segundo_numero_da_faixa', () => {
    const c = corrida()
    const r = S.resumoCorrida(c, TEMPO, 7, historico())
    const raiz = Prog.CorridaProgresso({
      resumo: r, variante: 'painel', percentualTempo: '≈ 38% do tempo típico',
    })
    const textos = textoDe(raiz).map(t => String(t).trim()).filter(Boolean)
    return {
      ordem: textos,
      lido: tudoQueSeLe(raiz),
      // O que o leitor de tela anuncia pela BARRA continua sem "%": o
      // percentual de CONTAGEM não pode voltar pela porta da acessibilidade.
      aria_da_barra: (todosOsNos(raiz).find(n => n.tipo === 'Progress')
                      || { props: {} }).props.valorTexto,
    }
  })

  cenario('card_nao_recebe_percentual', () => {
    // O card da lista renderiza a MESMA barra sem o segundo número: lá cabe um
    // número só, e o que fica é o primário.
    const r = S.resumoCorrida(corrida(), TEMPO, 7, historico())
    const raiz = Prog.CorridaProgresso({ resumo: r, variante: 'card' })
    return { lido: tudoQueSeLe(raiz) }
  })

  process.stdout.write(JSON.stringify(saida, null, 1))
}

main().catch(e => {
  process.stdout.write(JSON.stringify({ __falhou__: String(e && e.stack || e) }))
  process.exitCode = 1
})
