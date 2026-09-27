-- Backlog autorizado na entrevista de 27/09/2026. Não implementa validação.
-- Aplicar pela etapa 6c do deploy.sh; revalidar numeração antes da PR.
SET NOCOUNT ON;

IF OBJECT_ID('dbo.etl_backlog', 'U') IS NULL
    PRINT '[--] etl_backlog ausente (migration 035) — item não registrado';
ELSE
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM dbo.etl_backlog
        WHERE titulo = N'Valida Arquivo: confirmar origem do arquivo na execução e tratar concorrência'
    )
        INSERT INTO dbo.etl_backlog
            (titulo, descricao, tipo, area, prioridade, status, tags, criado_por)
        VALUES (
            N'Valida Arquivo: confirmar origem do arquivo na execução e tratar concorrência',
            N'Fora da primeira entrega por decisão do usuário em 27/09/2026. No caso informado, a limpeza existente remove os arquivos e há novo arquivo no dia seguinte, vazio ou com dados; comportamento ainda não certificado por teste desta feature. Avaliar mecanismos genéricos para impedir consumo de artefato antigo ou de outra execução: referência/run no caminho, manifesto do produtor e concorrência em diretório compartilhado. Não assumir que mtime isolado prova a origem. Pronto quando houver contrato configurável e testes cobrindo arquivo antigo, carga vazia, retomada e runs concorrentes, sem apagar arquivos automaticamente. Referência: docs/spec-parametros-globais-valida-arquivo.md.',
            N'feature', N'backend', N'P3', N'ideia',
            N'valida-arquivo', N'spec-parametros-valida-arquivo'
        );
END
GO
