using System.Data;
using Microsoft.Data.SqlClient;
using Orquestra.Application.Drafts;
using Orquestra.Application.Security;
using Orquestra.Infrastructure.Security;

namespace Orquestra.Infrastructure.Drafts;

// F2: uma linha por pipeline, igualdade decidida no SQL pela collation real das colunas pipeline_name
// (UNION + OUTER APPLY TOP(1)); nenhum agrupamento por nome em memória. READ COMMITTED, só dado confirmado (sem
// NOLOCK, READPAST nem snapshot): a leitura espera a escrita em andamento.
// Correção EOC-F2 (contenção): ler o JSON do rascunho (LOB) faz o SQL Server manter S na linha até o fim da
// instrução, e o lookup do índice filtrado segura S na chave dele. Na instrução única, a leitura segurava esses S
// enquanto esperava a posse ou a linha que a escrita já tinha (descarte: X na posse, depois X no rascunho e no índice
// filtrado): ciclo a cada descarte, e cada ciclo custa até o intervalo do monitor de deadlock (5 s) à escrita e à
// leitura. Agora o lote lê em instruções curtas: ids ativos pelo índice filtrado (sem lookup), resumo dos ativos pela
// chave (única instrução com LOB do rascunho, e só com o rascunho), pipeline gerido, operação pendente e base dela
// (uma tabela por instrução; a base pendente vem do rascunho pela chave, sem LOB, ativo ou não), resumo filtrado com
// a ordem já calculada, posse válida e nome do titular por último (uma tabela cada) e, depois de tudo, um corte UTC único. Página e contagem leem só as
// variáveis de tabela, com o mesmo corte. Nenhuma instrução segura lock de rascunho, posse, pipeline gerido ou
// publicação enquanto espera outra tabela.
// Não é retrato atômico: cada instrução lê dado confirmado no momento dela (READ COMMITTED). Página e contagem saem do
// mesmo resumo e do mesmo corte; posse liberada ou transferida depois da captura não é vista.
// DEADLOCK_PRIORITY LOW no pool próprio e a repetição só da 1205 continuam como rede de segurança (outras sessões).
public sealed class SqlPipelineIndex : IPipelineIndex
{
    // ApplicationName distinto = chave de pool distinta: uma sessão do índice nunca é reaproveitada por escrita.
    internal const string ApplicationName = "Orquestra.Workspace.Index";
    // Prefixo de toda instrução do índice. SET em lote vale para a sessão; por isso o pool próprio.
    internal const string SessionSettings = "SET NOCOUNT ON; SET DEADLOCK_PRIORITY LOW; SET TRANSACTION ISOLATION LEVEL READ COMMITTED;\n";
    private const int DeadlockVictim = 1205;
    private static WorkspaceException Missing() => new(503, "draft_schema_unavailable", "Rascunhos indisponíveis; aplique a migration 141_workspace_rascunhos.sql");
    private readonly WorkspaceSqlOptions options;
    private readonly PipelineIndexRetry retry;
    private readonly Func<PipelineIndexQuery, CancellationToken, Task<PipelineIndexPage>> attempt;
    private readonly Func<TimeSpan, CancellationToken, Task> wait;
    private int deadlockRetries, exhausted, expired, longestSuccess; private long backoffTicks;

    public SqlPipelineIndex(WorkspaceSqlOptions options) : this(options, PipelineIndexRetry.Default, null, null) { }
    // Testes trocam a tentativa e a espera; a política (só 1205, prazo único, cancelamento, 503) é a mesma.
    internal SqlPipelineIndex(WorkspaceSqlOptions options, PipelineIndexRetry retry, Func<PipelineIndexQuery, CancellationToken, Task<PipelineIndexPage>>? attempt, Func<TimeSpan, CancellationToken, Task>? wait)
    {
        this.options = options; this.retry = retry;
        this.attempt = attempt ?? ReadOnceAsync;
        this.wait = wait ?? ((delay, token) => Task.Delay(delay, token));
    }

