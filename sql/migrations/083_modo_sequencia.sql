-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 083 — Interruptor do MODO SEQUÊNCIA (ODATE fora da liberação)
--
--   Enquanto a operação amadurece o uso da execução agendada, a data de
--   referência pode atrapalhar mais do que ajuda: pai e filho carimbando
--   ODATEs diferentes travam (ou soltam) a cadeia por um motivo que o
--   operador não vê. Este interruptor troca a pergunta do predicado:
--
--     modo DATA (padrão, '0') — "o predecessor teve SUCESSO NESTA data de
--       referência?" — o comportamento de sempre;
--     modo SEQUÊNCIA ('1')    — "o predecessor teve SUCESSO NESTE ciclo?" —
--       a ordem dos jobs manda, a data não entra na conta.
--
--   O sucesso continua tendo de ser DESTA rodada (janela a partir da virada
--   corrente): ignorar isso faria o sucesso de ontem liberar o filho de hoje
--   para sempre — bem pior que o problema que o modo resolve.
--
--   A corrida SEGUE carimbando data_referencia (é a chave do índice único e
--   do claim). O que muda é só quem manda na LIBERAÇÃO — por isso dá para
--   ligar e desligar sem deploy, e voltar ao modo data quando quiser testar.
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_app_config', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_app_config
                   WHERE config_key = 'dependencia_modo_sequencia')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    -- ⚠️ T-SQL NAO concatena literais adjacentes (o erro da 025): uma string
    -- so, ou com +. Aqui vai inteira.
    VALUES ('dependencia_modo_sequencia', '0',
            'Liberacao por SEQUENCIA (1) ou por DATA DE REFERENCIA (0, padrao). Em 1, o Aguarde/dependencia libera quando o predecessor concluiu NESTE ciclo, sem exigir o mesmo ODATE. Vale no proximo run das DAGs - nao precisa republicar.');
    PRINT '[OK] etl_app_config.dependencia_modo_sequencia criada (padrao 0)';
END
GO
