-- ═══════════════════════════════════════════════════════════════════════════
-- Backlog — Utilitários: transferência de arquivos (spec
--   docs/spec-utilitarios-transferencia.md §2 OUT e §8). Itens que NÃO
--   entraram nas fases F1–F5, inclusive os registrados pelas revisões
--   adversariais e auditorias de segurança. Registro versionável para
--   dbo.etl_backlog (aba Admin › Sistema › Backlog). Idempotente por título:
--   rodar de novo não duplica.
-- Uso: sqlcmd -S <srv> -d <db> -b -I -i sql/backlog/utilitarios_transferencia.sql
-- ═══════════════════════════════════════════════════════════════════════════
IF OBJECT_ID('dbo.etl_backlog', 'U') IS NULL
BEGIN
    RAISERROR('dbo.etl_backlog não existe: aplique a migration 035 antes.', 16, 1);
    RETURN;
END
GO

DECLARE @itens TABLE (titulo NVARCHAR(200), descricao NVARCHAR(MAX), tipo NVARCHAR(16),
                      area NVARCHAR(24), prioridade NVARCHAR(4), tags NVARCHAR(200));
INSERT INTO @itens VALUES
(N'Utilitários: lista de extensões separada para o envio (ou denylist de executáveis)',
 N'A lista de extensões do Admin vale para editar texto E enviar binário (spec §8.16). Com a semente (só texto, sem sh) não há exposição nova, mas um admin que inclua jar/so/class/zip libera binários executáveis sob as raízes, e a sobrescrita preserva +x. Três saídas, decisão do usuário: (a) manter uma lista só e documentar (feito no manual §4.7); (b) coluna permite_envio em etl_utilitario_extensao + interruptor no Admin; (c) denylist fixa no upload para o que o Unix/DataStage executa (sh ksh bash csh pl py rb jar class so o exe dll dsx).',
 N'feature', N'backend', N'P2', N'utilitarios,seguranca'),
(N'Utilitários: cota diária de envio por usuário',
 N'50 MB por pedido, sem cota, e cada sobrescrita com cópia deixa mais 50 MB em .bak (spec §8.17): um usuário com acao_editar enche o disco do servidor do DataStage em minutos, totalmente auditado. Cota diária lida da própria auditoria — SUM(tamanho_bytes) de enviar/ok nas últimas 24 h antes de aceitar — sem migration; e ligar ao expurgo dos .bak (backlog anterior).',
 N'debt', N'backend', N'P2', N'utilitarios,operacao'),
(N'Utilitários: teto de transferência configurável no Admin',
 N'O teto do download e do envio é a constante TRANSFERENCIA_MAX_BYTES (50 MB), exposta como transferencia_max_kb no /utilitarios/config (spec §2 OUT e §8.3). Uma chave utilitarios_transferencia_max_kb em etl_app_config com o campo no Admin › Utilitários › Limites permitiria ajustar sem deploy; o client_max_body_size do nginx (64 MB) vira o limite prático.',
 N'feature', N'backend', N'P3', N'utilitarios'),
(N'Utilitários: download por link com ticket assinado',
 N'O download vai por fetch + Blob porque o token vive no localStorage, não em cookie: 50 MB passam pela memória do navegador e não há barra de progresso nativa (spec §2 OUT). Um ticket assinado de curta duração (GET /utilitarios/arquivo/baixar?ticket=…) permitiria <a href> direto, progresso do navegador e sem teto de memória — e resolveria o "ok" da auditoria antes da entrega.',
 N'feature', N'backend', N'P3', N'utilitarios,ux'),
(N'Utilitários: vários arquivos por operação e pasta como zip',
 N'Um arquivo por vez nos dois sentidos (spec §2 OUT). Seleção múltipla no envio (fila com resultado por arquivo) e download de pasta inteira compactada na API (com teto de tamanho e de entradas).',
 N'feature', N'frontend', N'P3', N'utilitarios,ux'),
(N'Utilitários: .tmp órfão quando o canal SSH morre no meio da gravação',
 N'Se a rede cai (ou o canal expira nos 60 s depois de um 504) durante a escrita, o _apagar_tmp usa o mesmo canal morto e engole a falha: fica .<nome>.tmp-<pid>-<hex> oculto na pasta (spec §8.19). Pré-existente na gravação; o envio de 50 MB multiplica a exposição. Varredura de .tmp- antigos na listagem do navegador (ou no expurgo dos .bak) com aviso ao admin.',
 N'debt', N'backend', N'P3', N'utilitarios,operacao'),
(N'Utilitários: fechar a janela sem o destino no backup (hardlink@openssh.com)',
 N'Com cópia de segurança ligada, rename(real→bak) + posix_rename(tmp→real) deixa um instante sem o caminho (spec §8.20, já documentado na spec anterior). A extensão hardlink@openssh.com (link(real, bak) + posix_rename) fecha a janela pelo mesmo _request usado no statvfs. Só se algum job tropeçar.',
 N'debt', N'backend', N'P3', N'utilitarios'),
(N'Utilitários: porta 8000 da API publicada em todas as interfaces',
 N'O compose publica ${API_PORT:-8000}:8000 no host inteiro (spec §8.13). Quem alcança a API sem o nginx fala com o uvicorn, que não tem timeout de leitura de corpo — a F3 se protege (vaga só com o corpo inteiro, 408 de corpo parado), mas a régua deve ser o nginx: publicar 127.0.0.1:8000:8000 ou não publicar (o nginx fala pela rede do compose). Conferir em produção com ss -ltnp e regras de firewall.',
 N'debt', N'infra', N'P2', N'utilitarios,seguranca,infra');

INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por, ref_pr)
SELECT i.titulo, i.descricao, i.tipo, i.area, i.prioridade, N'ideia', i.tags, N'spec-utilitarios-transferencia-f5', N'#364-#368'
FROM @itens i
WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_backlog b WHERE b.titulo = i.titulo);

PRINT '[OK] backlog da transferência de arquivos registrado (sem duplicar)';
GO
