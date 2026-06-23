import { useState, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { HeaderV2 } from './header/HeaderV2'
import { Sidebar } from './Sidebar'
import { ToastContainer } from '../ui/Toast'

// Shell v2 (beta, atrás da flag `orquestra_shell` + gate RBAC). Header fino +
// sidebar colapsável (desktop) / drawer off-canvas (mobile) + conteúdo. O estado
// do drawer mobile vive aqui: abre pelo hambúrguer do header, fecha no backdrop/X
// e ao navegar (efeito no pathname).
export function AppShellV2() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const { pathname } = useLocation()
  useEffect(() => { setMobileOpen(false) }, [pathname])

  return (
    <div className="flex flex-col h-screen bg-canvas overflow-hidden">
      <HeaderV2 onMenuClick={() => setMobileOpen(true)} />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
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
