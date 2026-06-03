-- =============================================================================
-- ORQUESTRA — Tabela de parâmetros da aplicação
-- Centraliza configurações sem precisar alterar código
-- =============================================================================

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_app_config'
)
BEGIN
    CREATE TABLE dbo.etl_app_config (
        config_key    VARCHAR(100)  NOT NULL PRIMARY KEY,
        config_value  VARCHAR(500)  NOT NULL,
        descricao     VARCHAR(500)  NULL,
        updated_by    VARCHAR(100)  NULL,
        updated_at    DATETIME      NOT NULL DEFAULT GETDATE()
    );
    PRINT 'Tabela dbo.etl_app_config criada.';
END
GO

-- Inserir/atualizar parâmetros padrão
MERGE dbo.etl_app_config AS t
USING (VALUES
  ('dashboard_refresh_interval_sec', '60',
   'Intervalo de auto-refresh do Dashboard em segundos (0 = desativado)'),

  ('failure_badge_refresh_sec',      '300',
   'Frequência de atualização do badge de falhas no header (segundos)'),

  ('failure_badge_hours_lookback',   '24',
   'Badge de falhas: janela de tempo a verificar (horas)'),

  ('app_version',      '2.1.0',
   'Versão atual do ORQUESTRA — atualizar a cada release'),

  ('app_release_name', 'Sprint 1 — Junho/2026',
   'Descrição do release atual — exibida no rodapé da UI'),

  ('pipeline_query_limit', '20',
   'Número de pipelines por página na tabela'),

  ('jobs_query_limit',     '50',
   'Número de jobs por página na tabela'),

  ('logs_query_limit',     '30',
   'Número de logs por página na tabela')
) AS s (config_key, config_value, descricao)
ON t.config_key = s.config_key
WHEN MATCHED     THEN UPDATE SET t.descricao   = s.descricao
WHEN NOT MATCHED THEN INSERT (config_key, config_value, descricao)
                      VALUES (s.config_key, s.config_value, s.descricao);
GO

PRINT '==> etl_app_config populada com parâmetros padrão.';
GO

-- View para consulta fácil
SELECT config_key, config_value, descricao, updated_at
FROM dbo.etl_app_config
ORDER BY config_key;
GO
