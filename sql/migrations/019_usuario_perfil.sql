-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 019 — RBAC completo: perfis, permissões, usuários e sessões
--
--   etl_perfil           → perfis de acesso (admin, desenvolvedor, operador, consulta)
--   etl_perfil_permissao → o que cada perfil pode acessar (telas e ações)
--   etl_usuario          → cadastro do usuário (dados do Airflow no 1º login;
--                          base para avatar/nome no "Olá, xxx")
--   etl_sessao           → tokens de sessão (hash SHA-256; sobrevivem ao F5)
--
-- Recursos (telas):  tela_dashboard, tela_pipelines, tela_jobs, tela_logs,
--                    tela_ds_monitor, tela_governanca, tela_malha, tela_admin
-- Recursos (ações):  acao_executar (rodar/rerun/ack), acao_editar (cadastrar
--                    pipelines/jobs/lineage/sequences), acao_admin (tudo do admin)
--
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── Perfis ───────────────────────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_perfil')
BEGIN
    CREATE TABLE dbo.etl_perfil (
        perfil_nome  VARCHAR(30)  NOT NULL,
        descricao    VARCHAR(200) NULL,
        criado_em    DATETIME     NOT NULL DEFAULT GETDATE(),
        criado_por   VARCHAR(50)  NULL,
        CONSTRAINT PK_etl_perfil PRIMARY KEY (perfil_nome)
    );
    PRINT '[OK] Tabela etl_perfil criada';
END
GO

-- ── Permissões por perfil ─────────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_perfil_permissao')
BEGIN
    CREATE TABLE dbo.etl_perfil_permissao (
        perfil_nome  VARCHAR(30) NOT NULL,
        recurso      VARCHAR(50) NOT NULL,
        criado_em    DATETIME    NOT NULL DEFAULT GETDATE(),
        criado_por   VARCHAR(50) NULL,
        CONSTRAINT PK_etl_perfil_permissao PRIMARY KEY (perfil_nome, recurso),
        CONSTRAINT FK_perm_perfil FOREIGN KEY (perfil_nome)
            REFERENCES dbo.etl_perfil (perfil_nome) ON DELETE CASCADE
    );
    PRINT '[OK] Tabela etl_perfil_permissao criada';
END
GO

-- ── Usuários ──────────────────────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_usuario')
BEGIN
    CREATE TABLE dbo.etl_usuario (
        matricula      VARCHAR(20)  NOT NULL,
        perfil_nome    VARCHAR(30)  NOT NULL DEFAULT 'consulta',
        primeiro_nome  VARCHAR(100) NULL,
        ultimo_nome    VARCHAR(100) NULL,
        email          VARCHAR(200) NULL,
        avatar_url     VARCHAR(500) NULL,      -- reservado para avatar futuro
        ativo          BIT          NOT NULL DEFAULT 1,
        primeiro_login DATETIME     NULL,
        ultimo_login   DATETIME     NULL,
        criado_em      DATETIME     NOT NULL DEFAULT GETDATE(),
        criado_por     VARCHAR(50)  NULL,
        CONSTRAINT PK_etl_usuario PRIMARY KEY (matricula),
        CONSTRAINT FK_usuario_perfil FOREIGN KEY (perfil_nome)
            REFERENCES dbo.etl_perfil (perfil_nome)
    );
    PRINT '[OK] Tabela etl_usuario criada';
END
GO

-- ── Sessões (token opaco, hash SHA-256 — a senha nunca é armazenada) ─────────
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_sessao')
BEGIN
    CREATE TABLE dbo.etl_sessao (
        token_hash  CHAR(64)    NOT NULL,       -- sha256 hex do token
        matricula   VARCHAR(20) NOT NULL,
        criado_em   DATETIME    NOT NULL DEFAULT GETDATE(),
        expira_em   DATETIME    NOT NULL,
        CONSTRAINT PK_etl_sessao PRIMARY KEY (token_hash)
    );
    CREATE INDEX IX_etl_sessao_matricula ON dbo.etl_sessao (matricula);
    CREATE INDEX IX_etl_sessao_expira    ON dbo.etl_sessao (expira_em);
    PRINT '[OK] Tabela etl_sessao criada';
END
GO

-- ── Seed: perfis padrão ───────────────────────────────────────────────────────
MERGE dbo.etl_perfil AS t
USING (VALUES
    ('admin',         'Acesso total, incluindo painel Admin e gestão de usuários'),
    ('desenvolvedor', 'Cadastra/edita pipelines, jobs, lineage e sequences; executa'),
    ('operador',      'Executa pipelines, reexecuta falhas, assume incidentes'),
    ('consulta',      'Somente visualização (dashboard, logs, malha, governança)')
) AS s (perfil_nome, descricao)
ON t.perfil_nome = s.perfil_nome
WHEN NOT MATCHED THEN INSERT (perfil_nome, descricao, criado_por)
    VALUES (s.perfil_nome, s.descricao, 'migration-019');
GO

-- ── Seed: permissões padrão por perfil ───────────────────────────────────────
MERGE dbo.etl_perfil_permissao AS t
USING (VALUES
    -- consulta: só telas de visualização
    ('consulta', 'tela_dashboard'), ('consulta', 'tela_pipelines'),
    ('consulta', 'tela_jobs'),      ('consulta', 'tela_logs'),
    ('consulta', 'tela_ds_monitor'),('consulta', 'tela_governanca'),
    ('consulta', 'tela_malha'),
    -- operador: consulta + executar
    ('operador', 'tela_dashboard'), ('operador', 'tela_pipelines'),
    ('operador', 'tela_jobs'),      ('operador', 'tela_logs'),
    ('operador', 'tela_ds_monitor'),('operador', 'tela_governanca'),
    ('operador', 'tela_malha'),     ('operador', 'acao_executar'),
    -- desenvolvedor: operador + editar
    ('desenvolvedor', 'tela_dashboard'), ('desenvolvedor', 'tela_pipelines'),
    ('desenvolvedor', 'tela_jobs'),      ('desenvolvedor', 'tela_logs'),
    ('desenvolvedor', 'tela_ds_monitor'),('desenvolvedor', 'tela_governanca'),
    ('desenvolvedor', 'tela_malha'),     ('desenvolvedor', 'acao_executar'),
    ('desenvolvedor', 'acao_editar'),
    -- admin: tudo
    ('admin', 'tela_dashboard'), ('admin', 'tela_pipelines'),
    ('admin', 'tela_jobs'),      ('admin', 'tela_logs'),
    ('admin', 'tela_ds_monitor'),('admin', 'tela_governanca'),
    ('admin', 'tela_malha'),     ('admin', 'tela_admin'),
    ('admin', 'acao_executar'),  ('admin', 'acao_editar'),
    ('admin', 'acao_admin')
) AS s (perfil_nome, recurso)
ON t.perfil_nome = s.perfil_nome AND t.recurso = s.recurso
WHEN NOT MATCHED THEN INSERT (perfil_nome, recurso, criado_por)
    VALUES (s.perfil_nome, s.recurso, 'migration-019');
GO

-- ── Seed: administrador original ─────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM dbo.etl_usuario WHERE matricula = 'CVT38571')
BEGIN
    INSERT INTO dbo.etl_usuario (matricula, perfil_nome, criado_por)
    VALUES ('CVT38571', 'admin', 'migration-019');
    PRINT '[OK] Administrador CVT38571 inserido';
END
GO
