import { Outlet } from 'react-router-dom'
import { HeaderV2 } from './header/HeaderV2'
import { Sidebar } from './Sidebar'
import { ToastContainer } from '../ui/Toast'

// Shell v2 (beta, atrás da flag `orquestra_shell` + gate RBAC). Header fino no
// topo (identidade + título da página + controles, sem nav — ela vive na
// sidebar) + sidebar colapsável à esquerda + conteúdo. Falta a responsividade (5).
export function AppShellV2() {
  return (
    <div className="flex flex-col h-screen bg-canvas overflow-hidden">
      <HeaderV2 />
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
