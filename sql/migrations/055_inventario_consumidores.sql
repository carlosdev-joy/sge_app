-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 055 — Inventário de Consumidores (endpoints → views/procs)
--   etl_inventario_endpoint — cadastro documental de serviços/endpoints que
--                             consomem objetos de um banco (caso motivador:
--                             BUCC), com plataforma/consumidor/responsável.
--   etl_inventario_objeto   — objetos (view/proc/tabela) consumidos por cada
--                             endpoint, com status de validação e observação.
--   RBAC                    — recurso tela_inventario p/ admin/desenvolvedor.
--   SEED                    — endpoints reais levantados no incidente do BUCC
--                             de 2026-07-02 (ver docs/inventario-consumidores-bucc.md).
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_inventario_endpoint', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_inventario_endpoint (
        id             INT IDENTITY(1,1) PRIMARY KEY,
        endpoint       NVARCHAR(200)  NOT NULL,   -- nome do serviço/endpoint (ex.: GBE_ConsultaContratos)
        plataforma     NVARCHAR(100)  NULL,       -- ex.: 'GI', 'Salesforce', 'Genesys'
        consumidor     NVARCHAR(200)  NULL,       -- quem chama o endpoint
        banco          NVARCHAR(128)  NOT NULL DEFAULT 'BUCC',
        descricao      NVARCHAR(1000) NULL,
        responsavel    NVARCHAR(200)  NULL,
        ativo          BIT            NOT NULL DEFAULT 1,
        criado_por     NVARCHAR(64)   NULL,
        criado_em      DATETIME       NOT NULL DEFAULT GETDATE(),
        atualizado_por NVARCHAR(64)   NULL,
        atualizado_em  DATETIME       NULL
    );
    -- Nome único apenas entre os endpoints ATIVOS (índice filtrado, padrão da
    -- 052): o soft delete (ativo=0) libera o nome para um novo cadastro.
    CREATE UNIQUE NONCLUSTERED INDEX UX_inventario_endpoint_nome
        ON dbo.etl_inventario_endpoint (endpoint)
        WHERE ativo = 1;
    PRINT '[OK] Tabela dbo.etl_inventario_endpoint criada';
END
ELSE
    PRINT '[SKIP] Tabela dbo.etl_inventario_endpoint ja existe';
GO

