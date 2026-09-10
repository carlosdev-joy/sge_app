---
name: orquestra-caixa-seguro-poc
description: POC Caixa Seguro (Lovable) vira subpáginas /caixa-seguro no Orquestra com RBAC por USUÁRIO; plano de 5 fases acordado em 2026-07-08
metadata: 
  node_type: memory
  type: project
  originSessionId: 1bd7ac33-9e53-4987-8718-865c1cf5ddcc
  modified: 2026-09-02T01:08:57.564Z
---

Prioridade nova (2026-07-08), à frente dos smokes do [[orquestra-fluxo-etapas]]: trazer a POC **caixa-seguro-busca** (zip em `/root/caixa-seguro-busca-completo.zip`, feita no Lovable) para dentro do [[orquestra-sge-app]] como subpáginas em `/caixa-seguro/*`, com acesso concedido a usuários específicos.

**O que é a POC:** Vite + React 18 + shadcn/ui (Radix) + Tailwind + TanStack Query. 5 páginas: busca de propostas (Index), /acompanhamento (gestão de vendas), /acompanhamento/:status, /portabilidades, /ia-operacional. Dados 100% MOCK nos componentes. 3 assistentes IA (Diego/Lari/Léo) via Supabase edge functions → gateway Lovable (projeto ykreyhtdezagefjddapp). ProfileContext = toggle demo Operacional×Funcionário CAIXA (client-side). Tema CAIXA (azul #0055B1/laranja) em tokens CSS no :root.

**Fatos do Orquestra levantados (2026-07-08):** login valida credenciais contra a REST do Airflow (api/routers/auth.py; token opaco sha256 em etl_sessao); RBAC é POR PERFIL (etl_perfil_permissao, recursos string tipo tela_jobs), usuário tem 1 perfil (etl_usuario.perfil_nome); NÃO existe guard de rota no front (PrivateRoute só checa token; menu filtrado por useVisibleNav em lib/nav.ts, mas URL direta renderiza — proteção real é o 403 do backend); ui-react = React 19 + router 7 + TanStack 5 + zustand + Tailwind 3.4, SEM Radix/shadcn (componentes caseiros em src/components/ui/); rotas derivadas do registry NAV em lib/nav.ts + PAGE_ELEMENT no App.tsx (WILDCARD_ROUTES p/ subrotas); API base '/orquestra' (nginx remove o prefixo); migrations T-SQL idempotentes em sql/migrations (última: 059; skill .claude/skills/nova-migration); catálogo de recursos RBAC hardcoded em Admin.tsx RBAC_RECURSOS.

**DECISÕES do usuário (2026-07-08):**
1. Login: usuários-alvo JÁ conseguem logar (têm conta no Airflow) — não mexer na autenticação.
2. Permissões: `tela_caixa_seguro` (seção) + `caixa_seguro_operacional` (nível elevado — substitui o toggle demo por RBAC real).
3. Assistentes IA: DESENVOLVER JÁ com toggle ativar/desativar; se ativar, exige chave de LLM; ocultos no front quando off.
4. Visual: manter tema CAIXA da POC — shadcn/Radix em namespace próprio (src/caixa/), tokens escopados (NÃO no :root).

**PLANO (5 fases):**
- F1 RBAC por usuário: migration 060 (recursos novos semeados só no perfil admin + tabela `etl_usuario_permissao` matricula×recurso); `carregar_usuario` (deps.py) une perfil+overrides; actions no admin.py + UI no Admin.tsx (grants por usuário, invalidar sessões ao mudar, RBAC_RECURSOS atualizado).
- F2 Guard de rota no front: wrapper RequirePerm aplicado a TODAS as rotas com perm do NAV (fecha gap do app inteiro); redirect pós-login para a 1ª tela visível (usuário só-caixa cai em /caixa-seguro, não /dashboard).
- F3 Portar POC: src/caixa/{pages,components,ui,theme.css}; deps Radix/cva/tailwind-merge/docx (só o que as páginas usam); tokens sob .caixa-theme; conferir colisões no tailwind.config; rotas /caixa-seguro/* (WILDCARD_ROUTES); grupo novo no NAV; ProfileContext → hook de permissões reais; dados mock mantidos nesta fase.
- F4 Assistentes IA: router api/routers/caixa_chat.py (POST /caixa/chat/{assistente}, system prompts portados das edge functions); config enabled/provider/model em tabela + chave criptografada (reusar mecanismo ORQUESTRA_CONN_KEY) ou env var; log em `etl_caixa_chat_log` (substitui leo_conversations); front esconde assistentes se off.
- F5 Testes + revisão adversarial + deploy (migration 060 etapa 6c + api + dist; sem dags) + smoke com usuário de teste.

Sugestão de PRs: PR1=F1+F2 (fundação), PR2=F3 (seção), PR3=F4 (IA). POC extraída (efêmero) em scratchpad/caixa-seguro/ — re-extrair do zip se a sessão reiniciar.

**STATUS (2026-07-08): F1 IMPLEMENTADA na branch feat/caixa-seguro (commits 270b930 feat + 99a50da dist).** Entregue: migration 060 (etl_usuario_permissao matricula×recurso FK cascade + recursos tela_caixa_seguro/caixa_seguro_operacional só no perfil admin); carregar_usuario une perfil ∪ overrides (try/except pré-060, expõe permissoes_extra); actions user_perm_list/user_perm_set no admin.py (replace-all, invalida sessões exceto a própria, exige usuário cadastrado); Admin.tsx com RBAC_RECURSOS atualizado + coluna Extras + modal por usuário (herdadas do perfil travadas). pytest: 608 ok, 5 falhas pré-existentes na main (auth do ambiente de teste). **F2 TAMBÉM IMPLEMENTADA (commits cfda20c + eca9238 dist)**: canAccess/firstVisiblePath em lib/nav.ts (regra única sidebar+guard+redirect; /avisos = fallback sem perm); RequirePerm em todas as rotas do NAV no App.tsx; HomeRedirect no index/catch-all; Login navega p/ 1ª tela visível. Lint: 2 anys pré-existentes no Login.tsx (fora do diff). **PR #185 (F1+F2) MERGEADO em 2026-07-08** (usuário tentou pelo GitHub, ficou OPEN; concluí via gh pr merge). **F3 IMPLEMENTADA — PR #186 aberto** (branch feat/caixa-seguro-secao, commits 55b2edd + e2a8064 dist): src/caixa/ com 5 páginas + ~30 componentes + 17 shadcn; tema em .caixa-theme (portais Radix recebem a classe nos próprios ui/*.tsx); tailwind com tokens shadcn + paletas blue/orange/yellow/green MESCLADAS às escalas numeradas (não quebrar Orquestra) + tailwindcss-animate; ProfileContext lê caixa_seguro_operacional (sem toggle demo); assistentes chamam POST /caixa/chat/{assistente} via apiFetch, ocultos por ASSISTENTES_IA_ATIVOS=false em src/caixa/lib/config.ts (F4 liga); NAV grupo "Caixa Seguro" item Busca & Vendas; wildcard /caixa-seguro/*; deps novas (10 Radix, cva, clsx, tailwind-merge, sonner, tailwindcss-animate, jspdf, xlsx — deploy precisa de npm install); bundle 1,2→2,7MB (code-split futuro); ajustes p/ recharts v3 + tsconfig estrito; sem docx/file-saver (código morto não portado). Próximo: merge #186 → Fase 4 (router caixa_chat.py, config enabled+chave LLM, log etl_caixa_chat_log) → F5 testes+deploy.

**✅ EM PRODUÇÃO E FUNCIONANDO (confirmado pelo usuário 2026-07-09).** Toda a seção Caixa Seguro (Fases 1–4 + wheels #188 + UX #189/#190/#191/#192) deployada e validada em produção. F5 concluída.

---

## 🏁 2026-08-14 — WORKFLOW DA HOME NA SEQUÊNCIA DO DESENHO: TUDO EM PRODUÇÃO
> ⚠️ **SUPERADA em 2026-08-31** pela sequência de 8 cards (seção no fim deste
> arquivo). Os GOTCHAs desta seção continuam valendo; a tabela de 10 cards, não.

✅ **PRs #316, #317, #318, #319 e #320 MERGEADAS, DEPLOYADAS e CONFIRMADAS
FUNCIONANDO pelo usuário.** Nada pendente — main == produção. O usuário
**aguarda novas fases desta tela e avisará quando houver**.

Entrada: a imagem `/root/sequencia_wkf.png` (desenho aprovado do card
"Workflow" de Busca & Vendas, em `caixa/components/InlineWorkflow.tsx`).

**A sequência (ordem, nomes e sinal), como ficou:**

| # | card | sinal | | # | card | sinal |
|---|---|---|---|---|---|---|
| 1 | Aguardando Assinatura | aviso | | 6 | Pendência de DPS | aviso |
| 2 | Proposta Assinada | positivo | | 7 | Propostas Emitidas | positivo |
| 3 | Aguardando Pagamento | aviso | | 8 | Propostas Declinadas | perda |
| 4 | Propostas Pagas | positivo | | 9 | Devolução em Andamento | aviso |
| 5 | Pendência Documental | aviso | | 10 | Monitoramento de Sensibilização | positivo |

- **saiu** "Ass. e Sensibilizado" (`approved`); **entraram** `paid`
  (status NOVO, no tipo `ProposalOrq`) e `emission_sent` (já existia sem card).
- **Sinais** = ícone lucide + cor + `aria-label` + `<title>`:
  `aviso` 🔺 TriangleAlert âmbar · `perda` 📉 TrendingDown vermelho ·
  `positivo` ✅ CircleCheck verde. **TrendingDown e não X**: X lê como *erro*,
  e proposta declinada é *negócio perdido*.
- **Posição**: canto **INFERIOR** direito (`absolute bottom-1.5 right-1.5` +
  `relative` no botão). No topo colidiria com o rótulo longo; embaixo convive
  com o número, curto e centralizado.
- Mock de 17 → **18 propostas, ZERO órfãs**: `approved` virou `paid`, as duas
  `declined` viraram `refund_scheduled` (que é quem responde por "Propostas
  Declinadas").

⚠️ **GOTCHAs desta tela, que valem para qualquer card novo:**
1. **`counts` descarta em silêncio.** O laço faz
   `if (counts[status] !== undefined) counts[status]++` — status ausente do
   dicionário faz a proposta ser DESCARTADA sem erro: card zerado COM dado no
   mock, e isso passa por "ainda não tem proposta nesse status".
2. **Filtro de sub-status compara IGUALDADE.** Proposta de
   `refund_scheduled` sem `refundSubStatus` some ao filtrar por qualquer
   sub-status, aparecendo só em "Todos".
3. **Órfã = status no mock sem card.** Some de TODOS os filtros e só existe
   em "Todas as Propostas".
4. **Número e ícone no mesmo flex** faziam o número mudar de posição conforme
   1 ou 2 dígitos — numa fileira de dez cards, dançavam.

🧪 **`tests/test_caixa_workflow_sequencia.py` (28 testes)** prende tudo isso
lendo o TSX por regex: ordem/nomes exatos do desenho, sinal por card, ícone
PRÓPRIO por sinal (recusa dois iguais — voltaria a ser "só a cor"), cor nunca
sozinha, todo status contando, nenhum card permanentemente zerado (exceto
Devolução, que o desenho já mostra em 0), `ORFAS_CONHECIDAS` VAZIO e a
posição do sinal. Todas as mudanças foram conferidas por mutação.

✅ **PR #217 EM PRODUÇÃO E FUNCIONANDO (merge bac016a; deploy e validação
confirmados pelo usuário em 2026-08-01).** Nada pendente — main == produção.
Dois defeitos achados na véspera da apresentação:
1. **Busca da Consulta de Proposta não pesquisava.** Causa: mock ISOLADO com
   uma proposta (`80316460327404`) que não existia na lista do Monitoramento
   (`8047413032422-7`…), comparação por igualdade LITERAL, e o modo CPF sem
   `value`/`onChange`/`onClick` (agência/SEV/SR sem campo nenhum). Correção:
   **`caixa/lib/propostas.ts` virou FONTE ÚNICA** (20 propostas) e o
   Acompanhamento importa de lá; busca por dígitos (ignora máscara), múltiplos
   resultados, estado "nenhuma encontrada", Enter em todos os modos, e botão
   por linha que abre a proposta no Monitoramento já no status dela.
2. **Lari atrás do balão na etapa 1 do tutorial.** Causa: o clamp do PR #192
   usava altura ASSUMIDA (340px) e não sabia onde o avatar estava — sem espaço
   acima do centro, empurrava o balão para baixo sobre a Lari (92px de
   sobreposição em 1366×768, resolução de projetor). Correção:
   **`caixa/lib/tutorialLayout.ts`** mede o balão e testa lado preferido →
   oposto → demais, ficando no primeiro que cabe sem encostar no avatar;
   empilha no fallback; triângulo aponta para o lado EFETIVO.

⚠️ **TÉCNICA QUE FUNCIONOU SEM RUNTIME LOCAL:** extrair a lógica pura para um
módulo (`lib/*.ts`), compilar com `npx tsc <arquivo> --ignoreConfig --outDir
<tmp> --module commonjs` e exercitar com `node -e`. Assim dá para PROVAR a
correção sem navegador — 8 resoluções × 5 passos do tutorial e 10 casos de
busca foram validados assim. O front do Orquestra **não tem test runner**
(sem vitest/jest), então esse é o caminho para verificar lógica de front.

**F4 MERGEADA — PR #187 na main em 2026-07-08 (merge autorizado pelo usuário; commit 1f3e4e6).** Branch feat/caixa-seguro-ia (commits 73330df feat + 74458c2 dist): caixa_chat.py (POST /caixa/chat/{assistente} + /status + /historico, atrás de tela_caixa_seguro; 500 de config vira 503 genérico p/ usuário do chat), caixa_ia.py (config caixa_ia_* em etl_app_config, chave Fernet, provedores anthropic claude-opus-4-8 adaptive thinking MAX_TOKENS=4096 e openai_compat), admin.py actions caixa_ia_get/set/test (valida model≤100 e token cifrado≤1000; chave write-only mascarada), migration 061 etl_caixa_chat_log, front com useAssistentesIA (GET /status) + aba Admin "Caixa Seguro IA" (CaixaIAForm separado do loader p/ evitar setState em efeito). Validação: pytest 608 ok (5 falhas pré-existentes), eslint baseline 66 (zero novos), tsc ok, revisão adversarial 43 agentes: 13 achados → 7 corrigidos / 6 refutados. requirements ganhou anthropic==0.116.0 (deploy: pip install + migration 061 etapa 6c + api + dist; sem dags; assistentes nascem DESLIGADOS — ligar no Admin após configurar chave). Após merge → F5: deploy + smoke com usuário de teste. **UX/polimento (PR #189, mergeada 2026-07-08):** overlay de Sheet/Dialog corrigido (theme.css pintava background na classe .caixa-theme e vencia o bg-black dos overlays portalados → fix com :where() de especificidade zero; overlays agora bg-black/60 + backdrop-blur-sm; popovers voltaram ao dark da POC); Header da seção com logo CVP (/branding/logo-cvp.png + fallback SVG) + filete laranja + title por prop; KPI cards do Monitoramento Tático refinados (label uppercase/número 6xl/hover de elevação); gráficos unificados em emissões=#3E96D1/declínios=#DB6A1E (par CVD-safe validado); gotcha: comentário CSS com "*/" interno quebra o lightningcss no build. **PR #190 (mergeada 2026-07-08):** rotas /caixa-seguro/* full-bleed no AppShellV2 (FULL_BLEED_PREFIXES — sem a moldura p-6/max-w clara do shell); ToastViewport com bg-transparent (carrega .caixa-theme e herdava fundo branco → painel branco atrás do toast destructive); DialogDescription/SheetDescription sr-only nos 13 diálogos + sheet (warning Radix). Backlog UX CONCLUÍDO E EM PRODUÇÃO (PR #193, deploy confirmado 2026-07-09): filtros sticky no Monitoramento Tático (gotcha: overflow-hidden do wrapper capturava o position:sticky → trocado por overflow-clip, que recorta sem criar scroll-container), skeletons (ui/skeleton.tsx) no lugar do modal-spinner ao trocar de produto, gráfico de portabilidade dividido em Quantidade/Valor (fim do eixo duplo). Nada pendente de deploy — main == produção. **PR #192 (mergeada 2026-07-09):** balão do tutorial não corta mais (position:fixed + clamp(); animação separada do posicionamento; scroll em wrapper interno p/ não clipar o triângulo/cauda); GOTCHA descoberto: bg-gradient-primary/bg-gradient-dark eram usados em botões mas não existiam no tailwind.config → resolviam p/ sem-fundo (botão branco); adicionados em backgroundImage apontando p/ vars do theme.css; removido rodapé "Powered by IA Operacional CAIXA". **PR #191 (mergeada 2026-07-08): header único** — filete laranja CAIXA agora no HeaderV2 do shell (app inteiro); header interno da seção removido das 5 páginas e caixa/components/Header.tsx apagado (logo CVP e nome da tela já vêm do Brand+breadcrumb do shell). **Gotcha do deploy corrigido (PR #188, mergeada 2026-07-08):** a imagem do orquestra-api instala offline (pip --no-index --find-links=wheels) — todo pacote novo no requirements.txt exige as wheels em api/wheels/ (versionadas no git); anthropic 0.116.0 + distro + docstring_parser + jiter cp311 adicionadas e build validado localmente.

---

## 🏁 2026-08-31 — A SEQUÊNCIA DO WORKFLOW VIRA 8 CARDS, NUMA FONTE SÓ

**PR #345 MERGEADA na `main` (squash `ce8963c`), merge autorizado pelo usuário.
⏳ DEPLOY DE PRODUÇÃO PENDENTE** — só front (`ui-react/dist`), sem migration,
sem `dags/`, sem wheels; responder **n** para `config/` (ver
[[orquestra-chamados-tabela-copiar-notas]]). Motivo do pedido: *"iremos colocar
dados reais agora em cada card"* — os 8 cards são o esqueleto que vai receber a
fonte real, que **ainda não foi definida**.

**A sequência, ditada pelo usuário (substitui os 10 do desenho de agosto).**
Os nomes foram encurtados numa segunda passada, a pedido dele — "Proposta…"
repetido em oito cards não distinguia nada:

| # | card | status | sinal | selo na lista |
|---|---|---|---|---|
| 1 | Pendentes de Assinatura | `pending_signature` | aviso | Pendente de Assinatura |
| 2 | Pendentes de Pagamento | `awaiting_payment` | aviso | Pendente de Pagamento |
| 3 | Assinadas e Pagas | `paid` | positivo | Assinada e Paga |
| 4 | Em Análise | `in_analysis` 🆕 | aviso | Em Análise |
| 5 | Emitidas | `emission_sent` | positivo | Emitida |
| 6 | Rejeitadas | `declined` | perda | Rejeitada |
| 7 | Devoluções de Prêmio | `refund_scheduled` | aviso | Devolução de Prêmio |
| 8 | Sensibilizações | `sensitization_monitoring` | positivo | Sensibilização |

**As duas fusões que levam 10 → 8** (decididas por mim, com as premissas
declaradas ao usuário — ele dispensou a rodada de perguntas e mandou seguir):
- `signed_proposal` entrou no card 2, com o sub-status do ciclo de pagamento
  preservado no filtro;
- `pending_dps` virou **sub-status** `dps` do card 4 — é ele que troca o botão
  da proposta entre *Upload* e *Enviar Link DPS*, em vez do card;
- `return_in_progress` saiu (não tinha proposta nenhuma);
- `declined` virou o estado de ORIGEM da devolução: *Gerenciar Devolução* move
  a proposta do card 6 para o 7.

⚠️ **ACHADO: a home tinha DOIS "Workflow" com vocabulários diferentes.** O botão
do cabeçalho (`ProposalWorkflowSheet`) tinha 9 status próprios — "Ag. Link
Pagamento", "Cotação", "Rascunho" — sobre 13 propostas que não eram as da tela;
o card colapsável (`InlineWorkflow`), outros 10. **Agora os dois leem
`caixa/lib/workflow.ts`**, que é a constante a ser trocada pela consulta quando
os dados reais entrarem. `tests/…_sequencia.py` recusa que qualquer um deles
volte a declarar `statusInfo`/`mockWorkflowProposals` próprios.

⚠️ **GOTCHA NOVO (achado na auto-revisão): sub-status × status que muda em
runtime.** A regra "toda proposta de status com sub-filtro precisa do campo"
não bastava: a rejeitada vira `refund_scheduled` **no clique do botão**, e sem
`refundSubStatus` sumiria do card 7 no primeiro filtro. Ela nasce com o campo,
e há teste para isso. Regra geral: olhar também os destinos de
`setProposalStatuses`, não só o status estático do mock.

✅ **Melhoria estrutural:** a contagem virou `contarPorStatus()`, que zera uma
chave POR ETAPA da sequência — o dicionário escrito à mão (GOTCHA nº 1 da seção
anterior, que DESCARTAVA proposta em silêncio) deixou de existir.

🧪 **Validação:** pytest **8 falhas / 3980 passam** = as MESMAS 8 do baseline
(4 auth em `test_api_v2_4`, 3 `test_kanban_rodape_card`, 1 `test_smoke`), zero
novas; `tsc -b` limpo; eslint só o erro pré-existente de `ProfileContext.tsx`;
`npm run build` com `dist/` commitada. `test_caixa_workflow_sequencia.py`
reescrito: 29 testes.

📌 **PENDENTES:**
1. ~~Deploy de produção~~ ✅ **FEITO em 2026-09-01**.
2. ~~A fonte de dados reais de cada card~~ 🏁 **OS 8 CARDS LEEM O PIO, EM
   PRODUÇÃO** (2026-09-01) — ver [[project-pio]]. `propostasWorkflow` continua no
   repo mas **some da tela por completo**: `PROPOSTAS_DE_EXEMPLO` fica vazio
   quando todo status tem origem no PIO.
3. Revisão adversarial multi-agente **não foi feita** (a desta PR foi manual, e
   foi ela que pegou o bug do sub-status em runtime). O usuário mandou abrir e
   mergear direto.

---

## ⚠️ 2026-09-01 — A ORDEM DOS BLOCOS DA HOME É DECISÃO DO USUÁRIO

Regra geral em [[regra-nao-mudar-ordem-da-tela]]: **não reordenar objeto de tela
sem pedido claro; na dúvida, perguntar ANTES.** Ela nasceu aqui.

**Ordem atual de `caixa/components/SearchProposals.tsx`** (PR #347 mergeada,
`70bb90e` — ⏳ **deploy do `dist/` pendente**; decidida pelo usuário com as duas
opções desenhadas lado a lado):

`escolha do modo` → `campo + Pesquisar` → `nenhuma encontrada` → `tabela de
resultados` → **`InlineWorkflow`** → dialog de detalhe

O Workflow ficava no MEIO (posição herdada da tela antiga, F8): quem escolhia
"Nº da Proposta"/"CPF" no topo rolava os 8 cards para achar o campo, e rolava de
novo para ver o resultado. Subiram o campo **e** os resultados — mover só o campo
recriaria a rolagem na volta. Há comentário no ponto exato do TSX dizendo que foi
decisão explícita, para ninguém "consertar" de volta.

O Tutorial destaca o container `.search-section` e mede com
`getBoundingClientRect` — reordenar filhos não afeta o highlight.
