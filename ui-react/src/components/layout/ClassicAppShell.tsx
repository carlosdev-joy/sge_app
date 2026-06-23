import { Outlet } from 'react-router-dom'
import { Header } from './Header'
import { ToastContainer } from '../ui/Toast'

// Shell clássico (atual) — base estável. O shell v2 nasce como cópia fiel deste.
export function ClassicAppShell() {
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
