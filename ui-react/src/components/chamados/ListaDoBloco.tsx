// Os chamados do bloco aberto no painel, em TABELA.
//
// ⚠️ Isto era uma lista `flex`, e o defeito era de alinhamento: prazo e data só
// eram renderizados quando existiam, então um chamado SEM PRAZO perdia duas
// células e o responsável escorregava para o lugar delas. A mesma coluna visual
// mostrava prazo numa linha e nome de pessoa na seguinte — e, com `truncate` e
// largura fixa, o nome ainda saía cortado sem forma de ver o resto.
//
// A tabela resolve as duas coisas de uma vez: a célula vazia continua ocupando
// a coluna, e a largura é arrastável. Ver `TabelaChamados`.
import { dataDoFim, type ChamadoDoPainel } from '../../lib/dashboardChamados'
// A aritmética de prazo serve às DUAS abas — mora em `prazoChamados`.
import { dataDoPrazo, mostraPrazo, rotuloDoPrazo } from '../../lib/prazoChamados'
import { NumeroChamado } from './NumeroChamado'
import { TabelaChamados, type ColunaTabela } from './TabelaChamados'
import { ExternalLink } from 'lucide-react'

const TOM_PRAZO: Record<string, string> = {
  atrasado: 'text-red-600 dark:text-red-400',
  hoje: 'text-orange-600 dark:text-orange-400',
  'no prazo': 'text-emerald-600 dark:text-emerald-400',
}

const SEM_DONO = 'sem responsável'
// A tarefa não carrega solicitante no ServiceNow, e o incidente usa outro
// campo: a ausência é comum e precisa ser DITA, não deixada em branco.
const SEM_SOLICITANTE = 'sem solicitante'

export function ListaDoBloco({ chamados, resolvidos = false, aoAbrir }: {
  chamados: ChamadoDoPainel[]; resolvidos?: boolean
  aoAbrir: (c: ChamadoDoPainel) => void
}) {
  // Chamado finalizado não mostra prazo: "vencido há 40 dias" num resolvido é
  // ruído que ensina a ignorar o aviso. No bloco de resolvidos, a data que
  // importa é a do FIM — é ela que deixa conferir o número: "22 resolvidos" só
  // significa alguma coisa quando dá para ver quando saíram.
  const colunas: ColunaTabela<ChamadoDoPainel>[] = [
    {
      chave: 'numero', rotulo: 'Chamado', largura: 168, minima: 120,
      titulo: c => c.numero,
      conteudo: c => (
        <span className="flex items-center gap-1.5 min-w-0">
          <NumeroChamado numero={c.numero} aoAbrir={() => aoAbrir(c)} />
          {c.url && (
            <a href={c.url} target="_blank" rel="noopener noreferrer"
              className="text-blue-600 dark:text-blue-400 shrink-0"
              title="Abrir no ServiceNow (nova aba)">
              <ExternalLink size={11} />
            </a>
          )}
        </span>
      ),
    },
    {
      chave: 'titulo', rotulo: 'Título', largura: 340, minima: 120,
      titulo: c => c.titulo || '(sem título)',
      conteudo: c => <span className="text-ink">{c.titulo || '(sem título)'}</span>,
    },
    {
      // Quem PEDIU, ao lado de quem ATENDE. São perguntas diferentes, e a
      // tabela respondia só a segunda.
      chave: 'solicitante', rotulo: 'Solicitante', largura: 190, minima: 100,
      titulo: c => c.demandante || SEM_SOLICITANTE,
      conteudo: c => (
        <span className={c.demandante ? 'text-ink' : 'text-dim italic'}>
          {c.demandante || SEM_SOLICITANTE}
        </span>
      ),
    },
    {
      chave: 'responsavel', rotulo: 'Responsável', largura: 190, minima: 100,
      // O `title` traz o nome INTEIRO: enquanto o usuário não arrasta a coluna,
      // é por ele que "Cristiane Gomes de Moura" deixa de ser "Cristiane Gom…".
      titulo: c => c.atribuido_a || SEM_DONO,
      conteudo: c => (
        // Sem dono é DITO, não deixado em branco: célula vazia numa coluna de
        // nome parece falha de carregamento, e a informação aqui é que o
        // chamado não tem responsável — que é o que faz alguém agir.
        <span className={c.atribuido_a ? 'text-ink' : 'text-dim italic'}>
          {c.atribuido_a || SEM_DONO}
        </span>
      ),
    },
  ]

  if (resolvidos) {
    colunas.push({
      chave: 'fim', rotulo: 'Resolvido em', largura: 150, minima: 90,
      titulo: c => {
        const f = dataDoFim(c)
        if (!f) return ''
        return f.exata
          ? `Encerrado em ${f.data}`
          : `Última atualização em ${f.data} — no ServiceNow, "Resolvido" ainda `
            + 'não preenche a data de encerramento'
      },
      conteudo: c => {
        const f = dataDoFim(c)
        // O til marca a APROXIMAÇÃO. Sem ele, "resolvido em 27/08" seria
        // afirmação — e no ServiceNow o `closed_at` de um resolvido costuma
        // estar vazio, então a data mostrada é a da última atualização.
        return f ? <span className="text-dim tabular-nums">{f.exata ? '' : '~'}{f.data}</span> : null
      },
    })
  } else {
    colunas.push(
      {
        chave: 'prazo', rotulo: 'Prazo', largura: 110, minima: 80,
        titulo: c => (mostraPrazo(c.estado_kanban) && dataDoPrazo(c.prazo)) || '',
        conteudo: c => {
          const data = mostraPrazo(c.estado_kanban) ? dataDoPrazo(c.prazo) : null
          return data ? <span className="text-dim tabular-nums">{data}</span> : null
        },
      },
      {
        chave: 'situacao', rotulo: 'Situação', largura: 120, minima: 80,
        titulo: c => (mostraPrazo(c.estado_kanban)
          && rotuloDoPrazo(c.prazo)?.texto) || '',
        conteudo: c => {
          // A data sozinha obriga quem lê a fazer a conta; as palavras sozinhas
          // não deixam conferir. As duas colunas existem por isso.
          const p = mostraPrazo(c.estado_kanban) ? rotuloDoPrazo(c.prazo) : null
          return p ? <span className={`tabular-nums ${TOM_PRAZO[p.tom]}`}>{p.texto}</span> : null
        },
      },
    )
  }

  return (
    <TabelaChamados id={resolvidos ? 'painel-resolvidos' : 'painel-fila'}
      colunas={colunas} itens={chamados} chaveDe={c => c.sys_id}
      vazio="Nenhum chamado nesta categoria." />
  )
}
