-- =============================================================================
-- forcar-reset-ciclo-malha.sql — Força o encerramento de TODOS os ciclos dos
-- membros de uma malha e deixa o terreno pronto para uma corrida de VALIDAÇÃO
-- partindo do zero, com todos na mesma data de referência.
--
-- Quando usar: o disparo da malha recusa com "Ciclo em andamento" + "Data de
-- referência diferente" e o Equalizar da tela recusa com "já existe ciclo
-- deste pipeline na data da malha — recarimbar criaria duas".
--
-- O que ele faz (na ordem, numa transação só):
--   1. Encerra (status=FALHA, fim, motivo) os ciclos EXECUTANDO/AGUARDANDO
--      dos membros — em QUALQUER data (é a trava 1 do disparo).
--   2. Recarimba para @alvo os ciclos dos membros com data DIVERGENTE que a
--      trava 2 enxerga: data posterior ao alvo, ou data anterior com `inicio`
--      dentro do ciclo corrente (mesmo recorte de _datas_divergentes, que não
--      olha status nem substituida_em). Colisão no índice único ux_pipe_exec
--      (pipeline+data+execution_id, onde NULL colide com NULL) é resolvida
--      sufixando o execution_id da linha movida com '_forca_<id>' — linha com
--      execution_id NULL não tem DagRun apontando para ela, e a linha será
--      aposentada no passo seguinte de toda forma.
--   3. Aposenta (substituida_em) TODOS os ciclos vivos dos membros na data
--      @alvo. É isso que permite o push criar ciclo NOVO para cada dependente
--      na corrida de validação — ciclo aposentado não conta como "já há ciclo
--      na data" (contrato da migration 078, mesmo NOT EXISTS do claim).
--   4. Fecha como CANCELADA as corridas ABERTAS da malha (etl_malha_execucao).
--   5. Deixa o rastro em etl_dependencia_evento (DATA_EQUALIZADA) — com guarda
--      NOT EXISTS: o Equalizar oficial grava o mesmo shape e o índice único
--      ux_dep_evento_corrida derrubaria a transação inteira (o rastro por
--      linha já fica no `motivo` de cada ciclo tocado). Só roda com @limpar=0.
--   6. Com @limpar = 1, REMOVE de vez o rastro do ciclo dos membros — para a
--      corrida de validação partir de terreno raso, sem FALHA de ontem nos
--      painéis nem aviso "já rodou (N)" nas raízes:
--        • execuções dos membros com data >= @alvo OU inicio >= @corte;
--        • eventos (etl_dependencia_evento) dos membros com data >= @alvo;
--        • corridas da malha (etl_malha_execucao) com data >= @alvo — o
--          snapshot etl_malha_execucao_membro cai junto (FK ON DELETE CASCADE);
--        • telemetria POR JOB (etl_job_execution) dos membros com
--          start_time >= meia-noite de @alvo — é ela que alimenta a tela
--          Execuções, o dashboard e a Gestão de Falhas; sem este passo o
--          "job com falha de ontem" continuaria aparecendo lá. O filtro é
--          pela coluna `pipeline` da própria execução (job compartilhado
--          entre pipelines não perde a telemetria dos vizinhos).
--      Datas ANTERIORES a @alvo com inicio antigo são história legítima e
--      ficam intactas nos dois modos. ⚠️ Logo: FALHA com ODATE anterior a
--      @alvo só some se @alvo apontar para AQUELA data — para "limpar desde
--      ontem", @alvo = a data de ontem (as travas e o recarimbo puxam o
--      resto do ciclo para ela).
--      ⚠️ Apagar eventos apaga também a MEMÓRIA DE DEDUP da guardiã: se uma
--      condição de alerta ainda for verdadeira na data (ex.: hora-limite já
--      estourada antes do disparo), o próximo ciclo de 5 min pode REENVIAR
--      um card do Teams já enviado antes. Esperado; observe 1–2 ciclos da
--      guardiã antes de disparar a validação.
--
-- O script é re-executável: rodar duas vezes não estoura índice nem duplica
-- rastro — a segunda passada encontra tudo tratado e afeta 0 linhas.
--
-- ⚠️ ANTES de rodar: pare no Airflow os DagRuns em voo dos membros (a tela de
--    Execuções ou a UI do Airflow). Encerrar no banco NÃO mata processo: um pai
--    em voo que concluir DEPOIS da força faz push dos filhos na data VELHA e
--    suja o ciclo de novo.
-- ⚠️ DEPOIS de rodar e ANTES de disparar: Republicar pipelines da malha. Ciclo
--    carimbado fora da data por 'agenda' = DAG antiga ainda disparando por
--    cron — sem republicar, a próxima virada recria a divergência.
-- ⚠️ RELÓGIO: o @corte usa SYSDATETIME() (relógio do BANCO); a trava da API
--    calcula no relógio dela e compensa o delta. Se o banco estiver HORAS À
--    FRENTE da API, evite rodar no corredor da hora da virada (os dois lados
--    do corte podem divergir); confira SELECT SYSDATETIME() contra o relógio
--    do container da API antes de rodar em produção.
-- =============================================================================

