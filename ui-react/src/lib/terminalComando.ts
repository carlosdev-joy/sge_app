/**
 * Lógica pura do agente Terminal (spec docs/spec-agente-terminal.md, F1).
 *
 * Sem React e sem rede: tudo aqui roda na bancada `tests/js/agente_terminal_harness.cjs`.
 * O contrato (`ComandoTerminal`) é o que a F2–F4 do backend vai devolver; na F1 ele é
 * alimentado por `terminalSimulado.ts`.
 */

export type ClasseComando = 'leitura' | 'escrita' | 'proibido'

export type EstadoComando =
  | 'proposto'    // escrita aguardando Confirmar/Recusar
  | 'executando'
  | 'executado'
  | 'falhou'
  | 'recusado'
  | 'expirado'
  | 'bloqueado'   // classe "proibido": nunca roda

export interface ComandoTerminal {
  cmd_id: string
  comando: string
  servidor: string
  classe: ClasseComando
  estado: EstadoComando
  /** Por que o Claude quer rodar (aparece no card de confirmação). */
  motivo?: string | null
  saida?: string | null
  codigo_saida?: number | null
  duracao_ms?: number | null
  /** A saída passou do teto da API e foi cortada no servidor. */
  truncada?: boolean
  /** ISO — só em `proposto`. */
  expira_em?: string | null
  /** Quem decidiu (confirmou/recusou) e quando, para o rastro "executado por". */
  decidido_por?: string | null
  decidido_em?: string | null
  /** Interrompido pelo limite de tempo do servidor. */
  interrompido?: boolean
  /** Avisos do Orquestra sobre a execução (ex.: busca recursiva omite arquivos sensíveis). */
  notas?: string[]
  /** Hash do texto que o usuário vê — vai de volta na confirmação (prova que ele viu ESTE comando). */
  hash?: string
}

export type MensagemTerminal =
  | { id: string; papel: 'usuario'; texto: string }
  | { id: string; papel: 'assistente'; texto: string }
  | { id: string; papel: 'comando'; comando: ComandoTerminal }
  /** Consulta a DataStage/banco feita pelo agente nesta resposta (sem saída: o que ela devolveu está no texto). */
  | { id: string; papel: 'nota'; rotulo: string; detalhe?: string; sql?: string }

export const MAX_LINHAS_SAIDA = 40
export const MAX_ENTRADA = 4000

export const ROTULO_CLASSE: Record<ClasseComando, string> = {
  leitura: 'leitura',
  escrita: 'escrita',
  proibido: 'proibido',
}

export const ROTULO_ESTADO: Record<EstadoComando, string> = {
  proposto: 'aguardando confirmação',
  executando: 'executando',
  executado: 'executado',
  falhou: 'falhou',
  recusado: 'recusado',
  expirado: 'expirado',
  bloqueado: 'bloqueado',
}

/** Segundos até expirar (0 se já passou ou sem prazo). */
export function segundosRestantes(expiraEm: string | null | undefined, agora: Date): number {
  if (!expiraEm) return 0
  const alvo = Date.parse(expiraEm)
  if (Number.isNaN(alvo)) return 0
  return Math.max(0, Math.ceil((alvo - agora.getTime()) / 1000))
}

/** O estado que a tela mostra: uma proposta vencida é "expirado" mesmo antes de o servidor dizer. */
export function estadoEfetivo(cmd: ComandoTerminal, agora: Date): EstadoComando {
  if (cmd.estado === 'proposto' && segundosRestantes(cmd.expira_em, agora) <= 0) return 'expirado'
  return cmd.estado
}

/** Os botões Confirmar/Recusar só existem para quem pode escrever e numa proposta viva. */
export function podeDecidir(cmd: ComandoTerminal, agora: Date, podeEscrever: boolean): boolean {
  return podeEscrever && cmd.classe === 'escrita' && estadoEfetivo(cmd, agora) === 'proposto'
}

