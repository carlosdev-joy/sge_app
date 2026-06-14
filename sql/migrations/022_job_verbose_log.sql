-- Adiciona verbose_log em etl_pipeline_job.
-- Quando 1, o DataStageOperator chama dsjob -logsum a cada N polls durante
-- a execução para mostrar progresso dos jobs filhos (SEQUENCE). Default 0.
-- Ativável por job individualmente via tela de Pipelines, sem regerar a malha.
--
-- Inclui ssh_conn_id (migration 012) caso ainda não exista no banco.

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job'
      AND COLUMN_NAME='ssh_conn_id'
)
BEGIN
    ALTER TABLE dbo.etl_pipeline_job ADD ssh_conn_id VARCHAR(100) NULL;
    PRINT '[OK] Coluna ssh_conn_id adicionada em dbo.etl_pipeline_job';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_job'
      AND COLUMN_NAME='verbose_log'
)
BEGIN
    ALTER TABLE dbo.etl_pipeline_job ADD verbose_log BIT NOT NULL DEFAULT 0;
    PRINT '[OK] Coluna verbose_log adicionada em dbo.etl_pipeline_job';
END
GO

CREATE OR ALTER PROCEDURE dbo.sp_etl_pipeline_job_upsert
    @pipeline_name   VARCHAR(200),
    @job_name        VARCHAR(200),
    @execution_order INT,
    @job_type        VARCHAR(50),
    @job_command     NVARCHAR(MAX) = NULL,
    @ssh_conn_id     VARCHAR(100)  = NULL,
    @verbose_log     BIT           = 0
AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS (SELECT 1 FROM dbo.etl_pipeline_job WHERE pipeline_name=@pipeline_name AND job_name=@job_name)
        UPDATE dbo.etl_pipeline_job
        SET execution_order=@execution_order, job_type=@job_type,
            job_command=@job_command, ssh_conn_id=@ssh_conn_id,
            verbose_log=@verbose_log, updated_at=GETDATE()
        WHERE pipeline_name=@pipeline_name AND job_name=@job_name;
    ELSE
        INSERT INTO dbo.etl_pipeline_job
            (pipeline_name, job_name, execution_order, job_type, job_command, ssh_conn_id, verbose_log)
        VALUES
            (@pipeline_name, @job_name, @execution_order, @job_type, @job_command, @ssh_conn_id, @verbose_log);
END
GO
