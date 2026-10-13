using System.Data;
using Microsoft.Data.SqlClient;
using Orquestra.Application.Drafts;
using Orquestra.Application.Security;
using Orquestra.Infrastructure.Security;

namespace Orquestra.Infrastructure.Drafts;

// F2: uma linha por pipeline, igualdade decidida no SQL pela collation real das colunas pipeline_name
// (UNION + OUTER APPLY TOP(1)); nenhum agrupamento por nome em memória. Leitura de instrução única em READ COMMITTED,
// só dado confirmado (sem NOLOCK, READPAST nem snapshot): espera a escrita em andamento e ainda pode fechar ciclo com
// ela (S no rascunho/índice do rascunho × X na posse/linha do rascunho das transações de autoria e publicação).
// Por isso o índice roda em DEADLOCK_PRIORITY LOW, num pool próprio, e é sempre a vítima diante de uma escrita
// (NORMAL), que então conclui sem 409 induzido pela leitura. A vítima (1205, e só ela) refaz a leitura inteira.
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
    private int deadlockRetries;

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
                try { return await attempt(query, deadline.Token); }
                catch (SqlException e) when (e.Number == DeadlockVictim && n < retry.Attempts && !deadline.IsCancellationRequested) { }
                Interlocked.Increment(ref deadlockRetries);
                await wait(retry.Backoff(n), deadline.Token);
            }
        }
        // Cancelamento do cliente vence a repetição e se propaga como cancelamento.
        catch (Exception e) when (ct.IsCancellationRequested && e is OperationCanceledException or SqlException or InvalidOperationException) { throw new OperationCanceledException(ct); }
        // Prazo esgotado ou 1205 além do limite: 503 honesto, sem texto do SQL.
        catch (Exception e) when (deadline.IsCancellationRequested && e is OperationCanceledException or SqlException or InvalidOperationException) { throw new DependencyUnavailableException(); }
        catch (SqlException e) when (e.Number is 208 or 207) { throw Missing(); }
        catch (SqlException) { throw new DependencyUnavailableException(); }
        catch (InvalidOperationException) { throw new DependencyUnavailableException(); }
    }

    private async Task<PipelineIndexPage> ReadOnceAsync(PipelineIndexQuery query, CancellationToken ct)
    {
        await using var c = new SqlConnection(ConnectionString(options)); await c.OpenAsync(ct);
        bool managed;
        await using (var schema = Command(c, "SELECT CASE WHEN OBJECT_ID('dbo.etl_workspace_rascunho','U') IS NOT NULL AND OBJECT_ID('dbo.etl_workspace_lease','U') IS NOT NULL AND OBJECT_ID('dbo.etl_workspace_versao','U') IS NOT NULL THEN 1 ELSE 0 END,CASE WHEN OBJECT_ID('dbo.etl_workspace_pipeline','U') IS NOT NULL AND OBJECT_ID('dbo.etl_workspace_publicacao','U') IS NOT NULL THEN 1 ELSE 0 END"))
        await using (var r = await schema.ExecuteReaderAsync(ct))
        {
            await r.ReadAsync(ct);
            if (r.GetInt32(0) != 1) throw Missing();
            managed = r.GetInt32(1) == 1;
        }
        var items = new List<PipelineIndexItem>(); var total = 0;
        await using (var page = Command(c, Sql(managed, count: false), query))
        await using (var r = await page.ExecuteReaderAsync(ct))
            while (await r.ReadAsync(ct)) { total = r.GetInt32(r.GetOrdinal("total")); items.Add(Item(r)); }
        if (items.Count == 0 && query.Offset > 0)
        {
            // Página além do fim: total informado por uma contagem própria, sem itens.
            await using var counter = Command(c, Sql(managed, count: true), query);
            total = (int)(await counter.ExecuteScalarAsync(ct))!;
        }
        return new(total, query.Limit, query.Offset, items);
    }

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
    private static string Sql(bool managed, bool count)
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
              OUTER APPLY (SELECT TOP(1) x.pipeline_name,x.version_id,x.pending_operation_id FROM dbo.etl_workspace_pipeline x WHERE x.pipeline_name=n.pipeline_name) m
              OUTER APPLY (SELECT TOP(1) pr.base_version_id FROM dbo.etl_workspace_publicacao o JOIN dbo.etl_workspace_rascunho pr ON pr.draft_id=o.draft_id WHERE o.operation_id=m.pending_operation_id) pend
              OUTER APPLY (SELECT TOP(1) x.version_id,x.numero,x.criada_em,x.definition_json FROM dbo.etl_workspace_versao x WHERE x.version_id=COALESCE(m.version_id,pend.base_version_id)) v
              """
            : "";
        var select = count
            ? "SELECT COUNT(*) FROM summary r"
            : "SELECT COUNT(*) OVER() AS total,r.pipeline_name,r.display_name,r.project,r.domain,r.responsavel,r.draft_id,r.draft_revision,r.has_published,r.published_number,r.is_active,r.managed,r.updated_at,r.holder_user,r.holder_name,r.expires_at FROM summary r";
        var page = count ? "" : "ORDER BY COALESCE(r.display_name,r.pipeline_name),r.pipeline_name,r.pipeline_name COLLATE Latin1_General_BIN2 OFFSET @offset ROWS FETCH NEXT @limit ROWS ONLY";
        return $"""
            WITH names AS (
             SELECT pipeline_name FROM dbo.etl_pipeline
             UNION
             SELECT pipeline_name FROM dbo.etl_workspace_rascunho WHERE estado='ativo'
            ), base AS (
             SELECT
              d.draft_id,d.revision AS draft_revision,d.responsavel,d.atualizado_em AS draft_updated,
              JSON_VALUE(d.definition_json,'$.identity.displayName') AS draft_display,
              JSON_VALUE(d.definition_json,'$.metadata.legacyPipeline.project_name') AS draft_project,
              JSON_VALUE(d.definition_json,'$.metadata.legacyPipeline.domain') AS draft_domain,
              p.pipeline_name AS legacy_name,n.pipeline_name AS key_name,d.pipeline_name AS draft_name,
              {managedColumns}
              l.holder_user,l.expires_at,u.holder_name
             FROM names n
             OUTER APPLY (SELECT TOP(1) x.pipeline_name,x.project_name,x.domain,x.active FROM dbo.etl_pipeline x WHERE x.pipeline_name=n.pipeline_name) p
             OUTER APPLY (SELECT TOP(1) x.draft_id,x.pipeline_name,x.revision,x.responsavel,x.atualizado_em,x.definition_json FROM dbo.etl_workspace_rascunho x WHERE x.pipeline_name=n.pipeline_name AND x.estado='ativo' ORDER BY x.atualizado_em DESC,x.draft_id) d
             {managedApply}
             OUTER APPLY (SELECT TOP(1) x.holder_user,x.expires_at FROM dbo.etl_workspace_lease x WHERE x.draft_id=d.draft_id AND x.expires_at>SYSUTCDATETIME()) l
             OUTER APPLY (SELECT TOP(1) NULLIF(LTRIM(RTRIM(CONCAT(x.primeiro_nome,' ',x.ultimo_nome))),'') AS holder_name FROM dbo.etl_usuario x WHERE x.matricula=l.holder_user) u
            ), summary AS (
             SELECT
              COALESCE(b.managed_name,b.legacy_name,b.draft_name,b.key_name) AS pipeline_name,
              COALESCE(NULLIF(b.pub_display,N''),NULLIF(b.draft_display,N'')) AS display_name,
              COALESCE(NULLIF(b.pub_project,N''),NULLIF(b.draft_project,N'')) AS project,
              COALESCE(NULLIF(b.pub_domain,N''),NULLIF(b.draft_domain,N'')) AS domain,
              b.responsavel,b.draft_id,b.draft_revision,b.has_published,b.published_number,b.managed,
              CASE WHEN b.has_published=1 THEN b.pub_active END AS is_active,
              CASE WHEN b.draft_id IS NOT NULL THEN b.draft_updated ELSE b.version_created END AS updated_at,
              b.holder_user,b.holder_name,b.expires_at
             FROM base b
            )
            {select}
            WHERE (@pattern IS NULL OR r.pipeline_name LIKE @pattern OR r.display_name LIKE @pattern)
             AND (@project IS NULL OR r.project=@project)
             AND (@domain IS NULL OR r.domain=@domain)
             AND (@state='all' OR (@state='draft' AND r.draft_id IS NOT NULL) OR (@state='published' AND r.has_published=1)
              OR (@state='editing' AND r.holder_user IS NOT NULL) OR (@state='inactive' AND r.has_published=1 AND r.is_active=0))
            {page};
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
