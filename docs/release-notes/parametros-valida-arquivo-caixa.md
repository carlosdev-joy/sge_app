# Aplicação assistida — parâmetros e Valida Arquivo na Caixa

## Estado e limite de autorização

Código, QA local e documentação preparados. **Nenhum deploy foi feito na Caixa.** O DEV segue o [fluxo de integração](../fluxo-desenvolvimento.md); sua validação não certifica DataStage real. Certificação de `dsjob`, `orchadmin` e arquivos DataStage reais será feita somente no ambiente Caixa, por decisão do usuário. Fixtures locais e a bancada Airflow/SQL/SFTP não comprovam compatibilidade da versão instalada.

Este roteiro prepara a aplicação; os campos abaixo e os resultados não estão preenchidos como se já tivessem sido executados. A configuração do pipeline real requer nomes/conexões/arquivos confirmados no ambiente Caixa. Não copiar credenciais ou conteúdo de dados para repositório, chat ou evidências.

## Pré-requisitos e implantação

1. Confirmar merges autorizados da cadeia F2a #456 → F2b #457 → F3 #458 → F4 #459 → F5 #460 → F6 #461 → F7. F1 #455 já foi mergeada. Resolver conflitos preservando o código cumulativo e recompilar dist quando necessário. Não implantar F2b sem a correção F4 que usa `execution_id` real em `etl_pipeline_execucao`.
2. Registrar versão anterior e candidata, backup do banco/configuração e referência segura da chave Fernet existente (`ORQUESTRA_CONN_KEY`). Não trocar nem exibir a chave: snapshots dependem dela.
3. Confirmar janela, responsável de aplicação, responsável ETL e operador de validação. Suspender novas execuções dos pipelines de ensaio até conferir o conjunto instalado. Não encerrar corridas de negócio para facilitar teste.
4. Usar o fluxo local de `scripts/deploy.sh`; aplicar migrations pendentes 128–134 (134 registra a versão da entrega em Admin → Versões e sincroniza a versão exibida) na etapa 6c e conservar as anteriores, incluindo 072 (`execution_id VARCHAR(250)`). No bloco de `config/`, manter o nginx local conforme a instrução de deploy do repositório. Instalação é offline; esta entrega não adiciona dependências Python ou wheels.
5. Atualizar API, UI/dist, fábrica e `dags/utils` como conjunto; reiniciar workers do Airflow para limpar cache dos módulos. Conferir importações da DAG e versões antes do primeiro disparo.
6. Publicar inicialmente as DAGs que ativarem vínculos/validadores. Conferir grafo gerado, conexão efetiva, parâmetros e dependências; retirar eventuais agendamentos durante o ensaio isolado.
7. Na conexão SSH aprovada, configurar extras administrativos `valida_dsenv`, `valida_orchadmin` e, se necessário, `valida_apt_config`, todos como caminhos absolutos da instalação local. A credencial continua na conexão. O usuário do SSH deve ter as permissões de leitura necessárias.

## Certificar os contratos DataStage primeiro

Em diretório e projeto de ensaio aprovados, com datasets preparados pela equipe ETL:

- Conferir versão instalada e coletar somente saída sanitizada de metadados para dataset vazio e dataset com contagem conhecida. O avaliador usa `orchadmin describe -d -l`; não usa dump do conteúdo.
- Comparar a contagem reportada com a fonte de verdade do ensaio. O parser atual exige exatamente um total explícito `Total records: N` ou `Total rows: N` (também aceita `=`). Resumo diferente deve falhar como erro técnico, jamais ser convertido em zero. Se a instalação usar outro formato, preservar exemplo sanitizado, ajustar parser/testes em PR e repetir a certificação antes de liberar operação.
- Certificar `dsjob -lparams` e `-paraminfo` com String/Pathname, numérico, default vazio, Encrypted e Parameter Set quando usado. Não registrar valor secreto na saída coletada. Comparar tipos/defaults permitidos com o Designer; formato desconhecido continua recusado.
- Confirmar tempo máximo, permissões, dsenv/APT e leitura sem escrita nos arquivos. Não testar timeout ou permissão retirando acesso de um diretório de produção; usar recurso exclusivo de ensaio.

## Configuração do caso inicial

Preencher na Caixa, antes do primeiro disparo:

