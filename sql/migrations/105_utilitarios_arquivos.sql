-- sql/migrations/105_utilitarios_arquivos.sql
-- Utilitários de arquivos no servidor (spec docs/spec-utilitarios-arquivos.md, F1).
--
-- A tela Utilitários lê (e, na F4, grava) arquivos do servidor do DataStage por
-- SFTP, pela API. O que esta migration cria é a POLÍTICA e o RASTRO:
--
--   1. dbo.etl_utilitario_raiz      — diretórios-raiz por servidor. Tudo abaixo de
--                                     uma raiz ATIVA é alcançável; fora dela, nada.
--                                     Raiz se DESATIVA, não se apaga: o log de
--                                     auditoria referencia caminhos abaixo dela.
--   2. dbo.etl_utilitario_extensao  — extensões que podem ser GRAVADAS (a leitura
--                                     é limitada só pelas raízes e pelo teste de
--                                     texto: muito arquivo Unix não tem extensão).
--   3. dbo.etl_utilitario_arquivo_log — quem leu/listou/gravou o quê, com hash.
--                                     O CONTEÚDO nunca entra aqui (LGPD, volume).
--   4. etl_app_config              — teto de tamanho e backup ao sobrescrever.
--   5. RBAC                        — recurso tela_utilitarios (admin, desenvolvedor
--                                     e operador). Gravar exige TAMBÉM acao_editar,
--                                     que o operador não tem (019).
--
-- ⚠️ Nenhuma raiz vem de fábrica: o admin cadastra pela tela (Admin › Utilitários)
--    e, até lá, a tela avisa "nenhum diretório liberado". A spec não adivinha
--    caminhos de produção.
-- ⚠️ A semente de extensões só entra com a tabela VAZIA: reexecutar a migration
--    não ressuscita extensão que o admin excluiu. `sh` fica FORA da semente —
--    gravar script que roda em pipeline é o caso de maior risco; o admin liga
--    pela tela se quiser.
--
-- Idempotente: IF OBJECT_ID nas tabelas, IF NOT EXISTS na semente, MERGE nos
-- seeds de config e no RBAC. Aplicada pela etapa 6c do deploy.sh.

