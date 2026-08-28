// O conteúdo de um chamado — descrição, histórico de notas e anexos.
//
// A rota `/chamados/{sys_id}/detalhe` existe desde a F2 e até aqui não tinha
// tela: respondia e ninguém perguntava. Este é o consumidor dela.
//
// Escrito nos tokens da casa (`text-ink`, `text-dim`, `bg-canvas`,
// `border-edge`), e não nas cores fixas da versão de produção — cor fixa
// ignora o tema e a tela fica ilegível no modo claro.
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, Paperclip } from 'lucide-react'
import { apiFetch } from '../../lib/api'
import { Modal } from '../ui/Modal'
import { Spinner } from '../ui/Spinner'
import {
  dataHoraDaNota, rotuloDaNota, tamanhoLegivel,
  type AnexoChamado, type NotaChamado, type RespostaDetalhe,
} from '../../lib/chamadoDetalhe'

const ROTULO_ESTADO: Record<string, string> = {
  novo: 'Novo', andamento: 'Em andamento', aguardando: 'Aguardando',
  resolvido: 'Resolvido', encerrado: 'Encerrado', outros: 'Outros',
}

function Nota({ nota }: { nota: NotaChamado }) {
  return (
    <li className="bg-canvas border border-edge rounded-md p-2.5 flex flex-col gap-1">
      <div className="flex flex-wrap items-baseline gap-2 text-[10px]">
        <span className="text-ink font-medium">{nota.autor || 'autor desconhecido'}</span>
        <span className="text-dim tabular-nums">{dataHoraDaNota(nota.criado_em)}</span>
        {/* `work_notes` fica entre a equipe; `comments` o solicitante lê.
            Mostrar as duas iguais faz alguém escrever para dentro achando que
            escreveu para fora — ou o contrário, que é pior. */}
        <span className="text-dim px-1 py-px rounded bg-panel border border-edge">
          {rotuloDaNota(nota.tipo)}
        </span>
      </div>
      {/* `whitespace-pre-wrap`: as notas do ServiceNow vêm com quebras de
          linha que carregam sentido — lista de passos, saída de comando. */}
      <p className="text-xs text-ink whitespace-pre-wrap leading-relaxed">
        {nota.texto || '—'}
      </p>
    </li>
  )
}

function Anexo({ anexo }: { anexo: AnexoChamado }) {
  return (
    <li className="flex items-center gap-2 text-xs py-1">
      {/* O download passa pelo NOSSO backend: a credencial do ServiceNow não
          vai para o navegador, e o proxy exige o par (anexo, chamado). */}
      <a href={anexo.url_proxy} target="_blank" rel="noopener noreferrer"
        className="text-blue-600 dark:text-blue-400 truncate"
        title={anexo.nome_arquivo || 'anexo'}>
        {anexo.nome_arquivo || 'anexo'}
      </a>
      <span className="text-dim shrink-0 tabular-nums">
        {tamanhoLegivel(anexo.tamanho_bytes)}
      </span>
    </li>
  )
}

function Campo({ rotulo, valor }: { rotulo: string; valor: React.ReactNode }) {
  return (
    <div className="text-xs">
      <span className="text-dim">{rotulo}: </span>
      <span className="text-ink">{valor || '—'}</span>
    </div>
  )
}

export function ChamadoDetalheModal({ sysId, numero, aoFechar }: {
  sysId: string; numero: string; aoFechar: () => void
}) {
  const { data, isLoading, isError, error } = useQuery<RespostaDetalhe>({
    queryKey: ['chamado-detalhe', sysId],
    queryFn: () => apiFetch(`/chamados/${sysId}/detalhe`),
  })

  const c = data?.chamado

  return (
    <Modal open onClose={aoFechar} title={`Chamado ${numero}`} size="lg">
      {isLoading && (
        <div className="flex justify-center py-8"><Spinner /></div>
      )}

      {isError && (
        <div className="border rounded-lg px-4 py-3 text-[12px] bg-red-50
          dark:bg-red-900/20 border-red-200 dark:border-red-800
          text-red-800 dark:text-red-200">
          Não foi possível carregar o chamado: {(error as Error).message}
        </div>
      )}

      {!isLoading && !isError && data && (
        <div className="flex flex-col gap-4">
          {/* Espelho indisponível AVISA. Sem isso, um chamado sem notas e um
              chamado cujas notas não puderam ser lidas têm a mesma cara. */}
          {data.migration_ausente && (
            <div className="border rounded-lg px-3 py-2 text-[11px] bg-amber-50
              dark:bg-yellow-900/20 border-amber-200 dark:border-yellow-800
              text-amber-800 dark:text-yellow-200">
              Parte do conteúdo não pôde ser lida — o que aparece abaixo pode
              estar incompleto.
            </div>
          )}

          {c && (
            <>
              <p className="text-sm text-ink leading-snug">
                {c.titulo || '(sem título)'}
              </p>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1">
                <Campo rotulo="Estado"
                  valor={ROTULO_ESTADO[c.estado_kanban] ?? c.estado_kanban} />
                <Campo rotulo="Responsável" valor={c.atribuido_a} />
                <Campo rotulo="Grupo" valor={c.grupo} />
                <Campo rotulo="Aberto em" valor={dataHoraDaNota(c.aberto_em)} />
                <Campo rotulo="Prazo" valor={dataHoraDaNota(c.prazo)} />
                {/* O estado da ORIGEM ao lado do nosso: quando o card cai em
                    "Outros", é ele que explica por quê. */}
                <Campo rotulo="Na origem" valor={c.estado_origem} />
              </div>

              {c.descricao && (
                <section className="flex flex-col gap-1">
                  <h3 className="text-[10px] font-semibold text-dim uppercase tracking-wider">
                    Descrição
                  </h3>
                  <p className="text-xs text-ink whitespace-pre-wrap leading-relaxed
                    bg-canvas border border-edge rounded-md p-3">
                    {c.descricao}
                  </p>
                </section>
              )}
            </>
          )}

          <section className="flex flex-col gap-2">
            <h3 className="text-[10px] font-semibold text-dim uppercase tracking-wider">
              Histórico de notas{data.notas.length ? ` (${data.notas.length})` : ''}
            </h3>
            {data.notas.length === 0 ? (
              <p className="text-xs text-dim">
                {data.migration_ausente
                  ? 'As notas não puderam ser lidas.'
                  : 'Nenhuma nota registrada.'}
              </p>
            ) : (
              <ul className="flex flex-col gap-2">
                {data.notas.map(n => <Nota key={n.sys_id_nota} nota={n} />)}
              </ul>
            )}
          </section>

          {data.anexos.length > 0 && (
            <section className="flex flex-col gap-1">
              <h3 className="text-[10px] font-semibold text-dim uppercase tracking-wider
                flex items-center gap-1">
                <Paperclip size={11} /> Anexos ({data.anexos.length})
              </h3>
              <ul className="flex flex-col divide-y divide-edge">
                {data.anexos.map(a => <Anexo key={a.sys_id_anexo} anexo={a} />)}
              </ul>
            </section>
          )}

          {c?.url && (
            <a href={c.url} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs
                text-blue-600 dark:text-blue-400 self-start">
              <ExternalLink size={12} /> Abrir no ServiceNow
            </a>
          )}
        </div>
      )}
    </Modal>
  )
}
