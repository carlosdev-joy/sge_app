-- 176: aceite técnico Pipeline F6; versão e pendências idempotentes.
DECLARE @titulo NVARCHAR(200) = N'Pipeline no orçamento com logs sob demanda e perfis de piloto';

IF OBJECT_ID('dbo.etl_versao_ferramenta', 'U') IS NULL
    PRINT '[--] etl_versao_ferramenta ausente (migration 003) — versão não registrada';
ELSE IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta WHERE titulo = @titulo)
    PRINT '[SKIP] versão desta entrega já registrada';
ELSE
BEGIN
    DECLARE @maior INT, @menor INT, @patch INT, @nova NVARCHAR(20);

    -- Só versões numéricas de 1 a 4 partes ("3", "2.2", "2.4.1", "2.4.1.7"),
    -- completadas para 4 partes; o resto é ignorado.
    ;WITH v AS (
        SELECT versao + REPLICATE('.0', 3 - (LEN(versao) - LEN(REPLACE(versao, '.', '')))) AS v4
          FROM dbo.etl_versao_ferramenta
         WHERE versao NOT LIKE '%[^0-9.]%' AND versao NOT LIKE '%..%'
           AND versao NOT LIKE '.%' AND versao NOT LIKE '%.' AND versao <> ''
           AND LEN(versao) - LEN(REPLACE(versao, '.', '')) BETWEEN 0 AND 3
    ), n AS (
        SELECT TRY_CONVERT(INT, PARSENAME(v4, 4)) AS a, TRY_CONVERT(INT, PARSENAME(v4, 3)) AS b,
               TRY_CONVERT(INT, PARSENAME(v4, 2)) AS c, TRY_CONVERT(INT, PARSENAME(v4, 1)) AS d
          FROM v
    )
    SELECT TOP 1 @maior = a, @menor = b, @patch = c
      FROM n
     WHERE a IS NOT NULL AND b IS NOT NULL AND c IS NOT NULL AND d IS NOT NULL
     ORDER BY a DESC, b DESC, c DESC, d DESC;

    -- Versão fora do padrão (sufixo "-hotfix", 5+ partes, espaço) é ignorada aqui,
    -- mas o cabeçalho a compara com parseInt: avisa no log do deploy, para o admin
    -- conferir o número em Admin › Versões.
    IF EXISTS (SELECT 1 FROM dbo.etl_versao_ferramenta
                WHERE versao LIKE '%[^0-9.]%' OR versao LIKE '%..%' OR versao LIKE '.%' OR versao LIKE '%.'
                   OR LEN(versao) - LEN(REPLACE(versao, '.', '')) > 3)
        PRINT '[ATENÇÃO] há versões fora do padrão em etl_versao_ferramenta (ignoradas no cálculo) — confira o número em Admin › Versões';

    IF @maior IS NULL
        SELECT @maior = 2, @menor = 2, @patch = 0;
    SET @nova = CONCAT(@maior, '.', @menor, '.', @patch + 1);

    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@nova, @titulo, N'## Pipeline no orçamento com logs sob demanda e perfis de piloto

- Detalhes de logs carregados ao abrir, com Cancelar/Esc durante a espera e erro local sem desmontar o Dashboard.
- Reexecutar e reconhecer falha respeitam a permissão de operação, inclusive em perfis personalizados.
- Orçamento de carga fria e seleção de 300 etapas medidos; atualização mantida em 30 segundos.
- Roteiro e matriz do piloto preparados. Perfis DEV disponíveis; validação técnica não substitui aceite por usuários ou DataStage/Caixa.
', 'deploy');

    -- O mesmo que o "Nova Versão" da aba faz.
    IF OBJECT_ID('dbo.etl_app_config', 'U') IS NOT NULL
    BEGIN
        UPDATE dbo.etl_app_config SET config_value = @nova WHERE config_key = 'app_version';
        IF @@ROWCOUNT = 0
            INSERT INTO dbo.etl_app_config (config_key, config_value) VALUES ('app_version', @nova);
        UPDATE dbo.etl_app_config SET config_value = @titulo WHERE config_key = 'app_release_name';
        IF @@ROWCOUNT = 0
            INSERT INTO dbo.etl_app_config (config_key, config_value) VALUES ('app_release_name', @titulo);
    END

    PRINT CONCAT('[OK] versão ', @nova, ' registrada: ', @titulo);
END

GO

-- Pendências reais do aceite; este registro não habilita polling em 5 s nem conclui o piloto.
IF OBJECT_ID('dbo.etl_backlog', 'U') IS NULL
    PRINT '[--] etl_backlog ausente (migration 035) — pendências não registradas';
ELSE
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'EOC-F6: piloto humano Pipeline e certificação DataStage/Caixa')
        INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'EOC-F6: piloto humano Pipeline e certificação DataStage/Caixa',
                N'Testes técnicos com os três perfis DEV aprovados; falta aceite de pessoas reais em Desenvolvimento, Consulta e Sustentação. Registrar sucesso, tempo, retornos, dúvidas e ajuda por jornada em docs/eoc-f6-aceite-pipeline.md. DataStage e dataset real exigem validação na Caixa; SQL/Shell em DEV não substituem essa certificação. Preparação técnica não encerra o aceite humano.',
                N'spike', N'frontend', N'P1', N'refinado', N'EOC-F6,UX-F6,piloto', N'eoc-f6');
    IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'EOC-F6: benchmark SQL e upstream antes de polling em 5 segundos')
        INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (N'EOC-F6: benchmark SQL e upstream antes de polling em 5 segundos',
                N'Manter 30 segundos. Leitura de Execução local teve p95 de 544,80 ms em 30 amostras sequenciais; coorte concorrente de quatro foi medida separadamente. Falta medir plano, IO, SQL/upstream e carga representativa antes de avaliar 5 segundos. Artefatos e limitações em docs/eoc-f6-aceite-pipeline.md. Não otimizar ou criar índice sem medição e hipótese verificável.',
                N'spike', N'backend', N'P2', N'refinado', N'EOC-F6,performance,polling', N'eoc-f6');
END
GO
