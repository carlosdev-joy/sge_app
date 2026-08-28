-- ============================================================
-- SNAPSHOT COMPLETO DO SCHEMA DE PRODUÇÃO — gerado em 2026-08-27
-- Todas as tabelas etl_* existentes em dbo
-- Aplicar em ordem em um banco vazio para recriar o ambiente
-- ============================================================

-- etl_airflow_role_perfil
IF OBJECT_ID('dbo.etl_airflow_role_perfil', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_airflow_role_perfil (
    [role_airflow] varchar(100) NOT NULL,
    [perfil_nome] varchar(30) NOT NULL,
    [ordem_prioridade] int NOT NULL DEFAULT ((99)),
    [descricao] varchar(200) NULL,
    [ativo] bit NOT NULL DEFAULT ((1)),
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [criado_por] varchar(50) NULL,
    [atualizado_em] datetime NULL,
    [atualizado_por] varchar(50) NULL,
    CONSTRAINT PK_etl_airflow_role_perfil PRIMARY KEY ([role_airflow])
  )
END

-- etl_app_config
IF OBJECT_ID('dbo.etl_app_config', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_app_config (
    [config_key] varchar(100) NOT NULL,
    [config_value] varchar(1000) NOT NULL,
    [descricao] varchar(500) NULL,
    [updated_by] varchar(100) NULL,
    [updated_at] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_app_config PRIMARY KEY ([config_key])
  )
END

-- etl_backlog
IF OBJECT_ID('dbo.etl_backlog', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_backlog (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [titulo] nvarchar(200) NOT NULL,
    [descricao] nvarchar(MAX) NULL,
    [tipo] nvarchar(16) NOT NULL DEFAULT ('feature'),
    [area] nvarchar(24) NULL,
    [prioridade] nvarchar(4) NOT NULL DEFAULT ('P2'),
    [status] nvarchar(16) NOT NULL DEFAULT ('ideia'),
    [estimativa] nvarchar(16) NULL,
    [responsavel] nvarchar(64) NULL,
    [ref_pr] nvarchar(60) NULL,
    [tags] nvarchar(200) NULL,
    [criado_por] nvarchar(64) NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [atualizado_em] datetime NULL,
    [concluido_em] datetime NULL,
    CONSTRAINT PK_etl_backlog PRIMARY KEY ([id])
  )
END

-- etl_blackout
IF OBJECT_ID('dbo.etl_blackout', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_blackout (
    [id] int IDENTITY(1,1) NOT NULL,
    [inicio] datetime NOT NULL,
    [fim] datetime NOT NULL,
    [escopo] nvarchar(200) NULL,
    [motivo] nvarchar(300) NOT NULL,
    [ativo] bit NOT NULL DEFAULT ((1)),
    [criado_por] varchar(100) NULL,
    [created_at] datetime NOT NULL DEFAULT (getdate()),
    [encerrado_por] varchar(100) NULL,
    [encerrado_em] datetime NULL,
    CONSTRAINT PK_etl_blackout PRIMARY KEY ([id])
  )
END

-- etl_caixa_chat_log
IF OBJECT_ID('dbo.etl_caixa_chat_log', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_caixa_chat_log (
    [id] int IDENTITY(1,1) NOT NULL,
    [assistente] varchar(10) NOT NULL,
    [matricula] varchar(20) NOT NULL,
    [mensagem] nvarchar(MAX) NOT NULL,
    [resposta] nvarchar(MAX) NULL,
    [contexto] nvarchar(MAX) NULL,
    [modelo] varchar(100) NULL,
    [duracao_ms] int NULL,
    [status] varchar(20) NOT NULL DEFAULT ('ok'),
    [erro] nvarchar(1000) NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_caixa_chat_log PRIMARY KEY ([id])
  )
END

-- etl_calendario
IF OBJECT_ID('dbo.etl_calendario', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_calendario (
    [id] int IDENTITY(1,1) NOT NULL,
    [calendario_nome] varchar(100) NOT NULL,
    [data] date NOT NULL,
    [descricao] nvarchar(200) NULL,
    [created_by] varchar(100) NULL,
    [created_at] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_calendario PRIMARY KEY ([id])
  )
END

-- etl_chamado
IF OBJECT_ID('dbo.etl_chamado', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_chamado (
    [id] int IDENTITY(1,1) NOT NULL,
    [sys_id] varchar(32) NOT NULL,
    [numero] varchar(20) NOT NULL,
    [tipo] varchar(20) NOT NULL,
    [titulo] nvarchar(400) NULL,
    [estado_origem] varchar(60) NULL,
    [estado_kanban] varchar(20) NOT NULL,
    [prioridade] varchar(20) NULL,
    [atribuido_a] nvarchar(120) NULL,
    [grupo] nvarchar(120) NULL,
    [aberto_em] datetime NULL,
    [atualizado_em] datetime NULL,
    [encerrado_em] datetime NULL,
    [ativo] bit NOT NULL DEFAULT ((1)),
    [url] nvarchar(500) NULL,
    [sync_em] datetime NOT NULL DEFAULT (getdate()),
    [pai_sys_id] varchar(32) NULL,
    [pai_numero] varchar(20) NULL,
    [estado_cru] varchar(20) NULL,
    [descricao] nvarchar(4000) NULL,
    [work_notes] nvarchar(4000) NULL,
    [catalogo] nvarchar(200) NULL,
    [demandante] nvarchar(120) NULL,
    [prazo] datetime NULL,
    [vencimento] datetime NULL,
    [sla_vencido] bit NULL,
    [tipo_demanda] nvarchar(60) NULL,
    [categoria_diaadia] nvarchar(60) NULL,
    [objetos] nvarchar(200) NULL,
    [veredito] varchar(30) NULL,
    [suficiencia] varchar(20) NULL,
    [resumo] nvarchar(400) NULL,
    [entendimento] nvarchar(1000) NULL,
    [lacunas] nvarchar(2000) NULL,
    [perguntas] nvarchar(2000) NULL,
    [triagem_origem] varchar(20) NULL,
    [triagem_modelo] varchar(60) NULL,
    [triagem_em] datetime NULL,
    [triagem_hash] varchar(64) NULL,
    [triagem_erro] nvarchar(400) NULL,
    [atribuido_a_email] nvarchar(200) NULL,
    [tem_anexo] tinyint NULL DEFAULT ((0)),
    CONSTRAINT PK_etl_chamado PRIMARY KEY ([id])
  )
END

-- etl_chamado_anexo
IF OBJECT_ID('dbo.etl_chamado_anexo', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_chamado_anexo (
    [sys_id_anexo] varchar(32) NOT NULL,
    [sys_id_chamado] varchar(32) NOT NULL,
    [nome_arquivo] nvarchar(255) NULL,
    [mime_type] nvarchar(100) NULL,
    [tamanho_bytes] int NULL,
    [url_download] nvarchar(500) NULL,
    [criado_em] datetime2 NULL,
    [sync_em] datetime2 NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_chamado_anexo PRIMARY KEY ([sys_id_anexo])
  )
END

-- etl_chamado_ciclo
IF OBJECT_ID('dbo.etl_chamado_ciclo', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_chamado_ciclo (
    [id] int IDENTITY(1,1) NOT NULL,
    [modo] nvarchar(10) NOT NULL,
    [iniciado_em] datetime2 NOT NULL,
    [terminado_em] datetime2 NULL,
    [status] nvarchar(10) NOT NULL DEFAULT ('ERRO'),
    [qtd_chamados] int NULL,
    [qtd_notas] int NULL,
    [qtd_anexos] int NULL,
    [qtd_desativados] int NULL,
    [disparado_por] nvarchar(50) NULL,
    [erro] nvarchar(1000) NULL,
    CONSTRAINT PK_etl_chamado_ciclo PRIMARY KEY ([id])
  )
END

-- etl_chamado_nota
IF OBJECT_ID('dbo.etl_chamado_nota', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_chamado_nota (
    [sys_id_nota] varchar(32) NOT NULL,
    [sys_id_chamado] varchar(32) NOT NULL,
    [autor] nvarchar(120) NULL,
    [autor_email] nvarchar(200) NULL,
    [criado_em] datetime2 NULL,
    [texto] nvarchar(4000) NULL,
    [tipo] nvarchar(20) NOT NULL,
    [sync_em] datetime2 NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_chamado_nota PRIMARY KEY ([sys_id_nota])
  )
END

-- etl_chamado_sync
IF OBJECT_ID('dbo.etl_chamado_sync', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_chamado_sync (
    [id] int IDENTITY(1,1) NOT NULL,
    [iniciado_em] datetime NOT NULL DEFAULT (getdate()),
    [terminado_em] datetime NULL,
    [status] varchar(10) NOT NULL,
    [qtd_incident] int NULL,
    [qtd_ritm] int NULL,
    [qtd_task] int NULL,
    [qtd_change] int NULL,
    [qtd_desativados] int NULL,
    [erro] nvarchar(1000) NULL,
    [disparado_por] varchar(100) NULL,
    CONSTRAINT PK_etl_chamado_sync PRIMARY KEY ([id])
  )
END

-- etl_comunicado
IF OBJECT_ID('dbo.etl_comunicado', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_comunicado (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [titulo] nvarchar(160) NOT NULL,
    [mensagem] nvarchar(MAX) NOT NULL,
    [tipo] nvarchar(32) NOT NULL DEFAULT ('info'),
    [formato] nvarchar(16) NOT NULL DEFAULT ('simples'),
    [link] nvarchar(300) NULL,
    [imagem_url] nvarchar(500) NULL,
    [publico_tipo] nvarchar(16) NOT NULL,
    [publico_desc] nvarchar(300) NULL,
    [criado_por] nvarchar(64) NOT NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [expira_em] datetime NULL,
    [ativo] bit NOT NULL DEFAULT ((1)),
    CONSTRAINT PK_etl_comunicado PRIMARY KEY ([id])
  )
END

-- etl_comunicado_destinatario
IF OBJECT_ID('dbo.etl_comunicado_destinatario', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_comunicado_destinatario (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [comunicado_id] bigint NOT NULL,
    [matricula] nvarchar(64) NOT NULL,
    [entregue_em] datetime NOT NULL DEFAULT (getdate()),
    [visto_em] datetime NULL,
    [confirmado_em] datetime NULL,
    CONSTRAINT PK_etl_comunicado_destinatario PRIMARY KEY ([id])
  )
END

-- etl_conexao
IF OBJECT_ID('dbo.etl_conexao', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_conexao (
    [id] int IDENTITY(1,1) NOT NULL,
    [conn_id] varchar(100) NOT NULL,
    [conn_type] varchar(20) NOT NULL DEFAULT ('mssql'),
    [host] nvarchar(255) NOT NULL,
    [port] int NULL,
    [login] nvarchar(128) NOT NULL,
    [senha_enc] varchar(2000) NOT NULL,
    [descricao] nvarchar(400) NULL,
    [extra_json] nvarchar(MAX) NULL,
    [origem] varchar(20) NOT NULL DEFAULT ('orquestra'),
    [criado_por] nvarchar(64) NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [atualizado_por] nvarchar(64) NULL,
    [atualizado_em] datetime NULL,
    CONSTRAINT PK_etl_conexao PRIMARY KEY ([id])
  )
END

-- etl_configuracao
IF OBJECT_ID('dbo.etl_configuracao', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_configuracao (
    [chave] nvarchar(100) NOT NULL,
    [valor] nvarchar(MAX) NULL,
    [descricao] nvarchar(500) NULL,
    [atualizado_em] datetime2 NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_configuracao PRIMARY KEY ([chave])
  )
END

-- etl_copy_catalogo
IF OBJECT_ID('dbo.etl_copy_catalogo', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_copy_catalogo (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [conn_id] varchar(100) NOT NULL,
    [database_name] nvarchar(128) NOT NULL DEFAULT (''),
    [payload_tipo] nvarchar(16) NOT NULL,
    [objeto] nvarchar(400) NOT NULL DEFAULT (''),
    [payload_json] nvarchar(MAX) NOT NULL,
    [atualizado_em] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_copy_catalogo PRIMARY KEY ([id])
  )
END

-- etl_copy_exec
IF OBJECT_ID('dbo.etl_copy_exec', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_copy_exec (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [copy_job_id] int NOT NULL,
    [dag_run_id] nvarchar(250) NULL,
    [status] nvarchar(16) NOT NULL DEFAULT ('pendente'),
    [rows_total] bigint NULL,
    [rows_copied] bigint NOT NULL DEFAULT ((0)),
    [streams] int NULL,
    [engine] nvarchar(32) NULL,
    [erro_msg] nvarchar(MAX) NULL,
    [matricula] nvarchar(64) NULL,
    [iniciado_em] datetime NULL,
    [concluido_em] datetime NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_copy_exec PRIMARY KEY ([id])
  )
END

-- etl_copy_exec_range
IF OBJECT_ID('dbo.etl_copy_exec_range', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_copy_exec_range (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [exec_id] bigint NOT NULL,
    [range_index] int NOT NULL,
    [valor_ini] nvarchar(100) NULL,
    [valor_fim] nvarchar(100) NULL,
    [status] nvarchar(16) NOT NULL DEFAULT ('pendente'),
    [rows_copied] bigint NOT NULL DEFAULT ((0)),
    [erro_msg] nvarchar(MAX) NULL,
    [iniciado_em] datetime NULL,
    [concluido_em] datetime NULL,
    CONSTRAINT PK_etl_copy_exec_range PRIMARY KEY ([id])
  )
END

-- etl_copy_job
IF OBJECT_ID('dbo.etl_copy_job', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_copy_job (
    [id] int IDENTITY(1,1) NOT NULL,
    [nome] nvarchar(200) NOT NULL,
    [src_conn_id] varchar(100) NOT NULL,
    [src_database] nvarchar(128) NOT NULL,
    [src_schema] nvarchar(128) NOT NULL DEFAULT ('dbo'),
    [src_table] nvarchar(256) NOT NULL,
    [src_filtro] nvarchar(MAX) NULL,
    [dst_conn_id] varchar(100) NOT NULL,
    [dst_database] nvarchar(128) NOT NULL,
    [dst_schema] nvarchar(128) NOT NULL DEFAULT ('dbo'),
    [dst_table] nvarchar(256) NOT NULL,
    [criar_tabela] bit NOT NULL DEFAULT ((0)),
    [truncar_antes] bit NOT NULL DEFAULT ((0)),
    [particao_coluna] nvarchar(128) NULL,
    [streams] int NOT NULL DEFAULT ((4)),
    [batch_size] int NOT NULL DEFAULT ((50000)),
    [colunas_json] nvarchar(MAX) NULL,
    [select_sql] nvarchar(MAX) NULL,
    [count_sql] nvarchar(MAX) NULL,
    [dst_columns_json] nvarchar(MAX) NULL,
    [ativo] bit NOT NULL DEFAULT ((1)),
    [criado_por] nvarchar(64) NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [atualizado_por] nvarchar(64) NULL,
    [atualizado_em] datetime NULL,
    [src_query] nvarchar(MAX) NULL,
    [src_top] int NULL,
    CONSTRAINT PK_etl_copy_job PRIMARY KEY ([id])
  )
END

-- etl_dag_pendente
IF OBJECT_ID('dbo.etl_dag_pendente', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_dag_pendente (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [pipeline_name] nvarchar(200) NOT NULL,
    [desired_paused] bit NOT NULL,
    [matricula] nvarchar(64) NULL,
    [status] nvarchar(16) NOT NULL DEFAULT ('pendente'),
    [tentativas] int NOT NULL DEFAULT ((0)),
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [atualizado_em] datetime NULL,
    [concluido_em] datetime NULL,
    [dag_run_id] nvarchar(200) NULL,
    [modo_verificacao] bit NOT NULL DEFAULT ((0)),
    CONSTRAINT PK_etl_dag_pendente PRIMARY KEY ([id])
  )
END

-- etl_dependencia_evento
IF OBJECT_ID('dbo.etl_dependencia_evento', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_dependencia_evento (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [pipeline_name] nvarchar(200) NOT NULL,
    [data_referencia] date NOT NULL,
    [tipo] varchar(30) NOT NULL,
    [detalhe] varchar(1000) NULL,
    [detectado_em] datetime2 NOT NULL DEFAULT (getdate()),
    [notificado_em] datetime2 NULL,
    [malha_execucao_id] bigint NULL,
    CONSTRAINT PK_etl_dependencia_evento PRIMARY KEY ([id])
  )
END

-- etl_ds_job_log
IF OBJECT_ID('dbo.etl_ds_job_log', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_ds_job_log (
    [id] int IDENTITY(1,1) NOT NULL,
    [execution_id] varchar(50) NOT NULL,
    [pipeline_name] varchar(200) NOT NULL,
    [job_name] varchar(200) NOT NULL,
    [project] varchar(100) NOT NULL,
    [wave_number] int NULL,
    [pid] varchar(20) NULL,
    [status] varchar(50) NOT NULL,
    [status_code] int NULL,
    [child_jobs] nvarchar(MAX) NULL,
    [log_summary] nvarchar(MAX) NULL,
    [poll_snapshots] nvarchar(MAX) NULL,
    [last_polled_at] datetime NULL,
    [created_at] datetime NOT NULL DEFAULT (getdate()),
    [updated_at] datetime NOT NULL DEFAULT (getdate()),
    [ds_start_time] varchar(50) NULL,
    [ds_end_time] datetime NULL,
    [queued_seconds] int NULL,
    [rows_out] int NULL,
    [stuck_since] datetime NULL,
    CONSTRAINT PK_etl_ds_job_log PRIMARY KEY ([id])
  )
END

-- etl_ds_seq_flow
IF OBJECT_ID('dbo.etl_ds_seq_flow', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_ds_seq_flow (
    [project] nvarchar(128) NOT NULL,
    [job] nvarchar(256) NOT NULL,
    [flow_json] nvarchar(MAX) NOT NULL,
    [nodes_count] int NULL,
    [edges_count] int NULL,
    [source_file] nvarchar(512) NULL,
    [parsed_by] nvarchar(64) NULL,
    [parsed_at] datetime2 NOT NULL DEFAULT (sysutcdatetime()),
    CONSTRAINT PK_etl_ds_seq_flow PRIMARY KEY ([project], [job])
  )
END

-- etl_ds_supervisao_estrutura
IF OBJECT_ID('dbo.etl_ds_supervisao_estrutura', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_ds_supervisao_estrutura (
    [supervisao_id] int NOT NULL,
    [job_filho] varchar(255) NOT NULL,
    [execucoes_com_sucesso] int NOT NULL DEFAULT ((0)),
    [primeira_vez] datetime NOT NULL DEFAULT (getdate()),
    [ultima_vez] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_ds_supervisao_estrutura PRIMARY KEY ([supervisao_id], [job_filho])
  )
END

-- etl_ds_supervisao_evento
IF OBJECT_ID('dbo.etl_ds_supervisao_evento', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_ds_supervisao_evento (
    [id] int IDENTITY(1,1) NOT NULL,
    [supervisao_id] int NOT NULL,
    [data_ref] date NOT NULL,
    [tipo] varchar(20) NOT NULL,
    [chave_ocorrencia] varchar(64) NOT NULL DEFAULT (''),
    [detalhe] nvarchar(1000) NULL,
    [run_inicio] datetime NULL,
    [detectado_em] datetime NOT NULL DEFAULT (getdate()),
    [notificado_em] datetime NULL,
    [mensagem] nvarchar(2000) NULL,
    CONSTRAINT PK_etl_ds_supervisao_evento PRIMARY KEY ([id])
  )
END

-- etl_ds_supervisao_job
IF OBJECT_ID('dbo.etl_ds_supervisao_job', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_ds_supervisao_job (
    [id] int IDENTITY(1,1) NOT NULL,
    [project] varchar(128) NOT NULL,
    [job_name] varchar(255) NOT NULL,
    [descricao] varchar(400) NOT NULL,
    [janela_inicio] time NOT NULL,
    [janela_fim] time NOT NULL,
    [tolerancia_min] int NOT NULL DEFAULT ((0)),
    [dias_semana] varchar(20) NOT NULL DEFAULT ('1,2,3,4,5'),
    [vigencia_inicio] date NOT NULL DEFAULT (CONVERT([date],getdate())),
    [max_linhas] int NOT NULL DEFAULT ((200)),
    [grupo_id] int NULL,
    [alerta_abortou] bit NOT NULL DEFAULT ((1)),
    [alerta_nao_executou] bit NOT NULL DEFAULT ((1)),
    [alerta_atraso] bit NOT NULL DEFAULT ((1)),
    [alerta_estrutura] bit NOT NULL DEFAULT ((1)),
    [ativo] bit NOT NULL DEFAULT ((1)),
    [created_by] varchar(20) NULL,
    [created_at] datetime NOT NULL DEFAULT (getdate()),
    [updated_at] datetime NOT NULL DEFAULT (getdate()),
    [execucoes_aprendidas] int NOT NULL DEFAULT ((0)),
    [alerta_sucesso_falso] bit NOT NULL DEFAULT ((1)),
    [alerta_filho_ausente] bit NOT NULL DEFAULT ((1)),
    CONSTRAINT PK_etl_ds_supervisao_job PRIMARY KEY ([id])
  )
END

-- etl_ds_supervisao_mensagem
IF OBJECT_ID('dbo.etl_ds_supervisao_mensagem', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_ds_supervisao_mensagem (
    [supervisao_id] int NOT NULL,
    [tipo] varchar(20) NOT NULL,
    [mensagem] nvarchar(2000) NOT NULL,
    [updated_at] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_ds_supervisao_mensagem PRIMARY KEY ([supervisao_id], [tipo])
  )
END

-- etl_ds_supervisao_run
IF OBJECT_ID('dbo.etl_ds_supervisao_run', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_ds_supervisao_run (
    [id] int IDENTITY(1,1) NOT NULL,
    [supervisao_id] int NOT NULL,
    [data_ref] date NOT NULL,
    [run_inicio] datetime NOT NULL,
    [run_fim] datetime NULL,
    [duracao_seg] int NULL,
    [resultado] varchar(20) NOT NULL,
    [jobs_filhos] int NULL,
    [coletado_em] datetime NOT NULL DEFAULT (getdate()),
    [aprendido] bit NOT NULL DEFAULT ((0)),
    [expandido] bit NOT NULL DEFAULT ((0)),
    CONSTRAINT PK_etl_ds_supervisao_run PRIMARY KEY ([id])
  )
END

-- etl_ds_supervisao_run_filho
IF OBJECT_ID('dbo.etl_ds_supervisao_run_filho', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_ds_supervisao_run_filho (
    [supervisao_id] int NOT NULL,
    [run_inicio] datetime NOT NULL,
    [job_filho] varchar(255) NOT NULL,
    [status_code] int NOT NULL,
    [data_ref] date NOT NULL,
    [coletado_em] datetime NOT NULL DEFAULT (getdate()),
    [nivel] int NOT NULL DEFAULT ((1)),
    [job_pai] varchar(255) NULL,
    [inicio] datetime NULL,
    [fim] datetime NULL,
    CONSTRAINT PK_etl_ds_supervisao_run_filho PRIMARY KEY ([supervisao_id], [run_inicio], [job_filho])
  )
END

-- etl_etapa_pausa
IF OBJECT_ID('dbo.etl_etapa_pausa', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_etapa_pausa (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [pipeline_name] nvarchar(200) NOT NULL,
    [execution_id] varchar(50) NOT NULL,
    [job_name] nvarchar(200) NOT NULL,
    [task_id] nvarchar(200) NULL,
    [run_id] varchar(250) NULL,
    [data_referencia] date NULL,
    [estado] varchar(20) NOT NULL DEFAULT ('PENDENTE'),
    [motivo] varchar(1000) NULL,
    [observacao] varchar(1000) NULL,
    [teto_minutos] int NULL,
    [solicitado_por] nvarchar(200) NOT NULL,
    [solicitado_em] datetime2 NOT NULL DEFAULT (getdate()),
    [aguardando_desde] datetime2 NULL,
    [ultima_verificacao] datetime2 NULL,
    [verificacoes] int NOT NULL DEFAULT ((0)),
    [alertado_em] datetime2 NULL,
    [resolvido_por] nvarchar(200) NULL,
    [resolvido_em] datetime2 NULL,
    CONSTRAINT PK_etl_etapa_pausa PRIMARY KEY ([id])
  )
END

-- etl_factory_log
IF OBJECT_ID('dbo.etl_factory_log', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_factory_log (
    [id] int IDENTITY(1,1) NOT NULL,
    [dag_run_id] varchar(200) NOT NULL,
    [iniciado_em] datetime NOT NULL DEFAULT (getdate()),
    [finalizado_em] datetime NULL,
    [estado] varchar(20) NOT NULL DEFAULT ('RUNNING'),
    [escopo] nvarchar(500) NULL,
    [pipeline_name] varchar(200) NULL,
    [geradas] int NOT NULL DEFAULT ((0)),
    [erros] int NOT NULL DEFAULT ((0)),
    [detalhes_json] nvarchar(MAX) NULL,
    CONSTRAINT PK_etl_factory_log PRIMARY KEY ([id])
  )
END

-- etl_failure_ack
IF OBJECT_ID('dbo.etl_failure_ack', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_failure_ack (
    [id] int IDENTITY(1,1) NOT NULL,
    [execution_id] varchar(100) NOT NULL,
    [pipeline] varchar(200) NOT NULL,
    [ack_by] varchar(100) NOT NULL,
    [ack_at] datetime NOT NULL DEFAULT (getdate()),
    [note] nvarchar(500) NULL,
    [display_name] nvarchar(200) NULL,
    [resolved_by] nvarchar(64) NULL,
    [resolved_at] datetime NULL,
    [resolution_note] nvarchar(500) NULL,
    [snow_ticket] nvarchar(64) NULL,
    [resolved_display_name] nvarchar(128) NULL,
    CONSTRAINT PK_etl_failure_ack PRIMARY KEY ([id])
  )
END

-- etl_field_change_item
IF OBJECT_ID('dbo.etl_field_change_item', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_field_change_item (
    [id] int IDENTITY(1,1) NOT NULL,
    [plan_id] int NOT NULL,
    [dsx_file] varchar(200) NULL,
    [project_name] varchar(200) NULL,
    [job_name] nvarchar(200) NOT NULL,
    [stage_name] varchar(200) NULL,
    [stage_type] varchar(100) NULL,
    [direction] varchar(30) NULL,
    [object_name] nvarchar(500) NULL,
    [column_name] nvarchar(200) NOT NULL,
    [datatype_atual] varchar(60) NULL,
    [precision_val] int NULL,
    [scale_val] int NULL,
    [datatype_alvo] varchar(60) NULL,
    [status] varchar(20) NOT NULL DEFAULT ('pendente'),
    [observacao] nvarchar(MAX) NULL,
    [assigned_to] nvarchar(100) NULL,
    [started_at] datetime2 NULL,
    [done_at] datetime2 NULL,
    [done_by] nvarchar(100) NULL,
    [created_at] datetime2 NOT NULL DEFAULT (sysdatetime()),
    [updated_at] datetime2 NOT NULL DEFAULT (sysdatetime()),
    CONSTRAINT PK_etl_field_change_item PRIMARY KEY ([id])
  )
END

-- etl_field_change_plan
IF OBJECT_ID('dbo.etl_field_change_plan', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_field_change_plan (
    [id] int IDENTITY(1,1) NOT NULL,
    [nome] nvarchar(200) NOT NULL,
    [descricao] nvarchar(MAX) NULL,
    [status] varchar(20) NOT NULL DEFAULT ('aberto'),
    [created_by] nvarchar(100) NULL,
    [created_at] datetime2 NOT NULL DEFAULT (sysdatetime()),
    [updated_at] datetime2 NOT NULL DEFAULT (sysdatetime()),
    [finalized_at] datetime2 NULL,
    [finalized_by] nvarchar(100) NULL,
    CONSTRAINT PK_etl_field_change_plan PRIMARY KEY ([id])
  )
END

-- etl_indicador_meta
IF OBJECT_ID('dbo.etl_indicador_meta', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_indicador_meta (
    [id] int IDENTITY(1,1) NOT NULL,
    [metrica] nvarchar(60) NOT NULL,
    [valor_meta] decimal(8,1) NOT NULL,
    [periodo_inicio] date NOT NULL,
    [periodo_fim] date NULL,
    [grupo] nvarchar(120) NULL,
    [criado_por] nvarchar(120) NULL,
    [criado_em] datetime2 NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_indicador_meta PRIMARY KEY ([id])
  )
END

-- etl_indicador_snapshot
IF OBJECT_ID('dbo.etl_indicador_snapshot', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_indicador_snapshot (
    [id] int IDENTITY(1,1) NOT NULL,
    [capturado_em] datetime2 NOT NULL DEFAULT (getdate()),
    [total_ativos] int NOT NULL DEFAULT ((0)),
    [novo] int NOT NULL DEFAULT ((0)),
    [andamento] int NOT NULL DEFAULT ((0)),
    [aguardando] int NOT NULL DEFAULT ((0)),
    [resolvido] int NOT NULL DEFAULT ((0)),
    [outros] int NOT NULL DEFAULT ((0)),
    [sla_vencidos] int NOT NULL DEFAULT ((0)),
    [idade_media_dias] decimal(6,1) NULL,
    [tempo_medio_resolucao_horas] decimal(8,1) NULL,
    [qtd_encerrados_7d] int NOT NULL DEFAULT ((0)),
    [qtd_abertos_7d] int NOT NULL DEFAULT ((0)),
    [qtd_iniciativas_abertas] int NOT NULL DEFAULT ((0)),
    CONSTRAINT PK_etl_indicador_snapshot PRIMARY KEY ([id])
  )
END

-- etl_indicador_snapshot_analista
IF OBJECT_ID('dbo.etl_indicador_snapshot_analista', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_indicador_snapshot_analista (
    [id_snapshot] int NOT NULL,
    [atribuido_a] nvarchar(120) NOT NULL,
    [atribuido_a_email] nvarchar(200) NOT NULL DEFAULT (''),
    [total_ativos] int NOT NULL DEFAULT ((0)),
    [sla_vencidos] int NOT NULL DEFAULT ((0)),
    [idade_media_dias] decimal(6,1) NULL,
    CONSTRAINT PK_etl_indicador_snapshot_analista PRIMARY KEY ([id_snapshot], [atribuido_a_email])
  )
END

-- etl_indicador_snapshot_grupo
IF OBJECT_ID('dbo.etl_indicador_snapshot_grupo', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_indicador_snapshot_grupo (
    [id_snapshot] int NOT NULL,
    [grupo] nvarchar(120) NOT NULL,
    [total_ativos] int NOT NULL DEFAULT ((0)),
    [sla_vencidos] int NOT NULL DEFAULT ((0)),
    [idade_media_dias] decimal(6,1) NULL,
    CONSTRAINT PK_etl_indicador_snapshot_grupo PRIMARY KEY ([id_snapshot], [grupo])
  )
END

-- etl_inventario_endpoint
IF OBJECT_ID('dbo.etl_inventario_endpoint', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_inventario_endpoint (
    [id] int IDENTITY(1,1) NOT NULL,
    [endpoint] nvarchar(200) NOT NULL,
    [plataforma] nvarchar(100) NULL,
    [consumidor] nvarchar(200) NULL,
    [banco] nvarchar(128) NOT NULL DEFAULT ('BUCC'),
    [descricao] nvarchar(1000) NULL,
    [responsavel] nvarchar(200) NULL,
    [ativo] bit NOT NULL DEFAULT ((1)),
    [criado_por] nvarchar(64) NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [atualizado_por] nvarchar(64) NULL,
    [atualizado_em] datetime NULL,
    CONSTRAINT PK_etl_inventario_endpoint PRIMARY KEY ([id])
  )
END

-- etl_inventario_objeto
IF OBJECT_ID('dbo.etl_inventario_objeto', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_inventario_objeto (
    [id] int IDENTITY(1,1) NOT NULL,
    [endpoint_id] int NOT NULL,
    [objeto] nvarchar(300) NOT NULL,
    [tipo] varchar(10) NOT NULL DEFAULT ('view'),
    [status_validacao] varchar(20) NOT NULL DEFAULT ('pendente'),
    [observacao] nvarchar(1000) NULL,
    [criado_por] nvarchar(64) NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_inventario_objeto PRIMARY KEY ([id])
  )
END

-- etl_job_execution
IF OBJECT_ID('dbo.etl_job_execution', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_job_execution (
    [execution_id] varchar(50) NOT NULL,
    [project] varchar(100) NOT NULL,
    [job_name] varchar(200) NOT NULL,
    [pipeline] varchar(200) NOT NULL,
    [host] varchar(200) NULL,
    [start_time] datetime2 NOT NULL,
    [end_time] datetime2 NULL,
    [duration_seconds] int NULL,
    [status_code] int NULL,
    [attempt] int NULL DEFAULT ((1)),
    [log_file] varchar(500) NULL,
    [created_at] datetime2 NULL DEFAULT (getdate()),
    [status] varchar(20) NULL,
    [updated_at] datetime2 NULL,
    [task_id] varchar(200) NOT NULL,
    CONSTRAINT PK_etl_job_execution PRIMARY KEY ([execution_id], [pipeline], [job_name], [task_id])
  )
END

-- etl_job_execution_tentativa
IF OBJECT_ID('dbo.etl_job_execution_tentativa', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_job_execution_tentativa (
    [execution_id] varchar(50) NOT NULL,
    [pipeline] varchar(200) NOT NULL,
    [job_name] varchar(200) NOT NULL,
    [task_id] varchar(200) NOT NULL,
    [attempt] int NOT NULL,
    [project] varchar(100) NULL,
    [host] varchar(200) NULL,
    [start_time] datetime2 NULL,
    [end_time] datetime2 NULL,
    [duration_seconds] int NULL,
    [status] varchar(20) NULL,
    [status_code] int NULL,
    [log_file] varchar(500) NULL,
    [arquivado_em] datetime2 NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_job_execution_tentativa PRIMARY KEY ([execution_id], [pipeline], [job_name], [task_id], [attempt])
  )
END

-- etl_job_lineage
IF OBJECT_ID('dbo.etl_job_lineage', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_job_lineage (
    [id] int IDENTITY(1,1) NOT NULL,
    [pipeline_name] nvarchar(200) NOT NULL,
    [job_name] nvarchar(200) NOT NULL,
    [direction] nvarchar(30) NOT NULL,
    [object_type] varchar(100) NULL,
    [object_name] nvarchar(500) NOT NULL,
    [created_at] datetime2 NOT NULL DEFAULT (sysdatetime()),
    [updated_at] datetime2 NOT NULL DEFAULT (sysdatetime()),
    [stage_name] varchar(200) NULL,
    [stage_type_raw] varchar(100) NULL,
    [database_name] varchar(200) NULL,
    [sql_expression] nvarchar(MAX) NULL,
    [dsx_source_file] varchar(500) NULL,
    [extracted_at] datetime2 NULL,
    [extraction_method] varchar(50) NULL,
    [file_path] varchar(500) NULL,
    [columns_json] nvarchar(MAX) NULL,
    CONSTRAINT PK_etl_job_lineage PRIMARY KEY ([id])
  )
END

-- etl_job_type
IF OBJECT_ID('dbo.etl_job_type', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_job_type (
    [id] int IDENTITY(1,1) NOT NULL,
    [nome] nvarchar(100) NOT NULL,
    [descricao] nvarchar(500) NULL,
    [lineage_enabled] bit NOT NULL DEFAULT ((1)),
    [status] bit NOT NULL DEFAULT ((1)),
    [criado_em] datetime2 NOT NULL DEFAULT (getdate()),
    [criado_por] nvarchar(100) NOT NULL DEFAULT ('admin'),
    CONSTRAINT PK_etl_job_type PRIMARY KEY ([id])
  )
END

-- etl_malha
IF OBJECT_ID('dbo.etl_malha', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_malha (
    [malha_name] nvarchar(200) NOT NULL,
    [descricao] nvarchar(1000) NULL,
    [ativo] bit NOT NULL DEFAULT ((1)),
    [criado_em] datetime2 NOT NULL DEFAULT (sysdatetime()),
    [criado_por] nvarchar(100) NULL,
    [atualizado_em] datetime2 NULL,
    [orientacao] varchar(12) NOT NULL DEFAULT ('horizontal'),
    [agendamento_json] nvarchar(MAX) NULL,
    [hora_virada] time NULL,
    [equalizar_data] bit NOT NULL DEFAULT ((0)),
    [teto_horas] int NULL,
    [grupo_id] int NULL,
    CONSTRAINT PK_etl_malha PRIMARY KEY ([malha_name])
  )
END

-- etl_malha_aresta
IF OBJECT_ID('dbo.etl_malha_aresta', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_malha_aresta (
    [id] int IDENTITY(1,1) NOT NULL,
    [malha_name] nvarchar(200) NOT NULL,
    [origem_no] int NULL,
    [origem_pipeline] nvarchar(200) NULL,
    [destino_no] int NULL,
    [destino_pipeline] nvarchar(200) NULL,
    CONSTRAINT PK_etl_malha_aresta PRIMARY KEY ([id])
  )
END

-- etl_malha_execucao
IF OBJECT_ID('dbo.etl_malha_execucao', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_malha_execucao (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [malha_name] nvarchar(200) NOT NULL,
    [data_referencia] date NOT NULL,
    [sequencia] int NOT NULL,
    [status] varchar(20) NOT NULL,
    [aberta_em] datetime2 NOT NULL DEFAULT (sysdatetime()),
    [fechada_em] datetime2 NULL,
    [fechada_por] nvarchar(200) NULL,
    [origem] varchar(20) NOT NULL,
    [aberta_por] nvarchar(200) NULL,
    [ancora_pipeline] nvarchar(200) NULL,
    [ancora_execution_id] varchar(250) NULL,
    [no_inicio] int NULL,
    [no_fim] int NULL,
    [modo_fechamento] varchar(20) NOT NULL,
    [teto_em] datetime2 NULL,
    [teto_creditado_min] int NOT NULL DEFAULT ((0)),
    [falha_vista_em] datetime2 NULL,
    [atraso_visto_em] datetime2 NULL,
    [tentativas] int NOT NULL DEFAULT ((1)),
    [reaberta_em] datetime2 NULL,
    [reaberta_por] nvarchar(200) NULL,
    [motivo] nvarchar(500) NULL,
    [criado_em] datetime2 NOT NULL DEFAULT (sysdatetime()),
    [atualizado_em] datetime2 NOT NULL DEFAULT (sysdatetime()),
    CONSTRAINT PK_etl_malha_execucao PRIMARY KEY ([id])
  )
END

-- etl_malha_execucao_membro
IF OBJECT_ID('dbo.etl_malha_execucao_membro', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_malha_execucao_membro (
    [malha_execucao_id] bigint NOT NULL,
    [pipeline_name] nvarchar(200) NOT NULL,
    [conta_para_fim] bit NOT NULL,
    [ativo_na_abertura] bit NOT NULL,
    [eh_raiz] bit NOT NULL,
    CONSTRAINT PK_etl_malha_execucao_membro PRIMARY KEY ([malha_execucao_id], [pipeline_name])
  )
END

-- etl_malha_no
IF OBJECT_ID('dbo.etl_malha_no', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_malha_no (
    [id] int IDENTITY(1,1) NOT NULL,
    [malha_name] nvarchar(200) NOT NULL,
    [tipo] varchar(20) NOT NULL,
    [config_json] nvarchar(MAX) NULL,
    [layout_x] float NULL,
    [layout_y] float NULL,
    [criado_em] datetime2 NOT NULL DEFAULT (sysdatetime()),
    [criado_por] nvarchar(100) NULL,
    [retido_em] datetime NULL,
    [retido_por] nvarchar(64) NULL,
    CONSTRAINT PK_etl_malha_no PRIMARY KEY ([id])
  )
END

-- etl_malha_pipeline
IF OBJECT_ID('dbo.etl_malha_pipeline', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_malha_pipeline (
    [malha_name] nvarchar(200) NOT NULL,
    [pipeline_name] nvarchar(200) NOT NULL,
    [layout_x] float NULL,
    [layout_y] float NULL,
    CONSTRAINT PK_etl_malha_pipeline PRIMARY KEY ([malha_name], [pipeline_name])
  )
END

-- etl_monitor_snapshot
IF OBJECT_ID('dbo.etl_monitor_snapshot', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_monitor_snapshot (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [tabela_id] bigint NOT NULL,
    [captured_at] datetime NOT NULL DEFAULT (getdate()),
    [total_linhas] bigint NULL,
    [ultima_data] datetime NULL,
    [last_write] datetime NULL,
    [qtde_ultimo_dia] bigint NULL,
    [por_dia] nvarchar(MAX) NULL,
    [erro] nvarchar(400) NULL,
    CONSTRAINT PK_etl_monitor_snapshot PRIMARY KEY ([id])
  )
END

-- etl_monitor_tabela
IF OBJECT_ID('dbo.etl_monitor_tabela', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_monitor_tabela (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [database_name] nvarchar(128) NOT NULL,
    [schema_name] nvarchar(128) NOT NULL DEFAULT ('dbo'),
    [table_name] nvarchar(128) NOT NULL,
    [coluna_data] nvarchar(128) NOT NULL,
    [coluna_atualizacao] nvarchar(128) NULL,
    [criticidade] nvarchar(8) NULL,
    [sla_horas] int NULL,
    [ativo] bit NOT NULL DEFAULT ((1)),
    [descricao] nvarchar(300) NULL,
    [criado_por] nvarchar(64) NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [atualizado_em] datetime NULL,
    CONSTRAINT PK_etl_monitor_tabela PRIMARY KEY ([id])
  )
END

-- etl_msg_grupo
IF OBJECT_ID('dbo.etl_msg_grupo', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_msg_grupo (
    [id] int IDENTITY(1,1) NOT NULL,
    [nome] varchar(120) NOT NULL,
    [descricao] varchar(400) NULL,
    [webhook_url] nvarchar(1000) NULL,
    [ativo] bit NOT NULL DEFAULT ((1)),
    [created_at] datetime NOT NULL DEFAULT (getdate()),
    [updated_at] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_msg_grupo PRIMARY KEY ([id])
  )
END

-- etl_msg_template
IF OBJECT_ID('dbo.etl_msg_template', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_msg_template (
    [id] int IDENTITY(1,1) NOT NULL,
    [grupo_id] int NULL,
    [nome] varchar(120) NOT NULL,
    [titulo] varchar(200) NULL,
    [corpo] nvarchar(MAX) NOT NULL,
    [ativo] bit NOT NULL DEFAULT ((1)),
    [created_at] datetime NOT NULL DEFAULT (getdate()),
    [updated_at] datetime NOT NULL DEFAULT (getdate()),
    [facts] nvarchar(MAX) NULL,
    [cor] varchar(20) NULL,
    [botao_texto] varchar(120) NULL,
    [botao_url] nvarchar(1000) NULL,
    CONSTRAINT PK_etl_msg_template PRIMARY KEY ([id])
  )
END

-- etl_notificacao
IF OBJECT_ID('dbo.etl_notificacao', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_notificacao (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [matricula] nvarchar(64) NOT NULL,
    [tipo] nvarchar(32) NOT NULL DEFAULT ('info'),
    [titulo] nvarchar(160) NOT NULL,
    [mensagem] nvarchar(800) NULL,
    [link] nvarchar(300) NULL,
    [lida] bit NOT NULL DEFAULT ((0)),
    [created_at] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_notificacao PRIMARY KEY ([id])
  )
END

-- etl_object_tag
IF OBJECT_ID('dbo.etl_object_tag', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_object_tag (
    [id] int IDENTITY(1,1) NOT NULL,
    [object_key] varchar(400) NOT NULL,
    [tag] varchar(50) NOT NULL,
    [added_by] varchar(100) NULL,
    [added_at] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_object_tag PRIMARY KEY ([id])
  )
END

-- etl_perfil
IF OBJECT_ID('dbo.etl_perfil', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_perfil (
    [perfil_nome] varchar(30) NOT NULL,
    [descricao] varchar(200) NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [criado_por] varchar(50) NULL,
    CONSTRAINT PK_etl_perfil PRIMARY KEY ([perfil_nome])
  )
END

-- etl_perfil_permissao
IF OBJECT_ID('dbo.etl_perfil_permissao', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_perfil_permissao (
    [perfil_nome] varchar(30) NOT NULL,
    [recurso] varchar(50) NOT NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [criado_por] varchar(50) NULL,
    CONSTRAINT PK_etl_perfil_permissao PRIMARY KEY ([perfil_nome], [recurso])
  )
END

-- etl_pipeline
IF OBJECT_ID('dbo.etl_pipeline', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_pipeline (
    [pipeline_name] nvarchar(200) NOT NULL,
    [scheduled_time] time NOT NULL,
    [active] bit NULL DEFAULT ((1)),
    [last_execution] datetime2 NULL,
    [created_at] datetime2 NULL DEFAULT (sysdatetime()),
    [updated_at] datetime2 NULL DEFAULT (sysdatetime()),
    [ENVIA_MSG_INICIO] bit NOT NULL DEFAULT ((1)),
    [ENVIA_MSG_FIM] bit NOT NULL DEFAULT ((1)),
    [ENVIA_MSG_ERRO] bit NOT NULL DEFAULT ((1)),
    [DAG_CRIADA] bit NOT NULL DEFAULT ((0)),
    [project_name] nvarchar(50) NOT NULL,
    [domain] nvarchar(100) NOT NULL,
    [tags] nvarchar(500) NOT NULL,
    [schedule_type] varchar(20) NULL,
    [schedule_hour] tinyint NULL,
    [schedule_minute] tinyint NULL,
    [schedule_dow] tinyint NULL,
    [schedule_dom] tinyint NULL,
    [depends_on] nvarchar(2000) NULL,
    [dag_start_date] date NULL,
    [descricao] nvarchar(500) NULL,
    [criticidade] nvarchar(10) NULL DEFAULT ('Media'),
    [sla_minutos] int NULL,
    [ambiente] nvarchar(10) NULL DEFAULT ('PROD'),
    [max_active_runs] int NULL DEFAULT ((1)),
    [retries_count] int NULL DEFAULT ((1)),
    [retry_delay_seconds] int NULL DEFAULT ((300)),
    [pool_name] nvarchar(100) NULL,
    [runbook_md] nvarchar(MAX) NULL,
    [calendario_nome] varchar(100) NULL,
    [somente_dias_uteis] bit NOT NULL DEFAULT ((0)),
    [trigger_por_dependencia] bit NOT NULL DEFAULT ((0)),
    [horarios_especificos] varchar(500) NULL,
    [dias_semana] varchar(30) NULL,
    [dias_horarios_mes] varchar(1000) NULL,
    [motivo_inativacao] nvarchar(500) NULL,
    [inativado_por] nvarchar(64) NULL,
    [inativado_em] datetime NULL,
    [hora_virada] time NULL,
    [nao_iniciar_antes] time NULL,
    [hora_limite_dependencia] time NULL,
    [dag_config_pendente_em] datetime2 NULL,
    [agenda_no] int NULL,
    CONSTRAINT PK_etl_pipeline PRIMARY KEY ([pipeline_name])
  )
END

-- etl_pipeline_audit
IF OBJECT_ID('dbo.etl_pipeline_audit', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_pipeline_audit (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [pipeline_name] nvarchar(200) NOT NULL,
    [changed_by] nvarchar(100) NOT NULL DEFAULT ('system'),
    [field_name] nvarchar(100) NOT NULL,
    [old_value] nvarchar(MAX) NULL,
    [new_value] nvarchar(MAX) NULL,
    [changed_at] datetime2 NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_pipeline_audit PRIMARY KEY ([id])
  )
END

-- etl_pipeline_dependencia
IF OBJECT_ID('dbo.etl_pipeline_dependencia', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_pipeline_dependencia (
    [id] int IDENTITY(1,1) NOT NULL,
    [pipeline_name] nvarchar(200) NOT NULL,
    [depende_de] nvarchar(200) NOT NULL,
    [tipo] varchar(20) NOT NULL DEFAULT ('PIPELINE'),
    [job_origem] nvarchar(200) NULL,
    [job_destino] nvarchar(200) NULL,
    [criado_em] datetime2 NOT NULL DEFAULT (getdate()),
    [criado_por] varchar(100) NULL,
    [origem_no] int NULL,
    CONSTRAINT PK_etl_pipeline_dependencia PRIMARY KEY ([id])
  )
END

-- etl_pipeline_execucao
IF OBJECT_ID('dbo.etl_pipeline_execucao', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_pipeline_execucao (
    [id] bigint IDENTITY(1,1) NOT NULL,
    [pipeline_name] nvarchar(200) NOT NULL,
    [data_referencia] date NOT NULL,
    [execution_id] varchar(250) NULL,
    [status] varchar(30) NOT NULL,
    [inicio] datetime2 NULL,
    [fim] datetime2 NULL,
    [disparado_por] nvarchar(200) NULL,
    [motivo] varchar(500) NULL,
    [criado_em] datetime2 NOT NULL DEFAULT (getdate()),
    [atualizado_em] datetime2 NOT NULL DEFAULT (getdate()),
    [substituida_em] datetime2 NULL,
    [substituida_por] nvarchar(200) NULL,
    [malha_execucao_id] bigint NULL,
    CONSTRAINT PK_etl_pipeline_execucao PRIMARY KEY ([id])
  )
END

-- etl_pipeline_job
IF OBJECT_ID('dbo.etl_pipeline_job', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_pipeline_job (
    [pipeline_name] nvarchar(200) NOT NULL,
    [job_name] nvarchar(200) NOT NULL,
    [execution_order] int NOT NULL,
    [created_at] datetime NOT NULL DEFAULT (getdate()),
    [updated_at] datetime NULL,
    [job_type] nvarchar(20) NOT NULL,
    [job_command] nvarchar(500) NULL,
    [verbose_log] bit NOT NULL DEFAULT ((0)),
    [ssh_conn_id] varchar(100) NULL,
    [mssql_conn_id] varchar(100) NULL,
    [depends_on_jobs] nvarchar(MAX) NULL,
    [layout_x] float NULL,
    [layout_y] float NULL,
    [notify_json] nvarchar(MAX) NULL,
    [sql_json] nvarchar(MAX) NULL,
    [mssql_database] nvarchar(128) NULL,
    [condition_json] nvarchar(MAX) NULL,
    [python_json] nvarchar(MAX) NULL,
    [aguarde_json] nvarchar(MAX) NULL,
    CONSTRAINT PK_etl_pipeline_job PRIMARY KEY ([pipeline_name], [job_name])
  )
END

-- etl_pipeline_job_param
IF OBJECT_ID('dbo.etl_pipeline_job_param', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_pipeline_job_param (
    [id] int IDENTITY(1,1) NOT NULL,
    [pipeline_name] nvarchar(200) NOT NULL,
    [job_name] nvarchar(200) NOT NULL,
    [param_name] varchar(128) NOT NULL,
    [param_type] varchar(30) NOT NULL,
    [param_value] nvarchar(MAX) NULL,
    [param_order] int NOT NULL DEFAULT ((0)),
    [created_at] datetime2 NOT NULL DEFAULT (sysdatetime()),
    CONSTRAINT PK_etl_pipeline_job_param PRIMARY KEY ([id])
  )
END

-- etl_pipeline_owner
IF OBJECT_ID('dbo.etl_pipeline_owner', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_pipeline_owner (
    [pipeline_name] nvarchar(300) NOT NULL,
    [owner_name] nvarchar(100) NULL,
    [owner_email] nvarchar(150) NULL,
    [steward_name] nvarchar(100) NULL,
    [steward_email] nvarchar(150) NULL,
    [updated_at] datetime NOT NULL DEFAULT (getdate()),
    [updated_by] nvarchar(100) NULL,
    CONSTRAINT PK_etl_pipeline_owner PRIMARY KEY ([pipeline_name])
  )
END

-- etl_pipeline_performance_snapshot
IF OBJECT_ID('dbo.etl_pipeline_performance_snapshot', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_pipeline_performance_snapshot (
    [id] int IDENTITY(1,1) NOT NULL,
    [pipeline] varchar(200) NOT NULL,
    [project] varchar(100) NOT NULL,
    [execution_id] varchar(50) NOT NULL,
    [alerta_horas] int NOT NULL,
    [elapsed_seconds] int NOT NULL,
    [snapshot_at] datetime2 NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_pipeline_performance_snapshot PRIMARY KEY ([id])
  )
END

-- etl_project
IF OBJECT_ID('dbo.etl_project', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_project (
    [project_name] nvarchar(100) NOT NULL,
    [descricao] nvarchar(300) NULL,
    [ativo] bit NOT NULL DEFAULT ((1)),
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_project PRIMARY KEY ([project_name])
  )
END

-- etl_schema_version
IF OBJECT_ID('dbo.etl_schema_version', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_schema_version (
    [id] int IDENTITY(1,1) NOT NULL,
    [migration_name] varchar(120) NOT NULL,
    [applied_at] datetime NOT NULL DEFAULT (getdate()),
    [applied_by] varchar(50) NULL,
    [checksum] varchar(64) NULL,
    CONSTRAINT PK_etl_schema_version PRIMARY KEY ([id])
  )
END

-- etl_seq_import
IF OBJECT_ID('dbo.etl_seq_import', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_seq_import (
    [id] int IDENTITY(1,1) NOT NULL,
    [dsx_filename] varchar(500) NOT NULL,
    [seq_name_raw] varchar(500) NOT NULL,
    [seq_name] varchar(500) NOT NULL,
    [project_name] varchar(100) NOT NULL,
    [domain] varchar(100) NULL,
    [pipeline_name_override] varchar(300) NULL,
    [schedule_type] varchar(20) NULL,
    [schedule_cron] varchar(100) NULL,
    [schedule_hour] tinyint NULL,
    [schedule_minute] tinyint NULL,
    [schedule_dow] tinyint NULL,
    [schedule_dom] tinyint NULL,
    [status] varchar(30) NOT NULL DEFAULT ('pendente_aprovacao'),
    [obs] varchar(1000) NULL,
    [imported_by] varchar(100) NOT NULL,
    [imported_at] datetime NOT NULL DEFAULT (getdate()),
    [reviewed_by] varchar(100) NULL,
    [reviewed_at] datetime NULL,
    [pipeline_id] int NULL,
    CONSTRAINT PK_etl_seq_import PRIMARY KEY ([id])
  )
END

-- etl_seq_import_job
IF OBJECT_ID('dbo.etl_seq_import_job', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_seq_import_job (
    [id] int IDENTITY(1,1) NOT NULL,
    [import_id] int NOT NULL,
    [execution_order] int NOT NULL,
    [job_name_ds] varchar(300) NOT NULL,
    [job_name_orq] varchar(300) NOT NULL,
    [job_type] varchar(30) NOT NULL DEFAULT ('datastage'),
    [job_command] varchar(1000) NULL,
    [status] varchar(30) NOT NULL DEFAULT ('pendente'),
    [lineage_extracted] bit NOT NULL DEFAULT ((0)),
    [lineage_count] int NOT NULL DEFAULT ((0)),
    [pipeline_job_id] int NULL,
    CONSTRAINT PK_etl_seq_import_job PRIMARY KEY ([id])
  )
END

-- etl_seq_import_lineage
IF OBJECT_ID('dbo.etl_seq_import_lineage', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_seq_import_lineage (
    [id] int IDENTITY(1,1) NOT NULL,
    [import_job_id] int NOT NULL,
    [direction] varchar(20) NOT NULL,
    [object_name] varchar(300) NOT NULL,
    [object_type] varchar(100) NULL,
    [stage_type_raw] varchar(100) NULL,
    [sql_expression] varchar(MAX) NULL,
    [file_path] varchar(500) NULL,
    [database_name] varchar(255) NULL,
    [dsx_source_file] varchar(500) NULL,
    [extraction_method] varchar(50) NULL DEFAULT ('dsx_auto'),
    [status] varchar(30) NOT NULL DEFAULT ('pendente'),
    [lineage_id] int NULL,
    [columns_json] nvarchar(MAX) NULL,
    CONSTRAINT PK_etl_seq_import_lineage PRIMARY KEY ([id])
  )
END

-- etl_servicenow_gatilho
IF OBJECT_ID('dbo.etl_servicenow_gatilho', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_servicenow_gatilho (
    [id] int IDENTITY(1,1) NOT NULL,
    [tipo] nvarchar(60) NOT NULL,
    [condicao_json] nvarchar(500) NULL,
    [webhook_url] nvarchar(500) NULL,
    [ativo] tinyint NOT NULL DEFAULT ((0)),
    [grupo] nvarchar(120) NULL,
    [criado_em] datetime2 NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_servicenow_gatilho PRIMARY KEY ([id])
  )
END

-- etl_servicenow_grupo
IF OBJECT_ID('dbo.etl_servicenow_grupo', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_servicenow_grupo (
    [id] int IDENTITY(1,1) NOT NULL,
    [nome] nvarchar(200) NOT NULL,
    [ativo] tinyint NOT NULL DEFAULT ((1)),
    [criado_em] datetime2 NOT NULL DEFAULT (getdate()),
    [alterado_em] datetime2 NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_servicenow_grupo PRIMARY KEY ([id])
  )
END

-- etl_sessao
IF OBJECT_ID('dbo.etl_sessao', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_sessao (
    [token_hash] char(64) NOT NULL,
    [matricula] varchar(20) NOT NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [expira_em] datetime NOT NULL,
    CONSTRAINT PK_etl_sessao PRIMARY KEY ([token_hash])
  )
END

-- etl_sla_alert
IF OBJECT_ID('dbo.etl_sla_alert', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_sla_alert (
    [id] int IDENTITY(1,1) NOT NULL,
    [execution_id] varchar(100) NOT NULL,
    [pipeline] varchar(200) NOT NULL,
    [alert_type] varchar(10) NOT NULL,
    [sla_minutos] int NULL,
    [elapsed_min] int NULL,
    [alerted_at] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_sla_alert PRIMARY KEY ([id])
  )
END

-- etl_sn_categoria
IF OBJECT_ID('dbo.etl_sn_categoria', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_sn_categoria (
    [id] int IDENTITY(1,1) NOT NULL,
    [slug] varchar(60) NOT NULL,
    [label] nvarchar(80) NOT NULL,
    [descricao] nvarchar(400) NULL,
    [padrao] bit NOT NULL DEFAULT ((0)),
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [atualizado_em] datetime NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_sn_categoria PRIMARY KEY ([id])
  )
END

-- etl_stage_type_map
IF OBJECT_ID('dbo.etl_stage_type_map', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_stage_type_map (
    [stage_type] nvarchar(100) NOT NULL,
    [type_label] nvarchar(100) NOT NULL,
    [type_category] nvarchar(50) NULL,
    [role_hint] nvarchar(50) NULL,
    CONSTRAINT PK_etl_stage_type_map PRIMARY KEY ([stage_type])
  )
END

-- etl_teste_execucao
IF OBJECT_ID('dbo.etl_teste_execucao', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_teste_execucao (
    [id] int IDENTITY(1,1) NOT NULL,
    [tipo_teste] nvarchar(50) NOT NULL,
    [resultado] nvarchar(500) NOT NULL,
    [executado_em] datetime2 NOT NULL DEFAULT (getdate()),
    CONSTRAINT PK_etl_teste_execucao PRIMARY KEY ([id])
  )
END

-- etl_usuario
IF OBJECT_ID('dbo.etl_usuario', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_usuario (
    [matricula] varchar(20) NOT NULL,
    [perfil_nome] varchar(30) NOT NULL DEFAULT ('consulta'),
    [primeiro_nome] varchar(100) NULL,
    [ultimo_nome] varchar(100) NULL,
    [email] varchar(200) NULL,
    [avatar_url] varchar(500) NULL,
    [ativo] bit NOT NULL DEFAULT ((1)),
    [primeiro_login] datetime NULL,
    [ultimo_login] datetime NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [criado_por] varchar(50) NULL,
    CONSTRAINT PK_etl_usuario PRIMARY KEY ([matricula])
  )
END

-- etl_usuario_permissao
IF OBJECT_ID('dbo.etl_usuario_permissao', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_usuario_permissao (
    [matricula] varchar(20) NOT NULL,
    [recurso] varchar(50) NOT NULL,
    [criado_em] datetime NOT NULL DEFAULT (getdate()),
    [criado_por] varchar(50) NULL,
    CONSTRAINT PK_etl_usuario_permissao PRIMARY KEY ([matricula], [recurso])
  )
END

-- etl_versao_ferramenta
IF OBJECT_ID('dbo.etl_versao_ferramenta', 'U') IS NULL BEGIN
  CREATE TABLE dbo.etl_versao_ferramenta (
    [id] int IDENTITY(1,1) NOT NULL,
    [versao] nvarchar(20) NOT NULL,
    [titulo] nvarchar(200) NOT NULL,
    [descricao_md] nvarchar(MAX) NULL,
    [criado_em] datetime2 NOT NULL DEFAULT (getdate()),
    [criado_por] nvarchar(100) NOT NULL DEFAULT ('admin'),
    CONSTRAINT PK_etl_versao_ferramenta PRIMARY KEY ([id])
  )
END
