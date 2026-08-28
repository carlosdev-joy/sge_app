-- spec/sql/migrations/095_chamados_anexo.sql
IF OBJECT_ID('dbo.etl_chamado_anexo', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_chamado_anexo (
        sys_id_anexo     VARCHAR(32)    NOT NULL,
        sys_id_chamado   VARCHAR(32)    NOT NULL,
        nome_arquivo     NVARCHAR(255)  NULL,
        mime_type        NVARCHAR(100)  NULL,
        tamanho_bytes    INT            NULL,
        url_download     NVARCHAR(500)  NULL,
        criado_em        DATETIME2      NULL,
        sync_em          DATETIME2      NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_chamado_anexo PRIMARY KEY (sys_id_anexo),
        CONSTRAINT FK_anexo_chamado FOREIGN KEY (sys_id_chamado)
            REFERENCES dbo.etl_chamado(sys_id)
    );
    CREATE INDEX IX_anexo_chamado ON dbo.etl_chamado_anexo (sys_id_chamado);
END;
