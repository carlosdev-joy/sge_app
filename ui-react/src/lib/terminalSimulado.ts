/**
 * Respostas SIMULADAS do agente Terminal (F1 da spec docs/spec-agente-terminal.md).
 *
 * Nada aqui fala com servidor: serve para validar a tela antes do backend existir.
 * A F5 troca este módulo pela API real; ele continua só nos testes.
 */
import type { ComandoTerminal, MensagemTerminal } from './terminalComando'

let contador = 0
const proximoId = () => `sim${++contador}`

export const EXEMPLOS_TERMINAL = [
  'Mostre as últimas 50 linhas do log da DAG de malha',
  'Quais jobs do projeto DataStage falharam hoje?',
  'Reinicie a DAG etl_servicenow_sync',
] as const

const SAIDA_LOG = Array.from({ length: 60 }, (_, i) =>
  `[2026-11-04 08:${String(i % 60).padStart(2, '0')}:12] INFO  tarefa extrair_origem concluída (${1200 + i} linhas)`).join('\n')

function comando(parcial: Partial<ComandoTerminal> & Pick<ComandoTerminal, 'comando' | 'classe' | 'estado'>, servidor: string): ComandoTerminal {
  return { cmd_id: proximoId(), servidor, ...parcial }
}

/** Devolve as mensagens que o "servidor" produziria para o pedido do usuário. */
export function simularResposta(pedido: string, servidor: string, agora: Date = new Date()): MensagemTerminal[] {
  const p = pedido.toLowerCase()
  const texto = (t: string): MensagemTerminal => ({ id: proximoId(), papel: 'assistente', texto: t })
  const cmd = (c: ComandoTerminal): MensagemTerminal => ({ id: `c-${c.cmd_id}`, papel: 'comando', comando: c })

  if (/\.env|senha|password|segredo/.test(p)) {
    return [
      cmd(comando({ comando: 'cat /opt/airflow/.env', classe: 'proibido', estado: 'bloqueado',
        motivo: 'Arquivo de segredos' }, servidor)),
      texto('Não posso ler arquivos de segredos. Posso listar apenas os nomes das variáveis de ambiente esperadas, sem valores.'),
    ]
  }
  if (/reinici|restart|apag|limpar|delet|pausar|parar/.test(p)) {
    return [
      texto('Para isso preciso alterar o servidor. Confirma a execução abaixo?'),
      cmd(comando({
        comando: 'airflow dags unpause etl_servicenow_sync',
        classe: 'escrita', estado: 'proposto',
        motivo: 'Reativar a DAG que está pausada desde ontem.',
        expira_em: new Date(agora.getTime() + 120_000).toISOString(),
      }, servidor)),
    ]
  }
  if (/falha|erro quebrad|quebr/.test(p)) {
    return [
      cmd(comando({
        comando: 'dsjob -jobinfo PROJ_DEV job_carga_clientes', classe: 'leitura', estado: 'falhou',
        saida: 'ERRO: não foi possível conectar ao engine (timeout de 10 s).', codigo_saida: 1, duracao_ms: 10_050,
      }, servidor)),
      texto('O servidor do DataStage não respondeu dentro do prazo. Tente de novo em instantes ou me peça para consultar outro projeto.'),
    ]
  }
  if (/trunc|gigante|tudo/.test(p)) {
    return [
      cmd(comando({
        comando: 'journalctl -u orquestra-api -n 5000', classe: 'leitura', estado: 'executado',
        saida: SAIDA_LOG, codigo_saida: 0, duracao_ms: 1840, truncada: true,
      }, servidor)),
      texto('A saída passou do limite e foi cortada no servidor. Posso filtrar por erro ou por horário.'),
    ]
  }
  return [
    cmd(comando({
      comando: 'tail -n 60 /opt/airflow/logs/dag_malha/ultima_execucao.log', classe: 'leitura', estado: 'executado',
      saida: SAIDA_LOG, codigo_saida: 0, duracao_ms: 420,
    }, servidor)),
    texto('A última execução terminou sem erros: as 60 linhas mostram a extração concluída em todas as tarefas.'),
  ]
}

/** Decisão simulada: Confirmar "executa", Recusar só marca. */
export function simularDecisao(cmd: ComandoTerminal, decisao: 'confirmar' | 'recusar', usuario: string,
  agora: Date = new Date()): ComandoTerminal {
  const base = { ...cmd, decidido_por: usuario, decidido_em: agora.toISOString(), expira_em: null }
  if (decisao === 'recusar') return { ...base, estado: 'recusado' }
  return {
    ...base, estado: 'executado', saida: 'DAG etl_servicenow_sync reativada.', codigo_saida: 0, duracao_ms: 910,
  }
}
