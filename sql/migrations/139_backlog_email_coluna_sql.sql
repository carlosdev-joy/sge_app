-- 139_backlog_email_coluna_sql.sql
-- Itens fora do escopo da spec docs/spec-email-coluna-sql.md (02/10/2026).
-- Idempotente por título. Aplicar pela etapa 6c do deploy.sh.
SET NOCOUNT ON;

IF OBJECT_ID('dbo.etl_backlog', 'U') IS NULL
    PRINT '[--] etl_backlog ausente (migration 035) — itens não registrados';
ELSE
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'E-mail {coluna:…}: seletor listar as colunas do SQL automaticamente')
        INSERT INTO dbo.etl_backlog
            (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'E-mail {coluna:…}: seletor listar as colunas do SQL automaticamente',
            N'Fora da spec docs/spec-email-coluna-sql.md (02/10/2026). Hoje o alias é digitado no seletor porque a prévia do nó SQL (PainelSql) é estado local e não é gravada. Avaliar persistir as colunas da última prévia na configuração do nó SQL e listá-las no seletor do e-mail, avisando quando a prévia estiver desatualizada em relação ao SELECT. Pronto quando o seletor oferecer os alias reais sem digitar e o aviso de prévia antiga existir.',
            N'feature', N'frontend', N'P3', N'ideia', N'email,sql', N'spec-email-coluna-sql');

    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'E-mail {coluna:…}: escolher a linha do resultado ({coluna:NO.ALIAS.N})')
        INSERT INTO dbo.etl_backlog
            (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'E-mail {coluna:…}: escolher a linha do resultado ({coluna:NO.ALIAS.N})',
            N'Fora da spec docs/spec-email-coluna-sql.md (02/10/2026): o marcador só resolve resultado de 1 linha. Se surgir caso real (ex.: um valor por filial no corpo), avaliar a N-ésima linha sem ambiguidade com nomes de nó que têm ponto. Até lá, série é {tabela}.',
            N'feature', N'backend', N'P3', N'ideia', N'email,sql', N'spec-email-coluna-sql');

    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'Nó SQL: aceitar {odate} na consulta')
        INSERT INTO dbo.etl_backlog
            (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'Nó SQL: aceitar {odate} na consulta',
            N'Levantado na spec docs/spec-email-coluna-sql.md (02/10/2026): o SQL do nó não interpola marcadores, então a consulta que alimenta o e-mail não consegue filtrar pela data de referência da corrida e depende de GETDATE() ou de valor fixo. Avaliar passar {odate} como parâmetro (não por concatenação de texto), com prévia usando um valor de exemplo.',
            N'feature', N'backend', N'P3', N'ideia', N'sql,email', N'spec-email-coluna-sql');

END
GO
