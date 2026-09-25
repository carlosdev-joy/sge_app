// Casca do Admin (docs/spec-admin-reestruturacao.md §3.1): sub-menu lateral
// com busca, cabeçalho da aba (migalha, frase e "Copiar link") e o painel de
// conteúdo com Suspense + ErrorBoundary por aba. O conteúdo de cada aba é o de
// sempre — a casca não mexe dentro dele.
//
// ⚠️ sticky: o sub-menu gruda no <main overflow-y-auto> do AppShellV2. Nenhum
// ancestral entre ele e o <main> pode ter overflow-hidden/auto, senão o sticky
// morre em silêncio.
import { Fragment, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDown, Link2 } from 'lucide-react'
import { Sheet } from '../ui/Sheet'
import { Skeleton } from '../ui/Skeleton'
import { toast } from '../ui/Toast'
import { haOverlayAberto } from '../ui/overlay'
import { useMediaQuery } from '../../lib/useMediaQuery'
import { copiarTexto } from '../../lib/copiar'
import { caminhoDaAba, grupoDaAba, type AbaAdmin } from '../../lib/adminNav'
import { MenuAdmin } from './casca/MenuAdmin'
import { AbaErrorBoundary } from './casca/AbaErrorBoundary'

const FOCO = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--control-focus))]'

function campoEditavel(alvo: EventTarget | null): boolean {
  if (!(alvo instanceof HTMLElement)) return false
  return alvo.isContentEditable || !!alvo.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"], [role="textbox"]')
}

function EsqueletoAba() {
  return (
    <div aria-hidden className="flex flex-col gap-3">
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-28 w-full" />
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-40 w-full" />
    </div>
  )
}

function CabecalhoAba({ aba, tituloRef }: { aba: AbaAdmin; tituloRef: React.Ref<HTMLHeadingElement> }) {
  const copiarLink = async () => {
    const r = await copiarTexto(window.location.origin + caminhoDaAba(aba))
    if (r === 'copiado') toast.success('Link da aba copiado.')
    else toast.error('Não foi possível copiar. Copie o endereço na barra do navegador.')
  }
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-edge pb-3">
      <div className="min-w-0">
        <h2 ref={tituloRef} tabIndex={-1} className="relative text-base font-semibold text-ink focus:outline-none">
          {/* < 1024 px o seletor logo acima já mostra "Grupo › Aba": o grupo
              fica só para o leitor de tela, sem repetir a migalha na tela. */}
          <span className="font-normal text-dim max-lg:sr-only">{grupoDaAba(aba).rotulo}</span>
          <span aria-hidden className="mx-1.5 text-dim max-lg:hidden">›</span>
          <span className="sr-only">: </span>
          {aba.rotulo}
        </h2>
        <p className="mt-0.5 text-[13px] text-dim">{aba.descricao}</p>
      </div>
      <button
        type="button"
        onClick={copiarLink}
        className={`inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs lg:h-7 font-medium text-dim transition-colors hover:bg-edge/40 hover:text-ink ${FOCO}`}
      >
        <Link2 size={13} aria-hidden /> Copiar link
      </button>
    </header>
  )
}

function AbaNaoEncontrada({ aoBuscar }: { aoBuscar: () => void }) {
  return (
    <div className="rounded-lg border border-edge bg-panel px-5 py-8 text-center">
      <h2 className="text-base font-semibold text-ink">Aba não encontrada</h2>
      <p className="mt-1 text-sm text-dim">Não encontramos esta aba do admin. Ela pode ter mudado de lugar.</p>
      <button
        type="button"
        onClick={aoBuscar}
        className={`mt-3 text-sm font-medium text-[#1A5FA8] underline underline-offset-2 hover:no-underline dark:text-[rgb(var(--action))] ${FOCO}`}
      >
        Procurar na busca do admin
      </button>
    </div>
  )
}

