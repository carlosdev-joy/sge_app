-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 063 — Supervisão DataStage: mensagem por tipo de alerta
--
-- Ajustes pedidos após o uso da tela de cadastro:
--
--   (A) etl_ds_supervisao_mensagem → uma mensagem para CADA tipo de alerta.
--       Um job liga até quatro alertas diferentes (abortou, não executou,
--       atraso, falha de estrutura) e uma única mensagem fixa não consegue
--       explicar os quatro casos. Cada tipo passa a ter texto próprio, com
--       variáveis do contexto ({janela_inicio}, {tolerancia}, {inicio}…).
--
--   (B) descricao passa a ser OBRIGATÓRIA — é o rótulo que identifica o job
--       nos alertas e no painel; vazio deixava o card sem contexto.
--
--   (C) template_id sai: a mensagem por tipo substitui integralmente o
--       template único do catálogo, que nunca chegou a ser usado no envio.
--
-- É CONFIGURAÇÃO, não histórico: ON DELETE CASCADE nas mensagens, para o
-- cadastro sem histórico continuar podendo ser apagado de fato (regra da F1).
--
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── (A) Mensagem por tipo de alerta ─────────────────────────────────────────
IF OBJECT_ID('dbo.etl_ds_supervisao_mensagem', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_supervisao_mensagem (
        supervisao_id INT            NOT NULL,
        tipo          VARCHAR(20)    NOT NULL,
        mensagem      NVARCHAR(2000) NOT NULL,
        updated_at    DATETIME       NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_ds_supervisao_mensagem PRIMARY KEY (supervisao_id, tipo),
        CONSTRAINT FK_ds_superv_msg_job FOREIGN KEY (supervisao_id)
            REFERENCES dbo.etl_ds_supervisao_job (id) ON DELETE CASCADE,
        CONSTRAINT CK_ds_superv_msg_tipo CHECK (tipo IN
            ('ABORTOU', 'NAO_EXECUTOU', 'ATRASO', 'ESTRUTURA', 'SITUACAO_INICIAL'))
    );
    PRINT '[OK] Tabela etl_ds_supervisao_mensagem criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_mensagem ja existe';
GO

-- ── (A2) Texto já renderizado no evento ─────────────────────────────────────
-- A mensagem é montada na DETECÇÃO, quando o contexto do dia (runs, horários,
-- situação) está em mãos, e guardada pronta no evento. O envio (F4) só entrega
-- o que está aqui — e fica auditável o que foi (ou será) mandado ao canal.
IF COL_LENGTH('dbo.etl_ds_supervisao_evento', 'mensagem') IS NULL
BEGIN
    ALTER TABLE dbo.etl_ds_supervisao_evento ADD mensagem NVARCHAR(2000) NULL;
    PRINT '[OK] etl_ds_supervisao_evento.mensagem criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_evento.mensagem ja existe';
GO

-- ── (B) Descrição obrigatória ───────────────────────────────────────────────
-- Backfill ANTES do ALTER: cadastro existente sem descrição recebe o próprio
-- identificador do job, senão o ALTER falha com linhas nulas.
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_ds_supervisao_job'
             AND COLUMN_NAME = 'descricao' AND IS_NULLABLE = 'YES')
BEGIN
    UPDATE dbo.etl_ds_supervisao_job
       SET descricao = project + '.' + job_name
     WHERE descricao IS NULL OR LTRIM(RTRIM(descricao)) = '';

    ALTER TABLE dbo.etl_ds_supervisao_job ALTER COLUMN descricao VARCHAR(400) NOT NULL;
    PRINT '[OK] etl_ds_supervisao_job.descricao agora e NOT NULL';
END
ELSE
    PRINT '[--] etl_ds_supervisao_job.descricao ja e obrigatoria';
GO

-- ── (C) template_id sai ─────────────────────────────────────────────────────
-- A mensagem por tipo cobre o caso de uso; manter a coluna deixaria um vínculo
-- morto com etl_msg_template. O canal (grupo_id) continua — ele diz PARA ONDE
-- enviar, o que a mensagem não substitui.
IF COL_LENGTH('dbo.etl_ds_supervisao_job', 'template_id') IS NOT NULL
BEGIN
    ALTER TABLE dbo.etl_ds_supervisao_job DROP COLUMN template_id;
    PRINT '[OK] etl_ds_supervisao_job.template_id removida';
END
ELSE
    PRINT '[--] etl_ds_supervisao_job.template_id ja removida';
GO