-- ═══════════════════════════════════════════════════════════════════════════
-- 1. Diretórios-raiz
-- ═══════════════════════════════════════════════════════════════════════════
IF OBJECT_ID('dbo.etl_utilitario_raiz', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_utilitario_raiz (
        id          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_utilitario_raiz PRIMARY KEY,
        servidor    NVARCHAR(50)   NOT NULL,     -- 'datastage' hoje; outros no futuro
        -- 800, nao 1000: (50 + 800) x 2 bytes = 1.700, o maximo de uma chave de indice
        -- nao clusterizado. Com 1000 o CREATE so avisa e o INSERT de um caminho
        -- longo falha em runtime (Msg 1946). A API recusa acima de 800 (LIMITE_RAIZ).
        caminho     NVARCHAR(800)  NOT NULL,     -- absoluto, normalizado, sem barra final
        ativo       BIT            NOT NULL CONSTRAINT DF_etl_utilitario_raiz_ativo DEFAULT 1,
        criado_por  NVARCHAR(100)  NOT NULL,
        criado_em   DATETIME2(0)   NOT NULL CONSTRAINT DF_etl_utilitario_raiz_em DEFAULT GETDATE(),
        CONSTRAINT UQ_etl_utilitario_raiz UNIQUE (servidor, caminho)
    );
    PRINT '[OK] Tabela dbo.etl_utilitario_raiz criada';
END
ELSE
    PRINT '[SKIP] dbo.etl_utilitario_raiz ja existe';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 2. Extensões graváveis
-- ═══════════════════════════════════════════════════════════════════════════
IF OBJECT_ID('dbo.etl_utilitario_extensao', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_utilitario_extensao (
        extensao    VARCHAR(15)   NOT NULL CONSTRAINT PK_etl_utilitario_extensao PRIMARY KEY, -- minusculas, sem ponto
        criado_por  NVARCHAR(100) NOT NULL,
        criado_em   DATETIME2(0)  NOT NULL CONSTRAINT DF_etl_utilitario_extensao_em DEFAULT GETDATE()
    );
    PRINT '[OK] Tabela dbo.etl_utilitario_extensao criada';
END
ELSE
    PRINT '[SKIP] dbo.etl_utilitario_extensao ja existe';
GO

-- Semente SÓ com a tabela vazia (ver cabeçalho: não ressuscita o que o admin excluiu).
IF NOT EXISTS (SELECT 1 FROM dbo.etl_utilitario_extensao)
BEGIN
    INSERT INTO dbo.etl_utilitario_extensao (extensao, criado_por) VALUES
        ('txt',        'migration-105'),
        ('sql',        'migration-105'),
        ('csv',        'migration-105'),
        ('dat',        'migration-105'),
        ('log',        'migration-105'),
        ('param',      'migration-105'),
        ('prm',        'migration-105'),
        ('cfg',        'migration-105'),
        ('conf',       'migration-105'),
        ('ini',        'migration-105'),
        ('properties', 'migration-105'),
        ('json',       'migration-105'),
        ('xml',        'migration-105'),
        ('yaml',       'migration-105'),
        ('yml',        'migration-105');
    PRINT '[OK] Semente de extensoes inserida (15 extensoes; sh fica de fora de proposito)';
END
ELSE
    PRINT '[SKIP] dbo.etl_utilitario_extensao ja tem linhas — semente nao reaplicada';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 3. Auditoria (o conteúdo do arquivo NUNCA entra aqui)
-- ═══════════════════════════════════════════════════════════════════════════
IF OBJECT_ID('dbo.etl_utilitario_arquivo_log', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.etl_utilitario_arquivo_log (
        id            BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_etl_utilitario_arquivo_log PRIMARY KEY,
        executado_em  DATETIME2(0)   NOT NULL CONSTRAINT DF_etl_utilitario_arquivo_log_em DEFAULT GETDATE(),
        usuario       NVARCHAR(100)  NOT NULL,   -- matricula (get_current_user)
        servidor      NVARCHAR(50)   NOT NULL,
        acao          VARCHAR(10)    NOT NULL,   -- 'ler' | 'listar' | 'gravar' | 'testar'
        caminho       NVARCHAR(1000) NOT NULL,   -- caminho REAL (pos realpath), ou o pedido se negado
        tamanho_bytes BIGINT         NULL,
        sha256        CHAR(64)       NULL,       -- so em 'gravar'
        resultado     VARCHAR(20)    NOT NULL,   -- 'ok' | 'negado' | 'erro'
        detalhe       NVARCHAR(500)  NULL,       -- motivo do negado/erro, backup criado, truncado...
        duracao_ms    INT            NULL
    );
    CREATE INDEX IX_etl_utilitario_arquivo_log_em      ON dbo.etl_utilitario_arquivo_log (executado_em);
    CREATE INDEX IX_etl_utilitario_arquivo_log_usuario ON dbo.etl_utilitario_arquivo_log (usuario, executado_em);
    PRINT '[OK] Tabela dbo.etl_utilitario_arquivo_log criada';
END
ELSE
    PRINT '[SKIP] dbo.etl_utilitario_arquivo_log ja existe';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 4. Configuração (MERGE: não sobrescreve valor já editado no Admin)
-- ═══════════════════════════════════════════════════════════════════════════
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_app_config')
BEGIN
    MERGE dbo.etl_app_config AS t
    USING (VALUES
        ('utilitarios_arquivo_max_kb', '2048', 'Utilitarios: teto de tamanho (KB) para ler/gravar um arquivo; acima disso so "ultimas N linhas"'),
        ('utilitarios_arquivo_backup', '1',    'Utilitarios: 1 = guarda copia .bak-<data> antes de sobrescrever um arquivo; 0 = nao guarda')
    ) AS s (k, v, d)
    ON t.config_key = s.k
    WHEN NOT MATCHED THEN INSERT (config_key, config_value, descricao, updated_by, updated_at)
        VALUES (s.k, s.v, s.d, 'migration-105', GETDATE());
    PRINT '[OK] Seeds utilitarios_* garantidos em etl_app_config';
END
ELSE
    PRINT '[SKIP] dbo.etl_app_config ainda nao existe';
GO

-- ═══════════════════════════════════════════════════════════════════════════
-- 5. RBAC da tela — sem isto a tela nova sobe invisível no menu (gotcha 6c)
-- ═══════════════════════════════════════════════════════════════════════════
IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
           WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_perfil_permissao')
BEGIN
    MERGE dbo.etl_perfil_permissao AS t
    USING (VALUES
        ('admin',         'tela_utilitarios'),
        ('desenvolvedor', 'tela_utilitarios'),
        ('operador',      'tela_utilitarios')
    ) AS s (perfil_nome, recurso)
    ON t.perfil_nome = s.perfil_nome AND t.recurso = s.recurso
    WHEN NOT MATCHED THEN INSERT (perfil_nome, recurso, criado_por)
        VALUES (s.perfil_nome, s.recurso, 'migration-105');
    PRINT '[OK] Recurso tela_utilitarios garantido (admin/desenvolvedor/operador)';
END
ELSE
    PRINT '[SKIP] Tabela etl_perfil_permissao ainda nao existe (rode a 019 antes)';
GO
