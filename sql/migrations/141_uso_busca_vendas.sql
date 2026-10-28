-- 141_uso_busca_vendas.sql
-- Idempotente — seguro para rodar mais de uma vez.
-- Monitoramento de uso do módulo Busca & Vendas (/caixa-seguro/*) — spec
-- docs/spec-uso-busca-vendas.md.
--
--   etl_uso_evento    → 1 linha por ABERTURA de tela (acesso). Sem FK para
--                       etl_usuario de propósito: o evento sobrevive à remoção do usuário.
--   etl_uso_presenca  → 1 linha por matrícula, atualizada a cada batimento da aba
--                       visível; alimenta o "online agora" (janela de 10 min).
--   caixa_seguro_uso  → recurso RBAC da tela "Uso do módulo". Semeado SÓ no perfil
--                       admin; o Admin concede aos demais perfis/usuários.
--
-- Sem IP, sem user-agent: só matrícula, tela e instante (relógio do banco, Brasília).
-- ⚠️ Numeração: o `develop` também usa 141+ com outros nomes; o migrate.py controla
-- por NOME. Reconciliar ao promover o develop (mesma nota da 140).
SET NOCOUNT ON;

IF OBJECT_ID('dbo.etl_uso_evento', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_uso_evento (
        id          BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_uso_evento PRIMARY KEY,
        matricula   VARCHAR(20)  NOT NULL,
        modulo      VARCHAR(30)  NOT NULL CONSTRAINT DF_etl_uso_evento_modulo DEFAULT 'busca_vendas',
        rota        VARCHAR(120) NOT NULL,
        tela        VARCHAR(80)  NOT NULL,
        detalhe     VARCHAR(40)  NULL,
        ocorrido_em DATETIME     NOT NULL CONSTRAINT DF_etl_uso_evento_em DEFAULT GETDATE()
    );
    PRINT '[OK] etl_uso_evento criada';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_etl_uso_evento_ocorrido'
               AND object_id = OBJECT_ID('dbo.etl_uso_evento'))
    CREATE INDEX IX_etl_uso_evento_ocorrido ON dbo.etl_uso_evento (ocorrido_em);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_etl_uso_evento_matricula'
               AND object_id = OBJECT_ID('dbo.etl_uso_evento'))
    CREATE INDEX IX_etl_uso_evento_matricula ON dbo.etl_uso_evento (matricula, ocorrido_em);
GO

IF OBJECT_ID('dbo.etl_uso_presenca', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_uso_presenca (
        matricula     VARCHAR(20)  NOT NULL CONSTRAINT PK_etl_uso_presenca PRIMARY KEY,
        rota          VARCHAR(120) NOT NULL,
        atualizado_em DATETIME     NOT NULL
    );
    PRINT '[OK] etl_uso_presenca criada';
END
GO

IF OBJECT_ID('dbo.etl_perfil_permissao', 'U') IS NOT NULL
BEGIN
    MERGE dbo.etl_perfil_permissao AS t
    USING (VALUES ('admin', 'caixa_seguro_uso')) AS s (perfil_nome, recurso)
    ON t.perfil_nome = s.perfil_nome AND t.recurso = s.recurso
    WHEN NOT MATCHED THEN INSERT (perfil_nome, recurso, criado_por)
        VALUES (s.perfil_nome, s.recurso, 'migration-141');
    PRINT '[OK] caixa_seguro_uso garantido no perfil admin';
END
ELSE
    PRINT '[SKIP] etl_perfil_permissao ausente (rode a 019 antes)';
GO
