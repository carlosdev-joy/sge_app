> Estado consolidado em 12/10/2026: Informatica em leitura; Databricks com duas tentativas reais, a segunda Succeeded em17s, três tarefas e notebook fictício; Control-M com cinco tours guiados e nenhum motor real. Relatos de histórico vazio e acesso pendente são da rodada inicial. A expansão para Malha foi solicitada depois da SPEC Pipeline. Leia o guia do agente para distinguir evidência e proposta.

# Malha profissional: conceitos, configuração e proposta de estrutura

Data12/10/2026. Estudo de produto e proposta revisável; não implementação. Fonte atual Orquestra develop92d14d5, SPEC52c0c589; observações Informatica UI-001–021, Databricks DB-001–010 e Control-M CTM-006–008. Evidência documental é identificada nas referências abaixo. A ampliação solicitada pelo usuário abrange a Malha, antes tratada como escopo independente da SPEC Pipeline.

## Conceito canônico proposto

Malha é a composição de pipelines e suas dependências de negócio, condições de elegibilidade, agendas e políticas operacionais. Pipeline contém etapas; uma execução de malha contém instâncias de pipelines, cada uma ligada a sua versão/snapshot, execução e tentativas. Uma visão salva filtra/apresenta a malha; não muda seu contrato de execução.

Essa definição é uma proposta para o Orquestra. Os produtos usam entidades diferentes: Control-M agrupa jobs em folders/SMART folders; Databricks usa jobs com tasks; Informatica usa taskflows com tarefas. Não renomear essas entidades como equivalentes técnicos.

## O que configura a malha

| Camada | Configuração necessária na proposta | Pergunta que a interface deve responder |
|---|---|---|
| Identidade | Nome, domínio/projeto, responsável, ambiente e descrição | Quem mantém e onde opera? |
| Composição | Referência ao pipeline, versão desejada, parâmetros e contratos | Qual definição esta instância usa? |
| Dependências | Produtor, consumidor, resultado esperado e AND/OR suportado | O que libera o sucessor? |
| Correlação | Data de negócio, corrida, janela e validade do evento | O sucesso de qual dia/instância vale? |
| Agenda | Calendário, fuso, janela, exceções e política para dia não previsto | Quando é elegível e por quê? |
| Capacidade | Limite de corridas, fila, pool e eventual exclusividade | Qual recurso está impedindo a execução? |
| Políticas | Timeout, retry, atraso, falha, notificações e responsabilidade | O que acontece quando não conclui? |
| Publicação | Rascunho, validação, versão, aprovação e ativação | O que está editado versus ativo? |
| Operação | Estado, motivo de espera, corrida/tentativa e ações permitidas | O que posso fazer nesta instância? |
| Apresentação | Colunas, filtros, agrupamento, zoom/painéis e visão salva | Como acompanhar sem alterar a definição? |

Cada campo novo depende de contrato e capacidade do motor; a interface não deve oferecer política que Airflow/DataStage/adaptador atual não possa cumprir. Herança precisa mostrar valor efetivo, origem e sobrescrita. Não aplicar silenciosamente regra de folder do Control-M aos pipelines existentes.

## Semântica observada/documentada

Control-M documenta eventos como pré-requisitos, inclusive entre servidores, com correlação por data e relacionamento AND/OR. Agenda e recurso também precisam estar satisfeitos. Para o Orquestra, exigir identidade/correlação explícita evita que um sucesso antigo libere uma corrida nova. [Events](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Events.htm)

Calendários Control-M podem ser regulares, periódicos ou baseados em regras. Isso fundamenta explorar calendário reutilizável e preview de datas elegíveis, além da agenda simples; esses recursos adicionais ainda precisam de contrato próprio. [Calendars](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Calendars.htm)

Lock Resources compartilhados/exclusivos e Resource Pools quantitativos resolvem problemas diferentes: exclusão mútua versus capacidade. Propor diagnóstico que identifique quem ocupa o recurso e o motivo da espera; não confundir lock de execução com bloqueio de edição. [Locks](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Lock_Resources.htm), [Pools](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Resource_Pools.htm)

