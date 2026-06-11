-- =============================================================================
-- Migration 009 — Stored procedures de teste para validação do ORQUESTRA
-- Banco: orquestra_dev  Schema: dbo
-- Executa sem efeitos colaterais — seguro rodar em DEV/HML
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. sp_teste_orquestra_sql
--    Simula um job SQL (SELECT + INSERT em tabela de controle de testes).
--    Retorna status_code = 1 (SUCCESS) via PRINT para que o log_end detecte.
-- -----------------------------------------------------------------------------
IF OBJECT_ID('dbo.sp_teste_orquestra_sql', 'P') IS NOT NULL
    DROP PROCEDURE dbo.sp_teste_orquestra_sql;
GO

CREATE PROCEDURE dbo.sp_teste_orquestra_sql
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @resultado NVARCHAR(200);
    SET @resultado = 'ORQUESTRA_TEST_OK — executado em ' + CONVERT(VARCHAR(30), GETDATE(), 120);

    -- Registra na tabela de teste (cria se não existir)
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_teste_execucao'))
    BEGIN
        CREATE TABLE dbo.etl_teste_execucao (
            id          INT IDENTITY(1,1) PRIMARY KEY,
            tipo_teste  NVARCHAR(50)  NOT NULL,
            resultado   NVARCHAR(500) NOT NULL,
            executado_em DATETIME2    NOT NULL DEFAULT GETDATE()
        );
    END

    INSERT INTO dbo.etl_teste_execucao (tipo_teste, resultado)
    VALUES ('SQL_STOREDPROC', @resultado);

    SELECT @resultado AS resultado, GETDATE() AS executado_em;

    -- Status code 1 = SUCCESS para o log_end do Airflow
    PRINT 'Job Status Code: 1';
END;
GO

PRINT 'sp_teste_orquestra_sql criada/atualizada.';
GO


-- -----------------------------------------------------------------------------
-- 2. Projeto de teste (garante que existe)
-- -----------------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM dbo.etl_project WHERE project_name = 'TESTE_ORQUESTRA')
BEGIN
    INSERT INTO dbo.etl_project (project_name, ativo)
    VALUES ('TESTE_ORQUESTRA', 1);
    PRINT 'Projeto TESTE_ORQUESTRA inserido.';
END
ELSE
    PRINT 'Projeto TESTE_ORQUESTRA já existe.';
GO


-- -----------------------------------------------------------------------------
-- 3. Verificação final
-- -----------------------------------------------------------------------------
SELECT
    'sp_teste_orquestra_sql' AS objeto,
    OBJECT_ID('dbo.sp_teste_orquestra_sql', 'P') AS object_id,
    CASE WHEN OBJECT_ID('dbo.sp_teste_orquestra_sql','P') IS NOT NULL
         THEN 'OK' ELSE 'FALTANDO' END AS status;
GO