    // Vítimas 1205 refeitas por esta instância (a bancada SQL mede a recuperação).
    internal int DeadlockRetries => Volatile.Read(ref deadlockRetries);
    // Diagnóstico interno (testes e bancada; nunca na resposta nem no log): por que leituras pararam em 503, quantas
    // tentativas a leitura bem-sucedida mais longa usou e quanto tempo de espera entre tentativas foi cumprido.
    internal PipelineIndexStops Stops => new(Volatile.Read(ref exhausted), Volatile.Read(ref expired), Volatile.Read(ref longestSuccess), TimeSpan.FromTicks(Interlocked.Read(ref backoffTicks)));
    internal static string ConnectionString(WorkspaceSqlOptions options) => new SqlConnectionStringBuilder(options.ConnectionString()) { ApplicationName = ApplicationName }.ConnectionString;

    public async Task<PipelineIndexPage> ReadAsync(PipelineIndexQuery query, CancellationToken ct)
    {
        // Um prazo para todas as tentativas e esperas.
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        deadline.CancelAfter(retry.Budget);
        try
        {
            for (var n = 1; ; n++)
            {
                deadline.Token.ThrowIfCancellationRequested();
                // Cada tentativa abre conexão e lista próprias: itens e total de uma vítima não sobrevivem.
                try { var page = await attempt(query, deadline.Token); Longest(n); return page; }
                catch (SqlException e) when (e.Number == DeadlockVictim && n < retry.Attempts && !deadline.IsCancellationRequested) { }
                Interlocked.Increment(ref deadlockRetries);
                var delay = retry.Backoff(n);
                await wait(delay, deadline.Token); Interlocked.Add(ref backoffTicks, delay.Ticks);
            }
        }
        // Cancelamento do cliente vence a repetição e se propaga como cancelamento.
        catch (Exception e) when (ct.IsCancellationRequested && e is OperationCanceledException or SqlException or InvalidOperationException) { throw new OperationCanceledException(ct); }
        // Prazo esgotado ou 1205 além do limite: 503 honesto, sem texto do SQL.
        catch (Exception e) when (deadline.IsCancellationRequested && e is OperationCanceledException or SqlException or InvalidOperationException) { Interlocked.Increment(ref expired); throw new DependencyUnavailableException(); }
        catch (SqlException e) when (e.Number is 208 or 207) { throw Missing(); }
        catch (SqlException e) when (e.Number == DeadlockVictim) { Interlocked.Increment(ref exhausted); throw new DependencyUnavailableException(); }
        catch (SqlException) { throw new DependencyUnavailableException(); }
        catch (InvalidOperationException) { throw new DependencyUnavailableException(); }
    }

    private void Longest(int attempts)
    {
        for (var seen = Volatile.Read(ref longestSuccess); attempts > seen; seen = Volatile.Read(ref longestSuccess))
            if (Interlocked.CompareExchange(ref longestSuccess, attempts, seen) == seen) return;
    }

    private async Task<PipelineIndexPage> ReadOnceAsync(PipelineIndexQuery query, CancellationToken ct)
    {
        await using var c = new SqlConnection(ConnectionString(options)); await c.OpenAsync(ct);
        bool managed; string names, json, managedNames, holders;
        // Esquema e collation real das colunas do rascunho, do pipeline gerido e do titular da posse: as tabelas do lote herdam a
        // mesma, então UNION, igualdade de nome e de matrícula, LIKE, filtros e ordem continuam decididos pela collation das colunas.
        await using (var schema = Command(c, "SELECT CASE WHEN OBJECT_ID('dbo.etl_workspace_rascunho','U') IS NOT NULL AND OBJECT_ID('dbo.etl_workspace_lease','U') IS NOT NULL AND OBJECT_ID('dbo.etl_workspace_versao','U') IS NOT NULL THEN 1 ELSE 0 END,CASE WHEN OBJECT_ID('dbo.etl_workspace_pipeline','U') IS NOT NULL AND OBJECT_ID('dbo.etl_workspace_publicacao','U') IS NOT NULL THEN 1 ELSE 0 END,(SELECT collation_name FROM sys.columns WHERE object_id=OBJECT_ID('dbo.etl_workspace_rascunho','U') AND name='pipeline_name'),(SELECT collation_name FROM sys.columns WHERE object_id=OBJECT_ID('dbo.etl_workspace_rascunho','U') AND name='definition_json'),(SELECT collation_name FROM sys.columns WHERE object_id=OBJECT_ID('dbo.etl_workspace_pipeline','U') AND name='pipeline_name'),(SELECT collation_name FROM sys.columns WHERE object_id=OBJECT_ID('dbo.etl_workspace_lease','U') AND name='holder_user')"))
        await using (var r = await schema.ExecuteReaderAsync(ct))
        {
            await r.ReadAsync(ct);
            if (r.GetInt32(0) != 1 || r.IsDBNull(2) || r.IsDBNull(3) || r.IsDBNull(5)) throw Missing();
            managed = r.GetInt32(1) == 1;
            if (managed && r.IsDBNull(4)) throw Missing();
            names = Collation(r.GetString(2)); json = Collation(r.GetString(3)); managedNames = managed ? Collation(r.GetString(4)) : ""; holders = Collation(r.GetString(5));
        }
        var items = new List<PipelineIndexItem>(); var total = 0;
        await using (var page = Command(c, Sql(managed, names, json, managedNames, holders), query))
        await using (var r = await page.ExecuteReaderAsync(ct))
        {
            while (await r.ReadAsync(ct)) { total = r.GetInt32(r.GetOrdinal("total")); items.Add(Item(r)); }
            // Página além do fim: o mesmo lote devolve a contagem, sobre o mesmo resumo, a mesma posse e o mesmo corte.
            if (items.Count == 0 && query.Offset > 0 && await r.NextResultAsync(ct) && await r.ReadAsync(ct)) total = r.GetInt32(0);
        }
        return new(total, query.Limit, query.Offset, items);
    }

