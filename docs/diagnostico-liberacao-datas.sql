-- ═══════════════════════════════════════════════════════════════════════════
-- Diagnóstico: Aguarde liberou com predecessores em DATAS DE REFERÊNCIA
-- diferentes (relato de produção, malha Carga_Vida, 2026-08-04).
--
-- Três perguntas, nesta ordem. A 1ª quase sempre já responde.
-- Troque 'Carga_Vida' e as datas se precisar.
-- ═══════════════════════════════════════════════════════════════════════════

DECLARE @malha  SYSNAME = N'Carga_Vida';
DECLARE @d1     DATE    = '2026-08-03';
DECLARE @d2     DATE    = '2026-08-04';

-- ── 1. Quem ainda dispara SOZINHO apesar de ter dependência ────────────────
-- Pipeline com predecessor cadastrado tem de ter a DAG publicada como
-- dependente (schedule=None). Enquanto a DAG NÃO for republicada, ela mantém
-- o cron antigo e roda no horário dela, sem consultar liberação nenhuma — é a
-- causa mais provável de "sucesso fora de ordem" e de ODATE divergente.
--   publicacao_pendente = 1  → o cadastro mudou depois da última publicação
--   dag_criada = 0           → nunca publicada
SELECT
    p.pipeline_name,
    p.schedule_type,
    p.scheduled_time,
    p.hora_virada,
    CAST(p.dag_criada AS INT)                                   AS dag_criada,
    CASE WHEN p.dag_config_pendente_em IS NULL THEN 0 ELSE 1 END AS publicacao_pendente,
    (SELECT COUNT(*) FROM dbo.etl_pipeline_dependencia d
      WHERE d.pipeline_name = p.pipeline_name AND d.tipo = 'PIPELINE') AS qtd_predecessores
FROM dbo.etl_pipeline p
JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = p.pipeline_name
WHERE mp.malha_name = @malha
ORDER BY qtd_predecessores DESC, p.pipeline_name;
-- ⚠️ Linha com qtd_predecessores > 0 E schedule_type <> 'on_demand' com
--    publicacao_pendente = 1 é o alvo: a DAG no Airflow ainda tem cron.

-- ── 2. As execuções das duas datas, com a ORIGEM do disparo ────────────────
-- disparado_por = 'agenda'  → rodou pelo cron (não foi o Aguarde)
-- disparado_por = <nome>    → veio por push do predecessor
-- disparado_por = 'guardia' → foi a guardiã que ordenou
-- Compare `inicio` (dia REAL) com `data_referencia` (ODATE): quando os dois
-- não andam juntos entre os membros, a corrida do dia mistura dados.
SELECT
    e.pipeline_name,
    e.data_referencia,
    e.status,
    e.inicio,
    e.fim,
    e.disparado_por,
    CAST(e.inicio AS DATE) AS dia_real,
    CASE WHEN CAST(e.inicio AS DATE) <> e.data_referencia
         THEN '<<< ODATE != dia real' ELSE '' END AS alerta
FROM dbo.etl_pipeline_execucao e
JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = e.pipeline_name
WHERE mp.malha_name = @malha
  AND e.data_referencia IN (@d1, @d2)
ORDER BY e.data_referencia, e.pipeline_name, e.inicio;

-- ── 3. Viradas divergentes dentro da malha ────────────────────────────────
-- A hora de virada decide o ODATE de cada pipeline. Membros com viradas
-- diferentes carimbam datas diferentes para a MESMA corrida — e aí o
-- predicado de liberação (que compara só o ODATE) pode fechar a condição
-- com o sucesso de ontem de um deles.
SELECT
    ISNULL(CONVERT(VARCHAR(5), p.hora_virada, 108),
           '(global: ' + ISNULL((SELECT config_value FROM dbo.etl_app_config
                                  WHERE config_key = 'dependencia_hora_virada'), '00:00') + ')')
        AS virada_efetiva,
    COUNT(*)                              AS qtd_pipelines,
    STRING_AGG(p.pipeline_name, ', ')     AS pipelines
FROM dbo.etl_pipeline p
JOIN dbo.etl_malha_pipeline mp ON mp.pipeline_name = p.pipeline_name
WHERE mp.malha_name = @malha
GROUP BY p.hora_virada
ORDER BY virada_efetiva;
-- ⚠️ Mais de UMA linha aqui = a malha não tem régua de data única.

-- ── 4. Eventos que a guardiã já registrou sobre isso ──────────────────────
SELECT TOP 50 pipeline_name, data_referencia, tipo, detectado_em, detalhe
FROM dbo.etl_dependencia_evento
WHERE tipo IN ('DATA_DIVERGENTE', 'PREDECESSOR_FALHOU', 'NAO_LIBEROU')
  AND data_referencia IN (@d1, @d2)
ORDER BY detectado_em DESC;
