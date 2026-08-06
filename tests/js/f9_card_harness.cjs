// Banco de provas do CARD da F9 (spec-malha-execucao.md §9.1–§9.3) — o bloco
// de corrida da lista de malhas: `CorridaBadge`, `CorridaProgresso` e as
// derivações puras de `statusExecucao.ts` que os alimentam.
//
// Por que RENDERIZAR, e não conferir só o texto das funções puras
// ───────────────────────────────────────────────────────────────
// Três dos aceites da fase são afirmações sobre o que aparece na TELA, e dois
// deles são afirmações de AUSÊNCIA:
//
//   • sábado com todos os membros dispensados → **nenhuma barra**, o texto
//     "nada previsto", e a palavra "concluída" ausente. "Nenhuma barra" é uma
//     afirmação sobre a árvore renderizada: uma barra com `total = 0` passaria
//     em qualquer teste de string;
//   • corrida ABERTA com todos os membros prontos → barra CHEIA e nem "100%"
//     nem "concluída" em lugar nenhum. Prova de ausência quer todo o texto que
//     a árvore produz, incluindo `title`, `aria-label` e `aria-valuetext` —
//     este último é onde o percentual entraria sem ninguém ver, porque o leitor
//     de tela CALCULA `valuenow/valuemax` quando ele falta;
//   • `EXPIRADA`/`CANCELADA` → barra congelada com `opacity-60`. É classe no
//     nó, não frase no código.
//
// Como isto roda sem runner de JS: a mesma técnica de `f4_front_harness.cjs` e
// `f9_base_harness.cjs` — o `sucrase` que o Vite já traz transpila os arquivos
// do `src/` byte a byte, com o JSX clássico apontando para um `__h` nosso que
// devolve a árvore como objeto puro. Os dois componentes são funções de
// renderização sem hook e sem estado; foi assim que eles nasceram, e é por isso
// que dá para chamá-los direto.
//
// Saída: um JSON só, no stdout, consumido por `tests/test_malhas_f9_card.py`.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const SRC = path.join(RAIZ, 'ui-react', 'src')
const { transform } = require(path.join(RAIZ, 'ui-react', 'node_modules', 'sucrase'))

