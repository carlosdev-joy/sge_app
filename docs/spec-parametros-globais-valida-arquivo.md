# Spec: Parâmetros de pipeline e Valida Arquivo — Orquestra

Data: 2026-09-27 · Status: aprovada; F1 mergeada; F2a #456, F2b #457 e F3 #458 abertas

Base: documento v1.1 `/dados/bi/05_spec_parametros_globais_e_valida_dataset.md`, no container `orquestra-dev-sshd-amostra`, e respostas do usuário em 27/09/2026. O documento de entrada foi preservado. Código confrontado com `origin/main` c3f2b24, atualizado nesta sessão. Decisões do usuário prevalecem sobre os exemplos da v1.1. Implementação iniciada por autorização do usuário em 27/09/2026. F1 implementada na branch `feat/parametros-globais-f1`, validada no [PR #455](https://github.com/carlosdev-joy/sge_app/pull/455), mergeado em 27/09/2026 (8cf356b). F2a implementa cadastro e prévia de importação no [PR #456](https://github.com/carlosdev-joy/sge_app/pull/456), aguardando autorização de merge; F2b ([PR #457](https://github.com/carlosdev-joy/sge_app/pull/457), aberta sobre F2a) implementa referências aos nós DataStage/Python e antecipa a fundação do snapshot exigida para retomadas. F3 implementada no [PR #458](https://github.com/carlosdev-joy/sge_app/pull/458), aberta sobre F2b; F4 implementada no PR#459; F5 implementada com validação integrada local; F6–F7 pendentes. Sem deploy nesta sessão.

## 1. Visão

Permitir que o usuário configure parâmetros reutilizáveis de pipeline e controle a execução das etapas a partir da presença e do volume de arquivos. O nó visual Valida Arquivo é genérico: não pressupõe INSERT, UPDATE, nomes de arquivos, tipo do job consumidor ou significado dos dados. O usuário escolhe as dependências no canvas e vê o impacto de cada política antes de salvar.

## 2. Escopo

**IN:**
- Passo Parâmetros Globais antes de Notificações, aproveitando o cadastro existente por pipeline. Global significa compartilhado no pipeline, não em toda a instalação.
- Importação de metadados/defaults DataStage com prévia e confirmação; parâmetros exclusivos Orquestra; compatibilidade com parâmetros existentes.
- Valor literal informado no nó ou referência a parâmetro; valor explícito no nó prevalece sobre defaults herdados.
- Integração inicial do consumo de parâmetros em DataStage, Python e Valida Arquivo.
- Valida Arquivo pode controlar TODOS os tipos atuais do canvas: datastage, shell, python, storedproc, http, decisao, notificacao, sql, aguarde e email. Controlar execução não significa adicionar interpolação de parâmetros a todo campo desses nós.
- Dataset DataStage e arquivo de texto; N entradas; políticas por entrada; opção ignorar a primeira linha de arquivos de texto; sequência ou paralelismo definidos pelo usuário.
- Edição de valores/políticas sem regenerar DAG; versão original preservada na retomada; alteração de configuração exige nova execução para surtir efeito.
- Prévia de impacto, resultado por entrada/tentativa, motivo de skip/bloqueio, conclusão sem movimento e liberação configurável de dependentes.

**OUT (explícito):**
- Inferir regras de negócio pelo nome do arquivo/job; reordenar dependências automaticamente.
- Limpar arquivos, alterar o job produtor ou validar frescor/proveniência nesta entrega. Usuário informa que a limpeza existente remove os arquivos e haverá novo arquivo no dia seguinte, vazio ou com dados. É contexto informado, não teste realizado.
- Sincronização automática de defaults DataStage, exportação de parameter files e leitura genérica de qualquer formato binário.
- Parser semântico de registros CSV multilinha nesta versão: contagem é de linhas físicas, com exclusão opcional da primeira linha. Essa limitação aparece na configuração.
- Aplicar configuração nova a uma execução em falha. Para usar a nova, preservar a falha anterior e iniciar outra execução do zero.
- Cancelamento automático de tarefas independentes já em execução ao ocorrer falha num ramo.
- Frescor, artefatos por execução e concorrência de arquivos compartilhados entram no Backlog do produto via migration idempotente, sem aplicação à produção nesta etapa.

## 3. Arquitetura proposta

### Decisões funcionais confirmadas

1. Ordem: caso imediato sequencial; o produto permite ordem escolhida pelo usuário no canvas. Não usar INS/UPD como contrato, rótulo obrigatório ou regra implícita.
2. Políticas de ausência/vazio: usuário escolhe a ação permitida e vê nós diretamente afetados, dependentes transitivos e ponto de convergência. Erro técnico (SSH, permissão, leitura, timeout ou interpretação da saída) sempre falha a validação e bloqueia seus destinos; não admite continuar, pular como se fosse ausência ou executar sem validar.
3. Sem movimento: exibir Concluído sem movimento quando os destinos controlados não executaram por falta de dados/arquivo, sem esconder trabalho executado a montante. Permitir configurar liberação dos pipelines dependentes. O histórico técnico é obrigatório, inclusive sem movimento; apenas a notificação é opcional. A UI usa “Notificar conclusão sem movimento”, sem oferecer “sem registro”.
4. Literal no nó sobrepõe defaults. O campo oferece Valor direto ou Parâmetro; não substitui indiscriminadamente todos os campos por dropdown.
5. Ignorar cabeçalho: descartar exatamente a primeira linha física antes da contagem. Arquivo vazio ou apenas com cabeçalho resulta em zero; última linha sem newline também conta. Mostrar linhas físicas e linhas consideradas. Não oferecer cabeçalho para dataset DataStage.
6. Retomada reutiliza a versão original da configuração. Editar o cadastro só afeta novas execuções. Não oferecer Revalidar com configuração atual na corrida existente.
7. Valida Arquivo governa qualquer tipo de nó suportado pelo canvas, sem adicionar dependência de DataStage a consumidores que não o utilizem.

### Parâmetros e interface

- Evoluir `etl_pipeline_param`, `api/services/job_params.py` e `dags/utils/ds_params.py`, evitando criar um segundo cadastro concorrente para os mesmos defaults.
- Distinguir procedência do parâmetro (importado DS ou próprio ORQ), destino permitido e fonte do valor (`fixo`, data, run_id). Importado não significa automaticamente enviado ao DS.
- Preservar precedência existente pipeline → etapa → override de rerun nos recursos antigos. No novo Valida Arquivo, literal local vence default do parâmetro; escolher outro diretório não reconfigura silenciosamente o job produtor/consumidor. Mostrar divergência conhecida na prévia.
- Manter segredo cifrado e mascarado, fora de legendas, XCom, prompts e logs. Usar referências de conexão para credenciais quando aplicável.
- Importação usa jobs/sequence escolhidos e nomes declarados por cada job; nunca presume que um job inventaria todo o projeto. Conflitos de tipo/default ficam visíveis; reimportação preserva customizações. Prévia funciona antes de salvar o pipeline; persistência é transacional no save.
- Alterações em `ui-react/src/components/pipelines/PipelineFormModal.tsx`, `ParametrosPipeline.tsx`, `ui-react/src/components/etapas/JobTypeFields.tsx`, `FluxoEditor.tsx` e `ui-react/src/lib/dsParams.ts`; novos helpers puros e seletor reutilizável. Usar componentes `ui/`, `apiFetch`, react-query e tokens claro/escuro existentes.
- Wizard atual: Identificação, Agendamento, Notificações, Revisão. Inserir Parâmetros Globais antes de Notificações e mover a seção existente; não inventar passo Jobs adicional.
- Prévia mostra o caminho resolvido, origem do valor e tabela de cenários: arquivo ausente, vazio, com linhas e erro técnico, com destinos liberados/pulados/bloqueados. Não mostra conteúdo do arquivo.

### Runtime e grafo

- Implementar serviço puro de normalização/decisão em `api/services/valida_arquivo.py` e equivalente testado em `dags/utils/valida_arquivo.py`; fábrica em `dags/etl_dag_factory.py`. Reusar padrões SSH de `api/services/ssh_datastage.py`, respeitando diferenças API/worker.
- Um nó visual pode gerar avaliação + guardas por destino e convergências internas. Não impor um único BranchPythonOperator quando isso violar as dependências escolhidas. Identificadores internos estáveis e sem colisões; não expor tasks técnicas como novos jobs de negócio.
- Avaliar as entradas e registrar diagnósticos antes de liberar destinos. Erro técnico sempre falha o nó e bloqueia todos os seus destinos, sem publicar sucesso nem liberar pipelines dependentes. Registrar as entradas não avaliadas como tal se a avaliação for interrompida. Política de negócio configurada como falha também mantém corrida em falha. Demais políticas preservam o efeito explícito escolhido; uma falha não cancela tasks independentes já iniciadas.
- Proposta técnica para várias entradas no mesmo destino: todas devem liberar; uma que mande pular impede execução e uma falha bloqueante prevalece. A UI mostra essa combinação; não aceitar semântica OR implícita.
- Conexões, dsenv e APT vêm da configuração autorizada, sem paths de projeto hardcoded. Separar ausência confirmada de falha técnica; contagem ilegível é desconhecida, nunca zero. Quoting, limites de caminho, timeout, tamanho de saída e comandos permitidos no servidor.
- Não inferir contagem DataStage do primeiro inteiro de uma linha contendo rows/record. Parser validado contra saídas sanitizadas da versão instalada; preservar caixa/extensão real do nome.
- Decisões do validador: liberar, pular, bloquear; resultado real do destino vem do estado da execução. Persistir mesmo se a task lançar exceção; XCom complementa o registro durável.
- Reusar `_flow_close` para telemetria, sem torná-lo exclusivamente um ramo para todos pulados. `publish_dataset` publica evento de sucesso do Airflow, não arquivo físico. Não usar ALL_DONE como atalho de sucesso.
- Separar encerramento da corrida, liberação de dependentes e notificação. Caso sem movimento não libera dependentes quando a política negar, mas deve encerrar a corrida sem deixá-la EXECUTANDO. A liberação permitida deve ser idempotente por execução.
- Criar snapshot imutável dos parâmetros e políticas desta feature antes da primeira task consumidora. Todas as tasks e retries da corrida usam a mesma revisão. Snapshot ausente em corrida antiga não deve ser reconstruído silenciosamente do cadastro atual; retornar orientação de nova execução.
- Alteração de topologia/conexão exige regeneração. Corridas em andamento devem manter contrato compatível com a revisão gerada; impedir republicação incompatível que inviabilize sua retomada, com orientação na UI. Não prometer snapshot de toda configuração preexistente do produto nesta feature.

### API e permissões

- Evoluir rotas de parâmetros em `api/routers/pipelines.py` e gravação de nós em `api/routers/jobs.py`; evitar duas famílias de endpoints CRUD para a mesma entidade.
- Prévia de importação e validação tem autorização do pipeline e da conexão; não permitir trocar conn_id para atravessar permissões.
- Serviço de leitura de execução entrega revisão, observações, políticas e impactos; ocultar segredos.
- Erros estruturados compatíveis com `apiFetch`: 422 com erros por campo, 409 para revisão concorrente/incompatibilidade e 503 nomeando migration ausente. Nenhuma gravação parcial no salvar.

## 4. Modelo de dados

Proposta de migrations; confirmar numeração na main antes de cada fase. Base atual termina em 127. Todas idempotentes, com GO, aplicadas na etapa 6c do deploy.sh.

- `128_backlog_validacao_frescor_arquivo.sql`: item no `etl_backlog`, título único, sobre garantia de arquivo da execução e concorrência. Não implementa validação de frescor.
- `129_parametros_pipeline_origem.sql`: ampliar `etl_pipeline_param` com procedência/destino e metadados de importação. Preservar `param_name VARCHAR(128) COLLATE Latin1_General_BIN2`, valor NVARCHAR(MAX) cifrado quando Encrypted, fontes/cálculos já existentes, FK e nomes por caixa exata. Tipos adicionais só com validação equivalente API/runtime.
- `130_parametros_vinculos_snapshot.sql`: referências JSON por nó, flag permanente de ativação no pipeline e snapshot Fernet por pipeline/run. Antecipado de F4 para F2b: referências não podem estrear com retomada usando valores novos.
- `131_valida_arquivo_config.sql`: `etl_valida_arquivo_no` guarda conexão, prazo, revisão BIGINT e data por nó; `etl_valida_arquivo_config` guarda pipeline/nó NVARCHAR(200), entrada estável UNIQUEIDENTIFIER (chave composta), ordem INT, tipo VARCHAR(16), param_name compatível com cadastro, diretorio_literal NVARCHAR(2000), arquivo NVARCHAR(300), alvo NVARCHAR(200), políticas VARCHAR(16) e ignorar_cabecalho BIT. Revisão é atômica para todas as entradas. Literal preenchido prevalece sobre referência; CHECKs/FKs e alvo pertencente ao mesmo pipeline; alteração de alvo, conexão ou conjunto de entradas é estrutural.
- `132_valida_arquivo_execucao.sql`: extensão do snapshot cifrado 130 para configurações e políticas; tabelas de tentativa, entradas e conclusão por pipeline/run; resultados por nó/entrada/tentativa com estado observado, contagens BIGINT anuláveis, decisão, motivo, alvo, instante e revisão. JSON validado; índices por execução/nó. Chave de run deve adotar o contrato real existente sem truncamento. Persistência idempotente por tentativa.
- `133_valida_arquivo_guardas.sql`: prova durável de decisão por task técnica/tentativa/início, origens de autorização e resultado SEM_EXECUCAO para ramos sem avaliação, sem confundir com falta de dados.
- Política de conclusão sem movimento/liberação de dependentes pertence ao pipeline e é incluída no snapshot. Histórico técnico não tem interruptor; `notificar_sem_movimento BIT` controla somente a notificação e integra o snapshot. Desligá-lo não suprime auditoria, diagnóstico nem estado da execução.
- Atualização concorrente com revisão esperada e transação; prévia não insere parâmetros nem altera configuração. Reimportação não apaga automaticamente itens ainda referenciados.

## 5. Fases

Cada fase deixa a main funcional, ganha PR própria e revisão adversarial multi-agente antes da PR. Validação obrigatória em todas: pytest completo comparado com main (zero falha nova), `npx tsc -b`, eslint por arquivo/regra/mensagem contra baseline, build e dist recompilada por último quando houver front, fontes sem NUL. Mudanças em entrada/segredo passam também por revisão de segurança. Autorização de 27/09/2026: seguir até concluir todas as fases, QA e documentação, sem nova confirmação de implementação a cada fase; deixar PRs para decisão de merge do usuário. Não há dependência Python nova prevista; se necessária, wheel offline deve entrar na mesma fase. Não ativar criação do nó na UI antes do suporte ao runtime.

### F1 — Contrato único de parâmetros
- Entregável: migration 129 e extensão compatível de modelo/API; rascunho do backlog 128 incluído na PR documental ou nesta fase.
- Aceite: parâmetros legados não mudam de significado; literal vence default; ORQ não vaza para DS; Encrypted não aparece em leitura; migration roda duas vezes; ausência de migration degrada com mensagem.
- Validação: conjunto obrigatório acima + anti-drift de parâmetros, matriz de precedência e autorização.
- Revisão adversarial antes da PR `feat: evolui parâmetros compartilhados de pipeline`.

### F2 — Importação e passo de parâmetros

Divisão de execução: F2a entrega catálogo v2 no wizard, seções DS/ORQ, consulta reutilizável e importação com prévia. F2b conecta referências aos campos dos nós DS/Python e ao runtime; não está disponível em F2a. A extração real via dsjob continua dependente de smoke na versão instalada.
- Entregável: importação com prévia/conflitos, passo do wizard e seletor reutilizável; integração DS/Python pode ser dividida em PRs menores mantendo contrato funcional.
- Aceite: cancelar importação não persiste; reimportação não apaga valor próprio; fontes DS e ORQ distinguíveis; salvar erro não perde preenchimento; teclado e temas funcionam.
- Validação: conjunto obrigatório + dublês de comandos e smoke com saída DS real sanitizada; sem confirmar extração real apenas por fixture.
- Revisão adversarial antes da PR `feat: importa e seleciona parâmetros do pipeline`.

### F3 — Configuração e avaliação de arquivos
- Entregável: migration 131, serviço/API com políticas e prévia, avaliação dataset/texto e cabeçalho. Nó ainda indisponível para publicação.
- Aceite: ausência/vazio/dados/erro técnico distintos; path literal e referência; cabeçalho e última linha sem newline; nenhum comando/caminho arbitrário; prévia informa impacto.
- Validação: conjunto obrigatório + matriz de políticas, quoting e timeout; contratos do parser DS.
- Revisão adversarial antes da PR `feat: avalia arquivos com políticas por entrada`.

### F4 — Snapshot e registro da validação
- Entregável: migration 132, extensão do snapshot 130 para políticas e resultados duráveis; sem ativação prematura da UI.
- Aceite: retry usa revisão original após edição; resultados de falha persistem; sem segredo em XCom; nova execução recebe configuração nova; gravação concorrente idempotente.
- Validação: conjunto obrigatório + concorrência, restart e falha na persistência; migração duas vezes.
- Revisão adversarial antes da PR `feat: preserva configuração e diagnóstico por execução`.

### F5 — Integração com grafo e encerramento
- Entregável: fábrica com guardas por destino, fluxo genérico, conclusão sem movimento, liberação e fechamento corretos. Restart do worker e regeneração inicial das DAGs afetadas no deploy.
- Aceite: sequência/paralelismo preservados; controle de todos os tipos; todos pulados encerra; dependentes respeitam política; falha não publica sucesso; topology incompatível não altera uma retomada silenciosamente.
- Validação: conjunto obrigatório + execução com Airflow real dos cenários de branching, múltiplos pais, convergência e recuperação; testes da fábrica declaram alterações do código gerado.
- Revisão adversarial antes da PR `feat: controla etapas por validação de arquivos`.

### F6 — Canvas e acompanhamento
- Entregável: ativação do nó, configuração acessível, prévia de impacto, detalhes por arquivo e configuração sem movimento.
- Aceite: qualquer tipo suportado é selecionável; labels genéricos; estado liberado não aparece como executado; impacto transitivo e mudanças que exigem publicação são visíveis; versão original indicada na retomada.
- Validação: conjunto obrigatório + smoke real em DEV, teclado, claro/escuro, erros e limites de largura; dist por último.
- Revisão adversarial antes da PR `feat: configura e acompanha validação de arquivos no canvas`.

### F7 — Documentação e aplicação assistida
- Entregável: manual, release note, roteiro de deploy/rollback e configuração do caso inicial com nomes reais somente nos dados do pipeline.
- Aceite: matriz do §7 executada; limitações documentadas; nenhum hardcode do caso inicial no produto; item de frescor preparado para Backlog.
- Validação: conjunto obrigatório + smoke em ambiente com dsjob/orchadmin; DEV sem DataStage não certifica integração real. Implantação no ambiente final segue autorização e processo locais.
- Revisão adversarial antes da PR `docs: documenta parâmetros e validação de arquivos`.

## 6. Riscos e mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| Branch ignora dependência ou libera destino indevido | Execução fora de ordem | Guardas por destino, matriz de grafo e teste Airflow real |
| ALL_DONE mascara falha | Sucesso/liberação incorretos | Separar finalização, resultado e evento de sucesso |
| Default difere do caminho escolhido no nó | Arquivo errado | Origem visível, literal explícito e aviso de divergência conhecida |
| Configuração muda durante retry | Resultado não reproduzível | Snapshot original e novo run para nova configuração |
| Arquivo antigo/concorrência | Dado de outra execução | Limitação explícita e backlog; sem garantia de frescor nesta versão |
| Erro técnico vira ausência/zero | Skip ou execução indevida | Estado desconhecido/erro distinto e política explícita |
| Valor sensível exposto | Vazamento | Cifragem, máscaras, RBAC e logs limitados |
| Worker mantém módulo antigo | UI/runtime divergentes | Restart do worker no deploy de dags/utils e smoke |
| Linhas físicas diferem de registros CSV | Contagem enganosa | Label e escopo explícitos; primeira linha opcional; multilinha fora |

## 7. Smoke pós-deploy

a) Reexecutar migrations duas vezes; confirmar compatibilidade de pipeline antigo.
b) Importar parâmetros de dois jobs com conflito; cancelar e depois confirmar sem perder customização.
c) Selecionar parâmetro e depois literal no nó; prévia e runtime usam o literal; segredo não aparece.
d) Arquivo inexistente, vazio, com cabeçalho apenas, com dados e sem newline final: estados e contagens corretos.
e) Dataset real vazio/com dados; erro de permissão, SSH, timeout ou saída ilegível sempre falha o nó, bloqueia destinos e não publica sucesso. Configuração para pular ausência/vazio não pode contornar erro técnico.
f) Dois destinos em sequência, depois paralelos; primeiro pulado não libera segundo contra sua política; falha bloqueante não publica sucesso.
g) Matriz dos dez tipos de nó: liberação/skip/bloqueio, múltiplos pais e convergência sem efeitos colaterais indevidos.
h) Todos sem dados: Concluído sem movimento, liberação de dependentes ligada/desligada e histórico técnico presente em todos os casos. Ligar/desligar notificação não altera histórico nem política de liberação.
i) Alterar cadastro após falha e retomar: usa original. Nova execução: usa configuração nova; falha anterior preservada.
j) Diagnóstico permanece visível após falha/retry; mostra decisão e resultado efetivo separadamente.
k) Alteração runtime não pede republicação; mudança topológica pede e protege corridas existentes.
l) Falha de permissão no endpoint e configuração concorrente retornam erro sem gravação parcial; testar teclado e temas.

## 8. Decisões finais e estado

Em 27/09/2026, o usuário confirmou os dois pontos restantes:

1. **Histórico técnico obrigatório; notificação opcional.** Toda execução, inclusive Concluído sem movimento, mantém registro técnico de configuração, decisões e resultado. A opção de notificação não interfere na liberação de dependentes.
2. **Erro técnico sempre resulta em falha.** Falha de conexão, permissão, leitura, timeout ou interpretação não pode ser tratada como ausência/vazio nem permitir continuar sem validação. Os destinos do nó ficam bloqueados; o diagnóstico é preservado.

Não restam perguntas funcionais da entrevista. Importação, guardas internas, agregação de várias entradas por destino e modelo físico são propostas técnicas desta spec, sujeitas à validação das fases; não são implementações concluídas. As decisões foram consolidadas antes do código. Em seguida o usuário autorizou iniciar as alterações; a implementação segue as fases e merges separados.

Confirmação operacional do usuário: o teste com dataset DataStage real só pode ocorrer na Caixa. Implementação/QA local seguem; certificação nessa versão é etapa assistida pendente, explicitamente separada do aceite local.
