// Card 1 (Pendentes de Assinatura) lendo a FOTO diária — parte PURA (RITM0117336).
//
// Sem react-query nem apiFetch: o que está aqui roda no node nos testes
// (`tests/test_pio_card1_front.py`). Os hooks de leitura ficam em `pioCard1.ts`,
// que reexporta este módulo — os componentes importam de um lugar só.

import type { FotoCard1, PropostaWorkflow, SituacaoDevolucao, StatusWorkflow } from "./workflow";
import { regiaoDaUf } from "./regiao";
import type { AtualDoFluxo } from "./fluxoProposta";

/** O card do Workflow que lê da foto. */
export const STATUS_CARD1: StatusWorkflow = "pending_signature";

/** O Card 2 (Pendentes de Pagamento) lê a mesma estrutura de foto — contrato
 *  idêntico (`ResumoCard1`/`PaginaCard1`), só a fonte muda (`/pio/card2/*`). */
export const STATUS_CARD2: StatusWorkflow = "awaiting_payment";

/** O Card 3 (Assinadas e Pagas) também: `/pio/card3/*`. Já está paga, então não
 *  há "dias pendente" a mostrar. */
export const STATUS_CARD3: StatusWorkflow = "paid";

/** O Card 4 (Em Análise = críticas) também: `/pio/card4/*`. A unidade é o
 *  CERTIFICADO — uma linha por certificado, com o nº de críticas dele. */
export const STATUS_CARD4: StatusWorkflow = "in_analysis";

/** O Card 5 (Emitidas, VG + AP) também: `/pio/card5/*`. A unidade é o CONTRATO
 *  (segmento + nº), já emitido: não há "dias pendente". */
export const STATUS_CARD5: StatusWorkflow = "emission_sent";

/** O Card 6 (Rejeitadas, Vida em Grupo) também: `/pio/card6/*`. A unidade é o
 *  CERTIFICADO — uma linha por certificado, com os motivos dele no Resumo. */
export const STATUS_CARD6: StatusWorkflow = "declined";

/** O Card 7 (Devolução de Prêmio, VG + AP) também: `/pio/card7/*`. Diferente dos outros, o
 *  card NÃO abre lista: abre 3 sub-cards (realizada, em andamento, pendente) e só o clique em
 *  um deles lista os contratos. O número do card é o VALOR DEVOLVIDO (todos os status). */
export const STATUS_CARD7: StatusWorkflow = "refund_scheduled";

/** O Card 8 (Sensibilizações = último movimento de propostas Vida) também: `/pio/card8/*`. A unidade
 *  é a IDENTIFICAÇÃO (o número da proposta pode faltar). O número do card é o valor sensibilizado. */
export const STATUS_CARD8: StatusWorkflow = "sensitization_monitoring";

/** Cards do Workflow que leem a foto diária. */
export const STATUS_DE_FOTO: StatusWorkflow[] = [STATUS_CARD1, STATUS_CARD2, STATUS_CARD3, STATUS_CARD4, STATUS_CARD5, STATUS_CARD6, STATUS_CARD7, STATUS_CARD8];

const PREFIXO_ID: Partial<Record<StatusWorkflow, string>> = {
  [STATUS_CARD1]: "pio1", [STATUS_CARD2]: "pio2", [STATUS_CARD3]: "pio3", [STATUS_CARD4]: "pio4", [STATUS_CARD5]: "pio5", [STATUS_CARD6]: "pio6", [STATUS_CARD7]: "pio7", [STATUS_CARD8]: "pio8",
};

export interface ResumoCard1 {
  disponivel: boolean;
  referencia: string | null;
  atualizacao: string | null;
  lote_id: string | null;
  desatualizado: boolean;
  dias_defasagem: number;
  premio_total: number | null;
  /** Só o Card 5: contratos com prêmio informado (< quantidade = soma parcial). */
  premios_informados?: number;
  /** Só o Card 7: contratos e valor devolvido por sub-card (somam o total do card). */
  /** Só o Card 8: identificações sem status de movimento (NULL ou código de controle). */
  sem_status?: number;
  por_situacao?: Record<SituacaoDevolucao, { quantidade: number; valor: number | null; valores_informados: number }>;
  quantidade: number;
  grupos: number;
}

