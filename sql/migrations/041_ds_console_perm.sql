-- 041_ds_console_perm.sql
-- Recurso RBAC 'tela_ds_console' (Console DataStage). O acesso ao console deixa
-- de ser só de admin e passa a ser configurável por perfil em
-- Admin > Usuários & Perfis. Aqui semeamos o recurso para o perfil 'admin'
-- (para os administradores já enxergarem o menu). Os demais perfis recebem por
-- atribuição manual na tela de perfis.
--
-- Idempotente: MERGE só insere se ainda não existir. Degrada se a tabela não
-- existir (ambientes que ainda não rodaram a migration 019).

IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_perfil_permissao')
BEGIN
    MERGE dbo.etl_perfil_permissao AS t
    USING (VALUES
        ('admin', 'tela_ds_console')
    ) AS s (perfil_nome, recurso)
    ON t.perfil_nome = s.perfil_nome AND t.recurso = s.recurso
    WHEN NOT MATCHED THEN INSERT (perfil_nome, recurso, criado_por)
        VALUES (s.perfil_nome, s.recurso, 'migration-041');

    PRINT '[OK] Recurso tela_ds_console garantido para o perfil admin';
END
ELSE
    PRINT '[SKIP] Tabela etl_perfil_permissao ainda não existe (rode a 019 antes)';
GO
