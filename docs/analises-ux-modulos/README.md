# Análises de experiência e proposta profissional por módulos

Branch: `docs/analises-ux-modulos-malha`. Data: 12/10/2026, America/Sao_Paulo.
Pacote de documentação para leitura por outro agente. Não contém implementação, migration, deploy ou merge. Base do código auditado: develop `92d14d596c95212d10bd30c3085edde4ce7c6b83`; base documental Pipeline: `52c0c589a3cf8f3dc5d7ee7c110a85416fd8fd85`.

**Comece pelo [GUIA-DO-AGENTE.md](GUIA-DO-AGENTE.md).** Ele define ordem, contexto, evidência, limites e resultado esperado da leitura.

O pedido também abrange **design premium e fácil de usar em toda a ferramenta**. Leia [Design global](design-global/README.md): percepção visual, tipografia, menus, espaçamento, objetos, componentes, arquitetura e adoção progressiva. As [quatro pranchas conceituais](design-global/pranchas/README.md) ilustram Pipeline, Malha, Monitoramento e tema escuro. São propostas, sem alteração do produto.

## Módulos do Orquestra

| Módulo | Responsabilidade / leitura |
|---|---|
| [Pipeline](modulos/pipelines/README.md) | Encontrar, configurar, montar e versionar um pipeline; paridade com a implementação vigente |
| [Malha](modulos/malhas/README.md) | Compor pipelines e entender dependências, data de negócio, agendas, recursos e operação global |
| [Monitoramento e execução](modulos/monitoramento/README.md) | Corrida, snapshot, etapa, tentativa, bloqueio, histórico, diagnóstico e recuperação |
| [Configuração e agendas](modulos/configuracao-agendas/README.md) | Configuração pipeline/etapa/corrida, parâmetros, calendários e políticas |
| [Governança e personalização](modulos/governanca-personalizacao/README.md) | Autoria, publicação, papéis, rastreabilidade e preferências separadas da definição |

## Referências por produto

| Produto | Cobertura |
|---|---|
| [Informatica Data Integration e Monitor](referencias/informatica/README.md) | UI-001–021: leitura autenticada, sem mutações |
| [Databricks](referencias/databricks/README.md) | DB-001–012: autoria e execução demonstrativa real, sem dados externos |
| [Control-M](referencias/control-m/README.md) | CTM-001–010: acesso e cinco tours guiados; sem motor real |

## Material transversal

- [Detalhamento de notificações e alertas](modulos/monitoramento/notificacoes-e-alertas-comparativo.md): falha, sucesso, aviso, gestão operacional e Control-M; pesquisa complementar em13/10/2026, sem envio real.

- [Inventário e cobertura](geral/inventario-e-cobertura.md), [glossário](geral/glossario-e-nomenclatura.md) e [visão geral da análise](geral/visao-geral-da-analise.md).
- [Backlog proposto e aceites](planejamento/backlog-e-criterios-de-aceite.md) e [preservação/validação](planejamento/preservacao-funcional-e-validacao.md).
- [Registro das observações](evidencias/registro-ui.md), [auditoria do código](evidencias/fontes-dev.md), [fontes oficiais](evidencias/fontes-documentais.md), [manifesto das fontes Orquestra](evidencias/manifesto-fontes-orquestra.md).
- [Manifesto SHA-256](evidencias/manifesto-sha256.json) e [mapa da reorganização](geral/mapa-documentos-originais.md).

Os documentos detalhados mantêm o registro cronológico. Estado atual: primeira execução Databricks Failed/RunExecutionError com tarefas Skipped; segunda Succeeded em17s com fixture em memória (dois registros, total30). Control-M: Build a workflow25/25, Error handling15/15, Reference folder13/13, Forecast13/13 e Self-Healing16/16. Proposta premium revisável; repair real, carga e governança empresarial não certificados.