export interface ItemCard1 {
  id_foto: number;
  proposta: string;
  nome: string;
  cpf: string;
  agencia: string;
  matricula: string;
  data_venda: string | null;
  dias_pendente: number;
  produto: string;
  area_produto: string;
  premio: number | null;
  imp_segurada: number | null;
  renda: number | null;
  cidade: string;
  uf: string;
  idade: number | null;
  situacao: string;
  assinatura: string;
  pago: string;
  contato: { email: string | null; celular: string | null; residencial: string | null };
  /** Só o Card 4 (críticas): situação da venda, nº de mensagens do certificado
   *  e data de quitação (`null` = não informada). */
  sub_situacao?: string;
  criticas?: number;
  quitacao?: string | null;
  /** Só o Card 5: tom do selo, segmento (VG/AP), emissão e dados do cancelamento. */
  tom_status?: "emitida" | "suspensa" | "cancelada";
  segmento?: string;
  emissao?: string | null;
  inativo?: boolean;
  cancelamento?: string | null;
  motivo_cancelamento?: string | null;
  /** Só o Card 6: nº de motivos do certificado, declínio e dias da quitação ao declínio. */
  motivos?: number;
  declinio?: string | null;
  dias_venda_declinio?: number | null;
  /** Só o Card 8: último movimento da identificação, situação da proposta e o botão Sensibilizar. */
  sensibilizacao?: {
    identificacao: string; linha: string; status_movimento: string; status_movimento_codigo: string;
    status_atual: string; status_atual_codigo: string; motivo: string | null; data_movimento: string | null;
    data_envio: string | null; pode_sensibilizar: boolean;
  };
  /** Só o Card 7: sub-card, status do último movimento e data dele. */
  devolucao?: {
    situacao: SituacaoDevolucao; status: string; retorno: string;
    data_movimento: string | null; declinio: string | null;
  };
}

/** Dados da devolução e BANCÁRIOS de um contrato do Card 7 (`/pio/card7/devolucao`).
 *  Campo ausente na fonte vem `null`; banco só tem o código (o nome não está na foto). */
export interface DevolucaoDetalhe {
  situacao: SituacaoDevolucao;
  valor: number | null;
  status: string;
  retorno: string;
  codigo_movimento: string | null;
  data_movimento: string | null;
  data_lancamento: string | null;
  parcela: number | null;
  forma_pagamento: string | null;
  banco: string | null;
  agencia: string | null;
  operacao: string | null;
  conta: string | null;
  digito_conta: string | null;
}

export interface RespostaDevolucao {
  disponivel: boolean;
  referencia: string | null;
  segmento: string;
  numero: number;
  encontrado: boolean;
  devolucao: DevolucaoDetalhe | null;
}

/** Um motivo de rejeição de um certificado (Card 6): `DES_MSG_CRITICA` e
 *  `DES_COMPLEMENTAR`, como vieram. Nenhuma ação é inferida do texto. */
export interface MotivoCard6 {
  codigo: number | null;
  descricao: string;
  complemento: string;
  data_motivo: string | null;
}

export interface MotivosCard6 {
  disponivel: boolean;
  referencia: string | null;
  certificado: number;
  itens: MotivoCard6[];
}

/** Uma mensagem de crítica de um certificado (Card 4): `DES_MSG_CRITICA` e
 *  `DES_COMPLEMENTAR`, como vieram. Nenhuma ação é inferida do texto. */
export interface PendenciaCard4 {
  codigo: number | null;
  descricao: string;
  complemento: string;
  data_critica: string | null;
  imp_segurada: number | null;
  premio: number | null;
}

export interface PendenciasCard4 {
  disponivel: boolean;
  referencia: string | null;
  certificado: number;
  itens: PendenciaCard4[];
}

