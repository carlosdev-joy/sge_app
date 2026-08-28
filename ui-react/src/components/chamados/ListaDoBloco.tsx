// A lista de chamados do bloco aberto no painel.
//
// Componente próprio para poder ser RENDERIZADO em bancada: o que ele entrega é
// a ponte entre um número do painel e o conteúdo por trás dele — clicar no
// número abre o detalhe AQUI, e não uma aba do ServiceNow. Dentro da página do
// painel isso era inalcançável para teste (a página importa react-query).
import { ExternalLink } from 'lucide-react'
import { dataDoFim, type ChamadoDoPainel } from '../../lib/dashboardChamados'
// A aritmética de prazo serve às DUAS abas — mora em `prazoChamados`.
import { dataDoPrazo, mostraPrazo, rotuloDoPrazo } from '../../lib/prazoChamados'

const TOM_PRAZO: Record<string, string> = {
  atrasado: 'text-red-600 dark:text-red-400',
  hoje: 'text-orange-600 dark:text-orange-400',
  'no prazo': 'text-emerald-600 dark:text-emerald-400',
}

/** A lista do bloco aberto. */
export
function ListaDoBloco({ chamados, resolvidos = false, aoAbrir }: {
  chamados: ChamadoDoPainel[]; resolvidos?: boolean
  aoAbrir: (c: ChamadoDoPainel) => void
}) {
  if (!chamados.length) {
    return <p className="text-xs text-dim">Nenhum chamado nesta categoria.</p>
  }
  return (
    <ul className="flex flex-col gap-1">
      {chamados.map(c => {
        // Chamado finalizado não mostra prazo: "vencido há 40 dias" num
        // resolvido é ruído que ensina a ignorar o aviso.
        // No cartão de resolvidos a data que importa é a do FIM, não a do
        // prazo: é ela que deixa conferir o número — "22 resolvidos" só
        // significa alguma coisa quando dá para ver quando saíram.
        const fim = resolvidos ? dataDoFim(c) : null
        const mostra = !resolvidos && mostraPrazo(c.estado_kanban)
        const prazo = mostra ? rotuloDoPrazo(c.prazo) : null
        const data = mostra ? dataDoPrazo(c.prazo) : null
        return (
          <li key={c.sys_id}
            className="flex items-baseline gap-2 text-xs py-1 border-b border-edge last:border-0">
            {/* O número abre o DETALHE aqui, não o ServiceNow: a pergunta de
                quem clica na lista do painel é "o que é este chamado?", e ir
                para outra aba para responder isso custa o contexto inteiro.
                O link externo continua, ao lado, dito com seu ícone. */}
            <button type="button" onClick={() => aoAbrir(c)}
              className="font-mono font-semibold text-blue-600 dark:text-blue-400
                shrink-0 hover:underline"
              title="Ver descrição, histórico de notas e anexos">
              {c.numero}
            </button>
            <span className="text-ink truncate flex-1 min-w-0" title={c.titulo || ''}>
              {c.titulo || '(sem título)'}
            </span>
            {c.url && (
              <a href={c.url} target="_blank" rel="noopener noreferrer"
                className="text-blue-600 dark:text-blue-400 shrink-0"
                title="Abrir no ServiceNow (nova aba)">
                <ExternalLink size={11} />
              </a>
            )}
            <span className="text-dim shrink-0 w-32 truncate text-right"
              title={c.atribuido_a || 'sem responsável'}>
              {c.atribuido_a || 'sem responsável'}
            </span>
            {/* A DATA e o prazo em palavras, lado a lado.
                A data existe para conferir a olho — sem ela, "vence hoje" só
                pode ser verificado indo ao ServiceNow. E as palavras existem
                porque a data sozinha obriga quem lê a fazer a conta. */}
            {data && (
              <span className="shrink-0 w-24 text-right text-dim tabular-nums"
                title="Prazo do chamado">
                {data}
              </span>
            )}
            {prazo && (
              <span className={`shrink-0 w-24 text-right tabular-nums ${TOM_PRAZO[prazo.tom]}`}>
                {prazo.texto}
              </span>
            )}
            {/* A data do fim, e o que ela É. O til marca a aproximação: sem
                ele, "resolvido em 27/08" seria afirmação, e no ServiceNow o
                `closed_at` de um resolvido costuma estar vazio — a data
                mostrada é a da última atualização. */}
            {fim && (
              <span className="shrink-0 w-32 text-right text-dim tabular-nums"
                title={fim.exata
                  ? 'Data de encerramento do chamado'
                  : 'Última atualização — no ServiceNow, "Resolvido" ainda não '
                    + 'preenche a data de encerramento'}>
                {fim.exata ? '' : '~'}{fim.data}
              </span>
            )}
          </li>
        )
      })}
    </ul>
  )
}