SET NOCOUNT ON;
SET XACT_ABORT ON;
-- etl_pipeline_execucao tem índices FILTRADOS (085): escrever nela exige estas
-- opções ligadas — sqlcmd sem -I roda com QUOTED_IDENTIFIER OFF e cai no 1934.
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;

DECLARE @malha NVARCHAR(200) = N'<NOME_DA_MALHA>';   -- << AJUSTE AQUI
DECLARE @alvo  DATE          = '2026-08-10';         -- data única da corrida
DECLARE @quem  NVARCHAR(100) = N'forca-manual-validacao';
-- 0 = SÓ o dry-run (nenhuma escrita). 1 = executa a força de verdade.
-- Rode primeiro com 0, confira as listas, depois rode de novo com 1.
DECLARE @executar BIT = 0;                           -- << AJUSTE AQUI
-- 0 = preserva histórico (encerra/recarimba/aposenta — os painéis seguem
--     mostrando as linhas, com motivo). 1 = APAGA execuções, eventos e
--     corridas do ciclo (passo 6) — execução limpa, sem FALHA de ontem nas
--     telas nem "já rodou (N)" nas raízes. Vale também para o dry-run
--     (mostra as listas do que seria apagado).
DECLARE @limpar BIT = 0;                             -- << AJUSTE AQUI

-- O corte do ciclo corrente — a MESMA régua da trava de data divergente
-- (_inicio_do_ciclo): virada global 'dependencia_hora_virada' da
-- etl_app_config (fallback 00:00), no relógio do BANCO (SYSDATETIME).
-- Só os formatos que o parse_virada do produto aceita ('HH:MM' e 'HH:MM:SS');
-- TRY_CAST cru engoliria fração de segundo que o produto REJEITA (cai p/
-- 00:00) e o corte divergiria da trava em silêncio.
DECLARE @virada_raw NVARCHAR(50) = (SELECT TOP 1 LTRIM(RTRIM(config_value))
    FROM dbo.etl_app_config
    WHERE config_key = 'dependencia_hora_virada');
DECLARE @virada TIME = ISNULL(CASE WHEN LEN(@virada_raw) IN (5, 8)
    THEN TRY_CAST(@virada_raw AS TIME) END, '00:00');
DECLARE @corte DATETIME2 =
    DATEADD(DAY, DATEDIFF(DAY, 0, SYSDATETIME()), CAST(@virada AS DATETIME));
IF SYSDATETIME() < @corte SET @corte = DATEADD(DAY, -1, @corte);
PRINT CONCAT('corte do ciclo corrente (virada ', CONVERT(VARCHAR(8), @virada, 108),
             '): ', CONVERT(VARCHAR(19), @corte, 120));

