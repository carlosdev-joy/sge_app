-- spec/sql/migrations/094_chamados_nota_anexo.sql
-- Adiciona tem_anexo à etl_chamado e cria etl_chamado_nota.

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_chamado' AND COLUMN_NAME = 'tem_anexo'
)
BEGIN
    ALTER TABLE dbo.etl_chamado
        ADD tem_anexo TINYINT NULL DEFAULT 0;
END;

IF OBJECT_ID('dbo.etl_chamado_nota', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_chamado_nota (
        sys_id_nota      VARCHAR(32)    NOT NULL,
        sys_id_chamado   VARCHAR(32)    NOT NULL,
        autor            NVARCHAR(120)  NULL,
        autor_email      NVARCHAR(200)  NULL,
        criado_em        DATETIME2      NULL,
        texto            NVARCHAR(4000) NULL,
        tipo             NVARCHAR(20)   NOT NULL,  -- 'work_notes' | 'comments'
        sync_em          DATETIME2      NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_chamado_nota PRIMARY KEY (sys_id_nota),
        CONSTRAINT FK_nota_chamado FOREIGN KEY (sys_id_chamado)
            REFERENCES dbo.etl_chamado(sys_id)
    );
    CREATE INDEX IX_nota_chamado ON dbo.etl_chamado_nota (sys_id_chamado);
END;
