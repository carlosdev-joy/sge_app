# EOC-F0 — Inventário, rastreabilidade e contratos

Data: 2026-10-13 (America/Sao_Paulo) · Fase: **EOC-F0**, documental · SPEC: [experiência e operação consolidada](spec-experiencia-operacao-consolidada.md).

## 1. Bases e limites

| Base | Identificação | Uso neste inventário |
|---|---|---|
| Código integrado | `develop` `92d14d596c95212d10bd30c3085edde4ce7c6b83` | Fonte de “existente”. Linhas citadas vêm da reconciliação e, quando marcado, foram reconferidas nesta fase. |
| Análise comparativa | `docs/analises-ux-modulos-malha` `5a6dbf3644a2002ca967516163200e7924ea8659` | Estudo, design global e notificações. A matriz R01–R28 da reconciliação foi feita sobre o pacote anterior `41ac369d`; o complemento de notificações já usa `5a6dbf36`. |
| Referência documental Pipeline | `52c0c589` e registros posteriores no develop | [SPEC Pipeline](spec-ux-pipeline-profissional.md), [matriz de paridade](matriz-paridade-pipeline.md), [progresso](ux-pipeline-progresso.md). |
| Reconciliação local | `/root/orquestra-reconciliacao-20261013` | `RECONCILIACAO.md`, `MATRIZ-E-PLANO.md`, `NOTIFICACOES-E-ALERTAS.md`, `REQUISITO-ALERTAS-PIPELINE.md`, `bases.json` e snapshots `base/` e `referencias/`. |

Limites desta fase:

- Leitura estática de documentos e código. Registro estático não prova comportamento em runtime; nenhum smoke, teste, envio, conexão com banco ou execução de pipeline foi feito.
- DEV 2.21.1 com SHA `92d14d59` é evidência histórica de rodadas anteriores, não revalidada aqui.
- **Backlog canônico de produção (`dbo.etl_backlog`) não consultado.** Status vivo e responsáveis cadastrados ficam **desconhecidos**. A conciliação depende de consulta autorizada (gate G-BACKLOG, seção 7).
- UX01–UX12, V0–V5, R01–R28 e N01–N08 são identificadores documentais. Não são cadastro no backlog, reserva de versão ou de migration. Nenhum número de migration é reservado por este documento.
- Responsáveis: **Codex coordena e revisa; Claude implementa**. Donos externos (operação, Microsoft/tenant, DataStage, representantes dos três públicos) estão **a confirmar** e não foram atribuídos a pessoas.

Reconferências feitas no código desta base para dúvidas materiais:

- Não há `pipeline-index` em `backend-dotnet/`, `api/` ou `ui-react/src/` (busca na árvore do worktree, cujo commit atual só acrescenta documentação sobre `92d14d59`).
- `ui-react/src/components/workspace/WorkspaceRunInspector.tsx:32` monta as linhas de tentativa a partir de `step.tentativas` (histórico operacional), e a linha 41 usa esse número como `try_number` em `/pipeline-task-log`. Isso confirma estaticamente o bug de tentativas.
- `api/routers/execucoes.py:2582` documenta `user` e `display_name` no body do ack (achado N05, contrato estático).
- `sql/migrations/045_remove_tela_malha_ds.sql` e `046_drop_ds_malha_tables.sql` existem; a 046 remove `etl_ds_malha*`, inclusive `etl_ds_malha_status` e `etl_ds_malha_falha`.

## 2. Legenda

Estado, conforme §9 da SPEC: **não iniciado**, **candidato**, **integrado**, **publicado DEV**, **aceito com evidência**, **bloqueado**, **fora do escopo**. Status desconhecido nunca vira entregue.

Confiança da fonte: **C** código integrado em `92d14d59`; **E** evidência histórica com SHA/ambiente; **D** decisão do usuário ou SPEC; **P** proposta ou referência externa; **W** WIP local, sem commit.

## 3. Matriz dos 24 entregáveis

