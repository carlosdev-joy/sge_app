# Monitoramento e execução

Complemento de13/10/2026: [notificações, alertas e tratamento operacional](notificacoes-e-alertas-comparativo.md), com configuração nas três ferramentas, regras/destinos/Alerts do Control-M e proposta para o Orquestra.

Monitorar é selecionar uma instância e explicar estado, espera, falha e possibilidade de ação. Definição publicada, corrida, etapa e tentativa precisam permanecer identificáveis.

Leia a jornada Monitor em [Informatica](../../referencias/informatica/jornadas-data-integration.md), DB-011/012 em [Databricks](../../referencias/databricks/jornadas-e-execucoes.md), Monitoring/falhas/forecast/remediação em [Control-M](../../referencias/control-m/jornadas-e-limites.md), jornadas26–38 da [matriz](../pipelines/matriz-comparativa.md) e aceites F5 na [validação](../../planejamento/preservacao-funcional-e-validacao.md).

Informatica Monitor cobre Running e All Jobs/histórico, além de My Jobs. Databricks teve corrida real e alternância Graph/Timeline/List; Repair estava visível, não foi executado. Control-M é tour guiado. Cor sozinha não explica espera; distinguir dependência, agenda, capacidade, bloqueio e erro informado pela fonte.

Perguntas para o agente: qual corrida/tentativa é o alvo? A visão histórica pode acionar a atual por engano? Retomar/pular/parar/reparar tem qual contrato? Como manter seleção e retorno?