// Módulos do `src/`, achatados num diretório só. `ui/Progress.tsx` entra
// porque `CorridaProgresso` o usa de verdade — dublá-lo esconderia justamente
// o que a barra anuncia.
const MODULOS = [
  ['components/malhas/tempoCorrida.ts', 'tempoCorrida'],
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
    // Node ESM exige a extensão; o bundler do Vite não. `../ui/Progress` e
    // `./statusExecucao` viram vizinhos no diretório achatado.
    js = js
      .replace(/from\s*['"]lucide-react['"]/g, "from './lucide.mjs'")
      .replace(/from\s*'\.\.\/ui\/([A-Za-z0-9_]+)'/g, "from './$1.mjs'")
      .replace(/from\s*'\.\/([A-Za-z0-9_]+)'/g, "from './$1.mjs'")
    const precisaJsx = relativo.endsWith('.tsx')
    const preambulo = precisaJsx ? "import { __h, __Frag } from './jsx.mjs'\n" : ''
    fs.writeFileSync(path.join(destino, nome + '.mjs'), preambulo + js)
  }
  // Cada ícone vira o próprio NOME: é o que permite provar que os três
  // desfechos vermelhos e os dois âmbares NÃO compartilham ícone — cor nunca é
  // canal único nesta casa.
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

// ── utilidades de árvore ────────────────────────────────────────────────────
function todosOsNos(no, saida = []) {
  if (!no || typeof no !== 'object') return saida
  saida.push(no)
  for (const f of no.filhos || []) todosOsNos(f, saida)
  return saida
}

/** TODO o texto que a árvore renderiza — é sobre ele que se prova ausência. */
function textoDe(no, partes = []) {
  if (no === null || no === undefined || typeof no === 'boolean') return partes
  if (typeof no !== 'object') { partes.push(String(no)); return partes }
  for (const f of no.filhos || []) textoDe(f, partes)
  return partes
}

/** Texto + TUDO que é lido por quem não enxerga a tela (`title`, `aria-*`) e o
 *  que identifica cada nó. É este conjunto que responde "a palavra X aparece
 *  em algum lugar?". */
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

/** As props com que a `Progress` foi chamada — ela aparece na árvore como um
 *  nó de função (não há React aqui para expandi-la), e é por essas props que
 *  passam o denominador, o valor anunciado e o `aria-valuetext`. */
function propsDaBarra(raiz) {
  const no = todosOsNos(raiz).find(n => n.tipo === 'Progress')
  return no ? no.props : null
}

// ── os dois relógios, com o desvio MEDIDO no dev ────────────────────────────
const LOCAL = Date.parse('2026-08-05T10:59:00Z')
const APURADO_BANCO = '2026-08-05 13:59:20'
const TEMPO = { respostaEm: LOCAL, agora: LOCAL }

function corrida(over) {
  return Object.assign({
    id: 1, malha_name: 'M1', data_referencia: '2026-08-05', sequencia: 1,
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

function esperada(over) {
  return Object.assign({
    data_referencia: '2026-08-05', previsto_para: '01:00',
    atrasada_desde: '2026-08-05 01:00:00', atrasada_min: 360,
    bloqueada_por_corrida_aberta: false,
  }, over)
}

async function main() {
  const destino = fs.mkdtempSync(path.join(os.tmpdir(), 'f9card-'))
  preparar(destino)
  const S = await import(path.join(destino, 'statusExecucao.mjs'))
  const Badge = await import(path.join(destino, 'CorridaBadge.mjs'))
  const Prog = await import(path.join(destino, 'CorridaProgresso.mjs'))

  const saida = {}
  const cenario = (nome, fn) => {
    try { saida[nome] = fn() } catch (e) {
      saida[nome] = { __erro__: String((e && e.stack) || e) }
    }
  }

  const progresso = (c, extra) => Prog.CorridaProgresso(Object.assign({
    resumo: S.resumoCorrida(c, TEMPO, 7),
    variante: 'card',
  }, extra))

  // ══ ACEITE 1 — sábado com todos dispensados: NENHUMA barra ═══════════════
  cenario('sabado_sem_trabalho', () => {
    const c = corrida({
      status: 'SEM_TRABALHO', saude: null, membros_ok: 0, membros_vivos: 0,
      membros_dispensados: 7, data_referencia: '2026-08-08',
      fechada_em: '2026-08-08 01:15:00',
    })
    const raiz = progresso(c)
    const r = S.resumoCorrida(c, TEMPO, 7)
    return {
      barra: propsDaBarra(raiz),           // tem de ser null: NENHUMA barra
      contagem: r.contagem,
      nada_previsto: r.nadaPrevisto,
      membros: r.membros,
      lido: tudoQueSeLe(raiz),
      rotulo_do_estado: S.estadoDaCorrida(c).rotulo,
    }
  })

  // ══ ACEITE 2 — barra CHEIA não é "concluída" ═════════════════════════════
  cenario('corrida_aberta_com_tudo_pronto', () => {
    // 7 de 7, nenhum dispensado: o desenho do aceite, literal.
    const c = corrida({
      membros_ok: 7, membros_vivos: 0, membros_dispensados: 0,
      quiescencia_ate: '2026-08-05 04:17:00',
      ultimo_movimento_em: '2026-08-05 04:02:00',
    })
    const raiz = progresso(c)
    const r = S.resumoCorrida(c, TEMPO, 7)
    return {
      contagem: r.contagem,
      fechando: r.fechando,
      fechamento: r.fechamento,
      barra: propsDaBarra(raiz),
      lido: tudoQueSeLe(raiz),
      titulo_da_corrida: r.titulo,
    }
  })

  cenario('barra_cheia_com_dispensados', () => {
    // 5 prontos + 2 que não rodam hoje = os 7 do snapshot. A barra fecha, e o
    // denominador NÃO encolhe (Decisão 52): jamais "5 de 5".
    const c = corrida({
      membros_ok: 5, membros_vivos: 0, membros_dispensados: 2,
      quiescencia_ate: '2026-08-05 04:17:00',
    })
    const r = S.resumoCorrida(c, TEMPO, 7)
    const raiz = progresso(c)
    return {
      contagem: r.contagem, fechando: r.fechando, membros: r.membros,
      barra: propsDaBarra(raiz), lido: tudoQueSeLe(raiz),
    }
  })

  cenario('malha_com_no_fim_nao_promete_o_relogio_errado', () => {
    // Malha que fecha pelo nó Fim não tem carência de quiescência: dizer
    // "fecha 15 min após o último movimento" descreveria o mecanismo errado.
    const c = corrida({
      membros_ok: 7, membros_vivos: 0, membros_dispensados: 0,
      modo_fechamento: 'fim', quiescencia_ate: '2026-08-05 04:17:00',
    })
    return { fechamento: S.resumoCorrida(c, TEMPO, 7).fechamento }
  })

  // ══ ACEITE 3 — desfecho interrompido: barra CONGELADA ════════════════════
  cenario('expirada_congela_a_barra', () => {
    const c = corrida({
      status: 'EXPIRADA', saude: null, membros_ok: 4, membros_vivos: 0,
      membros_dispensados: 0, membros_travados: 2,
      fechada_em: '2026-08-05 07:10:00',
      pendentes: [{ pipeline: 'CARGA_A', classe: 'falhou',
                    desde: '2026-08-05 03:07:00', faltante: null }],
    })
    const r = S.resumoCorrida(c, TEMPO, 7)
    const raiz = Prog.CorridaProgresso({ resumo: r, variante: 'card',
                                         congelado: true })
    return {
      contagem: r.contagem, travados: r.travados,
      classes: classes(raiz), lido: tudoQueSeLe(raiz),
      barra: propsDaBarra(raiz),
      estilo: { rotulo: r.estilo.rotulo, icone: r.estilo.Icone },
    }
  })

  cenario('cancelada_diz_quem_e_por_que', () => {
    const c = corrida({
      status: 'CANCELADA', saude: null, membros_ok: 4, membros_vivos: 0,
      membros_dispensados: 0, fechada_em: '2026-08-05 05:20:00',
      fechada_por: 'manual:C123456',
      motivo: 'encerrada por C123456: carga do dia 03 remarcada para a tarde',
    })
    const r = S.resumoCorrida(c, TEMPO, 7)
    return {
      contagem: r.contagem, encerramento: r.encerramento, motivo: r.motivo,
      estilo: { rotulo: r.estilo.rotulo, chip: r.estilo.chip,
                icone: r.estilo.Icone },
      congelado_pela_lista: [...S.CORRIDA_INTERROMPIDA],
    }
  })

  // ══ ACEITE 4 — a corrida que NÃO ABRIU ═══════════════════════════════════
  cenario('nao_abriu', () => {
    const e = esperada({})
    const r = S.resumoEsperada(e, TEMPO)
    const raiz = Badge.CorridaBadge({ corrida: corrida({}), esperada: e })
    return {
      cabecalho: r.cabecalho, sem_corrida: r.semCorrida, bloqueio: r.bloqueio,
      estilo: { rotulo: r.estilo.rotulo, chip: r.estilo.chip,
                icone: r.estilo.Icone },
      titulo: r.titulo,
      // A pílula anuncia "não abriu" mesmo com a corrida de ONTEM em mãos: o
      // que o operador precisa às 8h não é que ontem foi bem.
      badge_lido: tudoQueSeLe(raiz),
    }
  })

  cenario('nao_abriu_bloqueada_pela_de_ontem', () => {
    const r = S.resumoEsperada(esperada({ bloqueada_por_corrida_aberta: true }),
                               TEMPO)
    return { bloqueio: r.bloqueio, titulo: r.titulo }
  })

  cenario('atraso_anda_com_o_relogio_local', () => {
    const e = esperada({})
    // O servidor mediu 360 min; 61 s de relógio LOCAL depois, 361. Nenhum
    // `Date.now() − atrasada_desde` no meio (o carimbo é do BANCO, 3h à
    // frente: a conta ingênua diria "há 3h a mais").
    const depois = S.resumoEsperada(e, { respostaEm: LOCAL, agora: LOCAL + 61_000 })
    return {
      agora: S.resumoEsperada(e, TEMPO).cabecalho,
      um_minuto_depois: depois.cabecalho,
      ingenuo_min: Math.round(
        (LOCAL - Date.parse(e.atrasada_desde.replace(' ', 'T') + 'Z')) / 60000),
    }
  })

  // ══ Decisão 56 — nenhum percentual de CONTAGEM, em superfície nenhuma ════
  cenario('nada_de_percentual_em_lugar_nenhum', () => {
    const estados = [
      corrida({}),
      corrida({ membros_ok: 7, membros_vivos: 0, membros_dispensados: 0 }),
      corrida({ status: 'CONCLUIDA', saude: null, membros_ok: 6,
                membros_vivos: 0, membros_dispensados: 1,
                fechada_em: '2026-08-05 04:02:00' }),
      corrida({ status: 'SEM_TRABALHO', saude: null, membros_ok: 0,
                membros_vivos: 0, membros_dispensados: 7 }),
      corrida({ status: 'EXPIRADA', saude: null, membros_travados: 2 }),
    ]
    return estados.map(c => {
      const raiz = progresso(c)
      const p = propsDaBarra(raiz)
      return {
        lido: tudoQueSeLe(raiz),
        valuetext: p ? p.valorTexto : null,
        arialabel: p ? p.ariaLabel : null,
        titulo: S.resumoCorrida(c, TEMPO, 7).titulo,
      }
    })
  })

  // ══ Decisão 74 — "#N" não aparece na interface ═══════════════════════════
  cenario('nada_de_numero_de_maquina', () => {
    const c = corrida({
      sequencia: 2, aberta_por: 'inicio:#12', id: 987,
      status: 'CANCELADA', saude: null, fechada_por: 'manual:C123456',
      fechada_em: '2026-08-05 05:20:00', tentativas: 2,
      reaberta_por: 'manual:C123456',
    })
    const r = S.resumoCorrida(c, TEMPO, 7)
    return {
      identidade: r.identidade,
      lido: tudoQueSeLe(progresso(c)),
      titulo: r.titulo,
      diagnostico: r.diagnostico,
    }
  })

  // ══ a barra: ordem FIXA, denominador que não encolhe, travado FORA ═══════
  cenario('composicao_da_barra', () => {
    const c = corrida({
      membros_ok: 3, membros_vivos: 1, membros_dispensados: 1,
      membros_travados: 2,
      pendentes: [{ pipeline: 'CARGA_A', classe: 'falhou',
                    desde: '2026-08-05 03:07:00', faltante: null },
                  { pipeline: 'CARGA_C', classe: 'nao_liberou',
                    desde: '2026-08-05 03:07:00', faltante: null }],
    })
    const raiz = progresso(c)
    const p = propsDaBarra(raiz)
    const r = S.resumoCorrida(c, TEMPO, 7)
    return {
      chaves: p.segmentos.map(s => s.chave),
      valores: p.segmentos.map(s => s.valor),
      animados: p.segmentos.map(s => !!s.animado),
      hachurados: p.segmentos.map(s => !!s.hachurado),
      total: p.total, valor_atual: p.valorAtual,
      soma_dos_segmentos: p.segmentos.reduce((s, x) => s + x.valor, 0),
      contagem: r.contagem, travados: r.travados, culpado: r.culpado,
      lido: tudoQueSeLe(raiz),
    }
  })

  cenario('sem_contadores_nao_desenha_barra', () => {
    // Lock timeout na apuração: `membros_total` nulo. Publicar barra vazia
    // seria mostrar zero como se fosse medida.
    const c = corrida({
      membros_total: null, membros_ok: null, membros_vivos: null,
      membros_dispensados: null, membros_travados: null, saude: null,
    })
    const r = S.resumoCorrida(c, TEMPO, 7)
    const raiz = progresso(c)
    return {
      barra: propsDaBarra(raiz), contagem: r.contagem, membros: r.membros,
      // o ESTADO do ciclo continua sendo dito — é o que mais importa às 3h
      rotulo: S.estadoDaCorrida(c).rotulo,
      lido: tudoQueSeLe(raiz),
    }
  })

  // ══ a pílula: um estado, três canais (cor, ícone e rótulo) ═══════════════
  cenario('pilula_por_estado', () => {
    const casos = {
      ABERTA_OK: corrida({}),
      ABERTA_COM_FALHA: corrida({ saude: 'COM_FALHA' }),
      ABERTA_SEM_PROGRESSO: corrida({ saude: 'SEM_PROGRESSO', sem_sinal_min: 40 }),
      CONCLUIDA: corrida({ status: 'CONCLUIDA', saude: null }),
      FALHA: corrida({ status: 'FALHA', saude: null }),
      EXPIRADA: corrida({ status: 'EXPIRADA', saude: null }),
      ABORTADA: corrida({ status: 'ABORTADA', saude: null }),
      SEM_TRABALHO: corrida({ status: 'SEM_TRABALHO', saude: null }),
      CANCELADA: corrida({ status: 'CANCELADA', saude: null }),
    }
    const out = {}
    for (const [nome, c] of Object.entries(casos)) {
      const raiz = Badge.CorridaBadge({ corrida: c })
      const nos = todosOsNos(raiz)
      out[nome] = {
        texto: textoDe(raiz).join(''),
        classes: raiz.props.className,
        icone: nos.map(n => n.tipo).find(t => String(t).startsWith('icone:')),
        animado: nos.some(n => String(n.props.className || '')
          .includes('animate-pulse')),
      }
    }
    return out
  })

  cenario('pilula_sem_dado_nao_renderiza', () => ({
    // Degradação por AUSÊNCIA (Decisão 41): quem escreve "(membro mais
    // recente)" é o CHAMADOR, que é quem tem o dado antigo.
    vazia: Badge.CorridaBadge({ corrida: null }),
    vazia_com_esperada_nula: Badge.CorridaBadge({ corrida: null, esperada: null }),
  }))

  process.stdout.write(JSON.stringify(saida, null, 1))
}

main().catch(e => {
  process.stderr.write(String((e && e.stack) || e))
  process.exit(1)
})
