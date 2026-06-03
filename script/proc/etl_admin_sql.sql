-- =============================================================================
-- ORQUESTRA — Admin: SP de delete cascade de pipeline + config manage
-- =============================================================================

-- ── sp_etl_pipeline_delete: cascade completo ─────────────────────────────────
IF OBJECT_ID('dbo.sp_etl_pipeline_delete', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_etl_pipeline_delete;
GO

CREATE PROCEDURE dbo.sp_etl_pipeline_delete
    @pipeline_name VARCHAR(300),
    @deleted_by    VARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM dbo.etl_pipeline WHERE pipeline_name = @pipeline_name)
        THROW 50001, 'Pipeline não encontrado.', 1;

    -- Contar dependências antes de deletar (para log)
    DECLARE
        @n_jobs     INT,
        @n_lineage  INT,
        @n_execucoes INT = 0;

    SELECT @n_jobs    = COUNT(*) FROM dbo.etl_pipeline_job   WHERE pipeline_name = @pipeline_name;
    SELECT @n_lineage = COUNT(*) FROM dbo.etl_job_lineage     WHERE pipeline_name = @pipeline_name;
    -- execuções: verificar se tabela existe
    IF OBJECT_ID('dbo.etl_job_execution', 'U') IS NOT NULL
        SELECT @n_execucoes = COUNT(*)
        FROM   dbo.etl_job_execution
        WHERE  pipeline_name = @pipeline_name;

    BEGIN TRANSACTION;
    BEGIN TRY

        -- 1. Lineage
        DELETE FROM dbo.etl_job_lineage     WHERE pipeline_name = @pipeline_name;
        -- 2. Execuções (se tabela existir)
        IF OBJECT_ID('dbo.etl_job_execution', 'U') IS NOT NULL
            EXEC('DELETE FROM dbo.etl_job_execution WHERE pipeline_name = ''' + @pipeline_name + '''');
        -- 3. Jobs
        DELETE FROM dbo.etl_pipeline_job    WHERE pipeline_name = @pipeline_name;
        -- 4. Referências em seq_import (nullifica FK sem deletar o histórico)
        IF OBJECT_ID('dbo.etl_seq_import', 'U') IS NOT NULL
            UPDATE dbo.etl_seq_import
            SET pipeline_id = NULL
            WHERE pipeline_name_override = @pipeline_name
               OR seq_name               = @pipeline_name;
        -- 5. Pipeline principal (por último)
        DELETE FROM dbo.etl_pipeline        WHERE pipeline_name = @pipeline_name;

        -- Log de auditoria (se tabela existir)
        IF OBJECT_ID('dbo.etl_pipeline_audit', 'U') IS NOT NULL
            INSERT INTO dbo.etl_pipeline_audit
                (pipeline_name, action, changed_by, changed_at, obs)
            VALUES
                (@pipeline_name, 'DELETE', @deleted_by, GETDATE(),
                 'Cascade: ' + CAST(@n_jobs AS VARCHAR) + ' jobs, ' +
                 CAST(@n_lineage AS VARCHAR) + ' lineage, ' +
                 CAST(@n_execucoes AS VARCHAR) + ' execuções removidos');

        COMMIT TRANSACTION;
        SELECT
            @pipeline_name AS pipeline_name,
            @n_jobs        AS jobs_removidos,
            @n_lineage     AS lineage_removidos,
            @n_execucoes   AS execucoes_removidas,
            'Deletado com sucesso' AS resultado;

    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
GO

-- ── View de dependências (para preview antes de deletar) ─────────────────────
CREATE OR ALTER VIEW dbo.vw_pipeline_dependencies AS
SELECT
    p.pipeline_name,
    p.project_name,
    p.active,
    COUNT(DISTINCT j.job_name)  AS total_jobs,
    COUNT(DISTINCT l.id)        AS total_lineage,
    p.dag_criada,
    p.updated_at
FROM dbo.etl_pipeline p
LEFT JOIN dbo.etl_pipeline_job j ON j.pipeline_name = p.pipeline_name
LEFT JOIN dbo.etl_job_lineage  l ON l.pipeline_name = p.pipeline_name
GROUP BY p.pipeline_name, p.project_name, p.active, p.dag_criada, p.updated_at;
GO

PRINT '==> sp_etl_pipeline_delete e vw_pipeline_dependencies criados.';
GO