-- ─── DRY-RUN: o que será tocado ──────────────────────────────────────────────
PRINT '== Ciclos em aberto dos membros (serão encerrados) ==';
SELECT e.id, e.pipeline_name, e.data_referencia, e.status, e.inicio, e.disparado_por
FROM dbo.etl_pipeline_execucao e
JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
WHERE mp.malha_name = @malha
  AND e.status IN ('EXECUTANDO','AGUARDANDO_DEPENDENCIA')
  AND e.substituida_em IS NULL;

PRINT '== Ciclos divergentes da trava 2 (serão recarimbados p/ @alvo) ==';
SELECT e.id, e.pipeline_name, e.data_referencia, e.status, e.inicio, e.disparado_por
FROM dbo.etl_pipeline_execucao e
JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
WHERE mp.malha_name = @malha
  AND e.data_referencia <> @alvo
  AND (e.data_referencia > @alvo OR e.inicio >= @corte);

PRINT '== Dessas, as que terão execution_id sufixado (colisão no ux_pipe_exec) ==';
SELECT e.id, e.pipeline_name, e.data_referencia, e.execution_id
FROM dbo.etl_pipeline_execucao e
JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
WHERE mp.malha_name = @malha
  AND e.data_referencia <> @alvo
  AND (e.data_referencia > @alvo OR e.inicio >= @corte)
  AND (EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao x
               WHERE x.pipeline_name = e.pipeline_name
                 AND x.data_referencia = @alvo
                 AND ISNULL(x.execution_id,'') = ISNULL(e.execution_id,''))
       OR EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e2
                  WHERE e2.pipeline_name = e.pipeline_name
                    AND e2.id < e.id
                    AND e2.data_referencia <> @alvo
                    AND (e2.data_referencia > @alvo OR e2.inicio >= @corte)
                    AND ISNULL(e2.execution_id,'') = ISNULL(e.execution_id,'')));

PRINT '== Ciclos vivos na data @alvo (serão aposentados) ==';
SELECT e.id, e.pipeline_name, e.data_referencia, e.status, e.inicio
FROM dbo.etl_pipeline_execucao e
JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
WHERE mp.malha_name = @malha AND e.data_referencia = @alvo
  AND e.substituida_em IS NULL;

PRINT '== Corridas ABERTAS da malha (serão CANCELADAS) ==';
SELECT id, malha_name, data_referencia, sequencia, status, aberta_em
FROM dbo.etl_malha_execucao
WHERE malha_name = @malha AND fechada_em IS NULL;

IF @limpar = 1
BEGIN
    PRINT '== @limpar=1: execuções que serão APAGADAS (inclui as FALHA de ontem) ==';
    SELECT e.id, e.pipeline_name, e.data_referencia, e.status, e.inicio
    FROM dbo.etl_pipeline_execucao e
    JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
    WHERE mp.malha_name = @malha
      AND (e.data_referencia >= @alvo OR e.inicio >= @corte);

    PRINT '== @limpar=1: eventos que serão APAGADOS ==';
    SELECT ev.id, ev.pipeline_name, ev.data_referencia, ev.tipo
    FROM dbo.etl_dependencia_evento ev
    WHERE ev.pipeline_name IN (SELECT pipeline_name FROM dbo.etl_malha_pipeline
                               WHERE malha_name = @malha)
      AND ev.data_referencia >= @alvo;

    PRINT '== @limpar=1: corridas da malha que serão APAGADAS (snapshot cai junto) ==';
    SELECT id, data_referencia, sequencia, status, aberta_em, fechada_em
    FROM dbo.etl_malha_execucao
    WHERE malha_name = @malha AND data_referencia >= @alvo;

    PRINT '== @limpar=1: telemetria por JOB que será APAGADA (tela Execuções) ==';
    SELECT je.execution_id, je.pipeline, je.job_name, je.status, je.start_time
    FROM dbo.etl_job_execution je
    WHERE je.pipeline IN (SELECT pipeline_name FROM dbo.etl_malha_pipeline
                          WHERE malha_name = @malha)
      AND je.start_time >= CAST(@alvo AS DATETIME);
