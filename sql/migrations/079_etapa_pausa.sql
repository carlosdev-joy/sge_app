-- ============================================================================
-- Migration 079 — Etapa em espera: a tabela de pausas de runtime
--                 (F5 de docs/spec-operacao-nivel-etapa.md, §5 Bloco C,
--                  decisão 3 do §7: "RUNTIME primeiro" — C2)
--
-- ─────────────────────────────────────────────────────────────────────────────
-- O QUE ESTA TABELA É
-- ─────────────────────────────────────────────────────────────────────────────
-- O ESTADO da pausa — e só ele. O preâmbulo da spec é a regra que governa esta
-- fase inteira: "a DAG é a planta, não o estado. Pausar, liberar e reexecutar
-- são estado em tabela — nenhum deles republica DAG."
--
-- O portão físico já existe: toda etapa tem um `log_start_<job>` imediatamente
-- antes dela (dags/etl_dag_factory.py, `_task_block`). A F5 faz esse log_start
-- consultar ESTA tabela e, havendo pausa PENDENTE para (execução, etapa),
-- aguardar em `reschedule` até a liberação. Sem linha aqui, o log_start segue
-- exatamente o caminho de sempre.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- A CHAVE: (pipeline, execution_id, job_name)
-- ─────────────────────────────────────────────────────────────────────────────
-- `execution_id` é o **ts_nodash** — a chave de execução de `etl_job_execution`
-- e o que o `log_start` tem na mão (`context['ts_nodash']`). NÃO é o run_id do
-- Airflow (a armadilha central do §2 da spec: as duas tabelas de execução usam
-- chaves diferentes). O `run_id` viaja junto na linha, mas como INFORMAÇÃO
-- para a tela e a auditoria, nunca como chave de leitura do portão: o portão
-- roda dentro da task e o barato dele é justamente ler por ts_nodash.
--
-- Largura VARCHAR(50) = a MESMA de `etl_job_execution.execution_id` (o
-- ts_nodash tem 15 chars; a 072 ampliou para 250 a coluna de
-- `etl_pipeline_execucao`, que guarda run_id — outro campo, outra largura).
--
-- ─────────────────────────────────────────────────────────────────────────────
-- OS ESTADOS
-- ─────────────────────────────────────────────────────────────────────────────
--   PENDENTE   — pedida; o portão segura a etapa quando ela chegar
--   LIBERADA   — o operador liberou (quem e quando ficam gravados)
--   CANCELADA  — o operador desistiu da execução; o portão FALHA a etapa
--   EXPIRADA   — o teto de espera estourou; o portão alerta e FALHA a etapa
--
-- ⚠️ CANCELADA e EXPIRADA fazem a etapa FALHAR, nunca pular. Pular deixaria o
-- DagRun verde com o pipeline pela metade — a classe de defeito que este
-- projeto já pagou caro (o "sucesso falso" da supervisão DataStage e o
-- ALL_DONE que escondia falha na spec do nó Aguarde). Vermelho com motivo é
-- informação; verde mentiroso é dano.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- POR QUE O ÚNICO É FILTRADO (WHERE estado = 'PENDENTE')
-- ─────────────────────────────────────────────────────────────────────────────
-- Duas pausas PENDENTES para a mesma (execução, etapa) seriam ambiguidade no
-- portão. Mas a MESMA etapa da MESMA execução pode ser pausada de novo depois
-- de um rerun (a F4 mantém o ts_nodash), e o histórico das pausas anteriores
-- não pode ser sobrescrito — ele é a auditoria. Índice único FILTRADO resolve
-- os dois: no máximo uma pendente, quantas resolvidas forem precisas.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- O TETO VIAJA NA LINHA
-- ─────────────────────────────────────────────────────────────────────────────
-- `teto_minutos` é gravado na PRÓPRIA pausa (default vindo de
-- `etl_app_config.espera_teto_minutos`). Assim o que a tela mostra é o que o
-- portão obedece — um teto só global mudaria por baixo de uma espera em curso
-- e a tela mentiria. A Variable `ESPERA_TETO_MINUTOS` do Airflow continua
-- existindo como alavanca de infra para linhas sem teto (degradação).
--
-- ─────────────────────────────────────────────────────────────────────────────
-- ⚠️ ESTA MIGRATION SOZINHA NÃO LIGA O PORTÃO
-- ─────────────────────────────────────────────────────────────────────────────
-- O portão vive no `log_start_<job>` das DAGs GERADAS. Depois do deploy de
-- `dags/` (que traz `utils/espera.py` e `utils/job_operators.LogStartOperator`),
-- é preciso **regerar as DAGs** para o portão passar a existir nelas:
--
--     etl_dag_factory  com conf {"force_all": true}
--
-- Antes de regerar, a consulta de dimensionamento de sempre (quantos pipelines
-- serão reescritos) — o mesmo cuidado do deploy da spec de dependências.
-- Pipeline NÃO regerado continua com o log_start antigo: sem portão, e uma
-- pausa pedida para ele fica PENDENTE sem nunca segurar nada. A tela mostra a
-- pausa como "marcada" e o processo passa direto.
--
-- Idempotente: roda 2x sem erro (etapa 6c do deploy.sh). Conferência por
-- SELECT — sql/migrate.py descarta PRINT (D40).
-- ============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 1) A tabela
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.etl_etapa_pausa', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_etapa_pausa (
        id                 BIGINT IDENTITY(1,1) NOT NULL
                           CONSTRAINT PK_etl_etapa_pausa PRIMARY KEY,
        -- a chave do portão
        pipeline_name      NVARCHAR(200) NOT NULL,
        execution_id       VARCHAR(50)   NOT NULL,   -- ts_nodash
        job_name           NVARCHAR(200) NOT NULL,
        -- contexto (informação da tela e da auditoria; NUNCA chave de leitura)
        task_id            NVARCHAR(200) NULL,
        run_id             VARCHAR(250)  NULL,
        data_referencia    DATE          NULL,       -- ODATE; alvo do evento de teto
        -- estado
        estado             VARCHAR(20)   NOT NULL
                           CONSTRAINT DF_etl_etapa_pausa_estado DEFAULT ('PENDENTE'),
        motivo             VARCHAR(1000) NULL,       -- por que pausou (operador)
        observacao         VARCHAR(1000) NULL,       -- por que liberou/cancelou
        teto_minutos       INT           NULL,
        -- quem pediu
        solicitado_por     NVARCHAR(200) NOT NULL,
        solicitado_em      DATETIME2     NOT NULL
                           CONSTRAINT DF_etl_etapa_pausa_solic DEFAULT (GETDATE()),
        -- o que o portão registrou
        aguardando_desde   DATETIME2     NULL,       -- 1ª chegada da etapa ao portão
        ultima_verificacao DATETIME2     NULL,
        verificacoes       INT           NOT NULL
                           CONSTRAINT DF_etl_etapa_pausa_verif DEFAULT (0),
        alertado_em        DATETIME2     NULL,       -- carimbo do alerta de teto
        -- quem resolveu
        resolvido_por      NVARCHAR(200) NULL,
        resolvido_em       DATETIME2     NULL
    );
    PRINT '[OK] Tabela etl_etapa_pausa criada';
