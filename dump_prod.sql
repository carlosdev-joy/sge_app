-- Dump de dados ORQUESTRA — gerado por sql/dump_dados.py
SET NOCOUNT ON;
GO
ALTER TABLE dbo.[etl_project] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_app_config] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_job_type] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_stage_type_map] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_versao_ferramenta] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_pipeline] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_pipeline_job] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_job_lineage] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_job_execution] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_pipeline_audit] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_pipeline_owner] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_pipeline_performance_snapshot] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_object_tag] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_calendario] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_blackout] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_seq_import] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_seq_import_job] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_seq_import_lineage] NOCHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_factory_log] NOCHECK CONSTRAINT ALL;
GO
DELETE FROM dbo.[etl_factory_log];
DELETE FROM dbo.[etl_seq_import_lineage];
DELETE FROM dbo.[etl_seq_import_job];
DELETE FROM dbo.[etl_seq_import];
DELETE FROM dbo.[etl_blackout];
DELETE FROM dbo.[etl_calendario];
DELETE FROM dbo.[etl_object_tag];
DELETE FROM dbo.[etl_pipeline_performance_snapshot];
DELETE FROM dbo.[etl_pipeline_owner];
DELETE FROM dbo.[etl_pipeline_audit];
DELETE FROM dbo.[etl_job_execution];
DELETE FROM dbo.[etl_job_lineage];
DELETE FROM dbo.[etl_pipeline_job];
DELETE FROM dbo.[etl_pipeline];
DELETE FROM dbo.[etl_versao_ferramenta];
DELETE FROM dbo.[etl_stage_type_map];
DELETE FROM dbo.[etl_job_type];
DELETE FROM dbo.[etl_app_config];
DELETE FROM dbo.[etl_project];
GO

-- ===== etl_project (6 linhas) =====
INSERT INTO dbo.[etl_project] ([project_name], [descricao], [ativo], [criado_em]) VALUES
(N'BI_CVP', NULL, 1, '2026-06-08 23:06:23.930'),
(N'BI_PRESTAMISTA', NULL, 1, '2026-06-08 23:06:23.930'),
(N'BI_PREVIDENCIA', NULL, 1, '2026-06-08 23:06:23.930'),
(N'BI_VIDA', NULL, 1, '2026-06-08 23:06:23.930'),
(N'PORTAL_ECONOMIARIO', NULL, 1, '2026-06-08 23:06:23.930'),
(N'TESTE_ORQUESTRA', NULL, 1, '2026-06-08 23:06:23.930');
GO

-- ===== etl_app_config (10 linhas) =====
INSERT INTO dbo.[etl_app_config] ([config_key], [config_value], [descricao], [updated_by], [updated_at]) VALUES
(N'app_release_name', N'Importação avançada, Agendamento e Última Execução', N'Descrição do release atual — exibida no rodapé da UI', N'CVT38571', '2026-06-03 20:37:43.747'),
(N'app_version', N'2.2.0', N'Versão atual do ORQUESTRA — atualizar a cada release', NULL, '2026-06-03 20:17:27.720'),
(N'dashboard_refresh_interval_sec', N'120', N'Intervalo de auto-refresh do Dashboard em segundos (0 = desativado)', N'CVT38571', '2026-06-05 09:32:48.470'),
(N'failure_badge_hours_lookback', N'24', N'Badge de falhas: janela de tempo a verificar (horas)', NULL, '2026-06-03 20:17:27.720'),
(N'failure_badge_refresh_sec', N'300', N'Frequência de atualização do badge de falhas no header (segundos)', NULL, '2026-06-03 20:17:27.720'),
(N'jobs_query_limit', N'50', N'Número de jobs por página na tabela', NULL, '2026-06-03 20:17:27.720'),
(N'logs_query_limit', N'30', N'Número de logs por página na tabela', NULL, '2026-06-03 20:17:27.720'),
(N'pipeline_query_limit', N'20', N'Número de pipelines por página na tabela', NULL, '2026-06-03 20:17:27.720'),
(N'teams_webhook_url', N'', N'Webhook padrão do Teams (fallback geral da API). Cole a mesma URL da Variable TEAMS_WEBHOOK_URL_CVP do Airflow.', NULL, '2026-06-11 16:18:07.160'),
(N'teams_webhook_url_ack', N'https://defaultff3e6150eee34b0bbacf0685ad02bf.38.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/41d3eea123ee40b2a255df1ea3c5990f/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=sqSKmvM8b9JV08qdVCZciXnGa0Lqr1dYd9U69AX62YQ', N'Webhook do Teams para notificações de falha assumida (Assumir). Se vazio, usa teams_webhook_url.', N'CVT38571', '2026-06-11 16:38:49.850');
GO

-- ===== etl_job_type (9 linhas) =====
SET IDENTITY_INSERT dbo.[etl_job_type] ON;
INSERT INTO dbo.[etl_job_type] ([id], [nome], [descricao], [lineage_enabled], [status], [criado_em], [criado_por]) VALUES
(1, N'SQL', N'Script SQL em banco relacional (SELECT/INSERT/UPDATE/MERGE)', 1, 1, '2026-06-08 23:06:23.993', N'admin'),
(2, N'Python', N'Script Python — pandas, requests, transformações customizadas', 1, 1, '2026-06-08 23:06:23.993', N'admin'),
(3, N'Bash', N'Script shell / bash para operações de sistema ou chamadas externas', 0, 1, '2026-06-08 23:06:23.993', N'admin'),
(4, N'Spark', N'Job PySpark / Spark SQL para processamento distribuído', 1, 1, '2026-06-08 23:06:23.993', N'admin'),
(5, N'dbt', N'Modelo dbt (Data Build Tool) para transformações declarativas', 1, 1, '2026-06-08 23:06:23.993', N'admin'),
(6, N'DataStage', N'Job IBM DataStage exportado via arquivo .dsx', 1, 1, '2026-06-08 23:06:23.993', N'admin'),
(7, N'SSIS', N'Pacote SSIS (SQL Server Integration Services)', 1, 1, '2026-06-08 23:06:23.993', N'admin'),
(8, N'HTTP', N'Chamada de API REST / webhook externo', 0, 1, '2026-06-08 23:06:23.996', N'admin'),
(9, N'StoredProc', N'Stored Procedure SQL Server', 1, 1, '2026-06-08 23:06:23.996', N'admin');
SET IDENTITY_INSERT dbo.[etl_job_type] OFF;
GO

-- ===== etl_stage_type_map (20 linhas) =====
INSERT INTO dbo.[etl_stage_type_map] ([stage_type], [type_label], [type_category], [role_hint]) VALUES
(N'CBMSOraBulkLoaderStage', N'Oracle Bulk Loader', N'database', N'source'),
(N'CChangeApplyStage', N'Change Apply', N'transform', N'transform'),
(N'CChangeCaptureStage', N'Change Capture', N'transform', N'transform'),
(N'CDataSetStage', N'Arquivo DataSet (.ds/.dx)', N'storage', N'source'),
(N'CFilterStage', N'Filter', N'transform', N'transform'),
(N'CFunnelStage', N'Funnel', N'transform', N'transform'),
(N'CHashPartitionStage', N'Hash Partition', N'transform', N'transform'),
(N'CJoinStage', N'Join', N'transform', N'transform'),
(N'CLookupStage', N'Lookup', N'transform', N'transform'),
(N'CNetezzaConnectorPX', N'Netezza', N'database', N'source'),
(N'CODBCConnectorPX', N'ODBC / SQL Server', N'database', N'source'),
(N'COracleConnectorPX', N'Oracle', N'database', N'source'),
(N'CRemoveDuplicatesStage', N'Remove Duplicates', N'transform', N'transform'),
(N'CRowGeneratorStage', N'Row Generator', N'transform', N'transform'),
(N'CSampleStage', N'Sample', N'transform', N'transform'),
(N'CSeqFileStage', N'Arquivo Sequencial', N'storage', N'source'),
(N'CSortStage', N'Sort', N'transform', N'transform'),
(N'CTransformerStage', N'Transformer', N'transform', N'transform'),
(N'DB2ConnectorPX', N'DB2', N'database', N'source'),
(N'SAPConnectorPX', N'SAP', N'database', N'source');
GO

