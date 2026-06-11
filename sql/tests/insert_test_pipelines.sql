-- =============================================================================
-- insert_test_pipelines.sql
-- Insere 3 pipelines de teste para validação do ORQUESTRA
-- Banco: orquestra_dev   Executar APÓS migration 009
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Limpa execuções anteriores dos testes (seguro — apenas os pipelines de teste)
-- -----------------------------------------------------------------------------
DELETE FROM dbo.etl_pipeline_job  WHERE pipeline_name LIKE 'ORQUESTRA_TESTE_%';
DELETE FROM dbo.etl_pipeline      WHERE pipeline_name LIKE 'ORQUESTRA_TESTE_%';
GO


-- =============================================================================
-- TESTE 1: Pipeline com job StoredProc (SQL)
-- =============================================================================
EXEC dbo.sp_etl_pipeline_upsert
    @pipeline_name         = 'ORQUESTRA_TESTE_PROC',
    @project_name          = 'TESTE_ORQUESTRA',
    @domain                = 'Validacao',
    @tags                  = 'teste,storedproc',
    @schedule_type         = 'manual',
    @schedule_hour         = 6,
    @schedule_minute       = 0,
    @schedule_dow          = NULL,
    @schedule_dom          = NULL,
    @active                = 1,
    @dag_criada            = 0,
    @envia_msg_inicio      = 0,
    @envia_msg_fim         = 0,
    @envia_msg_erro        = 1,
    @depends_on            = NULL,
    @dag_start_date        = '2026-01-01',
    @descricao             = 'Teste de job StoredProc — valida execucao de proc SQL via Airflow',
    @criticidade           = 'Baixa',
    @sla_minutos           = NULL,
    @ambiente              = 'DEV',
    @max_active_runs       = 1,
    @retries_count         = 0,
    @retry_delay_seconds   = 60,
    @pool_name             = NULL,
    @user_name             = 'qa_teste';
GO

EXEC dbo.sp_etl_pipeline_job_upsert
    @pipeline_name  = 'ORQUESTRA_TESTE_PROC',
    @job_name       = 'JOB_TESTE_STOREDPROC',
    @execution_order= 1,
    @job_type       = 'storedproc',
    @job_command    = 'dbo.sp_teste_orquestra_sql',
    @user_name      = 'qa_teste';
GO

PRINT 'Pipeline ORQUESTRA_TESTE_PROC inserido.';
GO


-- =============================================================================
-- TESTE 2: Pipeline com job Python
-- =============================================================================
EXEC dbo.sp_etl_pipeline_upsert
    @pipeline_name         = 'ORQUESTRA_TESTE_PYTHON',
    @project_name          = 'TESTE_ORQUESTRA',
    @domain                = 'Validacao',
    @tags                  = 'teste,python',
    @schedule_type         = 'manual',
    @schedule_hour         = 6,
    @schedule_minute       = 0,
    @schedule_dow          = NULL,
    @schedule_dom          = NULL,
    @active                = 1,
    @dag_criada            = 0,
    @envia_msg_inicio      = 0,
    @envia_msg_fim         = 0,
    @envia_msg_erro        = 1,
    @depends_on            = NULL,
    @dag_start_date        = '2026-01-01',
    @descricao             = 'Teste de job Python — valida importlib + funcao run()',
    @criticidade           = 'Baixa',
    @sla_minutos           = NULL,
    @ambiente              = 'DEV',
    @max_active_runs       = 1,
    @retries_count         = 0,
    @retry_delay_seconds   = 60,
    @pool_name             = NULL,
    @user_name             = 'qa_teste';
GO

EXEC dbo.sp_etl_pipeline_job_upsert
    @pipeline_name  = 'ORQUESTRA_TESTE_PYTHON',
    @job_name       = 'JOB_TESTE_PYTHON',
    @execution_order= 1,
    @job_type       = 'python',
    @job_command    = 'orquestra_teste',
    @user_name      = 'qa_teste';
GO

PRINT 'Pipeline ORQUESTRA_TESTE_PYTHON inserido.';
GO


-- =============================================================================
-- TESTE 3: Pipeline com job Shell (requer conexão SSH ativa)
-- Ajuste @job_command para o caminho do script no servidor de teste,
-- ou mantenha o echo para validar apenas a conectividade SSH.
-- =============================================================================
EXEC dbo.sp_etl_pipeline_upsert
    @pipeline_name         = 'ORQUESTRA_TESTE_SHELL',
    @project_name          = 'TESTE_ORQUESTRA',
    @domain                = 'Validacao',
    @tags                  = 'teste,shell',
    @schedule_type         = 'manual',
    @schedule_hour         = 6,
    @schedule_minute       = 0,
    @schedule_dow          = NULL,
    @schedule_dom          = NULL,
    @active                = 1,
    @dag_criada            = 0,
    @envia_msg_inicio      = 0,
    @envia_msg_fim         = 0,
    @envia_msg_erro        = 1,
    @depends_on            = NULL,
    @dag_start_date        = '2026-01-01',
    @descricao             = 'Teste de job Shell/Bash — valida SSHOperator + conectividade',
    @criticidade           = 'Baixa',
    @sla_minutos           = NULL,
    @ambiente              = 'DEV',
    @max_active_runs       = 1,
    @retries_count         = 0,
    @retry_delay_seconds   = 60,
    @pool_name             = NULL,
    @user_name             = 'qa_teste';
GO

EXEC dbo.sp_etl_pipeline_job_upsert
    @pipeline_name  = 'ORQUESTRA_TESTE_SHELL',
    @job_name       = 'JOB_TESTE_SHELL',
    @execution_order= 1,
    @job_type       = 'Bash',
    @job_command    = 'echo "ORQUESTRA SHELL TEST OK" && date && hostname',
    @user_name      = 'qa_teste';
GO

PRINT 'Pipeline ORQUESTRA_TESTE_SHELL inserido.';
GO


-- =============================================================================
-- Verificação final
-- =============================================================================
SELECT
    p.pipeline_name,
    p.project_name,
    p.ambiente,
    p.dag_criada,
    j.job_name,
    j.job_type,
    j.job_command
FROM dbo.etl_pipeline p
JOIN dbo.etl_pipeline_job j ON j.pipeline_name = p.pipeline_name
WHERE p.pipeline_name LIKE 'ORQUESTRA_TESTE_%'
ORDER BY p.pipeline_name, j.execution_order;
GO
