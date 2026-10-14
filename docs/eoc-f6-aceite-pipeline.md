# EOC-F6 — Aceite técnico do Pipeline e preparação do piloto

Referências: [SPEC consolidada EOC-F6](spec-experiencia-operacao-consolidada.md#eoc-f6--aceite-f6-pipeline-e-rollout), [SPEC original F6](spec-ux-pipeline-profissional.md#f6--aceite-da-jornada-e-preparação-das-próximas-telas), [contrato visual](design/pipeline-experiencia.md), [preservação funcional](matriz-paridade-pipeline.md) e [coorte do workspace](dev-workspace-dotnet.md).

## Estado e escopo

Entrega técnica 2.24.1 sobre `develop` `98a772934dcd742b34d96f5a022478db3cbbf33d` (2.24.0). O piloto com pessoas reais continua pendente. A autorização de 14/10/2026 permite criar os três perfis em DEV e testar seus acessos; testes com identidades descartáveis são prova técnica, não sessões realizadas por três usuários humanos. EOC-F7 depende de F0/F1 e pode avançar enquanto esse aceite externo é organizado.

Os detalhes de logs entram no bundle apenas ao abrir. A espera usa o modal da aplicação com Cancelar/Esc; cancelar impede abertura tardia. Uma falha ao buscar o módulo mostra mensagem local e Fechar, mantendo Dashboard e shell. Como React.lazy conserva a rejeição, a mensagem orienta recarregar a página para tentar novamente; não oferece um retry que reutilizaria a mesma falha.

No detalhe, Reexecutar e Reconhecer falha verificam `acao_executar`, em lugar de deduzir acesso pelo nome do perfil. O servidor continua sendo a autoridade. Autenticação, endpoints, banco de execução, DAGs e RBAC existentes não foram modificados.

## Três perfis preparados em DEV

Criados pela API administrativa existente, sem sobrescrever perfis existentes nem conceder permissões extras por usuário. Localização: **Admin → Acesso → Perfis e Permissões**. O administrador pode associá-los a usuários reais para o piloto. Eles não contêm senhas nem criam acesso de administrador.

| Perfil | Acessos comuns | Ações adicionais | Ações recusadas |
|---|---|---|---|
| `eoc_dev_sem_admin` | Dashboard, Pipelines, Fluxo de pipelines, Logs | Editar e publicar | Executar e administrar |
| `eoc_consulta` | Os mesmos quatro acessos | Nenhuma | Editar, publicar, executar e administrar |
| `eoc_sustentacao` | Os mesmos quatro acessos | Executar, reprocessar, pausar/reconhecer conforme regras do recurso | Editar, publicar e administrar |

A experiência selecionada na tela não muda a permissão. As contas descartáveis de teste usaram Airflow Viewer e login real, sem credenciais persistidas nos artefatos. Foram removidas com suas sessões ao concluir. O rascunho próprio criado e salvo pelo desenvolvedor sem admin foi descartado; não houve publicação, nova execução ou comunicação de negócio nessa rodada. Os três perfis permanecem disponíveis.

O teste de visibilidade falha na base2.24.0 (botão de reexecução aparecia para o desenvolvedor sem operação) e passa no candidato. Dezesseis cenários sintéticos cobrem modais, cancelamento, falha e os três perfis, incluindo payload sem lista de permissões. Provas: capabilities condizem com cada função; todos recebem 403 no Admin; Consulta/Sustentação recebem 403 ao editar/publicar; Desenvolvimento/Consulta recebem 403 ao executar. Todos consultam Montagem e Execução da fixture própria arquivada. No navegador, os controles operacionais do detalhe aparecem somente para Sustentação. Capacidade de publicar/operar foi conferida; publicação e execução positivas não foram repetidas com essas contas. O percurso real SQL/Shell da EOC-F3 permanece a evidência desses gestos, com sua identidade e fonte originais.

## Desempenho e método

Ambiente: Chromium headless, build Vite de produção, viewport 1440×1000, sem throttling, cache e service workers desabilitados; servidor compartilhado. Orçamento: soma gzip dos arquivos JS/CSS efetivamente solicitados até o canvas pronto (duas animações de frame). Compressão equivalente `gzip.compress(..., mtime=0)`, não bytes transferidos na rede. Fontes e imagens ficam fora desse orçamento específico. Montagem sintética usa 50/100/300 nós e 25 seleções via Localizar; p95 por nearest rank, até dois frames. Isso mede resposta da bancada, não INP de campo nem usabilidade humana.

| Medida | Base 2.24.0 | Candidato final | Critério |
|---|---:|---:|---|
| Montagem fria, JS+CSS gzip | 289.226 bytes | 283.380 bytes | <307.200 bytes (300 KiB) |
| Execução fria, JS+CSS gzip | 307.314 bytes | 301.676 bytes | <307.200 bytes |
| Seleção de 50 nós, p95 | 82,20 ms | 129,33 ms | Registrar separadamente |
| Seleção de 100 nós, p95 | 98,53 ms | 125,24 ms | Registrar separadamente |
| Seleção de 300 nós, p95 | 148,90 ms | 163,70 ms | <200 ms |

A base de Execução excedia o limite em 114 bytes; a carga sob demanda elimina esse excesso. Não inferir aceleração geral de interação por diferenças entre rodadas em host compartilhado. LCP e CLS estão nos artefatos como diagnósticos, sem alegação de Core Web Vitals de usuários reais.

Para repetir as bancadas sintéticas, usar ambiente de QA com Playwright/Chromium:

```bash
python3 scripts/medir_pipeline_f6.py --dist ui-react/dist --output /tmp/eoc-f6-performance.json
python3 scripts/verificar_logs_f6.py --dist ui-react/dist --output /tmp/eoc-f6-dashboard-logs.json
```

A API real foi medida separadamente, somente com GETs da fixture própria SQL/Shell da F3, 30 amostras por endpoint e modo. Índice filtrado por `search`, limite20. Nenhum job foi disparado. Atualização continua em **30 segundos**.

| Leitura local DEV | p95 sequencial | p95 com quatro clientes |
|---|---:|---:|
| Capabilities | 15,03 ms | 99,20 ms |
| Contexto | 18,82 ms | 93,14 ms |
| Índice filtrado | 34,48 ms | 156,31 ms |
| Execução | 544,80 ms | 378,70 ms |

O p95 sequencial de Execução supera 500 ms. Falta medir SQL/IO/plano, upstream e concorrência representativa da Caixa antes de considerar 5 segundos. A rodada inicial de API usava `name` no índice (filtro ignorado); seus números não compõem essa tabela. As medições finais de carga reutilizam a rodada de API corrigida porque o backend não mudou; não são novas medições de API. Essa limitação e o piloto estão registrados no Backlog pela migration176, sem declarar conclusão.

## Piloto com usuários reais

Cada pessoa usa sua própria identidade e o perfil correspondente; nenhum perfil admin substitui o desenvolvedor. Administrador associa perfil e solicita novo login para recarregar acessos. Usar projeto/pipelines de teste e destinos autorizados, sem executar jobs de negócio para medir navegação. Registrar versão, SHA, ambiente, papel, dispositivo, tarefa, resultado, tempo, retornos, dúvidas, ajuda e ocorrências. Não registrar senha/token/conteúdo sensível.

| Público | Jornadas essenciais | Evidência esperada |
|---|---|---|
| Desenvolvimento sem admin | Encontrar/criar pipeline; Montagem; configurar etapa; alterações entre abas/painéis; salvar; validar; publicar; consultar versão/restauração autorizada | Conclusão sem ajuda indevida; posse/sessão e confirmação respeitadas; sem perda de configuração |
| Consulta | Encontrar pipeline; distinguir publicado/rascunho; percorrer as cinco áreas disponíveis; localizar etapa; ler parâmetros e histórico | Entendimento da fonte; leitura útil; nenhuma ação mutadora acessível |
| Sustentação | Encontrar corrida; interpretar estado/tentativas; abrir log correto; investigar falha; confirmar execução/reprocesso/pausa autorizados | Identidade da corrida e etapa preservada; comunicação lida não equivale a falha resolvida; sem operação acidental |

Matriz de sessão a preencher **por pessoa**, inclusive tarefas que falharem:

| Versão/SHA · papel · viewport/tema | Tarefa | Concluiu? | Tempo | Retornos/dúvidas/ajuda | Ocorrência e evidência |
|---|---|---|---|---|---|
| Pendente | Pendente | Pendente | Pendente | Pendente | Pendente |

Repetir pontos de leitura/navegação em 1440/1280/947/390, claro/escuro, teclado e movimento reduzido; testar ausência de permissão, posse por segunda sessão, erro/timeout e confirmação de saída sem perda. As matrizes técnicas de F3/F4/F5 e os testes de F6 preparam esses casos e preservam seus limites; não preencher sucesso humano a partir delas. Encerrar UX-F6 apenas com sessões reais registradas, critérios resolvidos e aceite do responsável.

## Coorte, flags e reversão

`WORKSPACE_NAVIGATION_PILOT_USERS` é uma lista explícita de matrículas; não é um perfil nem concede autorização. Os novos perfis não foram incluídos automaticamente na coorte. Rotas diretas permitem testar suas capacidades; descoberta contextual requer inclusão explícita e atualização do serviço que carrega a configuração.

Flags de autoria/publicação/operação e navegação são distintas (`WORKSPACE_ENABLED`, `WORKSPACE_DRAFTS_ENABLED`, `WORKSPACE_PUBLICATIONS_ENABLED`, `WORKSPACE_OPERATIONS_ENABLED`). Prova offline: 29 testes de `OperationEndpointTests` passaram na imagem `orquestra-eoc-f3-replay-test:20261014t0150`; covers de coorte presente/ausente/case-insensitive, operações desabilitadas sem dispatch e permissões obrigatórias. Fonte .NET igual à F3 (`0b36d528`), sem diff até este candidato. Isso é TestServer, sem simular uma reversão real ou operação na Caixa.

Reversão da entrega visual: após conferir saúde, fonte dos ativos e erros, restaurar o dist do SHA base aprovado em uma correção para develop, com versão de correção registrada. Não apagar rascunhos, snapshots, publicações, intenções, corridas, banco ou volumes. Desabilitar o workspace não cancela jobs nem intenções persistidas. Antes de restringir funcionalidades, inventariar operações/publicações pendentes e responsáveis; decidir quais flags desligar e acompanhar sua conclusão. Retirar matrícula da coorte afeta navegação, não permissões. Reversão global de flags não foi exercitada em DEV compartilhado nesta rodada.

A implantação desta fase exige backup verificado, migration176 e dist; não exige restart de API/.NET/worker porque seus fontes/configurações não mudaram. Migrations de versão/backlog são idempotentes. Main e produção permanecem sujeitos a autorização própria; os perfis de piloto foram criados apenas no DEV, fora da migration de produto.

## Evidências e limites externos

Artefatos do root: `/root/orquestra-eoc-evidencias/f6/` — performance-before/final, native-metrics-after/final, dashboard-logs, profiles, dotnet-cohort, comparação de suite/lint, revisão independente, build e pós-deploy. Metadados resumidos e sem credenciais em [evidências F6](evidencias/eoc-f6-metricas.json). O índice SHA-256 do dist relaciona os testes ao build; o smoke pós-deploy confirma os bytes servidos.

Caixa/DataStage real continua pendente: validar conectividade/restrições, tipos reais, parâmetros protegidos, lineage, agendas, retry/log e resultado com dados e janela autorizados. Uma fixture SQL/Shell não comprova isso. Não houve envio de alertas, Teams ou e-mail de negócio nem publicação em produção.
