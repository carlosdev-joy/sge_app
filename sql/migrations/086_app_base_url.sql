-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 086 — app_base_url (docs/spec-malha-execucao.md §9.8, Decisao 69)
--
--   A camada de visibilidade da corrida (F4..F10) mora numa tela que, as 3h,
--   custa: destravar o telefone, abrir o notebook, VPN, /malha, achar a malha
--   na lista, trocar o modo, escolher a data. O card do Teams passa a levar um
--   botao que cai DIRETO na corrida — e o botao precisa saber em que endereco
--   este Orquestra atende, que e a unica coisa que o codigo nao tem como
--   descobrir sozinho.
--
--   ⚠️ Nasce VAZIA de proposito, e isso NAO e um esquecimento:
--     • o endereco muda por ambiente (dev, homologacao, a rede da Caixa) e
--       migration nao e o lugar de adivinhar host de producao;
--     • com a chave vazia o card sai EXATAMENTE como hoje, sem botao e sem
--       erro no ciclo da guardia (degradacao por ausencia — nunca URL
--       inventada, que mandaria o plantao para um endereco que nao existe as
--       3h da manha);
--     • a linha existe para ser DESCOBERTA: ela aparece na tela de
--       configuracao com a descricao ao lado, e preenche-la e uma edicao de
--       valor, nao um INSERT a mao no banco de producao.
--   Ligar o botao = preencher esta chave (pendencia 9 do §18 da spec).
--
--   Idempotente — seguro para rodar mais de uma vez (etapa 6c do deploy.sh).
--   ⚠️ T-SQL NAO concatena literais adjacentes (o erro real da 025 e da 083):
--   a descricao vai numa string SO, sem quebra de linha dentro das aspas.
-- ═══════════════════════════════════════════════════════════════════════════

IF OBJECT_ID('dbo.etl_app_config', 'U') IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM dbo.etl_app_config
                   WHERE config_key = 'app_base_url')
BEGIN
    INSERT INTO dbo.etl_app_config (config_key, config_value, descricao)
    VALUES ('app_base_url', '',
            'Endereco base desta instalacao do Orquestra (ex.: https://orquestra.exemplo.com), sem barra no fim. E a base do botao que os cards de malha do Teams levam para a corrida. VAZIA = o card sai sem botao, que e a degradacao correta. So aceita http:// ou https://; qualquer outro valor e tratado como vazio.');
    PRINT '[OK] etl_app_config.app_base_url criada (VAZIA — o card sai sem botao)';
END
ELSE
    PRINT '[--] etl_app_config.app_base_url ja existe (ou etl_app_config ausente)';
GO

-- ── Conferencia (spec §12.1 — migrate.py descarta PRINT, D40) ──────────────
SELECT config_key, config_value,
       CASE WHEN LTRIM(RTRIM(ISNULL(config_value, ''))) = ''
            THEN 'sem botao no card (preencha para ligar)'
            ELSE 'botao ligado' END AS efeito_no_card
FROM dbo.etl_app_config
WHERE config_key = 'app_base_url';
GO
