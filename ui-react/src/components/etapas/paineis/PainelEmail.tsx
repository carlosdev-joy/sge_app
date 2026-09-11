// ── Painel de um nó de E-MAIL ────────────────────────────────────────────────
// Spec docs/spec-notificacao-email.md (F2). Layout LARGO do dock inferior, o
// mesmo do painel de notificação: 2 colunas no lg+ — esquerda = identidade,
// destinatários e anexo; direita = assunto, corpo e placeholders.
//
// A régua (raízes de anexo permitidas, canal ligado) vem do Admin › E-mail por
// GET /email/status: o que a tela oferece é exatamente o que o envio aceita.
import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Node } from '@xyflow/react'
import { CalendarClock, Mail, Paperclip, Trash2 } from 'lucide-react'
import { apiFetch } from '../../../lib/api'
import { dataLegivel, sugerirOdate } from '../../../lib/emailAnexo'
import type { Listagem } from '../../../lib/utilitariosNavegador'
import { CampoPasta } from '../../utilitarios/CampoPasta'
import { NavegadorPastas } from '../../utilitarios/NavegadorPastas'
import { useNavegadorPastas } from '../../utilitarios/useNavegadorPastas'
import { Button } from '../../ui/Button'
import { Input, Select, Textarea } from '../../ui/Input'
import { PlaceholderPicker } from '../../ui/PlaceholderPicker'
import type { EmailNodeData } from '../EmailNode'
import {
  defaultEmailNo, errosDoEmailNo, opcoesDoModeloNo,
  separarDestinatarios, textoDosDestinatarios,
  EMAIL_PLACEHOLDERS, type EmailNoConfig,
} from '../fluxoTypes'
import { PreviaEmail } from '../PreviaEmail'
import { dicaDoMarcador, marcadoresDesconhecidos } from '../previaEmailDados'
import { NomeField } from './shared'

interface EmailStatus {
  enabled: boolean
  limite_mb: number
  raizes: string[]
  dominios: string[]
  disponivel: boolean
}

/** Catálogo de modelos + o interruptor de padronização (migration 112). */
interface EmailModelosApi {
  modelos: {
    id: number; nome: string; descricao: string | null; assunto: string | null
    corpo: string; html: boolean; padrao: boolean
  }[]
  disponivel: boolean
  exigir_modelo: boolean
}

export interface PainelEmailProps {
  node: Node
  onRename: (oldName: string, novo: string) => boolean
  onPatchEmail: (nodeId: string, patch: Partial<EmailNoConfig>) => void
  onDelete: (id: string) => void
}

