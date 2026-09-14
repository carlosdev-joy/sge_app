/** O editor publica node.id como job_name; títulos não identificam o SQL no envio. */
export function sqlDiretosDoEmail(
  emailId: string,
  nodes: readonly { id: string; type?: string }[],
  edges: readonly { source: string; target: string; data?: { branch?: unknown } }[],
): string[] {
  const sqlIds = new Set(nodes.filter(node => node.type === 'sql').map(node => node.id))
  // Só vizinhos imediatos, na ordem das ligações; não atravessa decisões.
  return [...new Set(edges
    .filter(edge => !edge.data?.branch && edge.target === emailId && edge.source !== emailId && sqlIds.has(edge.source))
    .map(edge => edge.source))]
}

/** Analisa o grafo conhecido, sem garantir que o SQL publicará resultado na execução. */
export function avisosTabelaEmail(texto: string, sqlNames: readonly string[]): string[] {
  const origens = new Set(sqlNames)
  const avisos: string[] = []
  if (texto.includes('{tabela}')) {
    if (origens.size === 0) {
      avisos.push('{tabela}: não há SQL ligado diretamente a este e-mail. A tabela não atravessa Decisão ou outros nós.')
    } else if (origens.size > 1) {
      avisos.push('{tabela}: há mais de um SQL ligado diretamente; o resultado pode ficar ambíguo. Use {tabela:NOME_DO_NO}.')
    }
  }
  // Mesmo alfabeto e sensibilidade a maiúsculas do operador de e-mail.
  const citados = new Set([...texto.matchAll(/\{tabela:([A-Za-z0-9_.-]{1,128})\}/g)].map(match => match[1]))
  for (const nome of citados) {
    if (!origens.has(nome)) {
      avisos.push(`{tabela:${nome}}: não há SQL com esse nome exato ligado diretamente a este e-mail. Confira o nome e as ligações do fluxo.`)
    }
  }
  for (const nome of origens) {
    if ((texto.includes('{tabela}') || citados.has(nome))
      && (nome.startsWith('log_end_') || nome.startsWith('log_start_'))) {
      avisos.push(`O envio atual pode não localizar a tabela de ${nome} por causa do prefixo log_end_/log_start_. Use um nome SQL sem esses prefixos e republique o fluxo.`)
    }
  }
  return avisos
}
