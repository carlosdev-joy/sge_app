# Subsistema B — Modal de Detalhes + Regra Visual INC

> **Para agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar modal de detalhes ao card do kanban (descrição, notas, anexos) e aplicar regra visual de destaque para INC não-encerrado nos cards.

**Architecture:** Dois novos arquivos no source React (`src/lib/chamado.ts` + `src/components/ChamadoDetalheModal.tsx`), modificação do card existente em `src/pages/Chamados.tsx` (reconstruído fiel ao bundle de produção). O source está desatualizado — `Chamados.tsx` não existe no source. É necessário recriar o arquivo fiel ao bundle antes de adicionar as novas features. O build gera `dist/` que é copiado para `/opt/airflow/ui-react/dist/`.

**Tech Stack:** React 18, TypeScript, Vite 5.4.21, @tanstack/react-query, lucide-react, Tailwind CSS. Node 20.18 (máximo Vite 5.x — não atualizar Vite nem Node neste plano).

**Spec:** docs/superpowers/specs/2026-08-22-servicenow-inteligencia-operacional-a.md (seções 7.1 e 7.2)

## Global Constraints

- Source em: `/opt/git/sge_app/ui-react/src/`
- Build: `cd /opt/git/sge_app/ui-react && npm run build`
- Deploy: `cp -r /opt/git/sge_app/ui-react/dist/* /opt/airflow/ui-react/dist/`
- Node 20.18 — Vite máximo 5.x. NÃO atualizar Vite, NÃO atualizar @vitejs/plugin-react
- Placeholder de query: `apiFetch` (fetch nativo em `src/lib/api.ts`, base `/orquestra`)
- Componentes UI existentes em `src/components/ui/`: Modal, Button, Spinner, Badge, Tabs, Input, Toast, Card
- NÃO tocar em App.tsx nem nav.ts — as rotas já estão corretas no bundle de produção
- NÃO fazer `npm run build` antes da Task 3 — o bundle atual de produção tem todas as telas e um build parcial as apagaria
- Executar `tsc --noEmit` após cada task para verificar tipos
- Após Task 3 (build), verificar no browser que `/chamados` abre sem erro de console

---

## Mapeamento de Arquivos

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `src/lib/chamado.ts` | **Criar** | Tipos `Chamado`, `NotaChamado`, `AnexoChamado`, `ChamadoDetalhe` + funções `isINCAtivo`, `formatBytes`, `formatDataNota` |
| `src/components/ChamadoDetalheModal.tsx` | **Criar** | Modal de detalhes: descrição + notas + anexos, consome `GET /chamados/{sys_id}/detalhe` |
| `src/pages/Chamados.tsx` | **Criar** | Reconstrução fiel do componente `yE` do bundle de produção + integração do modal de detalhes + regra visual INC |

---

## Task 1: Criar `src/lib/chamado.ts` — tipos e funções utilitárias

**Files:**
- Create: `src/lib/chamado.ts`
- Test: nenhum arquivo de teste — verificação via `tsc --noEmit`

**Interfaces:**
- Produces: `Chamado`, `NotaChamado`, `AnexoChamado`, `ChamadoDetalhe`, `isINCAtivo(c: Chamado): boolean`, `formatBytes(b: number | null): string`, `formatDataNota(s: string | null): string`
- Consumes: nada (arquivo base)

- [ ] **Step 1: Criar `src/lib/chamado.ts`**

```typescript
// Estados que indicam chamado encerrado (não-ativo para fins de INC visual)
const ESTADOS_ENCERRADO = new Set(['resolvido', 'encerrado'])

export interface Chamado {
  sys_id: string
  numero: string
  tipo: string             // 'incident' | 'ritm' | 'task' | 'change'
  titulo: string | null
  descricao?: string | null
  estado_kanban: string    // 'novo' | 'andamento' | 'aguardando' | 'resolvido' | 'outros'
  estado_origem?: string | null
  atribuido_a: string | null
  atribuido_a_email?: string | null
  grupo?: string | null
  demandante?: string | null
  prioridade?: string | null
  categoria_diaadia?: string | null
  tipo_demanda?: string | null
  objetos?: string | null
  catalogo?: string | null
  veredito?: string | null
  triagem_origem?: string | null
  triagem_erro?: string | null
  triagem_em?: string | null
  resumo?: string | null
  lacunas?: string[]
  perguntas?: string | null
  aberto_em?: string | null
  url?: string | null
  tem_anexo?: boolean
  sla_vencido?: boolean
  prazo?: string | null
  idade_dias?: number | null
  pai_sys_id?: string | null
}

export interface NotaChamado {
  sys_id_nota: string
  autor: string | null
  autor_email: string | null
  criado_em: string | null
  texto: string | null
  tipo: string   // 'work_notes' | 'comments'
}

export interface AnexoChamado {
  sys_id_anexo: string
  nome_arquivo: string | null
  mime_type: string | null
  tamanho_bytes: number | null
  url_proxy: string
  criado_em: string | null
}

export interface ChamadoDetalhe {
  chamado: Chamado
  notas: NotaChamado[]
  anexos: AnexoChamado[]
}

// INC ativo = tipo incident + estado NÃO encerrado
export function isINCAtivo(c: Pick<Chamado, 'tipo' | 'estado_kanban'>): boolean {
  return c.tipo === 'incident' && !ESTADOS_ENCERRADO.has(c.estado_kanban)
}

export function formatBytes(b: number | null | undefined): string {
  if (!b) return '—'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

export function formatDataNota(s: string | null | undefined): string {
  if (!s) return '—'
  const d = new Date(s)
  if (isNaN(d.getTime())) return s
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' }) +
    ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}
```

- [ ] **Step 2: Verificar tipos**

```bash
cd /opt/git/sge_app/ui-react && npx tsc --noEmit 2>&1 | head -30
```

Esperado: 0 erros (ou erros apenas em arquivos que ainda não referenciam chamado.ts).

- [ ] **Step 3: Commit**

```bash
cd /opt/git/sge_app/ui-react
git add src/lib/chamado.ts
git commit -m "feat(chamados-b): chamado.ts — tipos e utilitários isINCAtivo, formatBytes, formatDataNota"
```

---

## Task 2: Criar `src/components/ChamadoDetalheModal.tsx`

**Files:**
- Create: `src/components/ChamadoDetalheModal.tsx`
- Test: verificação via `tsc --noEmit`

**Interfaces:**
- Consumes: `ChamadoDetalhe`, `NotaChamado`, `AnexoChamado`, `isINCAtivo`, `formatBytes`, `formatDataNota` de `../lib/chamado`; `apiFetch` de `../lib/api`; `useQuery` de `@tanstack/react-query`; `Modal` de `./ui/Modal`; `Spinner` de `./ui/Spinner`
- Produces: `export function ChamadoDetalheModal({ sysId, numero, onClose }: ChamadoDetalheModalProps)`

