# Task 6 Report — Tela Admin ServiceNow

**Status:** DONE

## Resultado do `tsc --noEmit`

```
Exit code: 0 (sem erros)
```

## Arquivos criados/modificados

### Criado
- `/opt/git/sge_app/ui-react/src/pages/AdminServiceNow.tsx`
  - Componente com 4 abas: Conexão, Grupos, Sincronização, Acesso
  - Usa `apiFetch` (não axios), padrão do projeto
  - Usa componentes UI existentes: `Button`, `Tabs`, `toast`
  - Dark theme consistente com o restante da aplicação (`#0f1117`, `#1a1d27`, `#2a2d3a`, `#e2e8f0`, `#94a3b8`)
  - Consome todos os endpoints: `/admin/servicenow/{config,grupos,ciclos,perfis-acesso,testar,disparar-delta}`

### Modificado
- `/opt/git/sge_app/ui-react/src/pages/Admin.tsx`
  - Adicionado import `useNavigate` do react-router-dom
  - Adicionado tab "ServiceNow" ao `ADMIN_TABS`
  - `handleTabChange` redireciona para `/admin/servicenow` ao clicar no tab ServiceNow

- `/opt/git/sge_app/ui-react/src/App.tsx`
  - Adicionado import de `AdminServiceNow`
  - Rota `admin/*` separada em `admin` + `admin/servicenow` explícita

## Adaptações ao projeto real

O plano usava `import { api } from "../lib/api"` (cliente axios-like), mas o projeto usa `apiFetch` (fetch nativo com wrapper). O componente foi criado usando o padrão real do projeto:
- `apiFetch<T>(path, opts)` para chamadas HTTP
- `useState` + `useEffect` direto (sem `useQuery`/`useMutation`, para manter o componente simples e sem dependência de cache keys específicas)
- Tratamento de erro via `try/catch` com `toast.error()`

## Concerns

- `noUnusedLocals` e `noUnusedParameters` estão habilitados no tsconfig — todos os imports e variáveis foram verificados (sem warnings).
- O tab "ServiceNow" em Admin.tsx navega para uma rota separada (não renderiza inline), alinhado com o que o plano especifica.
- node_modules não existiam no projeto (`/opt/git/sge_app/ui-react/`) — foram instalados via `npm install` para rodar o tsc. A verificação passou sem erros.