export interface PaginaCard1 {
  disponivel: boolean;
  referencia: string | null;
  atualizacao: string | null;
  desatualizado: boolean;
  dias_defasagem: number;
  total: number;
  limite: number;
  offset: number;
  detalhe_disponivel: boolean;
  /** Só o Card 8: como a lista está ordenada (`identificacao`); sem isso, mais antigas primeiro. */
  ordem?: string;
  itens: ItemCard1[];
}

const MOEDA = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export function formatarMoeda(valor: number): string {
  return MOEDA.format(valor);
}

/** "2026-08-02" → "02/08/2026", sem `new Date()` (o ISO seria lido como UTC e a
 *  data recuaria um dia a oeste de Greenwich). Cópia deliberada de `dataBr` de
 *  `pio.ts`: este módulo é puro para ser exercitado no node sem o react-query. */
export function dataBr(iso: string | null): string {
  if (!iso) return "";
  const [ano, mes, dia] = iso.split("-");
  return ano && mes && dia ? `${dia}/${mes}/${ano}` : iso;
}

/** "2026-10-27T07:41:30" → "27/10/2026 07:41". */
export function dataHoraBr(iso: string | null): string {
  if (!iso) return "";
  const [data, hora = ""] = iso.split("T");
  return `${dataBr(data)}${hora ? ` ${hora.slice(0, 5)}` : ""}`.trim();
}

/** Item da foto → o formato que a lista e os diálogos já sabem exibir.
 *
 *  O telefone da lista segue a regra do Enviar: residencial se houver, senão o
 *  celular. Campos ausentes ficam VAZIOS, nunca inventados. */
export function propostaDoCard1(
  item: ItemCard1, referencia: string | null, atualizacao: string | null,
  status: StatusWorkflow = STATUS_CARD1,
): PropostaWorkflow {
  const foto: FotoCard1 = {
    idFoto: item.id_foto,
    referencia,
    atualizacao,
    situacao: item.situacao,
    assinatura: item.assinatura,
    pago: item.pago,
    contato: item.contato,
    ...(item.criticas === undefined ? {} : {
      subSituacao: item.sub_situacao ?? "", criticas: item.criticas, quitacao: item.quitacao ?? null,
    }),
    ...(item.sensibilizacao === undefined ? {} : {
      sensibilizacao: {
        identificacao: item.sensibilizacao.identificacao, linha: item.sensibilizacao.linha,
        statusMovimento: item.sensibilizacao.status_movimento, statusMovimentoCodigo: item.sensibilizacao.status_movimento_codigo,
        statusAtual: item.sensibilizacao.status_atual, statusAtualCodigo: item.sensibilizacao.status_atual_codigo,
        motivo: item.sensibilizacao.motivo, dataMovimento: item.sensibilizacao.data_movimento,
        dataEnvio: item.sensibilizacao.data_envio, podeSensibilizar: item.sensibilizacao.pode_sensibilizar,
      },
    }),
    ...(item.devolucao === undefined ? {} : {
      devolucao: {
        situacao: item.devolucao.situacao, segmento: item.segmento ?? "", status: item.devolucao.status,
        retorno: item.devolucao.retorno, dataMovimento: item.devolucao.data_movimento,
        declinio: item.devolucao.declinio,
      },
    }),
    ...(item.motivos === undefined ? {} : {
      rejeitada: {
        subSituacao: item.sub_situacao ?? "", motivos: item.motivos, quitacao: item.quitacao ?? null,
        declinio: item.declinio ?? null, diasVendaDeclinio: item.dias_venda_declinio ?? null,
      },
    }),
    ...(item.tom_status === undefined ? {} : {
      emitida: {
        tom: item.tom_status, segmento: item.segmento ?? "", subSituacao: item.sub_situacao ?? "",
        emissao: item.emissao ?? null, inativo: item.inativo ?? false,
        cancelamento: item.cancelamento ?? null, motivo: item.motivo_cancelamento ?? null,
      },
    }),
  };
  return {
    // `id_foto`, não o número da proposta: a query aceita pode repetir a mesma
    // proposta (JOIN), e chave repetida no React some com linha.
    id: `${PREFIXO_ID[status] ?? "pio1"}-${item.id_foto}`,
    number: item.proposta,
    insuredName: item.nome,
    date: dataBr(item.data_venda),
    status,
    value: item.premio === null ? "" : MOEDA.format(item.premio),
    individualIncome: item.renda === null ? "" : MOEDA.format(item.renda),
    insuredAmount: item.imp_segurada === null ? "" : MOEDA.format(item.imp_segurada),
    indicatorId: item.matricula,
    agency: item.agencia,
    cpf: item.cpf,
    product: item.produto,
    phone: item.contato.residencial ?? item.contato.celular ?? "",
    email: item.contato.email ?? "",
    region: regiaoDaUf(item.uf),
    ageRange: item.idade === null ? "" : `${item.idade} anos`,
    broker: item.matricula,
    daysInPending: status === STATUS_CARD3 || status === STATUS_CARD5 || status === STATUS_CARD6 || status === STATUS_CARD7 || status === STATUS_CARD8 ? 0 : item.dias_pendente,
    foto,
  };
}

