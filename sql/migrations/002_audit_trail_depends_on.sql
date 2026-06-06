-- =============================================================================
-- Migration 002 — S1 Audit Trail + S4 Dependência entre pipelines
-- Banco: DMDB41  Schema: dbo
-- Executar com permissão ddl_admin ou owner do schema
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Coluna depends_on na tabela etl_pipeline (S4)
-- -----------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_pipeline')
      AND name = 'depends_on'
)
BEGIN
    ALTER TABLE dbo.etl_pipeline
        ADD depends_on NVARCHAR(200) NULL;

    PRINT 'Coluna depends_on adicionada em dbo.etl_pipeline';
END
ELSE
    PRINT 'Coluna depends_on ja existe em dbo.etl_pipeline — ignorado';
GO


-- -----------------------------------------------------------------------------
-- 2. Tabela dbo.etl_pipeline_audit (S1)
--    Registra toda alteração feita via etl_pipeline_register.
-- -----------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.tables
    WHERE object_id = OBJECT_ID('dbo.etl_pipeline_audit')
)
BEGIN
    CREATE TABLE dbo.etl_pipeline_audit (
        id            BIGINT IDENTITY(1,1) NOT NULL,
        pipeline_name NVARCHAR(200)        NOT NULL,
        changed_by    NVARCHAR(100)        NOT NULL DEFAULT 'system',
        field_name    NVARCHAR(100)        NOT NULL,
        old_value     NVARCHAR(MAX)        NULL,
        new_value     NVARCHAR(MAX)        NULL,
        changed_at    DATETIME2            NOT NULL DEFAULT GETDATE(),

        CONSTRAINT PK_etl_pipeline_audit PRIMARY KEY CLUSTERED (id ASC)
    );

    -- Índice para consulta por pipeline (listagem do modal de histórico)
    CREATE NONCLUSTERED INDEX IX_etl_pipeline_audit_pipeline_name
        ON dbo.etl_pipeline_audit (pipeline_name ASC, changed_at DESC);

    -- Índice para consulta por usuário (relatórios futuros)
    CREATE NONCLUSTERED INDEX IX_etl_pipeline_audit_changed_by
        ON dbo.etl_pipeline_audit (changed_by ASC, changed_at DESC);

    PRINT 'Tabela dbo.etl_pipeline_audit criada com sucesso';
END
ELSE
    PRINT 'Tabela dbo.etl_pipeline_audit ja existe — ignorado';
GO


-- -----------------------------------------------------------------------------
-- 3. Atualiza sp_etl_pipeline_upsert para aceitar @depends_on (S4)
--    Recria o SP adicionando o parâmetro opcional.
--    OBS: adaptar o corpo completo se o SP original tiver lógica adicional.
-- -----------------------------------------------------------------------------
IF OBJECT_ID('dbo.sp_etl_pipeline_upsert', 'P') IS NOT NULL
BEGIN
    -- Verifica se o parâmetro já existe para evitar dupla adição
    IF NOT EXISTS (
        SELECT 1 FROM sys.parameters
        WHERE object_id = OBJECT_ID('dbo.sp_etl_pipeline_upsert')
          AND name = '@depends_on'
    )
    BEGIN
        PRINT 'AVISO: sp_etl_pipeline_upsert nao possui @depends_on.';
        PRINT 'O DAG etl_pipeline_register usa UPDATE separado para gravar depends_on.';
        PRINT 'Adicione @depends_on ao SP manualmente se quiser unificar a escrita.';
    END
    ELSE
        PRINT 'sp_etl_pipeline_upsert ja possui @depends_on — ignorado';
END
ELSE
    PRINT 'AVISO: sp_etl_pipeline_upsert nao encontrado. Verifique o schema.';
GO


-- -----------------------------------------------------------------------------
-- Verificação final
-- -----------------------------------------------------------------------------
SELECT
    'etl_pipeline'       AS tabela,
    COUNT(*)             AS total_registros,
    SUM(CASE WHEN depends_on IS NOT NULL THEN 1 ELSE 0 END) AS com_dependencia
FROM dbo.etl_pipeline
UNION ALL
SELECT
    'etl_pipeline_audit' AS tabela,
    COUNT(*)             AS total_registros,
    NULL
FROM dbo.etl_pipeline_audit;
GO
