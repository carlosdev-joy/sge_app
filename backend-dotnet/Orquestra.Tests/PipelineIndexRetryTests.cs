using System.Diagnostics;
using System.Net;
using System.Reflection;
using System.Text.Json;
using Microsoft.Data.SqlClient;
using Orquestra.Application.Drafts;
using Orquestra.Application.Security;
using Orquestra.Infrastructure.Drafts;
using Orquestra.Infrastructure.Security;
using Xunit;

namespace Orquestra.Tests;

// Correção EOC-F2 do deadlock do índice: pool e prioridade próprios; só a vítima 1205 é repetida, do zero, dentro de
// um prazo único; o cancelamento do cliente vence; esgotar é 503 sem texto do SQL. A tentativa é dublê, a política é a real.
public sealed class PipelineIndexRetryTests
{
    private static readonly WorkspaceSqlOptions Options = new("sql.invalid,1433", "OrquestraIndice", "app_workspace", "senha-sintetica", true);
    private static readonly PipelineIndexQuery Query = new("pubc", null, null, "all", 50, 100);
    private static readonly PipelineIndexRetry Fast = new(5, TimeSpan.FromSeconds(30), TimeSpan.FromMilliseconds(5));

    [Fact]
    public void IndexHasItsOwnPoolAndLowPriorityWhileWritersKeepTheirs()
    {
        var writer = new SqlConnectionStringBuilder(Options.ConnectionString());
        var index = new SqlConnectionStringBuilder(SqlPipelineIndex.ConnectionString(Options));
        // O pool do SqlClient é por cadeia de conexão: o nome da aplicação separa os pools; o resto é idêntico.
        Assert.Equal("Orquestra.Workspace", writer.ApplicationName); Assert.Equal("Orquestra.Workspace.Index", index.ApplicationName);
        Assert.True(index.Pooling); Assert.NotEqual(writer.ConnectionString, index.ConnectionString);
        Assert.Equal(writer.ConnectionString, new SqlConnectionStringBuilder(index.ConnectionString) { ApplicationName = writer.ApplicationName }.ConnectionString);
        // Só a sessão do índice cede o deadlock; leitura confirmada, sem dica que leia sujo ou pule linha travada.
        Assert.StartsWith("SET NOCOUNT ON; SET DEADLOCK_PRIORITY LOW; SET TRANSACTION ISOLATION LEVEL READ COMMITTED;", SqlPipelineIndex.SessionSettings);
        foreach (var forbidden in new[] { "NOLOCK", "READPAST", "SNAPSHOT", "UNCOMMITTED" }) Assert.DoesNotContain(forbidden, SqlPipelineIndex.SessionSettings, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("DEADLOCK", Options.ConnectionString(), StringComparison.OrdinalIgnoreCase);
        // Padrão: tentativas e prazo limitados.
        Assert.Equal(5, PipelineIndexRetry.Default.Attempts); Assert.Equal(TimeSpan.FromSeconds(10), PipelineIndexRetry.Default.Budget);
    }

    [Fact]
    public async Task DeadlockVictimRepeatsTheWholeAttemptAndReturnsOnlyTheLastResult()
    {
        // O dublê substitui a tentativa inteira (ReadOnceAsync): prova que a política repete a tentativa do zero e devolve
        // só o resultado da última. Não prova o descarte de linhas já lidas do SqlDataReader: isso vem da lista e do total
        // locais de ReadOnceAsync numa conexão nova (guarda estática no pytest) e da integração com SQL real.
        var calls = new List<(PipelineIndexQuery Query, CancellationToken Token)>(); var waits = new List<TimeSpan>();
        var final = new PipelineIndexPage(2, 50, 100, [Item("PUBC"), Item("PUBD")]);
        var index = new SqlPipelineIndex(Options, Fast, async (query, token) =>
        {
            calls.Add((query, token)); await Task.Yield();
            if (calls.Count <= 2) throw SqlErrors.Create(1205);
            return final;
        }, (delay, _) => { waits.Add(delay); return Task.CompletedTask; });
        var page = await index.ReadAsync(Query, default);
        Assert.Same(final, page); Assert.Equal(2, page.Total); Assert.Equal(new[] { "PUBC", "PUBD" }, page.Items.Select(i => i.PipelineName));
        // Toda tentativa refaz a mesma consulta, sob o mesmo prazo ainda vivo.
        Assert.Equal(3, calls.Count); Assert.All(calls, call => Assert.Equal(Query, call.Query));
        Assert.All(calls, call => { Assert.True(call.Token.CanBeCanceled); Assert.False(call.Token.IsCancellationRequested); Assert.Equal(calls[0].Token, call.Token); });
        Assert.Equal(2, waits.Count); Assert.InRange(waits[0], Fast.BaseDelay, 2 * Fast.BaseDelay); Assert.True(waits[1] >= 2 * Fast.BaseDelay && waits[1] > waits[0]);
        Assert.Equal(2, index.DeadlockRetries);
        // Diagnóstico: nenhuma parada em 503, a leitura usou 3 tentativas e a espera somada é a das duas pausas.
        Assert.Equal(new PipelineIndexStops(0, 0, 3, waits[0] + waits[1]), index.Stops);
    }

    [Theory]
    [InlineData(1222)] // espera por lock esgotada
    [InlineData(-2)]   // tempo do comando esgotado
    [InlineData(2627)] // chave duplicada
    [InlineData(4060)] // banco indisponível
    [InlineData(208)]  // esquema ausente
    public async Task OnlyTheDeadlockVictimIsRetried(int number)
    {
        var calls = 0; var waits = 0;
        var index = new SqlPipelineIndex(Options, Fast, (_, _) => { calls++; throw SqlErrors.Create(number); }, (_, _) => { waits++; return Task.CompletedTask; });
        var error = await Record.ExceptionAsync(() => index.ReadAsync(Query, default));
        if (number == 208) Assert.Equal("draft_schema_unavailable", Assert.IsType<WorkspaceException>(error).Code);
        else Assert.IsType<DependencyUnavailableException>(error);
        Assert.Equal(1, calls); Assert.Equal(0, waits); Assert.Equal(0, index.DeadlockRetries);
        // Outros erros não contam como 1205 esgotada nem como prazo.
        Assert.Equal(default, index.Stops);
    }

    [Fact]
    public async Task FailuresOutsideSqlAreNotRetried()
    {
        foreach (var failure in new Exception[] { new InvalidOperationException("pool"), new WorkspaceException(503, "draft_schema_unavailable", "Rascunhos indisponíveis"), new DependencyUnavailableException() })
        {
            var calls = 0;
            var index = new SqlPipelineIndex(Options, Fast, (_, _) => { calls++; throw failure; }, (_, _) => Task.CompletedTask);
            var error = await Record.ExceptionAsync(() => index.ReadAsync(Query, default));
            Assert.Equal(1, calls);
            if (failure is InvalidOperationException) Assert.IsType<DependencyUnavailableException>(error); else Assert.Same(failure, error);
        }
    }

    [Fact]
    public async Task ExhaustedDeadlockRetriesAreAnHonest503WithoutSqlText()
    {
        const string victim = "Transaction (Process ID 61) was deadlocked on lock resources with another process and has been chosen as the deadlock victim. Rerun the transaction.";
        var calls = 0; var waits = 0;
        var index = new SqlPipelineIndex(Options, Fast, (_, _) => { calls++; throw SqlErrors.Create(1205, victim); }, (_, _) => { waits++; return Task.CompletedTask; });
        await Assert.ThrowsAsync<DependencyUnavailableException>(() => index.ReadAsync(Query, default));
        Assert.Equal(Fast.Attempts, calls); Assert.Equal(Fast.Attempts - 1, waits); Assert.Equal(Fast.Attempts - 1, index.DeadlockRetries);
        // Diagnóstico: parou por tentativas (não por prazo) e nenhuma leitura deu certo.
        Assert.Equal(1, index.Stops.Exhausted); Assert.Equal(0, index.Stops.Expired); Assert.Equal(0, index.Stops.LongestSuccess); Assert.True(index.Stops.Backoff > TimeSpan.Zero);
        // Pela API: 503 genérico, sem texto, número nem processo do SQL.
        using var app = new IndexTestApp("tela_pipelines", true, index); using var client = app.CreateClient();
        client.DefaultRequestHeaders.Add("Authorization", "Bearer synthetic");
        var response = await client.GetAsync("/workspace/pipeline-index?search=pubc");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        var body = await response.Content.ReadAsStringAsync();
        Assert.Equal("dependency_unavailable", JsonDocument.Parse(body).RootElement.GetProperty("code").GetString());
        foreach (var leaked in new[] { "deadlock", "1205", "Process ID", "victim", "Transaction" }) Assert.DoesNotContain(leaked, body, StringComparison.OrdinalIgnoreCase);
        Assert.Equal(2 * Fast.Attempts, calls); Assert.Equal(2, index.Stops.Exhausted); Assert.Equal(0, index.Stops.Expired);
    }

    [Fact]
    public async Task OneBudgetCoversEveryAttemptAndWaitAndEndsIn503()
    {
        // Espera longa depois da 1ª vítima: o prazo único corta a espera e não há nova tentativa.
        var calls = 0;
        var waiting = new SqlPipelineIndex(Options, new(5, TimeSpan.FromMilliseconds(300), TimeSpan.FromMinutes(1)), (_, _) => { calls++; throw SqlErrors.Create(1205); }, null);
        var clock = Stopwatch.StartNew();
        await Assert.ThrowsAsync<DependencyUnavailableException>(() => waiting.ReadAsync(Query, default));
        Assert.Equal(1, calls); Assert.InRange(clock.Elapsed, TimeSpan.FromMilliseconds(200), TimeSpan.FromSeconds(10));
        // Diagnóstico: parada por prazo, não por tentativas; a espera cortada pelo prazo não conta como cumprida.
        Assert.Equal(new PipelineIndexStops(0, 1, 0, TimeSpan.Zero), waiting.Stops);
        // Tentativa presa (lock ou rede): o mesmo prazo a cancela; o cliente não cancelou, então é 503, não cancelamento.
        var stuck = new SqlPipelineIndex(Options, new(5, TimeSpan.FromMilliseconds(300), TimeSpan.FromMilliseconds(1)), async (_, token) => { await Task.Delay(Timeout.Infinite, token); return null!; }, null);
        clock.Restart();
        await Assert.ThrowsAsync<DependencyUnavailableException>(() => stuck.ReadAsync(Query, default));
        Assert.InRange(clock.Elapsed, TimeSpan.FromMilliseconds(200), TimeSpan.FromSeconds(10));
        Assert.Equal(new PipelineIndexStops(0, 1, 0, TimeSpan.Zero), stuck.Stops);
        // Driver que traduz o cancelamento do prazo em SqlException também termina em 503.
        var aborted = new SqlPipelineIndex(Options, new(5, TimeSpan.FromMilliseconds(300), TimeSpan.FromMilliseconds(1)), async (_, token) => { try { await Task.Delay(Timeout.Infinite, token); } catch (OperationCanceledException) { throw SqlErrors.Create(0, "Operation cancelled by user."); } return null!; }, null);
        await Assert.ThrowsAsync<DependencyUnavailableException>(() => aborted.ReadAsync(Query, default));
        Assert.Equal(new PipelineIndexStops(0, 1, 0, TimeSpan.Zero), aborted.Stops);
    }

    [Fact]
    public async Task ClientCancellationWinsInTheAttemptInTheWaitAndAfterAVictim()
    {
        // Durante a tentativa.
        using (var cancel = new CancellationTokenSource())
        {
            var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously); var calls = 0;
            var index = new SqlPipelineIndex(Options, Fast, async (_, token) => { calls++; started.TrySetResult(); await Task.Delay(Timeout.Infinite, token); return null!; }, (_, _) => throw new InvalidOperationException("sem espera"));
            var read = index.ReadAsync(Query, cancel.Token);
            await started.Task.WaitAsync(TimeSpan.FromSeconds(10)); cancel.Cancel();
            Assert.Equal(cancel.Token, (await Assert.ThrowsAnyAsync<OperationCanceledException>(() => read)).CancellationToken); Assert.Equal(1, calls);
        }
        // Durante a espera entre tentativas: nenhuma tentativa nova.
        using (var cancel = new CancellationTokenSource())
        {
            var waiting = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously); var calls = 0;
            var index = new SqlPipelineIndex(Options, Fast, (_, _) => { calls++; throw SqlErrors.Create(1205); }, async (_, token) => { waiting.TrySetResult(); await Task.Delay(Timeout.Infinite, token); });
            var read = index.ReadAsync(Query, cancel.Token);
            await waiting.Task.WaitAsync(TimeSpan.FromSeconds(10)); cancel.Cancel();
            Assert.Equal(cancel.Token, (await Assert.ThrowsAnyAsync<OperationCanceledException>(() => read)).CancellationToken); Assert.Equal(1, calls);
        }
        // Vítima que chega depois do cancelamento (o driver aborta o comando): não espera nem repete.
        using (var cancel = new CancellationTokenSource())
        {
            var calls = 0; var waits = 0;
            var index = new SqlPipelineIndex(Options, Fast, (_, _) => { calls++; cancel.Cancel(); throw SqlErrors.Create(1205); }, (_, _) => { waits++; return Task.CompletedTask; });
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => index.ReadAsync(Query, cancel.Token));
            Assert.Equal(1, calls); Assert.Equal(0, waits); Assert.Equal(0, index.DeadlockRetries);
            // Cancelamento do cliente não é parada em 503.
            Assert.Equal(default, index.Stops);
        }
        // Já cancelado: nenhuma tentativa.
        using (var cancel = new CancellationTokenSource())
        {
            var calls = 0; cancel.Cancel();
            var index = new SqlPipelineIndex(Options, Fast, (_, _) => { calls++; return Task.FromResult(new PipelineIndexPage(0, 50, 0, [])); }, null);
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => index.ReadAsync(Query, cancel.Token));
            Assert.Equal(0, calls);
        }
    }

    private static PipelineIndexItem Item(string name) => new(name, null, null, null, null, true, 1, true, null, true, false, null, null, null, null, null);
}