Responsável padrão de todas as linhas: Codex coordena/revisa, Claude implementa. A coluna “Externo” lista apenas o que depende de terceiros ainda não confirmados.

| Fase | Entregável | Estado | Capacidade existente a reutilizar (fonte) | Pendência real | Aceite que fecha | Externo / gate |
|---|---|---|---|---|---|---|
| F0 | Inventário, rastreabilidade e contratos | candidato: documentação revisada; integração pendente (sem publicação DEV, por ser fase documental) | Reconciliação R01–R28, N01–N08 e decisão de alertas (P/D) | Integração da PR; conciliação viva com backlog canônico | Aceite documental técnico após revisão; fonte/SHA/estado/responsável por item; G-BACKLOG registrado como aberto | G-BACKLOG |
| F1 | Tentativas reais do motor | candidato (W: `fix/ux-pipeline-tentativas-motor`, sem commit) | Inspector Resumo/Tentativas/Logs/Parâmetros e `/pipeline-task-log` (C); motor com 2 tries e logs 1/2 (E) | Interface usa contador operacional como `try_number` (C, reconferido); leitura exata DAG/run/task/map_index/try | Duas tentativas com logs corretos na fixture já encerrada; identidade divergente, resposta antiga, acesso indevido e fonte ausente rejeitados | — |
| F2 | Catálogo unificado e retomada | candidato (W: `feat/ux-pipeline-descoberta-f2`, sem commit) | `Pipelines.tsx`, `PipelineCreate`, lease em `SqlDraftRepository` (C) | Índice .NET inexistente (C, reconferido); achado pipelines-only/editor/filtro `editing` a resolver antes da PR | Criar→reencontrar→retomar a mesma identidade; uma linha por pipeline na collation; 503 honesto; publicação concorrente | — |
| F3 | encerrada em DEV2.22.3: PR507/508/509; L1/L4 nativos próprios, paridade11/8, replay e diagnóstico, suíte7913PASS/mesmas8falhas/51skip sem regressão; cleanup confirmado. DataStage/Caixa/canais/piloto externos permanecem pendentes nas fases próprias | [Aceite F3](eoc-f3-aceite-integrado.md), [2.22.2](release-notes/2.22.2-workspace-confirmacao-execucao.md), [2.22.3](release-notes/2.22.3-workspace-diagnostico-etapa.md) |
| F4 | Sistema visual comum | candidato2.23.0 validado: TypeScript/build/lint sem novas, suíte7914PASS/mesmas8falhas/51SKIP, amostra20casos e nativo próprio; publicação a confirmar na evidência pós-deploy | `components/ui/*`, `index.css`, `tailwind.config.js`, tokens claro/escuro (C) | [Contrato F4](eoc-f4-sistema-visual.md) entregue; expansão do shell/canvas F5. Integração e publicação DEV do candidato pendentes de prova | Dois temas, foco, zoom 200%, licença da fonte, canvas não reduzido | Inter local/OFL conferidos |
| F5 | Shell e piloto visual Pipeline | não iniciado | `Sidebar`, `HeaderV2`, `lib/nav.ts`, aliases (C) | Ordem de menu sem inventário de destinos/RBAC/frequência | Rotas/RBAC/aliases mantidos; 1440/1280/947/390; claro/escuro | — |
| F6 | Aceite F6 Pipeline e rollout | não iniciado | Flags/capabilities do workspace (C); homologação técnica F9 (E, não equivale a F6) | Piloto dos três públicos, métricas, coorte, reversão; benchmark antes de 5 s | Jornadas concluídas por públicos reais; orçamento de 300 KiB | Representantes dos três públicos a confirmar |
| F7 | Contrato de alertas principais | não iniciado | `notify.py`, `etl_failure_ack`, grupos/templates Teams, `etl_email_log`, `etl_sla_alert` (C) | Autoridade de Sucesso/Warning/Falha e geração de ciclo; policyRevision por run | Política por run; nós não suprimem; migração sem envio retroativo | Fonte do resultado agregado a validar |
| F8 | Configuração simples do pipeline | não iniciado | Seção Notificações em `WorkspaceConfiguration` (C) | Formulário Sucesso/Warning/Falha, destinatários, E-mail/Teams pessoal/canal | Três destinos geram três entregas; salvar draft não envia | — |
| F9 | Intenções persistentes e dispatcher | não iniciado | Dedup SLA e log de e-mail (C), sem outbox | N03, N04, N07: dedup antes do envio, status HTTP só impresso, resultado incerto | Crash/429/500/timeout sem perda nem reexecução; unique guards | — |
| F10 | Adapters E-mail e canal Teams | não iniciado | `email_operator.py`, grupos `etl_msg_grupo`, factory Teams (C) | Canal inválido sem fallback; reenvio auditado; cutover sem duplicar | Erro de canal não altera execução | Destinos de teste autorizados |
| F11 | Teams pessoal corporativo | não iniciado | Nenhuma (webhook de canal não é chat pessoal) | Resolver identidade → tenant/userId → conversa; escolher provider | 403/429, ausente e não instalado explicados | **G-MICROSOFT**: tenant, app/bot, permissões, instalação |
| F12 | Gestão de alertas e tratamento | não iniciado | `GestaoFalhas.tsx`, `/execucoes/ack` e `/resolve`, bulk, ticket (C) | N02 (ack repete comunicação), N05 (ator do body), N06 (link genérico `/logs`), chave pipeline+execution_id | Ler não assume; ator da sessão; 409; duas corridas isoladas | — |
| F13 | Comunicações customizadas e SLA | não iniciado | Nó E-mail falha a task; nó Notificação best-effort; SLA BREACH/RISK/PREDICT (C) | Opt-in de obrigação para Teams; SLA como intenção recuperável | Relatório SQL preservado; sem recursão | Restart de worker/DAGs geradas em DEV |
| F14 | Malha: catálogo e contexto | não iniciado | `Malha.tsx`, `SeletorCorrida`, `CabecalhoCorrida`, corrida/ODATE/snapshot (C) | Identidade definição × instância; retorno Malha→Pipeline→mesma corrida | Contexto preservado; histórico não atua na corrida atual | — |
| F15 | Malha: canvas, propriedades e diagnóstico | não iniciado | `MalhaEditor` React Flow, `PainelCorridaLateral` Agora/Travando/Eventos (C) | Busca/localizador, propriedades, alternativas por teclado | Layout não altera dependência; snapshot imutável | — |
| F16 | Malha: definição versionada | não iniciado | Snapshot de membros (C), que não é versionamento | Modelo de versão por membro, compatibilidade e impacto em voo | Modelo com revisão técnica do Codex antes de DDL ou mutação | — (revisão técnica, não nova confirmação do usuário) |
| F17 | Calendários e preview | não iniciado | Oito modos de agenda e campo calendário legado (C, `pipelineUtils.ts:3–9`) | Fuso/DST, exceções, preview sem disparo | Mesmo cron legado; preview não dispara | — |
| F18 | Eventos correlacionados e recursos | não iniciado | Dependências atuais da Malha (C); lease de edição não é recurso | Suporte real do motor a recursos e AND/OR | Teste concorrente; limites reais | — (modelo e carga com revisão técnica do Codex antes de ativar) |
| F19 | Monitor global | não iniciado | `Logs`, `Dashboard`, `Performance` e polling de 30 s (C) | N01 (erro vira lista vazia); lookup exato; timeline só com tempos reais | Vazio distinto de erro; RBAC servidor | — |
| F20 | Previsão e recuperação assistida | não iniciado | P90 heurístico do SLA (C) | Forecast com confiança; simulação; recuperação idempotente | Fato × previsão; sem Set to OK | Dados nativos autorizados |
| F21 | Preferências e governança de apresentação | não iniciado | Zoom/painéis/layout parciais (C) | Escopo pessoal × compartilhado; reset; migração | Reset não muda definição | — |
| F22 | Adoção visual por famílias | não iniciado | Rotas do `NAV` (C, seção 6) | Checklist por rota antes/depois | Campos/ações/RBAC iguais; Caixa com tema escopado | — |
| F23 | Aceite global e rollout final | não iniciado | — | Piloto integrado, carga, retenção, reversão | Requisitos com SHA/ambiente/evidência; nunca 100% com bloqueio ativo | G-MICROSOFT, DataStage, destinatários de teste |

