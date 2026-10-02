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

/** `{coluna:…}` contra o grafo conhecido — mesma leitura do operador: o
 *  qualificador é separado no ÚLTIMO ponto (`NO.ALIAS`); sem ponto, é a forma
 *  curta, que só resolve com UM SQL ligado. A tela não sabe quantas linhas o
 *  SELECT devolve: isso fica no log da corrida. */
export function avisosColunaEmail(texto: string, sqlNames: readonly string[]): string[] {
  const origens = new Set(sqlNames)
  const avisos: string[] = []
  if (texto.includes('{coluna}')) {
    avisos.push('{coluna} precisa do nome da coluna: use {coluna:ALIAS}, com o alias (AS) do SELECT.')
  }
  const citados = new Set([...texto.matchAll(/\{coluna:([A-Za-z0-9_.-]{1,128})\}/g)].map(match => match[1]))
  for (const qualificador of citados) {
    const ponto = qualificador.lastIndexOf('.')
    const no = ponto >= 0 ? qualificador.slice(0, ponto) : ''
    const alias = qualificador.slice(ponto + 1)
    if (ponto === 0) {
      avisos.push(`{coluna:${qualificador}}: falta o nome do nó antes do ponto — use {coluna:${alias}} ou {coluna:NOME_DO_NO.${alias}}.`)
    } else if (!/^[A-Za-z0-9_]{1,64}$/.test(alias)) {
      avisos.push(`{coluna:${qualificador}}: "${alias}" não é um alias válido — use letras sem acento, números ou sublinhado.`)
    } else if (ponto < 0 && origens.size === 0) {
      avisos.push(`{coluna:${qualificador}}: não há SQL ligado diretamente a este e-mail. A coluna não atravessa Decisão ou outros nós.`)
    } else if (ponto < 0 && origens.size > 1) {
      avisos.push(`{coluna:${qualificador}}: há mais de um SQL ligado diretamente; o marcador sai literal. Use {coluna:NOME_DO_NO.${alias}}.`)
    } else if (ponto >= 0 && !origens.has(no)) {
      avisos.push(`{coluna:${qualificador}}: não há SQL chamado "${no}" ligado diretamente a este e-mail. Confira o nome e as ligações do fluxo.`)
    }
  }
  // Mesma limitação da tabela: a coluna sai do mesmo resultado publicado.
  const usados = [...citados].map(q => (q.includes('.') ? q.slice(0, q.lastIndexOf('.')) : null))
  for (const nome of origens) {
    if ((usados.includes(nome) || (usados.includes(null) && origens.size === 1))
      && (nome.startsWith('log_end_') || nome.startsWith('log_start_'))) {
      avisos.push(`O envio atual pode não localizar as colunas de ${nome} por causa do prefixo log_end_/log_start_. Use um nome SQL sem esses prefixos e republique o fluxo.`)
    }
  }
  return avisos
}
