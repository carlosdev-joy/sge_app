// MalhaEditor — diagrama de montagem da malha (F8 da spec de dependências, §4b).
// Irmão do FluxoEditor (React Flow), NÃO parametrização dele: aqui o nó é um
// PIPELINE membro da malha e a aresta é uma DEPENDÊNCIA REAL e GLOBAL da
// etl_pipeline_dependencia (migration 067) — desenhar a aresta É cadastrar a
// dependência (POST /dependencias), e excluí-la apaga a dependência de verdade
// em TODAS as malhas (daí a confirmação explícita). O layout dos nós persiste
// por malha em etl_malha_pipeline (PUT /malhas/{name}/layout) — botão "Salvar
// posições" habilita só quando alguma posição mudou (salvar sem mudança é no-op).
// F9: toggle Montagem | Execução. No modo Execução a malha abre numa DATA DE
// REFERÊNCIA (default = ODATE corrente calculado no servidor pela virada
// global), colore os nós pelo status de etl_pipeline_execucao (polling 30s),
// lista os eventos da guardiã (etl_dependencia_evento) e TRAVA a edição —
// reusa o mesmo mecanismo do readOnly da F8. Em produção, antes da retomada
// F2–F4, nada alimenta essas tabelas: a visão mostra o estado vazio HONESTO.
// Orientação (migration 074): o diagrama desenha horizontal (esquerda →
// direita, default) ou vertical (cima → baixo) POR MALHA — a preferência
// persiste no servidor junto do layout (PATCH /malhas/{name}) e trocar
// reorganiza as posições na direção nova; a visão de Execução herda a mesma
// orientação (é o mesmo grafo) e a consulta vê a salva sem poder trocar.
// F12 (docs/malha-componentes-desenho.md §10): os QUATRO componentes de malha
// no canvas — Início, Aguarde, Notificação e Fim (etl_malha_no, migration 075),
// misturados aos nós-pipeline. A paleta arrasta-para-criar (POST /nos); as
// arestas de NÓ são gestos com efeito de COMPILAÇÃO (F11): todo gesto composto
// roda dry_run ANTES do write e o modal de confirmação mostra o efeito
// (criar/remover/transferir/republicar/manuais) — erros[] (ciclo) BLOQUEIAM
// com o texto literal do servidor, e o espelho client-side (criaCiclo sobre o
// preview_expandido do dry_run) cobre o vão, sem nunca ser a autoridade
// (Decisão 15). Aresta compilada por nó de OUTRA malha chega anotada
// (compilada_por) e desenha com CADEADO, somente leitura aqui — a recusa usa
// a mesma mensagem do 422 (Decisão 4). Avisos de desenho (§2.2): banner
// persistente alimentado pelo GET + toast no gesto que os cria.
// F15 (desenho §8): os componentes ganham CAMADA de execução no modo Execução
// — Início com raízes-na-data + próxima execução (display-only), Aguarde
// satisfeito/bloqueado/aguardando derivado de execucoes[] × upstream (o
// upstream vem do SERVIDOR), Notificação/Fim acesos pelo evento do dia
// (eventos_no da F14) — nó sem dado na data fica NEUTRO (regra F9); banner
// verde de "malha concluída"; eventos de nó entram no painel da guardiã; e o
// DISPARO MANUAL da malha: botão → dry_run (raízes + ODATE no modal) →
// confirmar → POST /malhas/{m}/disparo dispara as raízes pelo trigger REST
// da casa — a cascata anda pelo push, nenhum executor novo.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  Panel,
  MarkerType,
  useReactFlow,
  useNodesInitialized,
  useNodesState,
  useEdgesState,
  applyNodeChanges,
  type Node,
  type Edge,
  type Connection,
  type NodeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { apiFetch } from '../../lib/api'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { toast } from '../ui/Toast'
import { Autocomplete } from '../ui/Autocomplete'
import { PageSpinner } from '../ui/Spinner'
import {
  Activity, AlertCircle, AlertTriangle, Anchor, ArrowRightLeft, ArrowUpDown,
  CalendarClock, CheckCircle2, Info, Layers,
  Link2,
  Lock, Minus, MousePointerClick, Play, Plus, RefreshCw, Save,
  Unlock,
  Trash2, Wrench,
} from 'lucide-react'
import { useAuthStore } from '../../store/auth'
import { useColorMode } from '../etapas/useColorMode'
import { liveLayout, criaCiclo, type Orientacao } from '../etapas/layoutGrafo'
import { useRealceDependencias } from '../etapas/useRealceDependencias'
import { PainelRealce } from '../etapas/PainelRealce'
import { MalhaPipelineNode, type MalhaPipelineNodeData } from './MalhaPipelineNode'
import {
  InicioNode, AguardeNode, NotificacaoNode, FimNode,
  type ExecComponente, type MalhaComponenteNodeData,
} from './MalhaComponenteNodes'
import { COMPONENTE_META, type TipoComponente } from './componenteMeta'
// F13: painel de agendamento do nó Início — o agendamento mora na MALHA
// (Decisão 8); o nó é a porta.
import { AgendamentoInicioModal } from './AgendamentoInicioModal'
import {
  STATUS_EXECUCAO, ORDEM_LEGENDA,
  abaInicialDaCorrida, avisoPresoNaFila, resumoCorrida,
  type CorridasResposta, type ExecucaoPipeline, type MalhaExecucaoApi,
} from './statusExecucao'
// F10 — a faixa da corrida, o painel de "o que está travando" e a navegação
// por corrida (Decisões 42, 62, 63, 65 e 66).
import { CabecalhoCorrida, type NoSegurado } from './CabecalhoCorrida'
import { PainelCorridaLateral, type AbaCorrida } from './PainelCorridaLateral'
import { SeletorCorrida } from './SeletorCorrida'
// F7: o texto de duração da corrida (o mesmo módulo puro da faixa) — o crédito
// de retenção chega em MINUTOS do servidor e vira "6h" no toast.
import { textoDuracao } from './tempoCorrida'
// F4: o relógio LOCAL da faixa (Decisão 60) — o decorrido anda no navegador, o
// `apurado_em` do banco fica no tooltip.
import { useDecorrido } from './useDecorrido'
import type { CorridaCabecalho } from '../../types'
// Camada de FLUXO da visão de Execução: a linha entre dois nós conta por onde
// a corrida do dia passou, onde ela está agora e onde parou.
import {
  arestaComFluxo, estadoDaAresta, estadoDoComponente, estadoDoPipeline,
  ROTULO_FLUXO, type EstadoElemento,
} from './fluxoExecucao'
// F15: próxima execução do agendamento — DISPLAY-ONLY (a autoridade do
// gatilho é o scheduler; mesmo estatuto do calcularDataRef da F5).
// F10 (Decisão 61): o mesmo helper passa a dar o INSTANTE, que é o que permite
// escrever "a próxima corrida parte em 2h50 (01:00)" na faixa.
import { proximaExecucao, proximaExecucaoTexto } from './proximaExecucao'
// F10 (Decisão 65): a reexecução de um travado reusa a prévia que já existe —
// é ela que traz, do servidor, a frase do efeito na corrida em voo.
import { ModalRerunEtapa } from '../etapas/ModalRerunEtapa'
// Mensagens de recusa ESPELHADAS do servidor — módulo compartilhado com o
// DependenciasModal da F5: cliente e servidor com o MESMO texto, num lugar só.
import { msgCiclo, MSG_SELF, msgRepublicar, msgLinhaAssinada } from './mensagensDependencia'

// Nó-pipeline (F8) + os quatro componentes (F12). GOTCHA React Flow: aresta
// cujo source/target não casa com id de nó é DESCARTADA em silêncio — todos os
// ids (pipelines E componentes) entram no MESMO setNodes, antes das edges.
const nodeTypes = {
  malhaPipeline: MalhaPipelineNode,
  malhaInicio: InicioNode,
  malhaAguarde: AguardeNode,
  malhaNotificacao: NotificacaoNode,
  malhaFim: FimNode,
}

// ── Tipos do payload da API (/malhas/{name}) ────────────────────────────────
interface MalhaMembroApi {
  pipeline_name: string
  active: 0 | 1 | boolean
  criticidade: string | null
  schedule_type: string | null
  layout_x: number | null
  layout_y: number | null
  // F13 (aditivos): assinatura de agendamento (qual Início agenda esta raiz)
  // e o badge de contradição (raiz assinada que ganhou dependência por outra
  // porta — o agendamento da malha está inerte nela, §2.2).
  agenda_no?: number | null
  agenda_contradicao?: boolean
  // Publicação: dag_criada (a DAG já existe no Airflow?) e o carimbo da 073
  // (o cadastro mudou depois da última publicação?). `publicacao_pendente`
  // AUSENTE = banco sem a 073 — a tela não afirma "está em dia".
  dag_criada?: number
  publicacao_pendente?: boolean
  // Quantos predecessores o membro tem na 067. Com predecessor E agendamento
  // próprio, ele dispara FORA da malha: calcula a própria data de referência
  // e mistura a corrida (causa do incidente da Carga_Vida). Chave ausente =
  // sem a 067 no banco — a tela não afirma nada.
  qtd_predecessores?: number
}
// Proveniência de linha compilada (F11): o nó Aguarde dono e a malha dele.
interface CompiladaPor {
  malha: string | null
  no: number
}
interface MalhaArestaApi {
  pipeline_name: string   // o dependente (destino da seta)
  depende_de: string      // o predecessor (origem da seta)
  // F11 (§7.4): linha COMPILADA por nó de OUTRA malha — desenha com cadeado,
  // somente leitura aqui (a exclusão é 422 nomeando a dona).
  compilada_por?: CompiladaPor
}
// Nó especial do desenho (F10 — etl_malha_no).
interface MalhaNoApi {
  id: number
  tipo: string
  config: Record<string, unknown> | null
  layout_x: number | null
  layout_y: number | null
  // Upstream expandido pelo SERVIDOR (§3.2) — o front nunca expande.
  upstream: string[]
  // 082: Aguarde SEGURADO. Chaves ausentes = banco sem a migration, e a tela
  // não oferece o gesto (botão que não segura é pior que botão ausente).
  retido_em?: string | null
  retido_por?: string | null
}
// Aresta de nó do desenho (F10 — etl_malha_aresta).
interface MalhaArestaNoApi {
  id: number
  origem_no: number | null
  origem_pipeline: string | null
  destino_no: number | null
  destino_pipeline: string | null
}
// Aviso de desenho (§2.2): {no, nivel 'forte'|'leve', mensagem}. no=null =
// aviso do compilador, sem nó específico.
interface AvisoDesenho {
  no: number | null
  nivel: string
  mensagem: string
  // F15 (aditivo): chave estável do aviso — hoje só 'contradicao' (raiz
  // assinada com dependência). A visão de Execução mostra ESTE aviso mesmo
  // sem o banner de montagem: é lá que vive o disparo manual, que parte a
  // raiz por cima do predecessor.
  tipo?: string
}
interface MalhaDetalheApi {
  malha_name: string
  descricao: string | null
  ativo: 0 | 1 | boolean
  // Orientação do diagrama (migration 074) — preferência POR MALHA que viaja
  // com o layout persistido. Chave ausente (API/banco antigos) = horizontal.
  orientacao?: string
  membros: MalhaMembroApi[]
  // Contrato da F8: dependências (tipo PIPELINE) onde AMBAS as pontas são
  // membros da malha.
  arestas?: MalhaArestaApi[]
  // F10: nós especiais e arestas de nó do desenho + avisos §2.2. Chave ausente
  // (API anterior) degrada como a migration_075_pendente.
  nos?: MalhaNoApi[]
  arestas_no?: MalhaArestaNoApi[]
  avisos?: AvisoDesenho[]
  // Deploy parcial (migration 067 ausente): a API devolve "arestas": [] e liga
  // esta flag — o editor avisa e desliga a criação de arestas. Chave `arestas`
  // AUSENTE (API anterior à F8) degrada do mesmo jeito.
  migration_067_pendente?: boolean
  // Deploy parcial (migration 075 ausente): nós/arestas de nó vazios + flag —
  // o resto da malha segue intacto e a paleta de componentes desliga.
  migration_075_pendente?: boolean
  // F13 (aditivos): o agendamento da MALHA (fonte de compilação — o motor
  // nunca lê daqui) + o resumo humano do servidor. Chave ausente = colunas
  // da 075 pendentes; o painel do Início desliga.
  agendamento?: Record<string, unknown> | null
  agendamento_resumo?: string | null
  // F2 da spec-malha-data-unica (migration 081): a régua de data do ciclo.
  // `hora_virada` null = a malha segue a virada global; `virada_divergente`
  // lista os membros fora da régua (chaves ausentes = sem a 081 no banco, e a
  // tela não afirma nada).
  hora_virada?: string | null
  equalizar_data?: number
  // F7 (085): o limite de segurança da MALHA. Chave AUSENTE = a coluna não
  // está neste banco (deploy parcial) e o campo não é oferecido; `null` =
  // "segue o limite global", que é resposta, não ausência.
  teto_horas?: number | null
  virada_divergente?: string[]
}

// ── Contrato do gesto (dry_run — desenho §7.2) ──────────────────────────────
interface EfeitoDep { dependente: string; predecessor: string }
interface EfeitoGesto {
  dependencias_criar: EfeitoDep[]
  dependencias_remover: EfeitoDep[]
  dependencias_transferir: (EfeitoDep & { para_malha: string; para_no: number })[]
  ja_existentes_manuais: EfeitoDep[]
  agendamentos: { pipeline: string; de: string; para: string }[]
  republicar: string[]
}
interface GestoResposta {
  efeito: EfeitoGesto
  avisos: AvisoDesenho[]
  erros: string[]
  // Conjunto PÓS-gesto {pipeline_name, depende_de} — é sobre ele que o espelho
  // client-side do ciclo (criaCiclo) roda (§3.3).
  preview_expandido?: { pipeline_name: string; depende_de: string }[]
}
interface GestoWriteResposta {
  ok: boolean
  ja_existia?: boolean
  arestas_removidas?: number
  avisos: AvisoDesenho[]
  efeito: EfeitoGesto
}

// ── Contrato do disparo manual da malha (F15 — POST /malhas/{m}/disparo) ────
interface DisparoRaizInfo {
  pipeline: string
  active: number
  dag_criada: number
  // F15 (revisão): a raiz tem dependência na 067 (o disparo manual parte por
  // cima do predecessor) e quantas corridas ela já tem na data (a raiz não é
  // protegida pelo claim — disparar de novo roda de novo).
  tem_dependencia?: boolean
  corridas_na_data?: number
}
// F1 da spec-malha-data-unica: o que SEGURA a malha. `em_aberto` = membro com
// corrida viva (a malha começa do zero); `datas_divergentes` = membro que
// rodou NESTE ciclo carimbando outra data de referência (o incidente da
// Carga_Vida). O servidor recusa o disparo; o dry_run só mostra.
interface BloqueioCiclo {
  pipeline: string
  data_referencia: string | null
  status: string
  inicio: string | null
}
interface DisparoDryResposta {
  data_referencia: string
  raizes: DisparoRaizInfo[]
  avisos: AvisoDesenho[]
  bloqueios?: { em_aberto: BloqueioCiclo[]; datas_divergentes: BloqueioCiclo[] }
  bloqueado?: boolean
  // F3: malha marcada para equalizar — em vez de parar, ela carimba todos com
  // a data do ciclo. O de→para é mostrado ANTES de confirmar.
  equalizacao?: {
    prevista: BloqueioCiclo[]
    impedidos: (BloqueioCiclo & { motivo: string })[]
    bloqueado_por_corrida: boolean
  }
}
interface DisparoResposta {
  ok: boolean
  data_referencia: string
  disparadas: { pipeline: string; dag_run_id: string }[]
  falhas: { pipeline: string; erro: string }[]
  avisos: AvisoDesenho[]
  // F3: o que a malha recarimbou em nome do operador (aditivo).
  equalizados?: { pipeline: string; de: string; para: string }[]
}

// ── Republicação da malha (POST /malhas/{m}/republicar) ─────────────────────
// Desenhar aresta/Aguarde/agendamento grava a dependência na hora, mas a DAG
// que o Airflow executa continua sendo a ANTERIOR até ser regerada. O gesto
// republica TODOS os membros de uma vez; dry_run mostra quem entra, quem fica
// de fora e por quê.
interface RepublicarAlvo {
  pipeline: string
  active: number
  dag_criada: number
  // null = banco sem a migration 073 (nada a afirmar sobre estar em dia).
  publicacao_pendente: boolean | null
  // A DAG existe no Airflow? Vem do próprio Airflow (o cadastro não serve:
  // dag_criada fica 0 durante a regeneração). null = não deu para saber —
  // e aí o modal não afirma nada. Só no dry_run.
  dag_no_airflow?: boolean | null
}
interface RepublicarDryResposta {
  malha: string
  pipelines: RepublicarAlvo[]
  ignorados: { pipeline: string; motivo: string }[]
  avisos: AvisoDesenho[]
  pendentes_de_fora: number
}
interface RepublicarResposta {
  ok: boolean
  malha: string
  dag_run_id: string
  republicados: string[]
  ignorados: { pipeline: string; motivo: string }[]
  avisos: AvisoDesenho[]
  pendentes_de_fora: number
}

// Linha unificada do painel de eventos (F9 pipelines + F14 nós observadores).
interface EventoPainel {
  rotulo: string
  ehNo: boolean
  tipo: string
  criado_em: string
  mensagem: string | null
  // F10: o estado da FILA DE AVISO. Chave AUSENTE = o banco não tem a coluna
  // (não perguntei) · `null` = na fila, ninguém foi avisado · texto = avisado.
  // As três leituras precisam continuar distinguíveis: confundir a primeira
  // com a segunda acenderia o banner vermelho em toda malha de banco antigo.
  notificado_em?: string | null
}

// Ponta de aresta de nó no contrato §9: {no: id} XOR {pipeline: nome}.
type PontaGesto = { no: number } | { pipeline: string }

// Gesto aguardando confirmação no modal (alimentado pelo dry_run).
interface GestoPendente {
  acao: 'criar-aresta' | 'remover-aresta' | 'remover-no'
  rotulo: string          // ex.: "DEV_F10_B → Aguarde #8"
  origem?: PontaGesto
  destino?: PontaGesto
  arestaId?: number
  noId?: number
  resposta: GestoResposta
  // Ciclo do ESPELHO client-side quando o servidor não devolveu erro —
  // defensivo; o texto é o mesmo (msgCiclo).
  cicloLocal?: string | null
}

// ── Helpers da visão de execução (F9) ───────────────────────────────────────
// F10: `somaDia` saiu junto com o ◀ ▶ por DIA. A navegação temporal virou uma
// só — a faixa de corridas do `SeletorCorrida` (Decisão 42) —, e o dia deixou
// de ser um passo do teclado para virar um item de menu.

