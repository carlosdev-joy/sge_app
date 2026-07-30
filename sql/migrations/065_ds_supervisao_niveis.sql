-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 065 — Supervisão DataStage: níveis abaixo do job supervisionado
--
-- PROBLEMA QUE RESOLVE (caso real, observado no painel em 2026-07-29):
--   BI_PRESTAMISTA.SeqSsdPrs_CargaDiaria .......... "Concluído"  (supervisionado)
--     └── SeqSsdPrs_Dim ........................... "concluído"  (nível 1, já lido)
--           └── SeqSsdPrs_DimSocios ............... "Concluído"  (nível 2, INVISÍVEL)
--                 └── SsdPrs_DimSocios_01_ext ..... ABORTED      (nível 3, INVISÍVEL)
--
--   O "sucesso falso" é RECURSIVO: cada sequence intermediária reporta OK e
--   esconde o nível de baixo. Lendo só os filhos diretos, um abort a três
--   níveis de profundidade nunca aparece — e era exatamente o que acontecia.
--
--   Note que NENHUM job do nível 1 aparece falhado: descer apenas pela cadeia
--   de aborts (como faz o "Causa-raiz" do console) não encontraria nada. A
--   varredura tem de ser em LARGURA, em todos os filhos.
--
--   (A) nivel + job_pai em etl_ds_supervisao_run_filho → guarda a árvore, não
--       mais uma lista rasa, e permite mostrar a hierarquia no painel.
--   (B) expandido em etl_ds_supervisao_run → marca que a varredura profunda já
--       foi feita para aquele run. É o que evita repetir dezenas de chamadas
--       SSH a cada 15 min sobre um run que não muda mais.
--
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── (A) Hierarquia dos jobs abaixo do supervisionado ────────────────────────
IF COL_LENGTH('dbo.etl_ds_supervisao_run_filho', 'nivel') IS NULL
BEGIN
    -- Default 1 é o valor correto para o que já foi coletado antes desta
    -- migration: só o primeiro nível era lido.
    ALTER TABLE dbo.etl_ds_supervisao_run_filho
        ADD nivel INT NOT NULL CONSTRAINT DF_ds_superv_filho_nivel DEFAULT 1;
    PRINT '[OK] etl_ds_supervisao_run_filho.nivel criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_run_filho.nivel ja existe';
GO

IF COL_LENGTH('dbo.etl_ds_supervisao_run_filho', 'job_pai') IS NULL
BEGIN
    -- Quem disparou este job. NULL no histórico anterior à migration: naquele
    -- momento o pai era sempre o próprio job supervisionado.
    ALTER TABLE dbo.etl_ds_supervisao_run_filho ADD job_pai VARCHAR(255) NULL;
    PRINT '[OK] etl_ds_supervisao_run_filho.job_pai criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_run_filho.job_pai ja existe';
GO

-- Leitura do painel: a árvore de um run, na ordem em que ela é montada.
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'ix_ds_superv_filho_arvore'
                 AND object_id = OBJECT_ID('dbo.etl_ds_supervisao_run_filho'))
BEGIN
    CREATE NONCLUSTERED INDEX ix_ds_superv_filho_arvore
        ON dbo.etl_ds_supervisao_run_filho (supervisao_id, run_inicio, nivel);
    PRINT '[OK] indice ix_ds_superv_filho_arvore criado';
END
ELSE
    PRINT '[--] indice ix_ds_superv_filho_arvore ja existe';
GO

-- ── (B) Controle da varredura profunda ──────────────────────────────────────
IF COL_LENGTH('dbo.etl_ds_supervisao_run', 'expandido') IS NULL
BEGIN
    -- Fica 0 para os runs já coletados: eles serão expandidos no próximo ciclo
    -- que tiver orçamento, sem precisar de intervenção manual.
    ALTER TABLE dbo.etl_ds_supervisao_run
        ADD expandido BIT NOT NULL CONSTRAINT DF_ds_superv_run_expandido DEFAULT 0;
    PRINT '[OK] etl_ds_supervisao_run.expandido criada';
END
ELSE
    PRINT '[--] etl_ds_supervisao_run.expandido ja existe';
GO

-- A estrutura aprendida com apenas um nível está incompleta por construção:
-- zerar o aprendizado faz a próxima execução bem-sucedida reaprender a árvore
-- inteira. Sem isso, todo job de nível 2+ seria reportado como FILHO_AUSENTE
-- ao entrar na lista — ausente de uma estrutura que nunca o continha.
IF EXISTS (SELECT 1 FROM sys.columns
           WHERE object_id = OBJECT_ID('dbo.etl_ds_supervisao_run') AND name = 'expandido')
   AND EXISTS (SELECT 1 FROM dbo.etl_ds_supervisao_estrutura)
BEGIN
    DELETE FROM dbo.etl_ds_supervisao_estrutura;
    UPDATE dbo.etl_ds_supervisao_job SET execucoes_aprendidas = 0 WHERE execucoes_aprendidas > 0;
    UPDATE dbo.etl_ds_supervisao_run SET aprendido = 0 WHERE aprendido = 1;
    PRINT '[OK] aprendizado zerado — a arvore completa sera reaprendida';
END
ELSE
    PRINT '[--] nada a rezerar no aprendizado';
GO
