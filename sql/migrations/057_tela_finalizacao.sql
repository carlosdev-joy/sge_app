-- 057_tela_finalizacao.sql
-- Recurso RBAC 'tela_finalizacao' (tela Finalizar Pipeline — encerramento manual de
-- execuções penduradas em RUNNING nos logs do Orquestra, sem tocar no DataStage).
-- Concede aos perfis com poder de operação (admin/desenvolvedor/operador); 'consulta'
-- fica de fora porque a tela existe só para agir.
--
-- Idempotente: MERGE só insere o que faltar. Degrada graciosamente se a tabela
-- ainda não existir (ambientes pré-019). Seguro para rodar mais de uma vez.

IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_perfil_permissao')
BEGIN
    MERGE dbo.etl_perfil_permissao AS t
    USING (VALUES
        ('admin',         'tela_finalizacao'),
        ('desenvolvedor', 'tela_finalizacao'),
        ('operador',      'tela_finalizacao')
    ) AS s (perfil_nome, recurso)
    ON t.perfil_nome = s.perfil_nome AND t.recurso = s.recurso
    WHEN NOT MATCHED THEN INSERT (perfil_nome, recurso, criado_por)
        VALUES (s.perfil_nome, s.recurso, 'migration-057');
    PRINT '[OK] Recurso tela_finalizacao garantido para os perfis de operacao';
END
ELSE
    PRINT '[SKIP] Tabela etl_perfil_permissao ainda nao existe (rode a 019 antes)';
GO
