import { Outlet } from 'react-router-dom'
import { Header } from './Header'
import { Sidebar } from './Sidebar'
import { ToastContainer } from '../ui/Toast'

// Shell v2 (beta, atrás da flag `orquestra_shell` + gate RBAC). Header fino no
// topo (sem nav — ela migrou para a sidebar) + sidebar colapsável à esquerda +
// conteúdo. Os próximos incrementos refinam o header (4) e a responsividade (5).
export function AppShellV2() {
  return (
    <div className="flex flex-col h-screen bg-canvas overflow-hidden">
      <Header hideNav />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto">
          <div className="p-6 max-w-[1600px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
      <ToastContainer />
    </div>
  )
}