/** Rótulos dos códigos DOCUMENTADOS em `docs/pio-fonte-de-dados.md`. Código que
 *  não está aqui aparece CRU: traduzir de palpite é inventar status. */
const ROTULO_ASSINATURA: Record<string, string> = {
  PE: "Pendente de assinatura",
  CO: "Assinada",
  AP: "Assinada e paga",
  AN: "Em análise",
  EM: "Emitida",
  RE: "Rejeitada",
};
const ROTULO_SITUACAO: Record<string, string> = { AT: "Ativa" };
const ROTULO_PAGO: Record<string, string> = { N: "Não pago", S: "Pago" };

function rotulo(mapa: Record<string, string>, codigo: string): string {
  if (!codigo) return "Não informado";
  return mapa[codigo.toUpperCase()] ?? codigo;
}

export const ROTULO_SUBCARD_DEVOLUCAO: Record<SituacaoDevolucao, string> = {
  realizada: "Devolução Realizada", andamento: "Devolução em Andamento", pendente: "Devolução Pendente",
};

/** Cor do selo da devolução (fundo sólido + texto branco, como `STATUS_COR`). */
const COR_SUBCARD_DEVOLUCAO: Record<SituacaoDevolucao, string> = {
  realizada: "bg-emerald-600 text-white", andamento: "bg-amber-600 text-white", pendente: "bg-red-700 text-white",
};

/** A etapa ATUAL do fluxo do Resumo, quando o card sabe mais que o nome dele: o selo real do Card 5
 *  (Cancelada, Cobertura Suspensa…), o sub-card da devolução, o último movimento da sensibilização e
 *  a situação da análise. Sem foto (ou sem nada a dizer), `undefined`: vale o nome do card. */
export function atualDoFluxo(foto: FotoCard1 | undefined): AtualDoFluxo | undefined {
  if (!foto) return undefined;
  if (foto.emitida) {
    const e = foto.emitida;
    return {
      rotulo: e.subSituacao || undefined,
      tom: e.tom === "cancelada" ? "vermelho" : e.tom === "suspensa" ? "ambar" : "azul",
    };
  }
  if (foto.devolucao) {
    const d = foto.devolucao;
    return { rotulo: d.status ? `${ROTULO_SUBCARD_DEVOLUCAO[d.situacao]} · ${d.status}` : ROTULO_SUBCARD_DEVOLUCAO[d.situacao], tom: d.situacao === "realizada" ? "verde" : d.situacao === "andamento" ? "ambar" : "vermelho" };
  }
  if (foto.sensibilizacao) return { rotulo: `Sensibilização · ${foto.sensibilizacao.statusMovimento}` };
  if (foto.criticas !== undefined && foto.subSituacao) return { rotulo: `Em Análise · ${foto.subSituacao}` };
  return undefined;
}

export function rotuloSegmento(segmento: string): string {
  const s = segmento.toUpperCase();
  return s === "VG" ? "Vida em Grupo" : s === "AP" ? "Acidentes Pessoais" : segmento || "Não informado";
}

