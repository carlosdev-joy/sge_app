-- 093_chamado_triagem.sql
-- O veredito de triagem por chamado: dá para começar, ou falta informação?
--
-- É a pergunta que o painel da estação responde todo dia e que nenhuma coluna
-- do espelho respondia. O veredito é binário de propósito (PODE INICIAR ×
-- RETORNAR AO SOLICITANTE): "mais ou menos suficiente" não ajuda ninguém a
-- decidir o que fazer com o chamado agora.
--
-- ── A coluna mais importante desta migration é `triagem_origem` ───────────
-- O veredito pode vir da IA ou da heurística de recorte. As duas produzem o
-- mesmo formato, e é justamente por isso que a origem precisa estar gravada:
-- heurística apresentada como análise de IA é engano do operador, que confia
-- num julgamento que ninguém fez. Com a coluna, a tela DIZ quem julgou.
--
-- ── Por que `triagem_hash` existe ─────────────────────────────────────────
-- A triagem custa uma chamada de IA por chamado. Sem uma marca do texto que
-- foi analisado, o lote de 15 em 15 minutos re-triaria a fila inteira para
-- sempre — e, pior, um chamado cuja descrição MUDOU ficaria com o veredito
-- antigo, que é o defeito silencioso. O hash resolve os dois: só entra na fila
-- de triagem quem nunca foi triado ou cujo texto mudou.
--
-- ── `triagem_erro` ────────────────────────────────────────────────────────
-- Quando a IA falha, o chamado NÃO fica sem veredito: cai na heurística, e o
-- motivo da falha fica aqui. Sem esta coluna, "a IA está fora do ar há três
-- dias" e "a IA concorda com a heurística" têm exatamente a mesma aparência.
--
-- Idempotente. Colunas NULL para o que já existe; o lote preenche.

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_chamado')
BEGIN
    PRINT '[SKIP] dbo.etl_chamado ainda nao existe (rode a 088 antes)';
END
ELSE
BEGIN
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='veredito')
    BEGIN
        -- 'PODE INICIAR' | 'RETORNAR AO SOLICITANTE'
        ALTER TABLE dbo.etl_chamado ADD veredito VARCHAR(30) NULL;
        PRINT '[OK] Coluna veredito criada';
    END
    ELSE PRINT '[SKIP] veredito ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='suficiencia')
    BEGIN
        -- suficiente | parcial | insuficiente
        ALTER TABLE dbo.etl_chamado ADD suficiencia VARCHAR(20) NULL;
        PRINT '[OK] Coluna suficiencia criada';
    END
    ELSE PRINT '[SKIP] suficiencia ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='resumo')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD resumo NVARCHAR(400) NULL;
        PRINT '[OK] Coluna resumo criada';
    END
    ELSE PRINT '[SKIP] resumo ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='entendimento')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD entendimento NVARCHAR(1000) NULL;
        PRINT '[OK] Coluna entendimento criada';
    END
    ELSE PRINT '[SKIP] entendimento ja existe';

    -- Uma lacuna por linha, separadas por quebra: a tela renderiza como lista
    -- e o SQL não precisa saber disso. Tabela filha para três frases curtas
    -- custaria mais do que resolve.
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='lacunas')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD lacunas NVARCHAR(2000) NULL;
        PRINT '[OK] Coluna lacunas criada';
    END
    ELSE PRINT '[SKIP] lacunas ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='perguntas')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD perguntas NVARCHAR(2000) NULL;
        PRINT '[OK] Coluna perguntas criada';
    END
    ELSE PRINT '[SKIP] perguntas ja existe';

    -- 'ia' | 'heuristica'. A coluna que impede o engano: heurística
    -- apresentada como análise de IA é veredito em que ninguém pensou.
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='triagem_origem')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD triagem_origem VARCHAR(20) NULL;
        PRINT '[OK] Coluna triagem_origem criada';
    END
    ELSE PRINT '[SKIP] triagem_origem ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='triagem_modelo')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD triagem_modelo VARCHAR(60) NULL;
        PRINT '[OK] Coluna triagem_modelo criada';
    END
    ELSE PRINT '[SKIP] triagem_modelo ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='triagem_em')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD triagem_em DATETIME NULL;
        PRINT '[OK] Coluna triagem_em criada';
    END
    ELSE PRINT '[SKIP] triagem_em ja existe';

    -- SHA-256 do texto analisado: 64 hex. Só re-tria quem mudou.
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='triagem_hash')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD triagem_hash VARCHAR(64) NULL;
        PRINT '[OK] Coluna triagem_hash criada';
    END
    ELSE PRINT '[SKIP] triagem_hash ja existe';

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
                     AND COLUMN_NAME='triagem_erro')
    BEGIN
        ALTER TABLE dbo.etl_chamado ADD triagem_erro NVARCHAR(400) NULL;
        PRINT '[OK] Coluna triagem_erro criada';
    END
    ELSE PRINT '[SKIP] triagem_erro ja existe';
END
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- Interruptor próprio da triagem
-- ═══════════════════════════════════════════════════════════════════════════
-- NÃO reaproveita `caixa_ia_enabled`: aquele governa a visibilidade dos
-- assistentes do Caixa Seguro, e amarrar os dois faria desligar o Diego
-- desligar a triagem de chamados, sem que ninguém tivesse pedido.
--
-- Nasce em '0': uma instalação que aplique a migration sem ter gateway
-- configurado não deve começar a disparar chamadas de IA sozinha.
IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'chamados_triagem_habilitada')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    VALUES ('chamados_triagem_habilitada', '0',
            'Triagem de chamados por IA no ciclo do sync (0/1)', 'migration_093', GETDATE());
    PRINT '[OK] chamados_triagem_habilitada criada (desligada)';
END
ELSE PRINT '[SKIP] chamados_triagem_habilitada ja existe';
GO

-- Teto de chamados triados por ciclo. A fila é de ~50, mas um lote sem teto
-- transformaria um dia atípico numa conta de IA inesperada e num ciclo que
-- estoura o dagrun_timeout de 10 min.
IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'chamados_triagem_lote')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao, updated_by, updated_at)
    VALUES ('chamados_triagem_lote', '20',
            'Quantos chamados a triagem analisa por ciclo', 'migration_093', GETDATE());
    PRINT '[OK] chamados_triagem_lote criada (20)';
END
ELSE PRINT '[SKIP] chamados_triagem_lote ja existe';
GO

-- ⚠️ DEPOIS DO DEPLOY: mudanças em dags/utils/ — restart do worker. A guarda
-- de frescor (utils/frescor_modulo.py) acusa no ciclo se o worker estiver
-- servindo código antigo.