| Campo | Valor a confirmar |
|---|---|
| Pipeline/projeto de ensaio | Pendente — nome real aprovado |
| Conexão SSH / instância DataStage | Pendente — identificador, sem credencial |
| Diretório parametrizado | Pendente — caminho real de ensaio |
| Nome real de cada arquivo/dataset | Pendente — extensão e caixa exatas |
| Destino de cada entrada | Pendente — nome real no canvas |
| Ordem dos destinos | Sequencial no caso inicial; desenhada pelo usuário |
| Política se ausente / se vazio | Escolha explícita por entrada |
| Cabeçalho de arquivo texto | Confirmar se existe primeira linha a ignorar |
| Liberação de dependentes sem movimento | Escolha explícita do usuário |
| Notificação sem movimento / destinatário de ensaio | Escolha explícita; histórico sempre ativo |
| Resultado esperado e contagens conhecidas | Pendente — comparar com o ensaio ETL |

Nomes que descrevem operações de negócio ficam somente nos dados da configuração. Não introduzir regras INS/UPD no produto. Não reproduzir a limpeza real no ensaio: a informação de que o processo existente apaga e recria arquivos diariamente é uma premissa informada. Frescor/concorrência continuam fora do escopo e registrados no Backlog 128.

## Matriz de aceite na Caixa

Cada linha permanece **pendente de execução na Caixa**. Registrar corrida/tentativa, resultado esperado/observado, evidência sanitizada, responsável e data. Cenários de HTTP, SQL, e-mail e notificações usam recursos de ensaio sem efeito externo não autorizado.

| ID / spec §7 | Ensaio | Critério de aprovação |
|---|---|---|
| A | Migrations idempotentes / pipeline legado | Segunda aplicação não altera dados; pipeline antigo mantém comportamento |
| B | Importação de dois jobs / conflito / cancelar | Metadados corretos; cancelar não grava; customização preservada |
| C | Parâmetro e literal | Prévia e nova corrida usam literal; ORQ não é enviado a DS; segredo não aparece |
| D | Texto ausente/vazio/cabeçalho/dados/sem newline | Estados e contagens corretos, inclusive cabeçalho apenas = zero |
| E | Dataset vazio/dados e erros técnicos | Contagem real correta; erro falha, persiste diagnóstico e bloqueia destinos/publicação |
| F | Dois destinos sequenciais e paralelos | Cada decisão respeita dependências e política; pular um não libera outro indevidamente |
| G | Dez tipos, múltiplos pais e convergência | DataStage, Shell, Python, Stored Proc, HTTP, Decisão, Notificação, SQL, Aguarde e E-mail cumprem liberar/pular/bloquear |
| H | Todos pulados; liberação on/off; aviso on/off | Conclui sem movimento; publicação respeita liberação; histórico existe nos quatro casos |
| I | Falhar, editar cadastro, retomar; nova corrida | Retry conserva revisão original; nova corrida usa nova configuração; falha anterior preservada |
| J | Diagnóstico após falha/retry/remoção do nó | Tentativas e original visíveis; liberação não é exibida como execução |
| K | Alterar valor e alterar estrutura | Valor não exige publicar; estrutura exige e protege corridas retomáveis |
| L | Sem permissão / edição concorrente / teclado/temas | Erro explícito, sem gravação parcial ou perda do rascunho |
| Extra | Branch pulado e replay parcial | Sem avaliação não vira sem movimento; prova de tentativa antiga não libera publicação |

## Critérios de interrupção e rollback

Interromper o aceite diante de contagem desconhecida tratada como zero, segredo exposto, execução indevida de destino, sucesso publicado após falha, divergência de snapshot ou perda de diagnóstico. Preservar identificadores e evidências sem conteúdo privado; suspender apenas novos disparos afetados pelo ensaio.

Antes de ativar a feature, rollback de código pode conservar as migrations aditivas. Depois de ativar, **não basta voltar a UI ou apenas a fábrica**: preservar banco, chave, snapshots, tentativas e guardas; pausar novos disparos; concluir ou tratar corridas existentes conforme processo operacional; restaurar API/DAG/UI/runtime compatíveis como conjunto e reiniciar workers. Não apagar tabelas nem zerar `param_snapshot_ativo`; não reconstruir snapshot ausente a partir do cadastro atual. Não retomar corrida antiga com configuração nova.

Se não for possível restaurar uma combinação compatível, manter os pipelines afetados pausados e seguir correção progressiva validada, com responsável de operação. Retomar agenda e dependentes somente após aceite registrado. Esta documentação não autoriza testes com efeitos reais nem atesta implantação.

## Registro de aceite

| Item | Registro |
|---|---|
| Versão/commit instalado | Pendente |
| Responsável / data / janela | Pendente |
| Projeto, conexão e datasets de ensaio | Pendente |
| Matriz A–L e extra | Pendente |
| Desvios e PRs corretivas | Pendente |
| Decisão de liberação operacional | Pendente — responsável autorizado |