/** Selo de status da lista. No Card 5 mostra a SITUAÇÃO REAL do contrato e a cor
 *  vem do tom (azul = emitida, amarelo = cobertura suspensa, vermelho = cancelada);
 *  nos demais cards segue o rótulo e a cor do card. Texto sempre legível: branco
 *  sobre azul/vermelho 600+ e grafite sobre o amarelo. */
export function seloDaProposta(
  proposta: PropostaWorkflow, corDoCard: string, rotuloDoCard: string,
): { classe: string; rotulo: string } {
  const sens = proposta.foto?.sensibilizacao;
  // Card 8: o selo mostra o status REAL do último movimento (ou que ele não é identificável).
  if (sens) return { classe: `${corDoCard} text-white`, rotulo: sens.statusMovimento || rotuloDoCard };
  const d = proposta.foto?.devolucao;
  // Card 7: o selo mostra o status REAL do último movimento, na cor do sub-card.
  if (d) return { classe: COR_SUBCARD_DEVOLUCAO[d.situacao], rotulo: d.status || ROTULO_SUBCARD_DEVOLUCAO[d.situacao] };
  const e = proposta.foto?.emitida;
  if (!e) return { classe: `${corDoCard} text-white`, rotulo: rotuloDoCard };
  const classe = e.tom === "cancelada" ? "bg-red-700 text-white"
    : e.tom === "suspensa" ? "bg-amber-400 text-slate-900"
    : "bg-blue-600 text-white";
  // Sem situação na fonte, o texto acompanha a cor — nunca "Emitida" num selo vermelho.
  const porTom = e.tom === "cancelada" ? "Cancelada" : e.tom === "suspensa" ? "Cobertura Suspensa" : rotuloDoCard;
  return { classe, rotulo: e.subSituacao || porTom };
}

export function estadoDaFoto(foto: FotoCard1): { rotulo: string; valor: string }[] {
  // Card 4: a fonte não tem assinatura/pagamento; tem a sub-situação, as
  // mensagens de crítica e a data de quitação (que pode não existir).
  // Card 8: o último movimento (e a data dele) e a situação ATUAL da proposta — estados diferentes.
  if (foto.sensibilizacao) {
    const s = foto.sensibilizacao;
    return [
      { rotulo: "Último movimento", valor: s.statusMovimento },
      { rotulo: "Data", valor: s.dataMovimento ? dataBr(s.dataMovimento) : "Não informada" },
      { rotulo: "Situação da proposta", valor: s.statusAtual },
    ];
  }
  // Card 7: devolução — onde está (sub-card), status do último movimento e a data dele.
  if (foto.devolucao) {
    const d = foto.devolucao;
    return [
      { rotulo: "Situação", valor: ROTULO_SUBCARD_DEVOLUCAO[d.situacao] },
      { rotulo: "Movimento", valor: d.status || "Sem Movimento" },
      { rotulo: d.situacao === "andamento" ? "Previsão" : "Data", valor: d.dataMovimento ? dataBr(d.dataMovimento) : "Não informada" },
    ];
  }
  // Card 6: rejeitada — situação, motivos do certificado, declínio e quitação.
  if (foto.rejeitada) {
    const r = foto.rejeitada;
    return [
      { rotulo: "Situação", valor: r.subSituacao || "Não informado" },
      { rotulo: "Motivos", valor: String(r.motivos) },
      { rotulo: "Declínio", valor: r.declinio ? dataBr(r.declinio) : "Não informado" },
      { rotulo: "Quitação", valor: r.quitacao ? dataBr(r.quitacao) : "Não informada" },
    ];
  }
  // Card 5: contrato emitido (VG ou AP) — situação real, emissão e segmento.
  if (foto.emitida) {
    return [
      { rotulo: "Situação", valor: foto.emitida.subSituacao || "Não informado" },
      { rotulo: "Emissão", valor: foto.emitida.emissao ? dataBr(foto.emitida.emissao) : "Não informada" },
      { rotulo: "Segmento", valor: rotuloSegmento(foto.emitida.segmento) },
    ];
  }
  if (foto.criticas !== undefined) {
    return [
      { rotulo: "Situação", valor: foto.subSituacao || "Não informado" },
      { rotulo: "Críticas", valor: String(foto.criticas) },
      { rotulo: "Quitação", valor: foto.quitacao ? dataBr(foto.quitacao) : "Não informada" },
    ];
  }
  return [
    { rotulo: "Assinatura", valor: rotulo(ROTULO_ASSINATURA, foto.assinatura) },
    { rotulo: "Pagamento", valor: rotulo(ROTULO_PAGO, foto.pago) },
    { rotulo: "Situação", valor: rotulo(ROTULO_SITUACAO, foto.situacao) },
  ];
}