    // Nome de collation vem do catálogo do servidor, nunca da requisição; ainda assim só entra no SQL se for um nome.
    private static string Collation(string name) => name.Length is > 0 and <= 128 && name.All(ch => char.IsAsciiLetterOrDigit(ch) || ch == '_') ? name : throw new DependencyUnavailableException();

    private static PipelineIndexItem Item(SqlDataReader r)
    {
        string? Text(string column) { var i = r.GetOrdinal(column); return r.IsDBNull(i) ? null : PipelineIndexRules.Summary(r.GetString(i)); }
        DateTime? Date(string column) { var i = r.GetOrdinal(column); return r.IsDBNull(i) ? null : DateTime.SpecifyKind(r.GetDateTime(i), DateTimeKind.Utc); }
        var draft = !r.IsDBNull(r.GetOrdinal("draft_id"));
        var published = r.GetInt32(r.GetOrdinal("has_published")) == 1;
        var active = r.GetOrdinal("is_active"); var number = r.GetOrdinal("published_number"); var revision = r.GetOrdinal("draft_revision");
        var updated = Date("updated_at");
        return new(r.GetString(r.GetOrdinal("pipeline_name")), Text("display_name"), Text("project"), Text("domain"), draft ? Text("responsavel") : null,
            draft, draft ? r.GetInt64(revision) : null, published, r.IsDBNull(number) ? null : r.GetInt32(number), r.IsDBNull(active) ? null : r.GetInt32(active) == 1,
            r.GetInt32(r.GetOrdinal("managed")) == 1, updated, updated is null ? null : draft ? "draft" : "version",
            Text("holder_user"), Text("holder_name"), Date("expires_at"));
    }