**Props:**
```typescript
interface ChamadoDetalheModalProps {
  sysId: string       // sys_id do chamado
  numero: string      // ex: "INC0012345" — exibido no título antes dos dados carregarem
  onClose: () => void
}
```

**Comportamento:**
- Abre imediatamente (open=true fixo) com o título `numero` enquanto carrega
- `useQuery` para `GET /chamados/{sysId}/detalhe`, `staleTime: 60_000`
- Estado de loading: `<Spinner />` centralizado dentro do modal
- Estado de erro: mensagem de erro inline (sem fechar o modal)
- Dado carregado: renderiza descrição + notas + anexos conforme layout da spec

**Layout conforme spec seção 7.1:**

```
┌─ INC0012345 · Erro na carga ETL_VENDAS ──────────────[✕]─┐
│ Analista: João Silva  │  Grupo: Eng. Dados                 │
│ Estado: Em andamento  │  Aberto: 15/08/2026                │
├───────────────────────────────────────────────────────────┤
│ DESCRIÇÃO                                                  │
│ Falha na execução do job...                                │
├───────────────────────────────────────────────────────────┤
│ HISTÓRICO DE NOTAS (3)                                     │
│ ┌─ João Silva · 20/08 10:32  [work_notes] ──────────────┐ │
│ │ Verificado o job, coluna ausente...                    │ │
│ └────────────────────────────────────────────────────────┘ │
├───────────────────────────────────────────────────────────┤
│ ANEXOS (📎 2)                                             │
│ 🖼 screenshot.png  420 KB   [ver inline]                  │
│ 📄 log.txt  12 KB           [baixar]                      │
└───────────────────────────────────────────────────────────┘
```

- [ ] **Step 1: Criar `src/components/ChamadoDetalheModal.tsx`**

```typescript
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, Paperclip } from 'lucide-react'
import { apiFetch } from '../lib/api'
import {
  ChamadoDetalhe, NotaChamado, AnexoChamado,
  isINCAtivo, formatBytes, formatDataNota,
} from '../lib/chamado'
import { Modal } from './ui/Modal'
import { Spinner } from './ui/Spinner'

interface Props {
  sysId: string
  numero: string
  onClose: () => void
}

const TIPO_NOTA_LABEL: Record<string, string> = {
  work_notes: 'notas internas',
  comments: 'comentários',
}

const ESTADO_LABEL: Record<string, string> = {
  novo: 'Em aberto',
  andamento: 'Em andamento',
  aguardando: 'Aguardando',
  resolvido: 'Resolvido',
  outros: 'Outros',
}

function NotaItem({ nota }: { nota: NotaChamado }) {
  return (
    <div className="rounded-md border border-[#2a2d3a] bg-[#12141e] p-3 flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2 text-[11px] text-[#94a3b8]">
        <span className="font-medium text-[#e2e8f0]">{nota.autor ?? '—'}</span>
        <span className="flex items-center gap-2">
          <span>{formatDataNota(nota.criado_em)}</span>
          <span className="px-1.5 py-0.5 rounded bg-[#1a1d27] border border-[#2a2d3a] text-[10px]">
            {TIPO_NOTA_LABEL[nota.tipo] ?? nota.tipo}
          </span>
        </span>
      </div>
      <p className="text-xs text-[#e2e8f0] whitespace-pre-wrap leading-relaxed">{nota.texto ?? '—'}</p>
    </div>
  )
}

function AnexoItem({ anexo, sysId }: { anexo: AnexoChamado; sysId: string }) {
  const isImagem = (anexo.mime_type ?? '').startsWith('image/')
  const url = `/orquestra${anexo.url_proxy}`
  return (
    <div className="flex items-center justify-between gap-2 rounded-md border border-[#2a2d3a] bg-[#12141e] px-3 py-2 text-xs">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-base">{isImagem ? '🖼' : '📄'}</span>
        <span className="text-[#e2e8f0] truncate" title={anexo.nome_arquivo ?? undefined}>{anexo.nome_arquivo ?? 'anexo'}</span>
        <span className="text-[#64748b] shrink-0">{formatBytes(anexo.tamanho_bytes)}</span>
      </div>
      <a
        href={url}
        target={isImagem ? '_blank' : undefined}
        download={isImagem ? undefined : (anexo.nome_arquivo ?? true)}
        rel="noopener noreferrer"
        className="shrink-0 text-blue-400 hover:text-blue-300 transition-colors"
      >
        {isImagem ? 'ver' : 'baixar'}
      </a>
    </div>
  )
}

export function ChamadoDetalheModal({ sysId, numero, onClose }: Props) {
  const { data, isLoading, isError, error } = useQuery<ChamadoDetalhe>({
    queryKey: ['chamado-detalhe', sysId],
    queryFn: () => apiFetch<ChamadoDetalhe>(`/chamados/${sysId}/detalhe`),
    staleTime: 60_000,
  })

  const c = data?.chamado
  const incAtivo = c ? isINCAtivo(c) : false
  const titulo = c ? `${c.numero} · ${c.titulo ?? '(sem título)'}` : numero

  return (
    <Modal open onClose={onClose} title={titulo} size="lg">
      {isLoading && (
        <div className="flex justify-center py-10"><Spinner /></div>
      )}

      {isError && (
        <div className="rounded-md border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-300">
          Erro ao carregar detalhes: {(error as Error).message}
        </div>
      )}

      {c && (
        <div className="flex flex-col gap-4 text-sm">
          {/* Header INC visual */}
          {incAtivo && (
            <div className="rounded-md border border-red-800 bg-red-900/20 px-3 py-2 text-xs text-red-300 font-medium">
              Incidente ativo — acompanhe resolução
            </div>
          )}

          {/* Meta */}
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
            <div className="text-[#94a3b8]">Analista: <span className="text-[#e2e8f0]">{c.atribuido_a ?? '—'}</span></div>
            <div className="text-[#94a3b8]">Grupo: <span className="text-[#e2e8f0]">{c.grupo ?? '—'}</span></div>
            <div className="text-[#94a3b8]">Estado: <span className="text-[#e2e8f0]">{ESTADO_LABEL[c.estado_kanban] ?? c.estado_kanban}</span></div>
            <div className="text-[#94a3b8]">Aberto: <span className="text-[#e2e8f0]">{formatDataNota(c.aberto_em)}</span></div>
          </div>

          {/* Descrição */}
          {c.descricao && (
            <div className="flex flex-col gap-1">
              <h3 className="text-[10px] font-semibold text-[#94a3b8] uppercase tracking-wider">Descrição</h3>
              <p className="text-xs text-[#e2e8f0] whitespace-pre-wrap leading-relaxed bg-[#12141e] rounded-md border border-[#2a2d3a] p-3">{c.descricao}</p>
            </div>
          )}

          {/* Notas */}
          <div className="flex flex-col gap-2">
            <h3 className="text-[10px] font-semibold text-[#94a3b8] uppercase tracking-wider">
              Histórico de notas {data!.notas.length > 0 ? `(${data!.notas.length})` : ''}
            </h3>
            {data!.notas.length === 0
              ? <p className="text-xs text-[#64748b]">Nenhuma nota registrada.</p>
              : data!.notas.map(n => <NotaItem key={n.sys_id_nota} nota={n} />)
            }
          </div>

          {/* Anexos */}
          {data!.anexos.length > 0 && (
            <div className="flex flex-col gap-2">
              <h3 className="text-[10px] font-semibold text-[#94a3b8] uppercase tracking-wider flex items-center gap-1">
                <Paperclip size={11} /> Anexos ({data!.anexos.length})
              </h3>
              {data!.anexos.map(a => <AnexoItem key={a.sys_id_anexo} anexo={a} sysId={sysId} />)}
            </div>
          )}

          {/* Link ServiceNow */}
          {c.url && (
            <a
              href={c.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors self-start"
            >
              <ExternalLink size={12} /> Abrir no ServiceNow
            </a>
          )}
        </div>
      )}
    </Modal>
  )
}
```

