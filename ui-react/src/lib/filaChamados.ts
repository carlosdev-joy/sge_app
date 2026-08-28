// Como a fila de chamados vira uma fila de TRABALHOS.
//
// Todo RITM do catálogo gera uma sc_task, e o espelho traz as duas como linhas
// irmãs. Medido no dev em 2026-08-28: 95 registros para 59 trabalhos. O card
// passa a ser o pedido, e a tarefa vira linha dentro dele — sai da contagem
// sem sair da vista.
//
// Vive fora do componente porque a parte que importa é a RECUSA, e recusa não
// se vê na tela: o que se vê é um card a menos.

export interface ItemFila {
  sys_id: string
  tipo: string
  pai_sys_id: string | null
}

export interface FilaSeparada<T extends ItemFila> {
  /** O que vira card. */
  cards: T[]
  /** As filhas, indexadas pelo sys_id do pai. */
  filhasPorPai: Map<string, T[]>
}

export function separarFila<T extends ItemFila>(todos: T[]): FilaSeparada<T> {
  const filhasPorPai = new Map<string, T[]>()
  const cards: T[] = []

  for (const c of todos) {
    // Só sai da fila a task que TEM pai.
    //
    // A ÓRFÃ CONTINUA CARD. A regra da instância diz que ela não deveria
    // existir; se aparecer, é sintoma — do filtro de grupo, ou de a task ter
    // chegado antes do pai — e esconder o sintoma é o oposto do que esta tela
    // existe para fazer. Some da fila é diferente de sumir do sistema.
    //
    // `pai_sys_id` vazio conta como ausente: o sync grava '' quando o campo
    // não vem da API. Tratar '' como valor faria TODO chamado ter pai, e a
    // fila inteira desapareceria — sem erro nenhum.
    if (c.tipo === 'task' && c.pai_sys_id) {
      const lista = filhasPorPai.get(c.pai_sys_id)
      if (lista) lista.push(c)
      else filhasPorPai.set(c.pai_sys_id, [c])
    } else {
      cards.push(c)
    }
  }

  return { cards, filhasPorPai }
}
