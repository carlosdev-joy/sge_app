-- 089_chamados_parent.sql
-- Adiciona parent_sys_id em etl_chamado para ligar SCTASK ao RITM pai.

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_chamado')
      AND name = 'parent_sys_id'
)
BEGIN
    ALTER TABLE dbo.etl_chamado
        ADD parent_sys_id VARCHAR(32) NULL;

    CREATE INDEX IX_etl_chamado_parent
        ON dbo.etl_chamado (parent_sys_id)
        WHERE parent_sys_id IS NOT NULL;
END
GO
