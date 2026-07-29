-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 064 — Supervisão DataStage: estrutura de jobs filhos
--
-- PROBLEMA QUE RESOLVE (caso real de produção): uma sequence monitorada
-- termina com status "Finished OK" mesmo tendo um job filho ABORTADO. O
-- DataStage não propaga a falha do filho para o pai, então o acompanhamento
-- diário dá o dia como bom e o abort passa despercebido.
--
--   (A) etl_ds_supervisao_estrutura → a lista de jobs que rodam ABAIXO do job
--       supervisionado, APRENDIDA das execuções que terminaram bem. Guarda em
--       quantas dessas execuções cada filho apareceu: job condicional (que só
--       roda em alguns dias) não vira falso "faltou job".
--
--   (B) etl_ds_supervisao_run_filho → o resultado de CADA filho em CADA
--       execução observada. É o detalhe que o painel mostra e a prova de onde
--       veio o veredito.
--
--   (C) Dois tipos de evento novos:
--         SUCESSO_FALSO  → a sequence disse OK, mas um filho abortou.
--         FILHO_AUSENTE  → um job que sempre roda não apareceu na execução.
--
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── (A) Estrutura aprendida ─────────────────────────────────────────────────
IF OBJECT_ID('dbo.etl_ds_supervisao_estrutura', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_supervisao_estrutura (
        supervisao_id        INT          NOT NULL,
        job_filho            VARCHAR(255) NOT NULL,
        -- Em quantas execuções BEM-SUCEDIDAS este filho apareceu. A razão
        -- entre isto e o total de execuções aprendidas é a "frequência": só
        -- cobra ausência de quem aparece quase sempre.
        execucoes_com_sucesso INT         NOT NULL DEFAULT 0,
        primeira_vez         DATETIME     NOT NULL DEFAULT GETDATE(),
        ultima_vez           DATETIME     NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_ds_supervisao_estrutura PRIMARY KEY (supervisao_id, job_filho),
        CONSTRAINT FK_ds_superv_estrutura_job FOREIGN KEY (supervisao_id)
            REFERENCES dbo.etl_ds_supervisao_job (id) ON DELETE CASCADE
    );
    PRINT '[OK] Tabela etl_ds_supervisao_estrutura criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_estrutura ja existe';
GO

-- Total de execuções bem-sucedidas já aprendidas, por job supervisionado.
-- Fica no cadastro porque é o denominador da frequência.
IF COL_LENGTH('dbo.etl_ds_supervisao_job', 'execucoes_aprendidas') IS NULL
BEGIN
    ALTER TABLE dbo.etl_ds_supervisao_job
        ADD execucoes_aprendidas INT NOT NULL CONSTRAINT DF_ds_superv_aprendidas DEFAULT 0;
    PRINT '[OK] etl_ds_supervisao_job.execucoes_aprendidas criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_job.execucoes_aprendidas ja existe';
GO

-- Liga/desliga a análise de dependência por job (fica ligada por padrão: é o
-- problema que motivou a feature).
IF COL_LENGTH('dbo.etl_ds_supervisao_job', 'alerta_sucesso_falso') IS NULL
BEGIN
    ALTER TABLE dbo.etl_ds_supervisao_job
        ADD alerta_sucesso_falso BIT NOT NULL CONSTRAINT DF_ds_superv_sucesso_falso DEFAULT 1,
            alerta_filho_ausente BIT NOT NULL CONSTRAINT DF_ds_superv_filho_ausente DEFAULT 1;
    PRINT '[OK] flags de analise de dependencia criadas';
END
ELSE
    PRINT '[--] flags de analise de dependencia ja existem';
GO

-- Marca de que este run já foi contabilizado no aprendizado da estrutura.
-- Sem ela, cada ciclo de 15 min recontaria o mesmo run bem-sucedido e a
-- frequência dos filhos ficaria inflada em poucas horas.
IF COL_LENGTH('dbo.etl_ds_supervisao_run', 'aprendido') IS NULL
BEGIN
    ALTER TABLE dbo.etl_ds_supervisao_run
        ADD aprendido BIT NOT NULL CONSTRAINT DF_ds_superv_run_aprendido DEFAULT 0;
    PRINT '[OK] etl_ds_supervisao_run.aprendido criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_run.aprendido ja existe';
GO

-- ── (B) Resultado de cada filho em cada execução ────────────────────────────
IF OBJECT_ID('dbo.etl_ds_supervisao_run_filho', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_ds_supervisao_run_filho (
        supervisao_id INT          NOT NULL,
        run_inicio    DATETIME     NOT NULL,   -- mesma chave natural de _run
        job_filho     VARCHAR(255) NOT NULL,
        -- Código cru do DataStage: 1 ok, 2 avisos, 3 ABORTADO, 96 crash,
        -- 97 parado, 13 validação falhou, -1 disparado sem status no log.
        -- Guardamos TODOS; o que vira alerta é decidido no código, não aqui.
        status_code   INT          NOT NULL,
        data_ref      DATE         NOT NULL,
        coletado_em   DATETIME     NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_etl_ds_supervisao_run_filho
            PRIMARY KEY (supervisao_id, run_inicio, job_filho),
        CONSTRAINT FK_ds_superv_run_filho_job FOREIGN KEY (supervisao_id)
            REFERENCES dbo.etl_ds_supervisao_job (id)
    );
    CREATE NONCLUSTERED INDEX ix_ds_superv_run_filho_data
        ON dbo.etl_ds_supervisao_run_filho (data_ref, supervisao_id);
    PRINT '[OK] Tabela etl_ds_supervisao_run_filho criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_run_filho ja existe';
GO

-- ── (C) Tipos de evento novos ───────────────────────────────────────────────
-- O CHECK é recriado porque a lista de tipos cresceu. As constraints foram
-- nomeadas nas migrations 062/063 justamente para poderem ser localizadas aqui
-- sem depender de nome gerado pelo servidor.
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_ds_superv_evento_tipo')
BEGIN
    ALTER TABLE dbo.etl_ds_supervisao_evento DROP CONSTRAINT CK_ds_superv_evento_tipo;
    PRINT '[OK] CHECK antigo de tipo de evento removido';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_ds_superv_evento_tipo')
BEGIN
    ALTER TABLE dbo.etl_ds_supervisao_evento ADD CONSTRAINT CK_ds_superv_evento_tipo
        CHECK (tipo IN ('ABORTOU', 'NAO_EXECUTOU', 'ATRASO', 'ESTRUTURA',
                        'SITUACAO_INICIAL', 'SUCESSO_FALSO', 'FILHO_AUSENTE'));
    PRINT '[OK] CHECK de tipo de evento recriado com SUCESSO_FALSO e FILHO_AUSENTE';
END
GO

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_ds_superv_msg_tipo')
BEGIN
    ALTER TABLE dbo.etl_ds_supervisao_mensagem DROP CONSTRAINT CK_ds_superv_msg_tipo;
    PRINT '[OK] CHECK antigo de tipo de mensagem removido';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_ds_superv_msg_tipo')
BEGIN
    ALTER TABLE dbo.etl_ds_supervisao_mensagem ADD CONSTRAINT CK_ds_superv_msg_tipo
        CHECK (tipo IN ('ABORTOU', 'NAO_EXECUTOU', 'ATRASO', 'ESTRUTURA',
                        'SITUACAO_INICIAL', 'SUCESSO_FALSO', 'FILHO_AUSENTE'));
    PRINT '[OK] CHECK de tipo de mensagem recriado';
END
GO
