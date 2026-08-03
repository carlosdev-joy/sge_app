// Mensagens de recusa de dependência ESPELHADAS do servidor — módulo
// compartilhado entre o MalhaEditor (F8) e o DependenciasModal (F5): cliente e
// servidor falam o MESMO texto (aceite da F8, mantido na F5). O servidor segue
// sendo a autoridade — estes textos existem para o feedback imediato, e o 422
// real chega com o mesmo conteúdo.

// Texto IDÊNTICO ao de _check_circular em api/routers/pipelines.py.
// `pipeline` = dependente (alvo da seta); `dependeDe` = origem.
export function msgCiclo(pipeline: string, dependeDe: string): string {
  return `Dependência circular: '${pipeline}' → '${dependeDe}' fecha um ciclo ` +
    `(o caminho volta para '${pipeline}')`
}

// Mesmo texto do 422 de auto-dependência do cadastro (register_pipeline).
export const MSG_SELF = 'Pipeline não pode depender de si mesmo'

// Aviso de republicação (Decisão 6/D30): as duas portas de escrita de
// dependência (MalhaEditor e DependenciasModal) anexam este texto ao toast
// quando o servidor devolve dag_config_pendente=true.
export function msgRepublicar(pipeline: string): string {
  return `A DAG de ${pipeline} precisa ser republicada (Pipelines ▸ Publicar nova versão).`
}

// Texto IDÊNTICO ao de msg_linha_assinada em api/services/dependencias.py
// (F11/Decisão 4): linha COMPILADA por Aguarde de malha só se mexe pela malha
// dona — o MalhaEditor (aresta com cadeado) e o DependenciasModal (chip
// travado) recusam o gesto com a MESMA mensagem que o 422 do servidor daria.
export function msgLinhaAssinada(
  pipeline: string, dependeDe: string, malha: string | null, no: number,
): string {
  return `A dependência '${pipeline}' → '${dependeDe}' é compilada pelo ` +
    `Aguarde #${no} da malha '${malha}' — edite pelo desenho da malha ` +
    '(linha assinada só se mexe pela malha dona).'
}