    // Publicado = cadastro legado não gerido, ou versão confirmada/base importada do pipeline gerido (mesma regra do pipeline-context).
    // Projeção em reconciliação NÃO é publicação. Resumo publicado prevalece; o rascunho preenche o que a publicação não informa.
    // Lote em instruções curtas (ver o topo): 1) ids ativos pelo índice filtrado, 2) resumo dos ativos pela chave (único
    // LOB do rascunho; FORCESEEK fixa a busca pela chave primária, a única por draft_id, e impede o índice filtrado com
    // lookup), 3) gerido: pipeline, operação pendente e base_version_id do rascunho dela pela chave (sem LOB nem estado:
    // a base publicada continua valendo enquanto a publicação está pendente), 4) resumo filtrado, com a ordem da página
    // calculada pela collation das colunas, 5) posse válida e, à parte, nome do titular, a mais perto possível da página, 6) corte UTC único e
    // 7) página e, além do fim, contagem, só sobre variáveis de tabela. Cada instrução só lê dado confirmado no momento
    // dela; nada disso é retrato atômico das fontes.
    private static string Sql(bool managed, string names, string json, string managedNames, string holders)
    {
        var managedColumns = managed
            ? """
              m.pipeline_name AS managed_name,CASE WHEN m.pipeline_name IS NULL THEN 0 ELSE 1 END AS managed,
              CASE WHEN m.pipeline_name IS NOT NULL THEN CASE WHEN v.version_id IS NULL THEN 0 ELSE 1 END WHEN p.pipeline_name IS NOT NULL THEN 1 ELSE 0 END AS has_published,
              CASE WHEN m.version_id IS NOT NULL THEN v.numero END AS published_number,
              CASE WHEN m.version_id IS NOT NULL THEN v.criada_em END AS version_created,
              CASE WHEN m.pipeline_name IS NOT NULL THEN JSON_VALUE(v.definition_json,'$.identity.displayName') END AS pub_display,
              CASE WHEN m.pipeline_name IS NOT NULL THEN JSON_VALUE(v.definition_json,'$.metadata.legacyPipeline.project_name') ELSE p.project_name END AS pub_project,
              CASE WHEN m.pipeline_name IS NOT NULL THEN JSON_VALUE(v.definition_json,'$.metadata.legacyPipeline.domain') ELSE p.domain END AS pub_domain,
              CASE WHEN m.pipeline_name IS NOT NULL THEN CASE LOWER(JSON_VALUE(v.definition_json,'$.metadata.legacyPipeline.active')) WHEN 'true' THEN 1 WHEN '1' THEN 1 WHEN 'false' THEN 0 WHEN '0' THEN 0 END ELSE CAST(p.active AS INT) END AS pub_active,
              """
            : """
              CAST(NULL AS NVARCHAR(200)) AS managed_name,0 AS managed,CASE WHEN p.pipeline_name IS NULL THEN 0 ELSE 1 END AS has_published,
              CAST(NULL AS INT) AS published_number,CAST(NULL AS DATETIME2) AS version_created,CAST(NULL AS NVARCHAR(4000)) AS pub_display,
              p.project_name AS pub_project,p.domain AS pub_domain,CAST(p.active AS INT) AS pub_active,
              """;
        var managedApply = managed
            ? """
              OUTER APPLY (SELECT TOP(1) x.pipeline_name,x.version_id,x.base_version_id FROM @gerido x WHERE x.pipeline_name=n.pipeline_name) m
              OUTER APPLY (SELECT TOP(1) x.version_id,x.numero,x.criada_em,x.definition_json FROM dbo.etl_workspace_versao x WHERE x.version_id=COALESCE(m.version_id,m.base_version_id)) v
              """
            : "";
        // Gerido em três instruções de uma tabela cada; só a operação pendente de pipeline sem versão confirmada importa,
        // porque a versão lida é COALESCE(version_id, base pendente).
        var managedReads = managed
            ? $"""
              DECLARE @gerido TABLE(pipeline_name NVARCHAR(200) COLLATE {managedNames} NOT NULL PRIMARY KEY,version_id UNIQUEIDENTIFIER NULL,pending_operation_id UNIQUEIDENTIFIER NULL,pending_draft_id UNIQUEIDENTIFIER NULL,base_version_id UNIQUEIDENTIFIER NULL);
              INSERT @gerido(pipeline_name,version_id,pending_operation_id) SELECT x.pipeline_name,x.version_id,x.pending_operation_id FROM dbo.etl_workspace_pipeline x;
              UPDATE g SET g.pending_draft_id=o.draft_id FROM @gerido g JOIN dbo.etl_workspace_publicacao o WITH(FORCESEEK) ON o.operation_id=g.pending_operation_id WHERE g.version_id IS NULL;
              UPDATE g SET g.base_version_id=x.base_version_id FROM @gerido g JOIN dbo.etl_workspace_rascunho x WITH(FORCESEEK) ON x.draft_id=g.pending_draft_id;
              """
            : "";
        // Página e contagem leem o mesmo resumo materializado, a mesma posse e o mesmo corte.
        var holder = "OUTER APPLY (SELECT TOP(1) x.holder_user,x.expires_at,x.holder_name FROM @posse x WHERE x.draft_id=r.draft_id AND x.expires_at>@corte) l";
        return $"""
            DECLARE @ativo TABLE(draft_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY);
            DECLARE @rascunho TABLE(draft_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,pipeline_name NVARCHAR(200) COLLATE {names} NOT NULL,revision BIGINT NOT NULL,responsavel NVARCHAR(100) NOT NULL,atualizado_em DATETIME2 NOT NULL,
             display NVARCHAR(4000) COLLATE {json} NULL,project NVARCHAR(4000) COLLATE {json} NULL,domain NVARCHAR(4000) COLLATE {json} NULL,INDEX IX_nome(pipeline_name));
            -- Texto do resumo não é comparado nem ordenado depois de materializado: filtros e ordem já foram decididos na origem.
            DECLARE @resumo TABLE(ordem BIGINT NOT NULL PRIMARY KEY,pipeline_name NVARCHAR(200) NOT NULL,display_name NVARCHAR(4000) NULL,project NVARCHAR(4000) NULL,domain NVARCHAR(4000) NULL,
             responsavel NVARCHAR(100) NULL,draft_id UNIQUEIDENTIFIER NULL,draft_revision BIGINT NULL,has_published INT NOT NULL,published_number INT NULL,is_active INT NULL,managed INT NOT NULL,updated_at DATETIME2 NULL);
            DECLARE @posse TABLE(draft_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,holder_user NVARCHAR(100) COLLATE {holders} NOT NULL,expires_at DATETIME2 NOT NULL,holder_name NVARCHAR(MAX) NULL);
            DECLARE @corte DATETIME2;
            INSERT @ativo(draft_id) SELECT x.draft_id FROM dbo.etl_workspace_rascunho x WHERE x.estado='ativo';
            INSERT @rascunho(draft_id,pipeline_name,revision,responsavel,atualizado_em,display,project,domain)
            SELECT x.draft_id,x.pipeline_name,x.revision,x.responsavel,x.atualizado_em,JSON_VALUE(x.definition_json,'$.identity.displayName'),
             JSON_VALUE(x.definition_json,'$.metadata.legacyPipeline.project_name'),JSON_VALUE(x.definition_json,'$.metadata.legacyPipeline.domain')
            FROM @ativo a JOIN dbo.etl_workspace_rascunho x WITH(FORCESEEK) ON x.draft_id=a.draft_id WHERE x.estado='ativo';
            {managedReads}
            WITH names AS (
             SELECT pipeline_name FROM dbo.etl_pipeline
             UNION
             SELECT pipeline_name FROM @rascunho
            ), base AS (
             SELECT
              {managedColumns}
              d.draft_id,d.revision AS draft_revision,d.responsavel,d.atualizado_em AS draft_updated,
              d.display AS draft_display,d.project AS draft_project,d.domain AS draft_domain,
              p.pipeline_name AS legacy_name,n.pipeline_name AS key_name,d.pipeline_name AS draft_name
             FROM names n
             OUTER APPLY (SELECT TOP(1) x.pipeline_name,x.project_name,x.domain,x.active FROM dbo.etl_pipeline x WHERE x.pipeline_name=n.pipeline_name) p
             OUTER APPLY (SELECT TOP(1) x.draft_id,x.pipeline_name,x.revision,x.responsavel,x.atualizado_em,x.display,x.project,x.domain FROM @rascunho x WHERE x.pipeline_name=n.pipeline_name ORDER BY x.atualizado_em DESC,x.draft_id) d
             {managedApply}
            ), summary AS (
             SELECT
              COALESCE(b.managed_name,b.legacy_name,b.draft_name,b.key_name) AS pipeline_name,
              COALESCE(NULLIF(b.pub_display,N''),NULLIF(b.draft_display,N'')) AS display_name,
              COALESCE(NULLIF(b.pub_project,N''),NULLIF(b.draft_project,N'')) AS project,
              COALESCE(NULLIF(b.pub_domain,N''),NULLIF(b.draft_domain,N'')) AS domain,
              b.responsavel,b.draft_id,b.draft_revision,b.has_published,b.published_number,b.managed,
              CASE WHEN b.has_published=1 THEN b.pub_active END AS is_active,
              CASE WHEN b.draft_id IS NOT NULL THEN b.draft_updated ELSE b.version_created END AS updated_at
             FROM base b
            )
            INSERT @resumo(ordem,pipeline_name,display_name,project,domain,responsavel,draft_id,draft_revision,has_published,published_number,is_active,managed,updated_at)
            SELECT ROW_NUMBER() OVER(ORDER BY COALESCE(r.display_name,r.pipeline_name),r.pipeline_name,r.pipeline_name COLLATE Latin1_General_BIN2),
             r.pipeline_name,r.display_name,r.project,r.domain,r.responsavel,r.draft_id,r.draft_revision,r.has_published,r.published_number,r.is_active,r.managed,r.updated_at
            FROM summary r
            WHERE (@pattern IS NULL OR r.pipeline_name LIKE @pattern OR r.display_name LIKE @pattern)
             AND (@project IS NULL OR r.project=@project)
             AND (@domain IS NULL OR r.domain=@domain)
             AND (@state='all' OR (@state='draft' AND r.draft_id IS NOT NULL) OR (@state='published' AND r.has_published=1)
              OR (@state='editing' AND r.draft_id IS NOT NULL) OR (@state='inactive' AND r.has_published=1 AND r.is_active=0));
            -- Posse e nome do titular em instruções separadas: no APPLY, a linha da posse ficava com S enquanto o usuário era esperado.
            INSERT @posse(draft_id,holder_user,expires_at) SELECT x.draft_id,x.holder_user,x.expires_at FROM dbo.etl_workspace_lease x WHERE x.expires_at>SYSUTCDATETIME();
            UPDATE p SET p.holder_name=NULLIF(LTRIM(RTRIM(CONCAT(y.primeiro_nome,' ',y.ultimo_nome))),'') FROM @posse p JOIN dbo.etl_usuario y ON y.matricula=p.holder_user;
            -- Corte único depois de todas as leituras: posse que expirou enquanto alguma instrução esperava não vale.
            SET @corte=SYSUTCDATETIME();
            SELECT COUNT(*) OVER() AS total,r.pipeline_name,r.display_name,r.project,r.domain,r.responsavel,r.draft_id,r.draft_revision,r.has_published,r.published_number,r.is_active,r.managed,r.updated_at,l.holder_user,l.holder_name,l.expires_at
            FROM @resumo r {holder}
            WHERE @state<>'editing' OR l.holder_user IS NOT NULL
            ORDER BY r.ordem OFFSET @offset ROWS FETCH NEXT @limit ROWS ONLY;
            IF @@ROWCOUNT=0 AND @offset>0
             SELECT COUNT(*) FROM @resumo r {holder} WHERE @state<>'editing' OR l.holder_user IS NOT NULL;
            """;
    }