END
ELSE
    PRINT '[--] etl_etapa_pausa ja existe';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 2) Único FILTRADO: no máximo UMA pausa pendente por (execução, etapa).
--    É também o índice que o portão usa (seek por pipeline+execution+job com
--    estado='PENDENTE' — exatamente a consulta que roda em TODO log_start).
-- ─────────────────────────────────────────────────────────────────────────────
-- ⚠️ ÍNDICE FILTRADO EXIGE AS DUAS OPÇÕES ABAIXO — descoberto na prova viva
-- (2026-08-03): a criação falhou com "Msg 1934 ... 'QUOTED_IDENTIFIER'" porque
-- o sqlcmd conecta com QUOTED_IDENTIFIER OFF (só liga com -I). Elas valem para
-- a SESSÃO e o SET tem de estar no MESMO batch do CREATE.
--
-- E não é só a criação: o SQL Server recusa INSERT/UPDATE numa tabela com
-- índice filtrado quando a sessão está com essas opções OFF. Os dois clientes
-- que escrevem aqui foram MEDIDOS neste dev antes de a fase seguir:
--   • pymssql (portão, dags/)  → QUOTED_IDENTIFIER=1, ANSI_NULLS=1
--   • pyodbc  (API, api/)      → QUOTED_IDENTIFIER=1, ANSI_NULLS=1
-- Ambos ON por padrão do driver. Quem rodar DML nesta tabela pelo sqlcmd
-- precisa de `-I` (ou destes SET).
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_etapa_pausa_pendente'
               AND object_id = OBJECT_ID('dbo.etl_etapa_pausa'))