Nenhuma linha está em “integrado”, “publicado DEV” ou “aceito com evidência” como entregável EOC. As capacidades integradas listadas são insumo, não entrega desta SPEC.

## 4. Capacidades e pendências por módulo

Mapa dos achados reconciliados para as fases EOC. Estado da capacidade, não do entregável.

| Módulo | IDs | Já existe (C/E) | Pendência real | Fase EOC |
|---|---|---|---|---|
| Pipeline: descoberta | R01–R05 | Lista via `/pipelines`, criação, lease | Índice, draft-only, união publicado+draft, editor válido | F2 |
| Pipeline: autoria | R06–R11 | Sessão/fence, canvas amplo, arraste, Delete, inspector 11 tipos, undo de 50 patches, diagnóstico, versões, publicação | Aceite integrado e paridade abrangente | F3, F4, F5 |
| Execução | R12–R15 | Snapshot por corrida, renderer, histórico, pausa UUID (PR 503, smoke posterior aprovado), polling de 30 s | Tentativas reais (bug confirmado); 5 s depende de carga; harness pausa+overlap combinado falhou e não conta | F1, F3, F6 |
| Configuração e agendas | R16–R17 | Oito modos, campo calendário legado, cadastros reais | Round-trip amplo; calendário/fuso/DST | F3, F17 |
| Malha | R18–R22 | Catálogo, editor, dependências, corrida/ODATE/snapshot, abrir/fechar/reabrir | Contexto e retorno; versionamento; recursos e AND/OR | F14–F18 |
| Monitor/SLA | R23, N03 | SLA BREACH/RISK/PREDICT com P90 | Forecast real; dedup antes do envio | F13, F19, F20 |
| Governança e preferências | R24–R25 | Lease/fence/RBAC/versões; zoom/painéis | Preferências versionadas | F21 |
| Design global | R26–R27 | Tokens e componentes base | Contrato global, glossário | F4, F5, F22 |
| Rollout | R28 | Flags/capabilities | Piloto dos três públicos | F6, F23 |
| Notificações e falhas | N01–N08 | Inbox, sino, comunicados, Gestão de Falhas, grupos/templates, nó E-mail, nó Notificação, log de e-mail | Política no pipeline, entregas por canal, ator servidor, links exatos, resultado incerto | F7–F13, F19 |

