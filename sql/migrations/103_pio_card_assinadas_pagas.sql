-- sql/migrations/103_pio_card_assinadas_pagas.sql
-- O terceiro card do PIO: ASSINA_PAGA (Assinadas e Pagas).
--
--   COD_CARD      ASSINA_PAGA
--   filtro origem STA_ASSINATURA='CO' AND STA_PAGO='S'
--   detalhe       dbo.PIO_PROPOSTA_ASSINA_PAGA_DET  (criada aqui)
--
-- ⚠️ **O discriminador entre o card 2 e o card 3 é o `STA_PAGO`**, não o
-- `STA_ASSINATURA`: os dois saem de `'CO'`. PEND_PGTO fica com `'N'`,
-- ASSINA_PAGA com `'S'`. Se a carga do card 2 deixar de filtrar `STA_PAGO`,
-- as duas tabelas passam a conter as mesmas propostas pagas e os dois cards
-- somam a mesma venda duas vezes — sem erro em lugar nenhum.
--
-- Estrutura IDÊNTICA às outras duas DET (as mesmas 31 colunas, na mesma
-- ordem): a API lê as três com a mesma consulta, só troca o FROM.
--
-- ⚠️ Como nas 101 e 102, esta migration **não cria a procedure de carga**
-- (`PRC_PIO_CARGA_DIARIA`, que ganhou o passo 03 para esta tabela). O texto que
-- roda em produção é a fonte da verdade e não está versionado aqui. Em produção
-- a tabela provavelmente já existe e a migration é no-op; em ambiente novo ela
-- cria a tabela VAZIA, que é o caso que a API sabe tratar.
--
-- Idempotente: roda 2× sem alterar nada (regra do repo, `tests/test_migrations_*`).

-- ── ⚠️ COD_CARD precisa caber 'ASSINA_PAGA' ────────────────────────────────
-- O guia especifica `COD_CARD VARCHAR(10)`, e a migration 102 criou assim. Só
-- que **'ASSINA_PAGA' tem 11 caracteres**. Com a coluna em 10:
--   • com ANSI_WARNINGS ON  → a carga MORRE ("String or binary data would be
--     truncated", Msg 2628) e nenhum card é atualizado no dia;
--   • com ANSI_WARNINGS OFF → grava 'ASSINA_PAG' EM SILÊNCIO, o front pede
--     'ASSINA_PAGA', não casa, e o card mostra ZERO para sempre — sem erro em
--     lugar nenhum para investigar.
-- Foi assim que o defeito apareceu: o seed do DEV estourou na primeira carga.
-- 20 dá folga para o próximo código sem virar coluna larga à toa.
IF OBJECT_ID('dbo.PIO_AGG', 'U') IS NOT NULL
   AND EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.PIO_AGG')
                 AND name = 'COD_CARD' AND max_length < 20)
BEGIN
    ALTER TABLE dbo.PIO_AGG ALTER COLUMN COD_CARD VARCHAR(20) NOT NULL;
END
GO

IF OBJECT_ID('dbo.PIO_AGG_HIST', 'U') IS NOT NULL
   AND EXISTS (SELECT 1 FROM sys.columns
               WHERE object_id = OBJECT_ID('dbo.PIO_AGG_HIST')
                 AND name = 'COD_CARD' AND max_length < 20)
BEGIN
    ALTER TABLE dbo.PIO_AGG_HIST ALTER COLUMN COD_CARD VARCHAR(20) NOT NULL;
END
GO

IF OBJECT_ID('dbo.PIO_PROPOSTA_ASSINA_PAGA_DET', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.PIO_PROPOSTA_ASSINA_PAGA_DET (
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
        DTH_CARGA         DATETIME       NOT NULL CONSTRAINT DF_PIO_APAGA_DET_CARGA DEFAULT (GETDATE()),
        CONSTRAINT PK_PIO_PROPOSTA_ASSINA_PAGA_DET PRIMARY KEY CLUSTERED (ID)
    );
END
GO

IF OBJECT_ID('dbo.PIO_PROPOSTA_ASSINA_PAGA_DET', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_APAGA_DET_PROPOSTA'
                     AND object_id = OBJECT_ID('dbo.PIO_PROPOSTA_ASSINA_PAGA_DET'))
BEGIN
    CREATE INDEX IX_PIO_APAGA_DET_PROPOSTA
        ON dbo.PIO_PROPOSTA_ASSINA_PAGA_DET (COD_PROPOSTA);
END
GO

IF OBJECT_ID('dbo.PIO_PROPOSTA_ASSINA_PAGA_DET', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_APAGA_DET_REF'
                     AND object_id = OBJECT_ID('dbo.PIO_PROPOSTA_ASSINA_PAGA_DET'))
BEGIN
    CREATE INDEX IX_PIO_APAGA_DET_REF
        ON dbo.PIO_PROPOSTA_ASSINA_PAGA_DET (DTH_REFERENCIA);
END
GO

IF OBJECT_ID('dbo.PIO_PROPOSTA_ASSINA_PAGA_DET', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_APAGA_DET_STA'
                     AND object_id = OBJECT_ID('dbo.PIO_PROPOSTA_ASSINA_PAGA_DET'))
BEGIN
    CREATE INDEX IX_PIO_APAGA_DET_STA
        ON dbo.PIO_PROPOSTA_ASSINA_PAGA_DET (STA_ASSINATURA, STA_SITUACAO);
END
GO

-- Como nas outras duas DET (migration 102): a lista ordena sempre pela venda
-- mais antiga, e nenhum índice do guia cobre essa ordenação.
IF OBJECT_ID('dbo.PIO_PROPOSTA_ASSINA_PAGA_DET', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM sys.indexes
                   WHERE name = 'IX_PIO_APAGA_DET_VENDA'
                     AND object_id = OBJECT_ID('dbo.PIO_PROPOSTA_ASSINA_PAGA_DET'))
BEGIN
    CREATE INDEX IX_PIO_APAGA_DET_VENDA
        ON dbo.PIO_PROPOSTA_ASSINA_PAGA_DET (DTH_VENDA, COD_PROPOSTA);
END
GO