    // CommandTimeout é só limite de segurança; o prazo da leitura inteira vem do token.
    private static SqlCommand Command(SqlConnection c, string sql) => new(SessionSettings + sql, c) { CommandTimeout = 10 };
    private static SqlCommand Command(SqlConnection c, string sql, PipelineIndexQuery query)
    {
        var cmd = Command(c, sql);
        cmd.Parameters.Add("@pattern", SqlDbType.NVarChar, 4000).Value = query.Search is null ? DBNull.Value : PipelineIndexRules.LikePattern(query.Search);
        cmd.Parameters.Add("@project", SqlDbType.NVarChar, 200).Value = (object?)query.Project ?? DBNull.Value;
        cmd.Parameters.Add("@domain", SqlDbType.NVarChar, 200).Value = (object?)query.Domain ?? DBNull.Value;
        cmd.Parameters.Add("@state", SqlDbType.VarChar, 20).Value = query.State;
        cmd.Parameters.Add("@offset", SqlDbType.Int).Value = query.Offset;
        cmd.Parameters.Add("@limit", SqlDbType.Int).Value = query.Limit;
        return cmd;
    }
}

// Repetição só da vítima de deadlock do índice, com tentativas e prazo totais limitados. O monitor de deadlock do
// SQL Server pode levar até 5 s para escolher a vítima; 10 s cobrem essa espera e a leitura refeita. A espera cresce
// por tentativa e tem parte aleatória, para leitores derrubados juntos não voltarem juntos.
internal sealed record PipelineIndexRetry(int Attempts, TimeSpan Budget, TimeSpan BaseDelay)
{
    public static readonly PipelineIndexRetry Default = new(5, TimeSpan.FromSeconds(10), TimeSpan.FromMilliseconds(50));
    public TimeSpan Backoff(int attempt) => BaseDelay * (1 << Math.Clamp(attempt - 1, 0, 6)) + BaseDelay * Random.Shared.NextDouble();
}

// Motivos de parada em 503 (1205 além das tentativas; prazo único esgotado), a maior quantidade de tentativas de uma
// leitura que deu certo e a espera entre tentativas cumprida (a cortada pelo prazo não conta). Só para testes e bancada.
internal readonly record struct PipelineIndexStops(int Exhausted, int Expired, int LongestSuccess, TimeSpan Backoff);
