-- Migration 059 — python_json em etl_pipeline_job: nó Python v2 (execução remota).
--
-- O job python ganha dois modos NOVOS, ambos executando VIA SSH no servidor do
-- ssh_conn_id do job (mesma mecânica do job shell):
--   - "arquivo": executa um script .py que JÁ existe no servidor
--                ({"modo":"arquivo","script_path":"/opt/scripts/carga.py","interpretador":"python3"})
--   - "codigo":  o usuário cola o código no painel; o Orquestra PUBLICA o
--                arquivo no servidor (SFTP) e o executa
--                ({"modo":"codigo","destino_dir":"/opt/scripts","arquivo":"carga.py",
--                  "codigo":"...", "interpretador":"python3"})
-- python_json NULL = modo legado "modulo" (importa job_command no worker) —
-- jobs existentes não mudam. Análogo a condition/notify/sql_json: JSON
-- por-coluna, idempotente, backend/UI degradam se a coluna não existir.

IF COL_LENGTH('dbo.etl_pipeline_job', 'python_json') IS NULL
BEGIN
    ALTER TABLE dbo.etl_pipeline_job ADD python_json NVARCHAR(MAX) NULL;
    PRINT '[OK] etl_pipeline_job.python_json adicionada';
END
ELSE
    PRINT '[SKIP] etl_pipeline_job.python_json já existe';
GO
