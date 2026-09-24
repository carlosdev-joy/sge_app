// Admin › Agentes › Prompt (A2 + BK-1 da spec docs/spec-agentes-admin.md).
//
// O admin edita só o DOMÍNIO do prompt; o Orquestra monta em volta dele a
// parte fixa (contexto, protocolo de ferramentas, regras, propostas), que
// aparece aqui só para leitura. Cada gravação é uma VERSÃO nova — nada é
// sobrescrito — e vale a partir da próxima pergunta, sem reiniciar nada.
//
// Conflito (409 `prompt_mudou`): outro admin gravou antes. O texto digitado
// NÃO se perde: vai para "Seu texto" (copiável) e o editor recarrega a versão
// nova, para o admin refazer a mudança em cima dela.
//
// `versao_base` é a versão sobre a qual o RASCUNHO começou (`baseDoRascunho`),
// nunca a versão em uso no momento do clique: a query se refaz sozinha (foco
// da janela, invalidação), e usar `ativa.versao` ali fazia uma gravação feita
// sobre a v3 passar por cima da v4 de outro admin sem 409 (revisão
// adversarial da A2).
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { copyToClipboard } from '../../lib/clipboard'
import {
  LIMITE_PROMPT, codigoDoErro, dataHoraCurta, duracaoDaVigencia, mensagemDeErro, motivoValido, tempoMedio,
  type PromptResposta, type VersaoPrompt, type VersoesPromptResposta,
} from '../../lib/agentes'
import { Button } from '../ui/Button'
import { InfoBanner } from '../ui/InfoBanner'
import { Input, Textarea } from '../ui/Input'
import { Modal } from '../ui/Modal'
import { toast } from '../ui/Toast'

interface Props {
  agente: { id: string; nome: string }
  /** Dentro do painel do agente (Admin › Agentes): sem moldura de cartão e
   *  sem repetir o nome no título — o painel já diz de quem é. */
  embutido?: boolean
  /** Avisa quem contém se há texto NÃO salvo (rascunho ou "Seu texto" de um
   *  conflito) — o painel confirma antes de trocar de agente ou fechar. */
  onSujo?: (sujo: boolean) => void
}

