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
}

export type MensagemTerminal =
  | { id: string; papel: 'usuario'; texto: string }
  | { id: string; papel: 'assistente'; texto: string }
  | { id: string; papel: 'comando'; comando: ComandoTerminal }

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

/** Frase do rastro depois de decidido: "executado por 123 às 14:05". */
export function rastro(cmd: ComandoTerminal): string {
  if (cmd.estado === 'recusado') return cmd.decidido_por ? `recusado por ${cmd.decidido_por}` : 'recusado'
  if (cmd.classe === 'escrita' && cmd.decidido_por && (cmd.estado === 'executado' || cmd.estado === 'falhou')) {
    const hora = cmd.decidido_em ? ` às ${cmd.decidido_em.slice(11, 16)}` : ''
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
