// Sub-menu do Admin: busca (combobox) + lista de seções por grupo
// (docs/spec-admin-reestruturacao.md §3.1). O mesmo componente vive na coluna
// lateral (desktop) e dentro do Sheet (< 1024 px).
// - Sem busca: grupos sempre abertos, itens de 32 px, sem ícone por item; o
//   ativo tem barra de 3 px + fundo panel e aria-current="page".
// - Com busca: a lista vira resultados (listbox) com o trecho que casou em
//   destaque; ↑/↓ movem, Enter abre, Esc limpa e volta ao menu. O foco fica no
//   campo (padrão combobox com aria-activedescendant).
import React, { useEffect, useId, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Search, X } from 'lucide-react'
import {
  ABAS_ADMIN, GRUPOS_ADMIN, buscarAbas, caminhoDaAba, grupoDaAba,
  type AbaAdmin, type CampoBusca, type ResultadoBusca, type Trecho,
} from '../../../lib/adminNav'

interface Props {
  abaAtiva: AbaAdmin | null
  inputRef?: React.Ref<HTMLInputElement>
  autoFocus?: boolean
  /** chamado depois de navegar (o Sheet fecha aqui) */
  aoEscolher?: () => void
  /** Esc com a busca vazia (o Sheet fecha aqui) */
  aoEscVazio?: () => void
}

const FOCO = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--control-focus))]'

const ROTULO_CAMPO: Partial<Record<CampoBusca, string>> = {
  palavraChave: 'termo',
  chaveConfig: 'chave',
}

// Descrição longa: só um pedaço em volta do que casou.
function recortar(t: Trecho): Trecho {
  const antes = t.antes.length > 28 ? '…' + t.antes.slice(-26).replace(/^\S*\s/, '') : t.antes
  const depois = t.depois.length > 36 ? t.depois.slice(0, 34).replace(/\s\S*$/, '') + '…' : t.depois
  return { antes, casou: t.casou, depois }
}

function Destaque({ t }: { t: Trecho }) {
  return (
    <>
      {t.antes}
      <mark className="rounded-sm bg-amber-200 px-px text-ink dark:bg-amber-400/30">{t.casou}</mark>
      {t.depois}
    </>
  )
}

function LinhaResultado({ r }: { r: ResultadoBusca }) {
  const grupo = grupoDaAba(r.aba).rotulo
  const secundario = r.campo === 'rotulo' || r.campo === 'grupo' ? null
    : r.campo === 'descricao' ? <Destaque t={recortar(r.trecho)} />
    : <>{ROTULO_CAMPO[r.campo]}: <span className="font-mono"><Destaque t={r.trecho} /></span></>
  return (
    <>
      <span className="block truncate text-[13px] font-medium text-ink">
        {r.campo === 'rotulo' ? <Destaque t={r.trecho} /> : r.aba.rotulo}
      </span>
      <span className="block truncate text-[11px] text-dim">
        {r.campo === 'grupo' ? <Destaque t={r.trecho} /> : grupo}
        {secundario && <> · {secundario}</>}
      </span>
    </>
  )
}

