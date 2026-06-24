-- 044_perfil_perm_telas.sql
-- Alinha a seed de permissões RBAC ao estado já curado em produção e remove o
-- recurso de uma tela que foi excluída do produto.
--
-- Contexto: os recursos de tela tela_impacto_campo, tela_plano_ajuste,
-- tela_malha_ds e tela_powerbi nunca foram semeados por migration; o
-- tela_ds_console só foi semeado para 'admin' (migration 041). Em produção,
-- porém, esses recursos já estão concedidos (atribuídos à mão em
-- Admin > Usuários & Perfis) — então um ambiente NOVO nasceria sem eles e os
-- menus correspondentes ficariam invisíveis para os perfis certos. Aqui
-- garantimos o mesmo estado de forma rastreável, espelhando a configuração
-- atual: telas só de DataStage/Power BI para admin; impacto/planos/malha_ds e o
-- console DataStage também para 'desenvolvedor'.
--
-- Já o tela_ds_monitor gateava uma tela de monitor que foi REMOVIDA do produto;
-- a seed 019 ainda o concede a todos os perfis. Limpamos o recurso vestigial
-- para não ressuscitá-lo em ambientes novos nem poluir a tela de perfis.
--
-- Idempotente: MERGE só insere o que faltar; DELETE é no-op se já não existir.
-- Degrada graciosamente se a tabela ainda não existir (ambientes pré-019).

IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_perfil_permissao')
BEGIN
    -- 1) Recursos de tela já concedidos em produção, agora rastreáveis na seed.
    MERGE dbo.etl_perfil_permissao AS t
    USING (VALUES
        -- admin: enxerga todas as telas
        ('admin',         'tela_impacto_campo'), ('admin',         'tela_plano_ajuste'),
        ('admin',         'tela_malha_ds'),       ('admin',         'tela_powerbi'),
        -- desenvolvedor: impacto/planos + estrutura/console DataStage
        ('desenvolvedor', 'tela_impacto_campo'), ('desenvolvedor', 'tela_plano_ajuste'),
        ('desenvolvedor', 'tela_malha_ds'),       ('desenvolvedor', 'tela_ds_console')
    ) AS s (perfil_nome, recurso)
    ON t.perfil_nome = s.perfil_nome AND t.recurso = s.recurso
    WHEN NOT MATCHED THEN INSERT (perfil_nome, recurso, criado_por)
        VALUES (s.perfil_nome, s.recurso, 'migration-044');
    PRINT '[OK] Recursos de tela (impacto/planos/malha_ds/powerbi/ds_console) garantidos';

    -- 2) tela_ds_monitor: tela removida do produto -> limpa o recurso órfão.
    DELETE FROM dbo.etl_perfil_permissao WHERE recurso = 'tela_ds_monitor';
    PRINT '[OK] Recurso vestigial tela_ds_monitor removido';
END
ELSE
    PRINT '[SKIP] Tabela etl_perfil_permissao ainda nao existe (rode a 019 antes)';
GO
