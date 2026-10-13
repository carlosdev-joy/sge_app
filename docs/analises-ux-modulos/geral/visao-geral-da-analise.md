> Estado consolidado em 12/10/2026: Informatica em leitura; Databricks com duas tentativas reais, a segunda Succeeded em17s, três tarefas e notebook fictício; Control-M com cinco tours guiados e nenhum motor real. Relatos de histórico vazio e acesso pendente são da rodada inicial. A expansão para Malha foi solicitada depois da SPEC Pipeline. Leia o guia do agente para distinguir evidência e proposta.

# Referências de UX para o Orquestra

Data: 12/10/2026, America/Sao_Paulo. Estado: **Informatica Data Integration e autoria demonstrativa Databricks documentados; Databricks executado com fixture fictícia; cinco tours Control-M observados; proposta premium revisável**.

## Resumo executivo

A evolução deve continuar sobre a base React/.NET/FastAPI existente. O `develop` analisado é `92d14d596c95212d10bd30c3085edde4ce7c6b83`; a referência documental é `52c0c589a3cf8f3dc5d7ee7c110a85416fd8fd85`. A revisão documental não foi confundida com a implementação atual.

O código atual já contém cinco destinos do Pipeline, configuração única, inspector dos onze tipos, edição compartilhada por lease/fence, canvas com arraste/Delete e investigação por corrida/tentativa/log. Essas capacidades exigem preservação e aceite integrado, não uma segunda implementação. A lacuna mais objetiva é F2: a lista ainda consulta `/pipelines`, sem o índice unificado de rascunhos/publicados/edição previsto na SPEC.

No Informatica foram percorridas jornadas de leitura do catálogo, taskflow demonstrativo, propriedades, dependências, Mapping Task e Monitor do Data Integration. A referência reforça três princípios: encontrar o objeto antes de editar; configurar no contexto sem perder o desenho; investigar uma instância de execução sem confundi-la com a definição. O painel inferior do Informatica não deve ser copiado automaticamente: o contrato do Orquestra prevê inspector lateral e canvas dominante. A experiência estreita observada no Informatica é um limite a superar.

O usuário acrescentou uma rodada prática com Databricks e Control-M e um glossário antes do fechamento da estrutura customizável premium. A sessão Databricks Free Edition foi observada e, com autorização específica, recebeu o job ORQ_UX_DEMO com duas tarefas fictícias salvas, inicialmente sem execução; depois ampliado e executado conforme DB-011/012. Sem agenda ou dados externos. Control-M possui documentação e observação de tours guiados CTM-006–CTM-008. A proposta fica revisável; não há declaração de paridade total nem de escopo premium fechado.

## Cinco melhorias de maior impacto

1. **Descoberta unificada de rascunhos — UX-01/F2.** Criar, sair e reencontrar um draft sem publicar uma DAG; uma linha por pipeline com flags coexistentes, filtros e paginação no servidor. Resolve uma lacuna comprovada no código.
2. **Entrada única e retorno contextual — UX-02/F2.** Abrir sempre o workspace autorizado, manter filtros/paginação da lista e os aliases operacionais. Não reintroduzir Etapas como editor concorrente.
3. **Aceite da sessão de edição — UX-03/F3.** Confirmar em duas sessões que Montagem↔Configuração conserva edição, mesma posse e proteção contra revisão obsoleta. Reutilizar o contexto já implementado.
4. **Investigação confiável — UX-07/F5.** Fechar o smoke da corrida exata, snapshot, tentativa/log e pausa/liberação/retry com fixture própria. Ações e estados não podem depender de rótulos ou do desenho atual do rascunho.
5. **Canvas útil e operação por teclado — UX-04/05/06/F4.** Validar espaço, seleção, localizador, diagnóstico, foco e painéis nas larguras contratadas, com os onze formulários completos. Refinamento dirigido por evidência, preservando a implementação atual.

Os critérios, esforço e dependências estão em [05-backlog-e-criterios-de-aceite.md](../planejamento/backlog-e-criterios-de-aceite.md). Esses identificadores são locais desta proposta; não foram criados itens no backlog vivo.

## Cobertura e limitações

