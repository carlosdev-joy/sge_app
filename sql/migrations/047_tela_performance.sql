-- 047_tela_performance.sql
-- Recurso RBAC 'tela_performance' (tela de Performance — alertas de duração/SLA).
-- Concede aos perfis operacionais (admin/desenvolvedor/operador/consulta),
-- espelhando a visibilidade das demais telas de monitoramento (Logs/Dashboard).
--
-- Idempotente: MERGE só insere o que faltar. Degrada graciosamente se a tabela
-- ainda não existir (ambientes pré-019).

IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_perfil_permissao')
BEGIN
    MERGE dbo.etl_perfil_permissao AS t
    USING (VALUES
        ('admin',         'tela_performance'),
        ('desenvolvedor', 'tela_performance'),
        ('operador',      'tela_performance'),
        ('consulta',      'tela_performance')
    ) AS s (perfil_nome, recurso)
    ON t.perfil_nome = s.perfil_nome AND t.recurso = s.recurso
    WHEN NOT MATCHED THEN INSERT (perfil_nome, recurso, criado_por)
        VALUES (s.perfil_nome, s.recurso, 'migration-047');
    PRINT '[OK] Recurso tela_performance garantido para os perfis operacionais';
END
ELSE
    PRINT '[SKIP] Tabela etl_perfil_permissao ainda nao existe (rode a 019 antes)';
GO
