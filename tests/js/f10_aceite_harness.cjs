// Bancada de ACEITE do front da F10 — `docs/spec-malha-execucao.md` §10/F10.
//
// A diferença para o `f10_painel_harness.cjs`, que é da mesma fase: aquele
// executa os módulos PUROS (`statusExecucao`, `proximaExecucao`, `tempoCorrida`)
// e responde perguntas de função. Este RENDERIZA os componentes — `Cabecalho
// Corrida`, `PainelCorridaLateral`, `RelogioCorrida`, `SeletorCorrida` — e
// clica neles, porque metade do aceite desta fase é sobre o que a tela mostra,
// e não sobre o que uma função devolve.
//
// ⚠️ POR QUE ISTO, E NÃO `grep` NO `.tsx`
// Os aceites "`Encerrar corrida…` está presente e HABILITADO em ABERTA·OK,
// ABERTA·COM_FALHA e ABERTA·SEM_PROGRESSO", "a confirmação diz que os
// pipelines em execução continuam rodando", "`Agora (2)` → badge NEUTRO" e
// "malha sem `teto_horas` → NENHUMA barra de limite" são todos sobre RENDER.
// Um `grep` que ache a string no arquivo fica verde com a string num ramo
// morto — é o falso verde que a F7 já pagou nesta spec (afirmar a MENSAGEM e
// não o COMPORTAMENTO, com o hold congelando a corrida e a suíte verde).
//
// Como roda: `sucrase` (que o Vite já traz) transpila TS+JSX para CJS num
// diretório temporário que PRESERVA a árvore do `src/`; `react`,
// `react/jsx-runtime` e `lucide-react` viram shims num `node_modules/` local,
// então o `require` do Node resolve tudo sozinho, sem reescrever import
// nenhum. O React é o `minireact.cjs` — hooks de verdade e laço de re-render.
//
// Saída: um JSON só no stdout. Cada cenário é embrulhado e publica `{ erro }`
// em vez de derrubar o processo: um cenário que levanta tem de virar UM teste
// vermelho, não a suíte inteira.
'use strict'

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const SRC = path.join(RAIZ, 'ui-react', 'src')
const { transform } = require(path.join(RAIZ, 'ui-react', 'node_modules', 'sucrase'))
const mini = require(path.join(__dirname, 'minireact.cjs'))

const ENTRADAS = [
  'components/malhas/CabecalhoCorrida.tsx',
  'components/malhas/PainelCorridaLateral.tsx',
  'components/malhas/RelogioCorrida.tsx',
  'components/malhas/SeletorCorrida.tsx',
  'components/malhas/fluxoExecucao.ts',
  'components/malhas/statusExecucao.ts',
]

// ── transpilação com fecho transitivo pelos imports RELATIVOS ───────────────
function resolverRelativo(deDir, especificador) {
  const base = path.resolve(deDir, especificador)
  for (const tentativa of [base + '.tsx', base + '.ts',
                           path.join(base, 'index.tsx'),
                           path.join(base, 'index.ts')]) {
    if (fs.existsSync(tentativa)) return tentativa
  }
  return null
}

