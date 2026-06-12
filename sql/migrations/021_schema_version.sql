-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 021 — Controle de versão de schema (etl_schema_version)
--
--   Tabela de registro de migrations aplicadas. Usada por sql/migrate.py para
--   determinar quais migrations precisam ser aplicadas em cada ambiente.
--   Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_schema_version')
BEGIN
    CREATE TABLE dbo.etl_schema_version (
        id             INT          IDENTITY(1,1) NOT NULL,
        migration_name VARCHAR(120) NOT NULL,
        applied_at     DATETIME     NOT NULL DEFAULT GETDATE(),
        applied_by     VARCHAR(50)  NULL,
        checksum       VARCHAR(64)  NULL,
        CONSTRAINT PK_schema_version PRIMARY KEY (id),
        CONSTRAINT UQ_schema_version_name UNIQUE (migration_name)
    );
    PRINT '[OK] Tabela etl_schema_version criada';
END
GO

-- Seed: registra como aplicadas todas as migrations que já existiam antes desta tabela.
-- Se a tabela acabou de ser criada (está vazia), insere as migrations 002-020.
-- Se já tem registros (idempotência), o MERGE não duplica.
IF (SELECT COUNT(*) FROM dbo.etl_schema_version) = 0
BEGIN
    INSERT INTO dbo.etl_schema_version (migration_name, applied_by) VALUES
        ('002_audit_trail_depends_on',                 'migration-021-seed'),
        ('003_start_date_versoes',                     'migration-021-seed'),
        ('004_lineage_columns',                        'migration-021-seed'),
        ('005_object_type_varchar_expand',             'migration-021-seed'),
        ('006_governance_metadata',                    'migration-021-seed'),
        ('007_pipeline_advanced_fields',               'migration-021-seed'),
        ('008_job_types_audit_limit',                  'migration-021-seed'),
        ('009_test_pipelines',                         'migration-021-seed'),
        ('010_datastage_job_log',                      'migration-021-seed'),
        ('011_ds_job_log_timing',                      'migration-021-seed'),
        ('012_job_ssh_conn_id',                        'migration-021-seed'),
        ('013_operacao_fase2',                         'migration-021-seed'),
        ('014_teams_webhook_config',                   'migration-021-seed'),
        ('015_factory_log',                            'migration-021-seed'),
        ('016_ds_queued_seconds',                      'migration-021-seed'),
        ('017_scheduling_avancado',                    'migration-021-seed'),
        ('018_horarios_multiplos',                     'migration-021-seed'),
        ('019_usuario_perfil',                         'migration-021-seed'),
        ('020_airflow_role_perfil',                    'migration-021-seed'),
        ('021_schema_version',                         'migration-021-seed');
    PRINT '[OK] Seed: 20 migrations anteriores registradas como aplicadas';
END
GO
