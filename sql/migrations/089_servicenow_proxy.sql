-- 089_servicenow_proxy.sql
-- Rota de saída do sync dos chamados: seed de 'servicenow_proxy' em
-- dbo.etl_app_config (docs/spec-chamados-servicenow.md).
--
-- POR QUE ISTO EXISTE
-- O primeiro ciclo real do sync morreu com "Connection reset by peer" nas
-- QUATRO tabelas em 1 segundo — a rede da Caixa cortando a saída direta. O
-- proxy corporativo estava configurado só no container orquestra-api (é por
-- isso que a SONDA do Admin funcionava): a DAG roda no airflow-worker, que
-- nunca recebeu as variáveis.
--
-- A rota poderia ter virado variável de ambiente do worker. Virou CONFIG
-- porque variável de ambiente só entra em container NOVO, e recriar o
-- airflow-worker mata as tasks em execução — inclusive jobs DataStage, que
-- continuam vivos no DS enquanto o Airflow os dá por mortos. Aqui, trocar o
-- proxy é editar um campo na tela: o próximo ciclo já usa, sem recriar nada.
--
-- Fica na MESMA tabela e no MESMO prefixo das outras chaves servicenow_*, e
-- por isso a DAG já a enxerga sem mudar a consulta (ela lê LIKE 'servicenow%').
--
-- Valor VAZIO = conexão direta. É o correto para ambientes sem firewall de
-- saída (o dev alcança o ServiceNow sem proxy); em produção, preencha em
-- Admin > ServiceNow com o mesmo valor do HTTPS_PROXY do servidor.
--
-- Idempotente: MERGE só insere o que faltar. Rodar de novo NUNCA sobrescreve
-- um proxy já configurado em produção.

IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_app_config')
BEGIN
    MERGE dbo.etl_app_config AS t
    USING (VALUES
        ('servicenow_proxy', '',
         'ServiceNow: proxy de saida do sync (http://host:porta). Vazio = conexao direta')
    ) AS s (k, v, d)
    ON t.config_key = s.k
    WHEN NOT MATCHED THEN INSERT (config_key, config_value, descricao, updated_by, updated_at)
        VALUES (s.k, s.v, s.d, 'migration-089', GETDATE());
    PRINT '[OK] Seed servicenow_proxy garantido em etl_app_config';
END
ELSE
    PRINT '[SKIP] dbo.etl_app_config ainda nao existe (rode a 088 antes)';
GO

-- Conferência: as seis chaves do ServiceNow, com o proxy mascarado só o
-- suficiente para NÃO esconder se está vazio (que é a pergunta do dia).
SELECT config_key,
       CASE WHEN config_key LIKE '%senha%' AND config_value <> '' THEN '<cifrada>'
            WHEN config_value = '' THEN '<vazio>'
            ELSE config_value END AS valor,
       updated_by, updated_at
FROM dbo.etl_app_config
WHERE config_key LIKE 'servicenow%'
ORDER BY config_key;
GO
