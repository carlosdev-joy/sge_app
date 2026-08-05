// Banco de provas do FRONT da F4 + F4+ (spec-malha-execucao.md §9.1–§9.4).
//
// Por que este arquivo existe
// ───────────────────────────
// Três dos aceites da F4+ são afirmações sobre o NAVEGADOR, e nenhuma delas
// pode ser provada no pytest sozinho:
//
//   • "relógio deslocado 3 h → o carimbo diz `agora`, nunca `há -3h`, e o
//     alarme dispara aos 90 s" — é `frescor()` de `tempoCorrida.ts`, e o
//     defeito que ela evita SÓ aparece quando os dois relógios existem;
//   • "o card continua dizendo `2 de 7`, nunca `2 de 4`" — quem escreve essa
//     frase é `resumoCorrida()`, no front; a API só devolve os números;
//   • "o travado aparece FORA da barra" — é a separação entre `contagem` e
//     `travados` no mesmo resumo.
//
// O repo não tem runner de JS (`ui-react/package.json` tem `dev`, `build` e
// `lint`, e mais nada), e acrescentar um significaria acrescentar dependência
// de rede a um produto que faz deploy OFFLINE. Então a prova roda com o que já
// está instalado: o `sucrase` que o Vite traz transpila os módulos PUROS (que
// nasceram puros exatamente para isto — ver o cabeçalho de `tempoCorrida.ts`),
// e o Node executa. Nada aqui é dublê: os arquivos transpilados são os do
// `src/`, byte a byte, e a única substituição é `lucide-react`, que vira um
// stub de MARCADORES para que o teste possa afirmar *qual* ícone cada estado
// usa — a Decisão 59 exige que os três vermelhos tenham ícones diferentes.
//
// Saída: um JSON só, no stdout, consumido por `tests/test_malhas_f4_front.py`.
// Cada cenário é embrulhado em try/catch e publica `{ erro }` em vez de
// derrubar o processo: "renderizou sem exceção" é aceite, e um cenário que
// levanta tem de virar UM teste vermelho, não a suíte inteira.

const fs = require('fs')
const os = require('os')
const path = require('path')

const RAIZ = path.resolve(__dirname, '..', '..')
const SRC = path.join(RAIZ, 'ui-react', 'src', 'components', 'malhas')
const { transform } = require(path.join(RAIZ, 'ui-react', 'node_modules', 'sucrase'))

const MODULOS = ['tempoCorrida.ts', 'statusExecucao.ts', 'fluxoExecucao.ts']

// ── transpilação ────────────────────────────────────────────────────────────
// Só o transform `typescript`: o ESM é preservado, e é ele que o Node roda.
// Os `import type` (LucideIcon, CorridaApi, Edge, ExecComponente) somem no
// transform, então o único import de VALOR que sobra é o de `lucide-react`.
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
    // Node ESM exige a extensão no especificador; o bundler do Vite não.
    js = js
      .replace(/from\s*['"]lucide-react['"]/g, "from './lucide.mjs'")
      .replace(/from\s*'\.\/([A-Za-z0-9_]+)'/g, "from './$1.mjs'")
    fs.writeFileSync(path.join(destino, arquivo.replace(/\.ts$/, '.mjs')), js)
  }
  // O stub: cada ícone vira o próprio NOME. É o que permite ao teste provar
  // que `FALHA`, `EXPIRADA` e `ABORTADA` não compartilham ícone — cor nunca é
  // canal único nesta casa.
  const stub = [...icones].map(n => `export const ${n} = 'icone:${n}'`).join('\n')
  fs.writeFileSync(path.join(destino, 'lucide.mjs'), stub + '\n')
}

// ── os dois relógios, com o desvio MEDIDO no dev ─────────────────────────────
// O navegador (e o container da API) marcam 10:59; o SQL Server responde 13:59.
// Todo carimbo `apurado_em` desta bancada é o do BANCO, de propósito: é o valor
// que uma implementação ingênua subtrairia de `Date.now()`.
const LOCAL = Date.parse('2026-08-05T10:59:00Z')
const APURADO_BANCO = '2026-08-05 13:59:20'
const MIN = 60_000

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

function pendente(pipeline, classe, desde) {
  return { pipeline, classe, desde: desde ?? null, faltante: null }
}

// Só o que é serializável — o `Icone` vira o marcador do stub, e as funções
// não atravessam o JSON.
function comoJson(estilo) {
  return {
    rotulo: estilo.rotulo, chip: estilo.chip, dot: estilo.dot,
    icone: estilo.Icone, animado: !!estilo.animado,
  }
}

