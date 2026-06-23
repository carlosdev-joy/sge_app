import { useShellVariant } from '../../lib/shell'
import { ClassicAppShell } from './ClassicAppShell'
import { AppShellV2 } from './AppShellV2'

// Bifurcação clássico vs v2 (beta). A escolha vem da flag `orquestra_shell`
// gateada por RBAC em `useShellVariant`; App.tsx segue montando só <AppShell/>,
// então a troca é transparente para as rotas.
export function AppShell() {
  return useShellVariant() === 'v2' ? <AppShellV2 /> : <ClassicAppShell />
}