export function PainelEmail({ node, onRename, onPatchEmail, onDelete }: PainelEmailProps) {
  const d = node.data as EmailNodeData
  const isNew = !!d.isNew
  const cfg = d.email ?? defaultEmailNo()
  const patch = (p: Partial<EmailNoConfig>) => onPatchEmail(node.id, p)
  const corpoRef = useRef<HTMLTextAreaElement>(null)
  const assuntoRef = useRef<HTMLInputElement>(null)

  // Destinatários: o campo guarda o TEXTO CRU enquanto se digita, e o nó recebe
  // a lista já separada a cada tecla.
  //
  // ⛔ Antes o `value` era `cfg.destinatarios.join('\n')`: como `separar…`
  // descarta o pedaço vazio, o Enter (e a vírgula) era apagado no mesmo instante
  // em que era digitado e o 2º endereço colava no 1º (`ana@x.combruno@y.com`),
  // que a régua então recusava como inválido. Na prática só dava para cadastrar
  // UM destinatário — ou colar a lista pronta, que chega inteira num `onChange`
  // só. É o mesmo desenho do campo do fluxo (PipelineFormModal): texto cru na
  // tela, separação na hora de gravar.
  //
  // Não precisa de efeito para acompanhar a troca de nó: o PropriedadesPanel
  // monta este painel com `key={node.id}`, então o estado nasce do nó aberto.
  const [textoDest, setTextoDest] = useState(() => textoDosDestinatarios(cfg.destinatarios))
  // ⚠️ Espelho do que o campo emitiu por último. O nó também muda por FORA do
  // campo: salvar o fluxo invalida a query e o editor reconstrói os nós com a
  // resposta do servidor (que normaliza o domínio para minúsculas, e que pode
  // não ter o endereço digitado durante o POST). Sem esta comparação o campo
  // seguiria mostrando o texto antigo — contando uma coisa e o nó guardando
  // outra. Comparar TEXTO (e não o array, novo a cada patch) é o que impede o
  // laço: quando a mudança veio daqui, o espelho já bate e nada é reescrito —
  // que é o motivo de isto não poder ser um `useEffect` com `[cfg.destinatarios]`,
  // que reescreveria o campo a cada tecla e traria o defeito de volta.
  // (ajuste de estado durante o render, o padrão do React para "prop mudou" —
  // não pode ser `ref`, que o lint proíbe ler no render, nem `useEffect`.)
  const listaDoNo = textoDosDestinatarios(cfg.destinatarios)
  const [espelhoDest, setEspelhoDest] = useState(listaDoNo)
  if (listaDoNo !== espelhoDest) {
    setEspelhoDest(listaDoNo)
    setTextoDest(listaDoNo)
  }

  // Régua do Admin. Degrada para desligado/sem raízes: a tela então explica o
  // que falta em vez de oferecer um anexo que o envio recusaria.
  const { data: status, isError: statusFalhou } = useQuery<EmailStatus>({
    queryKey: ['email-status'],
    queryFn: () => apiFetch('/email/status'),
    staleTime: 300_000,
  })
  // Catálogo: sem a 112 vem `disponivel: false` e a lista some — o painel cai
  // no corpo livre, e a tela do nó não quebra por causa do catálogo.
  const { data: catalogo, isError: catalogoFalhou } = useQuery<EmailModelosApi>({
    queryKey: ['email-modelos'],
    queryFn: () => apiFetch('/email/modelos'),
    staleTime: 300_000,
  })
  const temCatalogo = catalogo?.disponivel === true
  const modelos = catalogo?.modelos ?? []
  const exigirModelo = catalogo?.exigir_modelo === true
  const modeloEscolhido = modelos.find(m => m.id === cfg.modelo_id) ?? null
  const corpoDoModelo = modeloEscolhido?.corpo
  const htmlDoModelo = modeloEscolhido?.html
  // Escolhido, mas fora da lista de escolha (que só traz os ativos): ou foi
  // DESATIVADO — e aí segue enviando, porque o envio de propósito não filtra
  // por ativo — ou foi apagado do banco, e aí a etapa falha. A tela não
  // consegue distinguir os dois casos, então não afirma nenhum dos dois.
  // ⚠️ Só vale COM catálogo em mãos: enquanto a lista carrega (ou se a
  // consulta falhar), `modelos` é [] e todo modelo pareceria "fora da lista".
  const modeloForaDaLista = temCatalogo && cfg.modelo_id != null && !modeloEscolhido
  // Catálogo que não respondeu, com um modelo já escolhido: nada mudou no
  // envio — o worker lê o modelo do banco — mas a tela não tem o que mostrar.
  const catalogoSemResposta = !temCatalogo && cfg.modelo_id != null
  // A regra do Corpo livre × padronização mora em fluxoTypes (testada na
  // bancada do front): é ela que precisa continuar batendo com a do backend.
  const { podeCorpoLivre, faltaEscolherModelo } = opcoesDoModeloNo({
    exigirModelo, isNew, modeloId: cfg.modelo_id,
  })

  const raizes = status?.raizes ?? []
  // Só passa a regra do catálogo quando o catálogo respondeu — senão a tela
  // cobraria um modelo que ela mesma não tem como oferecer.
  const erros = errosDoEmailNo(cfg, raizes, temCatalogo ? { exigirModelo, isNew } : undefined)
  // Marcador que o operador não conhece sai literal no e-mail — melhor avisar
  // aqui do que descobrir na caixa de quem recebeu.
  const desconhecidos = marcadoresDesconhecidos(
    `${cfg.assunto} ${cfg.corpo} ${cfg.anexo?.nome ?? ''}`)

  const anexoLigado = cfg.anexo != null
  function alternarAnexo(ligado: boolean) {
    patch({ anexo: ligado ? { raiz: raizes[0] ?? '', nome: '' } : null })
  }

  // Navegador de pastas dos Utilitários, com a rede apontando para o endpoint
  // do e-mail: as raízes e a permissão são outras, o gesto é o mesmo.
  const navegador = useNavegadorPastas('datastage', (_servidor, caminho, ocultos) => {
    const q = new URLSearchParams({ mostrar_ocultos: String(ocultos) })
    if (caminho) q.set('caminho', caminho)
    return apiFetch(`/email/anexo/listar?${q}`) as Promise<Listagem>
  })
  const odate = anexoLigado ? sugerirOdate(cfg.anexo?.nome ?? '') : null

  return (
    <div className="flex flex-1 flex-col">
      <div className="flex items-center gap-2 border-b border-edge px-4 py-2.5">
        {/* teal-600: o glifo branco precisa de 3:1 (WCAG 1.4.11) — como no nó. */}
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-teal-600 text-white">
          <Mail size={15} strokeWidth={2.2} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{d.name}</p>
          <p className="text-[11px] text-dim">E-mail</p>
        </div>
        <Button variant="danger" size="sm" className="ml-auto shrink-0" onClick={() => onDelete(node.id)}>
          <Trash2 size={13} /> Excluir e-mail
        </Button>
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-2">
        {/* ── Coluna esquerda: identidade, destinatários e anexo ──────────── */}
        <div className="flex min-w-0 flex-col gap-2">
          <NomeField id={node.id} name={d.name} isNew={isNew} placeholder="ex: AVISA_EQUIPE" onRename={onRename} />

          <div className="flex flex-col gap-1">
            <Textarea
              label="Destinatários"
              hint={'Um endereço por linha (ou separados por vírgula).\nPode ficar vazio se você herdar a lista do fluxo abaixo.'}
              value={textoDest}
              rows={3}
              onChange={e => {
                const lista = separarDestinatarios(e.target.value)
                setTextoDest(e.target.value)
                // O espelho acompanha o que ESTE campo acabou de emitir, senão
                // o render seguinte leria a própria emissão como "mudou por
                // fora" e redesenharia o texto, apagando o separador digitado.
                setEspelhoDest(textoDosDestinatarios(lista))
                patch({ destinatarios: lista })
              }}
              // Ao sair, o texto vira o que o nó de fato guarda: some a vírgula
              // sobrando, o espaço e o endereço repetido, e o que ficou na tela
              // é exatamente o que vai ser enviado.
              onBlur={() => setTextoDest(textoDosDestinatarios(separarDestinatarios(textoDest)))}
              placeholder={'ana@cvp.com.br\ncarlos@cvp.com.br'}
              className="text-xs"
            />
            <label className="flex cursor-pointer items-start gap-2 text-[11px] text-ink">
              <input
                type="checkbox"
                className="mt-0.5 h-3.5 w-3.5 rounded border-edge"
                checked={cfg.incluir_pipeline}
                onChange={e => patch({ incluir_pipeline: e.target.checked })}
              />
              <span>
                Incluir os destinatários do fluxo
                <span className="block text-[10px] text-dim/70">
                  Soma a lista cadastrada no fluxo (cadastro do pipeline › Destinatários de e-mail do fluxo), sem repetir endereço.
                </span>
              </span>
            </label>
            {status?.dominios?.length ? (
              <p className="text-[10px] text-dim/70">
                Domínios permitidos no Admin: {status.dominios.join(', ')}.
              </p>
            ) : null}
          </div>

          {/* ── Anexo: pasta da lista do Admin + nome livre ───────────────── */}
          <div className="flex flex-col gap-1.5 rounded-lg border border-edge p-2.5">
            <label className="flex cursor-pointer items-center gap-2 text-xs font-semibold text-ink">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 rounded border-edge"
                checked={anexoLigado}
                onChange={e => alternarAnexo(e.target.checked)}
                // Sem pasta liberada dá para DESMARCAR, nunca marcar: senão um
                // nó que já tem anexo ficaria sem como remover o anexo.
                disabled={raizes.length === 0 && !anexoLigado}
              />
              <Paperclip size={12} className="text-teal-600 dark:text-teal-300" />
              Anexar um arquivo do servidor
            </label>
            {raizes.length === 0 && !anexoLigado ? (
              <p className="text-[10px] text-dim/70">
                {statusFalhou
                  ? 'Não foi possível consultar as pastas liberadas agora — tente de novo em instantes.'
                  : 'Nenhuma pasta liberada para anexo — cadastre as pastas em Admin › E-mail.'}
              </p>
            ) : anexoLigado && cfg.anexo ? (
              <>
                {/* Pasta: caminho abaixo de uma raiz liberada. Era um Select
                    só com as raízes — que não alcançava o arquivo guardado
                    numa subpasta, o caso normal. O envio sempre aceitou a
                    subpasta; era o cadastro que recusava. */}
                <CampoPasta
                  value={cfg.anexo.raiz}
                  onChange={v => patch({ anexo: { ...cfg.anexo!, raiz: v } })}
                  raizes={raizes}
                  ajuda={'Caminho no servidor do DataStage, abaixo de uma pasta liberada em Admin › E-mail.\nUse Navegar… para escolher o arquivo sem digitar.'}
                  // As raízes do anexo são de Admin › E-mail, não da tela de
                  // Utilitários: sem isto o campo manda cadastrar no lugar
                  // errado, numa tabela que este painel nem lê.
                  ondeCadastrar="Admin › E-mail"
                  onNavegar={navegador.disponivel ? () => navegador.abrir(cfg.anexo?.raiz || null) : undefined}
                />
                <Input
                  label="Nome do arquivo"
                  hint={'O arquivo pode ainda não existir: ele costuma ser gerado pela própria corrida.\nAceita placeholders — ex.: relatorio_{odate}.xlsx'}
                  value={cfg.anexo.nome}
                  onChange={e => patch({ anexo: { ...cfg.anexo!, nome: e.target.value } })}
                  placeholder="relatorio_{odate}.xlsx"
                  className="text-xs"
                />
                {/* Escolher pelo navegador traz o arquivo DE HOJE; amanhã a
                    corrida procuraria o mesmo nome. A troca pela marca da data
                    é oferecida, nunca feita sozinha: nome com data fixa é caso
                    legítimo (uma carga histórica). */}
                {odate && (
                  <div className="flex flex-wrap items-center gap-2 rounded border border-edge bg-canvas px-2 py-1.5">
                    <span className="text-[10px] text-dim">
                      O nome tem a data <strong>{dataLegivel(odate.data)}</strong>. Trocar por{' '}
                      <code className="font-mono">{'{odate}'}</code> faz cada corrida buscar o arquivo do seu dia.
                    </span>
                    <Button variant="secondary" size="sm" className="ml-auto shrink-0"
                            onClick={() => patch({ anexo: { ...cfg.anexo!, nome: odate.sugestao } })}>
                      <CalendarClock size={12} /> Usar {'{odate}'}
                    </Button>
                  </div>
                )}
                <p className="text-[10px] text-dim/70">
                  Se o arquivo não estiver lá na hora do envio, o e-mail sai mesmo assim, sem anexo, e o log avisa.
                  Limite de {status?.limite_mb ?? 5} MB.
                </p>
              </>
            ) : null}
          </div>

          <NavegadorPastas
            aberto={navegador.aberto}
            listagem={navegador.listagem}
            carregando={navegador.carregando}
            erro={navegador.erro}
            mostrarOcultos={navegador.ocultos}
            filtro={navegador.filtro}
            onFiltro={navegador.mudarFiltro}
            onNavegar={navegador.navegar}
            onMostrarOcultos={navegador.mudarOcultos}
            onUsarPasta={p => { patch({ anexo: { raiz: p, nome: cfg.anexo?.nome ?? '' } }); navegador.fechar() }}
            // O pedido: clicar no arquivo já atribui — pasta e nome de uma vez.
            onEscolherArquivo={(pasta, nome) => {
              patch({ anexo: { raiz: pasta, nome } })
              navegador.fechar()
            }}
            onFechar={navegador.fechar}
          />

          {status && !status.enabled && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              O canal de e-mail está desligado em Admin › E-mail. O nó fica salvo, mas a corrida vai pular este envio.
            </p>
          )}
          {erros.length > 0 && (
            <ul className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              {erros.map(e => <li key={e}>{e}</li>)}
            </ul>
          )}
        </div>

        {/* ── Coluna direita: assunto, corpo e placeholders ────────────────── */}
        <div className="flex min-w-0 flex-col gap-2 lg:border-l lg:border-edge lg:pl-4">
          <div className="flex items-center gap-1.5">
            <Mail size={12} className="text-teal-600 dark:text-teal-300" />
            <span className="text-xs font-semibold text-ink">Mensagem</span>
          </div>

          {/* Catálogo que não respondeu não pode sumir em silêncio: o backend
              continua com a régua dele, e um nó novo com a padronização ligada
              ficaria irrecusável sem nenhuma explicação na tela. */}
          {catalogoFalhou && (
            <p className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              Não foi possível consultar os modelos agora. O que já está escolhido continua
              valendo no envio; para trocar de modelo, recarregue a página.
            </p>
          )}

          {temCatalogo && (
            <div className="flex flex-col gap-1">
              <Select
                label="Modelo"
                hint={'O layout vem do catálogo e é lido no envio: trocar o modelo em Admin › E-mail vale para todos os fluxos.\nCorpo livre é a saída para um aviso fora do padrão.'}
                value={cfg.modelo_id != null ? String(cfg.modelo_id) : ''}
                onChange={e => patch({ modelo_id: e.target.value ? Number(e.target.value) : null })}
                className="text-xs"
              >
                {podeCorpoLivre && <option value="">Corpo livre (escrever aqui)</option>}
                {/* Padronização ligada em nó novo: a lista abre sem escolha, e
                    não em Corpo livre — que a API recusaria ao salvar. */}
                {faltaEscolherModelo && <option value="">Selecione um modelo…</option>}
                {modelos.map(m => <option key={m.id} value={m.id}>{m.nome}</option>)}
                {modeloForaDaLista && (
                  <option value={String(cfg.modelo_id)}>#{cfg.modelo_id} (fora da lista)</option>
                )}
              </Select>
              {modeloEscolhido?.descricao && (
                <p className="text-[10px] text-dim/70">{modeloEscolhido.descricao}</p>
              )}
              {faltaEscolherModelo && (
                <p className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                  {modelos.length === 0
                    ? 'Admin › E-mail exige um modelo do catálogo, e não há nenhum modelo ativo. Peça ao Admin para ativar um antes de salvar este nó.'
                    : 'Admin › E-mail exige um modelo do catálogo: escolha um para salvar este nó.'}
                </p>
              )}
              {modeloForaDaLista && (
                <p className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                  O modelo #{cfg.modelo_id} não está na lista de escolha. Se foi apenas
                  desativado, o envio continua usando o layout dele; se foi removido do
                  catálogo, a corrida falha. Confira em Admin › E-mail › Modelos — ou
                  escolha outro aqui.
                </p>
              )}
            </div>
          )}

          <Input
            ref={assuntoRef}
            label="Assunto *"
            hint={'Aceita os placeholders do seletor abaixo.\nSem quebra de linha.'}
            value={cfg.assunto}
            onChange={e => patch({ assunto: e.target.value })}
            placeholder="[Orquestra] {pipeline} — {status}"
            className="text-xs"
          />

          {cfg.modelo_id != null ? (
            <p className="rounded-lg border border-edge bg-canvas px-3 py-2 text-[10px] text-dim">
              O corpo vem do modelo <strong>{modeloEscolhido?.nome ?? `#${cfg.modelo_id}`}</strong>,
              lido na hora do envio. Para escrever um texto próprio, escolha <em>Corpo livre</em>.
            </p>
          ) : (
          <div className="flex flex-col gap-1">
            <Textarea
              ref={corpoRef}
              label="Corpo *"
              hint="Aceita os mesmos placeholders, trocados na hora do envio."
              value={cfg.corpo}
              rows={7}
              onChange={e => patch({ corpo: e.target.value })}
              placeholder="A carga {pipeline} terminou em {data} com {linhas} linhas."
              className="text-xs"
            />
            <PlaceholderPicker
              label="Inserir:"
              placeholders={EMAIL_PLACEHOLDERS}
              targetRef={corpoRef}
              value={cfg.corpo}
              onChange={v => patch({ corpo: v })}
            />
            <label className="flex cursor-pointer items-center gap-2 text-[11px] text-ink">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 rounded border-edge"
                checked={cfg.html}
                onChange={e => patch({ html: e.target.checked })}
              />
              Corpo em HTML
            </label>
            <p className="text-[10px] text-dim/70">
              Com HTML ligado, quem não consegue ver HTML recebe a mesma mensagem sem as marcações.
            </p>
            {desconhecidos.length > 0 && (
              <p className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                {desconhecidos.length === 1 ? 'Marcador desconhecido' : 'Marcadores desconhecidos'}
                {' '}no assunto, no corpo ou no nome do anexo:{' '}
                {desconhecidos.map(m => {
                  const dica = dicaDoMarcador(m)
                  return dica ? `{${m}} (seria ${dica})` : `{${m}}`
                }).join(', ')} — vai sair assim mesmo no e-mail.
              </p>
            )}
          </div>
          )}

          <div className="flex flex-col gap-1">
            {/* Com modelo escolhido, a prévia mostra o corpo DO MODELO: é o que
                vai ser enviado. O corpo do nó continua guardado para a volta ao
                Corpo livre, mas não é o que sai. */}
            {modeloForaDaLista || catalogoSemResposta ? (
              // Sem o corpo em mão, prévia em branco pareceria "o e-mail vai
              // sair vazio" — falso tanto para um modelo apenas desativado
              // (que segue enviando) quanto para o catálogo que não respondeu.
              <p className="rounded-lg border border-edge bg-canvas px-3 py-2 text-[10px] text-dim">
                {catalogoSemResposta
                  ? `Sem prévia: não foi possível carregar o modelo #${cfg.modelo_id} agora. O envio continua usando o layout dele.`
                  : `Sem prévia: o modelo #${cfg.modelo_id} está fora da lista de escolha.`}
                {' '}O conteúdo dele fica em Admin › E-mail › Modelos.
              </p>
            ) : (
              <PreviaEmail
                corpo={cfg.modelo_id != null ? (corpoDoModelo ?? '') : cfg.corpo}
                html={cfg.modelo_id != null ? (htmlDoModelo ?? true) : cfg.html}
                altura={210}
                titulo={cfg.modelo_id != null ? 'Prévia do modelo' : 'Prévia'}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