async function main() {
  const destino = fs.mkdtempSync(path.join(os.tmpdir(), 'f4front-'))
  preparar(destino)
  const T = await import(path.join(destino, 'tempoCorrida.mjs'))
  const S = await import(path.join(destino, 'statusExecucao.mjs'))
  const F = await import(path.join(destino, 'fluxoExecucao.mjs'))

  const saida = {}
  const cenario = (nome, fn) => {
    try {
      saida[nome] = fn()
    } catch (e) {
      saida[nome] = { erro: String((e && e.stack) || e) }
    }
  }

  // ══ Decisão 60 — o FRESCOR é o relógio local consigo mesmo ═══════════════
  cenario('frescor_no_instante_da_resposta', () => T.frescor(LOCAL, LOCAL))

  cenario('frescor_com_o_banco_3h_a_frente', () => ({
    // O que uma implementação ingênua faria: `Date.now() − apurado_em`, com
    // um carimbo que veio de OUTRO relógio. Publicado aqui para que o teste
    // prove que a armadilha existe NESTA bancada antes de provar que o módulo
    // escapa dela — senão o teste ficaria verde num cenário sem desvio.
    ingenuo_ms: LOCAL - Date.parse(APURADO_BANCO.replace(' ', 'T') + 'Z'),
    real: T.frescor(LOCAL, LOCAL),
    // O texto do tooltip é o ÚNICO consumidor de `apurado_em`.
    tooltip: T.carimboLongo(APURADO_BANCO),
  }))

  cenario('frescor_por_idade', () => {
    const pontos = [0, 29_999, 30_000, 59_999, 60_000, 89_999, 90_000, 90_001,
                    150_000, 3_600_000]
    return pontos.map(ms => {
      const f = T.frescor(LOCAL, LOCAL + ms)
      return { ms, texto: f.texto, velho: f.velho }
    })
  })

  cenario('frescor_com_relogio_local_para_tras',
          () => T.frescor(LOCAL, LOCAL - 3 * 3600_000))

  cenario('decorrido_soma_o_delta_local', () => ({
    // 42 min já subtraídos NO SERVIDOR + 61 s de relógio local = 43.
    base_mais_um_minuto: T.decorridoMin(42, LOCAL, LOCAL + 61_000),
    sem_base: T.decorridoMin(null, LOCAL, LOCAL + 61_000),
    // Relógio local para trás não faz o decorrido andar de ré.
    local_para_tras: T.decorridoMin(42, LOCAL, LOCAL - 3 * 3600_000),
  }))

  cenario('duracao_entre_dois_carimbos_do_banco', () => ({
    // Legítimo: as duas pontas são do MESMO relógio, o desvio cancela.
    corrida_inteira: T.duracaoEntre('2026-08-05 01:10:00', '2026-08-05 04:02:00'),
    texto: T.textoDuracao(T.duracaoEntre('2026-08-05 01:10:00',
                                         '2026-08-05 04:02:00')),
    formas: [0, 1, 59, 60, 90, 1440, 1514].map(m => T.textoDuracao(m)),
  }))

  cenario('data_de_referencia_nao_anda_um_dia_para_tras', () => ({
    // `new Date('2026-08-05')` é UTC e, em Brasília, vira 04/08 no
    // `toLocaleDateString` — a corrida de hoje apareceria como a de ontem.
    dia: T.diaCurto('2026-08-05'),
    dia_de_carimbo: T.diaCurto('2026-08-05 01:10:00'),
    hora: T.horaCurta('2026-08-05 01:10:00'),
    lixo: T.horaCurta('sem formato'),
  }))

  // ══ §9.3 — os estados, a saúde e a cor ═══════════════════════════════════
  cenario('estilo_por_status', () => {
    const out = {}
    for (const s of ['ABERTA', 'CONCLUIDA', 'FALHA', 'EXPIRADA', 'ABORTADA',
                     'SEM_TRABALHO', 'CANCELADA', 'ESTADO_QUE_NAO_EXISTE']) {
      out[s] = comoJson(S.estiloCorrida(s))
    }
    return out
  })

  cenario('a_saude_manda_na_cor_com_o_ciclo_aberto', () => {
    const out = {}
    for (const s of ['OK', 'COM_FALHA', 'ATRASADA', 'SEM_PROGRESSO']) {
      out[s] = comoJson(S.estiloCorrida('ABERTA', s))
    }
    // Corrida TERMINAL não herda saúde: o status já respondeu.
    out.TERMINAL_COM_SAUDE = comoJson(S.estiloCorrida('CONCLUIDA', 'COM_FALHA'))
    return out
  })

  // ══ o DEFEITO, do lado do front ══════════════════════════════════════════
  cenario('o_defeito_relatado_no_texto_do_card', () => {
    const r = S.resumoCorrida(corrida({
      saude: 'COM_FALHA', membros_ok: 1, membros_total: 2, membros_vivos: 0,
      membros_travados: 1,
      pendentes: [pendente('CARGA_A', 'falhou', '2026-08-05 03:00:00')],
    }), { respostaEm: LOCAL, agora: LOCAL })
    return {
      rotulo: r.estilo.rotulo, chip: r.estilo.chip, faixa: r.faixa,
      contagem: r.contagem, culpado: r.culpado, travados: r.travados,
      titulo: r.titulo,
    }
  })

  // ══ F4+/2 — o denominador que NÃO encolhe ════════════════════════════════
  cenario('duas_de_sete_com_tres_pulados', () => {
    const r = S.resumoCorrida(corrida({
      membros_ok: 2, membros_total: 7, membros_vivos: 2,
      membros_dispensados: 3,
    }), { respostaEm: LOCAL, agora: LOCAL }, 7)
    return { contagem: r.contagem, membros: r.membros, vivos: r.vivos }
  })

  cenario('membro_inativado_na_sexta_aparece_no_card', () => {
    // O caso da Decisão 53: 7 no cadastro, 2 no snapshot. Sem a subtração o
    // card diria "2 de 2 · concluída", verde, num sábado em que 5 pipelines
    // foram inativados na sexta.
    const r = S.resumoCorrida(corrida({
      status: 'CONCLUIDA', saude: null, membros_ok: 2, membros_total: 2,
      membros_vivos: 0, aberta_em: '2026-08-05 01:10:00',
      fechada_em: '2026-08-05 04:02:00',
    }), { respostaEm: LOCAL, agora: LOCAL }, 7)
    return { contagem: r.contagem, membros: r.membros, tempo: r.tempo }
  })

  cenario('a_faixa_do_painel_tambem_diz_quem_ficou_fora', () => {
    // O MESMO fato, na outra superfície. A faixa do painel chama
    // `resumoCorrida` SEM `qtdCadastro` (ela não tem o cadastro em mãos), e
    // sem a segunda fonte ela calava justamente sobre "2 de 2 · concluída" —
    // o card contando a subtração e a faixa não, na mesma tela e sobre o mesmo
    // ciclo. `membros_inativos` viaja no payload da corrida e responde.
    const c = corrida({
      status: 'CONCLUIDA', saude: null, membros_ok: 2, membros_total: 2,
      membros_vivos: 0, membros_inativos: 5,
      fechada_em: '2026-08-05 04:02:00',
    })
    const t = { respostaEm: LOCAL, agora: LOCAL }
    return { faixa: S.resumoCorrida(c, t).membros,          // sem qtdCadastro
             card: S.resumoCorrida(c, t, 7).membros }       // com qtdCadastro
  })

  cenario('corrida_recem_aberta_nao_acusa_ninguem', () => {
    // 01:10:30 — a corrida abriu e NENHUM pipeline tem linha ainda. Todos
    // caem em `nao_partiu`. O chip vermelho já não sai do servidor
    // (`membros_travados = 0`); aqui se prova a outra metade: o card não
    // escolhe um culpado por ordem alfabética enquanto o ciclo está ABERTO.
    const t = { respostaEm: LOCAL, agora: LOCAL }
    const nova = S.resumoCorrida(corrida({
      membros_ok: 0, membros_vivos: 0, membros_travados: 0, decorrido_min: 0,
      pendentes: ['A', 'B', 'C'].map(p => pendente(p, 'nao_partiu')),
    }), t)
    // ...e, fechada a corrida, o mesmo dado vira VEREDITO e volta a aparecer
    const fechada = S.resumoCorrida(corrida({
      status: 'FALHA', saude: null, membros_ok: 0, membros_vivos: 0,
      membros_travados: 0, fechada_em: '2026-08-05 04:02:00',
      pendentes: ['A', 'B', 'C'].map(p => pendente(p, 'nao_partiu')),
    }), t)
    return { aberta_culpado: nova.culpado, aberta_travados: nova.travados,
             aberta_rotulo: nova.estilo.rotulo, aberta_faixa: nova.faixa,
             fechada_culpado: fechada.culpado }
  })

  // ══ F4+/3 — o travado FORA do que a barra preenche ═══════════════════════
  cenario('travado_e_chip_e_nao_comprimento', () => {
    const r = S.resumoCorrida(corrida({
      membros_ok: 3, membros_total: 7, membros_vivos: 2, membros_travados: 2,
      saude: 'COM_FALHA',
      pendentes: [pendente('CARGA_A', 'falhou', '2026-08-05 03:00:00'),
                  pendente('CARGA_Z', 'nao_liberou', '2026-08-05 03:10:00')],
    }), { respostaEm: LOCAL, agora: LOCAL }, 7)
    return { contagem: r.contagem, travados: r.travados, culpado: r.culpado,
             titulo: r.titulo }
  })

  // ══ Decisão 57 — interrompida congela; SEM_TRABALHO não tem barra ════════
  cenario('desfechos_que_nao_sao_progresso', () => {
    const base = { saude: null, aberta_em: '2026-08-05 01:10:00',
                   fechada_em: '2026-08-05 04:02:00', membros_ok: 4,
                   membros_total: 7, membros_vivos: 0, membros_travados: 3 }
    const r = s => S.resumoCorrida(corrida(Object.assign({ status: s }, base)),
                                   { respostaEm: LOCAL, agora: LOCAL })
    const sem = S.resumoCorrida(corrida({
      status: 'SEM_TRABALHO', saude: null, membros_ok: 0, membros_total: 7,
      membros_vivos: 0, membros_dispensados: 7,
      fechada_em: '2026-08-05 01:12:00',
    }), { respostaEm: LOCAL, agora: LOCAL })
    return {
      EXPIRADA: { contagem: r('EXPIRADA').contagem, tempo: r('EXPIRADA').tempo,
                  rotulo: r('EXPIRADA').estilo.rotulo },
      ABORTADA: { contagem: r('ABORTADA').contagem },
      CANCELADA: { contagem: r('CANCELADA').contagem },
      CONCLUIDA: { contagem: r('CONCLUIDA').contagem,
                   rotulo: r('CONCLUIDA').estilo.rotulo },
      SEM_TRABALHO: { contagem: sem.contagem, membros: sem.membros,
                      rotulo: sem.estilo.rotulo, faixa: sem.faixa },
    }
  })

  // ══ Decisão 41 — a degradação, dos dois jeitos ═══════════════════════════
  cenario('api_velha_sem_o_bloco_corrida', () => {
    // O que o card faz quando o payload não tem a chave: o guard do
    // `MalhaCard` é `malha.corrida ?? null`, e `resumoCorrida` NÃO é chamada.
    // Aqui se prova o outro lado — que chamá-la com o bloco AUSENTE seria o
    // único jeito de quebrar, e que o front nunca faz isso (o teste do
    // contrato do fonte, em pytest, guarda o `??`).
    const malha = { malha_name: 'M1', ultima_execucao: { pipeline: 'CARGA_B',
                                                         status: 'SUCESSO' } }
    const resumo = malha.corrida ? S.resumoCorrida(malha.corrida,
                                                   { respostaEm: LOCAL, agora: LOCAL })
      : null
    return { resumo, tem_fallback: !!malha.ultima_execucao }
  })

  cenario('corrida_sem_contadores_nao_quebra_a_tela', () => {
    // O payload do lock timeout na consulta (B): o ESTADO sai, os contadores
    // vêm `null`. `null` é "não consegui apurar", e é diferente de `0`, que a
    // tela desenharia como medida.
    const r = S.resumoCorrida(corrida({
      status: 'FALHA', saude: null, membros_total: null, membros_ok: null,
      membros_vivos: null, membros_dispensados: null, membros_travados: null,
      membros_fora_do_odate: null, membros_inativos: null, pendentes: [],
      decorrido_min: null, ultimo_movimento_em: null, sem_sinal_min: null,
      fechada_em: '2026-08-05 04:02:00',
    }), { respostaEm: LOCAL, agora: LOCAL })
    return { rotulo: r.estilo.rotulo, contagem: r.contagem, membros: r.membros,
             travados: r.travados, vivos: r.vivos, tempo: r.tempo,
             titulo: r.titulo }
  })

  // ══ §9.4 — um formato de tempo por posição ═══════════════════════════════
  cenario('tempo_relativo_com_a_corrida_aberta', () => {
    const r = S.resumoCorrida(corrida(),
                              { respostaEm: LOCAL, agora: LOCAL + 61_000 })
    return { tempo: r.tempo }
  })

  cenario('sem_progresso_conta_pelo_relogio_do_banco', () => {
    const r = S.resumoCorrida(corrida({
      saude: 'SEM_PROGRESSO', sem_sinal_min: 40, membros_vivos: 1,
    }), { respostaEm: LOCAL, agora: LOCAL })
    return { rotulo: r.estilo.rotulo, faixa: r.faixa }
  })

  // ══ a navegação entre duas corridas do MESMO ODATE ═══════════════════════
  cenario('duas_corridas_do_mesmo_dia_tem_rotulos_distintos', () => {
    const cab = (over) => Object.assign({
      id: 1, malha_name: 'M1', data_referencia: '2026-08-05', sequencia: 1,
      status: 'FALHA', aberta_em: '2026-08-05 01:10:00',
      fechada_em: '2026-08-05 04:02:00', fechada_por: 'guardia',
      origem: 'inicio', aberta_por: 'inicio:#1', ancora_pipeline: null,
      modo_fechamento: 'falha', teto_em: null, tentativas: 1,
      reaberta_em: null, motivo: null,
    }, over)
    return {
      primeira: S.rotuloCorrida(cab({})),
      segunda: S.rotuloCorrida(cab({ id: 2, sequencia: 2, status: 'CONCLUIDA',
                                     aberta_em: '2026-08-05 05:00:00' })),
      identidades: [
        S.resumoCorrida(corrida({}), { respostaEm: LOCAL, agora: LOCAL }).identidade,
        S.resumoCorrida(corrida({ id: 2, sequencia: 2 }),
                        { respostaEm: LOCAL, agora: LOCAL }).identidade,
      ],
    }
  })

  // ══ Decisão 74 — nenhum nome de máquina chega à tela ═════════════════════
  cenario('quem_fez_traduz_o_formato_de_maquina', () => ({
    manual: S.quemFez('manual:C123456'),
    inicio: S.quemFez('inicio:#12'),
    guardia: S.quemFez('guardia'),
    no_fim: S.quemFez('no_fim'),
    implicita: S.quemFez('implicita:CARGA_A'),
    vazio: S.quemFez(null),
    desconhecido: S.quemFez('coisa_nova:#3'),
  }))

  cenario('cancelamento_e_auditavel', () => {
    const r = S.resumoCorrida(corrida({
      status: 'CANCELADA', saude: null, fechada_em: '2026-08-05 04:02:00',
      fechada_por: 'manual:C123456',
      motivo: 'encerrada por C123456: fonte indisponível, refazemos amanhã',
      membros_ok: 4, membros_total: 7, membros_vivos: 0, membros_travados: 3,
    }), { respostaEm: LOCAL, agora: LOCAL })
    return { encerramento: r.encerramento, motivo: r.motivo,
             contagem: r.contagem, faixa: r.faixa }
  })

  cenario('fora_do_odate_e_nominal_e_ambar', () => {
    const r = S.resumoCorrida(corrida({ membros_fora_do_odate: 3 }),
                              { respostaEm: LOCAL, agora: LOCAL })
    return { foraDoOdate: r.foraDoOdate }
  })

  // ══ §9.9 — o canvas: "esperando" deixa de ser igual a "ninguém pediu" ════
  cenario('estado_do_pipeline_no_canvas', () => {
    const out = {}
    for (const s of ['SUCESSO', 'EXECUTANDO', 'AGUARDANDO_DEPENDENCIA', 'FALHA',
                     'NAO_LIBEROU', 'PULADO', null]) {
      out[String(s)] = F.estadoDoPipeline(s)
    }
    return out
  })

  cenario('a_linha_que_espera_nao_anda', () => {
    const esperando = F.decorarAresta('esperando', false)
    const ativo = F.decorarAresta('ativo', false)
    return {
      esperando: { animated: esperando.animated, style: esperando.style },
      ativo: { animated: ativo.animated, style: ativo.style },
      escuro: F.decorarAresta('esperando', true).cor,
      // Predecessor pronto + destino esperando: o trecho NÃO pode ser o azul
      // animado de "avançando" — do outro lado há um pipeline parado.
      aresta_pronta_para_quem_espera: F.estadoDaAresta('concluido', 'esperando'),
      aresta_pronta_para_quem_nao_partiu: F.estadoDaAresta('concluido', null),
      aresta_bloqueada: F.estadoDaAresta('concluido', 'bloqueado'),
      rotulos: F.ROTULO_FLUXO,
    }
  })

  process.stdout.write(JSON.stringify(saida))
  // A bancada roda a cada `pytest`: sem isto, cada execução deixaria uma
  // cópia dos módulos em /tmp para sempre.
  fs.rmSync(destino, { recursive: true, force: true })
}

main().catch(e => {
  process.stderr.write(String((e && e.stack) || e))
  process.exit(1)
})