END

-- =============================================================================
-- A FORÇA. Só roda com @executar = 1 — com 0, o script termina no dry-run.
-- =============================================================================
IF @executar = 0
BEGIN
    PRINT '== @executar = 0: dry-run apenas, NADA foi escrito. ==';
    PRINT '== Confira as listas acima e rode de novo com @executar = 1. ==';
    RETURN;
END

BEGIN TRAN;

-- 1) Encerrar os ciclos em aberto (trava 1: "Ciclo em andamento")
UPDATE e
   SET e.status = 'FALHA',
       e.fim = GETDATE(),
       e.atualizado_em = GETDATE(),
       e.motivo = LEFT(ISNULL(e.motivo + ' | ', '')
                       + 'encerrado a forca para corrida de validacao ('
                       + CAST(@quem AS VARCHAR(100)) + ')', 500)
FROM dbo.etl_pipeline_execucao e
JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
WHERE mp.malha_name = @malha
  AND e.status IN ('EXECUTANDO','AGUARDANDO_DEPENDENCIA')
  AND e.substituida_em IS NULL;
PRINT CONCAT('passo 1 - ciclos encerrados: ', @@ROWCOUNT);

-- 2) Equalizar à força (trava 2: "Data de referência diferente"), no MESMO
--    recorte da trava: data posterior ao alvo, ou anterior com inicio dentro
--    do ciclo corrente. Colisão no ux_pipe_exec (contra linha já em @alvo OU
--    entre duas linhas movidas juntas — o NOT EXISTS clássico não vê a
--    segunda, snapshot pré-UPDATE) é resolvida sufixando o execution_id.
UPDATE e
   SET e.data_referencia = @alvo,
       e.execution_id = CASE WHEN
             EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao x
                     WHERE x.pipeline_name = e.pipeline_name
                       AND x.data_referencia = @alvo
                       AND ISNULL(x.execution_id,'') = ISNULL(e.execution_id,''))
          OR EXISTS (SELECT 1 FROM dbo.etl_pipeline_execucao e2
                     WHERE e2.pipeline_name = e.pipeline_name
                       AND e2.id < e.id
                       AND e2.data_referencia <> @alvo
                       AND (e2.data_referencia > @alvo OR e2.inicio >= @corte)
                       AND ISNULL(e2.execution_id,'') = ISNULL(e.execution_id,''))
          -- trunca o ORIGINAL, nunca o sufixo: LEFT no concat inteiro comeria
          -- o '_forca_<id>' com execution_id longo e a colisão voltaria
          THEN LEFT(ISNULL(e.execution_id,''),
                    250 - LEN(CONCAT('_forca_', CAST(e.id AS VARCHAR(20)))))
               + CONCAT('_forca_', CAST(e.id AS VARCHAR(20)))
          ELSE e.execution_id END,
       e.atualizado_em = GETDATE(),
       e.motivo = LEFT(ISNULL(e.motivo + ' | ', '')
                       + 'data equalizada a forca de '
                       + CONVERT(VARCHAR(10), e.data_referencia, 23)
                       + ' para ' + CONVERT(VARCHAR(10), @alvo, 23)
                       + ' (' + CAST(@quem AS VARCHAR(100)) + ')', 500)
FROM dbo.etl_pipeline_execucao e
JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
WHERE mp.malha_name = @malha
  AND e.data_referencia <> @alvo
  AND (e.data_referencia > @alvo OR e.inicio >= @corte);
PRINT CONCAT('passo 2 - ciclos recarimbados para a data alvo: ', @@ROWCOUNT);

