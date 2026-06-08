-- =============================================================================
-- Migration 008 — Tabela de Tipos de Job + Parâmetro de limite de audit
-- Banco: orquestra_dev  Schema: dbo
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Tabela dbo.etl_job_type
--    Cadastro dos tipos de job disponíveis para seleção no wizard de pipelines.
--    - lineage_enabled: se 1, o formulário de cadastro de jobs exibe campos de lineage
--    - status: 1=ativo (aparece na lista), 0=inativo
-- -----------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.tables
    WHERE object_id = OBJECT_ID('dbo.etl_job_type')
)
BEGIN
    CREATE TABLE dbo.etl_job_type (
        id              INT IDENTITY(1,1) NOT NULL,
        nome            NVARCHAR(100)     NOT NULL,   -- nome exibido na UI
        descricao       NVARCHAR(500)     NULL,
        lineage_enabled BIT               NOT NULL DEFAULT 1,
        status          BIT               NOT NULL DEFAULT 1,
        criado_em       DATETIME2         NOT NULL DEFAULT GETDATE(),
        criado_por      NVARCHAR(100)     NOT NULL DEFAULT 'admin',

        CONSTRAINT PK_etl_job_type PRIMARY KEY CLUSTERED (id ASC),
        CONSTRAINT UQ_etl_job_type_nome UNIQUE (nome)
    );

    -- Tipos padrão
    INSERT INTO dbo.etl_job_type (nome, descricao, lineage_enabled, status)
    VALUES
        ('SQL',     'Script SQL em banco relacional (SELECT/INSERT/UPDATE/MERGE)',           1, 1),
        ('Python',  'Script Python — pandas, requests, transformações customizadas',         1, 1),
        ('Bash',    'Script shell / bash para operações de sistema ou chamadas externas',    0, 1),
        ('Spark',   'Job PySpark / Spark SQL para processamento distribuído',                1, 1),
        ('dbt',     'Modelo dbt (Data Build Tool) para transformações declarativas',         1, 1),
        ('DataStage','Job IBM DataStage exportado via arquivo .dsx',                         1, 1),
        ('SSIS',    'Pacote SSIS (SQL Server Integration Services)',                         1, 1),
        ('HTTP',    'Chamada de API REST / webhook externo',                                 0, 1);

    PRINT 'Tabela dbo.etl_job_type criada e populada com tipos padrão';
END
ELSE
    PRINT 'Tabela dbo.etl_job_type já existe — ignorado';
GO


-- -----------------------------------------------------------------------------
-- 2. Parâmetro audit_history_limit em dbo.etl_configuracao
--    Controla quantas alterações (excl. criação) são mantidas por pipeline.
-- -----------------------------------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.tables WHERE object_id = OBJECT_ID('dbo.etl_configuracao'))
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dbo.etl_configuracao WHERE chave = 'audit_history_limit')
    BEGIN
        INSERT INTO dbo.etl_configuracao (chave, valor, descricao)
        VALUES ('audit_history_limit', '9',
                'Número máximo de registros de alteração mantidos por pipeline no audit trail (excluindo o registro de criação). Total máximo exibido = este valor + 1.');
        PRINT 'Parâmetro audit_history_limit inserido em dbo.etl_configuracao';
    END
    ELSE
        PRINT 'Parâmetro audit_history_limit já existe — ignorado';
END
ELSE
    PRINT 'AVISO: tabela dbo.etl_configuracao não encontrada. Crie-a antes de inserir parâmetros.';
GO


-- -----------------------------------------------------------------------------
-- 3. Ambiente padrão PROD para pipelines sem ambiente cadastrado
-- -----------------------------------------------------------------------------
UPDATE dbo.etl_pipeline
SET ambiente = 'PROD'
WHERE ambiente IS NULL OR LTRIM(RTRIM(ambiente)) = '';
GO
PRINT 'Pipelines sem ambiente definido atualizados para PROD';
GO


-- -----------------------------------------------------------------------------
-- Verificação final
-- -----------------------------------------------------------------------------
SELECT 'etl_job_type' AS tabela, COUNT(*) AS total FROM dbo.etl_job_type
UNION ALL
SELECT 'etl_pipeline (ambiente=PROD)', COUNT(*) FROM dbo.etl_pipeline WHERE ambiente = 'PROD';
GO
