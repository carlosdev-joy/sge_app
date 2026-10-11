-- 167_versao_pipeline_ux_execucao.sql
-- Idempotente — seguro para rodar mais de uma vez.
-- Funcionalidade: incrementa o minor e zera o patch.
-- Título estável evita duplicação; sincroniza a versão e o nome da aplicação.
SET NOCOUNT ON;

DECLARE @titulo NVARCHAR(200) = N'Execução do Pipeline com investigação contextual';

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
    VALUES (@nova, @titulo, N'## Execução do Pipeline com investigação contextual

- Execução usa o mesmo desenho da Montagem, sem biblioteca nem ferramentas de edição. Cada etapa mostra ícone e rótulo do estado real: concluída, executando, falhou, pulada, em espera no portão, sem telemetria ou estado não traduzido. Só a etapa com telemetria ativa indica atividade; sucesso não pulsa e corrida encerrada não anima.
- Selecionar uma etapa abre à direita a investigação com Resumo, Tentativas, Logs e Parâmetros, e as ações autorizadas de reprocessar a partir da etapa e de pausa. Expandir leva a investigação à área do canvas sem perder corrida, etapa, tentativa ou zoom.
- Gráfico e Tabela são vistas alternativas da mesma corrida e seleção; Localizar etapa centraliza a etapa escolhida.
- Histórico abre sob demanda com filtros por data de referência, situação e versão publicada, paginação e retorno ao mesmo visualizador.
- Executar abre um formulário guiado: data de referência e data lógica opcionais, identificador estável da solicitação e JSON apenas sob demanda. A corrida retornada fica selecionada; Solicitado, Em fila e Executando aparecem como estados diferentes.
- A tela mostra a fonte do desenho (versão vinculada à corrida ou configuração publicada atual), a hora da última atualização e o estado da conexão; com a fonte indisponível, mantém o último estado e suspende o indicador de atividade.
- Confirmações de execução, reprocessamento e pausa valem só para a sessão, a corrida e a etapa em que foram abertas. Uma resposta de outra corrida ou de outro pipeline não altera desenho, versão nem estados. Com a aba oculta, as consultas param e são refeitas ao voltar.', 'deploy');

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
