-- sql/migrations/101_pio_proposta_pendente.sql
-- As duas tabelas do PIO (propostas pendentes) no banco do Orquestra.
--
-- `dbo.PIO_PROPOSTA_PENDENTE_AGG` alimenta os CARDS do Workflow em Busca &
-- Vendas (uma linha por categoria de STA_ASSINATURA); `_DET` é o drill-down,
-- uma linha por proposta. As duas são recarregadas por
-- `dbo.PRC_PIO_CARGA_PROPOSTA_PENDENTE` (TRUNCATE + INSERT), que busca no
-- TDDB48 via OPENQUERY no linked server SQL18\STAGING4 — a API NUNCA fala com
-- a fonte em runtime, só lê estas duas.
--
-- ⚠️ POR QUE ESTA MIGRATION EXISTE, se produção já tem as tabelas
-- Elas foram criadas direto no servidor (linhagem de produção, arquivo
-- `089_pio_proposta_pendente.sql`, que NUNCA entrou neste repo — o número 089
-- aqui é outra coisa). Como `dbo.etl_schema_version` rastreia por NOME, esta
-- entra como nova, encontra as tabelas já criadas e não faz nada. Em ambiente
-- novo — o DEV, um ambiente limpo — é ela que cria, e a tela degrada para
-- "sem carga" em vez de estourar "Invalid object name".
--
-- ⚠️ O QUE ESTA MIGRATION DELIBERADAMENTE **NÃO** FAZ
-- Não cria nem altera a PROCEDURE de carga. O texto que roda em produção é a
-- fonte da verdade e não está versionado aqui; recriá-la a partir da
-- documentação sobrescreveria a original por uma reconstituição. Enquanto ela
-- não for extraída do servidor e versionada, um ambiente novo tem as tabelas
-- VAZIAS — que é exatamente o que a API sabe tratar.
--
-- Tipos e índices seguem o dicionário de dados do projeto PIO. Idempotente:
-- roda 2× sem alterar nada (regra do repo, `tests/test_migrations_*`).

IF OBJECT_ID('dbo.PIO_PROPOSTA_PENDENTE_AGG', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.PIO_PROPOSTA_PENDENTE_AGG (
        ID              INT IDENTITY(1,1) NOT NULL,
        STA_CATEGORIA   VARCHAR(50)  NOT NULL,
        DES_CATEGORIA   VARCHAR(100) NOT NULL,
        QTD_PROPOSTAS   INT          NOT NULL CONSTRAINT DF_PIO_AGG_QTD DEFAULT (0),
        DTH_REFERENCIA  DATE         NOT NULL,
        DTH_CARGA       DATETIME     NOT NULL CONSTRAINT DF_PIO_AGG_CARGA DEFAULT (GETDATE()),
        CONSTRAINT PK_PIO_PROPOSTA_PENDENTE_AGG PRIMARY KEY CLUSTERED (ID)
    );
END
GO

IF OBJECT_ID('dbo.PIO_PROPOSTA_PENDENTE_AGG', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_AGG_REF'
                     AND object_id = OBJECT_ID('dbo.PIO_PROPOSTA_PENDENTE_AGG'))
BEGIN
    CREATE INDEX IX_PIO_AGG_REF
        ON dbo.PIO_PROPOSTA_PENDENTE_AGG (DTH_REFERENCIA, STA_CATEGORIA);
END
GO

IF OBJECT_ID('dbo.PIO_PROPOSTA_PENDENTE_DET', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.PIO_PROPOSTA_PENDENTE_DET (
        ID                BIGINT IDENTITY(1,1) NOT NULL,
        COD_PROPOSTA      VARCHAR(50)    NULL,
        NUM_AGENCIA       VARCHAR(20)    NULL,
        NUM_MATRICULA     VARCHAR(30)    NULL,
        DTH_VENDA         DATE           NULL,
        STA_SITUACAO      VARCHAR(10)    NULL,
        DES_JUST_CANC     VARCHAR(500)   NULL,
        STA_ASSINATURA    VARCHAR(10)    NULL,
        STA_PAGO          VARCHAR(5)     NULL,
        DTH_ALTERACAO     DATETIME       NULL,
        NOM_PESSOA        VARCHAR(200)   NULL,
        COD_CPF           VARCHAR(20)    NULL,
        DTA_NASCIMENTO    DATE           NULL,
        VLR_RENDA_FORMAL  DECIMAL(18,2)  NULL,
        NOM_LOGRADOURO    VARCHAR(200)   NULL,
        NOM_BAIRRO        VARCHAR(100)   NULL,
        NOM_CIDADE        VARCHAR(100)   NULL,
        NOM_UF            VARCHAR(5)     NULL,
        NUM_CEP           VARCHAR(10)    NULL,
        NOM_PRODUTO       VARCHAR(200)   NULL,
        AREA_PRODUTO      VARCHAR(100)   NULL,
        VLR_IMP_SEGURADA  DECIMAL(18,2)  NULL,
        VLR_PREMIO        DECIMAL(18,2)  NULL,
        COD_PLANO         VARCHAR(20)    NULL,
        NUM_DDD_TEL_RES   VARCHAR(5)     NULL,
        NUM_TEL_RES       VARCHAR(20)    NULL,
        NUM_DDD_TEL_CEL   VARCHAR(5)     NULL,
        NUM_TEL_CEL       VARCHAR(20)    NULL,
        DES_EMAIL         VARCHAR(200)   NULL,
        DTH_REFERENCIA    DATE           NOT NULL,
        DTH_CARGA         DATETIME       NOT NULL CONSTRAINT DF_PIO_DET_CARGA DEFAULT (GETDATE()),
        CONSTRAINT PK_PIO_PROPOSTA_PENDENTE_DET PRIMARY KEY CLUSTERED (ID)
    );
END
GO

IF OBJECT_ID('dbo.PIO_PROPOSTA_PENDENTE_DET', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_DET_REF'
                     AND object_id = OBJECT_ID('dbo.PIO_PROPOSTA_PENDENTE_DET'))
BEGIN
    CREATE INDEX IX_PIO_DET_REF
        ON dbo.PIO_PROPOSTA_PENDENTE_DET (DTH_REFERENCIA);
END
GO

IF OBJECT_ID('dbo.PIO_PROPOSTA_PENDENTE_DET', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_DET_STA'
                     AND object_id = OBJECT_ID('dbo.PIO_PROPOSTA_PENDENTE_DET'))
BEGIN
    CREATE INDEX IX_PIO_DET_STA
        ON dbo.PIO_PROPOSTA_PENDENTE_DET (STA_ASSINATURA, STA_SITUACAO);
END
GO

IF OBJECT_ID('dbo.PIO_PROPOSTA_PENDENTE_DET', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_DET_PROPOSTA'
                     AND object_id = OBJECT_ID('dbo.PIO_PROPOSTA_PENDENTE_DET'))
BEGIN
    CREATE INDEX IX_PIO_DET_PROPOSTA
        ON dbo.PIO_PROPOSTA_PENDENTE_DET (COD_PROPOSTA);
END
GO