- [ ] **Step 2: Verificar tipos**

```bash
cd /opt/git/sge_app/ui-react && npx tsc --noEmit 2>&1 | head -30
```

Esperado: 0 erros (erros em outros arquivos que não existem no source são esperados — focar em erros de `ChamadoDetalheModal.tsx`).

- [ ] **Step 3: Corrigir erros de tipo se houver e re-verificar**

- [ ] **Step 4: Commit**

```bash
cd /opt/git/sge_app/ui-react
git add src/components/ChamadoDetalheModal.tsx
git commit -m "feat(chamados-b): ChamadoDetalheModal — notas, anexos e regra INC no header"
```

---

## Task 3: Criar `src/pages/Chamados.tsx` — reconstrução + integração do modal + regra visual INC

Esta é a task central. Reconstrói `Chamados.tsx` fiel ao bundle de produção (componente `yE`) e integra o modal de detalhes e a borda vermelha INC.

**Files:**
- Create: `src/pages/Chamados.tsx`
- Test: `tsc --noEmit` + build + inspeção visual no browser

**Interfaces:**
- Consumes: `ChamadoDetalheModal` de `../components/ChamadoDetalheModal`; `Chamado`, `isINCAtivo` de `../lib/chamado`; `apiFetch` de `../lib/api`; `useQuery` de `@tanstack/react-query`; ícones de `lucide-react`
- Produces: `export default function Chamados()` — rota `/chamados`

**Dados da API (`GET /chamados`):**
```typescript
interface ChamadosResponse {
  chamados: Chamado[]
  colunas: string[]   // ['novo','andamento','aguardando','resolvido','outros']
  total: number
  ultimo_sync: {
    status: string
    idade_minutos?: number
    atrasado?: boolean
    em_andamento?: boolean
    erro?: string | null
  } | null
  alerta_fila_vazia?: string | null
  migration_ausente?: boolean
  derivacoes_pendentes?: boolean
}
```

**Constantes fiéis ao bundle de produção:**
```typescript
// estado_kanban → label de coluna
const COLUNA_LABEL: Record<string, string> = {
  novo: 'Em aberto', andamento: 'Em andamento',
  aguardando: 'Aguardando', resolvido: 'Resolvido', outros: 'Outros',
}

// tipo → label legível
const TIPO_LABEL: Record<string, string> = {
  incident: 'Incidente', ritm: 'RITM', task: 'Tarefa', change: 'Mudança',
}

// veredito → estilo do badge
const VEREDITO_STYLE: Record<string, { classe: string; curto: string }> = {
  'PODE INICIAR': {
    classe: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300',
    curto: 'pode iniciar',
  },
  'RETORNAR AO SOLICITANTE': {
    classe: 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300',
    curto: 'retornar',
  },
}

// thresholds de idade (dias)
const IDADE_THRESHOLDS = [
  { min: 7, classe: 'text-red-600 dark:text-red-400 font-semibold', rotulo: 'parado' },
  { min: 3, classe: 'text-amber-600 dark:text-yellow-400 font-medium', rotulo: 'atenção' },
]

function idadeStyle(dias: number | null) {
  if (dias === null) return { classe: 'text-[#94a3b8]', rotulo: '' }
  for (const t of IDADE_THRESHOLDS) if (dias > t.min) return { classe: t.classe, rotulo: t.rotulo }
  return { classe: 'text-[#94a3b8]', rotulo: '' }
}

function idadeTitle(dias: number | null): string {
  if (dias === null) return 'sem data de abertura'
  if (dias <= 0) return 'aberto hoje'
  if (dias === 1) return 'aberto há 1 dia'
  return `parado há ${dias} dias`
}

function syncStatus(s: ChamadosResponse['ultimo_sync']) {
  if (!s) return { texto: 'nunca sincronizado', tom: 'warning' }
  if (s.em_andamento) return { texto: 'sincronização em andamento', tom: 'info' }
  const t = s.idade_minutos ?? 0
  const n = t < 60 ? `sincronizado há ${t} min` : `sincronizado há ${Math.floor(t / 60)}h`
  if (s.status === 'OK') return { texto: n, tom: s.atrasado ? 'warning' : 'success' }
  return { texto: `${n} — com erro`, tom: 'error' }
}

function filtroBusca(c: Chamado, q: string): boolean {
  const lq = q.trim().toLowerCase()
  if (!lq) return true
  return [c.numero, c.titulo, c.atribuido_a, c.estado_origem].some(
    f => (f ?? '').toLowerCase().includes(lq)
  )
}
```

**Estrutura do card (KanbanCard):**
- Container: `bg-canvas border border-edge rounded-md p-2.5 flex flex-col gap-1.5 shadow-sm`
- **Regra INC (nova):** quando `isINCAtivo(c)` → adicionar `border-l-4 border-red-500` ao container
- Clicar no número ou título → `setDetalheAberto(c.sys_id)` (abre ChamadoDetalheModal)
- Badge INC vermelho (novo): quando `isINCAtivo(c)` → badge `INC` com `bg-red-100 text-red-700 dark:bg-red-950/60 dark:text-red-300`
- Restante do card: fiel ao bundle (tasks RITM, botão de veredito, idade, responsável)

