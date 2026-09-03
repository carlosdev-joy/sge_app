// Lógica PURA da aba Utilitários › Criar/editar arquivo (spec
// docs/spec-utilitarios-arquivos.md, F5): o contrato de
// `POST /utilitarios/arquivo/gravar`, as pré-validações do formulário (nome +
// extensão, caracteres fora do Latin-1, bytes) e a leitura do 409, que traz o
// que já existe. Sem React, sem rede.
//
// ⚠️ O servidor é a AUTORIDADE (normaliza CRLF→LF, recusa o que não cabe na
// codificação nomeando a posição, faz backup e escrita atômica). O que está aqui
// só evita uma ida à API que o usuário já sabe que vai falhar.
import { EXTENSAO_RE } from './utilitariosAdmin'
import { avisoNome, avisoPasta, erroLeitura, formatarTamanho, type ErroLeitura } from './utilitariosArquivo'

export type Codificacao = 'utf-8' | 'latin-1'

export interface PedidoGravacao {
  servidor: string
  diretorio: string
  nome: string
  extensao: string
  conteudo: string
  codificacao: Codificacao
  sobrescrever: boolean
}

export interface ResultadoGravacao {
  caminho: string
  tamanho_bytes: number
  sha256: string
  criado: boolean
  backup: string | null
  codificacao: string
  linhas: number
  duracao_ms: number
}

export interface Existente {
  tamanho_bytes: number
  modificado_em: string | null
}

export interface ErroGravacao extends ErroLeitura {
  /** Só no 409: o arquivo que já está lá. */
  existente?: Existente
}

// NAME_MAX (255) menos o que o servidor reserva para o `.tmp` e o `.bak`.
export const LIMITE_NOME_GRAVACAO_BYTES = 215

const CODIFICACOES: Codificacao[] = ['utf-8', 'latin-1']

export function codificacaoValida(v: unknown): Codificacao {
  return v === 'latin-1' ? 'latin-1' : 'utf-8'
}

export function extensaoValida(ext: string, permitidas: string[]): boolean {
  const s = (ext || '').trim().toLowerCase()
  return EXTENSAO_RE.test(s) && permitidas.includes(s)
}

export function nomeArquivoCompleto(nome: string, extensao: string): string {
  return `${(nome || '').trim()}.${(extensao || '').trim().toLowerCase()}`
}

/** "carga.2026.txt" → { nome: "carga.2026", extensao: "txt" }; sem ponto → extensão vazia. */
export function separarNomeExtensao(completo: string): { nome: string; extensao: string } {
  const s = (completo || '').trim()
  const i = s.lastIndexOf('.')
  if (i <= 0) return { nome: s, extensao: '' }
  return { nome: s.slice(0, i), extensao: s.slice(i + 1).toLowerCase() }
}

/** "/dados/bi/2026/x.txt" → { diretorio: "/dados/bi/2026", nome: "x.txt" }. */
export function pastaENomeDoCaminho(caminho: string): { diretorio: string; nome: string } {
  const s = (caminho || '').trim()
  const i = s.lastIndexOf('/')
  if (i < 0) return { diretorio: '', nome: s }
  return { diretorio: s.slice(0, i) || '/', nome: s.slice(i + 1) }
}

/** Aviso do campo Nome (sem a extensão): o que `avisoNome` diz, mais o teto de
 *  bytes do nome COMPLETO que o servidor exige para caber o `.tmp` e o `.bak`. */
export function avisoNomeBase(nome: string, extensao: string): string | null {
  const s = (nome || '').trim()
  if (!s) return null
  const base = avisoNome(s)
  if (base) return base
  if ([...s].some(c => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127)) return 'Sem caracteres de controle.'
  const completo = nomeArquivoCompleto(s, extensao || 'x')
  if (new TextEncoder().encode(completo).length > LIMITE_NOME_GRAVACAO_BYTES) {
    return `Nome longo demais para gravar (máximo ${LIMITE_NOME_GRAVACAO_BYTES} bytes com a extensão).`
  }
  return null
}