N01–N08 são riscos demonstráveis pelo código, não defeitos certificados em runtime. Cada um precisa de reprodução em fixture antes de ser declarado defeito.

## 5. Mapa UX01–UX12 e V0–V5 para EOC

Mapeamento documental; nenhum item é cadastro, fase ou versão.

| Origem | Fase EOC | Observação |
|---|---|---|
| UX01–UX02 | F2 | Descoberta e entrada. |
| UX03, UX07 | F1, F3 | Identidade, tentativas, aceite integrado. |
| UX04–UX06 | F4, F5 | F4 Pipeline já entregue; refinar sem duplicar. |
| UX08 | F3, F13 | Paridade 11/8 e tarefas customizadas. |
| UX09 | F6, F23 | Piloto, carga, rollout. |
| UX10 | F16–F22 | Templates, pastas e embedding seguem como proposta até aprovação; conectores novos e IA integral estão fora do escopo. |
| UX11 | Transversal | Pipeline ≠ Etapa ≠ Run ≠ Try; HTTP como tipo canônico; sem renomear API. |
| UX12 | Transversal | Confiança externa rotulada; não bloqueia correções. |
| V0–V5 | F0, F4, F5, F14, F15, F22 | Pranchas são referência vetorial, não renderizadas nem aprovadas visualmente. |
| Notificações 13/10 | F7–F13 | Decisão do usuário em `REQUISITO-ALERTAS-PIPELINE.md`. |