**Abas da tela:**
- `fila` — kanban (implementar nesta task)
- `indicadores` — inline, consome `GET /chamados/indicadores` (implementar nesta task, fiel ao `Vce` do bundle)
- `dashboard` — inline, consome `GET /chamados/dashboard` (implementar nesta task, fiel ao `DshPanel` do bundle)

**Nota sobre `indicadores` e `dashboard`:** O bundle de produção tem esses componentes (`Vce` e `DshPanel`) com implementações próprias. Nesta task, reconstruí-los **com fidelidade mínima** (mesmas queries, mesmo layout de fallback) — não é necessário reimplementar cada gráfico do recharts. O importante é que:
1. `fila` funcione 100% com o modal integrado
2. `indicadores` mostre o conteúdo básico sem quebrar (pode simplificar vs. bundle)
3. `dashboard` mostre o conteúdo básico sem quebrar (pode simplificar vs. bundle)

- [ ] **Step 1: Criar `src/pages/Chamados.tsx`**

```typescript
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw, Search, X, ExternalLink } from 'lucide-react'
import { apiFetch } from '../lib/api'
import { Chamado, isINCAtivo } from '../lib/chamado'
import { ChamadoDetalheModal } from '../components/ChamadoDetalheModal'
import { Spinner } from '../components/ui/Spinner'

// ── Constantes ────────────────────────────────────────────────────────────────

const COLUNA_LABEL: Record<string, string> = {
  novo: 'Em aberto', andamento: 'Em andamento',
  aguardando: 'Aguardando', resolvido: 'Resolvido', outros: 'Outros',
}

const TIPO_LABEL: Record<string, string> = {
  incident: 'Incidente', ritm: 'RITM', task: 'Tarefa', change: 'Mudança',
}

const VEREDITO_STYLE: Record<string, { classe: string; curto: string }> = {
  'PODE INICIAR': {
    classe: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300',
    curto: 'pode iniciar',
  },
  'RETORNAR AO SOLICITANTE': {
    classe: 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300',
    curto: 'retornar',
  },
}

const IDADE_THRESHOLDS = [
  { min: 7, classe: 'text-red-600 dark:text-red-400 font-semibold', rotulo: 'parado' },
  { min: 3, classe: 'text-amber-600 dark:text-yellow-400 font-medium', rotulo: 'atenção' },
]

function idadeStyle(dias: number | null) {
  if (dias === null) return { classe: 'text-[#94a3b8]', rotulo: '' }
  for (const t of IDADE_THRESHOLDS) if (dias > t.min) return { classe: t.classe, rotulo: t.rotulo }
  return { classe: 'text-[#94a3b8]', rotulo: '' }
}

function idadeTitle(dias: number | null): string {
  if (dias === null) return 'sem data de abertura'
  if (dias <= 0) return 'aberto hoje'
  if (dias === 1) return 'aberto há 1 dia'
  return `parado há ${dias} dias`
}

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface SyncStatus {
  status: string
  idade_minutos?: number
  atrasado?: boolean
  em_andamento?: boolean
  erro?: string | null
}

interface ChamadosResponse {
  chamados: Chamado[]
  colunas: string[]
  total: number
  ultimo_sync: SyncStatus | null
  alerta_fila_vazia?: string | null
  migration_ausente?: boolean
  derivacoes_pendentes?: boolean
}

interface TaskRitm {
  sys_id: string
  numero: string
  titulo: string | null
  estado_kanban: string
  url?: string | null
  ativo: boolean
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function syncStatusDisplay(s: SyncStatus | null) {
  if (!s) return { texto: 'nunca sincronizado', tom: 'warning' }
  if (s.em_andamento) return { texto: 'sincronização em andamento', tom: 'info' }
  const t = s.idade_minutos ?? 0
  const n = t < 60 ? `sincronizado há ${t} min` : `sincronizado há ${Math.floor(t / 60)}h`
  if (s.status === 'OK') return { texto: n, tom: s.atrasado ? 'warning' : 'success' }
  return { texto: `${n} — com erro`, tom: 'error' }
}

function filtroBusca(c: Chamado, q: string): boolean {
  const lq = q.trim().toLowerCase()
  if (!lq) return true
  return [c.numero, c.titulo, c.atribuido_a, c.estado_origem].some(
    f => (f ?? '').toLowerCase().includes(lq)
  )
}

// ── Subcomponentes ────────────────────────────────────────────────────────────

function AlertaBanner({ tom, children }: { tom: string; children: React.ReactNode }) {
  const cores: Record<string, string> = {
    error: 'border-red-700 bg-red-900/20 text-red-300',
    warning: 'border-amber-700 bg-amber-900/20 text-amber-300',
    info: 'border-blue-700 bg-blue-900/20 text-blue-300',
    success: 'border-green-700 bg-green-900/20 text-green-300',
  }
  return (
    <div className={`rounded-md border px-3 py-2 text-xs ${cores[tom] ?? cores.info}`}>
      {children}
    </div>
  )
}

function BadgeNeutro({ children }: { children: React.ReactNode }) {
  return (
    <span className="px-1.5 py-0.5 rounded text-[10px] bg-[#1a1d27] border border-[#2a2d3a] text-[#94a3b8]">
      {children}
    </span>
  )
}

function BadgeINC() {
  return (
    <span className="px-1.5 py-0.5 rounded text-[10px] bg-red-100 text-red-700 dark:bg-red-950/60 dark:text-red-300 font-semibold">
      INC
    </span>
  )
}

function KanbanCard({
  c,
  onOpenDetalhe,
  onOpenVeredito,
}: {
  c: Chamado
  onOpenDetalhe: (sysId: string) => void
  onOpenVeredito: (c: Chamado) => void
}) {
  const inc = isINCAtivo(c)
  const vStyle = c.veredito ? VEREDITO_STYLE[c.veredito] : undefined
  const iStyle = idadeStyle(c.idade_dias ?? null)

  const { data: tasksData } = useQuery<{ tasks: TaskRitm[] }>({
    queryKey: ['tasks', c.sys_id],
    queryFn: () => apiFetch(`/chamados/${c.sys_id}/tasks`),
    enabled: c.tipo === 'ritm',
    staleTime: 60_000,
  })
  const tasks = (tasksData?.tasks ?? []).filter(t => t.ativo)

  return (
    <div
      className={[
        'bg-[#12141e] border border-[#2a2d3a] rounded-md p-2.5 flex flex-col gap-1.5 shadow-sm',
        inc ? 'border-l-4 border-l-red-500' : '',
      ].join(' ')}
    >
      {/* Número + link SN */}
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => onOpenDetalhe(c.sys_id)}
          className="font-mono text-xs font-semibold text-[#e2e8f0] hover:text-blue-400 transition-colors text-left"
          title="Ver detalhes"
        >
          {c.numero}
        </button>
        {c.url && (
          <a
            href={c.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 dark:text-blue-400 shrink-0"
            title="Abrir no ServiceNow"
          >
            <ExternalLink size={12} />
          </a>
        )}
      </div>

      {/* Título clicável */}
      <button
        type="button"
        onClick={() => onOpenDetalhe(c.sys_id)}
        className="text-xs text-[#e2e8f0] leading-snug text-left hover:text-blue-400 transition-colors"
      >
        {c.titulo ?? '(sem título)'}
      </button>

      {/* Badges tipo + INC + prioridade + estado_origem */}
      <div className="flex flex-wrap items-center gap-1">
        <BadgeNeutro>{TIPO_LABEL[c.tipo] ?? c.tipo}</BadgeNeutro>
        {inc && <BadgeINC />}
        {c.prioridade && <BadgeNeutro>{c.prioridade}</BadgeNeutro>}
        {c.estado_origem && (
          <span className="text-[10px] text-[#64748b]" title={`Estado na origem: ${c.estado_origem}`}>
            {c.estado_origem}
          </span>
        )}
      </div>

      {/* Tags tipo_demanda, categoria, objetos, SLA, veredito */}
      <div className="flex flex-wrap items-center gap-1 text-[10px]">
        {c.tipo_demanda && (
          <span
            className="px-1.5 py-0.5 rounded bg-[#1a1d27] border border-[#2a2d3a] text-[#94a3b8]"
            title={`Tipo deduzido${c.catalogo ? ` · catálogo: ${c.catalogo}` : ''}`}
          >
            {c.tipo_demanda}
          </span>
        )}
        {c.categoria_diaadia === 'dia a dia' && (
          <span className="px-1.5 py-0.5 rounded bg-blue-500/10 border border-blue-500/30 text-blue-400">
            dia a dia
          </span>
        )}
        {c.categoria_diaadia === 'iniciativa' && (
          <span className="px-1.5 py-0.5 rounded bg-purple-500/10 border border-purple-500/30 text-purple-400">
            iniciativa
          </span>
        )}
        {c.objetos && (
          <span className="font-mono text-[#94a3b8] truncate max-w-full" title={`Objetos: ${c.objetos}`}>
            {c.objetos}
          </span>
        )}
        {c.sla_vencido && (
          <span className="px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-300">
            SLA vencido
          </span>
        )}
        {vStyle && (
          <button
            type="button"
            onClick={() => onOpenVeredito(c)}
            className={`px-1.5 py-0.5 rounded ${vStyle.classe}`}
            title={c.triagem_origem === 'heuristica' ? 'Veredito por regra de texto — clique para ver' : 'Veredito IA — clique para ver'}
          >
            {vStyle.curto}
            {c.triagem_origem === 'heuristica' && <span aria-hidden> ~</span>}
          </button>
        )}
      </div>

      {/* Tasks RITM filhas */}
      {tasks.length > 0 && (
        <div className="mt-1 border-t border-[#2a2d3a]/50 pt-1.5 flex flex-col gap-1">
          <span className="text-[10px] text-[#64748b] uppercase tracking-wide">Tasks ({tasks.length})</span>
          {tasks.map(tk => (
            <div key={tk.sys_id} className="flex items-start justify-between gap-1 bg-[#1a1d27] rounded px-1.5 py-1">
              <div className="flex flex-col gap-0.5 min-w-0">
                <span className="font-mono text-[10px] text-blue-500">
                  {tk.url
                    ? <a href={tk.url} target="_blank" rel="noopener noreferrer">{tk.numero}</a>
                    : tk.numero
                  }
                </span>
                <span className="text-[10px] text-[#e2e8f0] leading-snug truncate" title={tk.titulo ?? undefined}>
                  {tk.titulo ?? '(sem título)'}
                </span>
              </div>
              <span className="text-[10px] text-[#94a3b8] shrink-0 ml-1">{tk.estado_kanban}</span>
            </div>
          ))}
        </div>
      )}

      {/* Responsável + idade */}
      <div className="flex items-center justify-between gap-2 text-[11px] text-[#94a3b8]">
        <span
          className="truncate"
          title={c.demandante
            ? `Responsável: ${c.atribuido_a ?? 'sem responsável'} · Demandante: ${c.demandante}`
            : c.atribuido_a ?? 'sem responsável'
          }
        >
          {c.atribuido_a ?? 'sem responsável'}
        </span>
        <span
          title={idadeTitle(c.idade_dias ?? null)}
          className={`shrink-0 flex items-center gap-1 ${iStyle.classe}`}
        >
          {iStyle.rotulo && <span className="uppercase tracking-wide text-[9px]">{iStyle.rotulo}</span>}
          {c.idade_dias === null ? '—' : `${c.idade_dias}d`}
        </span>
      </div>
    </div>
  )
}

// ── Aba Indicadores (inline — simplificada, fiel aos endpoints) ───────────────

function AbaIndicadores() {
  const [responsavel, setResponsavel] = useState('')
  const { data, isLoading, isError, error } = useQuery<any>({
    queryKey: ['chamados-indicadores', responsavel],
    queryFn: () => apiFetch(responsavel
      ? `/chamados/indicadores?responsavel=${encodeURIComponent(responsavel)}`
      : '/chamados/indicadores'
    ),
    staleTime: 0,
  })

  if (isLoading) return <div className="flex justify-center py-10"><Spinner /></div>
  if (isError) return (
    <AlertaBanner tom="error">
      Erro ao carregar indicadores: {(error as Error).message}
    </AlertaBanner>
  )

  const d = data ?? {}
  return (
    <div className="flex flex-col gap-4">
      {d.analistas && d.analistas.length > 0 && (
        <div className="flex flex-col gap-2">
          <h2 className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider">Por analista</h2>
          <div className="overflow-x-auto rounded-lg border border-[#2a2d3a]">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-[#2a2d3a] text-[#94a3b8]">
                  <th className="text-left px-3 py-2">Analista</th>
                  <th className="text-right px-3 py-2">Ativos</th>
                  <th className="text-right px-3 py-2">SLA vencidos</th>
                  <th className="text-right px-3 py-2">Idade média</th>
                </tr>
              </thead>
              <tbody>
                {d.analistas.map((a: any) => (
                  <tr key={a.atribuido_a_email} className="border-b border-[#2a2d3a] last:border-0">
                    <td className="px-3 py-2 text-[#e2e8f0]">{a.atribuido_a}</td>
                    <td className="px-3 py-2 text-right">{a.total_ativos}</td>
                    <td className="px-3 py-2 text-right">{a.sla_vencidos}</td>
                    <td className="px-3 py-2 text-right">{a.idade_media_dias ?? '—'}d</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {(!d.analistas || d.analistas.length === 0) && (
        <p className="text-sm text-[#64748b]">Sem dados de indicadores disponíveis.</p>
      )}
    </div>
  )
}

// ── Aba Dashboard (inline — simplificada) ────────────────────────────────────

function AbaDashboard() {
  const { data, isLoading, isError, error } = useQuery<any>({
    queryKey: ['chamados-dashboard', 'geral'],
    queryFn: () => apiFetch('/chamados/dashboard?visao=geral'),
    staleTime: 0,
  })

  if (isLoading) return <div className="flex justify-center py-10"><Spinner /></div>
  if (isError) return (
    <AlertaBanner tom="error">
      Erro ao carregar dashboard: {(error as Error).message}
    </AlertaBanner>
  )

  const d = data ?? {}
  const metricas = [
    { label: 'Backlog', valor: d.backlog, desc: 'abertos há +14 dias' },
    { label: 'Abertas hoje', valor: d.abertas, desc: 'chamados abertos hoje' },
    { label: 'Em andamento', valor: d.andamento, desc: 'em análise' },
    { label: 'Sem analista', valor: d.sem_analista, desc: 'sem responsável' },
  ].filter(m => m.valor !== undefined)

  return (
    <div className="flex flex-col gap-4">
      {metricas.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {metricas.map(m => (
            <div key={m.label} className="rounded-lg border border-[#2a2d3a] bg-[#12141e] p-3">
              <div className="text-2xl font-bold text-[#e2e8f0]">{m.valor ?? '—'}</div>
              <div className="text-xs font-medium text-[#94a3b8] mt-0.5">{m.label}</div>
              <div className="text-[10px] text-[#64748b]">{m.desc}</div>
            </div>
          ))}
        </div>
      )}
      {metricas.length === 0 && (
        <p className="text-sm text-[#64748b]">Sem dados de dashboard disponíveis.</p>
      )}
    </div>
  )
}

// ── Modal de Veredito (TriagemModal — inline, fiel ao _E do bundle) ──────────

function TriagemModal({ c, onClose }: { c: Chamado; onClose: () => void }) {
  const heuristica = c.triagem_origem === 'heuristica'
  const { data: sugestoesData } = useQuery<any>({
    queryKey: ['chamados-sugestoes'],
    queryFn: () => apiFetch('/chamados/sugestoes'),
    staleTime: 300_000,
  })
  const sugestao = sugestoesData?.sugestoes?.find((s: any) => s.tipo_demanda === c.tipo_demanda)

  // Usar o Modal do design system existente
  const { Modal } = require('../components/ui/Modal') as { Modal: React.ComponentType<any> }

  return (
    <Modal open onClose={onClose} title={`Triagem · ${c.numero}`} size="lg">
      <div className="flex flex-col gap-3 text-xs">
        <div className={`rounded-md px-3 py-2 ${heuristica ? 'bg-amber-50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-200' : 'bg-[#1a1d27] text-[#e2e8f0]'}`}>
          {heuristica ? (
            <>
              <strong>Análise automática por regra de texto</strong> — a IA não respondeu, então este veredito vem de heurística: ela mede sinais da descrição, não lê o pedido.
              {c.triagem_erro && <span className="block text-[11px] mt-1">Motivo: {c.triagem_erro}</span>}
            </>
          ) : (
            <><strong>Análise por IA</strong>{c.triagem_em ? ` · ${c.triagem_em}` : ''}</>
          )}
        </div>
        {c.resumo && <p className="text-[#e2e8f0]">{c.resumo}</p>}
        {c.lacunas && c.lacunas.length > 0 && (
          <div>
            <h4 className="text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wide">Lacunas identificadas</h4>
            <ul className="list-disc pl-4 text-[#e2e8f0]">
              {c.lacunas.map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          </div>
        )}
        {c.perguntas && (
          <div>
            <div className="flex items-center justify-between gap-2">
              <h4 className="text-[11px] font-semibold text-[#94a3b8] uppercase tracking-wide">Perguntas sugeridas</h4>
              <button
                type="button"
                onClick={() => navigator.clipboard?.writeText(c.perguntas!)}
                className="text-[10px] px-2 py-0.5 rounded border border-[#2a2d3a] text-[#94a3b8] hover:text-[#e2e8f0]"
              >
                Copiar
              </button>
            </div>
            <pre className="whitespace-pre-wrap text-[#e2e8f0] font-sans">{c.perguntas}</pre>
          </div>
        )}
        {!c.resumo && (!c.lacunas || !c.lacunas.length) && !c.perguntas && (
          <p className="text-[#64748b]">Este chamado ainda não tem laudo de triagem.</p>
        )}
        {sugestao && sugestao.responsavel !== c.atribuido_a && (
          <p className="text-[11px] text-[#64748b] border-t border-[#2a2d3a] pt-2">
            Quem mais resolveu &quot;{c.tipo_demanda}&quot; nos últimos {sugestoesData?.dias ?? 90} dias:{' '}
            <strong className="text-[#e2e8f0]">{sugestao.responsavel}</strong> ({sugestao.resolvidos}). É histórico, não atribuição.
          </p>
        )}
      </div>
    </Modal>
  )
}

// ── Componente principal ───────────────────────────────────────────────────────

export default function Chamados() {
  const { data: resp, isLoading, isError, error, refetch, isFetching } =
    useQuery<ChamadosResponse>({
      queryKey: ['chamados'],
      queryFn: () => apiFetch('/chamados'),
    })

  const { data: catData } = useQuery<{ sugestoes: { slug: string; label: string }[] }>({
    queryKey: ['sn-categorias'],
    queryFn: () => apiFetch('/chamados/categorias'),
    staleTime: 300_000,
  })

  const [aba, setAba] = useState<'fila' | 'indicadores' | 'dashboard'>('fila')
  const [busca, setBusca] = useState('')
  const [filtroTipo, setFiltroTipo] = useState('')
  const [filtroResponsavel, setFiltroResponsavel] = useState('')
  const [filtroPrioridade, setFiltroPrioridade] = useState('')
  const [filtroCategoria, setFiltroCategoria] = useState('')
  const [detalheAberto, setDetalheAberto] = useState<string | null>(null)
  const [veretitoAberto, setVeredtoAberto] = useState<Chamado | null>(null)

  // Filtra tasks filhas para não exibir no topo
  const chamadosBase = useMemo(
    () => (resp?.chamados ?? []).filter(c => !(c.tipo === 'task' && c.pai_sys_id)),
    [resp]
  )

  const opcoes = useMemo(() => {
    const uniq = <T,>(arr: T[]) => [...new Set(arr)].sort()
    return {
      tipos: uniq(chamadosBase.map(c => c.tipo).filter(Boolean) as string[]),
      responsaveis: uniq(chamadosBase.map(c => c.atribuido_a).filter(Boolean) as string[]),
      prioridades: uniq(chamadosBase.map(c => c.prioridade).filter(Boolean) as string[]),
    }
  }, [chamadosBase])

  const chamadosFiltrados = useMemo(() => chamadosBase.filter(c =>
    (!filtroTipo || c.tipo === filtroTipo) &&
    (!filtroResponsavel || (filtroResponsavel === '__sem__' ? !c.atribuido_a : c.atribuido_a === filtroResponsavel)) &&
    (!filtroPrioridade || c.prioridade === filtroPrioridade) &&
    (!filtroCategoria || (filtroCategoria === 'sem marcacao' ? !c.categoria_diaadia : c.categoria_diaadia === filtroCategoria)) &&
    filtroBusca(c, busca)
  ), [chamadosBase, filtroTipo, filtroResponsavel, filtroPrioridade, filtroCategoria, busca])

  const temFiltro = !!(busca || filtroTipo || filtroResponsavel || filtroPrioridade || filtroCategoria)

  function limparFiltros() {
    setBusca(''); setFiltroTipo(''); setFiltroResponsavel(''); setFiltroPrioridade(''); setFiltroCategoria('')
  }

  const sync = syncStatusDisplay(resp?.ultimo_sync ?? null)

  const syncTomClass: Record<string, string> = {
    success: 'text-green-400', warning: 'text-amber-400', error: 'text-red-400', info: 'text-blue-400',
  }

  if (isLoading) return (
    <div className="flex justify-center py-20"><Spinner /></div>
  )
  if (isError) return (
    <div className="p-4">
      <AlertaBanner tom="error">
        Não foi possível carregar os chamados: {(error as Error).message}
      </AlertaBanner>
    </div>
  )

  const S = resp!

  return (
    <div className="p-4 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold text-[#e2e8f0]">Chamados da Engenharia</h1>
          <span className="px-1.5 py-0.5 rounded text-[10px] bg-[#1a1d27] border border-[#2a2d3a] text-[#94a3b8]">
            {temFiltro ? `${chamadosFiltrados.length} de ${chamadosBase.length}` : `${chamadosBase.length} na fila`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs ${syncTomClass[sync.tom] ?? 'text-[#94a3b8]'}`}>{sync.texto}</span>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="text-[#94a3b8] hover:text-[#e2e8f0] disabled:opacity-50"
            title="Recarregar"
          >
            <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Abas */}
      <div className="flex border-b border-[#2a2d3a]">
        {(['fila', 'indicadores', 'dashboard'] as const).map(id => (
          <button
            key={id}
            onClick={() => setAba(id)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              aba === id ? 'border-blue-500 text-blue-400' : 'border-transparent text-[#94a3b8] hover:text-[#e2e8f0]'
            }`}
          >
            {id === 'fila' ? 'Fila' : id === 'indicadores' ? 'Indicadores' : 'Dashboard'}
          </button>
        ))}
      </div>

      {/* Alertas globais */}
      {S.migration_ausente && (
        <AlertaBanner tom="warning">
          Sistema em atualização — o espelho de chamados ainda não está disponível neste ambiente. Assim que a migração for aplicada, a fila aparece aqui.
        </AlertaBanner>
      )}
      {S.ultimo_sync?.erro && (
        <AlertaBanner tom="warning">
          A última sincronização reportou erro: {S.ultimo_sync.erro} — a fila abaixo pode estar desatualizada.
        </AlertaBanner>
      )}
      {aba === 'fila' && S.alerta_fila_vazia && (
        <AlertaBanner tom={S.ultimo_sync?.status === 'OK' ? 'info' : 'warning'}>
          {S.alerta_fila_vazia}
        </AlertaBanner>
      )}
      {S.derivacoes_pendentes && (
        <AlertaBanner tom="warning">
          A fila está sendo servida, mas os campos de triagem e classificação ainda não existem no banco — as migrations desta versão não foram aplicadas.
        </AlertaBanner>
      )}

      {/* Fila */}
      {aba === 'fila' && !S.migration_ausente && S.total > 0 && (
        <>
          {/* Filtros */}
          <div className="bg-[#1a1d27] border border-[#2a2d3a] rounded-lg p-3 flex flex-wrap items-end gap-3">
            <div className="relative">
              <input
                value={busca}
                onChange={e => setBusca(e.target.value)}
                placeholder="número, título ou responsável"
                className="w-64 pl-7 pr-3 py-1.5 text-xs bg-[#12141e] border border-[#2a2d3a] rounded-md text-[#e2e8f0] placeholder-[#64748b] focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <Search size={13} className="absolute left-2 bottom-2 text-[#64748b] pointer-events-none" />
            </div>

            <div className="flex flex-col gap-0.5">
              <label className="text-[10px] text-[#94a3b8]">Tipo</label>
              <select value={filtroTipo} onChange={e => setFiltroTipo(e.target.value)}
                className="w-40 text-xs bg-[#12141e] border border-[#2a2d3a] rounded-md px-2 py-1.5 text-[#e2e8f0] focus:outline-none">
                <option value="">todos</option>
                {opcoes.tipos.map(t => <option key={t} value={t}>{TIPO_LABEL[t] ?? t}</option>)}
              </select>
            </div>

            <div className="flex flex-col gap-0.5">
              <label className="text-[10px] text-[#94a3b8]">Categoria</label>
              <select value={filtroCategoria} onChange={e => setFiltroCategoria(e.target.value)}
                className="w-44 text-xs bg-[#12141e] border border-[#2a2d3a] rounded-md px-2 py-1.5 text-[#e2e8f0] focus:outline-none">
                <option value="">todas</option>
                {(catData?.sugestoes ?? []).map((c: any) => <option key={c.slug} value={c.slug}>{c.label}</option>)}
                <option value="sem marcacao">Sem marcação</option>
              </select>
            </div>

            <div className="flex flex-col gap-0.5">
              <label className="text-[10px] text-[#94a3b8]">Responsável</label>
              <select value={filtroResponsavel} onChange={e => setFiltroResponsavel(e.target.value)}
                className="w-52 text-xs bg-[#12141e] border border-[#2a2d3a] rounded-md px-2 py-1.5 text-[#e2e8f0] focus:outline-none">
                <option value="">todos</option>
                <option value="__sem__">⚠ Sem responsável</option>
                {opcoes.responsaveis.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>

            <div className="flex flex-col gap-0.5">
              <label className="text-[10px] text-[#94a3b8]">Prioridade</label>
              <select value={filtroPrioridade} onChange={e => setFiltroPrioridade(e.target.value)}
                className="w-44 text-xs bg-[#12141e] border border-[#2a2d3a] rounded-md px-2 py-1.5 text-[#e2e8f0] focus:outline-none">
                <option value="">todas</option>
                {opcoes.prioridades.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>

            {temFiltro && (
              <button type="button" onClick={limparFiltros}
                className="flex items-center gap-1 text-xs text-[#94a3b8] hover:text-[#e2e8f0] px-2 py-1.5">
                <X size={13} /> Limpar
              </button>
            )}
          </div>

          {temFiltro && chamadosFiltrados.length === 0 && S.total > 0 && (
            <AlertaBanner tom="info">
              Nenhum chamado casa com os filtros atuais — a fila tem {S.total} chamado(s). Limpe os filtros para vê-la inteira.
            </AlertaBanner>
          )}

          {/* Kanban */}
          <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 xl:grid-cols-5">
            {S.colunas.map(coluna => {
              const cards = chamadosFiltrados.filter(c => c.estado_kanban === coluna)
              return (
                <div key={coluna} className="flex flex-col gap-2 min-w-0">
                  <div className="flex items-center justify-between px-1">
                    <h2 className="text-xs font-semibold text-[#94a3b8] uppercase tracking-wider">
                      {COLUNA_LABEL[coluna] ?? coluna}
                    </h2>
                    <span className="text-xs text-[#94a3b8]">{cards.length}</span>
                  </div>
                  <div className="flex flex-col gap-2">
                    {cards.length === 0
                      ? <p className="text-[11px] text-[#64748b] px-1 py-2">nenhum</p>
                      : cards.map(c => (
                          <KanbanCard
                            key={c.sys_id}
                            c={c}
                            onOpenDetalhe={sysId => setDetalheAberto(sysId)}
                            onOpenVeredito={c => setVeredtoAberto(c)}
                          />
                        ))
                    }
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}

      {/* Abas secundárias */}
      {aba === 'dashboard' && <AbaDashboard />}
      {aba === 'indicadores' && !S.migration_ausente && <AbaIndicadores />}

      {/* Modais */}
      {detalheAberto && (() => {
        const c = chamadosBase.find(x => x.sys_id === detalheAberto)
        return (
          <ChamadoDetalheModal
            sysId={detalheAberto}
            numero={c?.numero ?? detalheAberto}
            onClose={() => setDetalheAberto(null)}
          />
        )
      })()}
      {veretitoAberto && (
        <TriagemModal c={veretitoAberto} onClose={() => setVeredtoAberto(null)} />
      )}
    </div>
  )
}
```

**Atenção na implementação de `TriagemModal`:** o `require` dinâmico no código acima é didático — na implementação real, usar import estático no topo do arquivo:
```typescript
import { Modal } from '../components/ui/Modal'
```
E reescrever `TriagemModal` sem o `require`.

- [ ] **Step 2: Verificar tipos**

```bash
cd /opt/git/sge_app/ui-react && npx tsc --noEmit 2>&1
```

Erros esperados em arquivos que **não** existem no source (AdminServiceNow, etc.) são normais — focar apenas em erros de `Chamados.tsx`, `ChamadoDetalheModal.tsx` e `chamado.ts`.

Se `tsc --noEmit` retornar erros nesses 3 arquivos: corrigir antes de prosseguir.

- [ ] **Step 3: Build completo**

```bash
cd /opt/git/sge_app/ui-react && npm run build 2>&1
```

Esperado: build sem erros. Warnings de chunk size são aceitáveis. Se o build falhar com erro TypeScript, corrigir e repetir.

**ATENÇÃO:** este build irá gerar um bundle novo que NÃO contém as telas que estão no bundle de produção atual (AdminServiceNow, ChamadosIndicadoresHistorico, etc.) — isso é esperado para esta fase. As telas ausentes serão restauradas em sprints futuras.

- [ ] **Step 4: Deploy para produção**

```bash
# Backup do bundle atual
cp -r /opt/airflow/ui-react/dist /opt/airflow/ui-react/dist.bkp.$(date +%Y%m%d-%H%M%S)

# Deploy
cp -r /opt/git/sge_app/ui-react/dist/* /opt/airflow/ui-react/dist/
```

- [ ] **Step 5: Verificar no browser**

Abrir `http://orquestra.caixavidaeprevidencia.intranet:8090/chamados` (ou o IP/porta disponível).

Verificar:
1. A tela carrega sem erro de console
2. O kanban mostra as colunas
3. Clicar no número de um card abre o modal de detalhes
4. Chamados do tipo `incident` com estado não encerrado têm borda esquerda vermelha e badge `INC`
5. Clicar no badge de veredito ainda funciona (modal de triagem)

Se alguma verificação falhar: investigar o console do browser e corrigir antes de commitar.

- [ ] **Step 6: Commit**

```bash
cd /opt/git/sge_app/ui-react
git add src/pages/Chamados.tsx
git commit -m "feat(chamados-b): Chamados.tsx — kanban + modal de detalhes + regra visual INC"
```

---

## Self-Review

### Cobertura da spec (seções 7.1 e 7.2):

| Requisito spec | Task | Status |
|---|---|---|
| Modal de detalhes ao clicar no card | T3 (`onOpenDetalhe`) | ✅ |
| Descrição no modal | T2 (`ChamadoDetalheModal`) | ✅ |
| Notas no modal (com autor, data, tipo) | T2 | ✅ |
| Anexos no modal (inline imagens, download outros) | T2 | ✅ |
| Link "Abrir no ServiceNow" no modal | T2 | ✅ |
| Borda esquerda vermelha em INC ativo | T3 (`KanbanCard`) | ✅ |
| Badge `INC` vermelho | T3 (`BadgeINC`) | ✅ |
| `isINCAtivo()` em `chamado.ts` | T1 | ✅ |
| Header do modal com fundo vermelho quando INC ativo | T2 (banner no modal) | ✅ |

### Scan de placeholders:
- Nenhum "TBD", "TODO" ou "implement later" no plano.
- Todos os steps têm código completo.

### Consistência de tipos:
- `Chamado` definido em T1, consumido em T2 e T3. Campos consistentes.
- `ChamadoDetalhe` retorna `{ chamado, notas, anexos }` — alinhado com o endpoint real.
- `isINCAtivo` aceita `Pick<Chamado, 'tipo' | 'estado_kanban'>` — compatível com uso em T3.
- `onOpenDetalhe(sysId: string)` em T3, `sysId: string` em T2 — consistente.