// SqlException não tem construtor público: a fábrica interna do driver monta o erro (somente nos testes).
internal static class SqlErrors
{
    public static SqlException Create(int number, string message = "erro sintético")
    {
        const BindingFlags Hidden = BindingFlags.NonPublic | BindingFlags.Instance;
        var constructor = typeof(SqlError).GetConstructors(Hidden).Where(c => c.GetParameters()[0].ParameterType == typeof(int)).OrderBy(c => c.GetParameters().Length).First();
        object? Argument(ParameterInfo p, int i) => i == 0 ? number : p.ParameterType == typeof(byte) ? (byte)13 : p.ParameterType == typeof(string) ? (p.Name == "errorMessage" ? message : "sintético") : Default(p);
        var error = (SqlError)constructor.Invoke(constructor.GetParameters().Select(Argument).ToArray());
        var errors = (SqlErrorCollection)typeof(SqlErrorCollection).GetConstructor(Hidden, Type.EmptyTypes)!.Invoke(null);
        typeof(SqlErrorCollection).GetMethod("Add", Hidden)!.Invoke(errors, [error]);
        var factory = typeof(SqlException).GetMethods(BindingFlags.NonPublic | BindingFlags.Static).Where(m => m.Name == "CreateException" && m.GetParameters()[0].ParameterType == typeof(SqlErrorCollection)).OrderBy(m => m.GetParameters().Length).First();
        var exception = (SqlException)factory.Invoke(null, factory.GetParameters().Select((p, i) => i == 0 ? errors : p.ParameterType == typeof(string) ? "16.00.0000" : Default(p)).ToArray())!;
        Assert.Equal(number, exception.Number); Assert.Contains(message, exception.Message);
        return exception;
    }
    private static object? Default(ParameterInfo p) => p.HasDefaultValue ? p.DefaultValue : p.ParameterType.IsValueType ? Activator.CreateInstance(p.ParameterType) : null;
}