export function MenuAdmin({ abaAtiva, inputRef, autoFocus, aoEscolher, aoEscVazio }: Props) {
  const navigate = useNavigate()
  const [consulta, setConsulta] = useState('')
  const [ativo, setAtivo] = useState(0)
  const base = useId()
  const idLista = `${base}-resultados`
  const idOpcao = (i: number) => `${base}-opcao-${i}`

  const buscando = consulta.trim().length > 0
  const resultados = useMemo(() => (buscando ? buscarAbas(consulta) : []), [buscando, consulta])
  const idxAtivo = Math.min(ativo, Math.max(resultados.length - 1, 0))

  const abrir = (aba: AbaAdmin) => {
    setConsulta('')
    setAtivo(0)
    navigate(caminhoDaAba(aba))
    aoEscolher?.()
  }

  const aoTeclar = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      if (consulta) {
        // Não deixa o Esc chegar ao Sheet: aqui ele só limpa a busca.
        e.preventDefault(); e.stopPropagation()
        setConsulta(''); setAtivo(0)
      } else {
        aoEscVazio?.()
      }
      return
    }
    if (!buscando || resultados.length === 0) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setAtivo((idxAtivo + 1) % resultados.length) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setAtivo((idxAtivo - 1 + resultados.length) % resultados.length) }
    else if (e.key === 'Home') { e.preventDefault(); setAtivo(0) }
    else if (e.key === 'End') { e.preventDefault(); setAtivo(resultados.length - 1) }
    else if (e.key === 'Enter') { e.preventDefault(); abrir(resultados[idxAtivo].aba) }
  }

  // Item ativo fora da área visível do sub-menu (ex.: Sistema › Backlog numa
  // tela baixa): rola SÓ a lista, nunca a página (scrollIntoView rolaria o <main>).
  const listaRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const lista = listaRef.current
    const item = lista?.querySelector<HTMLElement>('[aria-current="page"]')
    if (!lista || !item) return
    const topo = item.offsetTop
    if (topo < lista.scrollTop || topo + item.offsetHeight > lista.scrollTop + lista.clientHeight) {
      lista.scrollTop = Math.max(0, topo - lista.clientHeight / 2)
    }
  }, [abaAtiva, buscando])

  const expandido = buscando && resultados.length > 0
  const anuncio = !buscando ? ''
    : resultados.length === 0 ? 'Nenhuma seção encontrada'
    : resultados.length === 1 ? '1 seção encontrada'
    : `${resultados.length} seções encontradas`

  return (
    // relative: bloco de contenção do aria-live sr-only (tests/test_casca_rolagem_por_foco.py).
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className="relative shrink-0">
        <Search size={14} aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-dim" />
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-label="Buscar no admin"
          aria-autocomplete="list"
          aria-expanded={expandido}
          aria-controls={idLista}
          aria-activedescendant={expandido ? idOpcao(idxAtivo) : undefined}
          autoComplete="off"
          spellCheck={false}
          // Só quando o próprio usuário pede (atalho "/"): no toque do seletor
          // mobile, abrir o teclado virtual sem pedido cobre a lista.
          autoFocus={autoFocus}
          value={consulta}
          onChange={(e) => { setConsulta(e.target.value); setAtivo(0) }}
          onKeyDown={aoTeclar}
          placeholder="Buscar no admin…"
          className="h-10 w-full rounded-md border border-edge bg-panel pl-8 pr-8 text-base lg:h-8 lg:text-sm text-ink placeholder:text-dim
            focus:outline-none focus:ring-1 focus:ring-[rgb(var(--control-focus))] focus:border-[rgb(var(--control-focus))]"
        />
        {consulta ? (
          <button
            type="button"
            onClick={() => { setConsulta(''); setAtivo(0) }}
            aria-label="Limpar busca"
            className={`absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-dim hover:text-ink ${FOCO}`}
          >
            <X size={14} aria-hidden />
          </button>
        ) : (
          <kbd aria-hidden className="max-lg:hidden pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border border-edge bg-canvas px-1.5 font-mono text-[10px] leading-4 text-dim">
            /
          </kbd>
        )}
      </div>
      <p aria-live="polite" className="sr-only">{anuncio}</p>

      <div ref={listaRef} className="relative -mx-1 mt-3 min-h-0 flex-1 overflow-y-auto overscroll-contain px-1 pb-2">
        {buscando ? (
          resultados.length > 0 ? (
            <ul id={idLista} role="listbox" aria-label="Seções encontradas" className="space-y-0.5">
              {resultados.map((r, i) => (
                <li
                  key={caminhoDaAba(r.aba)}
                  id={idOpcao(i)}
                  role="option"
                  aria-selected={i === idxAtivo}
                  // mousedown não rouba o foco do campo (padrão combobox).
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseMove={() => { if (i !== idxAtivo) setAtivo(i) }}
                  onClick={() => abrir(r.aba)}
                  className={`cursor-pointer rounded-md px-3 py-1.5 transition-colors ${
                    i === idxAtivo ? 'bg-[rgb(var(--action)/0.12)]' : 'hover:bg-edge/40'
                  }`}
                >
                  <LinhaResultado r={r} />
                </li>
              ))}
            </ul>
          ) : (
            <div id={idLista} className="px-1 py-2 text-[13px] leading-relaxed text-dim">
              Nada encontrado para “<span className="break-all text-ink">{consulta.trim()}</span>”. Tente o nome de um
              parâmetro, como <code className="rounded bg-edge/50 px-1 font-mono text-[12px] text-ink">email_remetente</code>,
              ou de um assunto, como e-mail ou agentes.
            </div>
          )
        ) : (
          <nav aria-label="Seções do admin">
            {GRUPOS_ADMIN.map((g, gi) => (
              <div key={g.id} className={gi > 0 ? 'mt-4' : ''}>
                <h2 className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-dim">{g.rotulo}</h2>
                <ul className="space-y-0.5">
                  {ABAS_ADMIN.filter((a) => a.grupo === g.id).map((a) => {
                    const atual = abaAtiva === a
                    return (
                      <li key={a.id}>
                        <Link
                          to={caminhoDaAba(a)}
                          aria-current={atual ? 'page' : undefined}
                          onClick={() => aoEscolher?.()}
                          className={`relative flex h-10 items-center rounded-md px-3 text-sm lg:h-8 lg:text-[13px] transition-colors ${FOCO} ${
                            atual
                              ? 'bg-panel font-medium text-ink shadow-sm ring-1 ring-edge before:absolute before:inset-y-1.5 before:left-0 before:w-[3px] before:rounded-full before:bg-[#1A5FA8] dark:before:bg-[rgb(var(--action))]'
                              : 'text-dim hover:bg-edge/40 hover:text-ink'
                          }`}
                        >
                          <span className="truncate">{a.rotulo}</span>
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </nav>
        )}
      </div>
    </div>
  )
}
