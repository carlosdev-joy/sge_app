# UX profissional do Pipeline
Data:2026-10-11 · Estado: especificação detalhada para revisão; produto não alterado.
Usuário pediu ferramenta bonita, funcional e fácil de utilizar e confirmou direção da reorganização após análise do repositório/mockups/DEV.
Base: develop df1a81caa3ef5400877bf3ab2f798011552143b2, DEV2.17.1.
Canônicos: docs/spec-ux-pipeline-profissional.md e docs/design/pipeline-experiencia.md.
Direção: cinco abas, editor principal por configuração, Montagem e Execução como abas principais, com histórico/logs dentro de Execução e visualizador operacional comum; Configuração fora do canvas; rascunhos descobertos na lista; sessão de edição contínua; estados reais e animações acessíveis.
DEV observado: QA5_A vazio; cabeçalho rascunho em Execuções com fonte publicada, formulário de governança/agenda dentro do Fluxo, orientação de editar no inspector operacional, ambiente aplicação/destino pouco distintos.
Não houve edição/publicação/disparo no DEV. Evidências F9 anteriores não são nova rodada de testes.
Elaboração da proposta autorizada; revisão do documento/protótipo precede implementação. Produção/main não autorizadas.
Próxima etapa: revisar spec, prototipar jornada com simulações identificadas e planejar fases contra develop; seguir CLAUDE.md, QA adversarial e gates vigentes. Não reabrir F1–F9 técnicos nem prometer50pipelines/IA integral.


## 2026-10-11 — protótipo autorizado e preparado
Usuário autorizou seguir com o protótipo navegável nesta conversa. Fonte em `docs/prototypes/pipeline-workspace/`, com HTML portátil, README, testes do modelo e evidências. Implementação no DEV não foi realizada. Antes de alterar o produto, obter a validação visual e adaptar a base React/.NET existente; não copiar motor, autenticação ou permissões simuladas para produção. A presença de Ana Lima e um rascunho em edição é fictícia e não demonstra lease multiusuário.


## Preservação funcional e revisão de navegação — 11/10/2026
Decisão do usuário: Montagem e Execução são abas principais. Histórico/logs integram Execução, sem uma segunda faixa de modos. O inventário dos 11 componentes, oito agendas, sessão, publicação e ações operacionais está na [matriz de preservação funcional](../../docs/matriz-paridade-pipeline.md). Essa matriz é requisito para implementação: reduzir densidade não autoriza perder campos, payloads, permissões ou funcionalidades. Integrações e campos especializados não cobertos pelo protótipo permanecem pendências explícitas.


## Estado das entregas — 11/10/2026
- 2.18.0 (F3 inicial, PR #499) e 2.19.0 (F4.1, PR #500, `develop` `3900e7c2`) publicadas e validadas no DEV.
- F4.2 candidata 2.20.0 na branch `feat/ux-pipeline-inspector-f4` (migration 166): inspector inline em subseções, mescla por campo (`lib/workspacePatch`), desfazer/refazer de 50 passos (`lib/workspaceHistory`), modo focado e diagnóstico por subseção. Sem commit/PR/DEV até a revisão do Codex. Release notes `docs/release-notes/2.20.0-pipeline-ux-inspector.md`.
- Gotchas: o React Compiler (eslint react-hooks 7) não analisava o `WorkspaceEditor` da base; após a F4.2 ele analisa e acusa `Date.now()` em funções do componente — o relógio de eventos fica em `eventClock` fora do componente. O minireact usa a `key` no caminho do estado; o estado de um caminho antigo persiste ao voltar à mesma key (React descartaria).
- F4.2, correções da revisão preliminar: `useNavigationGuard` do editor ativo com `dirty||unapplied` (formulário do inspector pendente; `WorkspaceSessionState.unapplied` e selo próprio no cabeçalho; Salvar não o inclui); Recarregar/Descartar avisam e descartam o formulário (`inspectorEpoch` na key do `NodeProperties`), Encerrar avisa e o mantém. `recordHistory` reinicia se antes OU depois expõe valor protegido (etapas, `legacyTables` e `parameters`). Gotcha da bancada: para testar a guarda, a seção 15 troca `react.useEffect` e roda só o efeito de registro e o `onSession` do último render.
- F4.2, terceiro achado (navegador): o botão Desfazer/Refazer que fica desabilitado no último passo perde o foco para o body e Ctrl+Shift+Z deixa de chegar ao `onKeyDown` da Montagem. Correção: `travel` guarda o `activeElement` e um `useLayoutEffect` aplica `historyFocusTarget` (botão oposto habilitado, senão o canvas via `focusRef` do `WorkspaceCanvas`, com `preventScroll`). Gotchas: a bancada do Codex usa `End` + `' X'` numa textarea que quebra linha — `End` para na quebra visual e o desfazer nativo agrupa diferente; minireact não roda `useLayoutEffect`, então foco só se prova na regra pura e no navegador. Mutar fontes com o Vite do worktree servindo afeta bancadas de navegador concorrentes.
- F4.2, achados 4 e 5: `PainelSql` usa container query nativa (Tailwind 3.4 sem plugin: `[container-type:inline-size]` + variante `[@container(min-width:42rem)]:`; a 947 o inspector tem 641 px e precisa continuar empilhado, daí 42 e não 40 rem). Foco do diagnóstico em `NodeProperties`: `MutationObserver` só na subseção, com `data-loading` nos fallbacks do Suspense e limite de 5 s; controle por `data-diagnostic-field`; regra pura em `diagnosticFocusTarget`/`diagnosticFocusAllowed`; `InspectorDiagnostic.focus` é consumido por `onDiagnosticFocus` para a remontagem não roubar o foco. Gotcha: o `setup()` das bancadas registra a rota do fixture ao criar o contexto; para mudar `/validate`, use uma subclasse em vez de trocar `f.route` depois.
- Pendentes: QA/navegador do Codex para F4.2, F5, F2, F6 e aceite integrado da F3. Malha pausada e fora de escopo.
