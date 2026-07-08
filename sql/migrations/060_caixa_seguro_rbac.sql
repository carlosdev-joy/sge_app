-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 060 — Caixa Seguro (Fase 1): RBAC por usuário
--
--   etl_usuario_permissao → permissões extras concedidas a usuários específicos,
--                           além das herdadas do perfil (matricula × recurso).
--                           carregar_usuario (api/deps.py) une perfil + overrides.
--
-- Recursos novos:  tela_caixa_seguro        → seção /caixa-seguro/*
--                  caixa_seguro_operacional → nível elevado dentro da seção
--                  (substitui o toggle demo Operacional×Funcionário da POC)
--
-- Semeados SOMENTE no perfil 'admin'; os demais usuários recebem acesso
-- individualmente via etl_usuario_permissao (Admin > Usuários & Perfis).
--
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── Permissões por usuário (overrides além do perfil) ────────────────────────
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_usuario_permissao')
BEGIN
    CREATE TABLE dbo.etl_usuario_permissao (
        matricula    VARCHAR(20) NOT NULL,
        recurso      VARCHAR(50) NOT NULL,
        criado_em    DATETIME    NOT NULL DEFAULT GETDATE(),
        criado_por   VARCHAR(50) NULL,
        CONSTRAINT PK_etl_usuario_permissao PRIMARY KEY (matricula, recurso),
        CONSTRAINT FK_usuario_permissao_usuario FOREIGN KEY (matricula)
            REFERENCES dbo.etl_usuario (matricula) ON DELETE CASCADE
    );
    PRINT '[OK] Tabela etl_usuario_permissao criada';
END
GO

-- ── Recursos do Caixa Seguro no perfil admin ─────────────────────────────────
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_perfil_permissao')
BEGIN
    MERGE dbo.etl_perfil_permissao AS t
    USING (VALUES
        ('admin', 'tela_caixa_seguro'),
        ('admin', 'caixa_seguro_operacional')
    ) AS s (perfil_nome, recurso)
    ON t.perfil_nome = s.perfil_nome AND t.recurso = s.recurso
    WHEN NOT MATCHED THEN INSERT (perfil_nome, recurso, criado_por)
        VALUES (s.perfil_nome, s.recurso, 'migration-060');
    PRINT '[OK] Recursos do Caixa Seguro garantidos no perfil admin';
END
ELSE
    PRINT '[SKIP] Tabela etl_perfil_permissao ainda nao existe (rode a 019 antes)';
GO