- **Observação direta:** Data Integration e Monitor restrito às execuções CDI, via navegador autenticado autorizado pelo usuário. Nenhum objeto foi criado, salvo, publicado, executado, excluído ou alterado. Run/Resume/Skip/Stop/Download Log e testes de conexão não foram acionados.
- **REA:** instalação e registro disponíveis, mas ferramentas MCP ausentes nesta conversa; `list-browser-targets` em `127.0.0.1:19222` retornou `endpoint_unreachable`. A observação foi feita pela conexão de navegador disponível. IDs UI são registros desta auditoria, **não** Evidence IDs do REA.
- **DEV:** fonte de `origin/develop` acessível; o SHA servido no ambiente DEV não foi confirmado por saúde/runtime nesta rodada. Não foram reexecutadas suítes, migrations, motor ou integrações externas.
- **Informatica:** não foram ensaiados save/publicação/execução, concorrência, versionamento, logs, valores de parâmetros ou transições operacionais. Agenda completa, erro/validação real e estados de acesso negado permanecem lacunas. Não foram coletados scripts, credenciais, cookies, HAR, cabeçalhos ou inventário da organização.
- **Databricks:** sessão Free Edition, catálogo, criação autorizada, tarefas/dependência, diálogo de agenda cancelado e colunas customizáveis observados. Duas tentativas reais: primeira Failed/RunExecutionError, segunda Succeeded em17s com saída fictícia; repair e governança premium não ensaiados. **Control-M:** cinco tours guiados percorridos, sem motor real. Acessos e roteiro em [08-validacao-databricks-control-m.md](../referencias/roteiro-comparativo.md).

## Ordem recomendada

1. Reconfirmar o SHA servido no DEV e fechar o smoke pendente da pausa/corrida exata F5; isso reduz risco operacional antes de ampliar o piloto.
2. Implementar a lacuna F2 — índice unificado e entrada/retomada — sobre o `develop` vigente, com contrato/RBAC e testes de collation, paginação e concorrência.
3. Concluir aceites F3/F4/F5 e paridade dos tipos/agendas. Não substituir controles existentes por formulários ilustrativos.
4. Fazer a rodada prática Databricks e Control-M com o mesmo roteiro, separando demo, trial e operação real.
5. Consolidar decisões de customização, escopo e rollout com três públicos; F6 continua sendo aceite de jornada, não um redesenho dos motores.

## Documentos

| Arquivo | Conteúdo |
|---|---|
| [01-inventario-e-cobertura.md](inventario-e-cobertura.md) | Fontes, identidade, cobertura A–G e lacunas |
| [02-jornadas-informatica.md](../referencias/informatica/jornadas-data-integration.md) | Percursos, estados, feedback e limites observados |
| [03-matriz-comparativa.md](../modulos/pipelines/matriz-comparativa.md) | Comportamentos, implementação atual, SPEC e propostas |
| [04-proposta-ux-orquestra.md](../modulos/pipelines/proposta-ux.md) | Arquitetura de informação, composição e reutilização |
| [05-backlog-e-criterios-de-aceite.md](../planejamento/backlog-e-criterios-de-aceite.md) | Itens revisáveis, dependências e aceites |
| [06-preservacao-funcional-e-validacao.md](../planejamento/preservacao-funcional-e-validacao.md) | Paridade, regressões e plano de validação real |
| [08-validacao-databricks-control-m.md](../referencias/roteiro-comparativo.md) | Acessos oficiais e roteiro comum de validação |
| [09-glossario-e-nomenclatura.md](glossario-e-nomenclatura.md) | Termos de mercado, diferenças semânticas e linguagem proposta |
| [10-jornadas-databricks.md](../referencias/databricks/jornadas-e-execucoes.md) | Observação prática da Free Edition e demonstração autorizada |
| [11-acesso-e-jornadas-control-m.md](../referencias/control-m/jornadas-e-limites.md) | Entrada atual dos tours, formulário e limites da cobertura |
| [evidencias/registro-ui.md](../evidencias/registro-ui.md) | Evidências textuais sanitizadas e imagens da demonstração Databricks |
| [evidencias/fontes-dev.md](../evidencias/fontes-dev.md) | Auditoria de código com arquivo/linha |
| [evidencias/fontes-documentais.md](../evidencias/fontes-documentais.md) | Links específicos e limites das fontes oficiais |
| [evidencias/manifesto-fontes-orquestra.md](../evidencias/manifesto-fontes-orquestra.md) | Documentos/protótipo conferidos e ausências |

## Passagem para implementação e revisão

Claude deve partir do `develop` atual no momento da implementação, conferir instruções locais e reconciliar UX-01…UX-12 com `dbo.etl_backlog`. Não reservar números de migration nem renumerar F1–F6/F7A–F9. Codex fará revisão independente de contrato, preservação, segurança, estados e evidências. Esta entrega não modifica código, não abre PR e não autoriza promoção para produção.



## Atualização da cobertura e escopo

O usuário autorizou execução demonstrativa e aprofundamento da Malha. Databricks DB-011/012 contém tentativas reais, inclusive Succeeded em17s e saída fictícia validada; a demonstração agora tem três tarefas e um notebook. Control-M CTM-006–010 cobre cinco tours guiados (montagem, falhas, referência, forecast e remediação), sem motor real. Esses registros posteriores substituem pendências de acesso/execução apresentadas nas rodadas iniciais, mas não certificam repair, governança ou desempenho empresarial.

A nova proposta está em [12-malha-conceitos-e-reestruturacao.md](../modulos/malhas/conceitos-e-reestruturacao.md). Essa ampliação não altera retroativamente a SPEC Pipeline. Nenhum código Orquestra foi modificado.
