-- sql/migrations/102_pio_agg_e_card_pagamento.sql
-- O PIO passa a ter DOIS cards, e o agregado passa a ser POR CARD.
--
-- Modelo novo (guia de referência do PIO, recebido em 2026-09-01), que
-- SUBSTITUI o da migration 101 no runtime da API:
--
--   dbo.PIO_AGG                      snapshot do dia, uma linha por COD_CARD
--   dbo.PIO_AGG_HIST                 mesma estrutura, INSERT-only (tendência)
--   dbo.PIO_PROPOSTA_PENDENTE_DET    detalhe do card PEND_ASSIN (já existe, 101)
--   dbo.PIO_PROPOSTA_PEND_PGTO_DET   detalhe do card PEND_PGTO (novo aqui)
--
-- Os cards e o filtro que a CARGA aplica (a API não refiltra — cada DET já
-- contém só o que é do seu card):
--
--   PEND_ASSIN  Pendentes de Assinatura  STA_ASSINATURA='PE'  ~8.700 registros
--   PEND_PGTO   Pendentes de Pagamento   STA_ASSINATURA='CO'  ~22.500 registros
--   ambos: STA_PAGO='N', STA_SITUACAO NOT IN ('CA','EXP'), DTH_VENDA nos últimos 30 dias
--
-- ⚠️ `dbo.PIO_PROPOSTA_PENDENTE_AGG` (migration 101) fica ÓRFÃ e não é lida por
-- ninguém a partir daqui. Não é dropada de propósito: a carga de produção nasceu
-- fora deste repo e derrubar tabela que talvez ainda seja escrita lá é troca de
-- um problema de tela por um de dado. Se o DBA confirmar que a proc não a
-- alimenta mais, um DROP vira migration própria.
--
-- ⚠️ Como na 101, esta migration **não cria a procedure de carga**
-- (`PRC_PIO_CARGA_DIARIA`). O texto que roda em produção é a fonte da verdade e
-- não está versionado aqui; recriá-lo a partir da documentação sobrescreveria o
-- original por uma reconstituição. Em produção estas tabelas provavelmente já
-- existem e a migration é no-op; em ambiente novo ela cria as tabelas VAZIAS,
-- que é o caso que a API sabe tratar ("li, e não há carga").
--
-- Idempotente: roda 2× sem alterar nada (regra do repo, `tests/test_migrations_*`).

-- ── Agregado do dia ────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.PIO_AGG', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.PIO_AGG (
        ID              INT IDENTITY(1,1) NOT NULL,
        COD_CARD        VARCHAR(10)  NOT NULL,
        DES_CARD        VARCHAR(100) NOT NULL,
        STA_CATEGORIA   VARCHAR(50)  NOT NULL,
        DES_CATEGORIA   VARCHAR(100) NOT NULL,
        QTD_PROPOSTAS   INT          NOT NULL CONSTRAINT DF_PIO_AGG2_QTD DEFAULT (0),
        DTH_REFERENCIA  DATE         NOT NULL,
        DTH_CARGA       DATETIME     NOT NULL CONSTRAINT DF_PIO_AGG2_CARGA DEFAULT (GETDATE()),
        CONSTRAINT PK_PIO_AGG PRIMARY KEY CLUSTERED (ID)
    );
END
GO

IF OBJECT_ID('dbo.PIO_AGG', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_AGG_CARD_REF'
                     AND object_id = OBJECT_ID('dbo.PIO_AGG'))
BEGIN
    CREATE INDEX IX_PIO_AGG_CARD_REF ON dbo.PIO_AGG (COD_CARD, DTH_REFERENCIA);
END
GO

