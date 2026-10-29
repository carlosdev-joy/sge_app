// Card 1 (Pendentes de Assinatura) lendo a FOTO diária — parte PURA (RITM0117336).
//
// Sem react-query nem apiFetch: o que está aqui roda no node nos testes
// (`tests/test_pio_card1_front.py`). Os hooks de leitura ficam em `pioCard1.ts`,
// que reexporta este módulo — os componentes importam de um lugar só.

import type { FotoCard1, PropostaWorkflow, StatusWorkflow } from "./workflow";
import { regiaoDaUf } from "./regiao";

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

/** Cards do Workflow que leem a foto diária. */
export const STATUS_DE_FOTO: StatusWorkflow[] = [STATUS_CARD1, STATUS_CARD2, STATUS_CARD3, STATUS_CARD4];

const PREFIXO_ID: Partial<Record<StatusWorkflow, string>> = {
  [STATUS_CARD1]: "pio1", [STATUS_CARD2]: "pio2", [STATUS_CARD3]: "pio3", [STATUS_CARD4]: "pio4",
};

export interface ResumoCard1 {
  disponivel: boolean;
  referencia: string | null;
  atualizacao: string | null;
  lote_id: string | null;
  desatualizado: boolean;
  dias_defasagem: number;
  premio_total: number | null;
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
    daysInPending: status === STATUS_CARD3 ? 0 : item.dias_pendente,
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

export function estadoDaFoto(foto: FotoCard1): { rotulo: string; valor: string }[] {
  // Card 4: a fonte não tem assinatura/pagamento; tem a sub-situação, as
  // mensagens de crítica e a data de quitação (que pode não existir).
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
    desatualizado: pagina?.desatualizado ?? resumo.data?.desatualizado ?? false,
    atualizacao: pagina?.atualizacao ?? resumo.data?.atualizacao ?? null,
    deFoto: true,
  };
}