BEGIN
    CREATE UNIQUE INDEX ux_etapa_pausa_pendente ON dbo.etl_etapa_pausa
        (pipeline_name, execution_id, job_name)
        WHERE estado = 'PENDENTE';
    PRINT '[OK] indice ux_etapa_pausa_pendente criado';
END
ELSE
    PRINT '[--] indice ux_etapa_pausa_pendente ja existe';
GO

-- Leitura da TELA: todas as pausas de uma execução (inclusive as resolvidas —
-- a tela mostra o histórico do que foi liberado e por quem).
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_etapa_pausa_execucao'
               AND object_id = OBJECT_ID('dbo.etl_etapa_pausa'))
BEGIN
    CREATE INDEX ix_etapa_pausa_execucao ON dbo.etl_etapa_pausa
        (pipeline_name, execution_id)
        INCLUDE (job_name, estado, aguardando_desde, solicitado_por,
                 solicitado_em, resolvido_por, resolvido_em);
    PRINT '[OK] indice ix_etapa_pausa_execucao criado';
END
ELSE
    PRINT '[--] indice ix_etapa_pausa_execucao ja existe';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 3) Teto de espera padrão (minutos) em etl_app_config — o MESMO lugar de
--    `dependencia_hora_virada` (067). A API lê daqui ao criar a pausa e grava
--    o valor NA LINHA; a tela mostra o que está na linha.
--
--    240 min (4h) é generoso de propósito: pausa é gesto humano e o teto
--    existe contra ESQUECIMENTO, não contra demora. Estourar o teto não é
--    "quase lá": é "ninguém voltou".
-- ─────────────────────────────────────────────────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM dbo.etl_app_config WHERE config_key = 'espera_teto_minutos')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('espera_teto_minutos', '240',
            'Teto padrao (minutos) de espera de uma etapa pausada antes de alertar e falhar (F5)');
    PRINT '[OK] config espera_teto_minutos = 240 criada';
END
ELSE
    PRINT '[--] config espera_teto_minutos ja existe';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 4) Conferência por SELECT (sql/migrate.py descarta PRINT — D40).
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    CASE WHEN OBJECT_ID('dbo.etl_etapa_pausa', 'U') IS NOT NULL
         THEN 'OK' ELSE 'FALTA' END                          AS tabela_pausa,
    CASE WHEN EXISTS (SELECT 1 FROM sys.indexes
                      WHERE name = 'ux_etapa_pausa_pendente'
                        AND object_id = OBJECT_ID('dbo.etl_etapa_pausa'))
         THEN 'OK' ELSE 'FALTA' END                          AS ux_pendente,
    CASE WHEN EXISTS (SELECT 1 FROM sys.indexes
                      WHERE name = 'ix_etapa_pausa_execucao'
                        AND object_id = OBJECT_ID('dbo.etl_etapa_pausa'))
         THEN 'OK' ELSE 'FALTA' END                          AS ix_execucao,
    (SELECT COUNT(*) FROM dbo.etl_app_config
      WHERE config_key = 'espera_teto_minutos')              AS cfg_teto,
    (SELECT COUNT(*) FROM dbo.etl_etapa_pausa
      WHERE estado = 'PENDENTE')                             AS pausas_pendentes;
GO
