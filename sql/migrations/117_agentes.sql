-- sql/migrations/117_agentes.sql
-- F1 da spec docs/spec-agentes-datastage.md: fundação da tela "Agentes" — o
-- catálogo de agentes de IA (o primeiro é o de mapeamento DataStage). Cria o
-- esquema INTEIRO da entrega (conversas, mensagens, fatos, propostas,
-- aprendizados) de uma vez, como a 106_lineage_isx.sql fez para as suas
-- quatro fases — só a F1 usa a parte de RBAC/identidade; o resto fica vazio
-- até as fases seguintes (F4 histórico, F5 fatos/propostas, F6 aprendizados).
--
-- Idempotente (roda 2×): IF OBJECT_ID(...) IS NULL / IF NOT EXISTS / IF
-- COL_LENGTH(...) IS NULL em cada bloco. SEM índice filtrado (WHERE) em
-- nenhum CREATE INDEX — gotcha do QUOTED_IDENTIFIER já pago numa migration
-- anterior (Msg 1934, e pior: todo DML seguinte na tabela passa a exigir
-- QUOTED_IDENTIFIER ON). A unicidade de identidade_gateway é conferida na
-- APLICAÇÃO (api/routers/admin.py, ação user_identidade_set), não por índice.
-- Aplicada pela etapa 6c do deploy.sh.

-- ═══════════════════════════════════════════════════════════════════════════
-- 1. etl_agente_conversa
-- ═══════════════════════════════════════════════════════════════════════════
IF OBJECT_ID('dbo.etl_agente_conversa', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_agente_conversa (
        conversa_id     VARCHAR(36)   NOT NULL,  -- gerado no servidor (uuid4)
        agente          VARCHAR(40)   NOT NULL,  -- id do catálogo em código (services/agentes.py)
        matricula       VARCHAR(20)   NOT NULL,  -- largura de dbo.etl_usuario.matricula
        titulo          NVARCHAR(200) NULL,
        -- Projeto DataStage já resolvido nesta conversa (spec §3, "resolução
        -- do projeto"): lembrado ao retomar, evita perguntar de novo e evita
        -- consulta às cegas ao servidor.
        projeto         NVARCHAR(50)  NULL,
        criada_em       DATETIME2(0)  NOT NULL CONSTRAINT DF_etl_agente_conversa_criada DEFAULT GETDATE(),
        ultima_msg_em   DATETIME2(0)  NOT NULL CONSTRAINT DF_etl_agente_conversa_ultima DEFAULT GETDATE(),
        CONSTRAINT PK_etl_agente_conversa PRIMARY KEY (conversa_id)
    );
    PRINT '[OK] Tabela etl_agente_conversa criada';
END
ELSE
    PRINT '[SKIP] Tabela etl_agente_conversa ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_etl_agente_conversa_usuario' AND object_id = OBJECT_ID('dbo.etl_agente_conversa'))
BEGIN
    CREATE INDEX IX_etl_agente_conversa_usuario
        ON dbo.etl_agente_conversa (matricula, ultima_msg_em DESC);
    PRINT '[OK] Indice IX_etl_agente_conversa_usuario criado';
END
ELSE
    PRINT '[SKIP] IX_etl_agente_conversa_usuario ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_etl_agente_conversa_purga' AND object_id = OBJECT_ID('dbo.etl_agente_conversa'))
BEGIN
    CREATE INDEX IX_etl_agente_conversa_purga
        ON dbo.etl_agente_conversa (ultima_msg_em);
    PRINT '[OK] Indice IX_etl_agente_conversa_purga criado';
END
ELSE
    PRINT '[SKIP] IX_etl_agente_conversa_purga ja existe';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 2. etl_agente_mensagem
