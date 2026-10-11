# Matriz de preservação funcional — Pipeline ORQUESTRA

Data: 11/10/2026. Fonte conferida: `develop` no commit `df1a81caa3ef5400877bf3ab2f798011552143b2`.

Decisões do usuário: Montagem e Execução são abas principais distintas. Histórico, tentativas e logs pertencem à Execução. Reduzir informação simultânea sem remover funcionalidades existentes. Este inventário é uma revisão do código, não uma certificação de funcionamento das integrações.

## Navegação e responsabilidade

`Visão geral | Montagem | Execução | Configuração | Versões`

Montagem e Execução reutilizam a representação do grafo, com responsabilidades distintas. Não haverá um segundo seletor Montagem/Execução abaixo das abas. Histórico abre sob demanda e retorna à corrida selecionada no canvas. Logs ficam no painel da etapa/tentativa, com opção de ampliar. A tabela operacional é uma alternativa ao grafo, preservando corrida e seleção.

Visão geral resume; Configuração edita dados do pipeline; Montagem edita dados da etapa. Não duplicar formulários. As funções globais de outros módulos não são eliminadas por esta reorganização.

## Inventário dos tipos de etapa

Fonte: [workspaceCatalog.ts](https://github.com/carlosdev-joy/sge_app/blob/df1a81caa3ef5400877bf3ab2f798011552143b2/ui-react/src/components/workspace/workspaceCatalog.ts), `SharedJobConfiguration`, `JobTypeFields`, `SpecializedConfiguration` e painéis especializados.

| Tipo existente | Configuração a preservar | Novo acesso | Protótipo atual |
|---|---|---|---|
| DataStage | Job, conexão SSH, campos e parâmetros DataStage, importação de parâmetros declarados, vínculos e lineage | Montagem → etapa → Configuração / Parâmetros / Lineage | Adição e campos principais; catálogo/importação/lineage pendentes |
| Python | SSH, interpretador, arquivo existente, módulo, código inline e opções de arquivo de destino; vínculos de parâmetros | Montagem → etapa → Configuração; editor ampliável | Adição, modo e recurso ilustrativo; formulários condicionais completos e execução remota pendentes |
| Shell | Comando e conexão SSH, parâmetros e políticas atuais | Montagem → etapa → Configuração | Adição e campos principais |
| Stored Proc | Procedure, conexão MSSQL, banco e parâmetros nome/tipo/valor | Montagem → etapa → Configuração / Parâmetros | Adição e campos principais; editor completo pendente |
| HTTP | URL/comando e todas as opções efetivamente suportadas pelo contrato atual | Montagem → etapa → Configuração | Adição e URL; não inventar novos métodos/auth |
| SQL | Consulta, conexão, banco, política falhar/publicar nulo e prévia autorizada | Montagem → etapa → Configuração | Adição, campos principais; prévia remota pendente |
| Decisão | Condição, origens suportadas, ramos Sim/Não, Switch, casos, ordem, saída padrão e simulação de ramo | Montagem → etapa → Condição / Saídas | Adição e indicação de modo; execução de condições e edição de ramos pendentes |
| Aguarde | Todas com sucesso/todas terminarem; conectar pontas soltas sem criar ciclo | Montagem → etapa → Liberação / Dependências | Adição e política ilustrativa; sem semântica de liberação especializada no simulador |
| Valida Arquivo | Configuração inteira, conexões, catálogo de diretórios e prévia de validação | Montagem → etapa → Validação | Adição e arquivo principal; regras e prévia completas pendentes |
| Notificação | Grupo Teams, template e mensagem | Montagem → etapa → Comunicação | Adição e campos; catálogo e envio pendentes |
| E-mail | Modelo ou corpo livre permitido; HTML, assunto, destinatários, herança do pipeline, placeholders, anexo autorizado e prévia | Montagem → etapa → Comunicação | Adição e campos principais; políticas, placeholders, catálogo, prévia e envio pendentes |

As categorias Extração, Transformação, Qualidade e Entrega da primeira demonstração não substituem estes 11 tipos. Podem futuramente ser templates sobre componentes existentes, mediante especificação própria. O simulador é genérico: não interpreta SQL, Python, Switch, e-mail ou política de Aguarde.

## Configuração do pipeline

Fonte: [WorkspacePipelineFields.tsx](https://github.com/carlosdev-joy/sge_app/blob/df1a81caa3ef5400877bf3ab2f798011552143b2/ui-react/src/components/workspace/WorkspacePipelineFields.tsx), `WorkspaceDraftTools`, `WorkspaceParameters`, `pipelineUtils`.

| Grupo/capacidade existente | Destino proposto | Evidência e aceite de preservação |
|---|---|---|
| Projeto e domínio; nome/identificação e descrição | Configuração → Identificação | Reutilizar catálogo existente; valores legados não disponíveis no catálogo permanecem visíveis e intactos |
| Tags, criticidade, ambiente/destino e SLA | Identificação e Políticas de execução | Preservar chaves, nulls, regras e distinção ambiente da aplicação/destino |
| Ativo e motivo de inativação | Políticas de execução | Publicado inativo exige motivo conforme regra atual; não confundir com pausa do motor |
| Diário, semanal, mensal, quinzenal | Agenda e dependências | Preservar hora e dia da semana/mês; limites reais, inclusive 1–13 na quinzenal |
| A cada N horas | Agenda e dependências | Intervalo, hora inicial/final e minuto; conferir cron/janela gerados |
| Horários específicos | Agenda e dependências | Lista de horários e dias da semana; preservar normalização/validação atual |
| Dia + Hora Específico | Agenda e dependências | Editor de até 5 dias, dias 1–28 e vários horários; não substituir no produto por um texto livre |
| Sob demanda | Agenda e dependências | Não cria agenda automática; execução manual preservada |
| Dias úteis e calendário de feriados | Agenda e dependências | Catálogo real e resposta de indisponibilidade; valor legado preservado |
| Data inicial da DAG e virada ODATE | Agenda e dependências | Mesma data lógica/operacional e regras de virada do contrato atual |
| Predecessores e janelas de dependência | Agenda e dependências | Seletor real, não iniciar antes e hora limite de aviso; preservar autoria das dependências geridas pela malha |
| Concorrência, retries, intervalo e pool | Políticas de execução | Mesmas chaves e limites; pool não equivale à capacidade global de 50 execuções |
| Liberar dependentes/notificar sem movimento | Políticas de execução | Falha técnica continua bloqueando; destino pulado não vira sucesso fabricado |
| Notificar início, conclusão e erro; destinatários | Notificações | Mesmas flags e herança de destinatários de e-mail; validações completas preservadas |
| Runbook Markdown | Documentação | Consulta e sustentação acessam sem entrar em edição |
| Parâmetros DataStage/Orquestra, defaults e vínculo por etapa | Parâmetros; etapa → Parâmetros | Tipo, origem, destino, descrição, precedência, data de referência e prévias preservados |
| Importar parâmetros, catálogo e Maestro | Parâmetros → ações contextuais | Reaproveitar componentes; aplicar proposta somente ao rascunho autorizado |
| Adicionar/alterar/remover valor protegido | Parâmetros → ação específica | Referências protegidas e validações existentes; nenhum segredo no protótipo, URL ou log |
| Configuração completa JSON | Configuração → Avançado | Preservar campos desconhecidos, não recriar o payload apenas com campos visíveis |

No protótipo as oito modalidades e principais campos de governança estão representados. Editor estruturado de dia+hora, seleção real de predecessores, importação, parâmetros completos e valores protegidos continuam pendentes. Campo ilustrativo não conta como integração entregue.

## Montagem, sessão, versões e operação

| Capacidade encontrada no código | Novo acesso | Regra/aceite |
|---|---|---|
| Iniciar, encerrar e assumir edição administrativamente | Contexto do rascunho / Mais | Lease/fence e RBAC do servidor; transferência não autoriza save da sessão anterior |
| Salvar, recarregar e descartar rascunho | Ações do rascunho | Mesma revisão entre Montagem/Configuração; confirmação para descarte; erro não perde alterações |
| Criar rascunho do publicado | Entrada em Montagem | Preservar draft/published e catálogo; não criar uma DAG só para tornar o rascunho localizável |
| Adicionar, mover e conectar etapas; remover aresta/nó | Canvas Montagem | 11 tipos, identificação única, preservação de payload e confirmações atuais |
| Renomear identificador e nome de exibição | Inspector → Identificação | Atualizar referências e ramos conforme contrato; não confundir nome amigável e ID técnico |
| Localizar etapa e organizar desenho | Ferramentas do canvas | Alternativa acessível ao drag; organizar só muda posições |
| Importar etapas e ordem executável | Montagem → Mais | Importação/ordem atuais; prioridade de execução não se confunde com posições do desenho |
| Validação da revisão e diagnóstico por etapa/campo | Resumo inferior e Validar | Revisão salva, guardas atuais, clique abre destino canônico; regras completas dos 11 tipos |
| Solicitar, acompanhar e retomar publicação | Publicar / Versões | Pendente → projetado → gerando → publicado/erro; só afirmar publicada após confirmação real |
| Histórico, comparação entre duas versões e restauração de versão publicada | Versões | Preservar seletores anterior/seguinte, diff de definição/layout e restrição de restauração; comparação rascunho × versão do protótipo é adicional e não substitui comparação entre versões |
| Solicitar execução com conf JSON/data lógica | Execução → Executar → confirmação | Cria solicitação Airflow; DAG pausada pode aguardar. Recebido, em fila e executando são diferentes |
| Data operacional, escolha da corrida e retorno à malha | Execução → seleção / Histórico | Preservar `run_id`, data e origem da navegação; corrida selecionada identifica snapshot ou limitações da fonte |
| Estados, espera, duração, origem e frescor | Canvas e resumo da execução | Sem telemetria não vira sucesso; animação acompanha estado confirmado |
| Tabela de etapas e busca | Execução → vista Tabela | Alternativa ao gráfico, mesma corrida/seleção, sem duplicar painel completo abaixo dele |
| Tentativas e logs Airflow | Inspector → Tentativas / Logs | Identidade pipeline/corrida/task/tentativa; erros e conteúdo vazio distintos; logs escapados |
| Reprocessamento de etapa/cascata e parâmetros | Inspector operacional → Reprocessar | Reutilizar ModalRerunEtapa e guardas; não permitir corrida antiga/versão incompatível onde o backend proíbe |
| Pausas de etapas e gerenciamento | Inspector operacional → Pausa | Reutilizar ModalPausaEtapa e guardas; não inventar cancelamento geral do pipeline |
| Capacidades por sessão/perfil | Ações e leitura conforme servidor | Desenvolvimento, Consulta e Sustentação são experiências; mudar seletor não concede permissão |

Fontes: `WorkspaceEditor.tsx`, `WorkspaceFlowTools.tsx`, `NodeProperties.tsx`, `WorkspacePublication.tsx`, `WorkspaceVersions.tsx`, `WorkspaceOperations.tsx`, `WorkspaceRunProperties.tsx`, `FluxoEditor.tsx` e `useWorkspaceCapabilities.ts`.

## Compatibilidade de acesso

Rotas atuais `fluxo`, `execucoes`, `logs`, `parametros` e `ferramentas` devem ter tratamento explícito. Proposta: `fluxo` abre Montagem; `execucoes` e `logs` abrem Execução, restaurando corrida/etapa/tentativa; `parametros` abre Configuração/Parâmetros; `ferramentas` resolve o destino contextual correspondente.

Preservar parâmetros de experiência, fonte, data, corrida, etapa, tentativa e retorno à malha. Não interpretar uma URL de rascunho como fonte de execução. Os aliases reais e o formato da tentativa serão definidos contra `App.tsx`/`workspaceNavigation` antes da alteração de rotas. Não publicar redirect presumido sem esse teste.

## Condições para substituir as telas no DEV

1. Para cada linha: registrar componente/campo/chave do payload, permissão, novo controle, endpoint, teste/evidência e estado. Nenhuma linha pode desaparecer como consequência da redução de abas.
2. Comparar fixtures de cada um dos 11 tipos antes/depois: valores, defaults, campos desconhecidos, ramos, arestas e referências protegidas permanecem equivalentes quando não editados.
3. Reexecutar testes existentes adequados a cada mudança; validar as oito agendas com cron/dias/ODATE equivalentes e round-trip dos catálogos.
4. Percorrer criar → montar → configurar → salvar → validar → publicar → confirmar → executar → investigar → reprocessar/pausar, com os três públicos e capacidades reais. Registrar operações externas não testadas como pendências.
5. Validar sessão entre abas e duas sessões concorrentes: conflito, expiração de posse e reconexão não sobrescrevem trabalho.
6. Testar links antigos e retorno à malha. Corrida histórica não adota silenciosamente o desenho do rascunho.
7. Não substituir a tela anterior enquanto houver capacidade existente sem destino implementado/testado. Manter piloto/rollback conforme flags atuais até paridade demonstrada.

**Estado desta entrega:** protótipo e especificação revistos; paridade funcional de produção ainda não certificada. A primeira aprovação é de organização e UX. Adaptação React/.NET e validação integrada são entregas subsequentes do DEV.

### Regra para campos adicionais da proposta
Responsável, fuso selecionável, timeout global ou outros controles que não correspondam a um campo comprovado no contrato atual devem ser classificados como proposta e especificados separadamente. Não mapear por semelhança de rótulo nem enviar chave nova silenciosamente. Reutilizar formas, limites e catálogos reais na implementação.