/** Canais do "Enviar": cada um traz o destino ou `null` quando não há. O
 *  WhatsApp é o celular — telefone residencial não recebe WhatsApp. Com só o
 *  celular cadastrado, "telefone" e "WhatsApp" apontam para ele (como o
 *  diálogo sempre fez). */
export function canaisDeEnvio(contato: FotoCard1["contato"]) {
  return {
    email: contato.email,
    telefone: contato.residencial ?? contato.celular,
    whatsapp: contato.celular,
  };
}

/** A lista de UM card do Workflow, com a mesma forma venha ela da foto (Card 1)
 *  ou da carga legada (os outros sete) — assim os dois componentes que listam
 *  propostas não ramificam por fonte em cada linha do JSX. */
export interface ListaPio {
  carregando: boolean;
  buscando: boolean;
  disponivel: boolean;
  referencia: string | null;
  total: number;
  propostas: PropostaWorkflow[];
  /** Card 1: a foto existe, mas o detalhe dela já saiu da retenção da fato. */
  detalheIndisponivel: boolean;
  desatualizado: boolean;
  atualizacao: string | null;
  deFoto: boolean;
  /** Card 8: `identificacao` = lista por nº de identificação (não é "as mais antigas primeiro"). */
  ordem: string | null;
}

interface ConsultaLegada {
  data?: { disponivel: boolean; referencia: string | null; total: number; itens: unknown[] };
  isPending: boolean;
  isFetching: boolean;
}

export function listaDoCard(
  emFoto: boolean,
  legada: ConsultaLegada,
  mapearLegado: (item: never) => PropostaWorkflow,
  resumo: { data?: ResumoCard1; isPending: boolean },
  foto: { data?: PaginaCard1; isPending: boolean; isFetching: boolean },
  status: StatusWorkflow = STATUS_CARD1,
): ListaPio {
  if (!emFoto) {
    return {
      carregando: legada.isPending,
      buscando: legada.isFetching,
      disponivel: Boolean(legada.data?.disponivel),
      referencia: legada.data?.referencia ?? null,
      total: legada.data?.total ?? 0,
      propostas: (legada.data?.itens ?? []).map((i) => mapearLegado(i as never)),
      detalheIndisponivel: false,
      ordem: null,
      desatualizado: false,
      atualizacao: null,
      deFoto: false,
    };
  }
  const semFoto = Boolean(resumo.data?.disponivel) && !resumo.data?.referencia;
  const pagina = foto.data;
  return {
    // Sem foto publicada não há lista a pedir: não fica "consultando" para sempre.
    carregando: resumo.isPending || (!semFoto && foto.isPending && resumo.data?.disponivel === true),
    buscando: foto.isFetching,
    disponivel: semFoto ? true : Boolean(pagina?.disponivel),
    referencia: pagina?.referencia ?? resumo.data?.referencia ?? null,
    total: pagina?.total ?? 0,
    propostas: (pagina?.itens ?? []).map((i) =>
      propostaDoCard1(i, pagina?.referencia ?? null, pagina?.atualizacao ?? null, status)),
    detalheIndisponivel: pagina ? !pagina.detalhe_disponivel : false,
    ordem: pagina?.ordem ?? null,
    desatualizado: pagina?.desatualizado ?? resumo.data?.desatualizado ?? false,
    atualizacao: pagina?.atualizacao ?? resumo.data?.atualizacao ?? null,
    deFoto: true,
  };
}