export function AdminShell({ aba }: { aba: AbaAdmin | null }) {
  const desktop = useMediaQuery('(min-width: 1024px)')
  const buscaRef = useRef<HTMLInputElement>(null)
  const tituloRef = useRef<HTMLHeadingElement>(null)
  const [sheetAberto, setSheetAberto] = useState(false)
  const [sheetComBusca, setSheetComBusca] = useState(false)

  const focarBusca = useCallback(() => {
    if (desktop) buscaRef.current?.focus()
    else { setSheetComBusca(true); setSheetAberto(true) }
  }, [desktop])

  // "/" foca a busca quando o foco não está num campo e nenhum overlay está na frente.
  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return
      if (campoEditavel(e.target) || haOverlayAberto()) return
      e.preventDefault()
      focarBusca()
    }
    document.addEventListener('keydown', aoTeclar)
    return () => document.removeEventListener('keydown', aoTeclar)
  }, [focarBusca])

  // Troca de aba → foco no título (não no primeiro render da página). Depende
  // da ABA, não do pathname: um redirect (/admin → última aba, /admin/config →
  // parametros) já monta a casca com a aba de destino, e a troca de URL que vem
  // depois não é troca de aba — não pode roubar o foco de quem acabou de chegar.
  const abaChave = aba ? caminhoDaAba(aba) : null
  const abaAnterior = useRef<string | null | undefined>(undefined)
  useEffect(() => {
    const anterior = abaAnterior.current
    abaAnterior.current = abaChave
    if (anterior === undefined || anterior === abaChave || abaChave === null) return
    const id = requestAnimationFrame(() => tituloRef.current?.focus({ preventScroll: false }))
    return () => cancelAnimationFrame(id)
  }, [abaChave])

  const fecharSheet = () => { setSheetAberto(false); setSheetComBusca(false) }

  const conteudo = aba ? (
    <section className="min-w-0">
      <CabecalhoAba aba={aba} tituloRef={tituloRef} />
      <div className="pt-4">
        <AbaErrorBoundary key={caminhoDaAba(aba)}>
          <Suspense fallback={<EsqueletoAba />}>
            <aba.componente />
          </Suspense>
        </AbaErrorBoundary>
      </div>
    </section>
  ) : (
    <AbaNaoEncontrada aoBuscar={focarBusca} />
  )

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-bold text-ink">Administração</h1>
        <p className="mt-0.5 text-xs text-dim">Gestão do sistema Orquestra</p>
      </div>

      {/* Um pai só nos dois tamanhos e `conteudo` sempre com a MESMA key: cruzar
          1024px (zoom, DevTools, tablet girado) não pode remontar a aba — antes,
          div × Fragment desmontava a aba e apagava o que o usuário digitava. */}
      <div className={desktop ? 'grid grid-cols-[240px_minmax(0,1fr)] items-start gap-6' : 'flex flex-col gap-4'}>
      {desktop ? (
          /* top-4 dentro do <main>; a altura desconta o header (52px) e as duas folgas. */
          <aside key="menu" className="sticky top-4 flex max-h-[calc(100vh-52px-2rem)] flex-col self-start">
            <MenuAdmin abaAtiva={aba} inputRef={buscaRef} />
          </aside>
      ) : (
        <Fragment key="menu-movel">
          <button
            type="button"
            onClick={() => setSheetAberto(true)}
            aria-haspopup="dialog"
            aria-expanded={sheetAberto}
            className={`relative flex h-11 w-full items-center justify-between gap-2 rounded-md border border-edge bg-panel px-3 text-left text-sm text-ink shadow-sm ${FOCO}`}
          >
            <span className="min-w-0 truncate">
              {aba
                ? <><span className="text-dim">{grupoDaAba(aba).rotulo}</span><span aria-hidden className="mx-1.5 text-dim">›</span><span className="sr-only">: </span><span className="font-medium">{aba.rotulo}</span></>
                : <span className="text-dim">Escolha uma seção do admin</span>}
            </span>
            <ChevronDown size={16} aria-hidden className="shrink-0 text-dim" />
          </button>
          <Sheet open={sheetAberto} onClose={fecharSheet} side="left" widthClass="max-w-[20rem]" title="Seções do admin">
            <div className="flex h-full flex-col">
              <MenuAdmin abaAtiva={aba} autoFocus={sheetComBusca} aoEscolher={fecharSheet} />
            </div>
          </Sheet>
        </Fragment>
      )}
        <div key="conteudo" className="min-w-0">{conteudo}</div>
      </div>
    </div>
  )
}