-- ===== etl_versao_ferramenta (1 linhas) =====
SET IDENTITY_INSERT dbo.[etl_versao_ferramenta] ON;
INSERT INTO dbo.[etl_versao_ferramenta] ([id], [versao], [titulo], [descricao_md], [criado_em], [criado_por]) VALUES
(1, N'2.2.0', N'Importação avançada, Agendamento e Última Execução', N'# ORQUESTRA — Histórico de Versões
## v2.2.0 — Importação avançada, Agendamento e Última Execução

### Importar Sequence
- Domínio agora é obrigatório ao importar uma sequence
- Novo passo de configuração ao importar: escolha se o pipeline nasce ativo ou inativo, defina a data de início do agendamento e configure quais notificações Teams serão enviadas

### Agendamento
- Novo campo **Data de início** no cadastro de pipeline — permite definir quando o agendamento começa a executar, inclusive com data futura para adiar a primeira execução
- Campos de hora e minuto com visual maior e mais legível, sem corte de caracteres

### Última Execução
- A coluna **Última exec.** na tela de Pipelines agora é preenchida automaticamente sempre que um pipeline termina de rodar, sem necessidade de ação manual

## v2.1.0 — Reexecutar do Log e Dependência Circular

### Reexecutar a partir do Log
- Botão de reexecução direto em cada linha da tabela de logs — sem precisar sair da tela ou navegar para outra página
- Avisos claros quando o pipeline não existe ou já está em execução

### Dependência entre Pipelines — proteção contra ciclos
- Ao configurar o campo **Depende de**, o sistema valida em tempo real se a dependência cria um ciclo entre pipelines, impedindo configurações que travem o Airflow
- A validação acontece tanto na tela quanto no momento de salvar

### Visual das Ações
- Ícones menores e mais modernos na coluna de ações das tabelas, ocupando menos espaço
- Tags ao lado do Agendamento no formulário de cadastro, aproveitando melhor o espaço da tela

## v2.0.0 — Histórico de Alterações e Dependência entre Pipelines

### Histórico de Alterações (Audit Trail)
- Cada pipeline passou a ter um botão **Histórico** que exibe todas as mudanças feitas: qual campo foi alterado, o valor anterior, o novo valor, quem alterou e quando
- O registro é automático — qualquer edição salva gera uma entrada no histórico

### Dependência entre Pipelines
- Novo campo **Depende de** no cadastro de pipeline
- Quando configurado, o pipeline só inicia após o pipeline pai concluir com sucesso no mesmo dia
- A dependência é gerada automaticamente na DAG do Airflow ao regenerar

## v1.2.0 — Correções e Estabilidade

### Falhas recentes
- Corrigida divergência entre o contador de falhas no cabeçalho e os registros exibidos na tela de Logs — agora ambos usam o mesmo período de tempo

### Visualizador de logs
- Logs de execução agora exibem o conteúdo completo com rolagem horizontal, sem quebras indevidas de linha

### Execução de pipelines
- Corrigido comportamento do botão **Executar agora** que em alguns casos não disparava a execução corretamente', '2026-06-05 01:34:55.823', N'CVT38571');
SET IDENTITY_INSERT dbo.[etl_versao_ferramenta] OFF;
GO

-- ===== etl_pipeline (9 linhas) =====
INSERT INTO dbo.[etl_pipeline] ([pipeline_name], [scheduled_time], [active], [last_execution], [created_at], [updated_at], [ENVIA_MSG_INICIO], [ENVIA_MSG_FIM], [ENVIA_MSG_ERRO], [DAG_CRIADA], [project_name], [domain], [tags], [schedule_type], [schedule_hour], [schedule_minute], [schedule_dow], [schedule_dom], [depends_on], [dag_start_date], [descricao], [criticidade], [sla_minutos], [ambiente], [max_active_runs], [retries_count], [retry_delay_seconds], [pool_name], [runbook_md], [calendario_nome], [somente_dias_uteis], [trigger_por_dependencia], [horarios_especificos], [dias_semana]) VALUES
(N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', '07:00:00', 0, '2026-06-09 07:00:12', '2026-06-05 18:09:50', '2026-06-10 01:30:36', 1, 1, 1, 0, N'BI_CVP', N'MKT_CLOUD', N'MKT_CLOUD,BUCC,CENTRAL', N'daily', 7, 0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'PROD', NULL, NULL, NULL, NULL, NULL, NULL, 0, 0, NULL, NULL),
(N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', '21:50:00', 0, NULL, '2026-06-12 14:48:01', '2026-06-12 14:52:59', 1, 1, 1, 0, N'BI_CVP', N'ASSISTENCIAS', N'DATASTAGE,ASSISTENCIAS,BI_CVP', N'daily', 21, 50, NULL, NULL, NULL, '2026-06-12', N'Carga da tabela DM_CONTRATO_ASSISTENCIA_CVP.', N'Media', NULL, N'PROD', 1, 3, 300, NULL, NULL, NULL, 0, 0, NULL, NULL),
(N'datastage_coberturas_unificadas_diario', '09:00:00', 1, '2026-06-12 09:49:16', '2026-05-29 09:13:25', '2026-06-12 09:49:16', 1, 1, 0, 1, N'BI_CVP', N'Coberturas', N'datastage,BI_CVP,COBERTURAS', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'PROD', NULL, NULL, NULL, NULL, NULL, NULL, 0, 0, NULL, NULL),
(N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', '09:45:00', 1, '2026-06-12 11:54:02', '2026-06-01 14:14:45', '2026-06-12 11:54:02', 1, 1, 1, 1, N'BI_CVP', N'CONTAS_BANCARIAS', N'DATASTAGE,CONTAS_BANCARIAS,DIARIO,CONTAS', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'PROD', NULL, NULL, NULL, NULL, NULL, NULL, 0, 0, NULL, NULL),
(N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', '09:00:00', 1, '2026-06-12 09:27:51', '2026-06-03 23:20:45', '2026-06-12 09:27:51', 1, 1, 1, 1, N'BI_CVP', N'PORTAL_ECONOMIARIO', N'BI_CVP,PORTAL_ECONOMIARIO,DIARIO', N'daily', 9, 0, NULL, NULL, NULL, NULL, N'Parcelas Inadimplentes', N'Media', NULL, N'PROD', 1, 1, 300, NULL, NULL, NULL, 0, 0, NULL, NULL),
(N'DATASTAGE_GECOMIS_MOV_DIARIO', '08:00:00', 1, '2026-06-12 10:34:22', '2026-06-10 11:02:15', '2026-06-12 10:34:22', 1, 1, 1, 1, N'BI_CVP', N'GECOMIS', N'GECOMIS,DATASTAGE,DEMANDA', N'daily', 8, 0, NULL, NULL, NULL, '2026-06-11', N'Carga das tabelas TB_GECOMIS_CVP_AUTO_105, TB_GECOMIS_CVP_F_APOLICE, TB_GECOMIS_CVP_F_CCA, TB_GECOMIS_CVP_F_VALIDADOR', N'Baixa', NULL, N'PROD', 1, 3, 300, NULL, NULL, NULL, 0, 0, NULL, NULL),
(N'DATASTAGE_MALHA_VIDA', '04:00:00', 1, '2026-06-12 22:43:47', '2026-06-09 21:17:06', '2026-06-12 22:43:47', 1, 1, 1, 1, N'BI_VIDA', N'GERAL', N'MALHA_VIDA,DIARIO', N'daily', 4, 0, NULL, NULL, NULL, '2026-06-09', N'Carga da malha diária do vida.', N'Alta', NULL, N'PROD', 1, 3, 1500, NULL, NULL, NULL, 0, 0, NULL, NULL),
(N'SEQ_FLEXIBILIZACAO_COBRANCA', '08:00:00', 0, '2026-06-09 17:49:01', '2026-06-09 16:44:19', '2026-06-10 01:30:36', 1, 1, 1, 0, N'BI_CVP', N'PORTAL_ECONOMIARIO', N'PORTAL_ECONOMIARIO', N'daily', 8, 0, NULL, NULL, NULL, NULL, N'Execução de carga de parcelas pendentes portal economiario atraves da Seq_Flexibilização_Cobrança do datastage.', N'Media', NULL, N'PROD', 1, 1, 300, NULL, NULL, NULL, 0, 0, NULL, NULL),
(N'SHELL_LIMPA_FS_DATASTAGE', '10:00:00', 0, NULL, '2026-06-08 10:29:17', '2026-06-11 06:00:36', 1, 1, 1, 0, N'BI_CVP', N'INFRA', N'FS_DATASTAGE,INFRA', N'daily', 10, 0, NULL, NULL, NULL, NULL, N'Limpeza de FS do datastage', N'Baixa', NULL, N'HOM', 1, 1, 300, NULL, NULL, NULL, 0, 0, NULL, NULL);
GO

-- ===== etl_pipeline_job (28 linhas) =====
INSERT INTO dbo.[etl_pipeline_job] ([pipeline_name], [job_name], [execution_order], [created_at], [updated_at], [job_type], [job_command]) VALUES
(N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BiCvp_Assistencia_00_ext_mkt_cloud', 1, '2026-06-05 18:12:43.373', NULL, N'datastage', NULL),
(N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BiCvp_Assistencia_01_ins_mkt_cloud', 2, '2026-06-05 18:14:00.667', NULL, N'datastage', NULL),
(N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_001', 1, '2026-06-12 14:50:40.493', NULL, N'datastage', NULL),
(N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_002', 2, '2026-06-12 14:51:25.980', NULL, N'datastage', NULL),
(N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_003', 3, '2026-06-12 14:51:55.400', NULL, N'datastage', NULL),
(N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_ext_vida', 1, '2026-06-12 14:50:01.597', NULL, N'datastage', NULL),
(N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_001', 1, '2026-05-29 09:18:22.430', '2026-06-01 23:44:54.670', N'datastage', NULL),
(N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_002', 2, '2026-05-29 09:18:22.493', '2026-06-01 23:55:41.390', N'datastage', NULL),
(N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_003', 3, '2026-05-29 09:18:22.523', '2026-06-01 23:56:01.533', N'datastage', NULL),
(N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_004', 4, '2026-05-29 09:18:22.547', '2026-06-01 23:56:19.690', N'datastage', NULL),
(N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_001', 1, '2026-06-02 09:05:39.317', NULL, N'datastage', NULL),
(N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_002', 2, '2026-06-02 09:06:23.743', NULL, N'datastage', NULL),
(N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_003', 3, '2026-06-02 09:07:00.910', NULL, N'datastage', NULL),
(N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', 0, '2026-06-03 23:20:44.697', '2026-06-03 23:20:44.697', N'datastage', NULL),
(N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', 1, '2026-06-03 23:20:44.697', '2026-06-03 23:20:44.697', N'datastage', NULL),
(N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', 2, '2026-06-03 23:20:44.697', '2026-06-03 23:20:44.697', N'datastage', NULL),
(N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', 3, '2026-06-03 23:20:44.697', '2026-06-03 23:20:44.697', N'datastage', NULL),
(N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext', 1, '2026-06-10 11:38:35.187', '2026-06-11 14:46:54.620', N'datastage', NULL),
(N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_02_ins', 2, '2026-06-11 14:54:36.670', NULL, N'datastage', NULL),
(N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_01_ext', 3, '2026-06-11 14:55:11.807', NULL, N'datastage', NULL),
(N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_02_ins', 4, '2026-06-11 14:56:16.047', NULL, N'datastage', NULL),
(N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_01_ext', 5, '2026-06-11 14:57:13.593', NULL, N'datastage', NULL),
(N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_02_ins', 6, '2026-06-11 14:58:11.623', NULL, N'datastage', NULL),
(N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_01_ext', 7, '2026-06-11 15:11:58.450', NULL, N'datastage', NULL),
(N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_02_ins', 8, '2026-06-11 15:13:29.773', NULL, N'datastage', NULL),
(N'DATASTAGE_MALHA_VIDA', N'SeqExecCargaVida', 1, '2026-06-09 21:17:58.580', '2026-06-11 08:40:15.093', N'datastage', NULL),
(N'SEQ_FLEXIBILIZACAO_COBRANCA', N'Seq_Flexibilização_Cobrança', 1, '2026-06-09 17:43:56.480', NULL, N'datastage', NULL),
(N'SHELL_LIMPA_FS_DATASTAGE', N'EXEC_ALL_ZIPS.sh', 1, '2026-06-08 10:32:31.757', NULL, N'shell', N'cd /Projetos/BI_CVP/Scripts/Scripts_THG/Purge && ./EXEC_ALL_ZIPS.sh');
GO

-- ===== etl_job_lineage (103 linhas) =====
SET IDENTITY_INSERT dbo.[etl_job_lineage] ON;
INSERT INTO dbo.[etl_job_lineage] ([id], [pipeline_name], [job_name], [direction], [object_type], [object_name], [created_at], [updated_at], [stage_name], [stage_type_raw], [database_name], [sql_expression], [dsx_source_file], [extracted_at], [extraction_method], [file_path], [columns_json]) VALUES
(103, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_002', N'origem', N'ODBCConnectorPX', N'CONSULTA_COBERTURAS_GERAIS', '2026-06-01 23:55:41.409', '2026-06-01 23:55:41.409', N'CONSULTA_COBERTURAS_GERAIS', N'ODBCConnectorPX', NULL, N'DM_CONTRATO_COBERTURA_CVP', N'BI_CVP.dsx', '2026-06-01 23:55:30', N'dsx_auto', NULL, NULL),
(104, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_002', N'origem', N'Arquivo', N'Data_Set_4', '2026-06-01 23:55:41.435', '2026-06-01 23:55:41.435', N'Data_Set_4', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_COBERTURA', N'BI_CVP.dsx', '2026-06-01 23:55:30', N'dsx_auto', NULL, NULL),
(105, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_002', N'transformacao', N'PxFilter', N'Filter_26', '2026-06-01 23:55:41.453', '2026-06-01 23:55:41.453', N'Filter_26', N'PxFilter', NULL, NULL, N'BI_CVP.dsx', '2026-06-01 23:55:30', N'dsx_auto', NULL, NULL),
(106, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_002', N'transformacao', N'PxChangeCapture', N'Change_Capture_40', '2026-06-01 23:55:41.471', '2026-06-01 23:55:41.471', N'Change_Capture_40', N'PxChangeCapture', NULL, NULL, N'BI_CVP.dsx', '2026-06-01 23:55:30', N'dsx_auto', NULL, NULL),
(107, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_002', N'destino', N'Arquivo', N'Copy_of_Data_Set_4', '2026-06-01 23:55:41.511', '2026-06-01 23:55:41.511', N'Copy_of_Data_Set_4', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_COBERTURA_INS', N'BI_CVP.dsx', '2026-06-01 23:55:30', N'dsx_auto', NULL, NULL),
(108, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_002', N'destino', N'Arquivo', N'Copy_2_of_Data_Set_4', '2026-06-01 23:55:41.531', '2026-06-01 23:55:41.531', N'Copy_2_of_Data_Set_4', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_COBERTURA_UPD', N'BI_CVP.dsx', '2026-06-01 23:55:30', N'dsx_auto', NULL, NULL),
(109, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_003', N'origem', N'Arquivo', N'Data_Set_4', '2026-06-01 23:56:01.560', '2026-06-01 23:56:01.560', N'Data_Set_4', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_COBERTURA_INS', N'BI_CVP.dsx', '2026-06-01 23:55:51', N'dsx_auto', NULL, NULL),
(110, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_003', N'destino', N'ODBCConnectorPX', N'CONSULTA_PREV', '2026-06-01 23:56:01.588', '2026-06-01 23:56:01.588', N'CONSULTA_PREV', N'ODBCConnectorPX', NULL, N'dbo.DM_CONTRATO_COBERTURA_CVP', N'BI_CVP.dsx', '2026-06-01 23:55:51', N'dsx_auto', NULL, NULL),
(111, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_003', N'destino', N'ODBCConnectorPX', N'Copy_of_CONSULTA_PREV', '2026-06-01 23:56:01.611', '2026-06-01 23:56:01.611', N'Copy_of_CONSULTA_PREV', N'ODBCConnectorPX', NULL, N'dbo.DM_CONTRATO_COBERTURA_CVP', N'BI_CVP.dsx', '2026-06-01 23:55:51', N'dsx_auto', NULL, NULL),
(112, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_004', N'origem', N'Arquivo', N'Data_Set_4', '2026-06-01 23:56:19.714', '2026-06-01 23:56:19.714', N'Data_Set_4', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_COBERTURA_UPD', N'BI_CVP.dsx', '2026-06-01 23:56:14', N'dsx_auto', NULL, NULL),
(113, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_004', N'destino', N'ODBCConnectorPX', N'CONSULTA_PREV', '2026-06-01 23:56:19.737', '2026-06-01 23:56:19.737', N'CONSULTA_PREV', N'ODBCConnectorPX', NULL, N'dbo.DM_CONTRATO_COBERTURA_CVP', N'BI_CVP.dsx', '2026-06-01 23:56:14', N'dsx_auto', NULL, NULL),
(114, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_004', N'destino', N'ODBCConnectorPX', N'Copy_of_CONSULTA_PREV', '2026-06-01 23:56:19.761', '2026-06-01 23:56:19.761', N'Copy_of_CONSULTA_PREV', N'ODBCConnectorPX', NULL, N'dbo.DM_CONTRATO_COBERTURA_CVP', N'BI_CVP.dsx', '2026-06-01 23:56:14', N'dsx_auto', NULL, NULL),
(115, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_001', N'origem', N'ODBCConnectorPX', N'PREST1', '2026-06-02 09:05:39.457', '2026-06-02 09:05:39.457', N'PREST1', N'ODBCConnectorPX', NULL, N'DMDB42.dbo.DM_ODS_PRS_PROPOSTAS_U
DMDB42.dbo.DM_ODS_PRS_FINANCEIRO_MOVTO', N'BI_CVP.dsx', '2026-06-02 09:05:35', N'dsx_auto', NULL, NULL),
(116, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_001', N'origem', N'ODBCConnectorPX', N'PREV1', '2026-06-02 09:05:39.481', '2026-06-02 09:05:39.481', N'PREV1', N'ODBCConnectorPX', NULL, N'DMDB11.dbo.DM_074_BASE_CARTEIRA
DMDB11.dbo.DM_066_VENDA
DMDB11.dbo.DM_035_DADOS_BANCARIOS
DMDB11.dbo.DM_001_PESSOA
DMDB11.dbo.DM_012_CERTIFICADO
DMDB11.dbo.SB_P_201909_MANUTENCOES_PREV_FASE_2', N'BI_CVP.dsx', '2026-06-02 09:05:35', N'dsx_auto', NULL, NULL),
(117, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_001', N'origem', N'ODBCConnectorPX', N'VIDA1', '2026-06-02 09:05:39.497', '2026-06-02 09:05:39.497', N'VIDA1', N'ODBCConnectorPX', NULL, N'DMDB05.dbo.DM_077_PARCELA_COBRANCA
DMDB05.dbo.DM_065_PROPOSTA_VIDA
DMDB05.dbo.DM_003_PROPOSTA
DMDB05.dbo.DM_056_PESSOA', N'BI_CVP.dsx', '2026-06-02 09:05:35', N'dsx_auto', NULL, NULL),
(118, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_001', N'origem', N'ODBCConnectorPX', N'VIDA2', '2026-06-02 09:05:39.533', '2026-06-02 09:05:39.533', N'VIDA2', N'ODBCConnectorPX', NULL, N'DMDB05.dbo.DM_056_PESSOA
DMDB05.dbo.DM_003_PROPOSTA
DMDB05.dbo.DM_065_PROPOSTA_VIDA
DMDB05.dbo.DM_066_CONTRATO_VIDA', N'BI_CVP.dsx', '2026-06-02 09:05:35', N'dsx_auto', NULL, NULL),
(119, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_001', N'transformacao', N'PxCopy', N'Copy_133', '2026-06-02 09:05:39.557', '2026-06-02 09:05:39.557', N'Copy_133', N'PxCopy', NULL, NULL, N'BI_CVP.dsx', '2026-06-02 09:05:35', N'dsx_auto', NULL, NULL),
(120, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_001', N'transformacao', N'PxJoin', N'Join_156', '2026-06-02 09:05:39.579', '2026-06-02 09:05:39.579', N'Join_156', N'PxJoin', NULL, NULL, N'BI_CVP.dsx', '2026-06-02 09:05:35', N'dsx_auto', NULL, NULL),
(121, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_001', N'transformacao', N'PxRemDup', N'Remove_Duplicates_183', '2026-06-02 09:05:39.608', '2026-06-02 09:05:39.608', N'Remove_Duplicates_183', N'PxRemDup', NULL, NULL, N'BI_CVP.dsx', '2026-06-02 09:05:35', N'dsx_auto', NULL, NULL),
(122, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_001', N'transformacao', N'PxFunnel', N'Funnel_2', '2026-06-02 09:05:39.635', '2026-06-02 09:05:39.635', N'Funnel_2', N'PxFunnel', NULL, NULL, N'BI_CVP.dsx', '2026-06-02 09:05:35', N'dsx_auto', NULL, NULL),
(123, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_001', N'transformacao', N'PxAggregator', N'Aggregator_Ultima_Parcela', '2026-06-02 09:05:39.658', '2026-06-02 09:05:39.658', N'Aggregator_Ultima_Parcela', N'PxAggregator', NULL, NULL, N'BI_CVP.dsx', '2026-06-02 09:05:35', N'dsx_auto', NULL, NULL),
(124, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_001', N'transformacao', N'PxSort', N'Sort_Certificados', '2026-06-02 09:05:39.677', '2026-06-02 09:05:39.677', N'Sort_Certificados', N'PxSort', NULL, NULL, N'BI_CVP.dsx', '2026-06-02 09:05:35', N'dsx_auto', NULL, NULL),
(125, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_001', N'destino', N'PxDataSet', N'DS_ContasBancarias_ext', '2026-06-02 09:05:39.694', '2026-06-02 09:05:39.694', N'DS_ContasBancarias_ext', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_CONTAS_BANCARIAS', N'BI_CVP.dsx', '2026-06-02 09:05:35', N'dsx_auto', NULL, NULL),
(126, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_002', N'origem', N'PxDataSet', N'DS_ContasBancarias_ext', '2026-06-02 09:06:23.773', '2026-06-02 09:06:23.773', N'DS_ContasBancarias_ext', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_CONTAS_BANCARIAS', N'BI_CVP.dsx', '2026-06-02 09:06:16', N'dsx_auto', NULL, NULL),
(127, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_002', N'origem', N'ODBCConnectorPX', N'DMDB41_CONTAS_BANCARIAS_UNIFICADAS', '2026-06-02 09:06:23.789', '2026-06-02 09:06:23.789', N'DMDB41_CONTAS_BANCARIAS_UNIFICADAS', N'ODBCConnectorPX', NULL, N'DMDB41.dbo.DM_CONTAS_BANCARIAS_UNIFICADAS', N'BI_CVP.dsx', '2026-06-02 09:06:16', N'dsx_auto', NULL, NULL),
(128, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_002', N'transformacao', N'PxJoin', N'Join_35', '2026-06-02 09:06:23.805', '2026-06-02 09:06:23.805', N'Join_35', N'PxJoin', NULL, NULL, N'BI_CVP.dsx', '2026-06-02 09:06:16', N'dsx_auto', NULL, NULL),
(129, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_002', N'transformacao', N'PxFilter', N'Filter_41', '2026-06-02 09:06:23.829', '2026-06-02 09:06:23.829', N'Filter_41', N'PxFilter', NULL, NULL, N'BI_CVP.dsx', '2026-06-02 09:06:16', N'dsx_auto', NULL, NULL),
(130, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_002', N'destino', N'PxDataSet', N'DS_ContaBrancarias_ins', '2026-06-02 09:06:23.842', '2026-06-02 09:06:23.842', N'DS_ContaBrancarias_ins', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_CONTAS_BANCARIAS_NOVOS', N'BI_CVP.dsx', '2026-06-02 09:06:16', N'dsx_auto', NULL, NULL),
(131, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_003', N'origem', N'PxDataSet', N'DS_ContasBancarias_ins', '2026-06-02 09:07:00.937', '2026-06-02 09:07:00.937', N'DS_ContasBancarias_ins', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_CONTAS_BANCARIAS_NOVOS', N'BI_CVP.dsx', '2026-06-02 09:06:56', N'dsx_auto', NULL, NULL),
(132, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_003', N'destino', N'ODBCConnectorPX', N'INS_SQL14_DMDB41', '2026-06-02 09:07:01.018', '2026-06-02 09:07:01.018', N'INS_SQL14_DMDB41', N'ODBCConnectorPX', NULL, N'dbo.DM_CONTAS_BANCARIAS_UNIFICADAS', N'BI_CVP.dsx', '2026-06-02 09:06:56', N'dsx_auto', NULL, NULL),
(133, N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'BiCVP_ContasBancarias_003', N'destino', N'ODBCConnectorPX', N'INS_SQL69_DBBUCC', '2026-06-02 09:07:01.047', '2026-06-02 09:07:01.047', N'INS_SQL69_DBBUCC', N'ODBCConnectorPX', NULL, N'dbo.DM_CONTAS_BANCARIAS_UNIFICADAS', N'BI_CVP.dsx', '2026-06-02 09:06:56', N'dsx_auto', NULL, NULL),
(145, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'destino', N'Arquivo DataSet (.ds/.dx)', N'DS_EXT_PARCELAS_PAGAS', '2026-06-03 23:20:44.696', '2026-06-03 23:20:44.696', N'DS_EXT_PARCELAS_PAGAS', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-03 23:20:44.696', N'dsx_auto', N'#SSD_DIROT.ParmDirDst#/DS_EXT_PARCELAS_PAGAS.dx', NULL),
(146, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'origem', N'Banco de Dados (ODBC)', N'EXT_PARCELAS_PAGAS', '2026-06-03 23:20:44.696', '2026-06-03 23:20:44.696', N'EXT_PARCELAS_PAGAS', N'ODBCConnectorPX', N'TDDB05', N'COBER_HIST_VIDAZUL', N'BI_CVP.dsx', '2026-06-03 23:20:44.696', N'dsx_auto', NULL, NULL),
(147, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'destino', N'Banco de Dados (ODBC)', N'TB_PARCELASPAGAS', '2026-06-03 23:20:44.696', '2026-06-03 23:20:44.696', N'TB_PARCELASPAGAS', N'ODBCConnectorPX', N'DBBUCC', N'TB_PARCELA_PAG', N'BI_CVP.dsx', '2026-06-03 23:20:44.696', N'dsx_auto', NULL, NULL),
(148, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'origem', N'Arquivo DataSet (.ds/.dx)', N'DS_EXT_PARCELAS_PAGAS', '2026-06-03 23:20:44.696', '2026-06-03 23:20:44.696', N'DS_EXT_PARCELAS_PAGAS', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-03 23:20:44.696', N'dsx_auto', N'#SSD_DIROT.ParmDirDst#/DS_EXT_PARCELAS_PAGAS.dx', NULL),
(149, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'destino', N'Arquivo DataSet (.ds/.dx)', N'DS_EXT_PARCELAS_CLIENTES', '2026-06-03 23:20:44.696', '2026-06-03 23:20:44.696', N'DS_EXT_PARCELAS_CLIENTES', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-03 23:20:44.696', N'dsx_auto', N'#SSD_DIROT.ParmDirDst#/DS_EXT_PARCELAS_CLIENTES.dx', NULL),
(150, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'origem', N'Banco de Dados (ODBC)', N'EXT_PARCELAS_CLIENTES', '2026-06-03 23:20:44.696', '2026-06-03 23:20:44.696', N'EXT_PARCELAS_CLIENTES', N'ODBCConnectorPX', N'DBBUCC', N'dbo.DM_COBRANCA_CVP
DM_CONTRATOS_CVP
VW_PRODUTOS_CVP
NECESS
dbo.TB_PARCELA_PAG
DM_CLIENTES_CONTRATOS_CVP
DM_CLIENTES_UNIFICADOS_CVP
DM_BENEFICIARIOS_CONTRATOS_CVP
VIDA', N'BI_CVP.dsx', '2026-06-03 23:20:44.696', N'dsx_auto', NULL, NULL),
(151, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'origem', N'Arquivo DataSet (.ds/.dx)', N'DS_EXT_PARCELAS_CLIENTES', '2026-06-03 23:20:44.696', '2026-06-03 23:20:44.696', N'DS_EXT_PARCELAS_CLIENTES', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-03 23:20:44.696', N'dsx_auto', N'#SSD_DIROT.ParmDirDst#/DS_EXT_PARCELAS_CLIENTES.dx', NULL),
(152, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'destino', N'Banco de Dados (ODBC)', N'TB_PARCELASPAGAS', '2026-06-03 23:20:44.696', '2026-06-03 23:20:44.696', N'TB_PARCELASPAGAS', N'ODBCConnectorPX', N'DBBUCC', N'TB_CLIENTES_FLEX_COB_CVP_SNAPSHOT', N'BI_CVP.dsx', '2026-06-03 23:20:44.696', N'dsx_auto', NULL, NULL),
(171, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BiCvp_Assistencia_00_ext_mkt_cloud', N'origem', N'Tabela', N'SEGURADOS_VGAP', '2026-06-05 18:12:43.402', '2026-06-05 18:12:43.402', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(172, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BiCvp_Assistencia_00_ext_mkt_cloud', N'origem', N'Tabela', N'APOLICE_COBERTURAS', '2026-06-05 18:12:43.429', '2026-06-05 18:12:43.429', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(173, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BiCvp_Assistencia_00_ext_mkt_cloud', N'destino', N'Arquivo', N'DS_EXT_SEGURADOS_VGAP', '2026-06-05 18:12:43.451', '2026-06-05 18:12:43.451', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(174, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BiCvp_Assistencia_01_ins_mkt_cloud', N'origem', N'Arquivo', N'DS_EXT_SEGURADOS_VGAP', '2026-06-05 18:14:00.706', '2026-06-05 18:14:00.706', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(175, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BiCvp_Assistencia_01_ins_mkt_cloud', N'destino', N'Tabela', N'TB_PROPOSTAS_VGAP', '2026-06-05 18:14:00.727', '2026-06-05 18:14:00.727', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(176, N'SHELL_LIMPA_FS_DATASTAGE', N'EXEC_ALL_ZIPS.sh', N'origem', N'Query', N'EXEC SHELL', '2026-06-08 10:32:31.830', '2026-06-08 10:32:31.830', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(177, N'SHELL_LIMPA_FS_DATASTAGE', N'EXEC_ALL_ZIPS.sh', N'destino', N'Query', N'EXEC SHELL', '2026-06-08 10:32:31.933', '2026-06-08 10:32:31.933', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(178, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'Seq_Flexibilização_Cobrança', N'origem', N'Tabela', N'geral', '2026-06-09 17:43:56.503', '2026-06-09 17:43:56.503', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(179, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'Seq_Flexibilização_Cobrança', N'destino', N'Tabela', N'geral', '2026-06-09 17:43:56.530', '2026-06-09 17:43:56.530', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(182, N'DATASTAGE_MALHA_VIDA', N'SeqExecCargaVida', N'origem', N'Tabela', N'geral', '2026-06-09 21:17:58.607', '2026-06-09 21:17:58.607', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(183, N'DATASTAGE_MALHA_VIDA', N'SeqExecCargaVida', N'destino', N'Tabela', N'geral', '2026-06-09 21:17:58.631', '2026-06-09 21:17:58.631', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(186, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext', N'origem', N'ODBC', N'AUTO_105_DADOS_SIGDC_MOV', '2026-06-11 14:46:54.832', '2026-06-11 14:46:54.832', N'AUTO_105_DADOS_SIGDC_MOV', N'ODBCConnectorPX', N'DCDB01', N'DCDB01_CVP.SISDC.AUTO_105_DADOS_SIGDC_MOV
[SQL14', N'BI_CVP.dsx', '2026-06-11 14:45:40', N'dsx_auto', NULL, NULL),
(187, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext', N'destino', N'Arquivo', N'DS_EXT_GECOMIS', '2026-06-11 14:46:54.881', '2026-06-11 14:46:54.881', N'DS_EXT_GECOMIS', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-11 14:45:40', N'dsx_auto', N'#SSD_DIROT.ParmDirFtpOut#DS_EXT_GECOMIS.dsx', NULL),
(188, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_02_ins', N'origem', N'Arquivo', N'DS_EXT_GECOMIS', '2026-06-11 14:54:36.696', '2026-06-11 14:54:36.696', N'DS_EXT_GECOMIS', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-11 14:54:33', N'dsx_auto', NULL, NULL),
(189, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_02_ins', N'destino', N'ODBC', N'INSERT_TB_GECOMIS_CVP_AUTO_105', '2026-06-11 14:54:36.720', '2026-06-11 14:54:36.720', N'INSERT_TB_GECOMIS_CVP_AUTO_105', N'ODBCConnectorPX', N'DMDB41', N'TB_GECOMIS_CVP_AUTO_105', N'BI_CVP.dsx', '2026-06-11 14:54:33', N'dsx_auto', NULL, NULL),
(190, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_01_ext', N'origem', N'ODBC', N'AUTO_105_DADOS_APOLICE', '2026-06-11 14:55:11.827', '2026-06-11 14:55:11.827', N'AUTO_105_DADOS_APOLICE', N'ODBCConnectorPX', N'DCDB01', N'DCDB01_CVP.SISDC.AUTO_105_DADOS_SIGDC_MOV', N'BI_CVP.dsx', '2026-06-11 14:55:09', N'dsx_auto', NULL, NULL),
(191, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_01_ext', N'destino', N'Arquivo', N'DS_EXT_GECOMIS_APOLICE', '2026-06-11 14:55:11.850', '2026-06-11 14:55:11.850', N'DS_EXT_GECOMIS_APOLICE', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-11 14:55:09', N'dsx_auto', N'#SSD_DIROT.ParmDirFtpOut#DS_EXT_GECOMIS_APOLICE.dsx', NULL),
(192, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_02_ins', N'origem', N'Arquivo', N'DS_EXT_GECOMIS_APOLICE', '2026-06-11 14:56:16.113', '2026-06-11 14:56:16.113', N'DS_EXT_GECOMIS_APOLICE', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-11 14:56:06', N'dsx_auto', NULL, NULL),
(193, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_02_ins', N'destino', N'ODBC', N'INSERT_TB_GECOMIS_CVP_F_APOLICE', '2026-06-11 14:56:16.158', '2026-06-11 14:56:16.158', N'INSERT_TB_GECOMIS_CVP_F_APOLICE', N'ODBCConnectorPX', N'DMDB41', N'TB_GECOMIS_CVP_F_APOLICE', N'BI_CVP.dsx', '2026-06-11 14:56:06', N'dsx_auto', NULL, NULL),
(194, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_01_ext', N'origem', N'ODBC', N'CCA', '2026-06-11 14:57:13.619', '2026-06-11 14:57:13.619', N'CCA', N'ODBCConnectorPX', N'DMDB41', N'[AGSQLCVP14
[SQL14', N'BI_CVP.dsx', '2026-06-11 14:57:10', N'dsx_auto', NULL, NULL),
(195, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_01_ext', N'destino', N'Arquivo', N'DS_EXT_GECOMIS_CCA', '2026-06-11 14:57:13.639', '2026-06-11 14:57:13.639', N'DS_EXT_GECOMIS_CCA', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-11 14:57:10', N'dsx_auto', N'#SSD_DIROT.ParmDirFtpOut#DS_EXT_GECOMIS_CCA.dsx', NULL),
(196, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_02_ins', N'origem', N'Arquivo', N'DS_EXT_GECOMIS_CCA', '2026-06-11 14:58:11.646', '2026-06-11 14:58:11.646', N'DS_EXT_GECOMIS_CCA', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-11 14:58:07', N'dsx_auto', NULL, NULL),
(197, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_02_ins', N'destino', N'ODBC', N'TB_GECOMIS_CVP_F_CCA', '2026-06-11 14:58:11.670', '2026-06-11 14:58:11.670', N'TB_GECOMIS_CVP_F_CCA', N'ODBCConnectorPX', N'DMDB41', N'TB_GECOMIS_CVP_F_CCA', N'BI_CVP.dsx', '2026-06-11 14:58:07', N'dsx_auto', NULL, NULL),
(198, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_01_ext', N'origem', N'ODBC', N'VALIDADOR', '2026-06-11 15:11:58.562', '2026-06-11 15:11:58.562', N'VALIDADOR', N'ODBCConnectorPX', N'DMDB41', N'[AGSQLCVP14
[SQL14', N'BI_CVP.dsx', '2026-06-11 15:11:49', N'dsx_auto', NULL, NULL),
(199, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_01_ext', N'destino', N'Arquivo', N'DS_EXT_GECOMIS_VALIDADOR', '2026-06-11 15:11:58.734', '2026-06-11 15:11:58.734', N'DS_EXT_GECOMIS_VALIDADOR', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-11 15:11:49', N'dsx_auto', N'#SSD_DIROT.ParmDirFtpOut#DS_EXT_GECOMIS_VALIDADOR.dsx', NULL),
(200, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_02_ins', N'origem', N'Arquivo', N'DS_EXT_GECOMIS_VALIDADOR', '2026-06-11 15:13:29.812', '2026-06-11 15:13:29.812', N'DS_EXT_GECOMIS_VALIDADOR', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-11 15:13:26', N'dsx_auto', NULL, NULL),
(201, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_02_ins', N'destino', N'ODBC', N'TB_GECOMIS_CVP_F_VALIDADOR', '2026-06-11 15:13:29.838', '2026-06-11 15:13:29.838', N'TB_GECOMIS_CVP_F_VALIDADOR', N'ODBCConnectorPX', N'DMDB41', N'TB_GECOMIS_CVP_F_VALIDADOR', N'BI_CVP.dsx', '2026-06-11 15:13:26', N'dsx_auto', NULL, NULL),
(202, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_001', N'origem', N'ODBCConnectorPX', N'CONSULTA_PREST', '2026-06-12 09:42:31.640', '2026-06-12 09:42:31.640', N'CONSULTA_PREST', N'ODBCConnectorPX', NULL, N'DM_ODS_PRS_CONTRATOS_U
DM_DIM_PRODUTO
DMDB41.DBO.BI_CONTROLE_CARGA', N'BI_CVP.dsx', '2026-06-12 09:42:31.640', N'dsx_auto', NULL, NULL),
(203, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_001', N'origem', N'ODBCConnectorPX', N'CONSULTA_PREV', '2026-06-12 09:42:31.646', '2026-06-12 09:42:31.646', N'CONSULTA_PREV', N'ODBCConnectorPX', NULL, N'dbo.SB_T_202101_BENEFICIO_CERTIFICADO', N'BI_CVP.dsx', '2026-06-12 09:42:31.646', N'dsx_auto', NULL, NULL),
(204, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_001', N'origem', N'ODBCConnectorPX', N'CONSULTA_VIDA', '2026-06-12 09:42:31.650', '2026-06-12 09:42:31.650', N'CONSULTA_VIDA', N'ODBCConnectorPX', NULL, N'PROPOSTAS_VA
HIS_COBER_PROPOST
VG_APOLICE_COB_GAR
VG_GRUPO_COB_CS_ETARIA
VG_FAIXA_ETARIA
VG_FAIXA_CAP_SEGUR
VG_GARANTIAE
VG_GRUPO_COBERTURAF
PRODUTOS_VG
PRODUTO
SUBGRUPOS_VGAP
PROPOSTA_FIDELIZ
SEGURADOSVGAP_HIST
VG_CARENCIA_MSG', N'BI_CVP.dsx', '2026-06-12 09:42:31.650', N'dsx_auto', NULL, NULL),
(205, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_001', N'origem', N'ODBCConnectorPX', N'Copy_of_CONSULTA_PREST', '2026-06-12 09:42:31.650', '2026-06-12 09:42:31.650', N'Copy_of_CONSULTA_PREST', N'ODBCConnectorPX', NULL, N'DMDB41.DBO.BI_CONTROLE_CARGA', N'BI_CVP.dsx', '2026-06-12 09:42:31.650', N'dsx_auto', NULL, NULL),
(206, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_001', N'origem', N'ODBCConnectorPX', N'Copy_of_CONSULTA_VIDA', '2026-06-12 09:42:31.756', '2026-06-12 09:42:31.756', N'Copy_of_CONSULTA_VIDA', N'ODBCConnectorPX', NULL, N'SEGURADOS_VGAP
VG_COBERTURAS_SUBG
CLIENTES
VG_ACESSORIO', N'BI_CVP.dsx', '2026-06-12 09:42:31.756', N'dsx_auto', NULL, NULL),
(207, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_001', N'origem', N'ODBCConnectorPX', N'Copy_of_CONSULTA_VIDA_COBERTURA_BASICA_BILHETE', '2026-06-12 09:42:31.760', '2026-06-12 09:42:31.760', N'Copy_of_CONSULTA_VIDA_COBERTURA_BASICA_BILHETE', N'ODBCConnectorPX', NULL, N'BILHETE
APOLICE_COBERTURAS
BILHETE_COBERTURA
COBERTURAS_DESCR', N'BI_CVP.dsx', '2026-06-12 09:42:31.760', N'dsx_auto', NULL, NULL),
(208, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_001', N'transformacao', N'PxFunnel', N'Copy_of_Funnel_2', '2026-06-12 09:42:31.760', '2026-06-12 09:42:31.760', N'Copy_of_Funnel_2', N'PxFunnel', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 09:42:31.760', N'dsx_auto', NULL, NULL),
(209, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_001', N'transformacao', N'PxFunnel', N'Funnel_2', '2026-06-12 09:42:31.766', '2026-06-12 09:42:31.766', N'Funnel_2', N'PxFunnel', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 09:42:31.766', N'dsx_auto', NULL, NULL),
(210, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_001', N'transformacao', N'PxLookup', N'Lookup_23', '2026-06-12 09:42:31.773', '2026-06-12 09:42:31.773', N'Lookup_23', N'PxLookup', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 09:42:31.773', N'dsx_auto', NULL, NULL),
(211, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_001', N'transformacao', N'PxRemDup', N'Remove_Duplicates_16', '2026-06-12 09:42:31.776', '2026-06-12 09:42:31.776', N'Remove_Duplicates_16', N'PxRemDup', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 09:42:31.776', N'dsx_auto', NULL, NULL),
(212, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_001', N'transformacao', N'PxSort', N'Sort_17', '2026-06-12 09:42:31.780', '2026-06-12 09:42:31.780', N'Sort_17', N'PxSort', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 09:42:31.780', N'dsx_auto', NULL, NULL),
(213, N'datastage_coberturas_unificadas_diario', N'BiCVP_CoberturasUnificadas_001', N'destino', N'Arquivo', N'Data_Set_4', '2026-06-12 09:42:31.783', '2026-06-12 09:42:31.783', N'Data_Set_4', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_COBERTURA', N'BI_CVP.dsx', '2026-06-12 09:42:31.783', N'dsx_auto', NULL, NULL),
(214, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_ext_vida', N'origem', N'ODBC', N'APOLICE_ESPECIFICA', '2026-06-12 14:50:01.685', '2026-06-12 14:50:01.685', N'APOLICE_ESPECIFICA', N'ODBCConnectorPX', NULL, N'SEGURADOS_VGAP
CLIENTES
ENDERECOS
PRODUTOS_VG
CONDICOES_TECNICAS
VG_COBERTURAS_SUBG
VG_ACESSORIO
PRODUTO
PROPOSTAS_VA', N'BI_CVP.dsx', '2026-06-12 14:49:49', N'dsx_auto', NULL, NULL),
(215, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_ext_vida', N'origem', N'ODBC', N'BILHETES', '2026-06-12 14:50:01.858', '2026-06-12 14:50:01.858', N'BILHETES', N'ODBCConnectorPX', NULL, N'BILHETE
APOLICES
APOLICE_COBERTURAS
PRODUTO
BILHETE_COBERTURA
VG_ACESSORIO', N'BI_CVP.dsx', '2026-06-12 14:49:49', N'dsx_auto', NULL, NULL),
(216, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_ext_vida', N'origem', N'ODBC', N'APOLICE_ESPECIFICA_2', '2026-06-12 14:50:02.135', '2026-06-12 14:50:02.135', N'APOLICE_ESPECIFICA_2', N'ODBCConnectorPX', NULL, N'SEGURADOS_VGAP
VG_COBERTURAS_SUBG
VG_ACESSORIO
CLIENTES
ENDERECOS
PRODUTOS_VG
CONDICOES_TECNICAS
PRODUTO
PROPOSTAS_VA', N'BI_CVP.dsx', '2026-06-12 14:49:49', N'dsx_auto', NULL, NULL),
(217, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_ext_vida', N'origem', N'ODBC', N'COBERTURAS_BASICAS_2', '2026-06-12 14:50:02.205', '2026-06-12 14:50:02.205', N'COBERTURAS_BASICAS_2', N'ODBCConnectorPX', NULL, N'PROPOSTAS_VA
CLIENTES
ENDERECOS
SEGURADOS_VGAP
VG_COBERTURAS_SUBG
VG_ACESSORIO
APOLICES
HIS_COBER_PROPOST', N'BI_CVP.dsx', '2026-06-12 14:49:49', N'dsx_auto', NULL, NULL),
(218, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_ext_vida', N'transformacao', N'PxFunnel', N'Funnel_2', '2026-06-12 14:50:02.230', '2026-06-12 14:50:02.230', N'Funnel_2', N'PxFunnel', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:49:49', N'dsx_auto', NULL, NULL),
(219, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_ext_vida', N'transformacao', N'PxRemDup', N'Remove_Duplicates_16', '2026-06-12 14:50:02.315', '2026-06-12 14:50:02.315', N'Remove_Duplicates_16', N'PxRemDup', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:49:49', N'dsx_auto', NULL, NULL),
(220, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_ext_vida', N'transformacao', N'PxSort', N'Sort_17', '2026-06-12 14:50:02.350', '2026-06-12 14:50:02.350', N'Sort_17', N'PxSort', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:49:49', N'dsx_auto', NULL, NULL),
(221, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_ext_vida', N'destino', N'Arquivo', N'DS_ASSISTENCIAS_VIDA', '2026-06-12 14:50:02.377', '2026-06-12 14:50:02.377', N'DS_ASSISTENCIAS_VIDA', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:49:49', N'dsx_auto', N'#SSD_DIROT.ParmDirDst#DS_ASSISTENCIAS_VIDA', NULL),
(222, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_001', N'origem', N'ODBC', N'CONSULTA_PREST', '2026-06-12 14:50:40.517', '2026-06-12 14:50:40.517', N'CONSULTA_PREST', N'ODBCConnectorPX', N'DMDB42', N'DM_ODS_PRS_CONTRATOS_U
dbo.DM_STG_VALID_FUNERAL_CROT', N'BI_CVP.dsx', '2026-06-12 14:50:29', N'dsx_auto', NULL, NULL),
(223, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_001', N'origem', N'ODBC', N'CONSULTA_PREV', '2026-06-12 14:50:40.539', '2026-06-12 14:50:40.539', N'CONSULTA_PREV', N'ODBCConnectorPX', N'DMDB11', NULL, N'BI_CVP.dsx', '2026-06-12 14:50:29', N'dsx_auto', NULL, NULL),
(224, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_001', N'origem', N'Arquivo', N'DS_ASSISTENCIAS_VIDA', '2026-06-12 14:50:40.555', '2026-06-12 14:50:40.555', N'DS_ASSISTENCIAS_VIDA', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:50:29', N'dsx_auto', NULL, NULL),
(225, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_001', N'transformacao', N'PxFunnel', N'Funnel_2', '2026-06-12 14:50:40.578', '2026-06-12 14:50:40.578', N'Funnel_2', N'PxFunnel', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:50:29', N'dsx_auto', NULL, NULL),
(226, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_001', N'transformacao', N'PxRemDup', N'Remove_Duplicates_16', '2026-06-12 14:50:40.591', '2026-06-12 14:50:40.591', N'Remove_Duplicates_16', N'PxRemDup', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:50:29', N'dsx_auto', NULL, NULL),
(227, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_001', N'transformacao', N'PxSort', N'Sort_17', '2026-06-12 14:50:40.667', '2026-06-12 14:50:40.667', N'Sort_17', N'PxSort', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:50:29', N'dsx_auto', NULL, NULL),
(228, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_001', N'destino', N'Arquivo', N'DS_ASSISTENCIAS', '2026-06-12 14:50:40.692', '2026-06-12 14:50:40.692', N'DS_ASSISTENCIAS', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:50:29', N'dsx_auto', N'#SSD_DIROT.ParmDirDst#DS_ASSISTENCIAS', NULL),
(229, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_002', N'origem', N'Arquivo', N'DS_ASSISTENCIAS', '2026-06-12 14:51:26.069', '2026-06-12 14:51:26.069', N'DS_ASSISTENCIAS', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:51:17', N'dsx_auto', NULL, NULL),
(230, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_002', N'transformacao', N'PxCopy', N'Copy_12', '2026-06-12 14:51:26.108', '2026-06-12 14:51:26.108', N'Copy_12', N'PxCopy', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:51:17', N'dsx_auto', NULL, NULL),
(231, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_002', N'destino', N'ODBC', N'CONSULTA_ASSISTENCIAS', '2026-06-12 14:51:26.129', '2026-06-12 14:51:26.129', N'CONSULTA_ASSISTENCIAS', N'ODBCConnectorPX', N'DMDB41', N'dbo.DM_CONTRATO_ASSISTENCIA_CVP', N'BI_CVP.dsx', '2026-06-12 14:51:17', N'dsx_auto', NULL, NULL),
(232, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_002', N'destino', N'ODBC', N'CONSULTA_ASSISTENCIAS_SQL_69', '2026-06-12 14:51:26.147', '2026-06-12 14:51:26.147', N'CONSULTA_ASSISTENCIAS_SQL_69', N'ODBCConnectorPX', N'DBBUCC', N'dbo.DM_CONTRATO_ASSISTENCIA_CVP', N'BI_CVP.dsx', '2026-06-12 14:51:17', N'dsx_auto', NULL, NULL),
(233, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_003', N'origem', N'Arquivo', N'DS_ASSISTENCIAS', '2026-06-12 14:51:55.429', '2026-06-12 14:51:55.429', N'DS_ASSISTENCIAS', N'PxDataSet', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:51:52', N'dsx_auto', NULL, NULL),
(234, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_003', N'origem', N'ODBC', N'CONSULTA_ASSISTENCIAS', '2026-06-12 14:51:55.446', '2026-06-12 14:51:55.446', N'CONSULTA_ASSISTENCIAS', N'ODBCConnectorPX', N'DMDB41', N'dbo.DM_CONTRATO_ASSISTENCIA_CVP', N'BI_CVP.dsx', '2026-06-12 14:51:52', N'dsx_auto', NULL, NULL),
(235, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_003', N'transformacao', N'PxJoin', N'Join_21', '2026-06-12 14:51:55.461', '2026-06-12 14:51:55.461', N'Join_21', N'PxJoin', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:51:52', N'dsx_auto', NULL, NULL),
(236, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_003', N'transformacao', N'PxFilter', N'Filter_26', '2026-06-12 14:51:55.480', '2026-06-12 14:51:55.480', N'Filter_26', N'PxFilter', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:51:52', N'dsx_auto', NULL, NULL),
(237, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_003', N'transformacao', N'PxSort', N'Sort_36', '2026-06-12 14:51:55.496', '2026-06-12 14:51:55.496', N'Sort_36', N'PxSort', NULL, NULL, N'BI_CVP.dsx', '2026-06-12 14:51:52', N'dsx_auto', NULL, NULL),
(238, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'BICVP_AssistenciasUnificadas_003', N'destino', N'ODBC', N'Copy_of_CONSULTA_ASSISTENCIAS', '2026-06-12 14:51:55.514', '2026-06-12 14:51:55.514', N'Copy_of_CONSULTA_ASSISTENCIAS', N'ODBCConnectorPX', N'DMDB41', N'[DM_CONTRATO_ASSISTENCIA_CVP]', N'BI_CVP.dsx', '2026-06-12 14:51:52', N'dsx_auto', NULL, NULL);
SET IDENTITY_INSERT dbo.[etl_job_lineage] OFF;
GO

-- ===== etl_job_execution (209 linhas) =====
INSERT INTO dbo.[etl_job_execution] ([execution_id], [project], [job_name], [pipeline], [host], [start_time], [end_time], [duration_seconds], [status_code], [attempt], [log_file], [created_at], [status], [updated_at], [task_id]) VALUES
(N'20260527T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-29 09:23:46', '2026-05-29 09:33:27', 581, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260527T130000.log', '2026-05-29 09:23:46.953', N'SUCCESS', '2026-05-29 09:33:27.523', N'BiCVP_CoberturasUnificadas_001'),
(N'20260527T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-29 09:33:28', '2026-05-29 09:37:05', 217, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260527T130000.log', '2026-05-29 09:33:28.536', N'SUCCESS', '2026-05-29 09:37:05.520', N'BiCVP_CoberturasUnificadas_002'),
(N'20260527T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-29 09:37:07', '2026-05-29 09:37:18', 11, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260527T130000.log', '2026-05-29 09:37:07.260', N'SUCCESS', '2026-05-29 09:37:18.653', N'BiCVP_CoberturasUnificadas_003'),
(N'20260527T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-29 09:37:19', '2026-05-29 09:46:50', 571, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260527T130000.log', '2026-05-29 09:37:19.790', N'SUCCESS', '2026-05-29 09:46:50.670', N'BiCVP_CoberturasUnificadas_004'),
(N'20260528T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-29 10:00:00', '2026-05-29 10:08:46', 526, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260528T130000.log', '2026-05-29 10:00:00.723', N'SUCCESS', '2026-05-29 10:08:46.343', N'BiCVP_CoberturasUnificadas_001'),
(N'20260528T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-29 10:08:47', '2026-05-29 10:16:00', 433, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260528T130000.log', '2026-05-29 10:08:47.220', N'SUCCESS', '2026-05-29 10:16:00.313', N'BiCVP_CoberturasUnificadas_002'),
(N'20260528T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-29 10:16:01', '2026-05-29 10:17:51', 110, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260528T130000.log', '2026-05-29 10:16:01.276', N'SUCCESS', '2026-05-29 10:17:51.136', N'BiCVP_CoberturasUnificadas_003'),
(N'20260528T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-29 10:17:52', '2026-05-29 10:35:28', 1056, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260528T130000.log', '2026-05-29 10:17:52.390', N'SUCCESS', '2026-05-29 10:35:28.273', N'BiCVP_CoberturasUnificadas_004'),
(N'20260529T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-30 10:00:01', '2026-05-30 10:10:42', 641, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260529T130000.log', '2026-05-30 10:00:01.170', N'SUCCESS', '2026-05-30 10:10:42.516', N'BiCVP_CoberturasUnificadas_001'),
(N'20260529T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-30 10:10:43', '2026-05-30 10:14:28', 225, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260529T130000.log', '2026-05-30 10:10:43.380', N'SUCCESS', '2026-05-30 10:14:28.506', N'BiCVP_CoberturasUnificadas_002'),
(N'20260529T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-30 10:14:29', '2026-05-30 10:14:37', 8, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260529T130000.log', '2026-05-30 10:14:29.576', N'SUCCESS', '2026-05-30 10:14:37.833', N'BiCVP_CoberturasUnificadas_003'),
(N'20260529T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-30 10:14:38', '2026-05-30 10:24:05', 567, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260529T130000.log', '2026-05-30 10:14:38.810', N'SUCCESS', '2026-05-30 10:24:05.523', N'BiCVP_CoberturasUnificadas_004'),
(N'20260530T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-31 10:00:01', '2026-05-31 10:08:51', 530, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260530T130000.log', '2026-05-31 10:00:01.150', N'SUCCESS', '2026-05-31 10:08:51.600', N'BiCVP_CoberturasUnificadas_001'),
(N'20260530T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-31 10:08:52', '2026-05-31 10:12:57', 245, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260530T130000.log', '2026-05-31 10:08:52.840', N'SUCCESS', '2026-05-31 10:12:57.330', N'BiCVP_CoberturasUnificadas_002'),
(N'20260530T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-31 10:12:58', '2026-05-31 10:13:02', 4, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260530T130000.log', '2026-05-31 10:12:58.383', N'SUCCESS', '2026-05-31 10:13:02.426', N'BiCVP_CoberturasUnificadas_003'),
(N'20260530T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-05-31 10:13:03', '2026-05-31 10:20:26', 443, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260530T130000.log', '2026-05-31 10:13:03.383', N'SUCCESS', '2026-05-31 10:20:26.623', N'BiCVP_CoberturasUnificadas_004'),
(N'20260531T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-06-01 10:00:01', '2026-06-01 10:09:44', 583, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260531T130000.log', '2026-06-01 10:00:01.670', N'SUCCESS', '2026-06-01 10:09:44.340', N'BiCVP_CoberturasUnificadas_001'),
(N'20260531T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-06-01 10:09:44', '2026-06-01 10:15:21', 337, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260531T130000.log', '2026-06-01 10:09:45.016', N'SUCCESS', '2026-06-01 10:15:21.610', N'BiCVP_CoberturasUnificadas_002'),
(N'20260531T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-06-01 10:15:22', '2026-06-01 10:15:30', 8, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260531T130000.log', '2026-06-01 10:15:22.526', N'SUCCESS', '2026-06-01 10:15:30.520', N'BiCVP_CoberturasUnificadas_003'),
(N'20260531T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'83b5620f4909', '2026-06-01 10:15:31', '2026-06-01 10:24:36', 545, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260531T130000.log', '2026-06-01 10:15:31.623', N'SUCCESS', '2026-06-01 10:24:36.816', N'BiCVP_CoberturasUnificadas_004'),
(N'20260601T124500', N'BI_CVP', N'BiCVP_ContasBancarias_001', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'94d4f38795cd', '2026-06-02 09:50:15', '2026-06-02 10:03:45', 810, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_001/BiCVP_ContasBancarias_001_20260601T124500.log', '2026-06-02 09:50:15.683', N'SUCCESS', '2026-06-02 10:03:45.773', N'BiCVP_ContasBancarias_001'),
(N'20260601T124500', N'BI_CVP', N'BiCVP_ContasBancarias_002', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'94d4f38795cd', '2026-06-02 10:03:46', '2026-06-02 10:05:52', 126, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_002/BiCVP_ContasBancarias_002_20260601T124500.log', '2026-06-02 10:03:46.893', N'SUCCESS', '2026-06-02 10:05:52.290', N'BiCVP_ContasBancarias_002'),
(N'20260601T124500', N'BI_CVP', N'BiCVP_ContasBancarias_003', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'94d4f38795cd', '2026-06-02 10:05:53', '2026-06-02 10:06:37', 44, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_003/BiCVP_ContasBancarias_003_20260601T124500.log', '2026-06-02 10:05:53.350', N'SUCCESS', '2026-06-02 10:06:37.996', N'BiCVP_ContasBancarias_003'),
(N'20260601T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-02 10:00:01', '2026-06-02 10:12:44', 763, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260601T130000.log', '2026-06-02 10:00:01.253', N'FAILED', '2026-06-02 10:12:44.326', N'BiCVP_CoberturasUnificadas_001'),
(N'20260601T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-02 10:12:45', '2026-06-02 10:15:24', 159, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260601T130000.log', '2026-06-02 10:12:45.513', N'FAILED', '2026-06-02 10:15:24.520', N'BiCVP_CoberturasUnificadas_002'),
(N'20260601T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-02 10:15:25', '2026-06-02 10:17:43', 138, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260601T130000.log', '2026-06-02 10:15:25.570', N'FAILED', '2026-06-02 10:17:44.070', N'BiCVP_CoberturasUnificadas_003'),
(N'20260601T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-02 10:17:45', '2026-06-02 10:20:01', 136, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260601T130000.log', '2026-06-02 10:17:45.163', N'FAILED', '2026-06-02 10:20:01.836', N'BiCVP_CoberturasUnificadas_004'),
(N'20260602T023000', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-03 23:26:11', '2026-06-03 23:27:23', 72, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260602T023000.log', '2026-06-03 23:26:12.103', N'SUCCESS', '2026-06-03 23:27:23.970', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260602T023000', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-03 23:27:24', '2026-06-03 23:27:30', 6, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260602T023000.log', '2026-06-03 23:27:24.816', N'SUCCESS', '2026-06-03 23:27:31.163', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260602T023000', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-03 23:27:32', '2026-06-03 23:29:19', 107, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260602T023000.log', '2026-06-03 23:27:32.350', N'SUCCESS', '2026-06-03 23:29:19.903', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260602T023000', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-03 23:29:20', '2026-06-03 23:29:27', 7, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260602T023000.log', '2026-06-03 23:29:20.790', N'SUCCESS', '2026-06-03 23:29:27.593', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260602T124500', N'BI_CVP', N'BiCVP_ContasBancarias_001', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'94d4f38795cd', '2026-06-03 09:45:01', '2026-06-03 10:05:20', 1219, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_001/BiCVP_ContasBancarias_001_20260602T124500.log', '2026-06-03 09:45:01.313', N'SUCCESS', '2026-06-03 10:05:20.653', N'BiCVP_ContasBancarias_001'),
(N'20260602T124500', N'BI_CVP', N'BiCVP_ContasBancarias_002', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'94d4f38795cd', '2026-06-03 10:05:21', '2026-06-03 10:09:39', 258, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_002/BiCVP_ContasBancarias_002_20260602T124500.log', '2026-06-03 10:05:21.550', N'SUCCESS', '2026-06-03 10:09:39.500', N'BiCVP_ContasBancarias_002'),
(N'20260602T124500', N'BI_CVP', N'BiCVP_ContasBancarias_003', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'94d4f38795cd', '2026-06-03 10:09:41', '2026-06-03 10:11:20', 99, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_003/BiCVP_ContasBancarias_003_20260602T124500.log', '2026-06-03 10:09:41.243', N'SUCCESS', '2026-06-03 10:11:20.563', N'BiCVP_ContasBancarias_003'),
(N'20260602T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-03 10:00:01', '2026-06-03 10:18:15', 1094, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260602T130000.log', '2026-06-03 10:00:01.793', N'FAILED', '2026-06-03 10:18:15.380', N'BiCVP_CoberturasUnificadas_001'),
(N'20260602T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-03 10:18:16', '2026-06-03 10:23:51', 335, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260602T130000.log', '2026-06-03 10:18:16.500', N'FAILED', '2026-06-03 10:23:51.670', N'BiCVP_CoberturasUnificadas_002'),
(N'20260602T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-03 10:23:52', '2026-06-03 10:26:17', 145, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260602T130000.log', '2026-06-03 10:23:52.386', N'FAILED', '2026-06-03 10:26:17.800', N'BiCVP_CoberturasUnificadas_003'),
(N'20260602T130000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-03 10:26:18', '2026-06-03 10:28:38', 140, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260602T130000.log', '2026-06-03 10:26:18.810', N'FAILED', '2026-06-03 10:28:38.400', N'BiCVP_CoberturasUnificadas_004'),
(N'20260602T184746', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-02 15:47:47', '2026-06-02 15:58:14', 627, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260602T184746.log', '2026-06-02 15:47:47.540', N'SUCCESS', '2026-06-02 15:58:14.296', N'BiCVP_CoberturasUnificadas_001'),
(N'20260602T184746', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-02 15:58:16', '2026-06-02 16:02:57', 281, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260602T184746.log', '2026-06-02 15:58:16.050', N'SUCCESS', '2026-06-02 16:02:57.270', N'BiCVP_CoberturasUnificadas_002'),
(N'20260602T184746', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-02 16:02:58', '2026-06-02 16:03:25', 27, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260602T184746.log', '2026-06-02 16:02:58.330', N'SUCCESS', '2026-06-02 16:03:26.070', N'BiCVP_CoberturasUnificadas_003'),
(N'20260602T184746', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-02 16:03:27', '2026-06-02 16:12:45', 558, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260602T184746.log', '2026-06-02 16:03:27.046', N'SUCCESS', '2026-06-02 16:12:45.553', N'BiCVP_CoberturasUnificadas_004'),
(N'20260603T023000', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-03 23:30:01', '2026-06-03 23:31:05', 64, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260603T023000.log', '2026-06-03 23:30:01.400', N'SUCCESS', '2026-06-03 23:31:05.363', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260603T023000', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-03 23:31:06', '2026-06-03 23:31:14', 8, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260603T023000.log', '2026-06-03 23:31:06.386', N'SUCCESS', '2026-06-03 23:31:14.326', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260603T023000', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-03 23:31:15', '2026-06-03 23:32:54', 99, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260603T023000.log', '2026-06-03 23:31:15.416', N'SUCCESS', '2026-06-03 23:32:54.436', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260603T023000', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-03 23:32:55', '2026-06-03 23:33:00', 5, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260603T023000.log', '2026-06-03 23:32:55.323', N'SUCCESS', '2026-06-03 23:33:00.856', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260603T113000', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-04 08:30:01', '2026-06-04 08:31:16', 75, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260603T113000.log', '2026-06-04 08:30:01.370', N'SUCCESS', '2026-06-04 08:31:16.276', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260603T113000', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-04 08:31:17', '2026-06-04 08:33:07', 110, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260603T113000.log', '2026-06-04 08:31:18.553', N'SUCCESS', '2026-06-04 08:33:07.820', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260603T113000', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-04 08:33:08', '2026-06-04 08:39:04', 356, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260603T113000.log', '2026-06-04 08:33:10.086', N'SUCCESS', '2026-06-04 08:39:04.350', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260603T113000', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-04 08:39:05', '2026-06-04 08:39:11', 6, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260603T113000.log', '2026-06-04 08:39:05.190', N'SUCCESS', '2026-06-04 08:39:11.860', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260603T120000', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-04 19:44:33', '2026-06-04 19:45:19', 46, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260603T120000.log', '2026-06-04 19:44:33.926', N'SUCCESS', '2026-06-04 19:45:20.013', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260603T120000', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-04 19:45:21', '2026-06-04 19:45:31', 10, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260603T120000.log', '2026-06-04 19:45:21.260', N'SUCCESS', '2026-06-04 19:45:31.383', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260603T120000', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-04 19:45:32', '2026-06-04 19:47:30', 118, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260603T120000.log', '2026-06-04 19:45:32.330', N'SUCCESS', '2026-06-04 19:47:30.360', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260603T120000', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-04 19:47:31', '2026-06-04 19:47:37', 6, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260603T120000.log', '2026-06-04 19:47:31.620', N'SUCCESS', '2026-06-04 19:47:37.850', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260603T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-04 09:00:01', '2026-06-04 09:18:21', 1100, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260603T120000.log', '2026-06-04 09:00:01.343', N'SUCCESS', '2026-06-04 09:18:21.540', N'BiCVP_CoberturasUnificadas_001'),
(N'20260603T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-04 09:18:22', '2026-06-04 09:28:12', 590, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260603T120000.log', '2026-06-04 09:18:23.023', N'SUCCESS', '2026-06-04 09:28:12.573', N'BiCVP_CoberturasUnificadas_002'),
(N'20260603T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-04 09:28:13', '2026-06-04 09:28:24', 11, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260603T120000.log', '2026-06-04 09:28:13.410', N'SUCCESS', '2026-06-04 09:28:24.900', N'BiCVP_CoberturasUnificadas_003'),
(N'20260603T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-04 09:28:25', '2026-06-04 09:38:12', 587, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260603T120000.log', '2026-06-04 09:28:25.956', N'SUCCESS', '2026-06-04 09:38:12.810', N'BiCVP_CoberturasUnificadas_004'),
(N'20260603T124500', N'BI_CVP', N'BiCVP_ContasBancarias_001', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'94d4f38795cd', '2026-06-04 09:45:01', '2026-06-04 10:14:06', 1745, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_001/BiCVP_ContasBancarias_001_20260603T124500.log', '2026-06-04 09:45:01.096', N'SUCCESS', '2026-06-04 10:14:06.916', N'BiCVP_ContasBancarias_001'),
(N'20260603T124500', N'BI_CVP', N'BiCVP_ContasBancarias_002', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'94d4f38795cd', '2026-06-04 10:14:07', '2026-06-04 10:15:47', 100, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_002/BiCVP_ContasBancarias_002_20260603T124500.log', '2026-06-04 10:14:07.943', N'SUCCESS', '2026-06-04 10:15:47.983', N'BiCVP_ContasBancarias_002'),
(N'20260603T124500', N'BI_CVP', N'BiCVP_ContasBancarias_003', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'94d4f38795cd', '2026-06-04 10:15:48', '2026-06-04 10:16:01', 13, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_003/BiCVP_ContasBancarias_003_20260603T124500.log', '2026-06-04 10:15:49.030', N'SUCCESS', '2026-06-04 10:16:02.046', N'BiCVP_ContasBancarias_003'),
(N'20260603T214201', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-03 18:42:03', '2026-06-03 18:50:26', 503, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260603T214201.log', '2026-06-03 18:42:03.256', N'SUCCESS', '2026-06-03 18:50:26.890', N'BiCVP_CoberturasUnificadas_001'),
(N'20260603T214201', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-03 18:50:28', '2026-06-03 18:53:01', 153, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260603T214201.log', '2026-06-03 18:50:28.300', N'SUCCESS', '2026-06-03 18:53:01.450', N'BiCVP_CoberturasUnificadas_002'),
(N'20260603T214201', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-03 18:53:02', '2026-06-03 18:53:10', 8, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260603T214201.log', '2026-06-03 18:53:02.480', N'SUCCESS', '2026-06-03 18:53:10.426', N'BiCVP_CoberturasUnificadas_003'),
(N'20260603T214201', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-03 18:53:11', '2026-06-03 19:01:38', 507, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260603T214201.log', '2026-06-03 18:53:11.546', N'SUCCESS', '2026-06-03 19:01:40.893', N'BiCVP_CoberturasUnificadas_004'),
(N'20260604T024344', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-03 23:43:45', '2026-06-03 23:50:52', 427, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260604T024344.log', '2026-06-03 23:43:45.966', N'SUCCESS', '2026-06-03 23:50:52.190', N'BiCVP_CoberturasUnificadas_001'),
(N'20260604T024344', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-03 23:50:53', '2026-06-03 23:53:42', 169, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260604T024344.log', '2026-06-03 23:50:53.220', N'SUCCESS', '2026-06-03 23:53:42.723', N'BiCVP_CoberturasUnificadas_002'),
(N'20260604T024344', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-03 23:53:43', '2026-06-04 00:10:04', 981, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260604T024344.log', '2026-06-03 23:53:43.990', N'SUCCESS', '2026-06-04 00:10:04.460', N'BiCVP_CoberturasUnificadas_003'),
(N'20260604T024344', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-04 00:10:05', '2026-06-04 00:19:22', 557, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260604T024344.log', '2026-06-04 00:10:05.660', N'SUCCESS', '2026-06-04 00:19:22.553', N'BiCVP_CoberturasUnificadas_004'),
(N'20260604T100000', N'BI_CVP', N'BiCvp_Assistencia_00_ext_mkt_cloud', N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'71adb627cc1e', '2026-06-05 18:22:58', '2026-06-05 18:23:01', 3, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_Assistencia_00_ext_mkt_cloud/BiCvp_Assistencia_00_ext_mkt_cloud_20260604T100000.log', '2026-06-05 18:22:58.270', N'FAILED', '2026-06-05 18:23:01.463', N'BiCvp_Assistencia_00_ext_mkt_cloud'),
(N'20260604T120000', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-05 09:00:01', '2026-06-05 09:03:05', 184, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260604T120000.log', '2026-06-05 09:00:01.660', N'SUCCESS', '2026-06-05 09:03:07.570', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260604T120000', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-05 09:03:08', '2026-06-05 09:06:32', 204, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260604T120000.log', '2026-06-05 09:03:08.950', N'SUCCESS', '2026-06-05 09:06:33.206', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260604T120000', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-05 09:06:34', '2026-06-05 09:10:01', 207, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260604T120000.log', '2026-06-05 09:06:34.293', N'SUCCESS', '2026-06-05 09:10:01.590', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260604T120000', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'94d4f38795cd', '2026-06-05 09:10:02', '2026-06-05 09:12:28', 146, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260604T120000.log', '2026-06-05 09:10:02.606', N'SUCCESS', '2026-06-05 09:12:31.083', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260604T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-05 09:00:01', '2026-06-05 09:17:43', 1062, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260604T120000.log', '2026-06-05 09:00:01.720', N'SUCCESS', '2026-06-05 09:17:43.900', N'BiCVP_CoberturasUnificadas_001'),
(N'20260604T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-05 09:17:47', '2026-06-05 09:25:23', 456, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260604T120000.log', '2026-06-05 09:17:48.173', N'SUCCESS', '2026-06-05 09:25:23.553', N'BiCVP_CoberturasUnificadas_002'),
(N'20260604T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-05 09:25:24', '2026-06-05 09:25:53', 29, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260604T120000.log', '2026-06-05 09:25:24.986', N'SUCCESS', '2026-06-05 09:25:54.860', N'BiCVP_CoberturasUnificadas_003'),
(N'20260604T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'94d4f38795cd', '2026-06-05 09:25:55', '2026-06-05 09:41:12', 917, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260604T120000.log', '2026-06-05 09:25:56.040', N'SUCCESS', '2026-06-05 09:41:13.170', N'BiCVP_CoberturasUnificadas_004'),
(N'20260604T124500', N'BI_CVP', N'BiCVP_ContasBancarias_001', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'94d4f38795cd', '2026-06-05 09:45:01', '2026-06-05 10:07:11', 1330, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_001/BiCVP_ContasBancarias_001_20260604T124500.log', '2026-06-05 09:45:01.860', N'SUCCESS', '2026-06-05 10:07:11.883', N'BiCVP_ContasBancarias_001'),
(N'20260604T124500', N'BI_CVP', N'BiCVP_ContasBancarias_002', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'94d4f38795cd', '2026-06-05 10:07:12', '2026-06-05 10:09:54', 162, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_002/BiCVP_ContasBancarias_002_20260604T124500.log', '2026-06-05 10:07:12.893', N'SUCCESS', '2026-06-05 10:09:54.376', N'BiCVP_ContasBancarias_002'),
(N'20260604T124500', N'BI_CVP', N'BiCVP_ContasBancarias_003', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'94d4f38795cd', '2026-06-05 10:09:54', '2026-06-05 10:10:43', 49, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_003/BiCVP_ContasBancarias_003_20260604T124500.log', '2026-06-05 10:09:55.070', N'SUCCESS', '2026-06-05 10:10:43.800', N'BiCVP_ContasBancarias_003'),
(N'20260605T120000', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-06 09:00:01', '2026-06-06 09:01:25', 84, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260605T120000.log', '2026-06-06 09:00:01.310', N'SUCCESS', '2026-06-06 09:01:25.800', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260605T120000', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-06 09:01:26', '2026-06-06 09:03:52', 146, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260605T120000.log', '2026-06-06 09:01:26.873', N'SUCCESS', '2026-06-06 09:03:52.210', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260605T120000', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-06 09:03:53', '2026-06-06 09:06:22', 149, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260605T120000.log', '2026-06-06 09:03:53.350', N'SUCCESS', '2026-06-06 09:06:22.903', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260605T120000', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-06 09:06:23', '2026-06-06 09:06:33', 10, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260605T120000.log', '2026-06-06 09:06:23.846', N'SUCCESS', '2026-06-06 09:06:33.383', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260605T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-06 09:00:01', '2026-06-06 10:12:14', 4333, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260605T120000.log', '2026-06-06 09:00:01.276', N'SUCCESS', '2026-06-06 10:12:14.333', N'BiCVP_CoberturasUnificadas_001'),
(N'20260605T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-06 10:12:15', '2026-06-06 10:15:58', 223, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260605T120000.log', '2026-06-06 10:12:15.360', N'SUCCESS', '2026-06-06 10:15:58.376', N'BiCVP_CoberturasUnificadas_002'),
(N'20260605T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-06 10:15:59', '2026-06-06 10:16:11', 12, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260605T120000.log', '2026-06-06 10:15:59.423', N'SUCCESS', '2026-06-06 10:16:11.260', N'BiCVP_CoberturasUnificadas_003'),
(N'20260605T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-06 10:16:12', '2026-06-06 10:27:27', 675, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260605T120000.log', '2026-06-06 10:16:12.430', N'SUCCESS', '2026-06-06 10:27:27.913', N'BiCVP_CoberturasUnificadas_004'),
(N'20260605T124500', N'BI_CVP', N'BiCVP_ContasBancarias_001', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-06 09:45:00', '2026-06-06 09:57:23', 743, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_001/BiCVP_ContasBancarias_001_20260605T124500.log', '2026-06-06 09:45:00.836', N'SUCCESS', '2026-06-06 09:57:23.846', N'BiCVP_ContasBancarias_001'),
(N'20260605T124500', N'BI_CVP', N'BiCVP_ContasBancarias_002', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-06 09:57:24', '2026-06-06 09:58:33', 69, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_002/BiCVP_ContasBancarias_002_20260605T124500.log', '2026-06-06 09:57:24.850', N'SUCCESS', '2026-06-06 09:58:33.726', N'BiCVP_ContasBancarias_002'),
(N'20260605T124500', N'BI_CVP', N'BiCVP_ContasBancarias_003', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-06 09:58:35', '2026-06-06 09:58:44', 9, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_003/BiCVP_ContasBancarias_003_20260605T124500.log', '2026-06-06 09:58:35.200', N'SUCCESS', '2026-06-06 09:58:44.600', N'BiCVP_ContasBancarias_003'),
(N'20260605T212501', N'BI_CVP', N'BiCvp_Assistencia_00_ext_mkt_cloud', N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'71adb627cc1e', '2026-06-05 18:25:02', '2026-06-05 18:25:09', 7, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_Assistencia_00_ext_mkt_cloud/BiCvp_Assistencia_00_ext_mkt_cloud_20260605T212501.log', '2026-06-05 18:25:02.690', N'SUCCESS', '2026-06-05 18:25:09.493', N'BiCvp_Assistencia_00_ext_mkt_cloud'),
(N'20260605T212501', N'BI_CVP', N'BiCvp_Assistencia_01_ins_mkt_cloud', N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'71adb627cc1e', '2026-06-05 18:25:10', '2026-06-05 18:25:16', 6, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_Assistencia_01_ins_mkt_cloud/BiCvp_Assistencia_01_ins_mkt_cloud_20260605T212501.log', '2026-06-05 18:25:10.746', N'SUCCESS', '2026-06-05 18:25:16.903', N'BiCvp_Assistencia_01_ins_mkt_cloud'),
(N'20260605T212846', N'BI_CVP', N'BiCvp_Assistencia_00_ext_mkt_cloud', N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'71adb627cc1e', '2026-06-05 18:28:46', '2026-06-05 23:28:46', 0, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_Assistencia_00_ext_mkt_cloud/BiCvp_Assistencia_00_ext_mkt_cloud_20260605T212846.log', '2026-06-05 18:28:46.980', N'SUCCESS', '2026-06-05 18:28:46.980', N'BiCvp_Assistencia_00_ext_mkt_cloud'),
(N'20260605T214543', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-05 18:45:45', '2026-06-05 18:47:09', 84, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260605T214543.log', '2026-06-05 18:45:45.153', N'SUCCESS', '2026-06-05 18:47:09.283', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260605T214543', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-05 18:47:10', '2026-06-05 18:47:19', 9, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260605T214543.log', '2026-06-05 18:47:10.370', N'SUCCESS', '2026-06-05 18:47:19.410', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260605T214543', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-05 18:47:20', '2026-06-05 18:49:19', 119, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260605T214543.log', '2026-06-05 18:47:20.523', N'SUCCESS', '2026-06-05 18:49:19.673', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260605T214543', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-05 18:49:20', '2026-06-05 18:49:33', 13, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260605T214543.log', '2026-06-05 18:49:20.796', N'SUCCESS', '2026-06-05 18:49:33.733', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260606T120000', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-07 09:00:02', '2026-06-07 09:01:38', 96, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260606T120000.log', '2026-06-07 09:00:02.186', N'SUCCESS', '2026-06-07 09:01:38.296', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260606T120000', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-07 09:01:39', '2026-06-07 09:02:07', 28, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260606T120000.log', '2026-06-07 09:01:39.076', N'SUCCESS', '2026-06-07 09:02:07.620', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260606T120000', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-07 09:02:08', '2026-06-07 09:04:37', 149, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260606T120000.log', '2026-06-07 09:02:08.813', N'SUCCESS', '2026-06-07 09:04:37.393', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260606T120000', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-07 09:04:38', '2026-06-07 09:04:47', 9, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260606T120000.log', '2026-06-07 09:04:38.970', N'SUCCESS', '2026-06-07 09:04:47.943', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260606T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-07 09:00:01', '2026-06-07 09:10:22', 621, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260606T120000.log', '2026-06-07 09:00:01.470', N'SUCCESS', '2026-06-07 09:10:22.310', N'BiCVP_CoberturasUnificadas_001'),
(N'20260606T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-07 09:10:23', '2026-06-07 09:13:17', 174, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260606T120000.log', '2026-06-07 09:10:23.386', N'SUCCESS', '2026-06-07 09:13:17.716', N'BiCVP_CoberturasUnificadas_002'),
(N'20260606T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-07 09:13:18', '2026-06-07 09:13:24', 6, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260606T120000.log', '2026-06-07 09:13:18.753', N'SUCCESS', '2026-06-07 09:13:24.280', N'BiCVP_CoberturasUnificadas_003'),
(N'20260606T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-07 09:13:26', '2026-06-07 09:21:18', 472, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260606T120000.log', '2026-06-07 09:13:26.536', N'SUCCESS', '2026-06-07 09:21:18.596', N'BiCVP_CoberturasUnificadas_004'),
(N'20260606T124500', N'BI_CVP', N'BiCVP_ContasBancarias_001', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-07 09:45:01', '2026-06-07 09:55:13', 612, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_001/BiCVP_ContasBancarias_001_20260606T124500.log', '2026-06-07 09:45:01.496', N'SUCCESS', '2026-06-07 09:55:13.293', N'BiCVP_ContasBancarias_001'),
(N'20260606T124500', N'BI_CVP', N'BiCVP_ContasBancarias_002', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-07 09:55:14', '2026-06-07 09:56:16', 62, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_002/BiCVP_ContasBancarias_002_20260606T124500.log', '2026-06-07 09:55:14.346', N'SUCCESS', '2026-06-07 09:56:16.320', N'BiCVP_ContasBancarias_002'),
(N'20260606T124500', N'BI_CVP', N'BiCVP_ContasBancarias_003', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-07 09:56:17', '2026-06-07 09:56:26', 9, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_003/BiCVP_ContasBancarias_003_20260606T124500.log', '2026-06-07 09:56:17.796', N'SUCCESS', '2026-06-07 09:56:26.886', N'BiCVP_ContasBancarias_003'),
(N'20260607T100000', N'BI_CVP', N'BiCvp_Assistencia_00_ext_mkt_cloud', N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'71adb627cc1e', '2026-06-08 15:38:44', '2026-06-08 15:38:48', 4, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_Assistencia_00_ext_mkt_cloud/BiCvp_Assistencia_00_ext_mkt_cloud_20260607T100000.log', '2026-06-08 15:38:44.233', N'FAILED', '2026-06-08 15:38:49.780', N'BiCvp_Assistencia_00_ext_mkt_cloud'),
(N'20260607T120000', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-08 09:00:01', '2026-06-08 09:01:16', 75, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260607T120000.log', '2026-06-08 09:00:01.530', N'SUCCESS', '2026-06-08 09:01:17.033', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260607T120000', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-08 09:01:18', '2026-06-08 09:03:50', 152, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260607T120000.log', '2026-06-08 09:01:18.586', N'SUCCESS', '2026-06-08 09:03:51.106', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260607T120000', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-08 09:03:52', '2026-06-08 09:07:31', 219, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260607T120000.log', '2026-06-08 09:03:52.206', N'SUCCESS', '2026-06-08 09:07:33.326', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260607T120000', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-08 09:07:34', '2026-06-08 09:09:30', 116, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260607T120000.log', '2026-06-08 09:07:34.453', N'SUCCESS', '2026-06-08 09:09:30.203', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260607T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-08 09:00:01', '2026-06-08 09:15:18', 917, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260607T120000.log', '2026-06-08 09:00:01.503', N'SUCCESS', '2026-06-08 09:15:18.740', N'BiCVP_CoberturasUnificadas_001'),
(N'20260607T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-08 09:15:19', '2026-06-08 09:24:17', 538, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260607T120000.log', '2026-06-08 09:15:19.826', N'SUCCESS', '2026-06-08 09:24:17.993', N'BiCVP_CoberturasUnificadas_002'),
(N'20260607T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-08 09:24:18', '2026-06-08 09:26:57', 159, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260607T120000.log', '2026-06-08 09:24:18.963', N'SUCCESS', '2026-06-08 09:26:57.916', N'BiCVP_CoberturasUnificadas_003'),
(N'20260607T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-08 09:26:58', '2026-06-08 09:39:19', 741, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260607T120000.log', '2026-06-08 09:26:58.733', N'SUCCESS', '2026-06-08 09:39:20.293', N'BiCVP_CoberturasUnificadas_004'),
(N'20260607T124500', N'BI_CVP', N'BiCVP_ContasBancarias_001', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-08 09:45:01', '2026-06-08 10:08:24', 1403, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_001/BiCVP_ContasBancarias_001_20260607T124500.log', '2026-06-08 09:45:01.280', N'SUCCESS', '2026-06-08 10:08:24.496', N'BiCVP_ContasBancarias_001'),
(N'20260607T124500', N'BI_CVP', N'BiCVP_ContasBancarias_002', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-08 10:08:25', '2026-06-08 10:10:21', 116, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_002/BiCVP_ContasBancarias_002_20260607T124500.log', '2026-06-08 10:08:25.570', N'SUCCESS', '2026-06-08 10:10:21.700', N'BiCVP_ContasBancarias_002'),
(N'20260607T124500', N'BI_CVP', N'BiCVP_ContasBancarias_003', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-08 10:10:23', '2026-06-08 10:10:32', 9, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_003/BiCVP_ContasBancarias_003_20260607T124500.log', '2026-06-08 10:10:23.470', N'SUCCESS', '2026-06-08 10:10:32.746', N'BiCVP_ContasBancarias_003'),
(N'20260608T100000', N'BI_CVP', N'BiCvp_Assistencia_00_ext_mkt_cloud', N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'71adb627cc1e', '2026-06-09 07:00:02', '2026-06-09 07:00:11', 9, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_Assistencia_00_ext_mkt_cloud/BiCvp_Assistencia_00_ext_mkt_cloud_20260608T100000.log', '2026-06-09 07:00:03.093', N'FAILED', '2026-06-09 07:00:11.673', N'BiCvp_Assistencia_00_ext_mkt_cloud'),
(N'20260608T110000', N'BI_CVP', N'Seq_Flexibilização_Cobrança', N'SEQ_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-09 17:46:08', '2026-06-09 17:49:00', 172, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/Seq_Flexibilização_Cobrança/Seq_Flexibilização_Cobrança_20260608T110000.log', '2026-06-09 17:46:09.043', N'SUCCESS', '2026-06-09 17:49:00.586', N'Seq_Flexibilização_Cobrança'),
(N'20260608T120000', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-09 09:00:02', '2026-06-09 09:05:41', 339, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260608T120000.log', '2026-06-09 09:00:02.133', N'SUCCESS', '2026-06-09 09:05:41.976', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260608T120000', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-09 09:05:42', '2026-06-09 09:07:59', 137, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260608T120000.log', '2026-06-09 09:05:42.970', N'SUCCESS', '2026-06-09 09:07:59.450', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260608T120000', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-09 09:08:00', '2026-06-09 09:17:18', 558, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260608T120000.log', '2026-06-09 09:08:00.733', N'SUCCESS', '2026-06-09 09:17:18.650', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260608T120000', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-09 09:17:19', '2026-06-09 09:19:59', 160, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260608T120000.log', '2026-06-09 09:17:19.690', N'SUCCESS', '2026-06-09 09:20:00.426', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260608T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-09 09:00:02', '2026-06-09 09:14:52', 890, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260608T120000.log', '2026-06-09 09:00:02.473', N'SUCCESS', '2026-06-09 09:14:52.630', N'BiCVP_CoberturasUnificadas_001'),
(N'20260608T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-09 09:14:54', '2026-06-09 09:25:58', 664, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260608T120000.log', '2026-06-09 09:14:54.560', N'SUCCESS', '2026-06-09 09:25:58.230', N'BiCVP_CoberturasUnificadas_002'),
(N'20260608T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-09 09:25:59', '2026-06-09 09:26:31', 32, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260608T120000.log', '2026-06-09 09:25:59.546', N'SUCCESS', '2026-06-09 09:26:32.333', N'BiCVP_CoberturasUnificadas_003'),
(N'20260608T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-09 09:26:33', '2026-06-09 09:37:46', 673, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260608T120000.log', '2026-06-09 09:26:33.960', N'SUCCESS', '2026-06-09 09:37:47.163', N'BiCVP_CoberturasUnificadas_004'),
(N'20260608T124500', N'BI_CVP', N'BiCVP_ContasBancarias_001', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-09 09:45:01', '2026-06-09 10:05:33', 1232, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_001/BiCVP_ContasBancarias_001_20260608T124500.log', '2026-06-09 09:45:01.306', N'SUCCESS', '2026-06-09 10:05:34.210', N'BiCVP_ContasBancarias_001'),
(N'20260608T124500', N'BI_CVP', N'BiCVP_ContasBancarias_002', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-09 10:05:35', '2026-06-09 10:07:54', 139, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_002/BiCVP_ContasBancarias_002_20260608T124500.log', '2026-06-09 10:05:35.786', N'SUCCESS', '2026-06-09 10:07:54.776', N'BiCVP_ContasBancarias_002'),
(N'20260608T124500', N'BI_CVP', N'BiCVP_ContasBancarias_003', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-09 10:07:55', '2026-06-09 10:08:55', 60, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_003/BiCVP_ContasBancarias_003_20260608T124500.log', '2026-06-09 10:07:56.060', N'SUCCESS', '2026-06-09 10:08:55.383', N'BiCVP_ContasBancarias_003'),
(N'20260609T050000', N'BI_VIDA', N'SeqExecCargaVida', N'DATASTAGE_MALHA_VIDA', N'71adb627cc1e', '2026-06-10 02:37:31', '2026-06-10 02:44:00', 389, NULL, 1, N'/Projetos/BI_VIDA/Logs/Airflow/BI_VIDA/SeqExecCargaVida/SeqExecCargaVida_20260609T050000.log', '2026-06-10 02:37:31.943', N'SUCCESS', '2026-06-10 02:44:00.436', N'SeqExecCargaVida'),
(N'20260609T070000', N'BI_VIDA', N'SeqExecCargaVida', N'DATASTAGE_MALHA_VIDA', N'71adb627cc1e', '2026-06-11 01:52:35', '2026-06-11 01:53:30', 55, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_VIDA/SeqExecCargaVida/SeqExecCargaVida_20260609T070000.log', '2026-06-11 01:52:35.390', N'SUCCESS', '2026-06-11 01:53:30.293', N'SeqExecCargaVida'),
(N'20260609T120000', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-10 09:00:01', '2026-06-10 09:01:08', 67, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260609T120000.log', '2026-06-10 09:00:01.156', N'SUCCESS', '2026-06-10 09:01:08.570', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260609T120000', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-10 09:01:09', '2026-06-10 09:01:31', 22, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260609T120000.log', '2026-06-10 09:01:09.956', N'SUCCESS', '2026-06-10 09:01:31.180', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260609T120000', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-10 09:01:32', '2026-06-10 09:05:29', 237, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260609T120000.log', '2026-06-10 09:01:32.286', N'SUCCESS', '2026-06-10 09:05:29.796', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260609T120000', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-10 09:05:30', '2026-06-10 09:05:40', 10, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260609T120000.log', '2026-06-10 09:05:31.043', N'SUCCESS', '2026-06-10 09:05:41.046', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260609T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-10 09:00:03', '2026-06-10 09:09:48', 585, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260609T120000.log', '2026-06-10 09:00:04.160', N'SUCCESS', '2026-06-10 09:09:48.810', N'BiCVP_CoberturasUnificadas_001'),
(N'20260609T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-10 09:09:49', '2026-06-10 09:14:57', 308, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260609T120000.log', '2026-06-10 09:09:50.120', N'SUCCESS', '2026-06-10 09:14:57.946', N'BiCVP_CoberturasUnificadas_002'),
(N'20260609T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-10 09:14:58', '2026-06-10 09:15:08', 10, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260609T120000.log', '2026-06-10 09:14:58.890', N'SUCCESS', '2026-06-10 09:15:08.850', N'BiCVP_CoberturasUnificadas_003'),
(N'20260609T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-10 09:15:09', '2026-06-10 09:25:01', 592, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260609T120000.log', '2026-06-10 09:15:09.820', N'SUCCESS', '2026-06-10 09:25:02.036', N'BiCVP_CoberturasUnificadas_004'),
(N'20260609T124500', N'BI_CVP', N'BiCVP_ContasBancarias_001', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-10 09:45:01', '2026-06-10 09:59:40', 879, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_001/BiCVP_ContasBancarias_001_20260609T124500.log', '2026-06-10 09:45:01.420', N'SUCCESS', '2026-06-10 09:59:40.113', N'BiCVP_ContasBancarias_001'),
(N'20260609T124500', N'BI_CVP', N'BiCVP_ContasBancarias_002', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-10 09:59:41', '2026-06-10 10:01:32', 111, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_002/BiCVP_ContasBancarias_002_20260609T124500.log', '2026-06-10 09:59:41.146', N'SUCCESS', '2026-06-10 10:01:32.823', N'BiCVP_ContasBancarias_002'),
(N'20260609T124500', N'BI_CVP', N'BiCVP_ContasBancarias_003', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-10 10:01:33', '2026-06-10 10:02:16', 43, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_003/BiCVP_ContasBancarias_003_20260609T124500.log', '2026-06-10 10:01:33.876', N'SUCCESS', '2026-06-10 10:02:16.900', N'BiCVP_ContasBancarias_003'),
(N'20260610T054759', N'BI_VIDA', N'SeqExecCargaVida', N'DATASTAGE_MALHA_VIDA', N'71adb627cc1e', '2026-06-10 02:48:00', '2026-06-10 02:53:37', 337, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_VIDA/SeqExecCargaVida/SeqExecCargaVida_20260610T054759.log', '2026-06-10 02:48:00.890', N'SUCCESS', '2026-06-10 02:53:37.683', N'SeqExecCargaVida'),
(N'20260610T055414', N'BI_VIDA', N'SeqExecCargaVida', N'DATASTAGE_MALHA_VIDA', N'71adb627cc1e', '2026-06-10 02:54:16', '2026-06-10 04:59:17', 7501, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_VIDA/SeqExecCargaVida/SeqExecCargaVida_20260610T055414.log', '2026-06-10 02:54:16.643', N'SUCCESS', '2026-06-10 04:59:18.150', N'SeqExecCargaVida'),
(N'20260610T070000', N'BI_VIDA', N'SeqExecCargaVida', N'DATASTAGE_MALHA_VIDA', N'71adb627cc1e', '2026-06-11 04:00:01', '2026-06-11 04:14:40', 879, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_VIDA/SeqExecCargaVida/SeqExecCargaVida_20260610T070000.log', '2026-06-11 04:00:01.570', N'SUCCESS', '2026-06-11 04:14:40.213', N'SeqExecCargaVida'),
(N'20260610T120000', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 09:00:01', '2026-06-11 09:02:18', 137, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260610T120000.log', '2026-06-11 09:00:01.360', N'SUCCESS', '2026-06-11 09:02:18.830', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260610T120000', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 09:02:19', '2026-06-11 09:05:33', 194, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260610T120000.log', '2026-06-11 09:02:20.696', N'SUCCESS', '2026-06-11 09:05:33.290', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260610T120000', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 09:05:34', '2026-06-11 09:09:47', 253, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260610T120000.log', '2026-06-11 09:05:35.153', N'SUCCESS', '2026-06-11 09:09:48.466', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260610T120000', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 09:09:49', '2026-06-11 09:11:59', 130, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260610T120000.log', '2026-06-11 09:09:50', N'SUCCESS', '2026-06-11 09:11:59.646', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260610T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-11 09:00:05', '2026-06-11 09:17:40', 1055, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260610T120000.log', '2026-06-11 09:00:06.090', N'SUCCESS', '2026-06-11 09:17:40.246', N'BiCVP_CoberturasUnificadas_001'),
(N'20260610T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-11 09:17:41', '2026-06-11 09:25:47', 486, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260610T120000.log', '2026-06-11 09:17:42.020', N'SUCCESS', '2026-06-11 09:25:47.576', N'BiCVP_CoberturasUnificadas_002'),
(N'20260610T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-11 09:25:48', '2026-06-11 09:26:14', 26, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260610T120000.log', '2026-06-11 09:25:49.020', N'SUCCESS', '2026-06-11 09:26:14.983', N'BiCVP_CoberturasUnificadas_003'),
(N'20260610T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-11 09:26:16', '2026-06-11 09:43:24', 1028, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260610T120000.log', '2026-06-11 09:26:16.786', N'SUCCESS', '2026-06-11 09:43:24.753', N'BiCVP_CoberturasUnificadas_004'),
(N'20260610T123837', N'BI_VIDA', N'SeqExecCargaVida', N'DATASTAGE_MALHA_VIDA', N'71adb627cc1e', '2026-06-10 09:38:38', '2026-06-10 23:47:05', 50907, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_VIDA/SeqExecCargaVida/SeqExecCargaVida_20260610T123837.log', '2026-06-10 09:38:38.653', N'FAILED', '2026-06-10 23:47:05.286', N'SeqExecCargaVida'),
(N'20260610T124500', N'BI_CVP', N'BiCVP_ContasBancarias_001', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-11 09:45:00', '2026-06-11 10:01:22', 982, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_001/BiCVP_ContasBancarias_001_20260610T124500.log', '2026-06-11 09:45:00.813', N'SUCCESS', '2026-06-11 10:01:22.640', N'BiCVP_ContasBancarias_001'),
(N'20260610T124500', N'BI_CVP', N'BiCVP_ContasBancarias_002', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-11 10:01:25', '2026-06-11 10:05:38', 253, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_002/BiCVP_ContasBancarias_002_20260610T124500.log', '2026-06-11 10:01:25.783', N'SUCCESS', '2026-06-11 10:05:38.363', N'BiCVP_ContasBancarias_002'),
(N'20260610T124500', N'BI_CVP', N'BiCVP_ContasBancarias_003', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-11 10:05:40', '2026-06-11 10:07:09', 89, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_003/BiCVP_ContasBancarias_003_20260610T124500.log', '2026-06-11 10:05:40.133', N'SUCCESS', '2026-06-11 10:07:10.073', N'BiCVP_ContasBancarias_003'),
(N'20260611T070000', N'BI_VIDA', N'SeqExecCargaVida', N'DATASTAGE_MALHA_VIDA', N'71adb627cc1e', '2026-06-12 04:00:02', '2026-06-12 22:43:47', 67425, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_VIDA/SeqExecCargaVida/SeqExecCargaVida_20260611T070000.log', '2026-06-12 04:00:02.160', N'SUCCESS', '2026-06-12 22:43:47.296', N'SeqExecCargaVida'),
(N'20260611T072223', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 04:22:24', '2026-06-11 04:24:54', 150, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260611T072223.log', '2026-06-11 04:22:24.820', N'SUCCESS', '2026-06-11 04:24:55.250', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260611T072223', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 04:24:56', '2026-06-11 04:25:12', 16, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260611T072223.log', '2026-06-11 04:24:56.290', N'SUCCESS', '2026-06-11 04:25:12.353', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260611T072223', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 04:25:13', '2026-06-11 04:25:52', 39, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260611T072223.log', '2026-06-11 04:25:13.483', N'SUCCESS', '2026-06-11 04:25:52.850', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260611T072223', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 04:25:53', '2026-06-11 04:26:02', 9, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260611T072223.log', '2026-06-11 04:25:54.006', N'SUCCESS', '2026-06-11 04:26:02.940', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260611T072647', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 04:26:48', '2026-06-11 05:26:48', 0, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260611T072647.log', '2026-06-11 04:26:48.960', N'SUCCESS', '2026-06-11 04:26:48.960', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260611T072929', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 04:29:31', '2026-06-11 04:30:38', 67, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260611T072929.log', '2026-06-11 04:29:31.090', N'SUCCESS', '2026-06-11 04:30:38.220', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260611T072929', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 04:30:39', '2026-06-11 04:31:46', 67, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260611T072929.log', '2026-06-11 04:30:39.636', N'SUCCESS', '2026-06-11 04:31:46.356', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260611T072929', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 04:31:47', '2026-06-11 04:40:02', 495, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260611T072929.log', '2026-06-11 04:31:47.790', N'SUCCESS', '2026-06-11 04:40:02.403', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260611T072929', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 04:40:05', '2026-06-11 04:41:15', 70, 2, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260611T072929.log', '2026-06-11 04:40:05.700', N'WARNING', '2026-06-11 04:41:15.383', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260611T074731', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 04:47:32', '2026-06-11 04:48:38', 66, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260611T074731.log', '2026-06-11 04:47:32.043', N'SUCCESS', '2026-06-11 04:48:38.520', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260611T074731', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 04:48:39', '2026-06-11 04:49:46', 67, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260611T074731.log', '2026-06-11 04:48:39.673', N'SUCCESS', '2026-06-11 04:49:46.896', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260611T074731', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 04:49:47', '2026-06-11 04:51:57', 130, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260611T074731.log', '2026-06-11 04:49:48.030', N'SUCCESS', '2026-06-11 04:51:57.623', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260611T074731', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 04:51:58', '2026-06-11 04:53:06', 68, 2, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260611T074731.log', '2026-06-11 04:51:58.450', N'WARNING', '2026-06-11 04:53:06.420', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260611T082812', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 05:28:13', '2026-06-11 05:37:35', 562, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260611T082812.log', '2026-06-11 05:28:13.023', N'SUCCESS', '2026-06-11 05:37:35.813', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260611T082812', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 05:37:37', '2026-06-11 05:56:08', 1111, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260611T082812.log', '2026-06-11 05:37:37.180', N'SUCCESS', '2026-06-11 05:56:08.376', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260611T082812', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 05:56:09', '2026-06-11 06:00:20', 251, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260611T082812.log', '2026-06-11 05:56:09.493', N'SUCCESS', '2026-06-11 06:00:21.216', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260611T082812', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 06:00:22', '2026-06-11 06:01:41', 79, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260611T082812.log', '2026-06-11 06:00:22.180', N'SUCCESS', '2026-06-11 06:01:41.533', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260611T083031', N'BI_VIDA', N'SeqExecCargaVida', N'DATASTAGE_MALHA_VIDA', N'71adb627cc1e', '2026-06-11 05:30:31', '2026-06-12 01:16:54', 71183, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_VIDA/SeqExecCargaVida/SeqExecCargaVida_20260611T083031.log', '2026-06-11 05:30:31.840', N'SUCCESS', '2026-06-12 01:16:54.633', N'SeqExecCargaVida'),
(N'20260611T110000', N'BI_CVP', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext', N'DATASTAGE_GECOMIS_MOV_DIARIO', N'71adb627cc1e', '2026-06-12 08:00:02', '2026-06-12 08:20:59', 1257, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext/CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext_20260611T110000.log', '2026-06-12 08:00:02.676', N'SUCCESS', '2026-06-12 08:20:59.376', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext'),
(N'20260611T110000', N'BI_CVP', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_02_ins', N'DATASTAGE_GECOMIS_MOV_DIARIO', N'71adb627cc1e', '2026-06-12 08:21:00', '2026-06-12 08:38:40', 1060, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/CvpBi_AUTO_105_RITM0062235_GECOMIS_02_ins/CvpBi_AUTO_105_RITM0062235_GECOMIS_02_ins_20260611T110000.log', '2026-06-12 08:21:00.490', N'SUCCESS', '2026-06-12 08:38:40.203', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_02_ins'),
(N'20260611T110000', N'BI_CVP', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_01_ext', N'DATASTAGE_GECOMIS_MOV_DIARIO', N'71adb627cc1e', '2026-06-12 08:38:42', '2026-06-12 08:42:59', 257, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_01_ext/CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_01_ext_20260611T110000.log', '2026-06-12 08:38:42.816', N'SUCCESS', '2026-06-12 08:43:00.030', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_01_ext'),
(N'20260611T110000', N'BI_CVP', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_02_ins', N'DATASTAGE_GECOMIS_MOV_DIARIO', N'71adb627cc1e', '2026-06-12 08:43:00', '2026-06-12 08:58:32', 932, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_02_ins/CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_02_ins_20260611T110000.log', '2026-06-12 08:43:01.070', N'SUCCESS', '2026-06-12 08:58:33.030', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_APOLICE_02_ins'),
(N'20260611T110000', N'BI_CVP', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_01_ext', N'DATASTAGE_GECOMIS_MOV_DIARIO', N'71adb627cc1e', '2026-06-12 08:58:35', '2026-06-12 09:14:12', 937, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_01_ext/CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_01_ext_20260611T110000.log', '2026-06-12 08:58:35.073', N'SUCCESS', '2026-06-12 09:14:12.923', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_01_ext'),
(N'20260611T110000', N'BI_CVP', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_02_ins', N'DATASTAGE_GECOMIS_MOV_DIARIO', N'71adb627cc1e', '2026-06-12 09:14:14', '2026-06-12 09:37:55', 1421, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_02_ins/CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_02_ins_20260611T110000.log', '2026-06-12 09:14:14.383', N'SUCCESS', '2026-06-12 09:37:55.210', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_CCA_02_ins'),
(N'20260611T110000', N'BI_CVP', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_01_ext', N'DATASTAGE_GECOMIS_MOV_DIARIO', N'71adb627cc1e', '2026-06-12 09:37:56', '2026-06-12 09:50:20', 744, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_01_ext/CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_01_ext_20260611T110000.log', '2026-06-12 09:37:56.413', N'SUCCESS', '2026-06-12 09:50:20.976', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_01_ext'),
(N'20260611T110000', N'BI_CVP', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_02_ins', N'DATASTAGE_GECOMIS_MOV_DIARIO', N'71adb627cc1e', '2026-06-12 09:50:21', '2026-06-12 10:34:22', 2641, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_02_ins/CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_02_ins_20260611T110000.log', '2026-06-12 09:50:22.276', N'SUCCESS', '2026-06-12 10:34:22.330', N'CvpBi_AUTO_105_RITM0063104_GECOMIS_VALIDADOR_02_ins'),
(N'20260611T120000', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-12 09:00:03', '2026-06-12 09:02:40', 157, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260611T120000.log', '2026-06-12 09:00:04.850', N'SUCCESS', '2026-06-12 09:02:41.040', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260611T120000', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-12 09:02:42', '2026-06-12 09:13:10', 628, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260611T120000.log', '2026-06-12 09:02:42.166', N'SUCCESS', '2026-06-12 09:13:10.850', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260611T120000', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-12 09:13:12', '2026-06-12 09:25:34', 742, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260611T120000.log', '2026-06-12 09:13:12.163', N'SUCCESS', '2026-06-12 09:25:34.246', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260611T120000', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-12 09:25:35', '2026-06-12 09:27:51', 136, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260611T120000.log', '2026-06-12 09:25:35.416', N'SUCCESS', '2026-06-12 09:27:51.246', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes'),
(N'20260611T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_001', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-12 09:00:03', '2026-06-12 09:21:45', 1302, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_001/BiCVP_CoberturasUnificadas_001_20260611T120000.log', '2026-06-12 09:00:04.173', N'SUCCESS', '2026-06-12 09:21:45.613', N'BiCVP_CoberturasUnificadas_001'),
(N'20260611T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_002', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-12 09:21:47', '2026-06-12 09:32:08', 621, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_002/BiCVP_CoberturasUnificadas_002_20260611T120000.log', '2026-06-12 09:21:47.490', N'SUCCESS', '2026-06-12 09:32:08.483', N'BiCVP_CoberturasUnificadas_002'),
(N'20260611T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_003', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-12 09:32:09', '2026-06-12 09:33:09', 60, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_003/BiCVP_CoberturasUnificadas_003_20260611T120000.log', '2026-06-12 09:32:09.723', N'SUCCESS', '2026-06-12 09:33:09.866', N'BiCVP_CoberturasUnificadas_003'),
(N'20260611T120000', N'BI_CVP', N'BiCVP_CoberturasUnificadas_004', N'datastage_coberturas_unificadas_diario', N'71adb627cc1e', '2026-06-12 09:33:11', '2026-06-12 09:49:15', 964, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_CoberturasUnificadas_004/BiCVP_CoberturasUnificadas_004_20260611T120000.log', '2026-06-12 09:33:11.826', N'SUCCESS', '2026-06-12 09:49:15.573', N'BiCVP_CoberturasUnificadas_004'),
(N'20260611T124500', N'BI_CVP', N'BiCVP_ContasBancarias_001', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-12 09:45:01', '2026-06-12 11:52:23', 7642, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_001/BiCVP_ContasBancarias_001_20260611T124500.log', '2026-06-12 09:45:01.213', N'SUCCESS', '2026-06-12 11:52:23.870', N'BiCVP_ContasBancarias_001'),
(N'20260611T124500', N'BI_CVP', N'BiCVP_ContasBancarias_002', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-12 11:52:26', '2026-06-12 11:53:44', 78, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_002/BiCVP_ContasBancarias_002_20260611T124500.log', '2026-06-12 11:52:26.070', N'SUCCESS', '2026-06-12 11:53:44.703', N'BiCVP_ContasBancarias_002'),
(N'20260611T124500', N'BI_CVP', N'BiCVP_ContasBancarias_003', N'DATASTAGE_CONTAS_BANCARIAS_DIARIO', N'71adb627cc1e', '2026-06-12 11:53:45', '2026-06-12 11:54:01', 16, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCVP_ContasBancarias_003/BiCVP_ContasBancarias_003_20260611T124500.log', '2026-06-12 11:53:45.703', N'SUCCESS', '2026-06-12 11:54:02.030', N'BiCVP_ContasBancarias_003'),
(N'20260611T192417', N'BI_CVP', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext', N'DATASTAGE_GECOMIS_MOV_DIARIO', N'71adb627cc1e', '2026-06-11 16:24:19', '2026-06-11 16:25:51', 92, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext/CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext_20260611T192417.log', '2026-06-11 16:24:19.396', N'SUCCESS', '2026-06-11 16:25:51.620', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext'),
(N'20260611T194558', N'BI_CVP', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext', N'DATASTAGE_GECOMIS_MOV_DIARIO', N'71adb627cc1e', '2026-06-11 16:45:59', '2026-06-11 16:47:25', 86, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext/CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext_20260611T194558.log', '2026-06-11 16:45:59.770', N'SUCCESS', '2026-06-11 16:47:25.770', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext'),
(N'20260611T205754', N'BI_CVP', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext', N'DATASTAGE_GECOMIS_MOV_DIARIO', N'71adb627cc1e', '2026-06-11 17:57:56', '2026-06-11 18:28:14', 1818, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext/CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext_20260611T205754.log', '2026-06-11 17:57:56.513', N'FAILED', '2026-06-11 18:28:14.590', N'CvpBi_AUTO_105_RITM0062235_GECOMIS_01_ext'),
(N'20260611T211603', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 18:16:04', '2026-06-11 18:26:12', 608, NULL, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260611T211603.log', '2026-06-11 18:16:04.223', N'FAILED', '2026-06-11 18:26:12.430', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260611T230856', N'BI_CVP', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 20:08:57', '2026-06-11 20:20:22', 685, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas/BiCvp_BaseCobranca_00_ext_Parcelas_Pagas_20260611T230856.log', '2026-06-11 20:08:57.093', N'SUCCESS', '2026-06-11 20:20:22.986', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas'),
(N'20260611T230856', N'BI_CVP', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 20:20:23', '2026-06-11 20:22:34', 131, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas/BiCvp_BaseCobranca_01_ins_Parcelas_Pagas_20260611T230856.log', '2026-06-11 20:20:23.716', N'SUCCESS', '2026-06-11 20:22:34.360', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas'),
(N'20260611T230856', N'BI_CVP', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 20:22:35', '2026-06-11 20:30:53', 498, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes/BiCvp_BaseCobranca_02_ext_Parcelas_Clientes_20260611T230856.log', '2026-06-11 20:22:35.900', N'SUCCESS', '2026-06-11 20:30:53.450', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes'),
(N'20260611T230856', N'BI_CVP', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'71adb627cc1e', '2026-06-11 20:30:54', '2026-06-11 20:32:07', 73, 1, 1, N'/Projetos/BI_CVP/Logs/Airflow/BI_CVP/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes/BiCvp_BaseCobranca_03_ins_Parcelas_Clientes_20260611T230856.log', '2026-06-11 20:30:54.496', N'SUCCESS', '2026-06-11 20:32:07.820', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes');
GO

-- ===== etl_pipeline_audit (225 linhas) =====
SET IDENTITY_INSERT dbo.[etl_pipeline_audit] ON;
INSERT INTO dbo.[etl_pipeline_audit] ([id], [pipeline_name], [changed_by], [field_name], [old_value], [new_value], [changed_at]) VALUES
(1, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'active', N'True', N'1', '2026-06-04 19:44:25.840'),
(2, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'scheduled_time', N'08:30:00', N'09:00:00', '2026-06-04 19:44:26.796'),
(3, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'schedule_hour', N'8', N'9', '2026-06-04 19:44:26.816'),
(4, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'schedule_minute', N'30', N'', '2026-06-04 19:44:26.840'),
(5, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'envia_msg_fim', N'True', N'1', '2026-06-04 19:44:26.863'),
(6, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'envia_msg_erro', N'True', N'1', '2026-06-04 19:44:26.886'),
(7, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'active', NULL, N'1', '2026-06-05 18:09:50.466'),
(8, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'scheduled_time', NULL, N'07:00:00', '2026-06-05 18:09:50.493'),
(9, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'schedule_type', NULL, N'daily', '2026-06-05 18:09:50.516'),
(10, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'schedule_hour', NULL, N'7', '2026-06-05 18:09:50.540'),
(11, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'schedule_minute', NULL, N'0', '2026-06-05 18:09:50.560'),
(12, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'schedule_dow', NULL, N'', '2026-06-05 18:09:50.583'),
(13, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'schedule_dom', NULL, N'', '2026-06-05 18:09:50.606'),
(14, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'envia_msg_inicio', NULL, N'1', '2026-06-05 18:09:50.626'),
(15, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'envia_msg_fim', NULL, N'1', '2026-06-05 18:09:50.650'),
(16, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'envia_msg_erro', NULL, N'1', '2026-06-05 18:09:50.673'),
(17, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'project_name', NULL, N'BI_CVP', '2026-06-05 18:09:50.700'),
(18, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'domain', NULL, N'MKT_CLOUD', '2026-06-05 18:09:50.720'),
(19, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'tags', NULL, N'MKT_CLOUD,BUCC,CENTRAL', '2026-06-05 18:09:50.736'),
(20, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'depends_on', NULL, N'', '2026-06-05 18:09:50.756'),
(21, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'active', NULL, N'1', '2026-06-08 10:29:16.593'),
(22, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'scheduled_time', NULL, N'10:30:00', '2026-06-08 10:29:16.620'),
(23, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'schedule_type', NULL, N'daily', '2026-06-08 10:29:16.640'),
(24, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'schedule_hour', NULL, N'10', '2026-06-08 10:29:16.680'),
(25, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'schedule_minute', NULL, N'30', '2026-06-08 10:29:16.703'),
(26, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'schedule_dow', NULL, N'', '2026-06-08 10:29:16.720'),
(27, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'schedule_dom', NULL, N'', '2026-06-08 10:29:16.743'),
(28, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'envia_msg_inicio', NULL, N'1', '2026-06-08 10:29:16.760'),
(29, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'envia_msg_fim', NULL, N'1', '2026-06-08 10:29:16.780'),
(30, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'envia_msg_erro', NULL, N'1', '2026-06-08 10:29:16.803'),
(31, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'project_name', NULL, N'BI_CVP', '2026-06-08 10:29:16.886'),
(32, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'domain', NULL, N'INFRA', '2026-06-08 10:29:16.910'),
(33, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'tags', NULL, N'FS_DATASTAGE,INFRA', '2026-06-08 10:29:16.933'),
(34, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'depends_on', NULL, N'', '2026-06-08 10:29:16.950'),
(35, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'active', N'True', N'1', '2026-06-08 10:40:33.800'),
(36, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'envia_msg_inicio', N'True', N'1', '2026-06-08 10:40:33.823'),
(37, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'envia_msg_fim', N'True', N'1', '2026-06-08 10:40:33.846'),
(38, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'envia_msg_erro', N'True', N'1', '2026-06-08 10:40:33.870'),
(39, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'active', N'True', N'1', '2026-06-08 15:38:40.140'),
(40, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'envia_msg_inicio', N'True', N'1', '2026-06-08 15:38:40.406'),
(41, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'envia_msg_fim', N'True', N'1', '2026-06-08 15:38:40.590'),
(42, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'CVT38571', N'envia_msg_erro', N'True', N'1', '2026-06-08 15:38:40.613'),
(43, N'TESTE2', N'CVT38571', N'active', NULL, N'1', '2026-06-09 09:17:32.006'),
(44, N'TESTE2', N'CVT38571', N'scheduled_time', NULL, N'00:00:00', '2026-06-09 09:17:32.040'),
(45, N'TESTE2', N'CVT38571', N'schedule_type', NULL, N'hourly', '2026-06-09 09:17:32.080'),
(46, N'TESTE2', N'CVT38571', N'schedule_hour', NULL, N'6', '2026-06-09 09:17:32.150'),
(47, N'TESTE2', N'CVT38571', N'schedule_minute', NULL, N'0', '2026-06-09 09:17:32.186'),
(48, N'TESTE2', N'CVT38571', N'schedule_dow', NULL, N'', '2026-06-09 09:17:32.216'),
(49, N'TESTE2', N'CVT38571', N'schedule_dom', NULL, N'', '2026-06-09 09:17:32.243'),
(50, N'TESTE2', N'CVT38571', N'envia_msg_inicio', NULL, N'1', '2026-06-09 09:17:32.400'),
(51, N'TESTE2', N'CVT38571', N'envia_msg_fim', NULL, N'1', '2026-06-09 09:17:32.430'),
(52, N'TESTE2', N'CVT38571', N'envia_msg_erro', NULL, N'1', '2026-06-09 09:17:32.453'),
(53, N'TESTE2', N'CVT38571', N'project_name', NULL, N'BI_CVP', '2026-06-09 09:17:32.480'),
(54, N'TESTE2', N'CVT38571', N'domain', NULL, N'INFRA', '2026-06-09 09:17:32.536'),
(55, N'TESTE2', N'CVT38571', N'tags', NULL, N'TESTE', '2026-06-09 09:17:32.556'),
(56, N'TESTE2', N'CVT38571', N'depends_on', NULL, N'', '2026-06-09 09:17:32.580'),
(57, N'TESTE2', N'CVT38571', N'criticidade', NULL, N'Media', '2026-06-09 09:17:32.613'),
(58, N'TESTE2', N'CVT38571', N'sla_minutos', NULL, N'', '2026-06-09 09:17:32.666'),
(59, N'TESTE2', N'CVT38571', N'ambiente', NULL, N'PROD', '2026-06-09 09:17:32.743'),
(60, N'TESTE2', N'CVT38571', N'max_active_runs', NULL, N'1', '2026-06-09 09:17:32.760'),
(61, N'TESTE2', N'CVT38571', N'retries_count', NULL, N'1', '2026-06-09 09:17:32.783'),
(62, N'TESTE2', N'CVT38571', N'retry_delay_seconds', NULL, N'300', '2026-06-09 09:17:32.800'),
(63, N'TESTE2', N'CVT38571', N'pool_name', NULL, N'', '2026-06-09 09:17:32.820'),
(64, N'TESTE2', N'CVT38571', N'descricao', NULL, N'teste33333', '2026-06-09 09:17:32.840'),
(65, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'active', NULL, N'1', '2026-06-09 16:44:19.620'),
(66, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'scheduled_time', NULL, N'08:00:00', '2026-06-09 16:44:19.646'),
(67, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'schedule_type', NULL, N'daily', '2026-06-09 16:44:19.720'),
(68, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'schedule_hour', NULL, N'8', '2026-06-09 16:44:19.743'),
(69, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'schedule_minute', NULL, N'0', '2026-06-09 16:44:19.770'),
(70, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'schedule_dow', NULL, N'', '2026-06-09 16:44:19.790'),
(71, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'schedule_dom', NULL, N'', '2026-06-09 16:44:19.866'),
(72, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'envia_msg_inicio', NULL, N'1', '2026-06-09 16:44:19.900'),
(73, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'envia_msg_fim', NULL, N'1', '2026-06-09 16:44:19.926'),
(74, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'envia_msg_erro', NULL, N'1', '2026-06-09 16:44:19.943'),
(75, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'project_name', NULL, N'BI_CVP', '2026-06-09 16:44:20.016'),
(76, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'domain', NULL, N'PORTAL_ECONOMIARIO', '2026-06-09 16:44:20.050'),
(77, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'tags', NULL, N'PORTAL_ECONOMIARIO', '2026-06-09 16:44:20.073'),
(78, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'depends_on', NULL, N'', '2026-06-09 16:44:20.093'),
(79, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'criticidade', NULL, N'Media', '2026-06-09 16:44:20.166'),
(80, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'sla_minutos', NULL, N'', '2026-06-09 16:44:20.200'),
(81, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'ambiente', NULL, N'PROD', '2026-06-09 16:44:20.223'),
(82, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'max_active_runs', NULL, N'1', '2026-06-09 16:44:20.246'),
(83, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'retries_count', NULL, N'1', '2026-06-09 16:44:20.320'),
(84, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'retry_delay_seconds', NULL, N'300', '2026-06-09 16:44:20.343'),
(85, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'pool_name', NULL, N'', '2026-06-09 16:44:20.370'),
(86, N'SEQ_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'descricao', NULL, N'Execução de carga de parcelas pendentes portal economiario atraves da Seq_Flexibilização_Cobrança do datastage.', '2026-06-09 16:44:20.386'),
(87, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'active', NULL, N'1', '2026-06-09 20:47:55.440'),
(88, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'scheduled_time', NULL, N'03:00:00', '2026-06-09 20:47:55.466'),
(89, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'schedule_type', NULL, N'daily', '2026-06-09 20:47:55.490'),
(90, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'schedule_hour', NULL, N'3', '2026-06-09 20:47:55.516'),
(91, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'schedule_minute', NULL, N'0', '2026-06-09 20:47:55.536'),
(92, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'schedule_dow', NULL, N'', '2026-06-09 20:47:55.560'),
(93, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'schedule_dom', NULL, N'', '2026-06-09 20:47:55.576'),
(94, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'envia_msg_inicio', NULL, N'1', '2026-06-09 20:47:55.600'),
(95, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'envia_msg_fim', NULL, N'1', '2026-06-09 20:47:55.620'),
(96, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'envia_msg_erro', NULL, N'1', '2026-06-09 20:47:55.643'),
(97, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'project_name', NULL, N'BI_VIDA', '2026-06-09 20:47:55.660'),
(98, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'domain', NULL, N'GERAL', '2026-06-09 20:47:55.680'),
(99, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'tags', NULL, N'DIARIO,MALHA_VIDA', '2026-06-09 20:47:55.706'),
(100, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'depends_on', NULL, N'', '2026-06-09 20:47:55.726'),
(101, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'criticidade', NULL, N'Alta', '2026-06-09 20:47:55.746'),
(102, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'sla_minutos', NULL, N'', '2026-06-09 20:47:55.770'),
(103, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'ambiente', NULL, N'PROD', '2026-06-09 20:47:55.800'),
(104, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'max_active_runs', NULL, N'1', '2026-06-09 20:47:55.823'),
(105, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'retries_count', NULL, N'1', '2026-06-09 20:47:55.843'),
(106, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'retry_delay_seconds', NULL, N'300', '2026-06-09 20:47:55.866'),
(107, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'pool_name', NULL, N'', '2026-06-09 20:47:55.886'),
(108, N'DATASTAGE_SEQEXECCARGAVIDA', N'CVT38571', N'descricao', NULL, N'Carga diária da malha do vida', '2026-06-09 20:47:55.903'),
(109, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'active', NULL, N'1', '2026-06-09 21:17:06.500'),
(110, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'scheduled_time', NULL, N'02:00:00', '2026-06-09 21:17:06.523'),
(111, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'schedule_type', NULL, N'daily', '2026-06-09 21:17:06.546'),
(112, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'schedule_hour', NULL, N'2', '2026-06-09 21:17:06.566'),
(113, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'schedule_minute', NULL, N'0', '2026-06-09 21:17:06.590'),
(114, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'schedule_dow', NULL, N'', '2026-06-09 21:17:06.610'),
(115, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'schedule_dom', NULL, N'', '2026-06-09 21:17:06.633'),
(116, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_inicio', NULL, N'1', '2026-06-09 21:17:06.656'),
(117, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_fim', NULL, N'1', '2026-06-09 21:17:06.680'),
(118, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_erro', NULL, N'1', '2026-06-09 21:17:06.700'),
(119, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'project_name', NULL, N'BI_VIDA', '2026-06-09 21:17:06.723'),
(120, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'domain', NULL, N'GERAL', '2026-06-09 21:17:06.760'),
(121, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'tags', NULL, N'MALHA_VIDA,DIARIO', '2026-06-09 21:17:06.783'),
(122, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'depends_on', NULL, N'', '2026-06-09 21:17:06.806'),
(123, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'criticidade', NULL, N'Alta', '2026-06-09 21:17:06.826'),
(124, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'sla_minutos', NULL, N'', '2026-06-09 21:17:06.853'),
(125, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'ambiente', NULL, N'PROD', '2026-06-09 21:17:06.876'),
(126, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'max_active_runs', NULL, N'1', '2026-06-09 21:17:06.900'),
(127, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'retries_count', NULL, N'1', '2026-06-09 21:17:06.923'),
(128, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'retry_delay_seconds', NULL, N'300', '2026-06-09 21:17:06.946'),
(129, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'pool_name', NULL, N'', '2026-06-09 21:17:06.970'),
(130, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'descricao', NULL, N'Carga da malha diária do vida.', '2026-06-09 21:17:06.986'),
(131, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'active', N'True', N'1', '2026-06-09 21:26:21.736'),
(132, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_inicio', N'True', N'1', '2026-06-09 21:26:21.760'),
(133, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_fim', N'True', N'1', '2026-06-09 21:26:21.780'),
(134, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_erro', N'True', N'1', '2026-06-09 21:26:21.803'),
(135, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'active', N'True', N'1', '2026-06-10 00:05:44.630'),
(136, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'scheduled_time', N'02:00:00', N'04:00:00', '2026-06-10 00:05:44.793'),
(137, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'schedule_hour', N'2', N'4', '2026-06-10 00:05:44.826'),
(138, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_inicio', N'True', N'1', '2026-06-10 00:05:44.866'),
(139, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_fim', N'True', N'1', '2026-06-10 00:05:44.896'),
(140, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_erro', N'True', N'1', '2026-06-10 00:05:45.083'),
(141, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'active', N'True', N'1', '2026-06-10 02:37:24.783'),
(142, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'scheduled_time', N'04:00:00', N'02:00:00', '2026-06-10 02:37:24.806'),
(143, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'schedule_hour', N'4', N'2', '2026-06-10 02:37:24.826'),
(144, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_inicio', N'True', N'1', '2026-06-10 02:37:24.846'),
(145, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_fim', N'True', N'1', '2026-06-10 02:37:24.866'),
(146, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_erro', N'True', N'1', '2026-06-10 02:37:24.890'),
(147, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'retries_count', N'1', N'3', '2026-06-10 02:37:24.916'),
(148, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'retry_delay_seconds', N'300', N'3600', '2026-06-10 02:37:24.940'),
(149, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'descricao', N'', N'Limpeza de FS do datastage', '2026-06-10 09:41:39.360'),
(150, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'scheduled_time', N'10:30:00', N'10:00:00', '2026-06-10 09:41:39.383'),
(151, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'envia_msg_erro', N'True', N'1', '2026-06-10 09:41:39.393'),
(152, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'schedule_minute', N'30', N'', '2026-06-10 09:41:39.400'),
(153, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'envia_msg_inicio', N'True', N'1', '2026-06-10 09:41:39.403'),
(154, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'envia_msg_fim', N'True', N'1', '2026-06-10 09:41:39.410'),
(155, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'ambiente', N'PROD', N'HOM', '2026-06-10 09:41:39.413'),
(156, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'max_active_runs', N'', N'1', '2026-06-10 09:41:39.420'),
(157, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'retries_count', N'', N'1', '2026-06-10 09:41:39.423'),
(158, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'active', N'', N'1', '2026-06-10 09:41:39.430'),
(159, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'criticidade', N'', N'Baixa', '2026-06-10 09:41:39.433'),
(160, N'SHELL_LIMPA_FS_DATASTAGE', N'CVT38571', N'retry_delay_seconds', N'', N'300', '2026-06-10 09:41:39.440'),
(161, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'active', NULL, N'1', '2026-06-10 11:02:15.136'),
(162, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'scheduled_time', NULL, N'08:00:00', '2026-06-10 11:02:15.146'),
(163, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'schedule_type', NULL, N'daily', '2026-06-10 11:02:15.150'),
(164, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'schedule_hour', NULL, N'8', '2026-06-10 11:02:15.150'),
(165, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'schedule_minute', NULL, N'0', '2026-06-10 11:02:15.153'),
(166, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'schedule_dow', NULL, N'', '2026-06-10 11:02:15.153'),
(167, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'schedule_dom', NULL, N'', '2026-06-10 11:02:15.153'),
(168, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'envia_msg_inicio', NULL, N'1', '2026-06-10 11:02:15.156'),
(169, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'envia_msg_fim', NULL, N'1', '2026-06-10 11:02:15.156'),
(170, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'envia_msg_erro', NULL, N'1', '2026-06-10 11:02:15.156'),
(171, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'project_name', NULL, N'BI_CVP', '2026-06-10 11:02:15.156'),
(172, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'domain', NULL, N'GECOMIS', '2026-06-10 11:02:15.160'),
(173, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'tags', NULL, N'GECOMIS,DATASTAGE,DEMANDA', '2026-06-10 11:02:15.160'),
(174, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'depends_on', NULL, N'', '2026-06-10 11:02:15.160'),
(175, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'criticidade', NULL, N'Baixa', '2026-06-10 11:02:15.163'),
(176, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'sla_minutos', NULL, N'', '2026-06-10 11:02:15.163'),
(177, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'ambiente', NULL, N'PROD', '2026-06-10 11:02:15.166'),
(178, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'max_active_runs', NULL, N'1', '2026-06-10 11:02:15.166'),
(179, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'retries_count', NULL, N'3', '2026-06-10 11:02:15.166'),
(180, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'retry_delay_seconds', NULL, N'300', '2026-06-10 11:02:15.166'),
(181, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'pool_name', NULL, N'', '2026-06-10 11:02:15.170'),
(182, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'cvp16036', N'descricao', NULL, N'Carga das tabelas TB_GECOMIS_CVP_AUTO_105, TB_GECOMIS_CVP_F_APOLICE, TB_GECOMIS_CVP_F_CCA, TB_GECOMIS_CVP_F_VALIDADOR', '2026-06-10 11:02:15.170'),
(183, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'retry_delay_seconds', N'3600', N'1500', '2026-06-11 01:52:29.060'),
(184, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_erro', N'True', N'1', '2026-06-11 01:52:29.066'),
(185, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_fim', N'True', N'1', '2026-06-11 01:52:29.070'),
(186, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'scheduled_time', N'02:00:00', N'04:00:00', '2026-06-11 01:52:29.070'),
(187, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'schedule_hour', N'2', N'4', '2026-06-11 01:52:29.073'),
(188, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'active', N'True', N'1', '2026-06-11 01:52:29.073'),
(189, N'DATASTAGE_MALHA_VIDA', N'CVT38571', N'envia_msg_inicio', N'True', N'1', '2026-06-11 01:52:29.073'),
(190, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'envia_msg_fim', N'True', N'1', '2026-06-11 05:27:25.213'),
(191, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'envia_msg_erro', N'True', N'1', '2026-06-11 05:27:25.233'),
(192, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'active', N'True', N'1', '2026-06-11 05:27:25.240'),
(193, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'criticidade', N'', N'Media', '2026-06-11 05:27:25.243'),
(194, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'envia_msg_inicio', N'', N'1', '2026-06-11 05:27:25.250'),
(195, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'retries_count', N'', N'1', '2026-06-11 05:27:25.253'),
(196, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'max_active_runs', N'', N'1', '2026-06-11 05:27:25.260'),
(197, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'descricao', N'', N'Parcelas Inadimplentes', '2026-06-11 05:27:25.263'),
(198, N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'CVT38571', N'retry_delay_seconds', N'', N'300', '2026-06-11 05:27:25.270'),
(199, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CVT38571', N'envia_msg_fim', N'True', N'1', '2026-06-11 17:56:29.236'),
(200, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CVT38571', N'active', N'', N'1', '2026-06-11 17:56:29.243'),
(201, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CVT38571', N'envia_msg_erro', N'True', N'1', '2026-06-11 17:56:29.243'),
(202, N'DATASTAGE_GECOMIS_MOV_DIARIO', N'CVT38571', N'envia_msg_inicio', N'True', N'1', '2026-06-11 17:56:29.246'),
(203, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'active', NULL, N'1', '2026-06-12 14:48:00.600'),
(204, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'scheduled_time', NULL, N'21:50:00', '2026-06-12 14:48:00.660'),
(205, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'schedule_type', NULL, N'daily', '2026-06-12 14:48:00.670'),
(206, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'schedule_hour', NULL, N'21', '2026-06-12 14:48:00.680'),
(207, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'schedule_minute', NULL, N'50', '2026-06-12 14:48:00.690'),
(208, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'schedule_dow', NULL, N'', '2026-06-12 14:48:00.693'),
(209, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'schedule_dom', NULL, N'', '2026-06-12 14:48:00.700'),
(210, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'envia_msg_inicio', NULL, N'1', '2026-06-12 14:48:00.710'),
(211, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'envia_msg_fim', NULL, N'1', '2026-06-12 14:48:00.720'),
(212, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'envia_msg_erro', NULL, N'1', '2026-06-12 14:48:00.730'),
(213, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'project_name', NULL, N'BI_CVP', '2026-06-12 14:48:00.733'),
(214, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'domain', NULL, N'ASSISTENCIAS', '2026-06-12 14:48:00.743'),
(215, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'tags', NULL, N'DATASTAGE,ASSISTENCIAS,BI_CVP', '2026-06-12 14:48:00.763'),
(216, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'depends_on', NULL, N'', '2026-06-12 14:48:01.236'),
(217, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'criticidade', NULL, N'Media', '2026-06-12 14:48:01.326'),
(218, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'sla_minutos', NULL, N'', '2026-06-12 14:48:01.333'),
(219, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'ambiente', NULL, N'PROD', '2026-06-12 14:48:01.520'),
(220, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'max_active_runs', NULL, N'1', '2026-06-12 14:48:01.533'),
(221, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'retries_count', NULL, N'3', '2026-06-12 14:48:01.676'),
(222, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'retry_delay_seconds', NULL, N'300', '2026-06-12 14:48:01.683'),
(223, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'pool_name', NULL, N'', '2026-06-12 14:48:01.706'),
(224, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'descricao', NULL, N'Carga da tabela DM_CONTRATO_ASSISTENCIA_CVP.', '2026-06-12 14:48:01.766'),
(225, N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'cvp16036', N'runbook_md', NULL, N'', '2026-06-12 14:48:01.770');
SET IDENTITY_INSERT dbo.[etl_pipeline_audit] OFF;
GO

-- ===== etl_pipeline_owner (0 linhas) =====

-- ===== etl_pipeline_performance_snapshot (21 linhas) =====
SET IDENTITY_INSERT dbo.[etl_pipeline_performance_snapshot] ON;
INSERT INTO dbo.[etl_pipeline_performance_snapshot] ([id], [pipeline], [project], [execution_id], [alerta_horas], [elapsed_seconds], [snapshot_at]) VALUES
(1, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BI_CVP', N'20260605T212846', 3, 12675, '2026-06-05 22:00:01.470'),
(2, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BI_CVP', N'20260605T212846', 3, 19874, '2026-06-06 00:00:00.856'),
(3, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BI_CVP', N'20260605T212846', 6, 23475, '2026-06-06 01:00:01.396'),
(4, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BI_CVP', N'20260605T212846', 12, 45075, '2026-06-06 07:00:01.506'),
(5, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BI_CVP', N'20260605T212846', 3, 106275, '2026-06-07 00:00:01.270'),
(6, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BI_CVP', N'20260605T212846', 6, 106275, '2026-06-07 00:00:01.310'),
(7, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BI_CVP', N'20260605T212846', 12, 106275, '2026-06-07 00:00:01.346'),
(8, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BI_CVP', N'20260605T212846', 3, 192675, '2026-06-08 00:00:01.696'),
(9, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BI_CVP', N'20260605T212846', 6, 192675, '2026-06-08 00:00:01.730'),
(10, N'DATASTAGE_ASSISTENCIA_MKT_CLOUD', N'BI_CVP', N'20260605T212846', 12, 192675, '2026-06-08 00:00:01.760'),
(11, N'DATASTAGE_MALHA_VIDA', N'BI_VIDA', N'20260610T123837', 3, 12083, '2026-06-10 13:00:01.226'),
(12, N'DATASTAGE_MALHA_VIDA', N'BI_VIDA', N'20260610T123837', 6, 22885, '2026-06-10 16:00:03.743'),
(13, N'DATASTAGE_MALHA_VIDA', N'BI_VIDA', N'20260611T083031', 3, 12575, '2026-06-11 09:00:07.363'),
(14, N'DATASTAGE_MALHA_VIDA', N'BI_VIDA', N'20260611T083031', 6, 23374, '2026-06-11 12:00:05.566'),
(15, N'DATASTAGE_MALHA_VIDA', N'BI_VIDA', N'20260611T083031', 12, 44970, '2026-06-11 18:00:01.766'),
(16, N'DATASTAGE_MALHA_VIDA', N'BI_VIDA', N'20260611T083031', 3, 66570, '2026-06-12 00:00:01.880'),
(17, N'DATASTAGE_MALHA_VIDA', N'BI_VIDA', N'20260611T083031', 6, 66570, '2026-06-12 00:00:01.910'),
(18, N'DATASTAGE_MALHA_VIDA', N'BI_VIDA', N'20260611T083031', 12, 66570, '2026-06-12 00:00:01.940'),
(19, N'DATASTAGE_MALHA_VIDA', N'BI_VIDA', N'20260611T070000', 3, 10800, '2026-06-12 07:00:02.280'),
(20, N'DATASTAGE_MALHA_VIDA', N'BI_VIDA', N'20260611T070000', 6, 25200, '2026-06-12 11:00:02.376'),
(21, N'DATASTAGE_MALHA_VIDA', N'BI_VIDA', N'20260611T070000', 12, 43200, '2026-06-12 16:00:03.190');
SET IDENTITY_INSERT dbo.[etl_pipeline_performance_snapshot] OFF;
GO

-- ===== etl_object_tag (0 linhas) =====

-- ===== etl_calendario (13 linhas) =====
SET IDENTITY_INSERT dbo.[etl_calendario] ON;
INSERT INTO dbo.[etl_calendario] ([id], [calendario_nome], [data], [descricao], [created_by], [created_at]) VALUES
(1, N'Feriados BR', '2026-01-01', N'Confraternização Universal', N'migration', '2026-06-12 06:36:23.237'),
(2, N'Feriados BR', '2026-02-16', N'Carnaval', N'migration', '2026-06-12 06:36:23.237'),
(3, N'Feriados BR', '2026-02-17', N'Carnaval', N'migration', '2026-06-12 06:36:23.237'),
(4, N'Feriados BR', '2026-04-03', N'Sexta-feira Santa', N'migration', '2026-06-12 06:36:23.237'),
(5, N'Feriados BR', '2026-04-21', N'Tiradentes', N'migration', '2026-06-12 06:36:23.237'),
(6, N'Feriados BR', '2026-05-01', N'Dia do Trabalho', N'migration', '2026-06-12 06:36:23.237'),
(7, N'Feriados BR', '2026-06-04', N'Corpus Christi', N'migration', '2026-06-12 06:36:23.237'),
(8, N'Feriados BR', '2026-09-07', N'Independência', N'migration', '2026-06-12 06:36:23.237'),
(9, N'Feriados BR', '2026-10-12', N'Nossa Senhora Aparecida', N'migration', '2026-06-12 06:36:23.237'),
(10, N'Feriados BR', '2026-11-02', N'Finados', N'migration', '2026-06-12 06:36:23.237'),
(11, N'Feriados BR', '2026-11-15', N'Proclamação da República', N'migration', '2026-06-12 06:36:23.237'),
(12, N'Feriados BR', '2026-11-20', N'Consciência Negra', N'migration', '2026-06-12 06:36:23.237'),
(13, N'Feriados BR', '2026-12-25', N'Natal', N'migration', '2026-06-12 06:36:23.237');
SET IDENTITY_INSERT dbo.[etl_calendario] OFF;
GO

-- ===== etl_blackout (0 linhas) =====

-- ===== etl_seq_import (10 linhas) =====
SET IDENTITY_INSERT dbo.[etl_seq_import] ON;
INSERT INTO dbo.[etl_seq_import] ([id], [dsx_filename], [seq_name_raw], [seq_name], [project_name], [domain], [pipeline_name_override], [schedule_type], [schedule_cron], [schedule_hour], [schedule_minute], [schedule_dow], [schedule_dom], [status], [obs], [imported_by], [imported_at], [reviewed_by], [reviewed_at], [pipeline_id]) VALUES
(1, N'BI_CVP.dsx', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'BI_CVP', NULL, N'seqbicvp_sf_mktcloud_comunicacao_sms', NULL, NULL, NULL, NULL, NULL, NULL, N'pendente_aprovacao', NULL, N'CVT38571', '2026-06-02 23:53:59.407', NULL, NULL, NULL),
(2, N'BI_CVP.dsx', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'BI_CVP', NULL, N'seqbicvp_sf_mktcloud_comunicacao_sms', NULL, NULL, NULL, NULL, NULL, NULL, N'pendente_aprovacao', NULL, N'CVT38571', '2026-06-03 00:01:01.057', NULL, NULL, NULL),
(3, N'BI_CVP.dsx', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'BI_CVP', NULL, N'DATASTAGE_SF_MKTCLOUD_COMUNICACAO_SMS', N'daily', N'0 8 * * *', 8, 0, NULL, NULL, N'pendente_aprovacao', N'ERRO (linha 91): String or binary data would be truncated in table ''DMDB41.dbo.etl_job_lineage'', column ''object_type''. Truncated value: ''Arquivo DataSet (.ds''.', N'CVT38571', '2026-06-03 00:04:23.510', NULL, NULL, NULL),
(4, N'BI_CVP.dsx', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'BI_CVP', NULL, N'SEQBICVP_SF_MKTCLOUD_COMUNICACAO_SMS', N'daily', N'0 8 * * *', 8, 0, NULL, NULL, N'aprovado', N'ERRO (linha 91): String or binary data would be truncated in table ''DMDB41.dbo.etl_job_lineage'', column ''object_type''. Truncated value: ''Arquivo DataSet (.ds''.', N'CVT38571', '2026-06-03 07:07:11.947', N'CVT38571', '2026-06-03 07:10:35', NULL),
(5, N'BI_CVP.dsx', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'BI_CVP', NULL, N'seqbicvp_sf_mktcloud_comunicacao_sms', NULL, NULL, NULL, NULL, NULL, NULL, N'pendente_aprovacao', NULL, N'CVT38571', '2026-06-03 16:33:23.733', NULL, NULL, NULL),
(6, N'BI_CVP.dsx', N'Seq_Flexibilização_Cobrança', N'Seq_Flexibilização_Cobrança', N'BI_CVP', N'PORTAL_ECONOMIARIO', N'seq_flexibilizacao_cobranca', NULL, NULL, NULL, NULL, NULL, NULL, N'pendente_aprovacao', NULL, N'CVT38571', '2026-06-03 23:00:28.680', NULL, NULL, NULL),
(7, N'BI_CVP.dsx', N'Seq_Flexibilização_Cobrança', N'Seq_Flexibilização_Cobrança', N'BI_CVP', N'PORTAL_ECONOMIARIO', N'seq_flexibilizacao_cobranca', NULL, NULL, NULL, NULL, NULL, NULL, N'pendente_aprovacao', NULL, N'CVT38571', '2026-06-03 23:17:53.800', NULL, NULL, NULL),
(8, N'BI_CVP.dsx', N'Seq_Flexibilização_Cobrança', N'Seq_Flexibilização_Cobrança', N'BI_CVP', N'PORTAL_ECONOMIARIO', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'daily', N'30 23 * * *', 23, 30, NULL, NULL, N'aprovado', NULL, N'CVT38571', '2026-06-03 23:18:59.410', N'CVT38571', '2026-06-03 23:20:44.763', NULL),
(9, N'BI_CVP.dsx', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'BI_CVP', N'PORTAL_ECONOMIARIO', N'SEQBICVP_SF_MKTCLOUD_COMUNICACAO_SMS', N'monthly', N'0 6 1 * *', 6, 0, NULL, 1, N'aprovado', NULL, N'CVT38571', '2026-06-05 01:13:16.880', N'CVT38571', '2026-06-05 01:14:30.990', NULL),
(10, N'BI_CVP.dsx', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'SeqBiCvp_Sf_MktCloud_Comunicacao_SMS', N'BI_CVP', N'MKT_CLOUD', N'SEQBICVP_SF_MKTCLOUD_COMUNICACAO_SMS', N'daily', N'0 6 * * *', 6, 0, NULL, NULL, N'aprovado', NULL, N'cvp16036', '2026-06-05 09:13:30.277', N'cvp16036', '2026-06-05 09:16:08.290', NULL);
SET IDENTITY_INSERT dbo.[etl_seq_import] OFF;
GO

-- ===== etl_seq_import_job (22 linhas) =====
SET IDENTITY_INSERT dbo.[etl_seq_import_job] ON;
INSERT INTO dbo.[etl_seq_import_job] ([id], [import_id], [execution_order], [job_name_ds], [job_name_orq], [job_type], [job_command], [status], [lineage_extracted], [lineage_count], [pipeline_job_id]) VALUES
(1, 2, 0, N'BiCvp_Sf_MktCloud_Comunicacao_SMS_ext', N'bicvp_sf_mktcloud_comunicacao_sms_ext', N'datastage', NULL, N'pendente', 1, 4, NULL),
(2, 2, 1, N'BiCvp_Sf_MktCloud_Comunicacao_SMS_load', N'bicvp_sf_mktcloud_comunicacao_sms_load', N'datastage', NULL, N'pendente', 1, 5, NULL),
(3, 3, 0, N'BiCvp_Sf_MktCloud_Comunicacao_SMS_ext', N'bicvp_sf_mktcloud_comunicacao_sms_ext', N'datastage', NULL, N'pendente', 1, 4, NULL),
(4, 3, 1, N'BiCvp_Sf_MktCloud_Comunicacao_SMS_load', N'bicvp_sf_mktcloud_comunicacao_sms_load', N'datastage', NULL, N'pendente', 1, 5, NULL),
(5, 4, 0, N'BiCvp_Sf_MktCloud_Comunicacao_SMS_ext', N'bicvp_sf_mktcloud_comunicacao_sms_ext', N'datastage', NULL, N'aprovado', 1, 4, NULL),
(6, 4, 1, N'BiCvp_Sf_MktCloud_Comunicacao_SMS_load', N'bicvp_sf_mktcloud_comunicacao_sms_load', N'datastage', NULL, N'aprovado', 1, 5, NULL),
(7, 5, 0, N'BiCvp_Sf_MktCloud_Comunicacao_SMS_ext', N'BiCvp_Sf_MktCloud_Comunicacao_SMS_ext', N'datastage', NULL, N'pendente', 1, 4, NULL),
(8, 5, 1, N'BiCvp_Sf_MktCloud_Comunicacao_SMS_load', N'BiCvp_Sf_MktCloud_Comunicacao_SMS_load', N'datastage', NULL, N'pendente', 1, 5, NULL),
(9, 6, 0, N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'datastage', NULL, N'pendente', 1, 2, NULL),
(10, 6, 1, N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'datastage', NULL, N'pendente', 0, 0, NULL),
(11, 7, 0, N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'datastage', NULL, N'pendente', 1, 2, NULL),
(12, 7, 1, N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'datastage', NULL, N'pendente', 1, 2, NULL),
(13, 7, 2, N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'datastage', NULL, N'pendente', 1, 2, NULL),
(14, 7, 3, N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'datastage', NULL, N'pendente', 1, 2, NULL),
(15, 8, 0, N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'BiCvp_BaseCobranca_00_ext_Parcelas_Pagas', N'datastage', NULL, N'aprovado', 1, 2, NULL),
(16, 8, 1, N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'BiCvp_BaseCobranca_01_ins_Parcelas_Pagas', N'datastage', NULL, N'aprovado', 1, 2, NULL),
(17, 8, 2, N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'BiCvp_BaseCobranca_02_ext_Parcelas_Clientes', N'datastage', NULL, N'aprovado', 1, 2, NULL),
(18, 8, 3, N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'BiCvp_BaseCobranca_03_ins_Parcelas_Clientes', N'datastage', NULL, N'aprovado', 1, 2, NULL),
(19, 9, 0, N'BiCvp_Sf_MktCloud_Comunicacao_SMS_ext', N'BiCvp_Sf_MktCloud_Comunicacao_SMS_ext', N'datastage', NULL, N'aprovado', 1, 4, NULL),
(20, 9, 1, N'BiCvp_Sf_MktCloud_Comunicacao_SMS_load', N'BiCvp_Sf_MktCloud_Comunicacao_SMS_load', N'datastage', NULL, N'aprovado', 1, 5, NULL),
(21, 10, 0, N'BiCvp_Sf_MktCloud_Comunicacao_SMS_ext', N'BiCvp_Sf_MktCloud_Comunicacao_SMS_ext', N'datastage', NULL, N'aprovado', 1, 4, NULL),
(22, 10, 1, N'BiCvp_Sf_MktCloud_Comunicacao_SMS_load', N'BiCvp_Sf_MktCloud_Comunicacao_SMS_load', N'datastage', NULL, N'aprovado', 1, 5, NULL);
SET IDENTITY_INSERT dbo.[etl_seq_import_job] OFF;
GO

-- ===== etl_seq_import_lineage (72 linhas) =====
SET IDENTITY_INSERT dbo.[etl_seq_import_lineage] ON;
INSERT INTO dbo.[etl_seq_import_lineage] ([id], [import_job_id], [direction], [object_name], [object_type], [stage_type_raw], [sql_expression], [file_path], [database_name], [dsx_source_file], [extraction_method], [status], [lineage_id], [columns_json]) VALUES
(1, 1, N'destino', N'DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS.ds', NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(2, 1, N'origem', N'QY_READ_SFMC_SMS_TRACKING', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TDDB46.dbo.SFMC_SMS_TRACKING', NULL, N'TDDB46', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(3, 1, N'transformacao', N'Sort_LastUpdate', N'PxSort', N'PxSort', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(4, 1, N'transformacao', N'Remove_Duplicates', N'PxRemDup', N'PxRemDup', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(5, 2, N'origem', N'DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS.ds', NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(6, 2, N'destino', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_INS', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(7, 2, N'transformacao', N'Change_Capture', N'PxChangeCapture', N'PxChangeCapture', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(8, 2, N'destino', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_UPD', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(9, 2, N'origem', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_REF', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(10, 3, N'destino', N'DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS.ds', NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(11, 3, N'origem', N'QY_READ_SFMC_SMS_TRACKING', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TDDB46.dbo.SFMC_SMS_TRACKING', NULL, N'TDDB46', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(12, 3, N'transformacao', N'Sort_LastUpdate', N'PxSort', N'PxSort', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(13, 3, N'transformacao', N'Remove_Duplicates', N'PxRemDup', N'PxRemDup', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(14, 4, N'origem', N'DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS.ds', NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(15, 4, N'destino', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_INS', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(16, 4, N'transformacao', N'Change_Capture', N'PxChangeCapture', N'PxChangeCapture', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(17, 4, N'destino', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_UPD', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(18, 4, N'origem', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_REF', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(19, 5, N'destino', N'DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS.ds', NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(20, 5, N'origem', N'QY_READ_SFMC_SMS_TRACKING', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TDDB46.dbo.SFMC_SMS_TRACKING', NULL, N'TDDB46', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(21, 5, N'transformacao', N'Sort_LastUpdate', N'PxSort', N'PxSort', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(22, 5, N'transformacao', N'Remove_Duplicates', N'PxRemDup', N'PxRemDup', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(23, 6, N'origem', N'DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS.ds', NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(24, 6, N'destino', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_INS', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(25, 6, N'transformacao', N'Change_Capture', N'PxChangeCapture', N'PxChangeCapture', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(26, 6, N'destino', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_UPD', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(27, 6, N'origem', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_REF', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(28, 7, N'destino', N'DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS.ds', NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(29, 7, N'origem', N'QY_READ_SFMC_SMS_TRACKING', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TDDB46.dbo.SFMC_SMS_TRACKING', NULL, N'TDDB46', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(30, 7, N'transformacao', N'Sort_LastUpdate', N'PxSort', N'PxSort', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(31, 7, N'transformacao', N'Remove_Duplicates', N'PxRemDup', N'PxRemDup', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(32, 8, N'origem', N'DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS.ds', NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(33, 8, N'destino', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_INS', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(34, 8, N'transformacao', N'Change_Capture', N'PxChangeCapture', N'PxChangeCapture', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(35, 8, N'destino', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_UPD', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(36, 8, N'origem', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_REF', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(37, 9, N'destino', N'DS_EXT_PARCELAS_PAGAS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_EXT_PARCELAS_PAGAS.dx', NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(38, 9, N'origem', N'EXT_PARCELAS_PAGAS', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'COBER_HIST_VIDAZUL', NULL, N'TDDB05', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(39, 11, N'destino', N'DS_EXT_PARCELAS_PAGAS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_EXT_PARCELAS_PAGAS.dx', NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(40, 11, N'origem', N'EXT_PARCELAS_PAGAS', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'COBER_HIST_VIDAZUL', NULL, N'TDDB05', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(41, 12, N'destino', N'TB_PARCELASPAGAS', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_PARCELA_PAG', NULL, N'DBBUCC', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(42, 12, N'origem', N'DS_EXT_PARCELAS_PAGAS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_EXT_PARCELAS_PAGAS.dx', NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(43, 13, N'destino', N'DS_EXT_PARCELAS_CLIENTES', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_EXT_PARCELAS_CLIENTES.dx', NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(44, 13, N'origem', N'EXT_PARCELAS_CLIENTES', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'dbo.DM_COBRANCA_CVP
DM_CONTRATOS_CVP
VW_PRODUTOS_CVP
NECESS
dbo.TB_PARCELA_PAG
DM_CLIENTES_CONTRATOS_CVP
DM_CLIENTES_UNIFICADOS_CVP
DM_BENEFICIARIOS_CONTRATOS_CVP
VIDA', NULL, N'DBBUCC', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(45, 14, N'origem', N'DS_EXT_PARCELAS_CLIENTES', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_EXT_PARCELAS_CLIENTES.dx', NULL, N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(46, 14, N'destino', N'TB_PARCELASPAGAS', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_CLIENTES_FLEX_COB_CVP_SNAPSHOT', NULL, N'DBBUCC', N'BI_CVP.dsx', N'dsx_auto', N'pendente', NULL, NULL),
(47, 15, N'destino', N'DS_EXT_PARCELAS_PAGAS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_EXT_PARCELAS_PAGAS.dx', NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(48, 15, N'origem', N'EXT_PARCELAS_PAGAS', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'COBER_HIST_VIDAZUL', NULL, N'TDDB05', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(49, 16, N'destino', N'TB_PARCELASPAGAS', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_PARCELA_PAG', NULL, N'DBBUCC', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(50, 16, N'origem', N'DS_EXT_PARCELAS_PAGAS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_EXT_PARCELAS_PAGAS.dx', NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(51, 17, N'destino', N'DS_EXT_PARCELAS_CLIENTES', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_EXT_PARCELAS_CLIENTES.dx', NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(52, 17, N'origem', N'EXT_PARCELAS_CLIENTES', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'dbo.DM_COBRANCA_CVP
DM_CONTRATOS_CVP
VW_PRODUTOS_CVP
NECESS
dbo.TB_PARCELA_PAG
DM_CLIENTES_CONTRATOS_CVP
DM_CLIENTES_UNIFICADOS_CVP
DM_BENEFICIARIOS_CONTRATOS_CVP
VIDA', NULL, N'DBBUCC', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(53, 18, N'origem', N'DS_EXT_PARCELAS_CLIENTES', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#/DS_EXT_PARCELAS_CLIENTES.dx', NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(54, 18, N'destino', N'TB_PARCELASPAGAS', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_CLIENTES_FLEX_COB_CVP_SNAPSHOT', NULL, N'DBBUCC', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(55, 19, N'destino', N'DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS.ds', NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(56, 19, N'origem', N'QY_READ_SFMC_SMS_TRACKING', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TDDB46.dbo.SFMC_SMS_TRACKING', NULL, N'TDDB46', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(57, 19, N'transformacao', N'Sort_LastUpdate', N'PxSort', N'PxSort', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(58, 19, N'transformacao', N'Remove_Duplicates', N'PxRemDup', N'PxRemDup', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(59, 20, N'origem', N'DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS.ds', NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(60, 20, N'destino', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_INS', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(61, 20, N'transformacao', N'Change_Capture', N'PxChangeCapture', N'PxChangeCapture', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(62, 20, N'destino', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_UPD', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(63, 20, N'origem', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_REF', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(64, 21, N'destino', N'DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS.ds', NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(65, 21, N'origem', N'QY_READ_SFMC_SMS_TRACKING', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TDDB46.dbo.SFMC_SMS_TRACKING', NULL, N'TDDB46', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(66, 21, N'transformacao', N'Sort_LastUpdate', N'PxSort', N'PxSort', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(67, 21, N'transformacao', N'Remove_Duplicates', N'PxRemDup', N'PxRemDup', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(68, 22, N'origem', N'DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS', N'Arquivo DataSet (.ds/.dx)', N'PxDataSet', NULL, N'#SSD_DIROT.ParmDirDst#DS_EXT_SF_MKT_CLOUD_COMUNICACAO_SMS.ds', NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(69, 22, N'destino', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_INS', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(70, 22, N'transformacao', N'Change_Capture', N'PxChangeCapture', N'PxChangeCapture', NULL, NULL, NULL, N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(71, 22, N'destino', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_UPD', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL),
(72, 22, N'origem', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS_REF', N'Banco de Dados (ODBC)', N'ODBCConnectorPX', N'TB_SF_MKT_CLOUD_COMUNICACAO_SMS', NULL, N'DMDB41', N'BI_CVP.dsx', N'dsx_auto', N'aprovado', NULL, NULL);
SET IDENTITY_INSERT dbo.[etl_seq_import_lineage] OFF;
GO

-- ===== etl_factory_log (3 linhas) =====
SET IDENTITY_INSERT dbo.[etl_factory_log] ON;
INSERT INTO dbo.[etl_factory_log] ([id], [dag_run_id], [iniciado_em], [finalizado_em], [estado], [escopo], [pipeline_name], [geradas], [erros], [detalhes_json]) VALUES
(1, N'orquestra_ui_1781212497175', '2026-06-11 18:14:58.403', '2026-06-11 18:14:58.500', N'SUCCESS', N'Pipeline específico: DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', 1, 0, N'{"steps": [{"tipo": "reset", "msg": "Pipeline ''DATASTAGE_FLEXIBILIZACAO_COBRANCA'' liberado para regeneração"}, {"tipo": "gerada", "msg": "Arquivo da DAG gravado em /opt/airflow/dags/generated/BI_CVP/PORTAL_ECONOMIARIO/DATASTAGE_FLEXIBILIZACAO_COBRANCA.py"}, {"tipo": "banco", "msg": "Pipeline ''DATASTAGE_FLEXIBILIZACAO_COBRANCA'' marcado como criado no cadastro"}, {"tipo": "resumo", "msg": "1 DAG(s) regenerada(s) com sucesso, 0 erro(s)"}], "erros": []}'),
(2, N'orquestra_ui_1781219328143', '2026-06-11 20:08:49.283', '2026-06-11 20:08:49.370', N'SUCCESS', N'Pipeline específico: DATASTAGE_FLEXIBILIZACAO_COBRANCA', N'DATASTAGE_FLEXIBILIZACAO_COBRANCA', 1, 0, N'{"steps": [{"tipo": "reset", "msg": "Pipeline ''DATASTAGE_FLEXIBILIZACAO_COBRANCA'' liberado para regeneração"}, {"tipo": "gerada", "msg": "Arquivo da DAG gravado em /opt/airflow/dags/generated/BI_CVP/PORTAL_ECONOMIARIO/DATASTAGE_FLEXIBILIZACAO_COBRANCA.py"}, {"tipo": "banco", "msg": "Pipeline ''DATASTAGE_FLEXIBILIZACAO_COBRANCA'' marcado como criado no cadastro"}, {"tipo": "resumo", "msg": "1 DAG(s) regenerada(s) com sucesso, 0 erro(s)"}], "erros": []}'),
(3, N'orquestra_ui_1781286775246', '2026-06-12 14:52:56.983', '2026-06-12 14:52:57.260', N'SUCCESS', N'Pipeline específico: DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', N'DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO', 1, 0, N'{"steps": [{"tipo": "reset", "msg": "Pipeline ''DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO'' liberado para regeneração"}, {"tipo": "gerada", "msg": "Arquivo da DAG gravado em /opt/airflow/dags/generated/BI_CVP/ASSISTENCIAS/DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO.py"}, {"tipo": "banco", "msg": "Pipeline ''DATASTAGE_ASSISTENCIAS_UNIFICADAS_DIARIO'' marcado como criado no cadastro"}, {"tipo": "resumo", "msg": "1 DAG(s) regenerada(s) com sucesso, 0 erro(s)"}], "erros": []}');
SET IDENTITY_INSERT dbo.[etl_factory_log] OFF;
GO
ALTER TABLE dbo.[etl_project] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_app_config] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_job_type] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_stage_type_map] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_versao_ferramenta] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_pipeline] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_pipeline_job] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_job_lineage] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_job_execution] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_pipeline_audit] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_pipeline_owner] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_pipeline_performance_snapshot] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_object_tag] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_calendario] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_blackout] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_seq_import] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_seq_import_job] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_seq_import_lineage] CHECK CONSTRAINT ALL;
ALTER TABLE dbo.[etl_factory_log] CHECK CONSTRAINT ALL;
GO
PRINT 'Dump de dados carregado com sucesso.';
GO
