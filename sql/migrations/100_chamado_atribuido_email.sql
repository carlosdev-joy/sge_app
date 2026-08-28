-- sql/migrations/100_chamado_atribuido_email.sql
-- O e-mail do analista atribuído, em dbo.etl_chamado.
--
-- Existe para o dashboard poder filtrar "Meu painel" por IGUALDADE em vez de
-- LIKE sobre o nome. Nome do meio, abreviação e homônimo fazem o LIKE trazer
-- chamado de outra pessoa — e o operador não tem como perceber, porque a tela
-- mostra a fila filtrada e não a regra.
--
-- ⚠️ POR QUE ESTA MIGRATION EXISTE, se produção já tem a coluna
-- Ela vem da `093_chamados_atribuido_email` da LINHAGEM DE PRODUÇÃO — e o
-- número 093 na nossa linhagem é `093_chamado_triagem`, outra coisa. Como
-- `dbo.etl_schema_version` rastreia por NOME, a de produção continuará
-- registrada lá e esta entrará como nova, encontrando a coluna já criada e não
-- fazendo nada. Em qualquer ambiente novo, é esta que cria.
--
-- ⚠️ O QUE FOI DELIBERADAMENTE MUDADO
-- A migration de produção cria o índice como FILTRADO:
--
--     CREATE INDEX IX_etl_chamado_atribuido_email
--         ON dbo.etl_chamado (atribuido_a_email)
--         WHERE atribuido_a_email IS NOT NULL;
--
-- Índice filtrado exige SET QUOTED_IDENTIFIER ON no momento da criação E em
-- todo DML posterior. O sqlcmd conecta com ele OFF: a criação falha com
-- Msg 1934 e, se o índice já existir, **todo INSERT/UPDATE/DELETE na tabela
-- passa a falhar por esse caminho** — enquanto o pymssql da DAG, que conecta
-- com ON, segue verde. O defeito aparece como "o deploy quebrou", nunca como
-- "o índice está errado".
--
-- Aqui o índice é simples. A coluna é esparsa (nem todo chamado tem e-mail),
-- então o índice guarda algumas linhas a mais — e essa é a troca certa: espaço
-- em disco contra um modo de falha que já custou diagnóstico neste repositório.
--
-- Idempotente nos dois blocos.

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_chamado')
      AND name = 'atribuido_a_email'
)
BEGIN
    ALTER TABLE dbo.etl_chamado
        ADD atribuido_a_email NVARCHAR(200) NULL;
END;
GO

IF OBJECT_ID('dbo.etl_chamado', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                    WHERE name = 'IX_etl_chamado_atribuido_email'
                      AND object_id = OBJECT_ID('dbo.etl_chamado'))
BEGIN
    CREATE INDEX IX_etl_chamado_atribuido_email
        ON dbo.etl_chamado (atribuido_a_email);
END;
GO
