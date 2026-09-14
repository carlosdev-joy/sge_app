import { EMAIL_PLACEHOLDERS } from '../components/etapas/fluxoTypes'
import { VALORES_EXEMPLO } from '../components/etapas/previaEmailDados'

export type EmailPlaceholderCampo = 'assunto' | 'corpo' | 'anexo'

const DESCRICOES: Record<string, string> = {
  pipeline: 'Nome do pipeline em execução.',
  job: 'Nome do nó de e-mail.',
  data: 'Data e hora do envio.',
  odate: 'Data de referência da execução no formato AAAAMMDD.',
  linhas: 'Total de linhas de saída informado pelos jobs imediatamente anteriores; não conta as linhas da tabela SQL.',
  status: 'Status geral da execução.',
  inicio: 'Data e hora de início da execução.',
  duracao: 'Tempo decorrido desde o início da execução.',
  execution_id: 'Identificador da execução.',
}

/** Mesmo alfabeto e limite do qualificador em dags/utils/email_operator.py. */
export function nomeSqlParaPlaceholderValido(nome: string): boolean {
  return /^[A-Za-z0-9_.-]{1,128}$/.test(nome)
}

export function emailPlaceholderCatalogo(campo: EmailPlaceholderCampo) {
  // data/inicio incluem barras, recusadas pelo caminho_do_anexo após interpolar.
  return EMAIL_PLACEHOLDERS.filter(nome => campo !== 'anexo' || !['tabela', 'data', 'inicio'].includes(nome)).map(nome => ({
    nome,
    descricao: nome === 'tabela'
      ? campo === 'assunto'
        ? 'Resumo do resultado do SQL imediatamente anterior. Com vários SQL, escolha a tabela pelo nome do nó.'
        : 'Resultado do SQL imediatamente anterior, em HTML ou texto conforme o corpo. Com vários SQL, escolha a tabela pelo nome do nó.'
      : DESCRICOES[nome],
    exemplo: nome === 'tabela'
      ? campo === 'assunto' ? '2 linhas × 2 colunas' : 'Tabela com colunas e linhas do SELECT'
      : VALORES_EXEMPLO[nome],
  }))
}

export function inserirEmailPlaceholder(value: string, nome: string, start: number, end: number) {
  const token = `{${nome}}`
  return { value: value.slice(0, start) + token + value.slice(end), cursor: start + token.length }
}
