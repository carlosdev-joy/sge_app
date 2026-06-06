-- ============================================================
-- Migração 006: Metadados de Governança
-- Adiciona ownership, classificação e tags por objeto/pipeline
-- ============================================================

-- Donos de pipeline (Data Owner / Steward)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'etl_pipeline_owner')
CREATE TABLE dbo.etl_pipeline_owner (
    pipeline_name  VARCHAR(300) NOT NULL,
    owner_name     VARCHAR(100) NULL,
    owner_email    VARCHAR(150) NULL,
    steward_name   VARCHAR(100) NULL,
    steward_email  VARCHAR(150) NULL,
    updated_at     DATETIME     NOT NULL DEFAULT GETDATE(),
    updated_by     VARCHAR(100) NULL,
    CONSTRAINT PK_etl_pipeline_owner PRIMARY KEY (pipeline_name),
    CONSTRAINT FK_pipeline_owner FOREIGN KEY (pipeline_name) REFERENCES dbo.etl_pipeline(pipeline_name)
);

-- Tags de classificação por objeto (tabela ou arquivo)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'etl_object_tag')
CREATE TABLE dbo.etl_object_tag (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    object_key    VARCHAR(400) NOT NULL,  -- database.object_name ou file_path
    tag           VARCHAR(50)  NOT NULL,  -- 'PII','Confidencial','Regulado','Publico'
    added_by      VARCHAR(100) NULL,
    added_at      DATETIME     NOT NULL DEFAULT GETDATE(),
    CONSTRAINT UQ_object_tag UNIQUE (object_key, tag)
);

PRINT '==> Migração 006: tabelas de governança criadas.';
GO