export function PromptAgente({ agente, embutido = false, onSujo }: Props) {
  const qc = useQueryClient()
  const base = `/agentes/admin/agentes/${encodeURIComponent(agente.id)}/prompt`
  const qPrompt = ['agentes-admin-prompt', agente.id] as const
  const qVersoes = ['agentes-admin-prompt-versoes', agente.id] as const

  const prompt = useQuery<PromptResposta>({ queryKey: qPrompt, queryFn: () => apiFetch(base) })
  const versoes = useQuery<VersoesPromptResposta>({ queryKey: qVersoes, queryFn: () => apiFetch(`${base}/versoes`) })

  // `null` = sem edição em curso: o editor mostra a versão ativa.
  const [rascunho, setRascunho] = useState<string | null>(null)
  // A versão que estava em uso quando o rascunho começou — o `versao_base`.
  const [baseDoRascunho, setBaseDoRascunho] = useState<number | null>(null)
  // Versão que ESTE admin criou restaurando com um rascunho aberto — para o
  // aviso não culpar "outro administrador" pela mudança que ele mesmo fez.
  const [minhaRestauracao, setMinhaRestauracao] = useState<number | null>(null)
  const [motivo, setMotivo] = useState('')
  // Texto de quem perdeu a corrida para outro admin (409): fica à mão.
  const [seuTexto, setSeuTexto] = useState<string | null>(null)
  const [conflito, setConflito] = useState<number | null>(null)
  const [restaurando, setRestaurando] = useState<{ versao: number; motivo: string } | null>(null)
  const [vendo, setVendo] = useState<number | null>(null)

  const texto = useQuery<{ versao: VersaoPrompt }>({
    queryKey: ['agentes-admin-prompt-versao', agente.id, vendo],
    queryFn: () => apiFetch(`${base}/versoes/${vendo}`),
    enabled: vendo !== null,
  })

  async function recarregar() {
    await Promise.all([qc.invalidateQueries({ queryKey: qPrompt }), qc.invalidateQueries({ queryKey: qVersoes })])
  }

  function tratarErro(e: unknown, padrao: string, textoDigitado: string | null) {
    if (codigoDoErro(e) === 'prompt_mudou') {
      const d = (e as { detail?: { versao_atual?: number } }).detail
      setConflito(typeof d?.versao_atual === 'number' ? d.versao_atual : null)
      // Só o conflito de uma GRAVAÇÃO troca o editor pela versão nova (e guarda
      // o texto digitado em "Seu texto"). O de uma restauração não mexe no
      // rascunho que estiver no editor — só fecha a caixa de restaurar.
      if (textoDigitado !== null) {
        setSeuTexto(textoDigitado)
        setRascunho(null)
        setBaseDoRascunho(null)
      }
      setRestaurando(null)
      void recarregar()
      return
    }
    toast.error(mensagemDeErro(e, padrao))
  }

  const ativa = prompt.data?.ativa
  const limites = prompt.data?.limites ?? { texto_max: LIMITE_PROMPT, motivo_min: 3, motivo_max: 200 }

  // O pai (painel do agente) precisa saber se sair daqui perde texto digitado.
  const sujo = rascunho !== null || seuTexto !== null
  useEffect(() => { onSujo?.(sujo) }, [sujo, onSujo])
  useEffect(() => () => onSujo?.(false), [onSujo])

  const salvar = useMutation({
    mutationFn: (v: { texto: string; motivo: string; versao_base: number }) =>
      apiFetch<{ ativa: VersaoPrompt }>(base, { method: 'PUT', body: JSON.stringify(v) }),
    onSuccess: async r => {
      toast.success(`Versão ${r.ativa.versao} gravada — vale a partir da próxima pergunta`)
      setRascunho(null); setBaseDoRascunho(null); setMotivo(''); setConflito(null); setSeuTexto(null)
      setMinhaRestauracao(null)
      await recarregar()
    },
    onError: (e: unknown, v) => tratarErro(e, 'Não foi possível gravar a versão', v.texto),
  })

  const restaurar = useMutation({
    mutationFn: (v: { versao: number; motivo: string; versao_base: number }) =>
      apiFetch<{ ativa: VersaoPrompt }>(`${base}/restaurar`, { method: 'POST', body: JSON.stringify(v) }),
    onSuccess: async (r, v) => {
      toast.success(`Versão ${v.versao} restaurada como versão ${r.ativa.versao}`)
      setRestaurando(null); setConflito(null)
      if (rascunho !== null) setMinhaRestauracao(r.ativa.versao)
      await recarregar()
    },
    onError: (e: unknown) => tratarErro(e, 'Não foi possível restaurar a versão', null),
  })

  if (prompt.isLoading) return <p className="text-sm text-dim">Carregando o prompt…</p>
  if (prompt.isError || !prompt.data || !ativa) {
    return (
      <InfoBanner icon="⚠">
        {`Falha ao carregar o prompt de ${agente.nome}: ${mensagemDeErro(prompt.error, 'erro desconhecido')}`}
      </InfoBanner>
    )
  }

  const valor = rascunho ?? ativa.texto
  // Começar a editar fixa a base; voltar a `null` (descartar/gravar) a solta.
  const editar = (t: string) => {
    if (rascunho === null) setBaseDoRascunho(ativa.versao)
    setRascunho(t)
  }
  // Outro admin gravou enquanto este editava: salvar vai dar 409 — avisa ANTES.
  const desatualizado = rascunho !== null && baseDoRascunho !== null && baseDoRascunho !== ativa.versao
  const mudou = rascunho !== null && rascunho.trim() !== ativa.texto
  const grande = valor.trim().length > limites.texto_max
  const podeSalvar = mudou && !grande && valor.trim().length > 0
    && motivoValido(motivo, limites.motivo_min, limites.motivo_max) && !salvar.isPending

  return (
    <section className={embutido ? 'flex flex-col gap-4'
                                 : 'bg-panel border border-edge rounded-lg p-4 shadow-sm flex flex-col gap-4'}
             data-agentes-prompt={agente.id}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          {/* Embutido, a aba "Prompt" do painel já é o título (e o campo abaixo se chama "Instruções do domínio"). */}
          {!embutido && <h3 className="text-sm font-semibold text-ink">Prompt — {agente.nome}</h3>}
          <p className="text-xs text-dim mt-0.5">
            Você edita só as instruções do domínio. Cada gravação vira uma versão nova e vale a partir da
            próxima pergunta, sem reiniciar nada.
          </p>
        </div>
        <span className="text-xs text-dim border border-edge rounded-md px-2 py-1 bg-canvas" data-agentes-prompt-ativa>
          {ativa.padrao
            ? 'Em uso: padrão do código'
            : `Em uso: versão ${ativa.versao} · ${ativa.criado_por ?? '—'} · ${dataHoraCurta(ativa.criado_em)}`}
        </span>
      </div>

      {conflito !== null && (
        <InfoBanner icon="⚠">
          {`Outro administrador gravou a versão ${conflito} antes de você. `
            + (seuTexto !== null
              ? 'O editor mostra agora a versão em uso — o texto que você tinha digitado está logo abaixo, em “Seu texto”, para copiar.'
              : rascunho !== null
                ? 'O seu rascunho continua no editor, mas foi feito sobre uma versão anterior: ao salvar, ele será recusado. Copie o que precisar e descarte o rascunho.'
                : 'A versão em uso foi recarregada.')}
        </InfoBanner>
      )}
      {conflito === null && desatualizado && (
        <InfoBanner icon="⚠">
          {(minhaRestauracao === ativa.versao
            ? `Você restaurou uma versão (agora a ${ativa.versao}) com este rascunho aberto, e ele partiu da ${baseDoRascunho}. `
              + 'Ao salvar, ele será recusado para não desfazer a restauração — descarte o rascunho e refaça sobre a versão nova.'
            : `A versão em uso mudou para a ${ativa.versao} enquanto você editava (seu rascunho partiu da ${baseDoRascunho}). `
              + 'Ao salvar, ele será recusado para não apagar a mudança do outro administrador — descarte o rascunho e refaça sobre a versão nova.')}
        </InfoBanner>
      )}

      <Textarea
        label="Instruções do domínio"
        value={valor}
        onChange={e => editar(e.target.value)}
        // Travado enquanto grava: o que se digitasse agora sumiria no sucesso
        // (o rascunho é zerado) e não entraria em "Seu texto" num 409.
        readOnly={salvar.isPending}
        rows={20}
        spellCheck={false}
        className="font-mono text-xs leading-relaxed"
        error={grande ? `Passa do limite de ${limites.texto_max.toLocaleString('pt-BR')} caracteres` : undefined}
        data-agentes-prompt-editor
      />
      <p className="text-xs text-dim -mt-2">
        {valor.trim().length.toLocaleString('pt-BR')} / {limites.texto_max.toLocaleString('pt-BR')} caracteres
      </p>

      {seuTexto !== null && (
        <details className="border border-edge rounded-md bg-canvas" open data-agentes-prompt-seu-texto>
          <summary className="cursor-pointer px-3 py-2 text-sm text-ink">Seu texto (não gravado)</summary>
          <div className="px-3 pb-3 flex flex-col gap-2">
            <pre className="text-xs text-ink font-mono whitespace-pre-wrap break-words max-h-64 overflow-y-auto">{seuTexto}</pre>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost"
                      onClick={async () => {
                        // `copyToClipboard` cai no execCommand em HTTP (a intranet não é HTTPS) e diz se deu certo.
                        if (await copyToClipboard(seuTexto)) toast.success('Texto copiado')
                        else toast.error('Não foi possível copiar — selecione o texto e copie à mão')
                      }}>
                Copiar
              </Button>
              {/* Recolocar no editor é refazer SOBRE a versão em uso: a base passa a ser ela. */}
              <Button size="sm" variant="ghost"
                      onClick={() => { setRascunho(seuTexto); setBaseDoRascunho(ativa.versao); setConflito(null) }}>
                Colocar no editor
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setSeuTexto(null)}>Descartar</Button>
            </div>
          </div>
        </details>
      )}

      <div className="flex flex-wrap items-end gap-2">
        <div className="flex-1 min-w-[16rem]">
          <Input
            label="Motivo da mudança"
            value={motivo}
            maxLength={limites.motivo_max}
            onChange={e => setMotivo(e.target.value)}
            placeholder="ex.: agente pedia o projeto mesmo com o prefixo claro"
            hint="Obrigatório — fica no histórico junto com quem gravou."
          />
        </div>
        <Button
          disabled={!podeSalvar}
          loading={salvar.isPending}
          onClick={() => salvar.mutate({ texto: valor, motivo, versao_base: baseDoRascunho ?? ativa.versao })}
          data-agentes-prompt-salvar
        >
          Salvar versão
        </Button>
        <Button variant="ghost" disabled={rascunho === null || salvar.isPending}
                onClick={() => {
                  setRascunho(null); setBaseDoRascunho(null); setMotivo(''); setConflito(null); setMinhaRestauracao(null)
                }}>
          Descartar
        </Button>
      </div>

      <details className="border border-edge rounded-md" data-agentes-prompt-parte-fixa>
        <summary className="cursor-pointer px-3 py-2 text-sm text-ink">
          Parte fixa montada pelo Orquestra (só leitura)
        </summary>
        <div className="px-3 pb-3 flex flex-col gap-2">
          <p className="text-xs text-dim">
            Vai junto com o seu texto em toda pergunta, nesta ordem. Traz o protocolo das ferramentas, as regras
            de segurança e o formato de propostas — por isso não é editável.
          </p>
          <pre className="text-xs text-dim font-mono whitespace-pre-wrap break-words bg-canvas border border-edge rounded-md p-2 max-h-72 overflow-y-auto">
            {prompt.data.parte_fixa.antes}
            {'\n\n'}
            <span className="text-ink">{'[ instruções do domínio — o texto acima ]'}</span>
            {'\n\n'}
            {prompt.data.parte_fixa.depois}
          </pre>
        </div>
      </details>

      <details className="border border-edge rounded-md" data-agentes-prompt-historico>
        <summary className="cursor-pointer px-3 py-2 text-sm text-ink">Histórico de versões</summary>
        <div className="px-3 pb-3 flex flex-col gap-2">
          {versoes.isLoading ? (
            <p className="text-sm text-dim">Carregando…</p>
          ) : versoes.isError || !versoes.data ? (
            <p className="text-sm text-dim">
              {`Não foi possível carregar o histórico: ${mensagemDeErro(versoes.error, 'erro desconhecido')}`}
            </p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-xs" data-agentes-prompt-versoes>
                  <thead>
                    <tr className="text-left text-dim border-b border-edge">
                      <th scope="col" className="py-1.5 pr-3 font-medium">Versão</th>
                      <th scope="col" className="py-1.5 pr-3 font-medium">Vigente de</th>
                      <th scope="col" className="py-1.5 pr-3 font-medium">Até</th>
                      <th scope="col" className="py-1.5 pr-3 font-medium">Duração</th>
                      <th scope="col" className="py-1.5 pr-3 font-medium text-right">Respostas</th>
                      <th scope="col" className="py-1.5 pr-3 font-medium text-right">Tempo médio</th>
                      <th scope="col" className="py-1.5 pr-3 font-medium">Por</th>
                      <th scope="col" className="py-1.5 pr-3 font-medium">Motivo</th>
                      <th scope="col" className="py-1.5 font-medium" aria-label="Ações" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-edge">
                    {versoes.data.versoes.map(v => {
                      const emUso = v.versao === versoes.data.ativa
                      return (
                        <tr key={v.versao} className="text-ink align-top" data-agentes-prompt-versao={v.versao}>
                          <td className="py-1.5 pr-3 whitespace-nowrap">
                            {v.padrao ? 'Padrão do código' : `v${v.versao}`}
                            {v.origem_versao !== null && (
                              <span className="text-dim">{` (restaurou ${v.origem_versao === 0 ? 'o padrão' : `v${v.origem_versao}`})`}</span>
                            )}
                            {emUso && <span className="ml-1 text-dim">· em uso</span>}
                          </td>
                          <td className="py-1.5 pr-3 whitespace-nowrap">
                            {v.padrao && !v.vigente_de ? 'deploy' : dataHoraCurta(v.vigente_de)}
                          </td>
                          <td className="py-1.5 pr-3 whitespace-nowrap">
                            {emUso ? 'agora' : dataHoraCurta(v.vigente_ate)}
                          </td>
                          <td className="py-1.5 pr-3 whitespace-nowrap">{duracaoDaVigencia(v.duracao_s)}</td>
                          <td className="py-1.5 pr-3 text-right tabular-nums">{v.respostas ?? 0}</td>
                          <td className="py-1.5 pr-3 text-right tabular-nums whitespace-nowrap">{tempoMedio(v.duracao_media_ms)}</td>
                          <td className="py-1.5 pr-3 whitespace-nowrap">{v.criado_por ?? '—'}</td>
                          <td className="py-1.5 pr-3 min-w-[12rem]">{v.motivo}</td>
                          <td className="py-1.5 whitespace-nowrap text-right">
                            <Button size="sm" variant="ghost" onClick={() => setVendo(v.versao)}
                                    aria-label={`Ver o texto da ${v.padrao ? 'versão padrão' : `versão ${v.versao}`}`}>
                              Ver
                            </Button>
                            {!emUso && (
                              <Button size="sm" variant="ghost"
                                      onClick={() => setRestaurando({ versao: v.versao, motivo: '' })}
                                      aria-label={`Restaurar a ${v.padrao ? 'versão padrão' : `versão ${v.versao}`}`}>
                                Restaurar
                              </Button>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-dim">
                {`“Respostas” e “Tempo médio” contam só as conversas ainda guardadas (últimos ${versoes.data.retencao_dias} dias). `}
                O padrão do código vale desde o último deploy, que o banco não registra — por isso ele não tem data
                de início nem duração.
              </p>
            </>
          )}
        </div>
      </details>

      <Modal
        open={restaurando !== null}
        onClose={() => setRestaurando(null)}
        title={restaurando?.versao === 0 ? 'Restaurar o padrão do código' : `Restaurar a versão ${restaurando?.versao ?? ''}`}
      >
        {restaurando && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-dim">
              O texto dessa versão é gravado como uma versão NOVA — nada do histórico é apagado — e passa a valer
              na próxima pergunta.
            </p>
            <Input
              label="Motivo"
              value={restaurando.motivo}
              maxLength={limites.motivo_max}
              onChange={e => setRestaurando({ ...restaurando, motivo: e.target.value })}
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setRestaurando(null)} disabled={restaurar.isPending}>Cancelar</Button>
              <Button
                disabled={!motivoValido(restaurando.motivo, limites.motivo_min, limites.motivo_max) || restaurar.isPending}
                loading={restaurar.isPending}
                onClick={() => restaurar.mutate({ versao: restaurando.versao, motivo: restaurando.motivo,
                                                 versao_base: ativa.versao })}
              >
                Restaurar
              </Button>
            </div>
          </div>
        )}
      </Modal>

      <Modal open={vendo !== null} onClose={() => setVendo(null)} size="xl"
             title={vendo === 0 ? 'Padrão do código' : `Versão ${vendo ?? ''}`}>
        {texto.isLoading ? (
          <p className="text-sm text-dim">Carregando…</p>
        ) : texto.isError || !texto.data ? (
          <p className="text-sm text-dim">{mensagemDeErro(texto.error, 'Não foi possível carregar o texto')}</p>
        ) : (
          <pre className="text-xs text-ink font-mono whitespace-pre-wrap break-words max-h-[70vh] overflow-y-auto">
            {texto.data.versao.texto}
          </pre>
        )}
      </Modal>
    </section>
  )
}