## 6. Superfícies para adoção visual (insumo da F22)

Lista concreta a partir de `ui-react/src/lib/nav.ts:34–68` em `92d14d59`. Cada superfície precisa de checklist próprio de campos, ações e RBAC antes da PR.

| Grupo atual | Rota | Permissão | Fase que trata primeiro |
|---|---|---|---|
| Operação | `/dashboard` | `tela_dashboard` | F22 |
| Operação | `/gestao-falhas` | `tela_logs` | F12, depois F22 |
| Operação | `/logs` | `tela_logs` | F19, depois F22 |
| Operação | `/ds-console` | `tela_ds_console` | F22 (DataStage com restrições) |
| Operação | `/utilitarios` | `tela_utilitarios` | F22 |
| Operação | `/performance` | `tela_performance` | F19/F22 |
| Operação | `/finalizacao` | `tela_finalizacao` | F22 |
| Operação | `/avisos` | sem permissão | F22 (destino de fallback; preservar) |
| Operação | `/chamados` | `tela_chamados` | F22 |
| Construção | `/pipelines` | `tela_pipelines` | F2, F5 |
| Construção | `/fluxos` | `tela_jobs` | F5 (oculto com navegação contextual) |
| Construção | `/publicacao` | `tela_logs` | F5/F22 |
| Construção | `/malha` | `tela_malha` | F14, F15 |
| Governança & Dados | `/governanca`, `/impacto-campo`, `/planos-ajuste`, `/copia-dados`, `/inventario` | `tela_*` próprias | F22 |
| BI | `/powerbi` | `tela_powerbi` | F22 |
| Caixa Seguro | `/caixa-seguro` | `tela_caixa_seguro` | F22, tema escopado |
| Agentes | `/agentes` | `tela_agentes` | F22 |
| Administração | `/admin` (inclui Comunicação/Notificações) | `tela_admin` | F8/F10 para Notificações, F22 para o restante |

Rotas fora do `NAV` (aliases, workspace por abas, telas internas de Admin e Caixa) precisam ser inventariadas em F5 antes de qualquer mudança de menu.

## 7. Backlog, duplicatas e artefatos removidos

**Gate G-BACKLOG.** Consultar `dbo.etl_backlog` somente com acesso autorizado, em leitura, para conferir status e responsáveis. Até lá: status desconhecido; não cadastrar, não reservar ID, não importar tarefas antigas automaticamente.

| Item histórico | Classificação | Tratamento |
|---|---|---|
| `docs/backlog-fase2-malha-observabilidade.md` (Fases 2.1–2.4) | **Obsoleto quanto a artefatos**: depende de `etl_ds_malha_status` e `etl_ds_malha_falha`, removidas pelas migrations 045/046 (C) | Não reativar. Conceitos de baseline e desvio só podem ser reaproveitados em F19/F20 sobre a arquitetura atual. |
| Textos que chamam F5/PR 502 e pausa/PR 503 de “candidato” | **Superado**: integrados no Git (C) | Não tratar pausa como pendência; manter cronologia histórica. |
| Trechos do estudo que dizem “sem execução Databricks” ou “três tours Control-M” | **Superado** pelas atualizações DB011/012 e CTM009/010 (P) | Usar a síntese consolidada. |
| UX-F2 e EOC-F2 | **Duplicata potencial** | EOC-F2 conclui o candidato UX-F2; não criar segunda lista. |
| UX-F6 e EOC-F6/F23 | **Duplicata potencial** | EOC-F6 encerra UX-F6 para Pipeline; F23 cobre o conjunto novo. |
| Homologação técnica F9 do workspace e F6 UX | **Distintos** | F9 não encerra F6. |
| F1–F9 de SPECs anteriores, fases Malha e técnicas | **Ocupados** | Não renumerar; EOC usa F0–F23 próprios. |
| Gestão de Falhas e “novo módulo de incidentes” | **Duplicata evitada** | F12 evolui a tela existente com adapter de `etl_failure_ack`. |
| Fila durável de envio | **Ausente** (inbox e log de e-mail não são outbox) | F9. |

