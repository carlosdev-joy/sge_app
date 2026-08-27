# Task 8 Report — Tela de Indicadores Históricos

**Status:** DONE

---

## Recharts

Recharts **disponível** — versão `^3.8.1` instalada em `package.json`. Implementação usa gráficos (não tabelas fallback).

---

## Arquivos criados/modificados

| Ação | Arquivo |
|------|---------|
| Criado | `/opt/git/sge_app/ui-react/src/pages/ChamadosIndicadoresHistorico.tsx` |
| Modificado | `/opt/git/sge_app/ui-react/src/App.tsx` (import + rota `chamados/indicadores/historico`) |
| Modificado | `/opt/git/sge_app/ui-react/src/lib/nav.ts` (link "Indicadores" com `migrated: true`, `adminOnly: true`) |

---

## Decisões de adaptação ao padrão real do projeto

- Usa `apiFetch` (fetch nativo) — não `api.get` do plano (que assumia axios).
- Dark theme consistente com o resto do app: cores `#1a1d27`, `#2a2d3a`, `#e2e8f0`, `#94a3b8`.
- Tooltip do recharts com `contentStyle` dark para harmonizar.
- Nav item com `adminOnly: true` (mesma flag do item Admin).
- Rota montada como sub-rota do `AppShell` (dentro do `PrivateRoute`), seguindo o padrão de `admin/servicenow`.

---

## Gráficos implementados (4)

1. **LineChart** — Total de ativos ao longo do tempo + SLA vencidos (linha vermelha tracejada)
2. **BarChart empilhado** — Distribuição por coluna kanban (novo / andamento / aguardando / resolvido / outros)
3. **LineChart** — Tempo médio de resolução (horas) com `ReferenceLine` de meta quando `etl_indicador_meta` tiver dados
4. **BarChart** — Encerrados × Abertos (acumulado 7 dias por snapshot)

## Tabelas implementadas

- Por Analista (snapshot atual): ativos, SLA vencidos em vermelho se > 0, idade média
- Por Grupo (snapshot atual): mesma estrutura

---

## Resultado `tsc --noEmit`

```
(sem output — zero erros)
```

---

## Concerns

Nenhum bloqueio. Pontos de atenção para quando o banco estiver populado:

- A API `GET /chamados/indicadores/historico` precisa das migrations 097 (`etl_indicador_snapshot`, `etl_indicador_snapshot_analista`, `etl_indicador_snapshot_grupo`, `etl_indicador_meta`) aplicadas no banco para retornar dados reais.
- A navegação só exibe o item "Indicadores" para usuários `adminOnly`. Se quiser abrir para todos os usuários, basta remover `adminOnly: true` em `nav.ts`.
