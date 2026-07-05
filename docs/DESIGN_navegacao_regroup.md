# Design — Reestruturação da navegação (proposta v1, para validação)

Status: **proposta** — nada implementado ainda além da migration `044` (perms).
Fonte da verdade do estado atual: tela *Admin › Perfis e Permissões* (estado vivo) +
`ui-react/src/lib/nav.ts`.

## 1. Estado real (o que cada persona vê hoje)

Derivado do estado vivo de produção (não da seed, que estava desatualizada):

| Item (menu)        | consulta | operador | desenvolvedor | admin |
|--------------------|:--:|:--:|:--:|:--:|
| Dashboard          | ✅ | ✅ | ✅ | ✅ |
| Pipelines          | ✅ | ✅ | ✅ | ✅ |
| Jobs               | ✅ | ✅ | ✅ | ✅ |
| Logs               | —  | ✅ | ✅ | ✅ |
| Governança         | ✅ | ✅ | ✅ | ✅ |
| Malha              | ✅ | ✅ | ✅ | ✅ |
| Impacto Campo      | —  | —  | ✅ | ✅ |
| Planos Ajuste      | —  | —  | ✅ | ✅ |
| Malha DS           | —  | —  | ✅ | ✅ |
| Console DS         | —  | —  | ✅ | ✅ |
| Power BI           | —  | —  | —  | ✅ |
| Admin              | —  | —  | —  | ✅ |

Itens visíveis por persona: **consulta 5 · operador 6 · desenvolvedor 10 · admin 12.**

Observações que viram decisão (não são bug, mas vale confirmar a intenção):
- **consulta não vê Logs** (a seed 019 concede, mas foi removido à mão em prod). Intencional?
- **Power BI é admin-only.** Se BI é consumo de negócio, talvez devesse ir para consulta/operador.
- `tela_ds_monitor` foi **excluída** (tela removida); recurso vestigial limpo na migration 044.

## 2. Problemas de IA que independem de RBAC

1. **Colisões de rótulo**
   - "Governança" é **grupo e item** ao mesmo tempo.
   - "Malha" (pipelines do ORQUESTRA) vs "Malha DS" (export do servidor DataStage) — objetos diferentes, nome quase igual.
   - "Console DS" (item) dentro do grupo "Console DataStage" (redundante).
2. **Rótulo enganoso**: "Jobs" parece job do Airflow, mas é o **editor de etapas** do pipeline.
3. **Grupos de 1 item**: "BI" (só Power BI) e "Administração" (só Admin) são cabeçalho para um link só.

## 3. ⚠️ Pegadinha de escopo dos renomes

Os `label` em `nav.ts` são **compartilhados pelo shell clássico E pelo v2** (ambos via
`useVisibleNav`). Logo, **renomear um item muda o texto para TODOS no próximo deploy**,
não só para o grupo beta do v2. Decisão necessária antes de codar:

- **(a) Global** — renomeia para todo mundo (mais simples, mas mexe no que a equipe já decorou no clássico).
- **(b) Só v2** — dar ao shell v2 uma fonte de `label` própria (ex.: campo `labelV2?`), mantendo o clássico intacto até o flip de default.

Recomendação: **(b)** enquanto o v2 é beta — renomes entram só no v2, validam com os admins, e viram global no flip.

## 4. Proposta de agrupamento (orientada a JTBD)

Dois níveis, para você escolher a profundidade.

### Nível 1 — só rótulos/colisões (barato, reversível)
| Antes (grupo · item)            | Depois                                  | Porquê |
|---------------------------------|-----------------------------------------|--------|
| Operação · Jobs                 | Operação · **Etapas**                   | desfaz colisão com "job do Airflow" |
| Governança · Governança         | Governança · **Catálogo & Lineage**     | mata grupo=item; descreve a tela |
| Governança · Malha              | Governança · **Malha de Pipelines**     | desambígua de Malha DS |
| Governança · Impacto Campo / Planos Ajuste | Governança · **Impacto de Campo** → **Planos de Ajuste** | preposição + ordem de fluxo |
| Console DataStage · Console DS  | **DataStage** · **Console (dsjob)**     | grupo curto; item específico |
| Console DataStage · Malha DS    | **DataStage** · **Estrutura (Malha DS)**| diferencia de "Malha de Pipelines" |
| BI · Power BI / Administração · Admin | itens **sem cabeçalho de grupo** (rodapé) | elimina seção de 1 item |

### Nível 2 — regroup por tarefa (aposta, só no v2 atrás da flag)
- **Operação** (diário, todas as personas): Dashboard, Logs.
- **Construção** (dev): Pipelines, Etapas. *(o editor de fluxo futuro entra como toggle grafo↔lista AQUI, não como item novo.)*
  - **REVISADO (2026-07-05)**: o editor amadureceu de mockup a caminho primário de
    construção (PRs #113–#139) e ganhou também o item **Fluxos** (`/fluxos`) no
    grupo Construção — tela dedicada com biblioteca + canvas em tela cheia e
    deep-link `?pipeline=`. O toggle da tela Etapas NÃO morre (dual-view mantido);
    a rota nova renderiza o MESMO componente `FluxoEditor`, sem fork, e reusa a
    permissão `tela_jobs` (sem migration de RBAC).
- **Governança & Dados**: Catálogo & Lineage, Malha de Pipelines, Impacto de Campo, Planos de Ajuste.
- **DataStage**: Estrutura (Malha DS), Console (dsjob).
- **Rodapé** (sem cabeçalho): Power BI, Admin.

Gaps de produto a considerar no Nível 2 (validar antes):
- Home de **"operação do dia / falhas a tratar"** (o `ack` já existe em Logs; falta a fila).
- **Avisos** como item de menu (hoje notificações/comunicados só no sino, sem histórico navegável).

## 5. Sequência — estado atual
1. ✅ **Migration 044** — perms órfãs + limpeza do `tela_ds_monitor` (PR #101, na `main`).
2. ✅ **Nível 1** (PR #101) — renomes via `labelV2` (só v2), fim das colisões, grupos de 1 item sem cabeçalho.
3. ✅ **Nível 2** (branch `claude/wizardly-knuth-we80cd`, atrás da flag v2):
   - **2A** regroup por tarefa: grupo `Operação` (Dashboard, Logs) vs `Construção` (Pipelines, Etapas); `Governança` → `Governança & Dados`.
   - **2B** itens de menu novos (flag `v2Only`): **Gestão de Falhas** (a aba homônima do Logs promovida a menu próprio — mesmo componente reusado; no v2 a aba some do Logs, no clássico continua) e **Avisos** (notificações + comunicados em página cheia, reusa endpoints do sininho).
4. ⏳ Validar com admins beta → flip de default.

## 6. Decisões — resolvidas
- **Escopo dos renomes**: só v2, via campo `labelV2` (e `v2Only` para telas novas). Clássico inalterado. ✅
- **RBAC**: mantido como em produção — `consulta` sem Logs, Power BI admin-only. Operação do dia herda `tela_logs`. ✅
- **Profundidade**: foi até o Nível 2 completo. ✅

> Em aberto para o beta: **Gestão de Falhas** deve virar o **destino default** do operador
> no v2 (hoje o index ainda vai pra `/dashboard`)? Decidir após feedback.