/** "1:45" — contagem regressiva do card de confirmação. */
export function relogio(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** Corta a saída em N linhas; `ocultas` diz quantas ficaram de fora ("Mostrar tudo"). */
export function limitarSaida(saida: string | null | undefined, maxLinhas = MAX_LINHAS_SAIDA): {
  texto: string
  ocultas: number
} {
  if (!saida) return { texto: '', ocultas: 0 }
  const linhas = saida.replace(/\r\n/g, '\n').replace(/\n$/, '').split('\n')
  if (linhas.length <= maxLinhas) return { texto: linhas.join('\n'), ocultas: 0 }
  return { texto: linhas.slice(0, maxLinhas).join('\n'), ocultas: linhas.length - maxLinhas }
}

/** Troca o comando de mesmo `cmd_id` (a decisão/execução chega depois da proposta). */
export function aplicarComando(mensagens: MensagemTerminal[], cmd: ComandoTerminal): MensagemTerminal[] {
  let achou = false
  const novas = mensagens.map(m => {
    if (m.papel === 'comando' && m.comando.cmd_id === cmd.cmd_id) {
      achou = true
      return { ...m, comando: cmd }
    }
    return m
  })
  return achou ? novas : [...novas, { id: `c-${cmd.cmd_id}`, papel: 'comando', comando: cmd }]
}

/** Troca SÓ se o comando estiver na lista — nunca acrescenta. É o que a decisão/reidratação usa: uma resposta que chega
 *  depois de "Nova conversa" não pode fazer um card (talvez confirmável) aparecer na conversa nova. */
export function substituirComando(mensagens: MensagemTerminal[], cmd: ComandoTerminal): MensagemTerminal[] {
  let achou = false
  const novas = mensagens.map(m => {
    if (m.papel === 'comando' && m.comando.cmd_id === cmd.cmd_id) {
      achou = true
      return { ...m, comando: cmd }
    }
    return m
  })
  return achou ? novas : mensagens
}

/** Frase do rastro depois de decidido: "executado por 123 às 14:05". */
export function rastro(cmd: ComandoTerminal): string {
  if (cmd.estado === 'recusado') return cmd.decidido_por ? `recusado por ${cmd.decidido_por}` : 'recusado'
  if (cmd.classe === 'escrita' && cmd.decidido_por && (cmd.estado === 'executado' || cmd.estado === 'falhou')) {
    const d = cmd.decidido_em ? new Date(cmd.decidido_em) : null
    const hora = d && !Number.isNaN(d.getTime()) ? ` às ${d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}` : ''
    return `${cmd.estado} por ${cmd.decidido_por}${hora}`
  }
  return ROTULO_ESTADO[cmd.estado]
}

/** Linha de duração curta: 850 ms → "0,9 s". */
export function duracaoCurta(ms: number | null | undefined): string {
  if (ms == null || ms < 0) return ''
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1).replace('.', ',')} s`
}

/** O texto digitado serve para enviar? (vazio, só espaços ou acima do teto não.) */
export function entradaValida(texto: string): boolean {
  const t = texto.trim()
  return t.length > 0 && texto.length <= MAX_ENTRADA
}


// ── F5: a resposta REAL da API vira mensagens do terminal ─────────────────────────────────────────────────────────

/** Bloco de comando que a API manda no artefato (`comando_executado`): já redigido e cortado. */
export interface BlocoComandoApi {
  cmd_id: string; comando: string; servidor: string; classe: ClasseComando; estado: EstadoComando
  saida?: string | null; codigo_saida?: number | null; duracao_ms?: number | null
  truncada?: boolean; interrompido?: boolean; motivo?: string | null; notas?: string[]
}
/** Proposta de escrita (`proposta_comando`): `segundos_restantes` é do MOMENTO da resposta. */
export interface PropostaComandoApi {
  cmd_id: string; hash: string; comando: string; servidor: string; motivo?: string | null; segundos_restantes?: number | null
}
export interface ArtefatoTerminalApi {
  ferramenta: string
  args?: Record<string, unknown>
  comando_executado?: BlocoComandoApi
  proposta_comando?: PropostaComandoApi
  banco?: { conexao?: string; banco?: string; linhas?: number; recusada?: string; erro?: string }
  recusada?: string
  falhou?: string
  repetida?: boolean
}

export function comandoDoBloco(b: BlocoComandoApi): ComandoTerminal {
  return { cmd_id: b.cmd_id, comando: b.comando, servidor: b.servidor, classe: b.classe, estado: b.estado,
           motivo: b.motivo ?? null, saida: b.saida ?? null, codigo_saida: b.codigo_saida ?? null, duracao_ms: b.duracao_ms ?? null,
           truncada: !!b.truncada, interrompido: !!b.interrompido, notas: b.notas ?? [] }
}

/** O prazo vem em SEGUNDOS (relógio do servidor): vira `expira_em` no relógio DESTE navegador — imune a relógio adiantado. */
export function comandoDaProposta(p: PropostaComandoApi, agora: Date): ComandoTerminal {
  const s = typeof p.segundos_restantes === 'number' && Number.isFinite(p.segundos_restantes) ? Math.max(0, p.segundos_restantes) : 0
  return { cmd_id: p.cmd_id, comando: p.comando, servidor: p.servidor, classe: 'escrita', estado: 'proposto',
           motivo: p.motivo ?? null, hash: p.hash, expira_em: new Date(agora.getTime() + s * 1000).toISOString() }
}

function texto(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

/** Nota de uma consulta feita pelo agente que não é comando de shell (DataStage ao vivo, banco). */
function notaDoArtefato(a: ArtefatoTerminalApi): { rotulo: string; detalhe?: string; sql?: string } | null {
  const args = a.args ?? {}
  if (a.recusada || a.repetida) return null  // não rodou: o texto do assistente explica
  if (a.ferramenta === 'dsjob') {
    const partes = [texto(args.comando), texto(args.job_name)].filter(Boolean).join(' ')
    return { rotulo: 'DataStage ao vivo', detalhe: `dsjob ${partes}`.trim() + (a.falhou ? ' — falhou' : '') }
  }
  if (a.ferramenta === 'banco_consulta' || a.ferramenta === 'banco_estrutura') {
    const onde = [a.banco?.conexao ?? texto(args.conexao), a.banco?.banco ?? texto(args.banco)].filter(Boolean).join('/')
    const linhas = typeof a.banco?.linhas === 'number' ? ` · ${a.banco.linhas} linha(s)` : ''
    return { rotulo: a.ferramenta === 'banco_consulta' ? 'Consulta ao banco' : 'Estrutura do banco',
             detalhe: `${onde}${linhas}${a.banco?.erro || a.banco?.recusada ? ' — não executou' : ''}`,
             sql: texto(args.sql) || undefined }
  }
  return null
}

/** Mensagens de UMA resposta: os blocos (comandos, propostas, consultas) na ordem em que rodaram e, por último, o texto. */
export function mensagensDaResposta(r: { texto: string; artefatos?: ArtefatoTerminalApi[] }, agora: Date,
                                    novoId: () => string): MensagemTerminal[] {
  const saida: MensagemTerminal[] = []
  for (const a of r.artefatos ?? []) {
    if (a.ferramenta === 'servidor_exec') {
      if (a.comando_executado) saida.push({ id: novoId(), papel: 'comando', comando: comandoDoBloco(a.comando_executado) })
      else if (a.proposta_comando) saida.push({ id: novoId(), papel: 'comando', comando: comandoDaProposta(a.proposta_comando, agora) })
      continue
    }
    const nota = notaDoArtefato(a)
    if (nota) saida.push({ id: novoId(), papel: 'nota', ...nota })
  }
  if (r.texto?.trim()) saida.push({ id: novoId(), papel: 'assistente', texto: r.texto })
  return saida
}

/** Estado do comando lido do servidor (`GET /agentes/terminal/comandos/{id}`) aplicado ao bloco da tela. */
export interface ComandoApi {
  cmd_id: string; comando: string; servidor: string; hash?: string; classe: ClasseComando; estado: EstadoComando
  motivo?: string | null; segundos_restantes?: number | null; decidido_por?: string | null; decidido_em?: string | null
  executado_em?: string | null; codigo_saida?: number | null; duracao_ms?: number | null; saida_resumo?: string | null
}
export function reidratar(atual: ComandoTerminal, c: ComandoApi, agora: Date): ComandoTerminal {
  const base: ComandoTerminal = { ...atual, estado: c.estado, decidido_por: c.decidido_por ?? atual.decidido_por ?? null,
                                  decidido_em: c.decidido_em ?? atual.decidido_em ?? null,
                                  codigo_saida: c.codigo_saida ?? atual.codigo_saida ?? null, duracao_ms: c.duracao_ms ?? atual.duracao_ms ?? null }
  if (c.saida_resumo != null) base.saida = c.saida_resumo
  if (c.estado === 'proposto') {
    const s = typeof c.segundos_restantes === 'number' ? Math.max(0, c.segundos_restantes) : 0
    base.expira_em = new Date(agora.getTime() + s * 1000).toISOString()
    if (c.hash) base.hash = c.hash
  } else {
    base.expira_em = null
  }
  return base
}

/** Mensagem para o usuário depois de uma confirmação/recusa recusada pela API (`detail.code`). `reidratar`: buscar o estado de novo. */
export function textoDoErroDeDecisao(code: string | null | undefined): { texto: string; reidratar: boolean } {
  switch (code) {
    case 'hash_diferente': return { texto: 'O comando mudou desde que você o viu. Peça a proposta de novo.', reidratar: true }
    case 'expirada': return { texto: 'A proposta expirou — nada foi executado. Peça o comando de novo.', reidratar: true }
    case 'ja_decidido': return { texto: 'Este comando já foi decidido.', reidratar: true }
    case 'servidor_ocupado_ou_indisponivel':
      return { texto: 'O servidor está ocupado ou indisponível — o comando NÃO foi executado. Você pode confirmar de novo.', reidratar: true }
    case 'falha_na_execucao': return { texto: 'A execução falhou no meio — o comando PODE ter sido executado. Confira antes de repetir.', reidratar: true }
    case 'agora_proibido': return { texto: 'Este comando passou a ser proibido e não foi executado.', reidratar: true }
    case 'agente_escrita_desligada': return { texto: 'A execução de comandos que alteram o servidor está desligada pelo administrador.', reidratar: false }
    case 'agente_escrita_nao_liberada': return { texto: 'Você não tem permissão para executar comandos que alteram o servidor.', reidratar: false }
    case 'comando_inexistente': return { texto: 'Comando não encontrado.', reidratar: false }
    default: return { texto: 'Não foi possível concluir a decisão agora. Tente de novo.', reidratar: true }
  }
}

/** Quantas linhas o comando tem (o card avisa quando é mais de uma: nada pode ficar escondido). */
export function linhasDoComando(comando: string): number {
  return (comando || '').split('\n').length
}
