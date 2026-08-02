-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 070 — Malha: agrupadora de pipelines (F7, spec §4b de dependências)
--
-- O QUE É: a malha é o análogo da sequence MESTRE do DataStage (a sequence que
--   orquestra outras sequences) e da malha/SMART Folder do Control-M — uma
--   entidade nomeada que agrupa pipelines para montagem e leitura de conjunto.
--
-- O QUE NÃO É: um executor novo. Quem roda continua sendo o modelo da spec
--   (ODATE + push + guardiã), e as DEPENDÊNCIAS continuam GLOBAIS em
--   etl_pipeline_dependencia (migration 067) — desenhar uma aresta no diagrama
--   da malha (F8) grava NAQUELA tabela. A malha é agrupador e lente de
--   montagem; não nasce aqui uma segunda fonte de verdade de orquestração.
--
-- DECISÕES DE MODELO:
--   • etl_malha_pipeline.pipeline_name tem ON DELETE CASCADE de propósito
--     (aceite da F7): excluir um pipeline faz o MEMBRO sumir sem quebrar a
--     malha. Contraste com FK_dep_predecessor (067), que BLOQUEIA o DELETE —
--     lá o sumiço silencioso mudaria a orquestração; aqui muda só a visão.
--   • layout_x/layout_y: posição do nó no diagrama de montagem (F8). NULL =
--     sem posição salva (o editor aplica layout automático).
--   • PK composta (malha_name, pipeline_name): um pipeline pode estar em N
--     malhas — a mesma aresta real aparece em toda malha que contenha as
--     duas pontas.
--
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── (A) A malha ─────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.etl_malha', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_malha (
        -- Nome é a identidade (mesmo padrão de etl_pipeline.pipeline_name):
        -- é o que o operador digita, exporta e procura no log.
        malha_name    NVARCHAR(200)  NOT NULL
                      CONSTRAINT PK_etl_malha PRIMARY KEY,
        descricao     NVARCHAR(1000) NULL,
        ativo         BIT            NOT NULL
                      CONSTRAINT DF_malha_ativo DEFAULT 1,
        criado_em     DATETIME2      NOT NULL
                      CONSTRAINT DF_malha_criado_em DEFAULT SYSDATETIME(),
        criado_por    NVARCHAR(100)  NULL,
        atualizado_em DATETIME2      NULL
    );
    PRINT '[OK] Tabela etl_malha criada';
END
ELSE
    PRINT '[--] etl_malha ja existe';
GO

-- ── (B) Membros da malha ────────────────────────────────────────────────────
IF OBJECT_ID('dbo.etl_malha_pipeline', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_malha_pipeline (
        malha_name    NVARCHAR(200) NOT NULL,
        -- NVARCHAR(200) casa exatamente com etl_pipeline.pipeline_name,
        -- senão o SQL Server recusa a FK (mesma lição da 067).
        pipeline_name NVARCHAR(200) NOT NULL,
        layout_x      FLOAT         NULL,
        layout_y      FLOAT         NULL,
        CONSTRAINT PK_etl_malha_pipeline PRIMARY KEY (malha_name, pipeline_name),
        -- Excluir a malha leva os membros junto: o vínculo não vive sem ela.
        CONSTRAINT FK_malha_pipe_malha FOREIGN KEY (malha_name)
            REFERENCES dbo.etl_malha (malha_name) ON DELETE CASCADE,
        -- CASCADE consciente (ver cabeçalho): excluir pipeline faz o membro
        -- sumir da malha sem quebrá-la — a tela avisa, ninguém trata erro.
        CONSTRAINT FK_malha_pipe_pipeline FOREIGN KEY (pipeline_name)
            REFERENCES dbo.etl_pipeline (pipeline_name) ON DELETE CASCADE
    );
    PRINT '[OK] Tabela etl_malha_pipeline criada';
END
ELSE
    PRINT '[--] etl_malha_pipeline ja existe';
GO

-- Caminho inverso: "em que malhas este pipeline está?" — pergunta da tela de
-- cadastro (F8) e do aviso de exclusão de pipeline.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_malha_pipe_pipeline'
               AND object_id = OBJECT_ID('dbo.etl_malha_pipeline'))
BEGIN
    CREATE INDEX ix_malha_pipe_pipeline ON dbo.etl_malha_pipeline (pipeline_name);
    PRINT '[OK] indice ix_malha_pipe_pipeline criado';
END
ELSE
    PRINT '[--] indice ix_malha_pipe_pipeline ja existe';
GO
