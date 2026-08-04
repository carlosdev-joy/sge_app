-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 084 — Janela do MODO SEQUÊNCIA
--
--   "O predecessor concluiu nas ultimas N horas?" — o corte que o modo
--   sequencia (083) usa no lugar da data de referencia.
--
--   NAO usamos a virada do dia como corte, de proposito: malha que comeca 23h
--   e termina 01h do dia seguinte teria o pai ANTES da virada e o filho
--   DEPOIS, e a corrida que atravessa a meia-noite travaria EM SILENCIO —
--   exatamente o problema que o ODATE existe para resolver. A janela
--   deslizante ignora a fronteira do dia e continua barrando a rodada
--   ANTERIOR, desde que seja menor que o intervalo entre execucoes.
--
--   Default 12h: cobre folgado uma malha de 2-3h e esta bem abaixo das 24h
--   de uma malha diaria. Dominio 1..168; fora disso, o codigo volta ao
--   default (janela 0 travaria tudo; janela enorme deixaria o sucesso da
--   semana passada liberar hoje).
--
--   Nasce em migration PROPRIA porque a 083 ja foi aplicada em ambiente:
--   migration aplicada nao se altera — alterar o arquivo nao a reaplica, e o
--   ambiente que ja rodou ficaria sem a chave, em silencio.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_app_config', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_app_config
                   WHERE config_key = 'dependencia_janela_sequencia_horas')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('dependencia_janela_sequencia_horas', '12',
            'Janela do modo SEQUENCIA em horas (1 a 168, padrao 12): o predecessor conta como concluido se terminou dentro dela. Use um valor MENOR que o intervalo entre execucoes da malha e MAIOR que a duracao dela.');
    PRINT '[OK] etl_app_config.dependencia_janela_sequencia_horas criada (padrao 12)';
END
GO
