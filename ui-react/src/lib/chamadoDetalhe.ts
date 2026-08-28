// O conteúdo de um chamado: descrição, notas do histórico e anexos.
//
// Alimenta `GET /chamados/{sys_id}/detalhe`, que existe desde a F2 e até aqui
// não tinha tela — a rota respondia e ninguém perguntava.

export interface NotaChamado {
  sys_id_nota: string
  autor: string | null
  autor_email: string | null
  criado_em: string | null
  texto: string | null
  /** 'work_notes' (interna) | 'comments' (visível ao solicitante). */
  tipo: string | null
  /** false = a nota veio de uma TAREFA do chamado, não dele mesmo. */
  origem_propria?: boolean
  /** O número da task de onde a nota veio. Nulo quando é do próprio chamado. */
  origem_numero?: string | null
}

export interface AnexoChamado {
  sys_id_anexo: string
  nome_arquivo: string | null
  mime_type: string | null
  tamanho_bytes: number | null
  /** Caminho no NOSSO backend — o arquivo não vem do ServiceNow direto. */
  url_proxy: string
  criado_em: string | null
}

export interface ChamadoDoDetalhe {
  sys_id: string
  numero: string
  tipo: string
  titulo: string | null
  descricao: string | null
  estado_kanban: string
  estado_origem: string | null
  atribuido_a: string | null
  atribuido_a_email: string | null
  /** Quem PEDIU — `requested_for` no RITM, `caller_id` no incidente. */
  demandante?: string | null
  grupo: string | null
  aberto_em: string | null
  url: string | null
  tem_anexo: boolean | null
  sla_vencido: boolean | null
  prazo: string | null
}

export interface RespostaDetalhe {
  chamado: ChamadoDoDetalhe | null
  notas: NotaChamado[]
  anexos: AnexoChamado[]
  /** true = a consulta falhou. Diferente de "não há notas". */
  migration_ausente: boolean
}

/**
 * Data e hora de uma nota, em dd/mm/aaaa hh:mm.
 *
 * Leitura TEXTUAL, pelo mesmo motivo de `dataDoPrazo`: a API manda
 * "2026-08-28 11:43:30", que o `new Date` de alguns navegadores lê como UTC e
 * devolve o dia anterior à noite — e `toLocaleString` muda de formato conforme
 * a máquina de quem abre a tela. Uma nota datada errado no histórico é pior
 * que uma nota sem data: ela afirma.
 */
export function dataHoraDaNota(valor: string | null | undefined): string {
  if (!valor) return '—'
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(valor.trim())
  if (m) return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}`
  const so_data = /^(\d{4})-(\d{2})-(\d{2})/.exec(valor.trim())
  if (so_data) return `${so_data[3]}/${so_data[2]}/${so_data[1]}`
  // Formato desconhecido volta CRU: melhor mostrar o que veio do que um
  // "Invalid Date" que faz o operador achar que o chamado está corrompido.
  return valor
}

/**
 * Tamanho do anexo em unidade legível.
 *
 * `0` devolve "—" junto com null/undefined: o ServiceNow manda 0 quando não
 * sabe o tamanho, e "0 B" faria parecer arquivo vazio — que é outra coisa, e
 * levaria alguém a não baixar um anexo que existe.
 */
export function tamanhoLegivel(bytes: number | null | undefined): string {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const ROTULO_NOTA: Record<string, string> = {
  work_notes: 'nota interna',
  comments: 'comentário ao solicitante',
}

/**
 * O tipo da nota em palavras.
 *
 * A distinção importa e não é decorativa: `work_notes` fica entre a equipe e
 * `comments` o solicitante lê. Mostrar as duas iguais faz alguém escrever para
 * dentro achando que escreveu para fora — ou o contrário, que é pior.
 */
export function rotuloDaNota(tipo: string | null | undefined): string {
  return ROTULO_NOTA[(tipo || '').trim()] || (tipo || 'nota')
}