-- ═══════════════════════════════════════════════════════════════════════════
IF OBJECT_ID('dbo.etl_agente_mensagem', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_agente_mensagem (
        id              BIGINT IDENTITY(1,1) NOT NULL,
        conversa_id     VARCHAR(36)   NOT NULL,
        papel           VARCHAR(10)   NOT NULL,  -- 'user' | 'assistant'
        conteudo        NVARCHAR(MAX) NOT NULL,  -- JÁ redigido (filtro de segredos antes de gravar)
        status          VARCHAR(20)   NULL,
        -- Ferramentas executadas nesta rodada ([{nome, args, exit, ms}]),
        -- grafo, links e ids de proposta — tudo que a F2/F2b/F5 anexam.
        artefatos_json  NVARCHAR(MAX) NULL,
        criada_em       DATETIME2(0)  NOT NULL CONSTRAINT DF_etl_agente_mensagem_em DEFAULT GETDATE(),
        CONSTRAINT PK_etl_agente_mensagem PRIMARY KEY (id),
        CONSTRAINT FK_etl_agente_mensagem_conversa FOREIGN KEY (conversa_id)
            REFERENCES dbo.etl_agente_conversa (conversa_id) ON DELETE CASCADE
    );
    PRINT '[OK] Tabela etl_agente_mensagem criada';
END
ELSE
    PRINT '[SKIP] Tabela etl_agente_mensagem ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_etl_agente_mensagem_conversa' AND object_id = OBJECT_ID('dbo.etl_agente_mensagem'))
BEGIN
    CREATE INDEX IX_etl_agente_mensagem_conversa
        ON dbo.etl_agente_mensagem (conversa_id, criada_em);
    PRINT '[OK] Indice IX_etl_agente_mensagem_conversa criado';
END
ELSE
    PRINT '[SKIP] IX_etl_agente_mensagem_conversa ja existe';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 3. etl_agente_fato — SEM FK para a conversa (sobrevive à purga de 30 dias)
-- ═══════════════════════════════════════════════════════════════════════════
IF OBJECT_ID('dbo.etl_agente_fato', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_agente_fato (
        id                 BIGINT IDENTITY(1,1) NOT NULL,
        ds_project         NVARCHAR(50)   NOT NULL,
        job_name           NVARCHAR(200)  NOT NULL,
        pipeline_name      NVARCHAR(200)  NULL,   -- NULL = job fora de pipeline (B-19)
        tipo               VARCHAR(20)    NOT NULL,  -- stage|parametro|tabela|campo|lineage|descricao
        chave              NVARCHAR(300)  NOT NULL,
        valor_json         NVARCHAR(MAX)  NULL,
        -- dsjob_lstages | dsjob_lparams | dsjob_report | isx | dsx | interpretacao_aprovada
        origem             VARCHAR(30)    NOT NULL,
        evidencia          NVARCHAR(MAX)  NULL,   -- autocontida (comando + trecho filtrado), nunca aponta pra conversa
        ds_last_modified   VARCHAR(40)    NULL,   -- ISX: data do lastModified; DSX: data do arquivo
        lido_em            DATETIME2(0)   NOT NULL CONSTRAINT DF_etl_agente_fato_lido DEFAULT GETDATE(),
        lido_por           VARCHAR(20)    NOT NULL,
        aprovado_por       VARCHAR(20)    NULL,
        aprovado_em        DATETIME2(0)   NULL,
        obsoleto_em        DATETIME2(0)   NULL,
        CONSTRAINT PK_etl_agente_fato PRIMARY KEY (id)
    );
    PRINT '[OK] Tabela etl_agente_fato criada';
END
ELSE
    PRINT '[SKIP] Tabela etl_agente_fato ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_etl_agente_fato_job' AND object_id = OBJECT_ID('dbo.etl_agente_fato'))
BEGIN
    CREATE INDEX IX_etl_agente_fato_job
        ON dbo.etl_agente_fato (ds_project, job_name, tipo);
    PRINT '[OK] Indice IX_etl_agente_fato_job criado';
END
ELSE
    PRINT '[SKIP] IX_etl_agente_fato_job ja existe';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 4. etl_agente_proposta — SEM FK para a conversa
