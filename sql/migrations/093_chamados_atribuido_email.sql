-- 093_chamados_atribuido_email.sql
-- Adiciona email do analista atribuído para filtro exato no dashboard "Meu painel".
-- Substitui o LIKE por nome (frágil, quebra com nomes do meio) por igualdade no email.

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_chamado')
      AND name = 'atribuido_a_email'
)
BEGIN
    ALTER TABLE dbo.etl_chamado
        ADD atribuido_a_email NVARCHAR(200) NULL;

    CREATE INDEX IX_etl_chamado_atribuido_email
        ON dbo.etl_chamado (atribuido_a_email)
        WHERE atribuido_a_email IS NOT NULL;
END
GO