-- 3) Aposentar TODOS os ciclos vivos da data alvo — é o que faz o push aceitar
--    criar ciclo novo por dependente na corrida de validação (contrato 078).
UPDATE e
   SET e.substituida_em = GETDATE(),
       e.atualizado_em = GETDATE(),
       e.motivo = LEFT(ISNULL(e.motivo + ' | ', '')
                       + 'aposentado a forca para corrida de validacao ('
                       + CAST(@quem AS VARCHAR(100)) + ')', 500)
FROM dbo.etl_pipeline_execucao e
JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
WHERE mp.malha_name = @malha
  AND e.data_referencia = @alvo
  AND e.substituida_em IS NULL;
PRINT CONCAT('passo 3 - ciclos aposentados (substituida_em): ', @@ROWCOUNT);

-- 4) Fechar corridas ABERTAS da malha (mesmo shape do fechar_corrida oficial)
UPDATE dbo.etl_malha_execucao
   SET status = 'CANCELADA',
       fechada_em = SYSDATETIME(),
       fechada_por = CONCAT('manual:', @quem),
       motivo = LEFT(ISNULL(motivo + ' | ', '')
                     + 'encerrada a forca para corrida de validacao', 500),
       atualizado_em = SYSDATETIME()
WHERE malha_name = @malha AND fechada_em IS NULL;
PRINT CONCAT('passo 4 - corridas da malha canceladas: ', @@ROWCOUNT);

-- 5) Rastro no painel (mesmo tipo de evento do Equalizar oficial). Guarda
--    NOT EXISTS: ux_dep_evento_corrida é único e o Equalizar oficial pode já
--    ter gravado esse shape na data — sem a guarda, o rastro derrubaria a
--    transação inteira (o oficial se protege com try/except; aqui é SQL puro).
--    A âncora é fixada ANTES da guarda: com o NOT EXISTS dentro do TOP 1, a
--    guarda escolheria "o próximo membro sem evento" e cada re-execução
--    rastejaria um evento novo pela malha, membro a membro.
--    Com @limpar = 1 não roda: o passo 6 apagaria o evento na sequência.
IF @limpar = 0
BEGIN
    INSERT INTO dbo.etl_dependencia_evento (pipeline_name, data_referencia, tipo, detalhe)
    SELECT mp.pipeline_name, @alvo, 'DATA_EQUALIZADA',
           CONCAT('malha ', @malha, ' (', @quem,
                  '): reset a forca — ciclos encerrados, datas equalizadas para ',
                  CONVERT(VARCHAR(10), @alvo, 23), ' e ciclos da data aposentados ',
                  'para corrida de validacao partir do zero')
    FROM dbo.etl_malha_pipeline mp
    WHERE mp.malha_name = @malha
      AND mp.pipeline_name = (SELECT TOP 1 pipeline_name
                              FROM dbo.etl_malha_pipeline
                              WHERE malha_name = @malha
                              ORDER BY pipeline_name)
      AND NOT EXISTS (SELECT 1 FROM dbo.etl_dependencia_evento ev
                      WHERE ev.pipeline_name = mp.pipeline_name
                        AND ev.data_referencia = @alvo
                        AND ev.tipo = 'DATA_EQUALIZADA');
    PRINT CONCAT('passo 5 - evento de rastro gravado: ', @@ROWCOUNT);
END