-- ═══════════════════════════════════════════════════════════════════════════
IF OBJECT_ID('dbo.etl_agente_proposta', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_agente_proposta (
        id              BIGINT IDENTITY(1,1) NOT NULL,
        conversa_id     VARCHAR(36)   NULL,   -- referência informativa; sem FK (sobrevive à purga)
        agente          VARCHAR(40)   NOT NULL,
        matricula       VARCHAR(20)   NOT NULL,
        ds_project      NVARCHAR(50)  NOT NULL,
        job_name        NVARCHAR(200) NOT NULL,
        tipo            VARCHAR(20)   NOT NULL,
        chave           NVARCHAR(300) NOT NULL,
        valor_json      NVARCHAR(MAX) NULL,
        evidencia       NVARCHAR(MAX) NULL,
        motivo          NVARCHAR(600) NULL,
        estado          VARCHAR(12)   NOT NULL CONSTRAINT DF_etl_agente_proposta_estado DEFAULT 'pendente',  -- pendente|aprovada|recusada|expirada
        criada_em       DATETIME2(0)  NOT NULL CONSTRAINT DF_etl_agente_proposta_criada DEFAULT GETDATE(),
        decidida_por    VARCHAR(20)   NULL,
        decidida_em     DATETIME2(0)  NULL,
        fato_id         BIGINT        NULL,
        CONSTRAINT PK_etl_agente_proposta PRIMARY KEY (id)
    );
    PRINT '[OK] Tabela etl_agente_proposta criada';
END
ELSE
    PRINT '[SKIP] Tabela etl_agente_proposta ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_etl_agente_proposta_estado' AND object_id = OBJECT_ID('dbo.etl_agente_proposta'))
BEGIN
    CREATE INDEX IX_etl_agente_proposta_estado
        ON dbo.etl_agente_proposta (estado, criada_em);
    PRINT '[OK] Indice IX_etl_agente_proposta_estado criado';
END
ELSE
    PRINT '[SKIP] IX_etl_agente_proposta_estado ja existe';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 5. etl_agente_aprendizado
-- ═══════════════════════════════════════════════════════════════════════════
IF OBJECT_ID('dbo.etl_agente_aprendizado', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_agente_aprendizado (
        id              BIGINT IDENTITY(1,1) NOT NULL,
        agente          VARCHAR(40)    NOT NULL,
        tipo            VARCHAR(20)    NOT NULL,  -- acesso|busca|leitura|detalhamento|erro
        assinatura      CHAR(64)       NOT NULL,  -- sha256 da chave normalizada (dedupe)
        titulo          NVARCHAR(200)  NOT NULL,
        corpo           NVARCHAR(2000) NOT NULL,
        evidencia       NVARCHAR(MAX)  NULL,
        origem          VARCHAR(20)    NOT NULL,  -- ferramenta|interpretacao|semente
        estado          VARCHAR(12)    NOT NULL CONSTRAINT DF_etl_agente_aprendizado_estado DEFAULT 'rascunho',  -- rascunho|validado|obsoleto|rejeitado
        criado_em       DATETIME2(0)   NOT NULL CONSTRAINT DF_etl_agente_aprendizado_criado DEFAULT GETDATE(),
        validado_por    VARCHAR(20)    NULL,
        validado_em     DATETIME2(0)   NULL,
        ultimo_uso_em   DATETIME2(0)   NULL,
        usos            INT            NOT NULL CONSTRAINT DF_etl_agente_aprendizado_usos DEFAULT 0,
        revalidar_em    DATETIME2(0)   NULL,
        CONSTRAINT PK_etl_agente_aprendizado PRIMARY KEY (id),
        CONSTRAINT UQ_etl_agente_aprendizado UNIQUE (agente, assinatura)
    );
    PRINT '[OK] Tabela etl_agente_aprendizado criada';
END
ELSE
    PRINT '[SKIP] Tabela etl_agente_aprendizado ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_etl_agente_aprendizado_estado' AND object_id = OBJECT_ID('dbo.etl_agente_aprendizado'))
