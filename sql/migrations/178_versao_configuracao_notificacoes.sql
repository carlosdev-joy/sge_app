-- 178: formulário de notificações F8; versão idempotente, sem transporte.
DECLARE @titulo NVARCHAR(200) = N'Configuração de notificações do pipeline';

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
    SET @nova = CONCAT(@maior, '.', @menor + 1, '.0');

    INSERT INTO dbo.etl_versao_ferramenta (versao, titulo, descricao_md, criado_por)
    VALUES (@nova, @titulo, N'## Configuração de notificações do pipeline

- Formulário de eventos Sucesso, Warning e Falha no mesmo rascunho e publicação.
- E-mails corporativos, E-mail e Teams pessoal independentes e canal adicional do cadastro existente.
- Resumo de entregas hipotéticas por evento; prévia autorizada sem envio ou resolução externa.
- Consulta de disponibilidade protegida sem exigir edição; integrações incompletas continuam indisponíveis.
- Políticas legadas e futuras preservadas; componentes de tarefas não são alterados.
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

-- A interface não certifica integrações externas por planejamento/simulação.
IF OBJECT_ID('dbo.etl_backlog', 'U') IS NULL
    PRINT '[--] etl_backlog ausente (migration 035) — gate externo não registrado';
ELSE IF NOT EXISTS (SELECT 1 FROM dbo.etl_backlog WHERE titulo = N'Notificações: certificar destinos no tenant antes de habilitar envio')
    INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
    VALUES (N'Notificações: certificar destinos no tenant antes de habilitar envio',
            N'Gate externo EOC-F8/F10/F11: validar transporte, resolução corporativa, consentimento e canal no tenant autorizado antes de disponibilizar integrações. Planejamento e prévia não resolvem destinatários nem certificam readiness. Não enviar para clientes durante a validação DEV; usar fixtures próprias com limpeza. F8 não ativa SMTP/Graph/webhook.',
            N'spike', N'backend', N'P1', N'refinado', N'EOC-F8,EOC-F10,EOC-F11,alertas', N'eoc-f8');
GO
