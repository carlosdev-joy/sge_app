import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '../../store/auth'
import { workspaceApi } from '../../lib/workspaceApi'
// Cache segregado por sessão. Sem persistência de configuração no navegador.
export function useWorkspaceCapabilities() {
 const token = useAuthStore(s => s.token)
 return useQuery({ queryKey: ['workspace-capabilities', token], queryFn: ({ signal }) => workspaceApi.capabilities(signal), enabled: !!token, retry: false, staleTime: 15_000, refetchInterval: 30_000 })
}