BEGIN
    CREATE INDEX IX_etl_agente_aprendizado_estado
        ON dbo.etl_agente_aprendizado (agente, estado, tipo);
    PRINT '[OK] Indice IX_etl_agente_aprendizado_estado criado';
END
ELSE
    PRINT '[SKIP] IX_etl_agente_aprendizado_estado ja existe';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 6. etl_usuario: identidade no gateway (D-16 — cadastro sobrepõe o padrão
--    cvp-<matrícula>). SEM índice único filtrado (gotcha QUOTED_IDENTIFIER,
--    Msg 1934) — a unicidade é conferida na aplicação (admin.py).
-- ═══════════════════════════════════════════════════════════════════════════
IF COL_LENGTH('dbo.etl_usuario', 'identidade_gateway') IS NULL
BEGIN
    ALTER TABLE dbo.etl_usuario ADD identidade_gateway VARCHAR(100) NULL;
    PRINT '[OK] etl_usuario.identidade_gateway';
END
ELSE PRINT '[SKIP] etl_usuario.identidade_gateway ja existe';
GO
IF COL_LENGTH('dbo.etl_usuario', 'identidade_gateway_por') IS NULL
BEGIN
    ALTER TABLE dbo.etl_usuario ADD identidade_gateway_por VARCHAR(20) NULL;
    PRINT '[OK] etl_usuario.identidade_gateway_por';
END
ELSE PRINT '[SKIP] etl_usuario.identidade_gateway_por ja existe';
GO
IF COL_LENGTH('dbo.etl_usuario', 'identidade_gateway_em') IS NULL
BEGIN
    ALTER TABLE dbo.etl_usuario ADD identidade_gateway_em DATETIME2(0) NULL;
    PRINT '[OK] etl_usuario.identidade_gateway_em';
END
ELSE PRINT '[SKIP] etl_usuario.identidade_gateway_em ja existe';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 7. Seeds
-- ═══════════════════════════════════════════════════════════════════════════
-- tela_agentes: SÓ no perfil admin (padrão da 060 para tela nova e restrita —
-- é assim que "o admin já nasce com a tela"). NENHUM outro perfil recebe
-- aqui; se o admin quiser abrir a outros, usa a Admin > Perfis já existente
-- (perfil_upsert) — mesmo mecanismo de qualquer outra tela_*. `agente_*`
-- (agente_datastage, agente_curador) NUNCA é semeado em perfil nenhum, nem
-- no admin: o admin passa por acao_admin (require_agente), e para os demais
-- é concessão explícita por usuário, sempre pelo admin.
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_perfil_permissao')
BEGIN
    MERGE dbo.etl_perfil_permissao AS t
    USING (SELECT 'admin' AS perfil_nome, 'tela_agentes' AS recurso) AS s
    ON t.perfil_nome = s.perfil_nome AND t.recurso = s.recurso
    WHEN NOT MATCHED THEN INSERT (perfil_nome, recurso, criado_por)
        VALUES (s.perfil_nome, s.recurso, 'migration-117');
    PRINT '[OK] tela_agentes semeada no perfil admin';
END
ELSE
    PRINT '[SKIP] Tabela etl_perfil_permissao ainda nao existe (rode a 019 antes)';
GO

-- Interruptores gerais (nascem desligados — o usuário liga em Admin >
-- Agentes depois de configurar o gateway e conceder os primeiros usuários).
IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'agentes_enabled')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    VALUES ('agentes_enabled', '0', 'Tela Agentes — interruptor geral', 'migration_117', GETDATE());
    PRINT '[OK] agentes_enabled = 0';
END
ELSE
    PRINT '[SKIP] agentes_enabled ja existe';
GO

IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'agente_datastage_enabled')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    VALUES ('agente_datastage_enabled', '0', 'Agente de mapeamento DataStage — interruptor proprio', 'migration_117', GETDATE());
    PRINT '[OK] agente_datastage_enabled = 0';
END
ELSE
    PRINT '[SKIP] agente_datastage_enabled ja existe';
GO

PRINT '[OK] migration 117 concluida';
GO