-- 6) Limpeza (@limpar = 1): apaga o rastro do ciclo — execuções (inclusive as
--    FALHA que o passo 1 acabou de carimbar), eventos e corridas da malha.
--    Ordem: eventos → execuções → corridas (o snapshot de membros cai por
--    cascade). Datas anteriores a @alvo com inicio antigo ficam intactas.
IF @limpar = 1
BEGIN
    DELETE ev
    FROM dbo.etl_dependencia_evento ev
    WHERE ev.pipeline_name IN (SELECT pipeline_name FROM dbo.etl_malha_pipeline
                               WHERE malha_name = @malha)
      AND ev.data_referencia >= @alvo;
    PRINT CONCAT('passo 6a - eventos apagados: ', @@ROWCOUNT);

    DELETE e
    FROM dbo.etl_pipeline_execucao e
    JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
    WHERE mp.malha_name = @malha
      AND (e.data_referencia >= @alvo OR e.inicio >= @corte);
    PRINT CONCAT('passo 6b - execucoes apagadas: ', @@ROWCOUNT);

    DELETE FROM dbo.etl_malha_execucao
    WHERE malha_name = @malha AND data_referencia >= @alvo;
    PRINT CONCAT('passo 6c - corridas da malha apagadas: ', @@ROWCOUNT);

    -- Telemetria por job: é onde a tela Execuções/Gestão de Falhas lê o "job
    -- com falha". Sem FK nem trigger (conferido em sys.foreign_keys); janela
    -- pela meia-noite de @alvo porque job não tem ODATE, só start_time.
    DELETE je
    FROM dbo.etl_job_execution je
    WHERE je.pipeline IN (SELECT pipeline_name FROM dbo.etl_malha_pipeline
                          WHERE malha_name = @malha)
      AND je.start_time >= CAST(@alvo AS DATETIME);
    PRINT CONCAT('passo 6d - telemetria por job apagada: ', @@ROWCOUNT);
END

COMMIT;
PRINT '== COMMIT feito ==';

-- ─── VERIFICAÇÃO: reproduz as travas do disparo — as três têm de dar VAZIO ──
PRINT '== Trava 1 (deve dar vazio): membros com ciclo em aberto ==';
SELECT e.pipeline_name, e.data_referencia, e.status
FROM dbo.etl_pipeline_execucao e
JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
WHERE mp.malha_name = @malha
  AND e.status IN ('EXECUTANDO','AGUARDANDO_DEPENDENCIA')
  AND e.substituida_em IS NULL;

PRINT '== Trava 2 (deve dar vazio): data <> alvo com inicio no ciclo corrente ==';
SELECT e.pipeline_name, e.data_referencia, e.status, e.inicio
FROM dbo.etl_pipeline_execucao e
JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
WHERE mp.malha_name = @malha
  AND e.data_referencia <> @alvo
  AND e.inicio >= @corte;

PRINT '== Corrida aberta (deve dar vazio) ==';
SELECT id, status, aberta_em FROM dbo.etl_malha_execucao
WHERE malha_name = @malha AND fechada_em IS NULL;

PRINT '== Ciclos vivos na data alvo (deve dar vazio — todos aposentados) ==';
SELECT e.pipeline_name, e.status
FROM dbo.etl_pipeline_execucao e
JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
WHERE mp.malha_name = @malha
  AND e.data_referencia = @alvo
  AND e.substituida_em IS NULL;

IF @limpar = 1
BEGIN
    PRINT '== Limpeza (deve dar 0 | 0 | 0 | 0): sobras de execuções, eventos, corridas e jobs ==';
    SELECT
        (SELECT COUNT(*) FROM dbo.etl_pipeline_execucao e
         JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
         WHERE mp.malha_name = @malha
           AND (e.data_referencia >= @alvo OR e.inicio >= @corte)) AS execucoes,
        (SELECT COUNT(*) FROM dbo.etl_dependencia_evento ev
         WHERE ev.pipeline_name IN (SELECT pipeline_name FROM dbo.etl_malha_pipeline
                                    WHERE malha_name = @malha)
           AND ev.data_referencia >= @alvo) AS eventos,
        (SELECT COUNT(*) FROM dbo.etl_malha_execucao
         WHERE malha_name = @malha AND data_referencia >= @alvo) AS corridas,
        (SELECT COUNT(*) FROM dbo.etl_job_execution je
         WHERE je.pipeline IN (SELECT pipeline_name FROM dbo.etl_malha_pipeline
                               WHERE malha_name = @malha)
           AND je.start_time >= CAST(@alvo AS DATETIME)) AS jobs;
END
