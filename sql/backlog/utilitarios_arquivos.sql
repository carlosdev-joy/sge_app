-- ═══════════════════════════════════════════════════════════════════════════
-- Backlog — Utilitários de arquivos (spec docs/spec-utilitarios-arquivos.md §8)
--   Itens que NÃO entraram nas fases F1–F7. Registro versionável para
--   dbo.etl_backlog (aba Admin › Sistema › Backlog). Idempotente por título:
--   rodar de novo não duplica.
-- Uso: sqlcmd -S <srv> -d <db> -b -I -i sql/backlog/utilitarios_arquivos.sql
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
(N'Utilitários: raiz só de leitura (permite_gravar por raiz)',
 N'Hoje toda raiz ativa vale para ler E gravar (spec §8.9). Uma coluna permite_gravar em etl_utilitario_raiz + interruptor no Admin + conferência em preparar_gravacao permitiria liberar diretórios de projeto com .param de credencial só para leitura. Enquanto não existe, a decisão operacional é não cadastrar esses diretórios como raiz.',
 N'feature', N'backend', N'P1', N'utilitarios,seguranca'),
(N'Utilitários: expurgo dos .bak e do log de auditoria',
 N'Cada sobrescrita com cópia de segurança deixa nome.ext.bak-<ts>-<ms> na mesma pasta e nada apaga (spec §8.7 e §8.10); etl_utilitario_arquivo_log também cresce sem limite. Purga por idade dos .bak (ou subpasta .orquestra_bak/ com limpeza) e retenção do log (ex.: 180 dias) antes de liberar a gravação em volume.',
 N'debt', N'backend', N'P2', N'utilitarios,operacao'),
(N'Utilitários: mais servidores além do DataStage',
 N'O registro SERVIDORES em api/services/ssh_arquivos.py aceita servidor novo com uma entrada (id, label, credencial); a tela e os endpoints seguem sozinhos. Falta decidir quais servidores entram, as variáveis de credencial de cada um e o known_hosts. Levar o utilitário ao Console DataStage é a mesma frente.',
 N'feature', N'backend', N'P3', N'utilitarios'),
(N'Utilitários: fila do executor SSH com teto (503 ocupado)',
 N'O executor dedicado (4 threads por worker, 90 s) atende ler/gravar/listar/testar; a fila não tem teto — 8 listagens grandes em paralelo fizeram uma listagem pequena esperar ~10 s (auditoria da F6, spec §8.12). Teto na fila com 503 "ocupado" ou semáforo por usuário. O corte de 20 mil entradas brutas já limita o pior caso.',
 N'debt', N'backend', N'P3', N'utilitarios,performance'),
(N'Utilitários: 413 antes de ler o corpo inteiro na gravação',
 N'O teto por arquivo é aplicado depois de ler o corpo inteiro (o nginx aceita 64 MB); um Content-Length acima do teto poderia ser recusado antes de ler (spec §8.11).',
 N'debt', N'backend', N'P3', N'utilitarios'),
(N'Utilitários: editor com nome completo (extensão maiúscula, sem extensão)',
 N'A aba Criar/editar só grava nome.extensão em minúscula (lista de extensões minúscula; o servidor distingue caixa). RELATORIO.TXT, README e nomes com espaço nas pontas se leem pela aba Ver arquivo mas não se editam (spec §8.14): o navegador preenche só a pasta e avisa. Campo único de nome com extensão inferida resolveria.',
 N'feature', N'frontend', N'P3', N'utilitarios,ux'),
(N'Utilitários: oráculo residual em link plantado no servidor',
 N'Link para /naoexiste/x responde 404 e link para /etc/naoexiste responde 403 (o realpath do OpenSSH tolera só o último componente ausente) — revela se a pasta-mãe do alvo existe, só para quem cria o link no servidor (spec §8.13). Fechável mapeando 404 num componente-link para 403 (um lstat por nível).',
 N'debt', N'backend', N'P3', N'utilitarios,seguranca'),
(N'Utilitários: TOCTOU entre realpath e open/rename',
 N'O open/rename no caminho real ainda segue symlink criado ENTRE o realpath e a operação (spec §8.8). Exige shell no servidor, sem ganho de privilégio; residual aceito e documentado. Fechar exigiria O_NOFOLLOW, que o SFTP não oferece.',
 N'debt', N'backend', N'P3', N'utilitarios,seguranca');

INSERT INTO dbo.etl_backlog (titulo, descricao, tipo, area, prioridade, status, tags, criado_por, ref_pr)
SELECT i.titulo, i.descricao, i.tipo, i.area, i.prioridade, N'ideia', i.tags, N'spec-utilitarios-f7', N'#356-#363'
FROM @itens i
WHERE NOT EXISTS (SELECT 1 FROM dbo.etl_backlog b WHERE b.titulo = i.titulo);

PRINT '[OK] backlog dos Utilitários registrado (sem duplicar)';
GO
