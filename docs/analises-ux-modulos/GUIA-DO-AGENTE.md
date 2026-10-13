# Guia de leitura e passagem para o agente

## Objetivo e contexto

Entender as análises de Informatica Data Integration/Monitor, Databricks e Control-M e produzir uma proposta coerente de evolução profissional/customizável do Orquestra, por módulo, preservando o que já funciona. Este pacote foi solicitado para passagem a outro agente. A existência da branch não autoriza implementar toda proposta, executar sistemas corporativos, integrar em develop ou promover para main.

Leia primeiro `CLAUDE.md`, instruções aplicáveis e memórias pertinentes do repositório. Confira o develop atual: o código auditado é92d14d5, não garantia do estado servido em DEV. A SPEC documental52c0c589 e o develop analisado são referências diferentes. Consulte os caminhos e SHAs do manifesto; não substitua a SPEC vigente pela proposta comparativa.

## Ordem sugerida

1. [Índice](README.md) e [inventário](geral/inventario-e-cobertura.md): escopo, datas, fontes e limites.
2. [Glossário](geral/glossario-e-nomenclatura.md): distinguir pipeline, etapa, job, task, taskflow, folder, malha, definição e execução.
3. Jornadas [Informatica](referencias/informatica/jornadas-data-integration.md), [Databricks](referencias/databricks/jornadas-e-execucoes.md) e [Control-M](referencias/control-m/jornadas-e-limites.md), junto ao [registro de evidências](evidencias/registro-ui.md).
4. [Pipeline](modulos/pipelines/README.md): matriz comportamento externo × código atual × SPEC × proposta.
5. [Malha](modulos/malhas/README.md): composição e semântica entre pipelines, data de negócio, recursos, recuperação e governança.
6. [Monitoramento](modulos/monitoramento/README.md), [configuração/agendas](modulos/configuracao-agendas/README.md) e [governança/personalização](modulos/governanca-personalizacao/README.md).
7. [Backlog e aceites](planejamento/backlog-e-criterios-de-aceite.md), [paridade](planejamento/preservacao-funcional-e-validacao.md) e [fontes do código](evidencias/fontes-dev.md).

## Como interpretar a evidência

| Classe | Interpretação |
|---|---|
| UI-001–021 | Observação Informatica autenticada, apenas leitura; nenhuma execução ou coleta de logs/segredos |
| DB-001–010 | Descoberta/configuração/criação demonstrativa, inicialmente sem execução |
| DB-011 | Tentativa real Failed/RunExecutionError na lista e Skipped no detalhe; causa inconclusiva |
| DB-012 | Após adicionar notebook fictício como terceira tarefa, Succeeded17s; saída total30 conferida; Graph/Timeline/List vistos |
| CTM-001–005 | Descoberta de acesso e liberação pelo usuário |
| CTM-006–010 | Cinco tours oficiais guiados; Next não executa jobs reais, transfere arquivos ou envia Slack |
| DOC-* | Documentação oficial; não prova licença, configuração ou execução no ambiente usado |
| Fonte DEV | Código em SHA específico; não é smoke de ambiente servido |
| Proposta | Decisão candidata para discussão; não capacidade implementada ou obrigação da SPEC |

O histórico vazio Databricks e o acesso pendente Control-M aparecem nos registros iniciais; são superados pelas atualizações DB-011/012 e CTM-006–010. Não atribua causalidade à adição do notebook: o sucesso posterior não determina sozinho a causa da primeira falha. Não invente resultados de repair, retry, desempenho, RBAC ou dados empresariais.

REA estava instalado, mas suas ferramentas MCP não estavam disponíveis e o endpoint dedicado recusava conexão. A observação ocorreu pela conexão de navegador disponível, autorizada pelo usuário; os IDs são deste estudo, não Evidence IDs do REA. Ghidra/Java configurados anteriormente não foram usados para estabelecer comportamento destas aplicações web.

## O que preservar e o que verificar

- Stack e motores existentes; cinco destinos do Pipeline; configuração única; onze tipos reais; oito agendas; lease/fence; canvas, formulários, identidade de corrida, snapshot, tentativa e logs.
- Entrada única e retomada; não criar editor paralelo de Etapas nem reduzir formulários reais a mockups.
- Diferenciar edição compartilhada de lock de execução, preferência pessoal de definição, dependência de asset de condição operacional e retry de corrida nova.
- F2 é lacuna objetiva de descoberta; F3/F5/F6 exigem os aceites indicados. Verificar novamente o código antes de propor reimplementação de recursos existentes.
- UX-01–12 são IDs locais deste estudo. Reconciliar com `dbo.etl_backlog` antes de cadastrar itens; o backlog vivo não foi consultado.
- Malha, calendário avançado, recursos globais, forecast/SLA, referências versionadas e monitor global são ampliação solicitada do estudo. Transformá-los em especificações próprias antes de código; não inseri-los retroativamente na SPEC Pipeline.

## Resultado esperado da sua leitura

O escopo inclui refinamento visual global, solicitado expressamente pelo usuário: premium e fácil de usar, com unificação além de Pipeline/Malha. Após o glossário, leia [direção visual](design-global/direcao-e-percepcao-visual.md), [sistema visual](design-global/sistema-visual.md), [arquitetura/adoção global](design-global/arquitetura-e-adocao-global.md) e [pranchas](design-global/pranchas/README.md). Não limitar a entrega à funcionalidade. Distinguir proposta global de interface, preservação funcional e requisito novo de motor.

Entregue uma síntese por módulo com: problema/jornada, capacidade atual com fonte, comportamento externo e confiança, proposta, contrato/capacidade do motor, riscos, dependências, preservação e critério de aceite. Marque cada item como existente, lacuna da SPEC, melhoria de clareza ou novo escopo. Depois proponha fases pequenas com ordem e decisões em aberto. A primeira entrega é leitura e reconciliação; implementação depende do processo e aprovação de especificação do repositório.

## Prompt pronto para passar ao agente

> Leia a branch docs/analises-ux-modulos-malha do repositório carlosdev-joy/sge_app. Comece por docs/analises-ux-modulos/GUIA-DO-AGENTE.md e siga a ordem indicada. Reconcilie as análises com o develop atual e a SPEC vigente. Produza uma proposta profissional por módulo (Pipeline, Malha, Monitoramento, Configuração/Agendas, Governança/Personalização), preservando contratos e recursos existentes. Inclua design premium e fácil de usar para toda a ferramenta: percepção visual, tipografia, menus, espaçamento, tipos de objeto, temas, componentes e arquitetura visual unificada. Use a pasta design-global e suas pranchas como proposta revisável. Diferencie observação real, tour guiado, documentação e inferência. Apresente lacunas, novos escopos, dependências, aceites funcionais/visuais e adoção progressiva, sem implementar ou promover alterações nesta etapa.