Viewpoint é uma visão de monitoramento filtrada, com opções públicas/privadas e acesso a dados históricos. No Orquestra, uma visão pessoal não deve alterar dependências, agenda, versão ou permissões. [Viewpoints](https://documents.bmc.com/supportu/controlm-saas/en-US/Documentation/Viewpoints.htm)

O tour Reference folder mostra reutilização com variáveis por região e instâncias com logs/output próprios. Isso sustenta estudar referências parametrizadas, mas não prova como o motor Orquestra resolverá versões ou idempotência. CTM-008 é tour guiado.

## Estrutura de experiência proposta

1. Catálogo de malhas: pesquisa, domínio, responsável, ambiente, estado de publicação e saúde operacional, com entrada clara na definição ou na execução.
2. Workspace de definição: visão geral, configuração, montagem de pipelines, validação e versões. Reutilizar padrões do Pipeline sem misturar etapas internas com relações entre pipelines.
3. Operação da malha: selecionar data de negócio e corrida, alternar mapa/lista/timeline quando suportado, investigar bloqueios e abrir o pipeline mantendo retorno à malha.
4. Catálogos compartilhados: calendários, recursos, conexões por referência e templates, somente para contratos aprovados.
5. Governança: papéis de autor/aprovador/operador, histórico de alterações e ações com alvo exato. Layout e filtros pessoais separados da definição.

O mapa deve suportar agrupamento e expansão progressiva. Cor acompanha texto/ícone; nenhuma causa de espera é inferida apenas da cor. Um painel de bloqueios apresenta condição, estado esperado/atual, origem, data, recurso/ocupante quando disponível e ação permitida.

## Exemplo de negócio

Fechamento diário depende de Carga de Pedidos E Carga de Pagamentos para a mesma data de negócio. Conciliação espera ambas, a janela permitida e uma vaga no pool do banco. Publicação espera a conciliação bem-sucedida. Atraso gera risco de prazo; falha permite recuperação conforme política. Reprocessar ontem não libera automaticamente o fechamento de hoje.

## Validação obrigatória antes da reestruturação

| Cenário | Resultado esperado |
|---|---|
| Duas corridas simultâneas | Eventos e tentativas não se misturam |
| Sucesso da data anterior | Não libera sucessor do dia atual sem política explícita |
| Predecessor fora do calendário | Explicação e regra definida; não ignorar dependência silenciosamente |
| Pool esgotado | Espera por capacidade distinta de espera por dependência |
| Falha e retry | Mesma corrida com tentativa nova e rastreabilidade |
| Recuperação parcial | Mostrar quais etapas/pipelines serão repetidos e efeitos possíveis |
| Mudança publicada durante corrida | Corrida preserva snapshot; nova versão não altera o passado |
| Operação em modo histórico | Sem ações que atinjam a corrida atual por engano |
| Visão salva | Preferência persiste sem modificar payload de execução |
| Adaptador sem recurso | Controle indisponível com explicação, sem falsa promessa |

## Sequência de entrega recomendada

Primeiro, concluir os aceites atuais Pipeline e mapear contratos reais de Malha. Depois, entregar catálogo/workspace consistente e operação contextual. Calendários avançados, recursos globais, referências versionadas, SLA e forecast seguem incrementos independentes com validação do motor. Por último, ampliar personalização e automação assistida. A reestruturação profissional depende de semântica e operação confiáveis, além do desenho visual.

## Limites da investigação

Control-M: três tours percorridos, sem motor real disponível. Databricks: primeira tentativa real terminou Failed/RunExecutionError na lista e Skipped no detalhe; sem causa técnica conclusiva. Criado notebook ORQ_UX_FIXTURE com dois registros Python fictícios em memória e adicionado validar_fixture como terceira tarefa, ligado ao ramo verdadeiro; segunda tentativa iniciada para verificar operação. Sem agenda, integração externa, tabelas corporativas ou alteração de permissões. O resultado será registrado no documento10.

SLA/forecast e publicação/governança são requisitos candidatos, não capacidades verificadas do código atual ou dos tours examinados. Não houve execução de DEV Orquestra, medição de desempenho ou alteração do seu código.


## Atualização dos ensaios e prevenção

DB-012 concluiu Succeeded em17s e exibiu a saída total30 da fixture; Graph/Timeline/List inspecionados. O sucesso após adicionar notebook é observação, não prova causal da falha anterior. Repair não ensaiado.

CTM-009 Forecast e CTM-010 Self-Healing foram percorridos. A proposta inclui preview de agenda, explicação Why, simulação what-if, caminho crítico e recuperação com limite/escalonamento como incrementos futuros. Não implementar forecast estatístico ou remediação apenas porque um tour exibe essas funções; exigir contratos, dados, autorização operacional e critérios próprios.