/** Primeiro caractere que não existe em Latin-1 (código > 255), com linha e posição. */
export function foraDoLatin1(texto: string): { linha: number; posicao: number; char: string } | null {
  let linha = 1
  for (let i = 0; i < texto.length; i++) {
    const c = texto.charCodeAt(i)
    if (c === 0x0a) { linha++; continue }
    if (c > 0xff) {
      // Par substituto (emoji) conta como um caractere só para o usuário.
      const ch = texto.codePointAt(i)! > 0xffff ? texto.slice(i, i + 2) : texto[i]
      return { linha, posicao: i, char: ch }
    }
  }
  return null
}

export function contarLinhas(texto: string): number {
  if (!texto) return 0
  return texto.split(/\r\n|\r|\n/).length - (/(\r\n|\r|\n)$/.test(texto) ? 1 : 0)
}

/** Bytes que o servidor vai gravar (antes da normalização de CRLF, que só encolhe). */
export function contarBytes(texto: string, cod: Codificacao): number {
  if (cod === 'latin-1') return texto.length
  return new TextEncoder().encode(texto).length
}

export interface CamposGravacao {
  diretorio: string
  nome: string
  extensao: string
  conteudo: string
  codificacao: Codificacao
}

/** Tudo que precisa estar certo para o Gravar ligar. */
export function gravacaoPronta(c: CamposGravacao, raizes: string[], extensoes: string[], podeGravar: boolean): boolean {
  if (!podeGravar) return false
  if (!c.diretorio.trim() || !c.nome.trim()) return false
  const ap = avisoPasta(c.diretorio, raizes)
  if (ap && ap.tom === 'erro') return false
  if (avisoNomeBase(c.nome, c.extensao)) return false
  if (!extensaoValida(c.extensao, extensoes)) return false
  if (c.codificacao === 'latin-1' && foraDoLatin1(c.conteudo)) return false
  return true
}

/** Erro do `apiFetch` na gravação: o 409 vem com `detail = {mensagem, existente}`. */
/** Extensão pré-selecionada: `txt` quando liberada (é a que menos surpreende),
 *  senão a primeira da lista, senão nada. */
export function extensaoPadrao(extensoes: string[]): string {
  return extensoes.includes('txt') ? 'txt' : (extensoes[0] ?? '')
}

export function erroGravacao(e: unknown): ErroGravacao {
  const err = e as { status?: number; detail?: unknown } | null
  const detail = err?.detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && 'mensagem' in detail) {
    const d = detail as { mensagem: unknown; existente?: unknown }
    const base: ErroGravacao = {
      status: typeof err?.status === 'number' ? err.status : null,
      mensagem: String(d.mensagem),
    }
    const ex = d.existente as Partial<Existente> | undefined
    if (ex && typeof ex === 'object') {
      base.existente = {
        tamanho_bytes: typeof ex.tamanho_bytes === 'number' ? ex.tamanho_bytes : 0,
        modificado_em: typeof ex.modificado_em === 'string' ? ex.modificado_em : null,
      }
    }
    return base
  }
  return erroLeitura(e)
}

/** Resumo do resultado, em frases curtas. */
export function resumoGravacao(r: ResultadoGravacao): string[] {
  const partes = [
    r.criado ? 'arquivo criado' : 'arquivo sobrescrito',
    formatarTamanho(r.tamanho_bytes),
    `${r.linhas} ${r.linhas === 1 ? 'linha' : 'linhas'}`,
    `codificação ${r.codificacao}`,
    `sha256 ${r.sha256.slice(0, 12)}…`,
  ]
  if (r.backup) partes.push(`cópia de segurança em ${r.backup}`)
  partes.push(`${(r.duracao_ms / 1000).toFixed(1).replace('.', ',')} s`)
  return partes
}

export const CODIFICACOES_OPCOES: { valor: Codificacao; rotulo: string }[] = [
  { valor: 'utf-8', rotulo: 'UTF-8' },
  { valor: 'latin-1', rotulo: 'Latin-1 (ISO-8859-1)' },
]

export function ehCodificacao(v: string): v is Codificacao {
  return (CODIFICACOES as string[]).includes(v)
}