## 8. Gates externos e decisões em aberto

O usuário aprovou todas as fases em 13/10/2026. Modelos, Warning e contratos passam por revisão técnica do Codex antes de DDL ou ativação, sem nova confirmação pessoal. Permanecem gates externos reais: Microsoft/tenant, destinatários de teste e acessos autorizados (backlog, DataStage, públicos).

| Gate | Bloqueia | Não bloqueia | Responsável |
|---|---|---|---|
| G-BACKLOG: leitura autorizada do backlog canônico | Fechamento completo da conciliação F0 | F1, F2 e demais fases técnicas | A confirmar (Codex coordena o pedido) |
| G-MICROSOFT: tenant, app/bot, permissões mínimas, instalação, destinatário de teste | F11 e parte de F23 | E-mail, canal Teams, Malha | A confirmar |
| Fonte confiável de Sucesso/Warning/Falha e geração de ciclo | Emissão de eventos F7 | F1–F6, F14–F15 | Claude levanta; Codex revisa tecnicamente antes de ativar |
| Destinos de teste autorizados | Envio real em F10/F23 | Mocks e dry-run | A confirmar |
| Três públicos e DataStage real | F6, F23 | Fases técnicas | A confirmar |
| Modelos de Malha versionada, calendário e recurso | F16–F18 antes de DDL ou motor | F14, F15 | Claude propõe; Codex revisa tecnicamente antes de DDL/ativação |
| Retenção, backoff, cooldown, prioridades | F9, F12 | F7, F8 | Operação, a confirmar |

## 9. Fechamento da F0

- Matriz com fonte/SHA, estado, responsável e aceite para os 24 entregáveis: seção 3.
- Duplicatas e artefatos DS removidos classificados: seção 7.
- Status desconhecido preservado: backlog não consultado, nenhuma linha promovida sem evidência.
- Aceite documental técnico da F0 após a revisão do Codex, com **G-BACKLOG aberto**: a conciliação viva com `dbo.etl_backlog` não foi concluída e fica pendente de acesso autorizado; isso não impede F1/F2.
- Estado: documentação revisada; integração pendente. Sem migration, versão Admin, publicação ou smoke DEV, por ser fase documental.

## 10. Atualização de 13/10/2026 (após F1/F2)

As linhas da seção 3 ficam como registro da F0. Estado atual das fases seguintes:

| Fase | Estado | Fonte |
|---|---|---|
| F1 | publicado DEV (2.21.2, `develop` `f05bd4e9`, PR #505); leitura nativa de tentativas 1/2 PASS | `/root/orquestra-eoc-evidencias/f1/native-read.json` |
| F2 | publicado DEV (2.22.0, `develop` `56484d77`, PR #506, migration 170); SQL 9/9 e smoke §7 b PASS | [release notes 2.22.0](release-notes/2.22.0-pipeline-ux-descoberta.md#publicação-dev-13102026) |
| F3 | encerrada em DEV2.22.3: PR507/508/509; L1/L4 nativos próprios, paridade11/8, replay e diagnóstico, suíte7913PASS/mesmas8falhas/51skip sem regressão; cleanup confirmado. DataStage/Caixa/canais/piloto externos permanecem pendentes nas fases próprias | [Aceite F3](eoc-f3-aceite-integrado.md), [2.22.2](release-notes/2.22.2-workspace-confirmacao-execucao.md), [2.22.3](release-notes/2.22.3-workspace-diagnostico-etapa.md) |
