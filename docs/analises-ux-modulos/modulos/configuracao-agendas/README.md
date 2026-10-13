# Configuração e agendas

Há três níveis: configuração do pipeline, propriedades da etapa e parâmetros de uma execução. Valores herdados devem indicar origem e sobrescrita; conexões são referências autorizadas, não segredos no formulário.

Leia configuração/agenda em [Informatica](../../referencias/informatica/jornadas-data-integration.md), previews de trigger/configuração em [Databricks](../../referencias/databricks/jornadas-e-execucoes.md), Planning/variáveis/calendário em [Control-M](../../referencias/control-m/jornadas-e-limites.md), [paridade atual](../../planejamento/preservacao-funcional-e-validacao.md) e [Malha](../malhas/conceitos-e-reestruturacao.md).

Preservar os oito modos de agenda existentes e seus campos. O preview Databricks foi cancelado, sem agenda salva. Calendários reutilizáveis, janela, fuso e políticas avançadas exigem contrato próprio quando não existem no código. Um preview deve explicar próximas datas elegíveis e exceções sem disparar execução.

Perguntas para o agente: valor efetivo vem de onde? O que o motor suporta? Data de negócio é distinta de horário de início? O calendário de um predecessor pode causar espera indefinida?
