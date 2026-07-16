# Spec: Migração do Caixa Seguro para o DS nativo do Orquestra — Orquestra (sge_app)
Data: 2026-07-15 · Status: em execução (F1) — aprovada pelo usuário em 2026-07-15

## 1. Visão
A seção `/caixa-seguro` roda hoje num design system paralelo (shadcn/Radix + tema navy/glass escopado em `.caixa-theme`, só claro), disjunto do resto do Orquestra. O piloto Orquestra-native do Monitoramento (PRs #194–#197) validou a alternativa e o usuário decidiu pela **opção C: migrar as 5 telas para o DS nativo neutro** (tokens `canvas/panel/edge/ink`, claro+escuro). Ao final, a seção inteira usa os mesmos componentes do restante do produto, ganha dark mode, e o tema shadcn/Radix é removido do bundle (~11.700 linhas de UI acoplada + ~10 pacotes `@radix-ui/*`).

## 2. Escopo
**IN:**
- Reescrita visual das 5 telas da POC no DS nativo: Index (home/busca), SalesManagement→já coberto pelo piloto `MonitoramentoOrq`, ProposalTracking, PortabilityTracking, AICommercialPanel.
- Reescrita dos ~15 diálogos operacionais, `InlineWorkflow`, `ProposalWorkflowSheet`, `ProposalCard`, `SearchProposals`, `DateFilters`, `Tutorial` (balão do mascote) e `MenuButton` em componentes nativos.
- Novos primitivos no DS nativo (`ui-react/src/components/ui/`): Table, Skeleton, Checkbox, Switch, RadioGroup, Sheet (drawer), DropdownMenu — caseiros, sem Radix, tokens claro+escuro.
- Troca dos 3 assistentes visuais (Diego/Léo/Lari) pelo `ChatAssistantOrq` (mesmo backend, mesmo gate `useAssistentesIA`).
- Remoção final: `CaixaSeguroApp`/`.caixa-theme`/`theme.css`, `caixa/components/ui/*` (shadcn), `use-toast`, deps `@radix-ui/*` sem outro consumidor.
- Gráficos continuam em **recharts**, no padrão do piloto (séries `#1A5FA8`/`#F26B00`, tooltip via CSS vars `--panel/--edge/--ink`), validados nos 2 temas.

**OUT (explícito):**
- **Backend**: `api/routers/caixa_chat.py` e `api/services/caixa_ia.py` intocados. Zero migration.
- **Dados reais**: as telas seguem 100% mock como hoje; ligação a dados reais é feature própria futura.
- **Identidade navy/glass CAIXA**: descartada por decisão do usuário (2026-07-15). Azul `#0055B1`/laranja `#F26B00` permanecem como cores de série de gráfico/acento (decisão 2026-07-15).
- **Novas features** nos assistentes (prompts, modelos, histórico) — só a casca visual muda. Export PDF é portado (F9), não é feature nova.

## 3. Arquitetura proposta
- **Front (padrão "rota paralela → promoção", herdado do piloto):** cada tela nativa nasce numa rota específica registrada no `App.tsx` ANTES do splat `caixa-seguro/*` (como `App.tsx:94-97` fez com `acompanhamento-orq`), **fora** do `CaixaSeguroApp`/`.caixa-theme`, com o mesmo `RequirePerm perm="tela_caixa_seguro"`. Quando a tela nativa atinge paridade, a rota oficial passa a apontar para ela e a antiga é apagada. Ao esvaziar o splat, `CaixaSeguroApp` morre.
- **Componentes nativos novos** em `ui-react/src/components/ui/` seguindo o padrão caseiro existente (PascalCase, tokens semânticos, sem Radix). Os já existentes cobrem: Button, Card, Tabs, Modal (←dialog), Input/Select/Textarea, Badge, InfoBanner (←alert), Spinner, Toast, Hint, Autocomplete.
- **Componentes de seção** reescritos em `ui-react/src/caixa/components/` com sufixo/pasta própria durante a transição; nomes finais limpos após a remoção dos antigos.
- **Navegação:** `MenuButton` nativo usando o novo DropdownMenu; entrada de menu em `lib/nav.ts:51` inalterada.
- **Decisões e alternativas descartadas:**
  - Re-skin do tema shadcn (trocar tokens HSL) — descartado: DS disjuntos, análise 2026-07-09 concluiu reescrita.
  - Trocar a regra `.caixa-theme * { border-color }` por `:where()` e migrar dentro do wrapper — descartado: alteraria as bordas glass das telas em produção durante a transição.
  - Wrapper de compatibilidade shadcn→nativo — descartado: prolonga a vida das deps Radix que queremos remover.
  - Componente de gráfico caseiro (substituir recharts) — descartado: recharts já é dep, padrão do piloto funciona.

## 4. Modelo de dados
Nenhuma alteração. Zero migration; etapa 6c do `deploy.sh` não se aplica. Deploy de cada fase = `ui-react/dist` commitada (parte automática do `deploy.sh`).

## 5. Fases

### F1 — Primitivos nativos de dados/formulário
- Entregável: Table, Skeleton, Checkbox, Switch, RadioGroup em `components/ui/`, com claro+escuro e `Hint` integrado onde couber.
- Inclui: API dos componentes espelhando os padrões dos existentes (`Input.tsx`, `Badge.tsx`); Table com variantes densa/normal e célula de ações; Skeleton com shimmer.
- Critérios de aceite: dado `html.dark` alternado, todos os primitivos mantêm contraste e bordas `edge`; nenhum uso de `@radix-ui/*`; tipos exportados; zero consumidores quebrados (código novo).
- Validação: tsc + eslint (baseline HEAD, zero erros novos) + build + pytest (inalterado).
- Revisão adversarial multi-agente antes da PR. PR: `feat(ui): primitivos nativos Table, Skeleton, Checkbox, Switch e RadioGroup`.

### F2 — Navegação nativa + promoção do piloto
- Entregável: `MonitoramentoOrq` é a tela oficial de `/caixa-seguro/acompanhamento`; `SalesManagement.tsx` apagado.
- Inclui: DropdownMenu nativo + `MenuButtonOrq`; skeletons nativos no loading dos KPIs; **`ProductTour` reescrito em versão nativa** (tour por passos, tokens `canvas/panel/edge/ink`, sem Radix) acoplado ao Monitoramento nativo; rota `acompanhamento` registrada fora do wrapper; rota antiga `acompanhamento-orq` vira redirect; remoção de `SalesManagement` e do `ProductTour` shadcn.
- Critérios de aceite: dado o menu da seção, quando navego entre as telas, então o `MenuButtonOrq` funciona na tela nativa e o `MenuButton` antigo segue nas telas ainda navy; a rota antiga redireciona; dark mode ok de ponta a ponta.
- Validação: tsc + eslint (baseline) + build + pytest; **verify** navegando o fluxo.
- Revisão adversarial antes da PR. PR: `feat(caixa-seguro): monitoramento nativo promovido a tela oficial`.

### F3 — Index (home) nativa
- Entregável: home da seção no DS nativo, rota `index` promovida.
- Inclui: `SearchProposals` nativo (Input/Badge/Card), `Tutorial` do mascote reescrito com posicionamento próprio e tokens nativos (sem Radix), FAB Diego via `ChatAssistantOrq`; apagar `Index.tsx` antigo + `Tutorial`/`TutorialRestart` shadcn.
- Critérios de aceite: dado um CPF/proposta buscado, quando o resultado renderiza, então paridade de conteúdo com a tela antiga; balão do mascote não sai da viewport (bug já corrigido no #192 — não regredir); gate de assistentes respeitado.
- Validação: tsc + eslint (baseline) + build + pytest; verify no fluxo de busca.
- Revisão adversarial antes da PR. PR: `feat(caixa-seguro): home nativa (busca, tutorial e FAB Diego)`.

### F4 — PortabilityTracking nativa
- Entregável: tela de portabilidades no DS nativo, rota `portabilidades` promovida.
- Inclui: Table nativa, `DateFilters` nativo, Checkbox nos filtros, badges de status; gráficos de portabilidade no padrão recharts do piloto; apagar tela antiga.
- Critérios de aceite: paridade campo a campo da tabela e filtros; ordenação/formatologia idênticas; dark mode ok.
- Validação: tsc + eslint (baseline) + build + pytest.
- Revisão adversarial antes da PR. PR: `feat(caixa-seguro): portabilidades no DS nativo`.

### F5 — AICommercialPanel nativa
- Entregável: painel IA-operacional no DS nativo, rota `ia-operacional` promovida.
- Inclui: tabelas + gráficos recharts padrão piloto; assistentes da tela (se houver) via `ChatAssistantOrq`; apagar tela antiga.
- Critérios de aceite: paridade de KPIs/gráficos/tabelas; tooltip de gráfico legível nos 2 temas.
- Validação: tsc + eslint (baseline) + build + pytest.
- Revisão adversarial antes da PR. PR: `feat(caixa-seguro): painel IA-operacional no DS nativo`.

### F6 — ProposalTracking nativa: tela base + consulta (rota paralela)
- Entregável: `acompanhamento/:status` nativa em rota paralela `-orq`, com cards e diálogos de consulta.
- Inclui: tela base (header, filtros, lista), `ProposalCard` nativo, `ProposalTimeline`, `ProposalDetailDialog` e `ProposalHistoryDialog` como Modal nativo.
- Critérios de aceite: dado cada status de proposta, quando abro a rota paralela, então cards e detalhe têm paridade com a antiga; a tela antiga permanece intocada e funcional.
- Validação: tsc + eslint (baseline) + build + pytest.
- Revisão adversarial antes da PR. PR: `feat(caixa-seguro): acompanhamento por status nativo — base e consulta`.

### F7 — ProposalTracking nativa: diálogos de envio
- Entregável: diálogos de envio nativos na rota paralela.
- Inclui: ResendLink, DPSLink, CreditCardLink, ProposalShare, SendOptions, SendAlert como Modal nativo + RadioGroup/Checkbox nativos.
- Critérios de aceite: cada diálogo abre/fecha por Esc e backdrop, foco gerenciado, paridade de campos e validações com o shadcn correspondente.
- Validação: tsc + eslint (baseline) + build + pytest.
- Revisão adversarial antes da PR. PR: `feat(caixa-seguro): diálogos de envio nativos`.

### F8 — ProposalTracking nativa: ações, workflow e sheet
- Entregável: fluxo operacional completo na rota paralela.
- Inclui: PaymentOptions, RefundManagement, DocumentUpload, NewSale, NPS (Switch/Textarea nativos), Sensitization + histórico (Table nativa); `ProposalWorkflowSheet` sobre o Sheet nativo novo; `InlineWorkflow` reescrito.
- Critérios de aceite: workflow inline navega todos os passos; sheet abre/fecha sem travar scroll da página; paridade de conteúdo.
- Validação: tsc + eslint (baseline) + build + pytest.
- Revisão adversarial antes da PR. PR: `feat(caixa-seguro): workflow e diálogos de ação nativos`.

### F9 — Promoção do ProposalTracking + assistentes
- Entregável: rota oficial `acompanhamento/:status` aponta para a nativa; assistentes visuais antigos removidos.
- Inclui: swap da rota; Diego/Léo/Lari → `ChatAssistantOrq` em todas as telas restantes (paridade do chat: histórico, gate, tratamento de erro por `err.status`, **export PDF portado dos assistentes antigos — `jspdf` permanece**); apagar `ProposalTracking.tsx` antigo + diálogos shadcn + assistentes antigos.
- Critérios de aceite: nenhuma referência restante aos diálogos shadcn; chat funciona por produto (Diego/Léo/Lari) com o mesmo backend; erros 429/402/503 mostram mensagem amigável via `err.status` (nunca `err.message.includes`).
- Validação: tsc + eslint (baseline) + build + pytest; verify no fluxo completo de propostas.
- Revisão adversarial antes da PR. PR: `feat(caixa-seguro): acompanhamento por status promovido + chat nativo único`.

### F10 — Aposentadoria do tema shadcn + polimento
- Entregável: seção 100% nativa; tema paralelo removido do bundle.
- Inclui: remover `CaixaSeguroApp.tsx`, `theme.css`/`.caixa-theme`, `caixa/components/ui/*`, `hooks/use-toast`, `toaster`; desinstalar `@radix-ui/*` e `sonner` se zerarem consumidores (`jspdf` FICA — export PDF portado na F9); redirects finais; renomear componentes `-Orq` para nomes limpos; passar **/simplify**; medir bundle antes/depois (skill performance: nunca otimizar sem medir).
- Critérios de aceite: `grep -r "caixa-theme\|@radix-ui" ui-react/src` sem hits (exceto package-lock de deps restantes); build menor que o baseline; navegação completa da seção sã nos 2 temas.
- Validação: tsc + eslint (baseline) + build + pytest; **/code-review** da fase; **security-review** (rotas RBAC preservadas).
- Revisão adversarial antes da PR. PR: `feat(caixa-seguro): remoção do tema shadcn e polimento final`.

## 6. Riscos e mitigações
| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Regra `.caixa-theme * { border-color }` engole bordas de componente nativo montado DENTRO do wrapper durante a transição | Bordas cinza #404040 em produção (bug já visto na análise) | Regra de ouro por fase: componente nativo só renderiza em rota FORA do wrapper; revisão adversarial confere imports cruzados |
| 2 | Perda de paridade silenciosa (telas são mock — reescrita pode trocar números, formatos, ordenações) | Usuário/stakeholder percebe dado "errado" e desconfia da migração inteira | Checklist de paridade campo a campo por tela na revisão adversarial; screenshots antes/depois nos PRs |
| 3 | Modal/Sheet caseiros regredirem acessibilidade que o Radix dava de graça (foco, Esc, aria) — a seção já teve PR de a11y (#190) | Teclado/leitor de tela quebrados em diálogos operacionais | Critérios de foco/Esc explícitos em F7/F8; reusar o Modal nativo já batalhado no editor de fluxo; verificação a11y na revisão |
| 4 | Gráficos recharts ilegíveis no dark (eixos `#94a3b8` fixos, grids claros) | Dashboards inúteis no tema escuro | Padrão do piloto formalizado numa constante compartilhada; validação dos 2 temas como critério em F4/F5; skill dataviz na revisão |
| 5 | PR sem rebuild da `dist/` | Fase "invisível" em produção | Checklist de PR: `npm run build` + dist no diff, toda fase |
| 6 | Remoção de dep Radix ainda usada por outro consumidor (F10) | Build quebra ou componente morre em produção | `grep` de consumidores antes de cada desinstalação; F10 só remove o que zerar referências |
| 7 | Rotas antigas favoritadas (`acompanhamento-orq`) somem | 404 para o usuário | Redirects nas promoções (F2, F9) e limpeza só em F10 |

## 7. Smoke pós-deploy
Por fase de promoção (F2, F3, F4, F5, F9) e completo após F10:
a) Navegar `/caixa-seguro` → todas as telas pelo menu; nenhuma tela abre com fundo navy/glass após F10; resultado esperado: visual nativo consistente com o resto do Orquestra.
b) Alternar dark mode (html.dark) em cada tela migrada; gráficos, tabelas e diálogos legíveis, bordas `edge` corretas.
c) Buscar proposta na home; abrir detalhe, histórico e timeline.
d) Em `acompanhamento/:status`: abrir cada diálogo de envio (Resend/DPS/Cartão/Share/Opções/Alerta), fechar por Esc e backdrop, conferir foco.
e) Rodar o workflow inline de ponta a ponta + abrir o sheet de workflow; upload de documento.
f) Com IA ativada no Admin: abrir FAB de chat em cada tela por produto (Diego/Léo/Lari), enviar mensagem, conferir histórico; desativar no Admin → FAB some.
g) Simular limite/erro do chat (se viável) → mensagem amigável, não stack/genérico.
h) Portabilidades: filtros de data + checkbox, tabela ordenada, gráficos.
i) Rota antiga `acompanhamento-orq` redireciona; nenhuma rota antiga dá 404.
j) Conferir bundle: tamanho do JS principal menor que antes da F10 (registrar números no PR).

## 8. Pendências e decisões em aberto
Decisões tomadas pelo usuário em 2026-07-15:
1. **Export PDF do chat**: PORTAR para o `ChatAssistantOrq` na F9; `jspdf` permanece.
2. **`ProductTour`**: PORTAR em versão nativa na F2.
3. **Acento de marca**: manter azul CAIXA `#0055B1`/laranja `#F26B00` como série/acento (padrão do piloto).
4. Ordem F3–F5: sem prioridade imposta — seguir F3→F4→F5.