IF OBJECT_ID('dbo.etl_inventario_objeto', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_inventario_objeto (
        id               INT IDENTITY(1,1) PRIMARY KEY,
        endpoint_id      INT            NOT NULL,  -- FK lógica p/ etl_inventario_endpoint
        objeto           NVARCHAR(300)  NOT NULL,  -- nome da view/proc/tabela
        tipo             VARCHAR(10)    NOT NULL DEFAULT 'view',
            -- view | proc | tabela
        status_validacao VARCHAR(20)    NOT NULL DEFAULT 'pendente',
            -- pendente | validado | com_erro
        observacao       NVARCHAR(1000) NULL,
        criado_por       NVARCHAR(64)   NULL,
        criado_em        DATETIME       NOT NULL DEFAULT GETDATE()
    );
    CREATE NONCLUSTERED INDEX IX_inventario_objeto_endpoint
        ON dbo.etl_inventario_objeto (endpoint_id);
    PRINT '[OK] Tabela dbo.etl_inventario_objeto criada';
END
ELSE
    PRINT '[SKIP] Tabela dbo.etl_inventario_objeto ja existe';
GO

-- Recurso RBAC 'tela_inventario' (tela Inventário de Consumidores) para os
-- perfis que documentam/validam. MERGE só insere o que faltar (padrão 052).
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_perfil_permissao')
BEGIN
    MERGE dbo.etl_perfil_permissao AS t
    USING (VALUES
        ('admin',         'tela_inventario'),
        ('desenvolvedor', 'tela_inventario')
    ) AS s (perfil_nome, recurso)
    ON t.perfil_nome = s.perfil_nome AND t.recurso = s.recurso
    WHEN NOT MATCHED THEN INSERT (perfil_nome, recurso, criado_por)
        VALUES (s.perfil_nome, s.recurso, 'migration-055');
    PRINT '[OK] Recurso tela_inventario garantido para admin/desenvolvedor';
END
ELSE
    PRINT '[SKIP] Tabela etl_perfil_permissao ainda nao existe (rode a 019 antes)';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- SEED — inventário inicial levantado no incidente do BUCC (2026-07-02).
-- Idempotente: IF NOT EXISTS por endpoint (independe de ativo, para não
-- ressuscitar um seed que o usuário tenha excluído).
-- ─────────────────────────────────────────────────────────────────────────────

IF NOT EXISTS (SELECT 1 FROM dbo.etl_inventario_endpoint
               WHERE endpoint = 'GBE_ConsultaContratosCelularEmailIREndereco_SF')
BEGIN
    DECLARE @eid1 INT;
    INSERT INTO dbo.etl_inventario_endpoint
        (endpoint, plataforma, consumidor, banco, descricao, criado_por)
    VALUES
        ('GBE_ConsultaContratosCelularEmailIREndereco_SF', 'GI', 'Salesforce', 'BUCC',
         'Endpoint do GI com erro reportado em 2026-07-02 durante a restauração do BUCC; validar se as views possuem o campo de CNPJ e se já foram recompiladas.',
         'SEED');
    SET @eid1 = SCOPE_IDENTITY();
    INSERT INTO dbo.etl_inventario_objeto (endpoint_id, objeto, tipo, status_validacao, criado_por)
    VALUES
        (@eid1, 'VW_PESSOAS_VINCULADAS_GENESYS',      'view', 'pendente', 'SEED'),
        (@eid1, 'VW_CONTRATO_IMPOSTO_RENDA',          'view', 'pendente', 'SEED'),
        (@eid1, 'VW_CELULAR_CONTRATOS_CVP_GENESYS',   'view', 'pendente', 'SEED'),
        (@eid1, 'VW_FIXA_CONTRATOS_CVP_GENESYS',      'view', 'pendente', 'SEED'),
        (@eid1, 'VW_ENDERECO_CONTRATOS_CVP_GENESYS',  'view', 'pendente', 'SEED'),
        (@eid1, 'VW_EMAIL_CONTRATOS_CVP_GENESYS',     'view', 'pendente', 'SEED');
    PRINT '[OK] Seed: GBE_ConsultaContratosCelularEmailIREndereco_SF (6 views)';
END
ELSE
    PRINT '[SKIP] Seed: GBE_ConsultaContratosCelularEmailIREndereco_SF ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_inventario_endpoint
               WHERE endpoint = 'GBE_ConsultaContratos')
BEGIN
    INSERT INTO dbo.etl_inventario_endpoint
        (endpoint, plataforma, consumidor, banco, descricao, criado_por)
    VALUES
        ('GBE_ConsultaContratos', 'GI', 'Salesforce', 'BUCC',
         'Consultado pelo SF (Salesforce).', 'SEED');
    PRINT '[OK] Seed: GBE_ConsultaContratos (sem objetos mapeados ainda)';
END
ELSE
    PRINT '[SKIP] Seed: GBE_ConsultaContratos ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_inventario_endpoint
               WHERE endpoint = 'Processo Genesys — contatos de clientes (Jordan)')
BEGIN
    DECLARE @eid3 INT;
    INSERT INTO dbo.etl_inventario_endpoint
        (endpoint, plataforma, consumidor, banco, descricao, criado_por)
    VALUES
        ('Processo Genesys — contatos de clientes (Jordan)', 'Genesys', 'Equipe Jordan', 'BUCC',
         'Processo que consulta contatos de clientes; confirmado em 2026-07-02.', 'SEED');
    SET @eid3 = SCOPE_IDENTITY();
    INSERT INTO dbo.etl_inventario_objeto (endpoint_id, objeto, tipo, status_validacao, criado_por)
    VALUES (@eid3, 'VW_CLIENTES_EMAIL_TELEFONE_CVP', 'view', 'pendente', 'SEED');
    PRINT '[OK] Seed: Processo Genesys — contatos de clientes (Jordan) (1 view)';
END
ELSE
    PRINT '[SKIP] Seed: Processo Genesys — contatos de clientes (Jordan) ja existe';
GO
