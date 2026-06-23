import { Outlet } from 'react-router-dom'
import { Header } from './Header'
import { ToastContainer } from '../ui/Toast'

// Shell v2 (beta, atrás da flag `orquestra_shell` + gate RBAC). Começa como
// cópia fiel do clássico — zero regressão. Os incrementos 2–5 fazem este
// arquivo divergir: registry + useVisibleNav, sidebar colapsável, header fino
// e responsividade. Mantido separado do clássico para reversão a um clique.
export function AppShellV2() {
  return (
    <div className="flex flex-col h-screen bg-canvas overflow-hidden">
      <Header />
      <main className="flex-1 overflow-y-auto">
        <div className="p-6 max-w-[1600px] mx-auto">
          <Outlet />
        </div>
      </main>
      <ToastContainer />
    </div>
  )
}
