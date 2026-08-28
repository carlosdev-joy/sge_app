-- sql/migrations/099_sn_categoria.sql
-- Catálogo de categorias do módulo ServiceNow.
--
-- Esta é a única das nove tabelas do módulo que NÃO tinha migration em lugar
-- nenhum: as 094–098 vieram da linhagem de produção, e esta foi criada direto
-- no banco. O DDL abaixo é o do schema REAL (dump de 2026-08-28), não uma
-- dedução a partir das queries — schema deduzido aceita os SELECT de hoje e
-- quebra no primeiro dado fora do formato imaginado.
--
-- `slug` é o identificador estável usado pelo código; `label` é o que a tela
-- mostra. Os dois existem porque renomear a categoria na tela não pode
-- invalidar o que já foi classificado.
--
-- ⚠️ O número 099 colide com a `099_servicenow_config_seed` da linhagem de
-- produção. Os nomes são diferentes, e `dbo.etl_schema_version` rastreia por
-- NOME — as duas convivem sem se anular. A colisão de número está registrada
-- na §4.1 de docs/spec-porte-chamados-producao.md.
--
-- Idempotente: em produção a tabela já existe e este bloco é inócuo.

IF OBJECT_ID('dbo.etl_sn_categoria', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_sn_categoria (
        id             INT IDENTITY(1,1) NOT NULL,
        slug           VARCHAR(60)    NOT NULL,
        label          NVARCHAR(80)   NOT NULL,
        descricao      NVARCHAR(400)  NULL,
        padrao         BIT            NOT NULL DEFAULT 0,
        criado_em      DATETIME       NOT NULL DEFAULT GETDATE(),
        atualizado_em  DATETIME       NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_sn_categoria PRIMARY KEY (id)
    );
END;
GO

-- O slug é chave de negócio: duas categorias com o mesmo slug fariam a
-- classificação apontar para duas linhas diferentes conforme a ordem da
-- consulta. A unicidade vem em bloco próprio porque, em produção, a tabela já
-- existe — e a restrição pode não.
--
-- Índice/constraint UNIQUE simples, não filtrado: `CREATE INDEX ... WHERE`
-- falha no sqlcmd por QUOTED_IDENTIFIER e, se criado assim, quebra todo DML da
-- tabela pelo sqlcmd enquanto o pymssql da DAG segue verde.
IF OBJECT_ID('dbo.etl_sn_categoria', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                    WHERE name = 'UQ_etl_sn_categoria_slug'
                      AND object_id = OBJECT_ID('dbo.etl_sn_categoria'))
BEGIN
    CREATE UNIQUE INDEX UQ_etl_sn_categoria_slug
        ON dbo.etl_sn_categoria (slug);
END;
GO
