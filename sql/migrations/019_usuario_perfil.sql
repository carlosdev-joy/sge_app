-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 019 — RBAC: tabela de perfis de usuário
--   etl_usuario_perfil:
--     matricula   → matrícula corporativa (chave)
--     perfil      → 'admin' | 'desenvolvedor' | 'operador' | 'consulta'
--   Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_usuario_perfil'
)
BEGIN
    CREATE TABLE dbo.etl_usuario_perfil (
        matricula   VARCHAR(20)  NOT NULL,
        perfil      VARCHAR(20)  NOT NULL CHECK (perfil IN ('admin','desenvolvedor','operador','consulta')),
        criado_em   DATETIME     NOT NULL DEFAULT GETDATE(),
        criado_por  VARCHAR(50)  NULL,
        CONSTRAINT PK_etl_usuario_perfil PRIMARY KEY (matricula)
    );
    PRINT '[OK] Tabela etl_usuario_perfil criada';
END
GO

-- Seed do administrador original — mantenha ou atualize conforme necessário
IF NOT EXISTS (SELECT 1 FROM dbo.etl_usuario_perfil WHERE matricula = 'CVT38571')
BEGIN
    INSERT INTO dbo.etl_usuario_perfil (matricula, perfil, criado_por)
    VALUES ('CVT38571', 'admin', 'migration-019');
    PRINT '[OK] Administrador CVT38571 inserido';
END
GO