function horaCurta(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  return isNaN(d.getTime())
    ? iso
    : d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

// Tooltip do nó com o resumo da execução (o card em si não muda — F9).
// F5 (D32): corrida aguardando anexa "aguardando: P1, P2" — os faltantes vêm
// do MESMO predicado do motor (port em api/services/dependencias.py).
function tituloExecucao(e: ExecucaoPipeline): string {
  const partes = [e.status]
  const ini = horaCurta(e.inicio)
  const fim = horaCurta(e.fim)
  if (ini) partes.push(`início ${ini}`)
  if (fim) partes.push(`fim ${fim}`)
  if (e.disparado_por) partes.push(`disparado por ${e.disparado_por}`)
  let linha = partes.join(' · ')
  if (e.faltantes && e.faltantes.length > 0) {
    linha += `\naguardando: ${e.faltantes.join(', ')}`
  }
  return e.motivo ? `${linha}\n${e.motivo}` : linha
}

// F15: estado de execução de um componente (desenho §8) — derivação PURA de
// dados que o payload já tem. null = NEUTRO: modo Montagem, nó desligado do
// grafo ou nenhuma execução na data que sustente estado (a regra F9 de nunca
// inventar cor). O upstream do Aguarde vem do SERVIDOR (§3.2) — aqui só se
// cruza com execucoes[]; Notificação/Fim acendem pelo evento do dia (F14).
function execDoComponente(
  n: MalhaNoApi,
  tipo: TipoComponente,
  raizes: string[],
  execPorPipeline: Map<string, ExecucaoPipeline>,
  eventoNoPorId: Map<string, string>,
  agendamento: Record<string, unknown> | null,
  // F4: o CICLO desta lente, como o nó Fim precisa dele. Só ele usa — é o
  // único nó que fala de ciclo, e até esta fase ele só tinha "verde" ou
  // "apagado".
  //   `aberto`     — há corrida ABERTA: o terceiro estado, anel azul discreto;
  //   `concluido`  — `true`/`false` quando existe corrida no payload; `null`
  //                  quando NÃO existe (API anterior, banco sem a 085, malha
  //                  sem ciclo), e aí o nó volta a ser o de hoje: o evento.
  ciclo: { aberto: boolean; concluido: boolean | null },
): ExecComponente | null {
  switch (tipo) {
    case 'inicio': {
      if (raizes.length === 0) return null
      // Contagem POR STATUS, nunca por presença de linha: PULADO (regra de
      // agenda barrou o dia) e FALHA também têm linha em
      // etl_pipeline_execucao — contá-las como "partiu" pintaria o Início de
      // verde num sábado em que nada rodou, ou ao lado de um Aguarde
      // vermelho. Verde é SUCESSO no canvas inteiro.
      let sucesso = 0, falha = 0, pulado = 0, emCurso = 0, semLinha = 0
      for (const p of raizes) {
        const st = execPorPipeline.get(p)?.status
        if (st === undefined) semLinha += 1
        else if (st === 'SUCESSO') sucesso += 1
        else if (st === 'FALHA') falha += 1
        else if (st === 'PULADO') pulado += 1
        else emCurso += 1        // EXECUTANDO / AGUARDANDO_DEPENDENCIA / cru
      }
      return {
        kind: 'inicio',
        raizes: raizes.length,
        sucesso, falha, pulado, emCurso, semLinha,
        proxima: proximaExecucaoTexto(agendamento),
      }
    }
    case 'aguarde': {
      const upstream = n.upstream
      if (upstream.length === 0) return null
      if (!upstream.some(p => execPorPipeline.has(p))) return null
      const bloqueiam = upstream.filter(p => {
        const st = execPorPipeline.get(p)?.status
        return st === 'FALHA' || st === 'NAO_LIBEROU'
      })
      const total = upstream.length
      if (bloqueiam.length > 0) {
        return { kind: 'aguarde', estado: 'bloqueado', faltam: [], bloqueiam, total }
      }
      const faltam = upstream.filter(
        p => execPorPipeline.get(p)?.status !== 'SUCESSO')
      return faltam.length === 0
        ? { kind: 'aguarde', estado: 'satisfeito', faltam: [], bloqueiam: [], total }
        : { kind: 'aguarde', estado: 'aguardando', faltam, bloqueiam: [], total }
    }
    // Observadores: upstream VAZIO é o skip da guardiã (Decisão 13) — a tela
    // diz isso, em vez de prometer "aguardando" para sempre. Mesma régua do
    // Aguarde acima, que já devolvia neutro sem upstream. Evento JÁ emitido
    // (upstream desligado depois) continua aparecendo: histórico verdadeiro.
    case 'notificacao':
      return {
        kind: 'notificacao',
        emitidaEm: eventoNoPorId.get(`${n.id}:MALHA_NOTIFICACAO`) ?? null,
        semEntradas: n.upstream.length === 0,
      }
    case 'fim': {
      // ⚠️ O EVENTO NÃO É MAIS A AUTORIDADE (§9.6: "o evento vira rastro, não
      // fonte de verdade"). `eventos_no` é recortado por DATA, nunca por
      // corrida — `etl_dependencia_evento` é chaveada por (pipeline, data,
      // tipo) e o marcador do nó não carrega o id do ciclo. Então o
      // `MALHA_CONCLUIDA` que a corrida #1 de 04/08 emitiu às 04:02 continua
      // na resposta quando a lente está na corrida #2 do MESMO dia — o
      // redisparo às 05h depois de um incidente, que é gesto diário.
      //
      // Sem esta guarda o nó Fim ficaria VERDE, com o tooltip "malha concluída
      // às 04:02", a 3 cm de uma faixa dizendo "em andamento · com falha" — e
      // a aresta que chega nele viraria "trecho percorrido", também verde
      // (`estadoDoComponente`). É o defeito desta fase inteira voltando pela
      // porta do canvas: a API já parou de publicar `malha_concluida` nesse
      // caso, e deixar o nó ler o evento cru desfazia metade da correção.
      const evento = eventoNoPorId.get(`${n.id}:MALHA_CONCLUIDA`) ?? null
      return {
        kind: 'fim',
        concluidaEm: ciclo.concluido === false ? null : evento,
        semEntradas: n.upstream.length === 0,
        cicloAberto: ciclo.aberto,
      }
    }
  }
}

// ── Construção de nós/arestas ───────────────────────────────────────────────
const EDGE_ARROW = { type: MarkerType.ArrowClosed, width: 16, height: 16 }

// Id do componente no canvas: "no:{id}" — o MESMO contrato do PUT /layout
// (§9); o prefixo não colide com pipeline real (':' não é dag_id válido).
const NO_PREFIX = 'no:'
const ehNo = (rfId: string) => rfId.startsWith(NO_PREFIX)
const noRfId = (id: number) => `${NO_PREFIX}${id}`
function pontaDoCanvas(rfId: string): PontaGesto {
  return ehNo(rfId)
    ? { no: Number(rfId.slice(NO_PREFIX.length)) }
    : { pipeline: rfId }
}

// Aresta de dependência: depende_de → pipeline_name, sem rótulo (o sentido da
// seta já diz tudo — Control-M também não rotula). Linha compilada por nó de
// OUTRA malha (compilada_por, §7.4) ganha o CADEADO: tracejada + Lock no meio,
// somente leitura aqui — quem manda é o desenho da malha dona.
function depEdge(a: MalhaArestaApi): Edge {
  const e: Edge = {
    id: `dep:${a.depende_de}->${a.pipeline_name}`,
    source: a.depende_de,
    target: a.pipeline_name,
    type: 'smoothstep',
    markerEnd: EDGE_ARROW,
  }
  if (a.compilada_por) {
    e.data = { compiladaPor: a.compilada_por }
    e.style = { strokeDasharray: '6 3' }
    e.label = (
      <span
        title={`Compilada pelo Aguarde #${a.compilada_por.no} da malha `
          + `'${a.compilada_por.malha}' — somente leitura aqui; edite pelo `
          + 'desenho da malha dona.'}
        className="inline-flex items-center justify-center rounded-full border border-edge bg-panel p-0.5 text-dim"
      >
        <Lock size={10} />
      </span>
    )
  }
  return e
}

// Aresta de NÓ do desenho (F10): id "ano:{id}" — a exclusão dela é gesto com
// dry_run, nunca o DELETE /dependencias do F8.
const ANO_PREFIX = 'ano:'
function noEdge(a: MalhaArestaNoApi): Edge | null {
  const source = a.origem_pipeline
    ?? (a.origem_no != null ? noRfId(a.origem_no) : null)
  const target = a.destino_pipeline
    ?? (a.destino_no != null ? noRfId(a.destino_no) : null)
  if (!source || !target) return null   // impossível pelo CHECK da 075; defensivo
  return {
    id: `${ANO_PREFIX}${a.id}`,
    source,
    target,
    type: 'smoothstep',
    markerEnd: EDGE_ARROW,
  }
}

function nodeData(m: MalhaMembroApi): MalhaPipelineNodeData {
  return {
    name: m.pipeline_name,
    active: !!m.active,
    criticidade: m.criticidade,
    // 'on_demand' é jargão do banco — o operador lê "sob demanda" (mesma
    // tradução do card da tela Malha).
    schedule: m.schedule_type === 'on_demand' ? 'sob demanda' : m.schedule_type,
  }
}

/** Membro cuja DAG no Airflow não reflete mais o cadastro — o carimbo da 073.
 *  `dag_criada` de propósito NÃO entra: ele fica 0 durante toda a regeneração
 *  (é assim que a factory seleciona o lote), então usá-lo acenderia o chip em
 *  todos os membros a cada republicação em voo. Sem a 073 no banco a chave nem
 *  vem, e a tela não afirma nada. */
function precisaRepublicar(m: MalhaMembroApi): boolean {
  return m.publicacao_pendente === true
}

// Cor do nó no minimapa: azul da casa p/ pipeline ativo, slate p/ inativo e a
// cor de identidade p/ cada componente (mesma do chip da paleta).
function miniMapColor(n: Node): string {
  const d = n.data as (Partial<MalhaComponenteNodeData> & Partial<MalhaPipelineNodeData>) | undefined
  const tipo = d?.tipo as TipoComponente | undefined
  if (tipo && COMPONENTE_META[tipo]) return COMPONENTE_META[tipo].cor
  return d?.active ? '#1A5FA8' : '#94a3b8'
}

// ── Paleta de componentes (F12) ─────────────────────────────────────────────
// Arrastar-para-criar, no padrão da paleta das Etapas (mesmo MIME próprio).
const DND_MIME_NO = 'application/orquestra-malha-componente'
const COMPONENTES_ORDEM: TipoComponente[] = ['inicio', 'aguarde', 'notificacao', 'fim']

function ItemPaletaComponente({ tipo, desabilitado, motivo }: {
  tipo: TipoComponente
  desabilitado: boolean
  motivo?: string
}) {
  const meta = COMPONENTE_META[tipo]
  const onDragStart = (e: React.DragEvent) => {
    if (desabilitado) { e.preventDefault(); return }
    e.dataTransfer.setData(DND_MIME_NO, tipo)
    e.dataTransfer.effectAllowed = 'move'
  }
  return (
    <div
      draggable={!desabilitado}
      onDragStart={onDragStart}
      title={desabilitado ? motivo : `Arrastar para o canvas — ${meta.rotulo}`}
      className={[
        'group flex items-center gap-2 rounded-md border border-edge bg-canvas px-2 py-1.5 text-ink transition-colors',
        desabilitado
          ? 'cursor-not-allowed opacity-50'
          : 'cursor-grab hover:border-blue-300 hover:bg-edge/40 active:cursor-grabbing dark:hover:border-blue-800',
      ].join(' ')}
    >
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded ${meta.chip}`}>
        <meta.Icon size={16} strokeWidth={2.2} />
      </span>
      <span className="min-w-0 flex-1 truncate text-[11px] font-medium leading-none text-ink">
        {meta.rotulo}
      </span>
    </div>
  )
}

interface Props {
  malha: string
  readOnly?: boolean
  // ── F3 (spec-operacao-nivel-etapa §3) ──────────────────────────────────
  /** Modo com que a malha ABRE. Serve ao deep-link (?modo=execucao) e, com
   *  ele, à volta do drill-down: quem desceu para as etapas precisa voltar
   *  para a MESMA lente. Depois de aberto, quem manda é o botão da barra. */
  modoInicial?: 'montagem' | 'execucao'
  /** Data de referência com que a visão de Execução abre (?data=). */
  dataInicial?: string | null
  /** (F9) LENTE de corrida com que a Execução abre (?corrida=). O `Acompanhar`
   *  do card da lista a preenche quando há ciclo registrado — sem ela o painel
   *  cairia na corrida corrente do servidor, que é OUTRA quando o operador
   *  clicou num card que mostrava a de ontem. A data sozinha não distingue duas
   *  corridas do mesmo ODATE (é a razão de a lente existir). */
  corridaInicial?: number | null
  /** Descer até o canvas de Etapas de um pipeline, na data exibida. Ausente =
   *  o gesto some (a malha continua exatamente como era). */
  onAbrirEtapas?: (pipeline: string, data: string) => void
}

// Wrapper com o provider (necessário p/ useReactFlow/fitView).
export function MalhaEditor(props: Props) {
  return (
    <ReactFlowProvider>
      <MalhaEditorInner {...props} />
    </ReactFlowProvider>
  )
}

function MalhaEditorInner({
  malha, readOnly = false, modoInicial, dataInicial = null,
  corridaInicial = null, onAbrirEtapas,
}: Props) {
  const colorMode = useColorMode()
  const rf = useReactFlow()
  const nosMedidos = useNodesInitialized()
  const qc = useQueryClient()

  const [nodes, setNodes] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])

  // ── Realce de dependências (F1 — spec de operação no nível de etapa, §6) ──
  // Ferramenta de LEITURA, vale nos DOIS modos (Montagem e Execução): acende a
  // cadeia do item em foco e esmaece o resto. É camada de pintura sobre cópias
  // — `nodes`/`edges` seguem intocados, e com eles a seleção nativa (que move o
  // botão de excluir), o `dirty` das posições, o dry_run e a camada de status.
  // A travessia atravessa os DOIS espaços de id do canvas (pipeline e "no:<id>"
  // do componente): um Aguarde no meio do caminho faz parte da cadeia.
  const realce = useRealceDependencias(nodes, edges, colorMode === 'dark')
  const {
    focarNo: realceFocarNo, focarAresta: realceFocarAresta, limpar: realceLimpar,
  } = realce

  // Arestas aguardando a confirmação de exclusão (Delete ou botão).
  const [delEdges, setDelEdges] = useState<Edge[] | null>(null)
  const [excluindo, setExcluindo] = useState(false)
  // Gesto de componente aguardando confirmação no modal (dry_run já rodou).
  const [gesto, setGesto] = useState<GestoPendente | null>(null)
  // F13: painel de agendamento do nó Início (duplo clique ou botão).
  const [agendaAberta, setAgendaAberta] = useState(false)
  const [gestoCarregando, setGestoCarregando] = useState(false)
  const [aplicandoGesto, setAplicandoGesto] = useState(false)
  const [prendendo, setPrendendo] = useState(false)
  // F15: disparo manual da malha — dry_run aguardando confirmação no modal.
  const [disparo, setDisparo] = useState<DisparoDryResposta | null>(null)
  const [disparoCarregando, setDisparoCarregando] = useState(false)
  const [disparando, setDisparando] = useState(false)
  // F2: alinhamento da régua de data (copia a virada da malha aos membros).
  const [alinhandoVirada, setAlinhandoVirada] = useState(false)
  // Republicação da malha — dry_run aguardando confirmação no modal.
  const [republicacao, setRepublicacao] = useState<RepublicarDryResposta | null>(null)
  const [republicacaoCarregando, setRepublicacaoCarregando] = useState(false)
  const [republicando, setRepublicando] = useState(false)
  // Busca da paleta (adicionar membro).
  const [busca, setBusca] = useState('')
  // F9: Montagem (default, editável) | Execução (leitura da data de referência).
  // (F3) O valor INICIAL vem da URL quando a página o passa — é o que faz a
  // volta do drill-down cair na mesma lente. Sem prop, o default de sempre.
  const [modo, setModo] = useState<'montagem' | 'execucao'>(
    modoInicial === 'execucao' ? 'execucao' : 'montagem')
  // Data de referência pedida. null = sem query — o SERVIDOR devolve o ODATE
  // corrente (virada global de etl_app_config), e é ele que aparece no input.
  const [dataRef, setDataRef] = useState<string | null>(dataInicial ?? null)
  // F4 — a LENTE da corrida (`?corrida={id}`). A data sozinha NÃO distingue
  // duas corridas do mesmo ODATE: redisparar às 05h depois de um incidente é
  // gesto diário, e navegar por dia devolveria as duas madrugadas embaralhadas
  // numa lista só, com a segunda SOBREPONDO a primeira em cada pipeline.
  // null = sem lente explícita (o servidor usa a corrida corrente). O valor
  // INICIAL vem da URL (?corrida=), do mesmo jeito que o modo e a data: é o que
  // faz o `Acompanhar` do card cair na corrida que o card estava mostrando.
  const [corridaRef, setCorridaRef] = useState<number | null>(corridaInicial)
  // Orientação: o servidor é a fonte (viaja com o layout — todos veem o mesmo
  // desenho); o override local dá resposta imediata ao toggle enquanto o PATCH
  // viaja. Carrega a malha DONA junto: trocar de malha invalida o override
  // sozinho, sem efeito de reset (lint react-hooks/set-state-in-effect).
  const [orientacaoLocal, setOrientacaoLocal] =
    useState<{ malha: string; valor: Orientacao } | null>(null)

  const { data, isLoading, isError, error } = useQuery<MalhaDetalheApi>({
    queryKey: ['malha', malha],
    queryFn: () => apiFetch(`/malhas/${encodeURIComponent(malha)}`),
    enabled: !!malha,
  })
  // Normalização defensiva: qualquer coisa que não seja 'vertical' (chave
  // ausente, payload antigo) é horizontal — o comportamento de sempre.
  const orientacaoServidor: Orientacao =
    data?.orientacao === 'vertical' ? 'vertical' : 'horizontal'
  const orientacao: Orientacao = (orientacaoLocal && orientacaoLocal.malha === malha)
    ? orientacaoLocal.valor
    : orientacaoServidor

  // ── Visão de execução (F9): status + eventos da data de referência ────────
  const emExecucao = modo === 'execucao'
  const execQuery = useQuery<MalhaExecucaoApi>({
    queryKey: ['malha-execucao', malha, dataRef, corridaRef],
    // A lente da CORRIDA tem precedência sobre a data: quando ela está em uso
    // o ODATE vem da própria corrida (pedir os dois juntos faria a faixa falar
    // de um dia sobre a lista de outro — o servidor ignora a data de
    // propósito, e o cliente nem a manda).
    queryFn: () => apiFetch(
      `/malhas/${encodeURIComponent(malha)}/execucao`
      + (corridaRef ? `?corrida=${corridaRef}`
        : dataRef ? `?data_referencia=${encodeURIComponent(dataRef)}` : '')),
    enabled: !!malha && emExecucao,
    // ── Decisão 73 — a cadência, e o ORDENAMENTO que a torna legítima ──────
    // Até a F10 este painel perguntava `deps_svc.liberado()` POR MEMBRO
    // esperando (2 round-trips cada, 3 no modo SEQUÊNCIA): numa malha de 40
    // com 12 esperando eram 24 a 36 idas ao banco A CADA REFETCH — e é durante
    // o incidente que esse número cresce. Encurtar o intervalo com o N+1 ainda
    // no caminho MULTIPLICARIA o estrago; por isso os 15 s só entram na mesma
    // PR em que o `pendentes[]` passou a ser uma consulta de conjunto.
    //
    // Condicional, e não fixo: corrida FECHADA é histórico, e histórico não
    // muda — repetir a consulta de 15 em 15 segundos gastaria banco para
    // redesenhar exatamente a mesma tela.
    refetchInterval: q => {
      const c = (q.state.data as MalhaExecucaoApi | undefined)?.corrida
      if (!c) return 30_000          // sem ciclo: a cadência de sempre
      return c.status === 'ABERTA' ? 15_000 : 60_000
    },
  })
  const execData = execQuery.data
  // A data exibida/navegada: a pedida ou a que o servidor calculou (ODATE).
  // Com a lente ligada quem manda é a resposta — a data da CORRIDA, que é a
  // mesma que o disparo usou (§9.6: é aqui que some a divergência confessada
  // entre o painel e o disparo).
  const dataExibida = (corridaRef ? execData?.data_referencia : dataRef)
    ?? execData?.data_referencia ?? ''
  // ── F4: a corrida desta lente ────────────────────────────────────────────
  // Chave AUSENTE (não `null`) é o contrato da degradação (Decisão 41): API
  // anterior à fase, banco sem a 085 e malha sem ciclo nenhum caem no MESMO
  // lugar — o painel volta ao texto de hoje, sem exceção e sem inventar nada.
  const corrida = execData?.corrida ?? null
  const sem085 = execData?.migration_085_pendente === true
  // O que o nó Fim precisa saber do ciclo, em DOIS primitivos — e não no
  // objeto `corrida`, que traz `apurado_em` novo a cada refetch e faria o
  // efeito do canvas remontar todos os nós de 30 em 30 segundos sem nada ter
  // mudado no desenho. `concluido = null` significa "não há corrida no
  // payload": o nó volta a ler o evento, que é o comportamento de hoje.
  const cicloAberto = corrida?.status === 'ABERTA'
  const cicloConcluido = corrida === null ? null : corrida.status === 'CONCLUIDA'
  // O relógio LOCAL (Decisão 60) — o decorrido da faixa sai dele somado ao
  // `decorrido_min` que o BANCO já subtraiu; `apurado_em` fica no tooltip.
  const agoraLocal = useDecorrido(emExecucao && corrida?.status === 'ABERTA')
  const resumo = useMemo(
    () => (corrida
      ? resumoCorrida(corrida, { respostaEm: execQuery.dataUpdatedAt, agora: agoraLocal })
      : null),
    [corrida, execQuery.dataUpdatedAt, agoraLocal])

  // As corridas desta malha — o que o ◀ ▶ percorre (Decisão 42). Duas do MESMO
  // ODATE são legítimas e vêm as duas, distinguidas por `sequencia`. Sem a 085
  // (ou em API anterior) a lista sai vazia e a navegação volta a ser por DIA:
  // é a degradação por ausência de dado, não por flag.
  const corridasQuery = useQuery<CorridasResposta>({
    queryKey: ['malha-corridas', malha],
    queryFn: () => apiFetch(`/malhas/${encodeURIComponent(malha)}/corridas?limite=30`),
    enabled: !!malha && emExecucao,
    // Metade da cadência do painel: a LISTA de ciclos muda quando um ciclo
    // abre ou fecha (uma vez por madrugada), não a cada movimento de pipeline.
    // O react-query já não dispara o timer com a aba fora de foco.
    refetchInterval: 60_000,
  })
  const corridas = useMemo(() => corridasQuery.data?.corridas ?? [],
                           [corridasQuery.data])
  // F10: o índice na lista saiu junto com o ◀ ▶ (Decisão 42) — a faixa mostra
  // TODAS as corridas de uma vez, então "onde estou na fila" deixou de ser
  // uma pergunta que a tela precisa responder com um número.
  function irParaCorrida(alvo: CorridaCabecalho | null) {
    if (!alvo) return
    setCorridaRef(alvo.id)
    // A data sai do caminho: com a lente ligada ela é derivada da corrida, e
    // manter as duas produziria dois recortes disputando a mesma tela.
    setDataRef(null)
  }
  function irParaDia(dia: string | null) {
    setCorridaRef(null)
    setDataRef(dia)
  }

  // ── F10: a aba com que o painel lateral ABRE (Decisão 62) ────────────────
  // A escolha é derivada da SAÚDE, e re-derivada quando a corrida em foco
  // MUDA — nunca quando a saúde muda no meio do acompanhamento. Um painel que
  // troca de aba sozinha às 3h tira o operador de onde ele estava lendo, que é
  // o oposto do que a Decisão 62 quer.
  const [abaPainel, setAbaPainel] = useState<AbaCorrida>('eventos')
  const abaDerivadaDe = useRef<number | null | undefined>(undefined)
  useEffect(() => {
    const id = corrida?.id ?? null
    if (abaDerivadaDe.current === id) return
    abaDerivadaDe.current = id
    setAbaPainel(abaInicialDaCorrida(corrida))
  }, [corrida])

  // ── F10: o prazo POR PADRÃO é o próximo gatilho da malha (Decisão 61) ────
  // Recalculado no tique do relógio LOCAL — é hora de parede contra hora de
  // parede, a única conta de tempo desta camada que não toca o banco.
  const proximoGatilho = useMemo(
    () => proximaExecucao(data?.agendamento ?? null, new Date(agoraLocal)),
    [data?.agendamento, agoraLocal])

  // ── F10: os nós SEGURADOS (Decisão 66/2) ────────────────────────────────
  // Hoje o cadeado existe só no nó, sem banner e sem contador: quem chega às
  // 3h não tem como saber que a malha está parada porque alguém a segurou às
  // 02:40. O mais antigo vem primeiro — é ele que o botão `Soltar` nomeia.
  const nosSegurados = useMemo<NoSegurado[]>(() => (data?.nos ?? [])
    .filter(n => !!n.retido_em)
    .map(n => ({
      id: n.id,
      tipo: n.tipo,
      rotulo: COMPONENTE_META[n.tipo as TipoComponente]?.rotulo ?? n.tipo,
      retido_em: n.retido_em ?? null,
      retido_por: n.retido_por ?? null,
    }))
    .sort((a, b) => (a.retido_em ?? '').localeCompare(b.retido_em ?? '')),
    [data?.nos])

  // ── F10: o aviso preso na fila do Teams (Decisão 66/3) ──────────────────
  // Só os eventos DO CICLO entram: `MALHA_FALHOU` sem `notificado_em` é a
  // malha falhando em silêncio para todo o plantão. A carência mora no módulo
  // puro, e a idade é medida entre dois carimbos do BANCO (Decisão 60).
  const avisoPreso = useMemo(
    () => avisoPresoNaFila(execData?.eventos_corrida ?? [], corrida?.apurado_em),
    [execData?.eventos_corrida, corrida?.apurado_em])

  // Execução MAIS RECENTE por pipeline (o endpoint já entrega uma por membro —
  // regra do §6 risco 6 da spec).
  const execPorPipeline = useMemo(() => {
    const map = new Map<string, ExecucaoPipeline>()
    for (const e of execData?.execucoes ?? []) map.set(e.pipeline_name, e)
    return map
  }, [execData])
  // Painel de eventos UNIFICADO (F15): eventos de pipeline (F9) + eventos dos
  // nós observadores (F14, marcador já resolvido pelo servidor) — o painel
  // nunca esconde linha que o banco tem (contrato F9).
  const eventos = useMemo<EventoPainel[]>(() => {
    const lista: EventoPainel[] = [
      // `notificado_em` é REPASSADO com a chave que veio (spread), e não
      // normalizado para `null`: a ausência dela significa "o banco não tem a
      // coluna", que é outra coisa que "está na fila e ninguém foi avisado".
      ...(execData?.eventos ?? []).map(ev => ({
        rotulo: ev.pipeline_name, ehNo: false, tipo: ev.tipo,
        criado_em: ev.criado_em, mensagem: ev.mensagem,
        ...('notificado_em' in ev ? { notificado_em: ev.notificado_em } : {}),
      })),
      ...(execData?.eventos_no ?? []).map(ev => ({
        rotulo: `${COMPONENTE_META[ev.tipo_no as TipoComponente]?.rotulo ?? ev.tipo_no} #${ev.no_id}`,
        ehNo: true, tipo: ev.tipo, criado_em: ev.criado_em,
        mensagem: ev.mensagem,
        ...('notificado_em' in ev ? { notificado_em: ev.notificado_em } : {}),
      })),
      // F7: os eventos do CICLO. Até aqui eles eram gravados e NUNCA chegavam
      // à tela — a tabela de eventos é chaveada por pipeline e a corrida não é
      // um pipeline, então o painel os descartava em silêncio. São eles que
      // explicam o que mudou no prazo: o aviso de atraso e o crédito de
      // retenção (Decisão 61). O rótulo é "corrida", nunca o marcador
      // `#corrida:{id}` (Decisão 74: nome de máquina não vai à tela).
      ...(execData?.eventos_corrida ?? []).map(ev => ({
        rotulo: 'corrida', ehNo: true,
        tipo: ev.tipo, criado_em: ev.criado_em,
        mensagem: ev.mensagem,
        ...('notificado_em' in ev ? { notificado_em: ev.notificado_em } : {}),
      })),
    ]
    return lista.sort((a, b) => b.criado_em.localeCompare(a.criado_em))
  }, [execData])
  // F15: evento mais recente por nó observador E tipo — a fonte do estado
  // aceso/apagado de Notificação ("emitida às") e Fim ("concluída às").
  const eventoNoPorId = useMemo(() => {
    const m = new Map<string, string>()
    for (const ev of [...(execData?.eventos_no ?? [])]
      .sort((a, b) => b.criado_em.localeCompare(a.criado_em))) {
      const k = `${ev.no_id}:${ev.tipo}`
      if (!m.has(k)) m.set(k, ev.criado_em)
    }
    return m
  }, [execData])
  // Edição travada na visão de execução — MESMO mecanismo do readOnly da F8.
  const travado = readOnly || emExecucao

  // ── F3: descer da malha até o canvas de Etapas ────────────────────────────
  // GESTO ESCOLHIDO E REGISTRADO: **botão, em dois lugares** — um chip no
  // PRÓPRIO card do pipeline (direto, onde o olho já está) e um botão na barra
  // de ações com o pipeline selecionado (o caminho que segue a gramática do
  // "Excluir componente"/"Agendamento" da montagem).
  //   • clique simples NÃO: desde a F1 ele é o realce de dependências, e
  //     roubá-lo tiraria a ferramenta de leitura de dentro da lente em que ela
  //     é mais útil;
  //   • duplo clique NÃO: medido no dev, `onNodeDoubleClick` está MORTO neste
  //     app — ver o comentário longo no próprio handler, mais abaixo. Anunciar
  //     um gesto que não dispara seria pior que não ter gesto.
  // A DATA vai junto: descer sempre abre o MESMO dia que a malha está
  // mostrando (é o ponto do drill-down — outra data seria outra história).
  // Declarado aqui em cima porque o rebuild dos nós (efeito do `grafo`) põe o
  // atalho no data de cada card.
  const descerParaEtapas = useCallback((pipelineId: string) => {
    if (!onAbrirEtapas || !dataExibida || ehNo(pipelineId)) return
    onAbrirEtapas(pipelineId, dataExibida)
  }, [onAbrirEtapas, dataExibida])

  // ── F10: um clique até o problema, SEM sair da lente ─────────────────────
  // Clicar numa linha do painel acende a cadeia (o mesmo `PainelRealce` do
  // canvas) e CENTRALIZA o nó. As duas coisas juntas: acender sem centralizar
  // deixa o realce fora da viewport numa malha de 40 nós — o operador clica,
  // "nada acontece" e ele volta a varrer o desenho com o olho, que é
  // exatamente o gesto que esta fase existe para eliminar.
  //
  // `maxZoom` limita a aproximação: sem ele o React Flow enquadra UM nó e
  // aproxima até perder a vizinhança, que é justamente o contexto que o realce
  // acabou de acender.
  const focarPipeline = useCallback((pipeline: string) => {
    realceFocarNo(pipeline)
    const alvo = rf.getNode(pipeline)
    if (alvo) rf.fitView({ nodes: [{ id: pipeline }], duration: 250, maxZoom: 1.1 })
  }, [realceFocarNo, rf])

  // Deploy parcial: migration 067 ausente (flag da API) ou API anterior à F8
  // (sem a chave `arestas`) — o diagrama abre só com os nós e avisa (nunca um
  // 500 na cara), e a criação de dependências fica desligada.
  const depsIndisponiveis = !!data
    && (data.migration_067_pendente === true || !Array.isArray(data.arestas))
  // Idem para a 075 (F12): sem ela não há componentes — a paleta desliga e o
  // aviso explica; o resto do diagrama segue como na F8.
  const nosIndisponiveis = !!data
    && (data.migration_075_pendente === true || !Array.isArray(data.nos))

  // Mapa id do nó → tipo (rótulos de gesto/aviso) e avisos persistentes §2.2.
  const tipoDoNo = useMemo(() => {
    const m = new Map<number, string>()
    for (const n of data?.nos ?? []) m.set(n.id, n.tipo)
    return m
  }, [data])
  const avisosDesenho = useMemo<AvisoDesenho[]>(
    () => (Array.isArray(data?.avisos) ? data.avisos : []), [data])
  // F15: os avisos de CONTRADIÇÃO (raiz assinada com dependência) valem
  // também na Execução — o disparo manual parte a raiz por cima do
  // predecessor (trigger manual não consulta a liberação).
  const avisosContradicao = useMemo(
    () => avisosDesenho.filter(a => a.tipo === 'contradicao'), [avisosDesenho])

  // Rótulo curto de uma ponta/nó para mensagens ("Aguarde #8" / nome do pipe).
  const rotuloPontaGesto = useCallback((p: PontaGesto): string => {
    if ('pipeline' in p) return p.pipeline
    const t = tipoDoNo.get(p.no) as TipoComponente | undefined
    return `${t && COMPONENTE_META[t] ? COMPONENTE_META[t].rotulo : 'nó'} #${p.no}`
  }, [tipoDoNo])

  // Espelho dos estados p/ callbacks estáveis (padrão do FluxoEditor).
  const nodesRef = useRef<Node[]>([])
  useEffect(() => { nodesRef.current = nodes }, [nodes])
  const edgesRef = useRef<Edge[]>([])
  useEffect(() => { edgesRef.current = edges }, [edges])

  // ── Grafo derivado da API (puro) ──────────────────────────────────────────
  // Arestas prontas + BASELINE de posições: o que o SERVIDOR conhece de cada
  // nó (layout salvo em etl_malha_pipeline/etl_malha_no, senão o auto-layout
  // topológico do liveLayout — colunas = ondas do grafo, componentes
  // incluídos). É contra este baseline que o "Salvar posições" decide.
  const grafo = useMemo(() => {
    if (!data) return null
    const membros = data.membros ?? []
    const arestas = Array.isArray(data.arestas) ? data.arestas : []
    // Nó com tipo fora do domínio (SQL direto) é ignorado — as arestas dele
    // cairiam do desenho junto (degradação, nunca tela quebrada).
    const nos = (Array.isArray(data.nos) ? data.nos : [])
      .filter(n => n.tipo in COMPONENTE_META)
    const arestasNo = Array.isArray(data.arestas_no) ? data.arestas_no : []
    const novasEdges = [
      ...arestas.map(depEdge),
      ...arestasNo.map(noEdge).filter((e): e is Edge => e !== null),
    ]
    // Contagens de arestas de nó — o subtítulo honesto dos cards.
    const entradasNo = new Map<number, number>()
    const saidasNo = new Map<number, number>()
    // F15: pipelines de SAÍDA por nó — as raízes do Início na camada de
    // execução ("raízes na data: M/N" conta execução registrada de cada uma).
    const saidasPipelineNo = new Map<number, string[]>()
    for (const a of arestasNo) {
      if (a.destino_no != null) {
        entradasNo.set(a.destino_no, (entradasNo.get(a.destino_no) ?? 0) + 1)
      }
      if (a.origem_no != null) {
        saidasNo.set(a.origem_no, (saidasNo.get(a.origem_no) ?? 0) + 1)
        if (a.destino_pipeline) {
          const lista = saidasPipelineNo.get(a.origem_no) ?? []
          lista.push(a.destino_pipeline)
          saidasPipelineNo.set(a.origem_no, lista)
        }
      }
    }
    // O auto-layout do baseline segue a orientação SALVA (a que o servidor
    // conhece) — o override local ainda-não-persistido não muda o baseline.
    const auto = liveLayout(
      [...membros.map(m => ({ id: m.pipeline_name })),
       ...nos.map(n => ({ id: noRfId(n.id) }))],
      novasEdges, new Map(),
      data.orientacao === 'vertical' ? 'vertical' : 'horizontal')
    const baseline = new Map<string, { x: number; y: number }>()
    for (const m of membros) {
      const salva = (m.layout_x != null && m.layout_y != null)
        ? { x: m.layout_x, y: m.layout_y }
        : null
      const base = salva ?? auto[m.pipeline_name] ?? { x: 0, y: 0 }
      baseline.set(m.pipeline_name, { x: Math.round(base.x), y: Math.round(base.y) })
    }
    for (const n of nos) {
      const salva = (n.layout_x != null && n.layout_y != null)
        ? { x: n.layout_x, y: n.layout_y }
        : null
      const base = salva ?? auto[noRfId(n.id)] ?? { x: 0, y: 0 }
      baseline.set(noRfId(n.id), { x: Math.round(base.x), y: Math.round(base.y) })
    }
    return { membros, nos, novasEdges, baseline, entradasNo, saidasNo,
             saidasPipelineNo }
  }, [data])

  // (Re)constrói nós/arestas a partir do grafo derivado. O rebuild PRESERVA a
  // posição atual de nó que já está no canvas (as arestas são persistidas na
  // hora, então todo refetch é seguro; só a posição é estado local até o
  // "Salvar posições"). Na visão de execução (F9) o mesmo rebuild anexa o
  // status da data como CAMADA no data do nó — membro sem linha em
  // etl_pipeline_execucao fica sem camada (exec: null), nunca com cor inventada.
  // Os COMPONENTES (F12) entram no MESMO array de nós, antes do setEdges —
  // React Flow descarta aresta órfã em silêncio, e aqui nunca há órfã. Na
  // Execução eles ficam neutros (a camada de estado dos nós é a F15).
  // A orientação entra no data de TODOS os nós (rebuild ao trocar): é ela que
  // decide onde os handles ancoram — a visão de Execução herda a mesma, porque
  // o grafo é o mesmo.
  useEffect(() => {
    if (!grafo) return
    const atuais = new Map(nodesRef.current.map(n => [n.id, n.position]))
    // Estado de cada COMPONENTE na data — calculado uma vez e reusado pelo card
    // e pela linha (duas leituras da mesma verdade, nunca dois cálculos).
    const camadaExecNos = emExecucao && !!execData
      && execData.migration_067_pendente !== true
    const estadoPonta = new Map<string, EstadoElemento>()
    if (camadaExecNos) {
      for (const m of grafo.membros) {
        estadoPonta.set(m.pipeline_name,
          estadoDoPipeline(execPorPipeline.get(m.pipeline_name)?.status))
      }
    }
    setNodes([
      ...grafo.membros.map(m => {
        const exec = emExecucao ? execPorPipeline.get(m.pipeline_name) : undefined
        return {
          id: m.pipeline_name,
          type: 'malhaPipeline' as const,
          position: atuais.get(m.pipeline_name)
            ?? grafo.baseline.get(m.pipeline_name)
            ?? { x: 0, y: 0 },
          data: {
            ...nodeData(m),
            orientacao,
            exec: exec ? { status: exec.status, titulo: tituloExecucao(exec) } : null,
            // (F3) Atalho de descer até as etapas — só na Execução e só quando
            // a página ofereceu o destino. Fora disso é `null` e o card fica
            // exatamente como era.
            abrirEtapas: (emExecucao && onAbrirEtapas && dataExibida)
              ? () => descerParaEtapas(m.pipeline_name)
              : null,
            dataExecucao: dataExibida || null,
            // F13/F15: badge de contradição no pipeline (raiz assinada com
            // dependência) — nos DOIS modos: na Execução ele convive com o
            // badge de status (cantos opostos do card).
            contradicao: !!m.agenda_contradicao,
            // Chip "republicar" — só na MONTAGEM: é lá que o gesto vive, e na
            // Execução o card já carrega a camada de status.
            publicacaoPendente: !emExecucao && precisaRepublicar(m),
          },
        }
      }),
      ...grafo.nos.map(n => {
        const tipo = n.tipo as TipoComponente
        // F15: a camada de execução só existe com a visão aberta E dados da
        // 067 disponíveis — deploy parcial degrada para o card neutro.
        const camadaExec = camadaExecNos
        const execNo = camadaExec
          ? execDoComponente(n, tipo,
              grafo.saidasPipelineNo.get(n.id) ?? [],
              execPorPipeline, eventoNoPorId,
              data?.agendamento ?? null,
              { aberto: cicloAberto, concluido: cicloConcluido })
          : null
        if (camadaExec) estadoPonta.set(noRfId(n.id), estadoDoComponente(execNo))
        return {
          id: noRfId(n.id),
          type: COMPONENTE_META[tipo].nodeType,
          position: atuais.get(noRfId(n.id))
            ?? grafo.baseline.get(noRfId(n.id))
            ?? { x: 0, y: 0 },
          data: {
            noId: n.id,
            tipo,
            entradas: grafo.entradasNo.get(n.id) ?? 0,
            saidas: grafo.saidasNo.get(n.id) ?? 0,
            config: n.config,
            orientacao,
            // F13: o Início mostra o resumo do agendamento da malha e o
            // badge de contradição quando alguma raiz assinada por ele
            // ganhou dependência por outra porta (§2.2).
            agendaResumo: tipo === 'inicio'
              ? (data?.agendamento_resumo ?? null)
              : null,
            // F15: a contradição vale nos DOIS modos — na Execução ela é
            // ainda mais importante (o disparo manual atropela a
            // dependência); o badge do Início não colide com camada nenhuma.
            contradicao: tipo === 'inicio'
              && grafo.membros.some(
                m => m.agenda_contradicao && m.agenda_no === n.id),
            execNo,
            retidoEm: n.retido_em,
            retidoPor: n.retido_por,
          } satisfies MalhaComponenteNodeData,
        }
      }),
    ])
    // A LINHA conta o caminho da corrida: verde onde já passou, azul animada na
    // frente que está avançando, vermelha onde parou. Fora da Execução (ou sem
    // dado na data) as arestas ficam exatamente como na Montagem.
    setEdges(camadaExecNos
      ? grafo.novasEdges.map(e => arestaComFluxo(
          e,
          estadoDaAresta(estadoPonta.get(e.source) ?? null,
                         estadoPonta.get(e.target) ?? null),
          colorMode === 'dark'))
      : grafo.novasEdges)
  }, [grafo, setNodes, setEdges, emExecucao, execPorPipeline, eventoNoPorId,
      execData, orientacao, data, onAbrirEtapas, dataExibida, descerParaEtapas,
      // F4: só os dois PRIMITIVOS do ciclo entram na chave (não o objeto
      // `corrida` inteiro) — são a única parte dela que muda o desenho, e o
      // payload traz `apurado_em` novo a cada refetch: a corrida inteira
      // remontaria todos os nós de 30 em 30 segundos, sem nada ter mudado no
      // grafo.
      cicloAberto, cicloConcluido, colorMode])

  // dirty = alguma posição difere do baseline do servidor (arredondado — é o
  // que o PUT envia). Mover um nó e devolvê-lo ao lugar volta a desabilitar o
  // botão: salvar sem mudança é no-op de verdade (aceite da F8). Depois do
  // PUT, o refetch traz o layout recém-salvo e o dirty cai sozinho.
  const dirty = useMemo(() => {
    if (!grafo) return false
    return nodes.some(n => {
      const b = grafo.baseline.get(n.id)
      return !b || Math.round(n.position.x) !== b.x || Math.round(n.position.y) !== b.y
    })
  }, [nodes, grafo])

  // Enquadra o diagrama ao abrir/trocar de malha.
  // (F3) O MODO entra na chave junto com a chegada do payload de execução: são
  // eles que acrescentam/retiram o painel de eventos à esquerda, os banners e a
  // legenda — ou seja, mudam a área do canvas. Antes desta fase o efeito só
  // olhava a malha, e o enquadramento ficava obsoleto ao entrar na Execução;
  // com o deep-link `?modo=execucao` isso passou a ser a PRIMEIRA coisa que o
  // operador vê. Só a PRESENÇA de `execData` entra na chave — o polling de 30s
  // traz objeto novo e não pode arrancar o zoom de quem está investigando.
  const fittedRef = useRef<string | null>(null)
  const chaveFit = `${malha}|${emExecucao ? 'exec' : 'montagem'}`
    + `|${emExecucao && execData ? 'carregado' : '-'}`
  // ⚠️ ESPERA a MEDIÇÃO dos nós (`useNodesInitialized`). Antes desta fase o fit
  // saía 90 ms depois do payload, e nesse instante o React Flow ainda não tinha
  // medido os nós: o bounding box saía minúsculo e o enquadramento abria com
  // zoom altíssimo, mostrando um nó só. Dava para não notar porque um segundo
  // fit (troca de modo, reorganizar) consertava — mas com o deep-link da F3 o
  // canvas em Execução passou a ser a PRIMEIRA tela do drill-down, e primeira
  // impressão torta é defeito.
  useEffect(() => {
    if (!data || !nosMedidos || fittedRef.current === chaveFit) return
    fittedRef.current = chaveFit
    const t = setTimeout(() => rf.fitView({ padding: 0.2, duration: 250 }), 90)
    return () => clearTimeout(t)
  }, [data, chaveFit, rf, nosMedidos])

  const onNodesChange = useCallback(
    (changes: NodeChange<Node>[]) => {
      setNodes(nds => applyNodeChanges(changes, nds))
    },
    [setNodes],
  )

  // ── Avisos e efeitos nos gestos (F12) ─────────────────────────────────────
  // Toast SÓ dos avisos que o gesto CRIOU (§2.2: "no momento de consequência")
  // — os que já estavam no banner não repetem; o banner persiste todos.
  const mostrarAvisos = useCallback((avisos: AvisoDesenho[] | undefined) => {
    const novos = (avisos ?? []).filter(a =>
      !avisosDesenho.some(b => b.no === a.no && b.mensagem === a.mensagem))
    novos.slice(0, 3).forEach(a => toast.info(a.mensagem))
    if (novos.length > 3) {
      toast.info(`+${novos.length - 3} avisos — veja o banner do desenho.`)
    }
  }, [avisosDesenho])

  // Resumo do efeito aplicado (o modal já mostrou a lista; o toast fecha o
  // laço) + republicação por dependente afetado (Decisão 6/D30).
  const resumoEfeito = useCallback((efeito: EfeitoGesto | undefined) => {
    if (!efeito) return
    const partes: string[] = []
    if (efeito.dependencias_criar.length > 0) {
      partes.push(`${efeito.dependencias_criar.length} criada(s)`)
    }
    if (efeito.dependencias_remover.length > 0) {
      partes.push(`${efeito.dependencias_remover.length} removida(s)`)
    }
    if (efeito.dependencias_transferir.length > 0) {
      partes.push(`${efeito.dependencias_transferir.length} transferida(s)`)
    }
    if (partes.length > 0) toast.info(`Dependências: ${partes.join(' · ')}.`)
    // F13: agendamento plantado/desligado nas raízes — o modal já listou o
    // de → para; o toast fecha o laço.
    if (efeito.agendamentos.length > 0) {
      toast.info(efeito.agendamentos.length === 1
        ? `A raiz ${efeito.agendamentos[0].pipeline} mudou de agendamento.`
        : `${efeito.agendamentos.length} raízes mudaram de agendamento.`)
    }
    efeito.republicar.slice(0, 3).forEach(nome => toast.info(msgRepublicar(nome)))
    if (efeito.republicar.length > 3) {
      toast.info(`+${efeito.republicar.length - 3} DAGs precisam ser republicadas.`)
    }
  }, [])

  const invalidarPosGesto = useCallback(() => {
    // A compilação é GLOBAL (067): toda malha que contenha as pontas muda —
    // mesma regra do F8; pipelines p/ o badge de publicação pendente.
    qc.invalidateQueries({ queryKey: ['malha'] })
    qc.invalidateQueries({ queryKey: ['pipelines'] })
  }, [qc])

  // ── Disparo manual da malha (F15) ─────────────────────────────────────────
  // Mesma permissão do botão de rodar pipeline (acao_executar) — o servidor
  // exige por baixo de qualquer forma.
  const user = useAuthStore(s => s.user)
  const isAdmin = useAuthStore(s => s.isAdmin)
  const podeExecutar = isAdmin() || !!user?.permissoes?.includes('acao_executar')

  // dry_run ANTES do gesto (§7.2): o modal mostra raízes + ODATE + avisos —
  // nada foi disparado ainda. A data enviada é a EXIBIDA (WYSIWYG: o que o
  // operador vê é o que as raízes recebem no conf).
  const abrirDisparo = useCallback(async () => {
    if (disparoCarregando) return
    setDisparoCarregando(true)
    try {
      const r = await apiFetch<DisparoDryResposta>(
        `/malhas/${encodeURIComponent(malha)}/disparo`, {
          method: 'POST',
          body: JSON.stringify({
            dry_run: true,
            ...(dataExibida ? { data_referencia: dataExibida } : {}),
          }),
        })
      setDisparo(r)
    } catch (err) {
      // 422 (sem Início / sem raiz / data inválida) e 503 (075) chegam como
      // detail pt-BR — o servidor é a autoridade.
      const httpErr = err as Error & { status?: number }
      toast.error(httpErr.message || 'Erro ao preparar o disparo da malha')
    } finally {
      setDisparoCarregando(false)
    }
  }, [disparoCarregando, malha, dataExibida])

  // Confirmar: re-envia SEM dry_run com a MESMA data mostrada no modal. O
  // resultado é reportado POR RAIZ — sucesso agregado + um toast de erro por
  // falha (nunca escondido num "ok" genérico).
  const confirmarDisparo = useCallback(async () => {
    if (!disparo || disparando) return
    setDisparando(true)
    try {
      const r = await apiFetch<DisparoResposta>(
        `/malhas/${encodeURIComponent(malha)}/disparo`, {
          method: 'POST',
          body: JSON.stringify({ data_referencia: disparo.data_referencia }),
        })
      // F3: o recarimbo vem ANTES do sucesso — mudança em histórico de
      // execução tem de ser dita, mesmo quando o operador pediu que fosse
      // automática.
      if (r.equalizados?.length) {
        toast.info(r.equalizados.length === 1
          ? `Data equalizada: ${r.equalizados[0].pipeline} passou de ${r.equalizados[0].de} para ${r.equalizados[0].para}.`
          : `${r.equalizados.length} execuções tiveram a data de referência equalizada para ${r.data_referencia}.`)
      }
      if (r.disparadas.length > 0) {
        toast.success(r.disparadas.length === 1
          ? `1 raiz disparada com data de referência ${r.data_referencia} — a cadeia anda pelo push.`
          : `${r.disparadas.length} raízes disparadas com data de referência ${r.data_referencia} — a cadeia anda pelo push.`)
      }
      r.falhas.forEach(f => toast.error(`${f.pipeline}: ${f.erro}`))
      if (r.disparadas.length === 0 && r.falhas.length === 0) {
        toast.info('Nenhuma raiz para disparar.')
      }
      qc.invalidateQueries({ queryKey: ['malha-execucao', malha] })
    } catch (err) {
      const httpErr = err as Error & { status?: number }
      toast.error(httpErr.message || 'Erro ao disparar a malha')
    } finally {
      setDisparando(false)
      setDisparo(null)
    }
  }, [disparo, disparando, malha, qc])

  // Membros cuja DAG no Airflow não reflete mais o cadastro — o contador do
  // botão de republicação. Zero NÃO desabilita o botão: republicar com tudo
  // em dia é legítimo (regerar depois de um deploy, por exemplo).
  const membrosDesatualizados = useMemo(
    () => (data?.membros ?? []).filter(precisaRepublicar).length,
    [data?.membros])

  // Membro que TEM predecessor mas continua com agendamento próprio: a DAG
  // dele não foi republicada, então ele dispara fora da malha, calcula a
  // própria data de referência e mistura a corrida. É o sintoma que precede o
  // estrago — e o único que aparece ANTES de a malha rodar errado.
  const membrosForaDaMalha = useMemo(
    () => (data?.membros ?? [])
      .filter(m => (m.qtd_predecessores ?? 0) > 0
        && !!m.schedule_type && m.schedule_type !== 'on_demand')
      .map(m => m.pipeline_name),
    [data?.membros])

  // F2: copia a virada da MALHA para todos os membros. Reenvia a própria
  // virada salva — o gesto é "alinhar", não "mudar a régua": trocar a régua é
  // outra decisão, e ela mora no painel de agendamento.
  // A virada sai do objeto ANTES do callback: `data?.x` na lista de deps
  // impede o compilador do React de preservar a memoização.
  const viradaSalva = data?.hora_virada ?? null
  const alinharVirada = useCallback(async () => {
    if (alinhandoVirada) return
    setAlinhandoVirada(true)
    try {
      const r = await apiFetch<{ equalizados?: string[]; migration_081_pendente?: boolean }>(
        `/malhas/${encodeURIComponent(malha)}`, {
          method: 'PATCH',
          body: JSON.stringify({ hora_virada: viradaSalva }),
        })
      if (r.migration_081_pendente) {
        toast.error('migration 081 pendente neste ambiente — a régua de data da malha ainda não pode ser salva.')
      } else {
        const n = r.equalizados?.length ?? 0
        toast.success(n === 1
          ? '1 pipeline alinhado à data da malha — republique-o para a régua valer no Airflow.'
          : `${n} pipelines alinhados à data da malha — republique-os para a régua valer no Airflow.`)
        qc.invalidateQueries({ queryKey: ['malha', malha] })
        qc.invalidateQueries({ queryKey: ['pipelines'] })
      }
    } catch (err) {
      const httpErr = err as Error & { status?: number }
      toast.error(httpErr.message || 'Erro ao alinhar a data da malha')
    } finally {
      setAlinhandoVirada(false)
    }
  }, [alinhandoVirada, malha, viradaSalva, qc])

  // 082: SEGURAR/soltar o Aguarde. A trava vive no nó e é obedecida pelo
  // predicado canônico — por isso o gesto é só um POST: nada aqui precisa
  // saber quem são os dependentes.
  const [retendo, setRetendo] = useState(false)
  // O rótulo da mensagem sai do DESENHO, não do botão: o toast precisa dizer
  // "Início" ou "Aguarde" mesmo quando o gesto vier de outro caminho.
  const ehInicioNo = useCallback(
    (noId: number) => grafo?.nos.find(n => n.id === noId)?.tipo === 'inicio',
    [grafo])
  const alternarRetencao = useCallback(async (noId: number, reter: boolean) => {
    if (retendo) return
    setRetendo(true)
    try {
      const r = await apiFetch<{
        dependentes?: string[]
        // F7: o servidor é quem sabe se há ciclo em voo e quanto de limite foi
        // creditado — os dois vêm da MESMA transação do gesto. Derivar isso no
        // cliente exigiria um refetch que ainda não aconteceu.
        aviso?: string
        credito_teto?: { minutos: number; teto_em: string | null }
      }>(
        `/malhas/${encodeURIComponent(malha)}/nos/${noId}/retencao`, {
          method: 'POST',
          body: JSON.stringify({ reter }),
        })
      if (reter) {
        toast.success(ehInicioNo(noId)
          ? `Início #${noId} SEGURADO — a malha não parte até você soltar.`
          : `Aguarde #${noId} SEGURADO — nada passa por ele até você soltar.`)
        // Decisão 45 — a regra DITA antes. Segurar o Início com corrida em voo
        // é o gesto mais mal-entendido da tela: parece "parar a malha" e não
        // para; ele segura a PARTIDA. Sem esta frase o operador segura o Início
        // às 3h achando que travou o ciclo que está rodando, e o ciclo
        // continua. O texto vem do servidor e não traz "#N" (Decisão 74).
        if (r.aviso) toast.info(r.aviso)
      } else {
        const n = r.dependentes?.length ?? 0
        // Soltar não dispara na hora: quem estava preso parte no próximo
        // publish do predecessor ou no próximo ciclo da guardiã.
        const rotulo = ehInicioNo(noId) ? 'Início' : 'Aguarde'
        toast.success(n > 0
          ? `${rotulo} #${noId} liberado — ${n} pipeline(s) voltam a ser avaliados no próximo ciclo.`
          : `${rotulo} #${noId} liberado — a malha volta a partir no próximo horário agendado.`)
        // Decisão 61 — o crédito NUNCA é silencioso. A barra do limite anda
        // para trás neste exato instante, e uma barra de prazo que recua sem
        // explicação destrói a confiança em todas as outras.
        if (r.credito_teto) {
          toast.info(`O tempo em que a malha ficou segurada foi devolvido ao `
            + `limite de segurança: +${textoDuracao(r.credito_teto.minutos)}`
            + ' — a corrida não expira por causa da retenção.')
        }
      }
      qc.invalidateQueries({ queryKey: ['malha', malha] })
      qc.invalidateQueries({ queryKey: ['malha-execucao', malha] })
    } catch (err) {
      const httpErr = err as Error & { status?: number }
      toast.error(httpErr.message || 'Erro ao mudar a retenção do Aguarde')
    } finally {
      setRetendo(false)
    }
  }, [retendo, malha, qc, ehInicioNo])

  // ── F10: a PORTA DE SAÍDA do operador (§6.8, Decisões 32 e 62) ───────────
  // Sem ela, a única saída para uma corrida travada às 3h seria esperar as 24h
  // do teto ou apagar a malha — e teto de 24h não é ferramenta de plantão, é
  // espera. O botão existe em TODA corrida ABERTA; o que muda por estado é o
  // texto da confirmação, que é onde mora a consequência.
  const [encerrando, setEncerrando] = useState(false)
  const encerrarCorrida = useCallback(async (motivo: string) => {
    if (!corrida || encerrando) return
    setEncerrando(true)
    try {
      const r = await apiFetch<{ aviso?: string }>(
        `/malhas/${encodeURIComponent(malha)}/corridas/${corrida.id}/encerrar`,
        { method: 'POST', body: JSON.stringify({ motivo }) })
      toast.success('Corrida encerrada — o disparo desta malha volta a funcionar.')
      // O aviso do SERVIDOR não é engolido: é ele que diz o que NÃO aconteceu
      // ("os pipelines em execução continuam rodando"), e essa é a metade da
      // verdade que impede o operador de achar que "encerrar" é "matar".
      if (r.aviso) toast.info(r.aviso)
      qc.invalidateQueries({ queryKey: ['malha-execucao', malha] })
      qc.invalidateQueries({ queryKey: ['malha-corridas', malha] })
      qc.invalidateQueries({ queryKey: ['malhas'] })
    } catch (err) {
      toast.error((err as Error).message || 'Erro ao encerrar a corrida')
    } finally {
      setEncerrando(false)
    }
  }, [corrida, encerrando, malha, qc])

  // ── F10: `↻ reexecutar` de um travado (Decisão 65) ──────────────────────
  // O gesto mais delicado do modelo não pode virar um clique de 3h no escuro:
  // o botão abre a PRÉVIA que já existe (`ModalRerunEtapa`), e é ela que traz
  // do servidor a frase do efeito no ciclo em voo — *"esta reexecução entra na
  // corrida de 04/08; o relógio de fechamento não reinicia por este gesto"*.
  //
  // A prévia é por ETAPA (o clear do Airflow é por task), então o alvo é a
  // PRIMEIRA etapa do pipeline, resolvida no clique. O que exatamente será
  // reexecutado continua sendo mostrado pelo modal ANTES de confirmar — é o
  // contrato dele desde a F4 de operação por etapa, e é o que torna honesto
  // oferecer o gesto a partir de um nó de malha.
  const [rerunAlvo, setRerunAlvo] = useState<
    { pipeline: string; taskId: string } | null>(null)
  const [resolvendoRerun, setResolvendoRerun] = useState(false)
  const abrirReexecucao = useCallback(async (pipeline: string) => {
    if (resolvendoRerun) return
    setResolvendoRerun(true)
    try {
      const r = await apiFetch<{ nodes?: { job_name: string }[] }>(
        `/pipelines/${encodeURIComponent(pipeline)}/fluxo`)
      const primeira = r.nodes?.[0]?.job_name
      if (!primeira) {
        // Sem etapa não há o que reexecutar — e mandar o operador ao modal
        // para descobrir isso lá dentro seria gastar o clique dele.
        toast.error(`Não encontrei as etapas de ${pipeline} para reexecutar. `
          + 'Abra "etapas" e escolha o ponto de retomada.')
        return
      }
      setRerunAlvo({ pipeline, taskId: primeira })
    } catch (err) {
      toast.error((err as Error).message
        || `Não foi possível ler as etapas de ${pipeline}`)
    } finally {
      setResolvendoRerun(false)
    }
  }, [resolvendoRerun])

  // ── Republicação da malha (dry_run → modal → write) ───────────────────────
  // Mudar o desenho grava a dependência na hora; a DAG do Airflow só passa a
  // obedecê-la depois de regerada. Este é o "Publicar nova versão" da tela
  // Pipelines aplicado à malha inteira — o dry_run diz quem entra e quem fica
  // de fora ANTES de qualquer marcação.
  const abrirRepublicacao = useCallback(async () => {
    if (republicacaoCarregando) return
    setRepublicacaoCarregando(true)
    try {
      const r = await apiFetch<RepublicarDryResposta>(
        `/malhas/${encodeURIComponent(malha)}/republicar`, {
          method: 'POST',
          body: JSON.stringify({ dry_run: true }),
        })
      setRepublicacao(r)
    } catch (err) {
      // 422 (malha vazia / todos inativos) e 503 (070) chegam como detail
      // pt-BR — o servidor é a autoridade da recusa.
      const httpErr = err as Error & { status?: number }
      toast.error(httpErr.message || 'Erro ao preparar a republicação da malha')
    } finally {
      setRepublicacaoCarregando(false)
    }
  }, [republicacaoCarregando, malha])

  const confirmarRepublicacao = useCallback(async () => {
    if (!republicacao || republicando) return
    setRepublicando(true)
    try {
      const r = await apiFetch<RepublicarResposta>(
        `/malhas/${encodeURIComponent(malha)}/republicar`, { method: 'POST' })
      toast.success(r.republicados.length === 1
        ? '1 pipeline enviado para publicação — a nova versão da DAG entra em alguns minutos.'
        : `${r.republicados.length} pipelines enviados para publicação — as novas versões das DAGs entram em alguns minutos.`)
      // Ignorado NÃO é sucesso silencioso: quem ficou de fora é dito com o
      // motivo, um por um (a mesma régua do erro-por-raiz do disparo).
      r.ignorados.forEach(i => toast.info(`${i.pipeline}: ${i.motivo}`))
      // O acompanhamento fino (erro de geração, import error) mora na tela de
      // Publicação, que lê o log da factory por run.
      qc.invalidateQueries({ queryKey: ['malha', malha] })
      qc.invalidateQueries({ queryKey: ['pipelines'] })   // badge "publicação pendente"
      qc.invalidateQueries({ queryKey: ['factory-runs'] })
    } catch (err) {
      const httpErr = err as Error & { status?: number }
      toast.error(httpErr.message || 'Erro ao republicar os pipelines da malha')
    } finally {
      setRepublicando(false)
      setRepublicacao(null)
    }
  }, [republicacao, republicando, malha, qc])

  // ── Gestos de aresta de nó / componente (dry_run → modal → write) ─────────
  const aplicarAresta = useCallback(async (
    origem: PontaGesto, destino: PontaGesto, rotulo: string,
  ) => {
    const r = await apiFetch<GestoWriteResposta>(
      `/malhas/${encodeURIComponent(malha)}/arestas`, {
        method: 'POST',
        body: JSON.stringify({ origem, destino }),
      })
    toast.success(r.ja_existia
      ? 'Essa ligação já existia — o desenho foi reconciliado.'
      : `Ligação criada: ${rotulo}`)
    resumoEfeito(r.efeito)
    mostrarAvisos(r.avisos)
    invalidarPosGesto()
  }, [malha, resumoEfeito, mostrarAvisos, invalidarPosGesto])

  const gestoCriarAresta = useCallback(async (
    origem: PontaGesto, destino: PontaGesto,
  ) => {
    if (gestoCarregando) return
    setGestoCarregando(true)
    try {
      // dry_run ANTES do write (§7.2): o efeito é dito, nada foi gravado.
      const r = await apiFetch<GestoResposta>(
        `/malhas/${encodeURIComponent(malha)}/arestas`, {
          method: 'POST',
          body: JSON.stringify({ origem, destino, dry_run: true }),
        })
      const ef = r.efeito
      const temEfeito = ef.dependencias_criar.length > 0
        || ef.dependencias_remover.length > 0
        || ef.dependencias_transferir.length > 0
        || ef.ja_existentes_manuais.length > 0
        || ef.agendamentos.length > 0            // F13: Início → raiz
        || ef.republicar.length > 0
      // Espelho client-side do ciclo (§3.3): criaCiclo roda sobre o
      // preview_expandido que o dry_run devolve — a autoridade é o servidor
      // (erros[]); o espelho cobre o vão de um preview sem erro, com o MESMO
      // texto (msgCiclo).
      let cicloLocal: string | null = null
      if (r.erros.length === 0 && r.preview_expandido) {
        for (const par of ef.dependencias_criar) {
          const resto = r.preview_expandido
            .filter(p => !(p.pipeline_name === par.dependente
              && p.depende_de === par.predecessor))
            .map(p => ({ source: p.depende_de, target: p.pipeline_name }))
          if (criaCiclo(resto, par.predecessor, par.dependente)) {
            cicloLocal = msgCiclo(par.dependente, par.predecessor)
            break
          }
        }
      }
      const rotulo = `${rotuloPontaGesto(origem)} → ${rotuloPontaGesto(destino)}`
      if (r.erros.length === 0 && !cicloLocal && !temEfeito) {
        // Gesto sem efeito composto (ex.: pipeline → Notificação): aplica
        // direto, como a aresta do F8 — não há nada além do desenho a
        // consentir; os avisos saem no toast.
        await aplicarAresta(origem, destino, rotulo)
      } else {
        setGesto({ acao: 'criar-aresta', rotulo, origem, destino,
                   resposta: r, cicloLocal })
      }
    } catch (err) {
      // Gramática §2.1 / 503 de migration / 404 — o detail pt-BR do servidor.
      const httpErr = err as Error & { status?: number }
      toast.error(httpErr.message || 'Erro ao validar a ligação')
    } finally {
      setGestoCarregando(false)
    }
  }, [gestoCarregando, malha, rotuloPontaGesto, aplicarAresta])

  const aplicarRemocaoAresta = useCallback(async (arestaId: number, rotulo: string) => {
    const r = await apiFetch<GestoWriteResposta>(
      `/malhas/${encodeURIComponent(malha)}/arestas/${arestaId}`,
      { method: 'DELETE' })
    toast.success(`Ligação removida: ${rotulo}`)
    resumoEfeito(r.efeito)
    mostrarAvisos(r.avisos)
    invalidarPosGesto()
  }, [malha, resumoEfeito, mostrarAvisos, invalidarPosGesto])

  const gestoRemoverAresta = useCallback(async (edge: Edge) => {
    if (gestoCarregando) return
    const arestaId = Number(edge.id.slice(ANO_PREFIX.length))
    if (!Number.isFinite(arestaId)) return
    setGestoCarregando(true)
    try {
      const r = await apiFetch<GestoResposta>(
        `/malhas/${encodeURIComponent(malha)}/arestas/${arestaId}?dry_run=true`,
        { method: 'DELETE' })
      const rotulo = `${rotuloPontaGesto(pontaDoCanvas(edge.source))} → `
        + `${rotuloPontaGesto(pontaDoCanvas(edge.target))}`
      // Remoção SEMPRE confirma (mesma barra do F8) — mesmo com efeito zero o
      // modal diz isso com todas as letras.
      setGesto({ acao: 'remover-aresta', rotulo, arestaId, resposta: r })
    } catch (err) {
      const httpErr = err as Error & { status?: number }
      if (httpErr.status === 404) {
        // Já não existia (gesto concorrente) — o estado final é o mesmo.
        toast.info(httpErr.message || 'Ligação já não existia.')
        qc.invalidateQueries({ queryKey: ['malha', malha] })
      } else {
        toast.error(httpErr.message || 'Erro ao validar a remoção')
      }
    } finally {
      setGestoCarregando(false)
    }
  }, [gestoCarregando, malha, rotuloPontaGesto, qc])

  const aplicarRemocaoNo = useCallback(async (noId: number, rotulo: string) => {
    const r = await apiFetch<GestoWriteResposta>(
      `/malhas/${encodeURIComponent(malha)}/nos/${noId}`,
      { method: 'DELETE' })
    toast.success(`Componente excluído: ${rotulo}`
      + (r.arestas_removidas ? ` (${r.arestas_removidas} ligação(ões) saíram do desenho)` : ''))
    resumoEfeito(r.efeito)
    mostrarAvisos(r.avisos)
    invalidarPosGesto()
  }, [malha, resumoEfeito, mostrarAvisos, invalidarPosGesto])

  const gestoRemoverNo = useCallback(async (rfId: string) => {
    if (gestoCarregando) return
    const noId = Number(rfId.slice(NO_PREFIX.length))
    if (!Number.isFinite(noId)) return
    setGestoCarregando(true)
    try {
      const r = await apiFetch<GestoResposta>(
        `/malhas/${encodeURIComponent(malha)}/nos/${noId}?dry_run=true`,
        { method: 'DELETE' })
      setGesto({ acao: 'remover-no', rotulo: rotuloPontaGesto({ no: noId }),
                 noId, resposta: r })
    } catch (err) {
      const httpErr = err as Error & { status?: number }
      if (httpErr.status === 404) {
        toast.info(httpErr.message || 'Componente já não existia.')
        qc.invalidateQueries({ queryKey: ['malha', malha] })
      } else {
        toast.error(httpErr.message || 'Erro ao validar a exclusão do componente')
      }
    } finally {
      setGestoCarregando(false)
    }
  }, [gestoCarregando, malha, rotuloPontaGesto, qc])

  // Confirmar o gesto do modal: re-envia SEM dry_run. O servidor RECOMPUTA
  // sobre o estado corrente (a autoridade é ele, não o preview — §7.2); 404 é
  // tolerado no padrão do confirmarExclusao do F8.
  const confirmarGesto = useCallback(async () => {
    if (!gesto) return
    setAplicandoGesto(true)
    try {
      if (gesto.acao === 'criar-aresta' && gesto.origem && gesto.destino) {
        await aplicarAresta(gesto.origem, gesto.destino, gesto.rotulo)
      } else if (gesto.acao === 'remover-aresta' && gesto.arestaId != null) {
        await aplicarRemocaoAresta(gesto.arestaId, gesto.rotulo)
      } else if (gesto.acao === 'remover-no' && gesto.noId != null) {
        await aplicarRemocaoNo(gesto.noId, gesto.rotulo)
      }
    } catch (err) {
      const httpErr = err as Error & { status?: number }
      if (httpErr.status === 404) {
        toast.info(httpErr.message || 'Já não existia — o desenho foi atualizado.')
      } else {
        // 422 do write (edição concorrente mudou o efeito) — o toast reporta
        // o que o servidor de fato decidiu.
        toast.error(httpErr.message || 'Erro ao aplicar o gesto')
      }
      invalidarPosGesto()
    } finally {
      setAplicandoGesto(false)
      setGesto(null)
    }
  }, [gesto, aplicarAresta, aplicarRemocaoAresta, aplicarRemocaoNo, invalidarPosGesto])

  // ── Criar dependência (conectar) ──────────────────────────────────────────
  const criarDep = useMutation({
    mutationFn: (body: { pipeline_name: string; depende_de: string }) =>
      apiFetch<{ ok: boolean; ja_existia: boolean; dag_config_pendente?: boolean }>('/dependencias', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: (r, body) => {
      const id = `dep:${body.depende_de}->${body.pipeline_name}`
      setEdges(eds => eds.some(e => e.id === id)
        ? eds
        : [...eds, depEdge(body)])
      toast.success(r.ja_existia
        ? 'Essa dependência já existia — nada foi alterado.'
        : `Dependência criada: ${body.depende_de} → ${body.pipeline_name}`)
      // Decisão 6/D30: a DAG do DEPENDENTE ficou para trás (o schedule dela
      // muda) — o servidor persistiu a pendência; aqui só se avisa o gesto.
      if (r.dag_config_pendente) toast.info(msgRepublicar(body.pipeline_name))
      // Invalida TODAS as consultas de malha: a dependência é global e aparece
      // em qualquer malha que contenha as duas pontas (aceite da F8).
      qc.invalidateQueries({ queryKey: ['malha'] })
      qc.invalidateQueries({ queryKey: ['pipelines'] })   // badge "publicação pendente"
    },
    // 422 (ciclo/inexistente/self) e 503 (migration 067) chegam como detail
    // pt-BR — o servidor é a autoridade; o toast mostra o texto dele.
    onError: (e: Error) => toast.error(e.message || 'Erro ao criar a dependência'),
  })

  const onConnect = useCallback(
    (conn: Connection) => {
      if (travado) return
      const origem = conn.source
      const alvo = conn.target
      if (!origem || !alvo) return
      const envolveNo = ehNo(origem) || ehNo(alvo)
      if (!envolveNo) {
        // Aresta pipeline → pipeline: o F8 de sempre, intocado.
        if (depsIndisponiveis) return
        if (origem === alvo) {
          toast.error(MSG_SELF)
          return
        }
        if (edgesRef.current.some(e => e.source === origem && e.target === alvo)) {
          toast.info('Essa dependência já está no diagrama.')
          return
        }
        // Validação client-side com a MESMA mensagem do servidor. O grafo local
        // só enxerga arestas entre membros da malha — ciclo que passe por
        // pipeline de fora é recusado pelo 422 do servidor (mesmo texto).
        if (criaCiclo(edgesRef.current, origem, alvo)) {
          toast.error(msgCiclo(alvo, origem))
          return
        }
        criarDep.mutate({ pipeline_name: alvo, depende_de: origem })
        return
      }
      // Aresta de NÓ (F12): gesto com dry_run antes do write. A gramática já
      // vive nos handles (Início sem entrada, Notificação/Fim sem saída); o
      // que restar proibido chega como 422 do servidor, texto literal.
      if (nosIndisponiveis) return
      if (edgesRef.current.some(e => e.source === origem && e.target === alvo)) {
        toast.info('Essa ligação já está no desenho.')
        return
      }
      void gestoCriarAresta(pontaDoCanvas(origem), pontaDoCanvas(alvo))
    },
    [travado, depsIndisponiveis, nosIndisponiveis, criarDep, gestoCriarAresta],
  )

  // ── Excluir (Delete/botão): classifica a seleção antes de qualquer modal ──
  // Aresta COMPILADA por outra malha (cadeado): recusa client-side com a MESMA
  // mensagem do 422 do servidor (Decisão 4) — e o DELETE /dependencias segue
  // recusando por baixo se algum caminho chegar lá. Aresta de NÓ: gesto com
  // dry_run (uma por vez — cada uma tem o próprio efeito). Aresta direta:
  // fluxo de confirmação do F8, intocado.
  const solicitarExclusaoArestas = useCallback((lista: Edge[]) => {
    const compiladas: Edge[] = []
    const deNo: Edge[] = []
    const diretas: Edge[] = []
    for (const e of lista) {
      const cp = (e.data as { compiladaPor?: CompiladaPor } | undefined)?.compiladaPor
      if (cp) compiladas.push(e)
      else if (e.id.startsWith(ANO_PREFIX)) deNo.push(e)
      else diretas.push(e)
    }
    for (const e of compiladas.slice(0, 2)) {
      const cp = (e.data as { compiladaPor: CompiladaPor }).compiladaPor
      toast.error(msgLinhaAssinada(e.target, e.source, cp.malha, cp.no))
    }
    if (deNo.length > 0) {
      if (deNo.length > 1) {
        toast.info('Exclua as ligações de componente uma por vez — cada uma tem o próprio efeito.')
      }
      if (diretas.length > 0) {
        toast.info('As dependências diretas selecionadas não foram tocadas — exclua-as em outro gesto.')
      }
      void gestoRemoverAresta(deNo[0])
      return
    }
    if (diretas.length > 0) setDelEdges(diretas)
  }, [gestoRemoverAresta])

  // Delete de NÓ: pipeline continua indo pro modal Membros; COMPONENTE (F12)
  // é gesto destrutivo com dry_run + confirmação (§7.3).
  const handleBeforeDelete = useCallback(
    async ({ nodes: toDel, edges: toDelEdges }: { nodes: Node[]; edges: Edge[] }) => {
      if (travado) return false
      const componentes = toDel.filter(n => ehNo(n.id))
      const pipelines = toDel.filter(n => !ehNo(n.id))
      if (pipelines.length > 0) {
        toast.info('Para retirar um pipeline da malha use o modal Membros — aqui o Delete só remove ligações (arestas) e componentes.')
        return false
      }
      if (componentes.length > 0) {
        if (componentes.length > 1) {
          toast.info('Exclua um componente por vez — cada exclusão tem o próprio efeito.')
        }
        void gestoRemoverNo(componentes[0].id)
        return false
      }
      if (toDelEdges.length > 0) {
        solicitarExclusaoArestas(toDelEdges)
        return false   // cancela o delete nativo; a confirmação decide
      }
      return true
    },
    [travado, gestoRemoverNo, solicitarExclusaoArestas],
  )

  const selEdges = useMemo(() => edges.filter(e => e.selected), [edges])
  const selComponentes = useMemo(
    () => nodes.filter(n => n.selected && ehNo(n.id)), [nodes])
  // (F3) Nó-PIPELINE selecionado — o alvo do botão de descer até as etapas.
  const selPipelines = useMemo(
    () => nodes.filter(n => n.selected && !ehNo(n.id)), [nodes])

  // ── F10: Segurar/Soltar também na EXECUÇÃO (§9.6) ────────────────────────
  // O gesto vivia SÓ no modo Montagem, e isso obrigava a sair da lente de
  // acompanhamento no meio do incidente para destravar a malha — trocar de
  // modo é perder o recorte da corrida, a faixa e o painel de quem está
  // travando, exatamente quando eles são o que se está lendo.
  //
  // Uma função só, usada nos dois modos: duas cópias do mesmo botão seriam
  // duas oportunidades de os textos divergirem, e este é o botão cuja frase
  // decide se o operador entende que "segurar o Início" NÃO para o ciclo que
  // já está rodando.
  const botaoRetencao = () => {
    if (readOnly || nosIndisponiveis || !podeExecutar) return null
    if (selComponentes.length !== 1) return null
    const noId = Number(selComponentes[0].id.slice(NO_PREFIX.length))
    const noSel = grafo?.nos.find(n => n.id === noId)
    if (!noSel || !['aguarde', 'inicio'].includes(noSel.tipo)) return null
    const preso = !!noSel.retido_em
    const ehInicio = noSel.tipo === 'inicio'
    return (
      <Button
        variant={preso ? 'primary' : 'secondary'}
        size="sm"
        loading={retendo}
        onClick={() => void alternarRetencao(noId, !preso)}
        title={preso
          ? (ehInicio
            ? 'Soltar a trava — a malha volta a partir no próximo horário agendado'
            : 'Soltar a trava — os pipelines depois deste Aguarde voltam a ser avaliados no próximo ciclo')
          : (ehInicio
            ? 'SEGURAR a malha: nenhuma raiz parte até você soltar'
            : 'SEGURAR aqui: nenhum pipeline depois deste Aguarde é liberado até você soltar')}
      >
        {preso ? <><Unlock size={13} /> Soltar</> : <><Lock size={13} /> Segurar</>}
      </Button>
    )
  }

  // ── Realce: rótulo e contador (F1) ────────────────────────────────────────
  // O id cru do componente ("no:5") não é linguagem de operador — o rótulo sai
  // pelo mesmo tradutor dos gestos ("Aguarde #5"). "Itens" e não "pipelines"
  // porque a cadeia atravessa componentes de desenho: dizer pipeline seria
  // mentira quando um Aguarde está no meio.
  const realceRotulo = useMemo(() => {
    const f = realce.foco
    if (!f || !realce.cadeia) return null
    if (f.tipo === 'no') return rotuloPontaGesto(pontaDoCanvas(f.id))
    const a = edges.find(e => e.id === f.id)
    if (!a) return null
    return `${rotuloPontaGesto(pontaDoCanvas(a.source))} → ${rotuloPontaGesto(pontaDoCanvas(a.target))}`
  }, [realce.foco, realce.cadeia, edges, rotuloPontaGesto])
  const realceTextos = useMemo(() => {
    const c = realce.cadeia
    if (!c) return { tras: null, frente: null }
    const ehAresta = realce.foco?.tipo === 'aresta'
    const it = (n: number) => (n === 1 ? 'item' : 'itens')
    return {
      tras: realce.sentido === 'frente' ? null
        : ehAresta ? `${c.qtdTras} ${it(c.qtdTras)} antes desta ligação`
        : c.qtdTras === 0 ? 'não depende de nenhum item'
        : `depende de ${c.qtdTras} ${it(c.qtdTras)}`,
      frente: realce.sentido === 'tras' ? null
        : ehAresta ? `${c.qtdFrente} ${it(c.qtdFrente)} depois desta ligação`
        : c.qtdFrente === 0 ? 'nenhum item depende deste'
        : `${c.qtdFrente} ${it(c.qtdFrente)} ${c.qtdFrente === 1 ? 'depende' : 'dependem'} deste`,
    }
  }, [realce.cadeia, realce.foco, realce.sentido])

  // Esc apaga o realce. Handler próprio (o MalhaEditor não tinha teclado) e
  // deliberadamente inerte quando não há realce: nenhum preventDefault, nenhum
  // stopPropagation — o Esc dos modais segue sendo tratado pelo Modal.
  useEffect(() => {
    if (!realce.foco) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') realceLimpar() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [realce.foco, realceLimpar])

  async function confirmarExclusao() {
    if (!delEdges || delEdges.length === 0) return
    setExcluindo(true)
    let removidas = 0
    const republicar = new Set<string>()
    for (const e of delEdges) {
      try {
        const r = await apiFetch<{ ok: boolean; dag_config_pendente?: boolean }>('/dependencias', {
          method: 'DELETE',
          body: JSON.stringify({ pipeline_name: e.target, depende_de: e.source }),
        })
        if (r.dag_config_pendente && e.target) republicar.add(e.target)
        removidas += 1
        setEdges(eds => eds.filter(x => x.id !== e.id))
      } catch (err) {
        const httpErr = err as Error & { status?: number }
        if (httpErr.status === 404) {
          // Já não existia no servidor (excluída por outra tela/pessoa):
          // remove do desenho e segue — o estado final é o mesmo.
          setEdges(eds => eds.filter(x => x.id !== e.id))
          toast.info(httpErr.message || 'Dependência já não existia.')
        } else {
          // Inclui o 422 de linha assinada (F11/Decisão 4) que tenha escapado
          // da recusa client-side: o texto do servidor manda, a aresta fica.
          toast.error(httpErr.message || 'Erro ao excluir a dependência')
        }
      }
    }
    setExcluindo(false)
    setDelEdges(null)
    if (removidas > 0) {
      toast.success(removidas === 1
        ? 'Dependência excluída — ela saiu de todas as malhas.'
        : `${removidas} dependências excluídas — elas saíram de todas as malhas.`)
      // Decisão 6/D30: remover dependência também muda o schedule da DAG do
      // dependente — o servidor ligou a pendência; o toast aponta o gesto.
      republicar.forEach(nome => toast.info(msgRepublicar(nome)))
      qc.invalidateQueries({ queryKey: ['malha'] })
      qc.invalidateQueries({ queryKey: ['pipelines'] })   // badge "publicação pendente"
    }
  }

  // ── Layout: reorganizar e salvar posições ─────────────────────────────────
  // Recoloca os nós em camadas na orientação pedida (a corrente, por default).
  const reLayout = useCallback((o: Orientacao) => {
    setNodes(nds => {
      const pos = liveLayout(nds, edgesRef.current, new Map(), o)
      return nds.map(n => (pos[n.id] ? { ...n, position: pos[n.id] } : n))
    })
  }, [setNodes])
  const reorganizar = useCallback(() => reLayout(orientacao), [reLayout, orientacao])

  // ── Orientação (migration 074): PATCH + re-layout automático ──────────────
  const mudarOrientacao = useMutation({
    mutationFn: ({ nova }: { nova: Orientacao; anterior: Orientacao }) =>
      apiFetch<{ ok: boolean; orientacao?: string; migration_074_pendente?: boolean }>(
        `/malhas/${encodeURIComponent(malha)}`, {
          method: 'PATCH',
          body: JSON.stringify({ orientacao: nova }),
        }),
    onSuccess: (r) => {
      // Deploy parcial (074 pendente): a tela funciona na orientação nova, mas
      // ela não persistiu — aviso honesto em vez de silêncio.
      if (r.migration_074_pendente) {
        toast.info('migration 074 pendente — a orientação vale só nesta sessão, '
          + 'o servidor ainda não a persiste.')
      }
      // O refetch traz a orientação recém-salva; o override local vira redundante.
      qc.invalidateQueries({ queryKey: ['malha', malha] })
    },
    onError: (e: Error, { anterior }) => {
      // UMA fonte só para o revert: o valor EXIBIDO antes do clique — não o do
      // servidor (numa sessão degradada sem a 074 eles divergem, e reverter
      // orientação para um lado e desenho para o outro criava estado híbrido:
      // handles laterais com nós empilhados — achado da revisão adversarial).
      setOrientacaoLocal({ malha, valor: anterior })
      reLayout(anterior)
      toast.error(e.message || 'Erro ao trocar a orientação do diagrama')
    },
  })

  const trocarOrientacao = useCallback((nova: Orientacao) => {
    if (nova === orientacao || travado) return
    const anterior = orientacao
    setOrientacaoLocal({ malha, valor: nova })
    mudarOrientacao.mutate({ nova, anterior })
    // Re-layout imediato na direção nova (mesmo módulo do Reorganizar) — as
    // posições recalculadas só persistem pelo "Salvar posições" (fica dirty).
    reLayout(nova)
    toast.info('Posições reorganizadas — use "Salvar posições" para persistir.')
    // Enquadra o desenho já na direção nova (mesmo delay do fit de abertura).
    setTimeout(() => rf.fitView({ padding: 0.2, duration: 250 }), 90)
  }, [orientacao, travado, malha, mudarOrientacao, reLayout, rf])

  const salvarLayout = useMutation({
    mutationFn: () =>
      apiFetch<{ ok: boolean; atualizados: number }>(
        `/malhas/${encodeURIComponent(malha)}/layout`, {
          method: 'PUT',
          body: JSON.stringify({
            // n.id serve para os dois mundos: pipeline pelo nome e componente
            // como "no:{id}" — o contrato §9 do PUT aceita ambos.
            posicoes: nodesRef.current.map(n => ({
              pipeline_name: n.id,
              layout_x: Math.round(n.position.x),
              layout_y: Math.round(n.position.y),
            })),
          }),
        }),
    onSuccess: (r) => {
      toast.success(`Posições salvas (${r.atualizados} nó${r.atualizados !== 1 ? 's' : ''}).`)
      // O refetch traz o layout recém-salvo — o baseline derivado passa a bater
      // com o canvas e o botão volta a desabilitar até a próxima mudança real.
      qc.invalidateQueries({ queryKey: ['malha', malha] })
    },
    onError: (e: Error) => toast.error(e.message || 'Erro ao salvar as posições'),
  })

  // ── Paleta: adicionar membro (POST /malhas/{name}/pipelines, F7) ──────────
  const addMembro = useMutation({
    mutationFn: (pipeline_name: string) =>
      apiFetch<{ ok: boolean; pipeline_name: string; ja_membro: boolean }>(
        `/malhas/${encodeURIComponent(malha)}/pipelines`, {
          method: 'POST',
          body: JSON.stringify({ pipeline_name }),
        }),
    onSuccess: (r) => {
      toast.success(r.ja_membro
        ? `"${r.pipeline_name}" já é membro desta malha.`
        : `Pipeline "${r.pipeline_name}" entrou na malha.`)
      setBusca('')
      qc.invalidateQueries({ queryKey: ['malha', malha] })
      qc.invalidateQueries({ queryKey: ['malhas'] })   // contagens dos cards
    },
    onError: (e: Error) => toast.error(e.message || 'Erro ao adicionar o pipeline'),
  })

  // ── Paleta de componentes: arrastar-para-criar (POST /nos, F12) ───────────
  const addNo = useMutation({
    mutationFn: (v: { tipo: TipoComponente; x: number; y: number }) =>
      apiFetch<{ ok: boolean; id: number; avisos: AvisoDesenho[] }>(
        `/malhas/${encodeURIComponent(malha)}/nos`, {
          method: 'POST',
          body: JSON.stringify({ tipo: v.tipo, layout_x: v.x, layout_y: v.y }),
        }),
    onSuccess: (r, v) => {
      toast.success(`Componente ${COMPONENTE_META[v.tipo].rotulo} adicionado ao desenho.`)
      mostrarAvisos(r.avisos)
      qc.invalidateQueries({ queryKey: ['malha', malha] })
    },
    // Inclui o 422 de 2º Início/Fim (a paleta previne; o servidor decide).
    onError: (e: Error) => toast.error(e.message || 'Erro ao adicionar o componente'),
  })

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])
  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    if (travado || nosIndisponiveis) return
    const tipo = e.dataTransfer.getData(DND_MIME_NO) as TipoComponente
    if (!tipo || !(tipo in COMPONENTE_META)) return
    const p = rf.screenToFlowPosition({ x: e.clientX, y: e.clientY })
    addNo.mutate({ tipo, x: Math.round(p.x), y: Math.round(p.y) })
  }, [travado, nosIndisponiveis, rf, addNo])

  // ── "Prender as pontas soltas" (§2.2): terminais membros → Fim ────────────
  // Terminal = pipeline sem saída para OUTRO pipeline, Aguarde ou Fim (saída
  // só para Notificação não conta — o aviso é escutar, não concluir). Ligar
  // ao Fim tem efeito zero na 067 — é o desenho da conclusão, em um clique.
  const fimNo = useMemo(
    () => grafo?.nos.find(n => n.tipo === 'fim') ?? null, [grafo])
  // F13: o nó Início e a contagem de raízes ligadas (painel de agendamento).
  const inicioNo = useMemo(
    () => grafo?.nos.find(n => n.tipo === 'inicio') ?? null, [grafo])
  const raizesInicio = inicioNo ? (grafo?.saidasNo.get(inicioNo.id) ?? 0) : 0
  const pontasSoltas = useMemo(() => {
    if (!fimNo) return []
    const naoSolto = new Set<string>()
    for (const e of edges) {
      if (ehNo(e.source)) continue
      const alvoTipo = ehNo(e.target)
        ? tipoDoNo.get(Number(e.target.slice(NO_PREFIX.length)))
        : 'pipeline'
      if (alvoTipo !== 'notificacao') naoSolto.add(e.source)
    }
    return nodes
      .filter(n => n.type === 'malhaPipeline' && !naoSolto.has(n.id))
      .map(n => n.id)
      .sort()
  }, [fimNo, nodes, edges, tipoDoNo])

  async function prenderPontasSoltas() {
    if (!fimNo || pontasSoltas.length === 0 || prendendo) return
    setPrendendo(true)
    let ligadas = 0
    for (const p of pontasSoltas) {
      try {
        await apiFetch(`/malhas/${encodeURIComponent(malha)}/arestas`, {
          method: 'POST',
          body: JSON.stringify({ origem: { pipeline: p }, destino: { no: fimNo.id } }),
        })
        ligadas += 1
      } catch (err) {
        const httpErr = err as Error & { status?: number }
        toast.error(httpErr.message || `Erro ao ligar ${p} ao Fim`)
      }
    }
    setPrendendo(false)
    if (ligadas > 0) {
      toast.success(ligadas === 1
        ? '1 ponta solta presa ao Fim.'
        : `${ligadas} pontas soltas presas ao Fim.`)
      qc.invalidateQueries({ queryKey: ['malha', malha] })
    }
  }

  // ── Estados de borda ──────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex h-full w-full items-center justify-center rounded-xl border border-edge bg-canvas">
        <PageSpinner />
      </div>
    )
  }
  if (isError) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 rounded-xl border border-edge bg-canvas text-sm">
        <AlertCircle size={20} className="text-red-600 dark:text-red-400" />
        <span className="text-ink">Não foi possível carregar a malha.</span>
        <span className="text-xs text-dim">{(error as Error)?.message}</span>
      </div>
    )
  }

  const modoBtnCls = (ativo: boolean) =>
    `inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
      ativo
        ? 'bg-[#1A5FA8] text-white'
        : 'border border-edge bg-canvas text-dim hover:text-ink hover:bg-edge/40'
    }`
  // Rótulo de nó p/ o banner de avisos ("Aguarde #8"), null p/ aviso geral.
  const rotuloNoAviso = (no: number | null): string | null => {
    if (no == null) return null
    return rotuloPontaGesto({ no })
  }

  const temInicio = !!grafo?.nos.some(n => n.tipo === 'inicio')
  const temFim = !!grafo?.nos.some(n => n.tipo === 'fim')

  // Efeito/erros do gesto pendente (modal).
  const gestoEf = gesto?.resposta.efeito
  const gestoErros = gesto
    ? [...gesto.resposta.erros,
       ...(gesto.cicloLocal && gesto.resposta.erros.length === 0
         ? [gesto.cicloLocal] : [])]
    : []
  const gestoTemEfeito = !!gestoEf && (
    gestoEf.dependencias_criar.length > 0
    || gestoEf.dependencias_remover.length > 0
    || gestoEf.dependencias_transferir.length > 0
    || gestoEf.ja_existentes_manuais.length > 0
    || gestoEf.agendamentos.length > 0           // F13
    || gestoEf.republicar.length > 0)

  return (
    <div className="flex h-full w-full flex-col overflow-hidden rounded-xl border border-edge bg-canvas">
      {/* Barra superior (F9): Montagem | Execução + seletor de data de referência. */}
      <div className="flex flex-wrap items-center gap-2 border-b border-edge bg-panel px-3 py-2">
        <div className="flex gap-1">
          <button
            onClick={() => setModo('montagem')}
            title="Montar a malha: membros, dependências e layout"
            className={modoBtnCls(!emExecucao)}
          >
            <Wrench size={12} /> Montagem
          </button>
          <button
            onClick={() => setModo('execucao')}
            title="Ver a execução da malha numa data de referência (edição travada)"
            className={modoBtnCls(emExecucao)}
          >
            <Activity size={12} /> Execução
          </button>
        </div>
        {/* Orientação do diagrama (por malha, persiste no servidor com o
            layout). Consulta (readOnly) vê a orientação salva, mas não troca —
            o controle nem aparece. */}
        {!emExecucao && !readOnly && (
          <div className="ml-auto flex flex-wrap items-center gap-3">
            {/* Republicação da malha: desenhar aresta/Aguarde/agendamento
                grava a dependência na hora, mas a DAG do Airflow só passa a
                obedecê-la depois de regerada. O contador diz quantos membros
                estão nessa situação AGORA (carimbo da 073 ou sem DAG). */}
            {podeExecutar && (
              <Button
                size="sm"
                variant={membrosDesatualizados > 0 ? 'primary' : 'secondary'}
                onClick={() => void abrirRepublicacao()}
                loading={republicacaoCarregando}
                disabled={(data?.membros.length ?? 0) === 0}
                title={(data?.membros.length ?? 0) === 0
                  ? 'A malha ainda não tem pipelines vinculados'
                  : membrosDesatualizados > 0
                    ? `${membrosDesatualizados} pipeline(s) com a DAG desatualizada — republicar gera as novas versões com os vínculos atuais`
                    : 'Gerar novamente as DAGs de todos os pipelines desta malha com o cadastro atual'}
              >
                <RefreshCw size={13} /> Republicar pipelines
                {membrosDesatualizados > 0 && (
                  <span className="ml-1 rounded-full bg-amber-100 px-1.5 py-px text-[10px] font-semibold text-amber-800 dark:bg-amber-900/60 dark:text-amber-300">
                    {membrosDesatualizados}
                  </span>
                )}
              </Button>
            )}
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-dim">Orientação</span>
            <div className="flex gap-1">
              <button
                onClick={() => trocarOrientacao('horizontal')}
                disabled={mudarOrientacao.isPending}
                title="Diagrama horizontal (esquerda → direita) — trocar reorganiza as posições na nova direção"
                className={modoBtnCls(orientacao === 'horizontal')}
              >
                <ArrowRightLeft size={12} /> horizontal
              </button>
              <button
                onClick={() => trocarOrientacao('vertical')}
                disabled={mudarOrientacao.isPending}
                title="Diagrama vertical (cima → baixo) — trocar reorganiza as posições na nova direção"
                className={modoBtnCls(orientacao === 'vertical')}
              >
                <ArrowUpDown size={12} /> vertical
              </button>
              </div>
            </div>
          </div>
        )}
        {emExecucao && (
          <div className="ml-auto flex flex-wrap items-center gap-1.5">
            {/* F10 — Decisão 42: a navegação temporal saiu daqui. Havia três
                mecanismos nesta barra (◀ ▶ · input de data · botão "agora") e
                a fase pedia uma faixa de corridas: quatro mecanismos para a
                mesma pergunta na mesma barra é decisão adiada, não
                flexibilidade — às 3h usa-se UM. Agora existe a FAIXA das
                últimas corridas, no cabeçalho da corrida (`SeletorCorrida`),
                com a data e o "agora" como itens do menu dela. */}
            {execQuery.isFetching && (
              <RefreshCw size={12} className="animate-spin text-dim" />
            )}
            {/* F15: disparo manual da malha — dry_run mostra raízes + ODATE
                no modal antes de qualquer trigger; sem Início o servidor
                recusa com instrução (o botão avisa no title). */}
            {!readOnly && podeExecutar && (
              <Button
                size="sm"
                onClick={() => void abrirDisparo()}
                loading={disparoCarregando}
                // Sem dataExibida (execQuery ainda carregando ou em erro) o
                // gesto enviaria SEM data e o servidor escolheria sozinho —
                // o operador dispararia numa data que a tela não mostrou.
                // Mesma condição dos botões de navegação de data.
                disabled={!temInicio || !dataExibida}
                title={!temInicio
                  ? 'A malha não tem componente Início — adicione-o no modo Montagem e ligue-o às raízes'
                  : !dataExibida
                    ? 'Aguardando a data de referência desta visão'
                    : 'Disparar as raízes da malha (ligadas ao Início) com esta data de referência — a cadeia anda pelo push'}
              >
                <Play size={13} /> Disparar malha
              </Button>
            )}
          </div>
        )}
      </div>

      {/* F2 da spec-malha-data-unica: membros fora da régua de data da malha.
          A virada decide o ODATE de quem roda por agenda — divergir aqui é o
          que parte a corrida em dois dias. O botão alinha todos de uma vez. */}
      {(data?.virada_divergente?.length ?? 0) > 0 && (
        <div className="flex items-start gap-2 border-b border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span className="min-w-0 flex-1">
            <strong>
              {data!.virada_divergente!.length === 1
                ? '1 pipeline fora da régua de data da malha'
                : `${data!.virada_divergente!.length} pipelines fora da régua de data da malha`}
            </strong>
            {' — '}a hora de virada deles é diferente da malha
            {data?.hora_virada
              ? <> (<span className="font-mono">{data.hora_virada}</span>)</>
              : ' (virada global)'}
            , então carimbam data de referência diferente na mesma corrida.{' '}
            <span className="font-mono text-[11px]">
              {data!.virada_divergente!.slice(0, 4).join(', ')}
              {data!.virada_divergente!.length > 4
                ? ` +${data!.virada_divergente!.length - 4}` : ''}
            </span>
          </span>
          {!readOnly && !emExecucao && (
            <button
              onClick={() => void alinharVirada()}
              disabled={alinhandoVirada}
              title="Copiar a hora de virada da malha para todos os membros"
              className="shrink-0 rounded-md border border-amber-300 bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800 transition-colors hover:bg-amber-200 disabled:opacity-50 dark:border-amber-700 dark:bg-amber-900/40 dark:text-amber-200 dark:hover:bg-amber-900/60"
            >
              {alinhandoVirada ? 'alinhando…' : 'Alinhar data da malha'}
            </button>
          )}
        </div>
      )}

      {/* F1 da spec-malha-data-unica: o pipeline que tem predecessor E
          agendamento próprio dispara FORA da malha — foi assim que a corrida
          da Carga_Vida saiu com metade dos membros num ODATE e metade em
          outro. Vale nos DOIS modos: na Execução é onde o estrago aparece. */}
      {membrosForaDaMalha.length > 0 && (
        <div className="flex items-start gap-2 border-b border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span className="min-w-0 flex-1">
            <strong>
              {membrosForaDaMalha.length === 1
                ? '1 pipeline com dependência ainda dispara por agenda'
                : `${membrosForaDaMalha.length} pipelines com dependência ainda disparam por agenda`}
            </strong>
            {' — '}a DAG deles não foi republicada depois que a dependência foi
            criada, então rodam no horário próprio, fora da ordem da malha, e
            carimbam a própria data de referência.{' '}
            <span className="font-mono text-[11px]">
              {membrosForaDaMalha.slice(0, 4).join(', ')}
              {membrosForaDaMalha.length > 4
                ? ` +${membrosForaDaMalha.length - 4}` : ''}
            </span>
          </span>
          {!readOnly && podeExecutar && (
            <button
              onClick={() => void abrirRepublicacao()}
              disabled={republicacaoCarregando}
              className="shrink-0 rounded-md border border-red-300 bg-red-100 px-2 py-0.5 text-[11px] font-semibold text-red-800 transition-colors hover:bg-red-200 disabled:opacity-50 dark:border-red-700 dark:bg-red-900/40 dark:text-red-200 dark:hover:bg-red-900/60"
            >
              Republicar pipelines
            </button>
          )}
        </div>
      )}

      {(depsIndisponiveis || (emExecucao && execData?.migration_067_pendente === true)) && (
        <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
          <AlertTriangle size={14} className="shrink-0" />
          <span>
            migration 067 pendente — as dependências não estão disponíveis neste
            ambiente; o diagrama mostra só os pipelines, sem arestas, e a criação
            de dependências fica desabilitada.
          </span>
        </div>
      )}

      {/* F12: deploy parcial da 075 — a malha abre normal, sem componentes. */}
      {!emExecucao && nosIndisponiveis && (
        <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
          <AlertTriangle size={14} className="shrink-0" />
          <span>
            migration 075 pendente — os componentes de malha (Início, Aguarde,
            Notificação e Fim) não estão disponíveis neste ambiente; o restante
            do diagrama funciona normalmente.
          </span>
        </div>
      )}

      {/* F12: banner PERSISTENTE de avisos do desenho (§2.2) — o GET repete a
          lista enquanto a situação durar; o toast do gesto mostra só os novos.
          A linha das pontas soltas é derivada do grafo vivo + o botão do §2.2. */}
      {!emExecucao && (avisosDesenho.length > 0
        || (temFim && pontasSoltas.length > 0)) && (
        <div className="max-h-28 overflow-y-auto border-b border-amber-200 bg-amber-50 px-3 py-1.5 dark:border-amber-800 dark:bg-amber-900/20">
          {avisosDesenho.map((a, i) => (
            <div
              key={`${a.no ?? 'g'}-${i}`}
              className="flex items-center gap-1.5 py-0.5 text-[11px] text-amber-700 dark:text-amber-400"
            >
              {a.nivel === 'forte'
                ? <AlertTriangle size={12} className="shrink-0" />
                : <Info size={12} className="shrink-0" />}
              <span>
                {rotuloNoAviso(a.no) && (
                  <strong>{rotuloNoAviso(a.no)}: </strong>
                )}
                {a.mensagem}
              </span>
            </div>
          ))}
          {temFim && pontasSoltas.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 py-0.5 text-[11px] text-amber-700 dark:text-amber-400">
              <AlertTriangle size={12} className="shrink-0" />
              <span>
                <strong>Fim: </strong>
                {pontasSoltas.length === 1
                  ? `o pipeline terminal ${pontasSoltas[0]} ainda não está ligado ao Fim`
                  : `${pontasSoltas.length} pipelines terminais ainda não estão ligados ao Fim`}
              </span>
              {!travado && (
                <button
                  onClick={() => void prenderPontasSoltas()}
                  disabled={prendendo}
                  title={`Ligar ao Fim: ${pontasSoltas.join(', ')}`}
                  className="inline-flex items-center gap-1 rounded-md border border-amber-300 bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800 transition-colors hover:bg-amber-200 disabled:opacity-50 dark:border-amber-700 dark:bg-amber-900/40 dark:text-amber-300 dark:hover:bg-amber-900/60"
                >
                  <Anchor size={10} /> {prendendo ? 'prendendo…' : 'Prender as pontas soltas'}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* F15: na Execução o banner de montagem não aparece, mas o aviso de
          CONTRADIÇÃO sim — é aqui que vive o "Disparar malha", e um disparo
          manual parte a raiz por cima do predecessor (o trigger manual não
          consulta a liberação). */}
      {emExecucao && avisosContradicao.length > 0 && (
        <div className="max-h-20 overflow-y-auto border-b border-amber-200 bg-amber-50 px-3 py-1.5 dark:border-amber-800 dark:bg-amber-900/20">
          {avisosContradicao.map((a, i) => (
            <div key={`c-${i}`}
              className="flex items-center gap-1.5 py-0.5 text-[11px] text-amber-700 dark:text-amber-400">
              <AlertTriangle size={12} className="shrink-0" />
              <span>{a.mensagem}</span>
            </div>
          ))}
        </div>
      )}

      {/* F9: estados honestos da visão de execução. Antes da retomada F2–F4
          nada grava em etl_pipeline_execucao — o vazio é esperado e dito. */}
      {emExecucao && execQuery.isError && (
        <div className="flex items-center gap-2 border-b border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          <AlertCircle size={14} className="shrink-0" />
          <span>
            Não foi possível carregar a execução desta data:{' '}
            {(execQuery.error as Error)?.message ?? 'erro desconhecido'}
          </span>
        </div>
      )}
      {/* F4: com corrida no payload este aviso sai do ar — a faixa já diz o
          estado do ciclo, e "sem execuções registradas" ao lado de "em
          andamento · 4 de 7" seriam duas afirmações opostas na mesma tela
          (uma corrida recém-aberta ainda não tem linha de pipeline nenhuma). */}
      {emExecucao && execData && !corrida && !execData.migration_067_pendente
        && execData.execucoes.length === 0 && (
        <div className="flex items-center gap-2 border-b border-blue-200 bg-blue-50 px-3 py-2 text-[12px] text-blue-800 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-200">
          <Info size={14} className="shrink-0" />
          <span>
            Sem execuções registradas nesta data — o registro chega com a
            retomada das dependências (F2).
          </span>
        </div>
      )}

      {/* ── F10: A FAIXA DA CORRIDA ───────────────────────────────────────
          Quem responde "a malha rodou?" é o CICLO — e não mais o membro que
          começou por último, que é a chave de comparação do defeito que esta
          spec mata. A faixa e o card da lista leem o MESMO agregado
          (`resumoCorrida`), porque duas superfícies derivando o mesmo fato por
          caminhos diferentes é como elas passam a discordar na mesma tela.

          A F10 tira o JSX daqui e o põe num componente: a faixa passou a ter
          os três banners da Decisão 66, o botão de encerrar, o relógio do
          prazo e a faixa de navegação — 120 linhas de JSX no meio de um editor
          de 3.400 é onde uma regressão de tema entra sem ninguém ver. */}
      {emExecucao && (
        <CabecalhoCorrida
          corrida={corrida}
          resumo={resumo}
          carregando={execQuery.isLoading}
          sem085={sem085}
          corridasNoDia={execData?.corridas_no_dia ?? null}
          proximoGatilho={proximoGatilho}
          respostaEm={execQuery.dataUpdatedAt}
          agoraLocal={agoraLocal}
          nosSegurados={nosSegurados}
          /* Soltar do BANNER: o mesmo gesto do botão do canvas, sem exigir que
             o operador saia da lente de acompanhamento, ache o nó no desenho e
             o selecione no meio do incidente. */
          onSoltar={!readOnly && podeExecutar && !nosIndisponiveis
            ? (noId => void alternarRetencao(noId, false))
            : undefined}
          soltando={retendo}
          avisoPreso={avisoPreso}
          onEncerrar={podeExecutar ? encerrarCorrida : undefined}
          encerrando={encerrando}
          onAbrirAba={setAbaPainel}
          seletor={(
            <SeletorCorrida
              corridas={corridas}
              corridaId={corridaRef ?? corrida?.id ?? null}
              onTrocar={irParaCorrida}
              dataExibida={dataExibida}
              onIrParaData={irParaDia}
              onAgora={() => irParaDia(null)}
              noAgora={dataRef === null && corridaRef === null}
              carregando={corridasQuery.isLoading}
            />
          )}
        />
      )}

      {/* F15 (§6): banner verde da conclusão — o evento MALHA_CONCLUIDA do nó
          Fim nesta data. Evento emitido é histórico verdadeiro: o banner some
          trocando a data consultada, nunca por apagamento.
          F4: só sobra para quem NÃO tem corrida no payload (API anterior à
          fase, ou interruptor em 0) — com a corrida, quem afirma "concluída" é
          o status dela, uma vez só, na faixa acima. */}
      {emExecucao && !corrida && !sem085 && execData?.malha_concluida?.em && (
        <div className="flex items-center gap-2 border-b border-green-200 bg-green-50 px-3 py-2 text-[12px] font-medium text-green-800 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300">
          <CheckCircle2 size={14} className="shrink-0" />
          <span>
            Malha concluída em {dataExibida} às {horaCurta(execData.malha_concluida.em)}.
          </span>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {/* ── F10: o painel lateral da CORRIDA (§9.5) ──────────────────────
            Até aqui ele era "EVENTOS DA GUARDIÃ" — e corrida saudável não gera
            evento, então ele ficava VAZIO justamente durante a corrida.
            Descobrir o que estava rodando era varrer o canvas com o olho
            procurando anel azul. Agora são três abas, com a inicial derivada
            da SAÚDE (Decisão 62), e cada linha leva ao problema em um clique
            SEM sair da lente de execução. */}
        {emExecucao && (
          <PainelCorridaLateral
            corrida={corrida}
            execucoes={execData?.execucoes ?? []}
            eventos={eventos}
            aba={abaPainel}
            onAba={setAbaPainel}
            onFocar={focarPipeline}
            onAbrirEtapas={onAbrirEtapas && dataExibida
              ? descerParaEtapas
              : undefined}
            /* Decisão 65 — o botão só existe quando a frase do efeito PODE ser
               escrita com certeza, e ela só pode com um ciclo ABERTO em foco:
               é dele que se afirma "esta reexecução entra nele e o relógio de
               fechamento não reinicia". Sem corrida aberta o botão some e
               sobra `▶ etapas`, que é o que a própria Decisão 65 manda. */
            onReexecutar={podeExecutar && corrida?.status === 'ABERTA' && dataExibida
              ? (p => void abrirReexecucao(p))
              : undefined}
            fraseReexecucao={corrida?.status === 'ABERTA'
              ? `Esta reexecução entra na ${resumo?.identidade ?? 'corrida em andamento'}`
                + ' (em andamento) e o relógio de fechamento do ciclo NÃO'
                + ' reinicia por este gesto. A prévia mostra o que será'
                + ' reexecutado antes de confirmar.'
              : null}
            respostaEm={execQuery.dataUpdatedAt}
            agoraLocal={agoraLocal}
          />
        )}

        {/* Paleta lateral: ADICIONAR membro (a remoção continua no modal
            Membros da F7 — sem duplicar o caminho) + componentes (F12). */}
        {!readOnly && !emExecucao && (
          <div className="flex w-60 shrink-0 flex-col gap-2 overflow-y-auto border-r border-edge bg-panel p-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-dim">
              Adicionar pipeline
            </span>
            <Autocomplete
              value={busca}
              onChange={setBusca}
              onSelect={setBusca}
              fetchSuggestions={q =>
                apiFetch<{ data: { pipeline_name: string }[] }>(
                  `/pipelines?limit=10&filter_name=${encodeURIComponent(q)}`)
                  .then(r => r.data.map(p => p.pipeline_name))
              }
              placeholder="busque por nome..."
              onKeyDown={e => {
                if (e.key === 'Enter' && busca.trim()) addMembro.mutate(busca.trim())
              }}
            />
            <Button
              size="sm"
              onClick={() => addMembro.mutate(busca.trim())}
              loading={addMembro.isPending}
              disabled={!busca.trim()}
            >
              <Plus size={13} /> Adicionar à malha
            </Button>
            <p className="mt-1 text-[11px] leading-relaxed text-dim">
              O pipeline entra como <strong className="text-ink">membro</strong> e
              vira um nó no canvas. Ligue dois nós para criar a
              dependência <em>(origem → dependente)</em> — ela é <strong className="text-ink">real
              e global</strong>, não um desenho desta malha.
            </p>

            {/* Componentes de malha (F12): arrastar para o canvas cria o nó
                (POST /nos) — unicidade de Início/Fim prevenida aqui e
                garantida pelo 422 + índice filtrado no servidor. */}
            <div className="flex flex-col gap-1.5 border-t border-edge pt-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-dim">
                Componentes
              </span>
              {nosIndisponiveis ? (
                <p className="text-[11px] leading-relaxed text-dim">
                  migration 075 pendente — os componentes ficam indisponíveis
                  neste ambiente.
                </p>
              ) : (
                <>
                  {COMPONENTES_ORDEM.map(tipo => {
                    const unico = (tipo === 'inicio' && temInicio)
                      || (tipo === 'fim' && temFim)
                    return (
                      <ItemPaletaComponente
                        key={tipo}
                        tipo={tipo}
                        desabilitado={unico}
                        motivo={unico
                          ? `A malha já tem um nó ${COMPONENTE_META[tipo].rotulo} — só pode haver um por malha`
                          : undefined}
                      />
                    )
                  })}
                  <p className="text-[11px] leading-relaxed text-dim">
                    Arraste para o canvas. Ligar pernas a um{' '}
                    <strong className="text-ink">Aguarde</strong> compila
                    dependências reais — o efeito é mostrado{' '}
                    <em>antes</em> de gravar.
                  </p>
                </>
              )}
            </div>

            <p className="border-t border-edge pt-2 text-[11px] leading-relaxed text-dim">
              Para <strong className="text-ink">retirar</strong> um pipeline da malha,
              use o modal <em>Membros</em> no card da malha.
            </p>
          </div>
        )}

        <div className="relative min-h-0 min-w-0 flex-1">
          {nodes.length === 0 && (
            <div className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center gap-1 text-dim">
              <span className="text-3xl">⬡</span>
              <p className="text-sm font-medium">Nenhum pipeline nesta malha</p>
              {!readOnly && !emExecucao && (
                <p className="text-xs">Adicione o primeiro pela busca à esquerda.</p>
              )}
            </div>
          )}
          <ReactFlow
            nodes={realce.nodesRealce}
            edges={realce.edgesRealce}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onBeforeDelete={handleBeforeDelete}
            onDrop={onDrop}
            onDragOver={onDragOver}
            /* (F1) Clique acende a cadeia. A seleção nativa do React Flow
               continua acontecendo por baixo — é ela que move os botões de
               excluir/agendamento; o realce só soma. */
            onNodeClick={(_, node) => realceFocarNo(node.id)}
            onEdgeClick={(_, edge) => realceFocarAresta(edge.id)}
            onPaneClick={() => realceLimpar()}
            // O zoom por duplo clique do React Flow fica DESLIGADO
            // (`zoomOnDoubleClick` abaixo): o `dblclicked` do d3-zoom
            // interrompe a propagação no pane e, com a delegação de eventos do
            // React 19, o gesto nunca chegava ao handler — o duplo clique
            // anunciado na interface não disparava. Zoom segue pelos controles,
            // pela roda e pelo atalho de teclado.
            onNodeDoubleClick={(_, node) => {
              // F13: duplo clique no Início abre o painel de agendamento —
              // o nó é a porta (Decisão 8); travado/sem 075 não abre.
              if (travado || nosIndisponiveis || !ehNo(node.id)) return
              if (tipoDoNo.get(Number(node.id.slice(NO_PREFIX.length))) === 'inicio') {
                setAgendaAberta(true)
              }
            }}
            colorMode={colorMode}
            zoomOnDoubleClick={false}
            fitView
            fitViewOptions={{ padding: 0.25 }}
            proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{ type: 'smoothstep' }}
            nodesDraggable={!travado}
            nodesConnectable={!travado && !(depsIndisponiveis && nosIndisponiveis)}
            edgesFocusable={!travado}
            deleteKeyCode={travado ? null : ['Delete', 'Backspace']}
          >
            <Background gap={18} size={1} />
            <Controls />
            <MiniMap pannable zoomable nodeColor={miniMapColor} className="!bg-panel" />

            {/* (F1) Painel do realce — nos dois modos; some sem foco. */}
            {realce.cadeia && realceRotulo && (
              <Panel position="top-left">
                <PainelRealce
                  foco={realceRotulo}
                  sentido={realce.sentido}
                  onSentido={realce.mudarSentido}
                  isolar={realce.isolar}
                  onIsolar={realce.alternarIsolar}
                  onLimpar={realce.limpar}
                  textoTras={realceTextos.tras}
                  textoFrente={realceTextos.frente}
                  acesos={realce.cadeia.nos.size}
                  total={nodes.length}
                />
              </Panel>
            )}

            {/* Barra de ações (topo direita) — selo nos modos de leitura. */}
            <Panel position="top-right">
              {emExecucao ? (
                <div className="flex items-center gap-2 rounded-lg border border-edge bg-panel/95 px-2.5 py-1.5 shadow-md backdrop-blur">
                  <span className="flex items-center gap-1.5 text-[11px] font-semibold text-dim">
                    <Activity size={12} /> visão de execução — edição travada
                  </span>
                  {/* (F3) Descer até as etapas do pipeline selecionado, na
                      data exibida. Só aparece com UM nó-pipeline selecionado —
                      mesma gramática do "Excluir componente" da montagem. */}
                  {onAbrirEtapas && selPipelines.length === 1 && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => descerParaEtapas(selPipelines[0].id)}
                      disabled={!dataExibida}
                      title={dataExibida
                        ? `Abrir o canvas de Etapas de ${selPipelines[0].id} em ${dataExibida}, `
                          + 'com status e horários de cada etapa (duplo clique no nó também abre)'
                        : 'Aguardando a data de referência desta visão'}
                    >
                      <Layers size={13} /> Ver etapas
                    </Button>
                  )}
                  {/* F10 — o gesto de retenção passa a existir AQUI. A edição
                      do desenho continua travada; segurar/soltar não é edição
                      de desenho, é operação do ciclo. */}
                  {botaoRetencao()}
                </div>
              ) : readOnly ? (
                <span className="flex items-center gap-1.5 rounded-lg border border-edge bg-panel/95 px-2.5 py-1.5 text-[11px] font-semibold text-dim shadow-md backdrop-blur">
                  <MousePointerClick size={12} /> somente leitura
                </span>
              ) : (
                <div className="flex items-center gap-2 rounded-lg border border-edge bg-panel/95 px-2.5 py-2 shadow-md backdrop-blur">
                  {selComponentes.length === 1
                    && tipoDoNo.get(Number(selComponentes[0].id.slice(NO_PREFIX.length))) === 'inicio'
                    && !nosIndisponiveis && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setAgendaAberta(true)}
                      title="Agendamento da malha — copiado às raízes ligadas ao Início (duplo clique no nó também abre)"
                    >
                      <CalendarClock size={13} /> Agendamento
                    </Button>
                  )}
                  {/* F10: a MESMA função do modo Execução — um botão só,
                      um texto só. */}
                  {botaoRetencao()}
                  {selComponentes.length === 1 && (
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => void gestoRemoverNo(selComponentes[0].id)}
                      title="Excluir o componente do desenho — o efeito nas dependências é mostrado antes de gravar"
                    >
                      <Trash2 size={13} /> Excluir componente
                    </Button>
                  )}
                  {selEdges.length > 0 && (
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => solicitarExclusaoArestas(selEdges)}
                      title="Excluir a(s) ligação(ões) selecionada(s) — o efeito real é mostrado antes"
                    >
                      <Trash2 size={13} />{' '}
                      {selEdges.some(e => e.id.startsWith(ANO_PREFIX))
                        ? 'Excluir ligação'
                        : 'Excluir dependência'}
                    </Button>
                  )}
                  {dirty && (
                    <span className="flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
                      <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                      posições não salvas
                    </span>
                  )}
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={reorganizar}
                    title="Recoloca os nós em camadas pelas dependências"
                  >
                    <RefreshCw size={13} /> Reorganizar
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => salvarLayout.mutate()}
                    loading={salvarLayout.isPending}
                    disabled={!dirty}
                    title={dirty
                      ? 'Persistir as posições dos nós nesta malha'
                      : 'Nenhuma posição mudou — nada a salvar'}
                  >
                    <Save size={13} /> Salvar posições
                  </Button>
                </div>
              )}
            </Panel>
          </ReactFlow>
        </div>
      </div>

      {/* Legenda fixa da visão de execução (F9) — os seis status do contrato. */}
      {emExecucao && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-edge bg-panel px-3 py-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-dim">Legenda</span>
          {ORDEM_LEGENDA.map(s => {
            const e = STATUS_EXECUCAO[s]
            return (
              <span key={s} className="flex items-center gap-1 text-[10px] text-dim">
                <span className={`h-2 w-2 rounded-full ${e.dot} ${e.animado ? 'animate-pulse' : ''}`} />
                {e.rotulo}
              </span>
            )
          })}
          {/* A linha é a outra metade da leitura: o card diz o estado de UM
              pipeline, a linha diz se a corrida ATRAVESSOU aquele trecho.
              F4: entra o traço tracejado ÂMBAR de `esperando` — e os rótulos
              passam a sair de ROTULO_FLUXO, a mesma fonte do nome acessível da
              aresta, para legenda e desenho não divergirem de vocabulário. */}
          <span className="flex items-center gap-1.5 border-l border-edge pl-3 text-[10px] text-dim">
            linha:
            <span className="inline-block h-0.5 w-4 rounded bg-green-600 dark:bg-green-400" />
            {ROTULO_FLUXO.concluido.replace('trecho ', '')}
            <span className="inline-block h-0.5 w-4 animate-pulse rounded bg-blue-600 dark:bg-blue-400" />
            {ROTULO_FLUXO.ativo}
            {/* Tracejado de verdade (border-dashed sobre 0 de altura): o
                operador precisa reconhecer no canvas o MESMO traço. */}
            <span className="inline-block w-4 border-t-2 border-dashed border-amber-600 dark:border-amber-400" />
            {ROTULO_FLUXO.esperando}
            <span className="inline-block h-0.5 w-4 rounded bg-red-600 dark:bg-red-400" />
            {ROTULO_FLUXO.bloqueado}
          </span>
          <span className="ml-auto text-[10px] text-dim">
            nó sem anel = sem execução registrada na data
          </span>
          {/* (F3) Descoberta do drill-down — o chip "etapas" mora no card. */}
          {onAbrirEtapas && (
            <span className="flex items-center gap-1 text-[10px] text-dim">
              <Layers size={11} /> “etapas” no card abre o pipeline etapa a etapa nesta data
            </span>
          )}
        </div>
      )}

      {/* Confirmação de exclusão de aresta — §4b: a dependência é GLOBAL. */}
      <Modal
        open={!!delEdges}
        onClose={() => setDelEdges(null)}
        title="Excluir dependência"
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm text-ink">
            Isto apaga a dependência REAL entre os pipelines — ela some de todas
            as malhas. Continuar?
          </p>
          <div className="flex flex-col gap-1">
            {(delEdges ?? []).map(e => (
              <div key={e.id} className="flex items-center gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                <Link2 size={12} className="shrink-0 text-dim" />
                <span className="font-mono text-xs text-ink">
                  {e.source} <span className="text-dim">→</span> {e.target}
                </span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-dim">
            Lê-se "origem → dependente": o dependente deixa de esperar a origem
            em TODAS as malhas — não é só um ajuste visual deste diagrama.
          </p>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="secondary" onClick={() => setDelEdges(null)}>Cancelar</Button>
            <Button variant="danger" onClick={confirmarExclusao} loading={excluindo}>
              <Trash2 size={13} /> Excluir dependência
            </Button>
          </div>
        </div>
      </Modal>

      {/* F12: modal do GESTO de componente — o efeito §7.2 dito ANTES do
          write; erros[] (ciclo) bloqueiam com o texto literal do servidor. */}
      <Modal
        open={!!gesto}
        onClose={() => { if (!aplicandoGesto) setGesto(null) }}
        title={gesto?.acao === 'criar-aresta' ? 'Ligar componente'
          : gesto?.acao === 'remover-aresta' ? 'Remover ligação'
          : 'Excluir componente'}
        size="lg"
      >
        {gesto && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-ink">
              {gesto.acao === 'criar-aresta' && (
                <>Ligar <strong className="font-mono text-xs">{gesto.rotulo}</strong> — o
                efeito abaixo é aplicado ao confirmar:</>
              )}
              {gesto.acao === 'remover-aresta' && (
                <>Remover a ligação <strong className="font-mono text-xs">{gesto.rotulo}</strong> — o
                efeito abaixo é aplicado ao confirmar:</>
              )}
              {gesto.acao === 'remover-no' && (
                <>Excluir <strong>{gesto.rotulo}</strong> — as ligações dele saem do
                desenho e o efeito abaixo é aplicado ao confirmar:</>
              )}
            </p>

            {/* Erros BLOQUEIAM (ciclo, Decisão 15) — o texto é o do servidor,
                literal; nada foi gravado. */}
            {gestoErros.map((e, i) => (
              <div
                key={i}
                className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
              >
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <span>{e}</span>
              </div>
            ))}
            {gestoErros.length > 0 && (
              <p className="text-[11px] text-dim">
                O gesto está bloqueado — nada foi gravado no desenho nem nas
                dependências.
              </p>
            )}

            {gestoErros.length === 0 && gestoEf && (
              <div className="flex max-h-[46vh] flex-col gap-2 overflow-y-auto">
                {!gestoTemEfeito && (
                  <p className="text-[12px] text-dim">
                    Nenhuma dependência real é afetada — só o desenho muda.
                  </p>
                )}
                {gestoEf.dependencias_criar.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-dim">
                      Dependências a criar
                    </p>
                    {gestoEf.dependencias_criar.map(d => (
                      <div key={`c-${d.dependente}-${d.predecessor}`}
                        className="flex items-center gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                        <Plus size={12} className="shrink-0 text-green-600 dark:text-green-400" />
                        <span className="font-mono text-xs text-ink">
                          {d.predecessor} <span className="text-dim">→</span> {d.dependente}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {gestoEf.dependencias_remover.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-dim">
                      Dependências a remover
                    </p>
                    {gestoEf.dependencias_remover.map(d => (
                      <div key={`r-${d.dependente}-${d.predecessor}`}
                        className="flex items-center gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                        <Minus size={12} className="shrink-0 text-red-600 dark:text-red-400" />
                        <span className="font-mono text-xs text-ink">
                          {d.predecessor} <span className="text-dim">→</span> {d.dependente}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {gestoEf.dependencias_transferir.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-dim">
                      Assinaturas transferidas (a dependência continua)
                    </p>
                    {gestoEf.dependencias_transferir.map(d => (
                      <div key={`t-${d.dependente}-${d.predecessor}`}
                        className="flex items-center gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                        <ArrowRightLeft size={12} className="shrink-0 text-blue-600 dark:text-blue-400" />
                        <span className="min-w-0 font-mono text-xs text-ink">
                          {d.predecessor} <span className="text-dim">→</span> {d.dependente}
                          <span className="ml-1 font-sans text-[10px] text-dim">
                            passa à malha '{d.para_malha}' (nó #{d.para_no})
                          </span>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {gestoEf.agendamentos.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-dim">
                      Agendamentos (raízes do Início)
                    </p>
                    {gestoEf.agendamentos.map(a => (
                      <div key={`a-${a.pipeline}`}
                        className="flex items-start gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                        <CalendarClock size={12} className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
                        <span className="min-w-0 text-xs text-ink">
                          <span className="font-mono">{a.pipeline}</span>
                          <span className="block text-[10px] text-dim">
                            {a.de} <span className="mx-0.5">→</span> {a.para}
                          </span>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {gestoEf.ja_existentes_manuais.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-dim">
                      Já existiam (manuais — seguem do operador, não serão assinadas)
                    </p>
                    {gestoEf.ja_existentes_manuais.map(d => (
                      <div key={`m-${d.dependente}-${d.predecessor}`}
                        className="flex items-center gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                        <Info size={12} className="shrink-0 text-dim" />
                        <span className="font-mono text-xs text-ink">
                          {d.predecessor} <span className="text-dim">→</span> {d.dependente}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {gestoEf.republicar.length > 0 && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
                    <strong>Republicação necessária:</strong>{' '}
                    {gestoEf.republicar.join(', ')} — depois de confirmar,
                    publique nova versão (Pipelines ▸ Publicar nova versão).
                  </div>
                )}
                {gesto.resposta.avisos.length > 0 && (
                  <div className="flex flex-col gap-0.5">
                    {gesto.resposta.avisos.map((a, i) => (
                      <div key={i} className="flex items-center gap-1.5 text-[11px] text-amber-700 dark:text-amber-400">
                        {a.nivel === 'forte'
                          ? <AlertTriangle size={12} className="shrink-0" />
                          : <Info size={12} className="shrink-0" />}
                        <span>
                          {rotuloNoAviso(a.no) && <strong>{rotuloNoAviso(a.no)}: </strong>}
                          {a.mensagem}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {gestoErros.length === 0 && (
              <p className="text-[11px] text-dim">
                O servidor recalcula o efeito ao confirmar — se algo mudou nesse
                meio tempo, o resultado real é reportado no aviso.
              </p>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <Button
                variant="secondary"
                onClick={() => setGesto(null)}
                disabled={aplicandoGesto}
              >
                {gestoErros.length > 0 ? 'Fechar' : 'Cancelar'}
              </Button>
              {gestoErros.length === 0 && (
                <Button
                  variant={gesto.acao === 'criar-aresta' ? 'primary' : 'danger'}
                  onClick={() => void confirmarGesto()}
                  loading={aplicandoGesto}
                >
                  {gesto.acao === 'criar-aresta' && <><Link2 size={13} /> Ligar e aplicar</>}
                  {gesto.acao === 'remover-aresta' && <><Trash2 size={13} /> Remover ligação</>}
                  {gesto.acao === 'remover-no' && <><Trash2 size={13} /> Excluir componente</>}
                </Button>
              )}
            </div>
          </div>
        )}
      </Modal>

      {/* F15: confirmação do disparo manual — o que SERÁ disparado (raízes +
          ODATE), dito antes de qualquer trigger; avisos honestos por raiz. */}
      <Modal
        open={!!disparo}
        onClose={() => { if (!disparando) setDisparo(null) }}
        title="Disparar malha"
      >
        {disparo && (
          <div className="flex flex-col gap-3">
            {/* F1: a malha começa do ZERO. O que segura vem PRIMEIRO, com nome
                e data de cada um — o operador precisa saber o que resolver, não
                só que não pode disparar. */}
            {/* F3: a malha marcada equaliza sozinha — mas o de→para aparece
                antes de confirmar. Automático não é secreto. */}
            {(disparo.equalizacao?.prevista.length ?? 0) > 0 && (
              <div className="flex flex-col gap-1 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 dark:border-blue-800 dark:bg-blue-900/20">
                <span className="flex items-center gap-1.5 text-[12px] font-semibold text-blue-700 dark:text-blue-300">
                  <RefreshCw size={13} /> Esta malha equaliza a data automaticamente
                </span>
                {disparo.equalizacao!.prevista.map(p => (
                  <div key={p.pipeline} className="text-[11px] text-blue-700 dark:text-blue-300">
                    <span className="font-mono">{p.pipeline}</span>: {p.data_referencia}
                    {' → '}<strong>{disparo.data_referencia}</strong>
                  </div>
                ))}
                <span className="text-[11px] text-blue-700/90 dark:text-blue-300/90">
                  A mudança fica registrada no histórico da execução e no painel
                  de eventos da malha.
                </span>
              </div>
            )}
            {(disparo.equalizacao?.impedidos.length ?? 0) > 0 && (
              <div className="flex flex-col gap-1 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 dark:border-amber-800 dark:bg-amber-900/20">
                <span className="text-[12px] font-semibold text-amber-700 dark:text-amber-300">
                  Não dá para equalizar:
                </span>
                {disparo.equalizacao!.impedidos.map(p => (
                  <div key={p.pipeline} className="text-[11px] text-amber-700 dark:text-amber-300">
                    <span className="font-mono">{p.pipeline}</span> — {p.motivo}
                  </div>
                ))}
              </div>
            )}
            {disparo.bloqueado && disparo.bloqueios && (
              <div className="flex flex-col gap-2 rounded-md border border-red-300 bg-red-50 px-3 py-2 dark:border-red-800 dark:bg-red-900/20">
                <span className="flex items-center gap-1.5 text-[12px] font-semibold text-red-700 dark:text-red-300">
                  <AlertTriangle size={13} /> A malha não pode começar agora
                </span>
                {disparo.bloqueios.em_aberto.length > 0 && (
                  <div className="text-[11px] text-red-700 dark:text-red-300">
                    <span className="font-semibold">Corrida em andamento:</span>{' '}
                    {disparo.bloqueios.em_aberto.map(b =>
                      `${b.pipeline} (${b.status.toLowerCase()}, ${b.data_referencia})`
                    ).join(' · ')}
                  </div>
                )}
                {disparo.bloqueios.datas_divergentes.length > 0 && (
                  <div className="text-[11px] text-red-700 dark:text-red-300">
                    <span className="font-semibold">
                      Data de referência diferente de {disparo.data_referencia}:
                    </span>{' '}
                    {disparo.bloqueios.datas_divergentes.map(b =>
                      `${b.pipeline} em ${b.data_referencia}`).join(' · ')}
                  </div>
                )}
                <span className="text-[11px] text-red-700/90 dark:text-red-300/90">
                  A malha só parte do zero e com todos na mesma data. Encerre as
                  corridas em aberto e iguale a data dos membros — o caso mais
                  comum é dependente que ainda dispara por agenda, resolvido por
                  <strong> Republicar pipelines</strong>.
                </span>
              </div>
            )}
            <p className="text-sm text-ink">
              As raízes abaixo (ligadas ao Início) serão disparadas com a data
              de referência{' '}
              <strong className="font-mono text-xs">{disparo.data_referencia}</strong> —
              o restante da malha anda sozinho pelo push, herdando a mesma data.
            </p>
            <div className="flex flex-col gap-1">
              {disparo.raizes.map(r => (
                <div key={r.pipeline}
                  className="flex items-center gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                  <Play size={12} className="shrink-0 text-dim" />
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-ink">
                    {r.pipeline}
                  </span>
                  {r.dag_criada === 0 && (
                    <span className="rounded-full border border-red-200 bg-red-50 px-1.5 py-px text-[10px] font-semibold text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
                      DAG não publicada
                    </span>
                  )}
                  {r.dag_criada === 1 && r.active === 0 && (
                    <span className="rounded-full border border-amber-200 bg-amber-50 px-1.5 py-px text-[10px] font-semibold text-amber-700 dark:border-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                      inativo
                    </span>
                  )}
                  {r.tem_dependencia && (
                    <span
                      title="O disparo manual não consulta a liberação — a corrida parte por cima do predecessor."
                      className="rounded-full border border-amber-200 bg-amber-50 px-1.5 py-px text-[10px] font-semibold text-amber-700 dark:border-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                    >
                      tem dependência
                    </span>
                  )}
                  {(r.corridas_na_data ?? 0) > 0 && (
                    <span
                      title="Esta raiz já rodou nesta data — disparar de novo executa o pipeline outra vez."
                      className="rounded-full border border-amber-200 bg-amber-50 px-1.5 py-px text-[10px] font-semibold text-amber-700 dark:border-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                    >
                      já rodou ({r.corridas_na_data})
                    </span>
                  )}
                </div>
              ))}
            </div>
            {disparo.avisos.length > 0 && (
              <div className="flex flex-col gap-0.5">
                {disparo.avisos.map((a, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-[11px] text-amber-700 dark:text-amber-400">
                    {a.nivel === 'forte'
                      ? <AlertTriangle size={12} className="shrink-0" />
                      : <Info size={12} className="shrink-0" />}
                    <span>{a.mensagem}</span>
                  </div>
                ))}
              </div>
            )}
            <p className="text-[11px] text-dim">
              O disparo é o mesmo gesto de "rodar pipeline", uma vez por raiz —
              quem disparou fica registrado na corrida. Erros são reportados
              por raiz.
            </p>
            <div className="flex justify-end gap-2 pt-1">
              <Button
                variant="secondary"
                onClick={() => setDisparo(null)}
                disabled={disparando}
              >
                Cancelar
              </Button>
              <Button
                onClick={() => void confirmarDisparo()}
                loading={disparando}
                disabled={disparo.bloqueado === true}
                title={disparo.bloqueado
                  ? 'A malha tem corrida em aberto ou data de referência divergente — resolva antes de disparar'
                  : undefined}
              >
                <Play size={13} /> Disparar {disparo.raizes.length === 1
                  ? '1 raiz'
                  : `${disparo.raizes.length} raízes`}
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Confirmação da republicação: quem entra, quem fica de fora e por quê
          — dito antes de qualquer marcação no cadastro. */}
      <Modal
        open={!!republicacao}
        onClose={() => { if (!republicando) setRepublicacao(null) }}
        title="Republicar pipelines da malha"
      >
        {republicacao && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-ink">
              As DAGs dos pipelines abaixo serão geradas de novo com o cadastro
              atual — é assim que os vínculos desenhados nesta malha passam a
              valer no Airflow.
            </p>
            <div className="flex max-h-56 flex-col gap-1 overflow-y-auto">
              {republicacao.pipelines.map(p => (
                <div key={p.pipeline}
                  className="flex items-center gap-2 rounded-md border border-edge bg-canvas px-3 py-1.5">
                  <RefreshCw size={12} className="shrink-0 text-dim" />
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-ink">
                    {p.pipeline}
                  </span>
                  {p.dag_no_airflow === false && (
                    <span className="rounded-full border border-blue-200 bg-blue-50 px-1.5 py-px text-[10px] font-semibold text-blue-700 dark:border-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
                      primeira publicação
                    </span>
                  )}
                  {p.dag_no_airflow !== false && p.publicacao_pendente === true && (
                    <span className="rounded-full border border-amber-200 bg-amber-50 px-1.5 py-px text-[10px] font-semibold text-amber-700 dark:border-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                      desatualizada
                    </span>
                  )}
                </div>
              ))}
            </div>
            {republicacao.ignorados.length > 0 && (
              <div className="flex flex-col gap-1 rounded-md border border-edge bg-panel px-3 py-2">
                <span className="text-[11px] font-semibold text-dim">
                  Fora desta publicação:
                </span>
                {republicacao.ignorados.map(i => (
                  <div key={i.pipeline} className="text-[11px] text-dim">
                    <span className="font-mono text-ink">{i.pipeline}</span> — {i.motivo}
                  </div>
                ))}
              </div>
            )}
            {republicacao.avisos.length > 0 && (
              <div className="flex flex-col gap-0.5">
                {republicacao.avisos.map((a, i) => (
                  <div key={i} className="flex items-start gap-1.5 text-[11px] text-amber-700 dark:text-amber-400">
                    {a.nivel === 'forte'
                      ? <AlertTriangle size={12} className="mt-px shrink-0" />
                      : <Info size={12} className="mt-px shrink-0" />}
                    <span>{a.mensagem}</span>
                  </div>
                ))}
              </div>
            )}
            <p className="text-[11px] text-dim">
              A publicação roda no gerador de DAGs (etl_dag_factory) e leva de
              alguns segundos a poucos minutos. O andamento e os erros de cada
              pipeline ficam na tela de Publicação. As corridas em andamento
              não são interrompidas.
            </p>
            <div className="flex justify-end gap-2 pt-1">
              <Button
                variant="secondary"
                onClick={() => setRepublicacao(null)}
                disabled={republicando}
              >
                Cancelar
              </Button>
              <Button onClick={() => void confirmarRepublicacao()} loading={republicando}>
                <RefreshCw size={13} /> Republicar {republicacao.pipelines.length === 1
                  ? '1 pipeline'
                  : `${republicacao.pipelines.length} pipelines`}
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* F13: painel de agendamento do nó Início — o agendamento é da MALHA
          (Decisão 8); salvar compila para as raízes com dry_run antes. */}
      <AgendamentoInicioModal
        malha={malha}
        aberto={agendaAberta}
        onClose={() => setAgendaAberta(false)}
        agendamento={data?.agendamento ?? null}
        raizes={raizesInicio}
        equalizarData={data?.equalizar_data}
        tetoHoras={data?.teto_horas ?? null}
        temTeto={data ? 'teto_horas' in data : false}
      />

      {/* F10 (Decisão 65): a prévia da reexecução de um travado. Montada só
          quando aberta — a prévia é uma chamada de rede (dry_run no Airflow +
          fecho de dependências) e não pode disparar por ter uma linha na tela.
          É este modal que traz, do SERVIDOR, a frase do efeito no ciclo em
          voo: sem ela o operador apertaria e o painel mudaria de estado por
          baixo dele. */}
      {rerunAlvo && (
        <ModalRerunEtapa
          open
          onClose={() => setRerunAlvo(null)}
          pipeline={rerunAlvo.pipeline}
          taskId={rerunAlvo.taskId}
          jobName={rerunAlvo.taskId}
          dataReferencia={dataExibida || null}
          /* Sem `run_id`: a lente da malha é a CORRIDA, e a identidade de run
             do pipeline dentro dela é resolvida pelo servidor a partir da
             data. Mandar um run_id que esta tela não escolheu seria escolher
             por ele. */
          runId={null}
          status={execPorPipeline.get(rerunAlvo.pipeline)?.status ?? null}
        />
      )}
    </div>
  )
}