-- ── Histórico acumulado (nunca truncado) ───────────────────────────────────
IF OBJECT_ID('dbo.PIO_AGG_HIST', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.PIO_AGG_HIST (
        ID              INT IDENTITY(1,1) NOT NULL,
        COD_CARD        VARCHAR(10)  NOT NULL,
        DES_CARD        VARCHAR(100) NOT NULL,
        STA_CATEGORIA   VARCHAR(50)  NOT NULL,
        DES_CATEGORIA   VARCHAR(100) NOT NULL,
        QTD_PROPOSTAS   INT          NOT NULL CONSTRAINT DF_PIO_AGGH_QTD DEFAULT (0),
        DTH_REFERENCIA  DATE         NOT NULL,
        DTH_CARGA       DATETIME     NOT NULL CONSTRAINT DF_PIO_AGGH_CARGA DEFAULT (GETDATE()),
        CONSTRAINT PK_PIO_AGG_HIST PRIMARY KEY CLUSTERED (ID)
    );
END
GO

IF OBJECT_ID('dbo.PIO_AGG_HIST', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_AGG_HIST_CARD_REF'
                     AND object_id = OBJECT_ID('dbo.PIO_AGG_HIST'))
BEGIN
    CREATE INDEX IX_PIO_AGG_HIST_CARD_REF ON dbo.PIO_AGG_HIST (COD_CARD, DTH_REFERENCIA);
END
GO

-- ── Detalhe do card PEND_PGTO ──────────────────────────────────────────────
-- Estrutura IDÊNTICA à PIO_PROPOSTA_PENDENTE_DET (as mesmas 31 colunas, na
-- mesma ordem): a API lê as duas com a mesma consulta, só troca o FROM.
IF OBJECT_ID('dbo.PIO_PROPOSTA_PEND_PGTO_DET', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.PIO_PROPOSTA_PEND_PGTO_DET (
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
        DTH_CARGA         DATETIME       NOT NULL CONSTRAINT DF_PIO_PGTO_DET_CARGA DEFAULT (GETDATE()),
        CONSTRAINT PK_PIO_PROPOSTA_PEND_PGTO_DET PRIMARY KEY CLUSTERED (ID)
    );
END
GO

IF OBJECT_ID('dbo.PIO_PROPOSTA_PEND_PGTO_DET', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_PGTO_DET_PROPOSTA'
                     AND object_id = OBJECT_ID('dbo.PIO_PROPOSTA_PEND_PGTO_DET'))
BEGIN
    CREATE INDEX IX_PIO_PGTO_DET_PROPOSTA
        ON dbo.PIO_PROPOSTA_PEND_PGTO_DET (COD_PROPOSTA);
END
GO

IF OBJECT_ID('dbo.PIO_PROPOSTA_PEND_PGTO_DET', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_PGTO_DET_REF'
                     AND object_id = OBJECT_ID('dbo.PIO_PROPOSTA_PEND_PGTO_DET'))
BEGIN
    CREATE INDEX IX_PIO_PGTO_DET_REF
        ON dbo.PIO_PROPOSTA_PEND_PGTO_DET (DTH_REFERENCIA);
END
GO

IF OBJECT_ID('dbo.PIO_PROPOSTA_PEND_PGTO_DET', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_PGTO_DET_STA'
                     AND object_id = OBJECT_ID('dbo.PIO_PROPOSTA_PEND_PGTO_DET'))
BEGIN
    CREATE INDEX IX_PIO_PGTO_DET_STA
        ON dbo.PIO_PROPOSTA_PEND_PGTO_DET (STA_ASSINATURA, STA_SITUACAO);
END
GO

-- A DET do card 1 nasceu na 101 sem o índice de venda; as duas listas ordenam
-- por DTH_VENDA (mais antigas primeiro), então ele vale para as duas.
IF OBJECT_ID('dbo.PIO_PROPOSTA_PENDENTE_DET', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_DET_VENDA'
                     AND object_id = OBJECT_ID('dbo.PIO_PROPOSTA_PENDENTE_DET'))
BEGIN
    CREATE INDEX IX_PIO_DET_VENDA
        ON dbo.PIO_PROPOSTA_PENDENTE_DET (DTH_VENDA, COD_PROPOSTA);
END
GO

IF OBJECT_ID('dbo.PIO_PROPOSTA_PEND_PGTO_DET', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_PGTO_DET_VENDA'
                     AND object_id = OBJECT_ID('dbo.PIO_PROPOSTA_PEND_PGTO_DET'))
BEGIN
    CREATE INDEX IX_PIO_PGTO_DET_VENDA
        ON dbo.PIO_PROPOSTA_PEND_PGTO_DET (DTH_VENDA, COD_PROPOSTA);
END
GO