function preparar(destino) {
  const feitos = new Set()
  const icones = new Set()
  const fila = ENTRADAS.map(e => path.join(SRC, e))
  while (fila.length) {
    const arquivo = fila.pop()
    if (feitos.has(arquivo)) continue
    feitos.add(arquivo)
    const fonte = fs.readFileSync(arquivo, 'utf8')
    const js = transform(fonte, {
      transforms: ['typescript', 'jsx', 'imports'],
      jsxRuntime: 'automatic',
      production: true,
      filePath: arquivo,
    }).code
    const rel = path.relative(SRC, arquivo).replace(/\.tsx?$/, '.js')
    const alvo = path.join(destino, rel)
    fs.mkdirSync(path.dirname(alvo), { recursive: true })
    fs.writeFileSync(alvo, js)
    // Os ícones usados viram stub — `lucide-react` só desenha, e um SVG a
    // menos não muda nenhuma resposta desta bancada.
    for (const m of fonte.matchAll(
      /import\s*\{([^}]+)\}\s*from\s*['"]lucide-react['"]/g)) {
      for (const nome of m[1].split(',')) {
        const limpo = nome.trim()
        if (limpo) icones.add(limpo)
      }
    }
    // Só imports RELATIVOS entram no fecho: os bare viram shim.
    for (const m of fonte.matchAll(/from\s*['"](\.[^'"]+)['"]/g)) {
      // `import type { X } from './y'` é apagado pelo sucrase — mas seguir o
      // arquivo mesmo assim é barato e evita depender de qual import é de tipo.
      const destinoRel = resolverRelativo(path.dirname(arquivo), m[1])
      if (destinoRel) fila.push(destinoRel)
    }
  }
  return icones
}

function shims(destino, icones) {
  const nm = path.join(destino, 'node_modules')
  const escrever = (pacote, arquivo, conteudo) => {
    const dir = path.join(nm, pacote)
    fs.mkdirSync(dir, { recursive: true })
    fs.writeFileSync(path.join(dir, arquivo), conteudo)
  }
  const caminhoMini = JSON.stringify(path.join(__dirname, 'minireact.cjs'))
  escrever('react', 'package.json', '{"name":"react","main":"index.js"}')
  escrever('react', 'index.js', `
const mini = require(${caminhoMini})
module.exports = Object.assign({}, mini.hooks, {
  createElement: mini.criar, Fragment: mini.FRAGMENT,
})
module.exports.default = module.exports
`)
  const runtime = `
const mini = require(${caminhoMini})
const jsx = (tipo, props, key) => ({ __el: true, tipo, props: props || {}, key })
module.exports = { jsx, jsxs: jsx, jsxDEV: jsx, Fragment: mini.FRAGMENT }
`
  escrever('react', 'jsx-runtime.js', runtime)
  escrever('react', 'jsx-dev-runtime.js', runtime)
  escrever('lucide-react', 'package.json',
           '{"name":"lucide-react","main":"index.js"}')
  escrever('lucide-react', 'index.js',
           [...icones].map(n =>
             `exports.${n} = function ${n}(p){ return { __el: true, ` +
             `tipo: 'svg', props: Object.assign({ 'data-icone': ${JSON.stringify(n)} }, p) } }`
           ).join('\n') + '\n')
}

// ── os dados dos cenários ──────────────────────────────────────────────────
// Os dois relógios com o desvio MEDIDO no dev: o navegador marca 10:59, o SQL
// Server responde 13:59. Nenhum número desta bancada pode sair de subtrair um
// do outro (Decisão 60).
const LOCAL = Date.parse('2026-08-05T10:59:00Z')
const APURADO = '2026-08-05 13:59:20'

// ⚠️ ESTE OBJETO NÃO PODE INVENTAR CAMPO. A F8 desta mesma spec pagou o modo
// de falha "dublê que fabrica dado que o servidor real nunca produz": a tela
// fica verde na bancada e em branco na madrugada. Por isso o conjunto de
// chaves daqui é PUBLICADO na saída, e o `test_malhas_f10_aceite.py` o compara
// com o payload de verdade do `GET /malhas/{m}/execucao`. Campo a mais ou a
// menos reprova.
function corrida(over) {
  return Object.assign({
    id: 12, malha_name: 'M1', data_referencia: '2026-08-05', sequencia: 1,
    status: 'ABERTA', saude: 'OK', aberta_em: '2026-08-05 01:10:00',
    fechada_em: null, fechada_por: null, motivo: null, origem: 'inicio',
    aberta_por: 'agendamento do Início (CARGA_RAIZ)', ancora_pipeline: null,
    modo_fechamento: null, tentativas: 1, reaberta_em: null, reaberta_por: null,
    decorrido_min: 169, apurado_em: APURADO,
    membros_total: 7, membros_ok: 4, membros_vivos: 2, membros_dispensados: 1,
    membros_travados: 0, membros_nao_partiram: 0, membros_fora_do_odate: 0,
    membros_inativos: 0, sem_membros: false,
    pendentes: [], ultimo_movimento_em: '2026-08-05 13:56:00',
    sem_sinal_min: 3,
    // ── F7: os relógios do prazo ────────────────────────────────────────────
    // `teto_configurado` (= `etl_malha.teto_horas IS NOT NULL`) é o que decide
    // se a BARRA DE LIMITE existe; `teto_total_min` é o denominador dela,
    // subtraído NO BANCO. O default aqui é a malha SEM teto — que é o caso
    // comum e o lado difícil do aceite.
    teto_em: null, teto_vencido: false, teto_total_min: null,
    teto_creditado_min: 0, teto_horas: null, teto_configurado: false,
    retido_desde: null, retido_nos: 0, retido_por: null,
    // ── F9: o relógio do fechamento ─────────────────────────────────────────
    quiescencia_min: 15, quiescencia_ate: null,
  }, over)
}

/** A malha COM `teto_horas` configurado — 24 h de limite sobre uma corrida
 *  aberta às 01:10. `teto_total_min` vem do banco (`aberta_em → teto_em`) e é
 *  o denominador da barra. */
const COM_TETO = {
  teto_configurado: true, teto_horas: 24, teto_em: '2026-08-06 01:10:00',
  teto_total_min: 24 * 60, teto_vencido: false,
}

const pendente = (over) => Object.assign({
  pipeline: 'CARGA_A', classe: 'falhou', desde: '2026-08-05 03:07:00',
  faltante: null, faltantes: null, alcance: null, alcance_alta: null,
  criticidade: null,
}, over)

function main() {
  const destino = fs.mkdtempSync(path.join(os.tmpdir(), 'f10aceite-'))
  const icones = preparar(destino)
  shims(destino, icones)
  const req = (rel) => require(path.join(destino, rel))
  const { CabecalhoCorrida } = req('components/malhas/CabecalhoCorrida.js')
  const { PainelCorridaLateral } = req('components/malhas/PainelCorridaLateral.js')
  const { RelogioCorrida } = req('components/malhas/RelogioCorrida.js')
  const { SeletorCorrida } = req('components/malhas/SeletorCorrida.js')
  const S = req('components/malhas/statusExecucao.js')
  const F = req('components/malhas/fluxoExecucao.js')
  const el = mini.criar

  const saida = {}
  const cenario = (nome, fn) => {
    try { saida[nome] = fn() } catch (e) {
      saida[nome] = { erro: String((e && e.stack) || e) }
    }
  }

  const faixa = (over, extra) => mini.montar(el(CabecalhoCorrida, Object.assign({
    corrida: over === null ? null : corrida(over),
    resumo: over === null ? null
      : S.resumoCorrida(corrida(over), { respostaEm: LOCAL, agora: LOCAL }, 7),
    seletor: null, carregando: false, sem085: false,
    respostaEm: LOCAL, agoraLocal: LOCAL, nosSegurados: [], avisoPreso: null,
    onEncerrar: async () => {},
  }, extra || {})))

  // ══ aceite: `Encerrar corrida…` em TODA corrida ABERTA (Decisão 62) ═══════
  cenario('encerrar_em_toda_corrida_aberta', () => {
    const out = {}
    for (const saude of ['OK', 'COM_FALHA', 'SEM_PROGRESSO', 'ATRASADA']) {
      const tela = faixa({ saude, membros_travados: saude === 'OK' ? 0 : 1 })
      const b = tela.botoes('Encerrar corrida…')
      out[`ABERTA:${saude}`] = {
        presente: b.length === 1,
        // HABILITADO é o aceite literal — um botão que aparece cinza é a
        // mesma porta trancada com outra roupa.
        habilitado: b.length === 1 && !b[0].props.disabled,
      }
    }
    // E ele não existe em corrida FECHADA: não há o que encerrar.
    for (const status of ['CONCLUIDA', 'FALHA', 'EXPIRADA', 'CANCELADA']) {
      out[status] = { presente: faixa({ status, saude: null })
        .botoes('Encerrar corrida…').length > 0 }
    }
    // Sem permissão de execução o botão APARECE desabilitado, com o motivo —
    // esconder a saída de emergência faria o operador procurá-la onde ela não
    // está.
    const semPerm = faixa({}, { onEncerrar: undefined })
      .botoes('Encerrar corrida…')
    out['sem_permissao'] = {
      presente: semPerm.length === 1,
      habilitado: semPerm.length === 1 && !semPerm[0].props.disabled,
      title: semPerm.length === 1 ? semPerm[0].props.title : null,
    }
    return out
  })

  // ══ aceite: a confirmação diz a CONSEQUÊNCIA ═════════════════════════════
  cenario('confirmacao_do_encerramento', () => {
    const out = {}
    for (const [nome, over] of [['ok', { saude: 'OK' }],
                                ['com_falha', { saude: 'COM_FALHA' }],
                                ['sem_progresso', { saude: 'SEM_PROGRESSO',
                                                    sem_sinal_min: 41 }]]) {
      const tela = faixa(over)
      // Antes do clique não há confirmação nenhuma na tela.
      const antes = tela.texto
      tela.clicar(tela.botoes('Encerrar corrida…')[0])
      const depois = tela.texto
      const confirmar = tela.botoes('Encerrar corrida').filter(
        b => b.props.disabled !== undefined)
      out[nome] = {
        antes_tem_frase: /CONTINUAM rodando/.test(antes),
        texto: depois,
        // Motivo obrigatório (Decisão 32): o botão de confirmar nasce travado.
        confirmar_travado_sem_motivo:
          confirmar.length > 0 && confirmar[confirmar.length - 1].props.disabled === true,
      }
    }
    return out
  })

  // ══ aceite: `Agora (2)` com dois saudáveis → badge NEUTRO ════════════════
  cenario('badge_da_aba_agora', () => {
    const execucoes = [
      { pipeline_name: 'CARGA_B', status: 'EXECUTANDO',
        inicio: '2026-08-05 13:47:00', fim: null, disparado_por: null,
        motivo: null, execution_id: '' },
      { pipeline_name: 'CARGA_D', status: 'EXECUTANDO',
        inicio: '2026-08-05 13:56:00', fim: null, disparado_por: null,
        motivo: null, execution_id: '' },
    ]
    const tela = mini.montar(el(PainelCorridaLateral, {
      corrida: corrida({ membros_vivos: 2 }), execucoes, eventos: [],
      aba: 'agora', onAba: () => {}, onFocar: () => {},
      respostaEm: LOCAL, agoraLocal: LOCAL,
    }))
    // O badge é o `span` com o número dentro do botão da aba.
    const abas = tela.botoes().map(b => ({
      rotulo: b.filhos.filter(f => typeof f === 'string').join(' ').trim(),
      badge: b.filhos.filter(f => typeof f !== 'string' && f.tag === 'span')
        .map(s => ({ classe: s.props.className,
                     valor: s.filhos.join('') }))
        .filter(s => s.valor !== ''),
    })).filter(a => a.badge.length > 0)
    const classeDe = (rotulo) => {
      const a = abas.find(x => x.rotulo.startsWith(rotulo))
      return a ? a.badge[0].classe : null
    }
    return {
      agora: classeDe('Agora'),
      // O contraste que dá sentido ao aceite: se as duas classes fossem
      // iguais, "neutro" não significaria nada.
      travando_com_travado: (() => {
        const t = mini.montar(el(PainelCorridaLateral, {
          corrida: corrida({ pendentes: [pendente({})] }), execucoes: [],
          eventos: [], aba: 'travando', onAba: () => {}, onFocar: () => {},
          respostaEm: LOCAL, agoraLocal: LOCAL,
        }))
        const b = t.botoes('Travando')[0]
        const badge = b.filhos.filter(f => typeof f !== 'string'
                                      && f.tag === 'span')
        return badge.length ? badge[0].props.className : null
      })(),
    }
  })

  // ══ aceite: barra de LIMITE só com `teto_horas` configurado (Decisão 61) ══
  cenario('barra_de_limite', () => {
    const gatilho = { proximoGatilho: { quando: new Date(2026, 7, 6, 1, 0),
                                        hora: '01:00', texto: 'amanhã 01:00' } }
    const semTeto = faixa({}, gatilho)
    const comTeto = faixa(COM_TETO, gatilho)
    const barras = (t) => t.porPapel('progressbar').map(b => ({
      label: b.props['aria-label'],
      valuetext: b.props['aria-valuetext'],
      valuenow: b.props['aria-valuenow'],
      valuemax: b.props['aria-valuemax'],
    }))
    // Soltar um hold de 6 h empurra `teto_em` — e a barra ANDA PARA TRÁS. O
    // crédito vem colado nela, nomeado, ou o recuo é silencioso.
    const comCredito = faixa(Object.assign({}, COM_TETO, {
      teto_em: '2026-08-06 07:10:00', teto_total_min: 30 * 60,
      teto_creditado_min: 360,
    }))
    return {
      sem_teto: barras(semTeto),
      com_teto: barras(comTeto),
      // A linha do próximo gatilho é o prazo por PADRÃO: ela existe nos dois.
      gatilho_sem_teto: /a próxima corrida parte/.test(semTeto.texto),
      gatilho_com_teto: /a próxima corrida parte/.test(comTeto.texto),
      texto_sem_teto: semTeto.texto,
      texto_com_teto: comTeto.texto,
      credito: comCredito.texto,
      // Sem crédito nenhum a frase NÃO aparece: ela explica um número que
      // mudou, e sem mudança ela seria ruído.
      sem_credito: comTeto.texto,
    }
  })

  // ══ aceite: §18/12b — o dia com N corridas deixa de ser mudo ═════════════
  cenario('dia_com_varias_corridas', () => {
    const blocos = [
      { id: 9, sequencia: 1, status: 'CONCLUIDA', saude: null,
        data_referencia: '2026-08-05', aberta_em: '2026-08-05 01:10:00',
        fechada_em: '2026-08-05 04:02:00', membros_total: 7, membros_ok: 6 },
      { id: 12, sequencia: 2, status: 'ABERTA', saude: 'OK',
        data_referencia: '2026-08-05', aberta_em: '2026-08-05 05:20:00',
        fechada_em: null, membros_total: 7, membros_ok: 2 },
    ]
    const trocas = []
    const seletor = el(SeletorCorrida, {
      corridas: blocos, corridaId: null, onTrocar: c => trocas.push(c.id),
      // ⚠️ Os nomes são os do CONTRATO do componente. O `minireact` não
      // tipa nada: prop com nome errado vira `undefined` em silêncio, o
      // cenário continua verde e a bancada passa a provar uma tela que não
      // existe — o dublê mais permissivo que a coisa que ele imita.
      dataExibida: '2026-08-05', onIrParaData: () => {},
      onAgora: () => {}, noAgora: false, carregando: false,
    })
    // A API OMITE `corrida` quando o dia teve mais de uma (descrever uma
    // corrida sobre a lista do dia inteiro é a mesma mentira que a F4 matou).
    const tela = faixa(null, { corridasNoDia: 2, seletor })
    const mudo = faixa(null, { corridasNoDia: null, seletor })
    // A faixa do seletor, isolada: dois blocos, um por corrida.
    const so = mini.montar(seletor)
    const blocosNaTela = so.botoes().filter(b => b.props.title
      && /corrida de/.test(b.props.title))
    so.clicar(blocosNaTela[0])
    return {
      texto: tela.texto,
      diz_quantas: /este dia teve 2 corridas/.test(tela.texto),
      manda_escolher: /escolha uma/.test(tela.texto),
      // Sem `corridas_no_dia` a frase NÃO aparece: ela é sobre o dia com mais
      // de uma, e não sobre qualquer lente sem ciclo.
      mudo: mudo.texto,
      blocos: blocosNaTela.length,
      titulos: blocosNaTela.map(b => b.props.title),
      trocou_para: trocas,
    }
  })

  // ══ aceite: clicar em `Travando` acende a cadeia e centraliza ════════════
  cenario('um_clique_ate_o_problema', () => {
    const focados = []
    const etapas = []
    const rerun = []
    const tela = mini.montar(el(PainelCorridaLateral, {
      corrida: corrida({
        saude: 'COM_FALHA', membros_travados: 2,
        pendentes: [
          pendente({ pipeline: 'CARGA_A', classe: 'falhou', alcance: 4,
                     alcance_alta: 1, criticidade: 'Alta' }),
          pendente({ pipeline: 'CARGA_C', classe: 'nao_liberou',
                     faltantes: ['CARGA_A'], alcance: 0, alcance_alta: 0 }),
          pendente({ pipeline: 'CARGA_Z', classe: 'nao_partiu' }),
        ],
      }),
      execucoes: [], eventos: [], aba: 'travando', onAba: () => {},
      onFocar: p => focados.push(p),
      onAbrirEtapas: p => etapas.push(p),
      onReexecutar: p => rerun.push(p),
      fraseReexecucao: 'esta reexecução entra na corrida de 05/08 (em '
        + 'andamento); o relógio de fechamento NÃO reinicia por este gesto',
      respostaEm: LOCAL, agoraLocal: LOCAL,
    }))
    const linhas = tela.botoes('CARGA_A')
    tela.clicar(linhas[0])
    const realcar = tela.botoes('realçar cadeia')
    tela.clicar(realcar[0])
    const bReexec = tela.botoes('reexecutar')
    tela.clicar(bReexec[0])
    return {
      texto: tela.texto,
      focados, etapas, rerun,
      // Decisão 65: a frase do efeito vem ANTES do clique, no próprio botão.
      title_reexecutar: bReexec.map(b => b.props.title),
      // `nao_partiu` não ganha botão de reexecutar nem cor de alarme.
      botoes_por_linha: ['CARGA_A', 'CARGA_C', 'CARGA_Z'].map(
        p => tela.botoes(p).length),
    }
  })

  // ══ Decisão 65 — sem a frase, o botão NÃO EXISTE ════════════════════════
  cenario('reexecutar_sem_frase_nao_existe', () => {
    const tela = mini.montar(el(PainelCorridaLateral, {
      corrida: corrida({ pendentes: [pendente({})] }),
      execucoes: [], eventos: [], aba: 'travando', onAba: () => {},
      onFocar: () => {}, respostaEm: LOCAL, agoraLocal: LOCAL,
      // sem `onReexecutar`: é o que o editor faz quando não há ciclo ABERTO
      // em foco — a condição em que a frase não pode ser escrita com certeza.
    }))
    return { botoes: tela.botoes('reexecutar').length, texto: tela.texto }
  })

  // ══ aceite: malha SEM nó Fim — o evento do ciclo na aba `Eventos` ════════
  cenario('evento_do_ciclo_na_aba', () => {
    const tela = mini.montar(el(PainelCorridaLateral, {
      corrida: corrida({ status: 'FALHA', saude: null }),
      execucoes: [], aba: 'eventos', onAba: () => {}, onFocar: () => {},
      respostaEm: LOCAL, agoraLocal: LOCAL,
      eventos: [
        // Como o editor entrega o evento do CICLO: rótulo "corrida", nunca o
        // marcador `#corrida:{id}` (Decisão 74).
        { rotulo: 'corrida', ehNo: true, tipo: 'MALHA_FALHOU',
          criado_em: '2026-08-05 03:07:00', mensagem: 'malha M1 falhou',
          notificado_em: null },
        { rotulo: 'corrida', ehNo: true, tipo: 'MALHA_TETO_CREDITADO',
          criado_em: '2026-08-05 03:05:00', mensagem: '+6h por retenção',
          notificado_em: '2026-08-05 03:06:00' },
      ],
    }))
    return {
      texto: tela.texto,
      // `#corrida:12` é chave de máquina e não pode chegar à tela.
      tem_marcador: /#corrida/.test(tela.texto),
    }
  })

  // ══ aceite: a aresta de AGUARDANDO_DEPENDENCIA ≠ "não rodou" ═════════════
  //
  // "não rodou" tem DOIS rostos no desenho, e a aresta de quem espera não pode
  // ser igual a nenhum dos dois:
  //   • predecessor pronto e o destino sem linha nenhuma → a corrida está
  //     AVANÇANDO ali (azul animado). Era exatamente aqui que
  //     `AGUARDANDO_DEPENDENCIA` caía antes, porque `estadoDoPipeline`
  //     devolvia `null`: a tela prometia movimento sobre um pipeline PARADO;
  //   • nenhuma das duas pontas com linha → trecho inerte, cinza da Montagem.
  cenario('aresta_de_quem_espera', () => {
    const decorar = (origem, destino) => F.decorarAresta(
      F.estadoDaAresta(F.estadoDoPipeline(origem),
                       F.estadoDoPipeline(destino)), false)
    const avancando = decorar('SUCESSO', null)      // "ninguém pediu ainda"
    const inerte = decorar(null, null)              // "não rodou" puro
    const espera = decorar('SUCESSO', 'AGUARDANDO_DEPENDENCIA')
    const aresta = F.arestaComFluxo(
      { id: 'e1', source: 'CARGA_A', target: 'CARGA_C' }, 'esperando', false)
    const igual = (a, b) => JSON.stringify(a) === JSON.stringify(b)
    return {
      estado_de_quem_espera: F.estadoDoPipeline('AGUARDANDO_DEPENDENCIA'),
      estado_da_aresta: F.estadoDaAresta('concluido', 'esperando'),
      avancando, inerte, espera,
      // O aceite literal: nenhuma das duas caras de "não rodou" pode ser
      // igual à de quem espera.
      igual_a_avancando: igual(avancando, espera),
      igual_a_inerte: igual(inerte, espera),
      rotulo: F.ROTULO_FLUXO.esperando,
      // O rótulo acessível da aresta vem de `ROTULO_FLUXO` — a linha deixa de
      // ter a cor como canal único.
      aria: aresta.ariaLabel,
      animada: aresta.animated,
    }
  })

  // ══ revisão F10: o banner de HOLD não pode depender de haver ciclo ═══════
  // A condição da Decisão 66/2 é `retido_em` em algum nó, e nada mais. Um
  // Início SEGURADO impede a corrida de ABRIR — então prender o banner à
  // existência do ciclo o apagava exatamente no caso que ele existe para
  // cobrir, e o deixava intestável com `malha_corrida_ativa = 0` (o estado do
  // dev e o do dia do deploy), onde não há corrida nenhuma no banco.
  cenario('hold_com_e_sem_ciclo', () => {
    const nos = [{ id: 5, tipo: 'inicio', rotulo: 'Início',
                   retido_em: '2026-08-05 02:40:00', retido_por: 'C123456' }]
    const soltos = []
    const props = { nosSegurados: nos, onSoltar: id => soltos.push(id) }
    const semCiclo = faixa(null, props)
    const comCiclo = faixa({}, props)
    const botao = semCiclo.botoes('Soltar')
    if (botao.length) semCiclo.clicar(botao[0])
    return {
      sem_ciclo: semCiclo.texto,
      com_ciclo: comCiclo.texto,
      // O gesto também: soltar dali mesmo, sem ciclo e sem sair da lente.
      botao_soltar_sem_ciclo: botao.length,
      soltou: soltos,
      // Sem nó segurado não há banner — o contraste que dá sentido ao aceite.
      sem_no_segurado: faixa(null, { nosSegurados: [] }).texto,
    }
  })

  // ══ revisão F10: o carimbo de frescor sem NENHUMA resposta ═══════════════
  // `dataUpdatedAt` vale 0 enquanto nada chegou — inclusive depois de um erro,
  // quando a faixa continua na tela. Carimbar esse zero daria "há 466702h",
  // que é o carimbo de frescor mentindo sobre o próprio frescor.
  cenario('carimbo_sem_resposta', () => ({
    sem_resposta: faixa(null, { respostaEm: 0 }).texto,
    com_resposta: faixa(null, { respostaEm: LOCAL }).texto,
    velho: faixa(null, { respostaEm: LOCAL - 300000 }).texto,
  }))

  // As chaves do dublê, publicadas para o pytest cruzar com o payload REAL.
  saida.__fixture_corrida = Object.keys(corrida({})).sort()
  saida.__fixture_pendente = Object.keys(pendente({})).sort()

  process.stdout.write(JSON.stringify(saida))
  fs.rmSync(destino, { recursive: true, force: true })
}

main()
