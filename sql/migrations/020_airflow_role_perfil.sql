-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 020 — Mapeamento Airflow Role → Perfil ORQUESTRA
--
--   etl_airflow_role_perfil → de-para entre roles do Airflow e perfis internos.
--   Usado no 1º login: se o usuário tem um role Airflow mapeado aqui,
--   recebe o perfil correspondente em vez do default 'consulta'.
--
--   Prioridade: se o usuário tem múltiplos roles, usa o de maior prioridade
--   (menor valor em ordem_prioridade → mais privilegiado).
--
--   Gerenciável via Admin → Usuários & Perfis → Mapeamento de Roles.
--   Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_airflow_role_perfil')
BEGIN
    CREATE TABLE dbo.etl_airflow_role_perfil (
        role_airflow      VARCHAR(100) NOT NULL,   -- nome exato do role no Airflow
        perfil_nome       VARCHAR(30)  NOT NULL,   -- FK etl_perfil
        ordem_prioridade  INT          NOT NULL DEFAULT 99,
        descricao         VARCHAR(200) NULL,
        ativo             BIT          NOT NULL DEFAULT 1,
        criado_em         DATETIME     NOT NULL DEFAULT GETDATE(),
        criado_por        VARCHAR(50)  NULL,
        atualizado_em     DATETIME     NULL,
        atualizado_por    VARCHAR(50)  NULL,
        CONSTRAINT PK_etl_airflow_role_perfil PRIMARY KEY (role_airflow),
        CONSTRAINT FK_arp_perfil FOREIGN KEY (perfil_nome)
            REFERENCES dbo.etl_perfil (perfil_nome)
    );
    PRINT '[OK] Tabela etl_airflow_role_perfil criada';
END
GO

-- ── Seed: roles padrão do Airflow ──────────────────────────────────────────
-- Admin(1) > Op(2) > User(3) > Viewer(4) > Public(5)
MERGE dbo.etl_airflow_role_perfil AS t
USING (VALUES
    ('Admin',   'admin',        1, 'Administrador do Airflow → admin do ORQUESTRA'),
    ('Op',      'desenvolvedor',2, 'Operator do Airflow → Desenvolvedor ETL'),
    ('User',    'operador',     3, 'Usuário padrão do Airflow → Operador'),
    ('Viewer',  'consulta',     4, 'Visualizador do Airflow → Consulta'),
    ('Public',  'consulta',     5, 'Acesso público (sem role) → Consulta')
) AS s (role_airflow, perfil_nome, ordem_prioridade, descricao)
ON t.role_airflow = s.role_airflow
WHEN NOT MATCHED THEN
    INSERT (role_airflow, perfil_nome, ordem_prioridade, descricao, criado_por)
    VALUES (s.role_airflow, s.perfil_nome, s.ordem_prioridade, s.descricao, 'migration-020');
GO
