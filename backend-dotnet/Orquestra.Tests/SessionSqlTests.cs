using Microsoft.Data.SqlClient;
using Orquestra.Application.Security;
using Orquestra.Infrastructure.Security;
using Xunit;

namespace Orquestra.Tests;

// Opt-in: cria e remove apenas banco sintético próprio, nunca o database servido.
public sealed class SqlFactAttribute : FactAttribute
{
    public SqlFactAttribute()
    {
        if (Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_PASSWORD") is null)
            Skip = "Integração SQL requer bancada autorizada e WORKSPACE_TEST_SQL_PASSWORD";
    }
}

public sealed class SessionSqlTests
{
    [SqlFact]
    public async Task LegacySessionAndRbacUseLiveSqlClockAndCurrentPermissions()
    {
        var database = "OrquestraF1Test_" + Guid.NewGuid().ToString("N");
        var login = "OrquestraF1Login_" + Guid.NewGuid().ToString("N");
        var password = Guid.NewGuid().ToString("N") + "aA1!";
        var options = new WorkspaceSqlOptions(
            Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_SERVER") ?? "127.0.0.1,1433",
            database, Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_USER") ?? "sa",
            Environment.GetEnvironmentVariable("WORKSPACE_TEST_SQL_PASSWORD")!, true);
        await using var master = new SqlConnection((options with { Database = "master" }).ConnectionString());
        await master.OpenAsync();
        var created = false;
        var loginCreated = false;
        try
        {
            await Execute(master, $"CREATE DATABASE [{database}] COLLATE SQL_Latin1_General_CP1_CI_AS");
            created = true;
            await Execute(master, $"CREATE LOGIN [{login}] WITH PASSWORD = '{password}', CHECK_POLICY = ON");
            loginCreated = true;
            await using (var connection = new SqlConnection(options.ConnectionString()))
            {
                await connection.OpenAsync();
                await Execute(connection, """
                    CREATE TABLE dbo.etl_sessao(token_hash char(64) PRIMARY KEY, matricula varchar(20) NOT NULL, expira_em datetime NOT NULL);
                    CREATE TABLE dbo.etl_usuario(matricula varchar(20) PRIMARY KEY, perfil_nome varchar(30) NOT NULL, ativo bit NOT NULL);
                    CREATE TABLE dbo.etl_perfil_permissao(perfil_nome varchar(30) NOT NULL, recurso varchar(50) NOT NULL);
                    CREATE TABLE dbo.etl_usuario_permissao(matricula varchar(20) NOT NULL, recurso varchar(50) NOT NULL);
                    INSERT dbo.etl_usuario VALUES ('SYNTHETIC','consulta',1),('INACTIVE','consulta',0),('EMPTY','admin',1);
                    INSERT dbo.etl_perfil_permissao VALUES ('consulta','tela_pipelines');
                    INSERT dbo.etl_usuario_permissao VALUES ('SYNTHETIC','tela_jobs'),('SYNTHETIC','tela_pipelines');
                    INSERT dbo.etl_sessao VALUES
                        (REPLICATE('a',64),'synthetic',DATEADD(hour,1,GETDATE())),
                        (REPLICATE('b',64),'SYNTHETIC',DATEADD(second,-1,GETDATE())),
                        (REPLICATE('c',64),'INACTIVE',DATEADD(hour,1,GETDATE())),
                        (REPLICATE('d',64),'UNKNOWN',DATEADD(hour,1,GETDATE())),
                        (REPLICATE('e',64),'EMPTY',DATEADD(hour,1,GETDATE()));
                    """);
                var repository = new SqlSessionRepository(options);
                await repository.CheckReadyAsync(default);
                var principal = await repository.FindValidAsync(new string('a',64), default);
                Assert.NotNull(principal);
                Assert.Equal("consulta", principal.Perfil);
                Assert.Equal("SYNTHETIC", principal.Matricula);
                Assert.Equal(2, principal.Permissions.Count);
                Assert.Contains("tela_jobs", principal.Permissions);
                Assert.Null(await repository.FindValidAsync(new string('b',64), default));
                Assert.Null(await repository.FindValidAsync(new string('f',64), default));
                Assert.Equal(403, (await Assert.ThrowsAsync<SessionRejectedException>(() => repository.FindValidAsync(new string('c',64), default))).StatusCode);
                Assert.Equal("consulta", (await repository.FindValidAsync(new string('d',64), default))!.Perfil);
                Assert.Empty((await repository.FindValidAsync(new string('e',64), default))!.Permissions);
                Assert.Equal(403, (await Assert.ThrowsAsync<SessionRejectedException>(() => repository.LoadAsync("INACTIVE", default))).StatusCode);
                Assert.Contains("tela_jobs", (await repository.LoadAsync("synthetic", default)).Permissions);
                await Execute(connection, $"CREATE USER [{login}] FOR LOGIN [{login}]; GRANT SELECT ON dbo.etl_sessao TO [{login}]; GRANT SELECT ON dbo.etl_usuario TO [{login}]; GRANT SELECT ON dbo.etl_perfil_permissao TO [{login}]");
                var restricted = new SqlSessionRepository(options with { User = login, Password = password });
                await Assert.ThrowsAsync<DependencyUnavailableException>(() => restricted.CheckReadyAsync(default));
                await Assert.ThrowsAsync<DependencyUnavailableException>(() => restricted.LoadAsync("SYNTHETIC", default));
                await Execute(connection, $"GRANT SELECT ON dbo.etl_usuario_permissao TO [{login}]");
                await restricted.CheckReadyAsync(default);
                Assert.Contains("tela_jobs", (await restricted.LoadAsync("SYNTHETIC", default)).Permissions);
                await using (var readonlyConnection = new SqlConnection((options with { User = login, Password = password }).ConnectionString()))
                {
                    await readonlyConnection.OpenAsync();
                    Assert.Equal(229, (await Assert.ThrowsAsync<SqlException>(() => Execute(readonlyConnection, "UPDATE dbo.etl_usuario SET ativo=0 WHERE matricula='SYNTHETIC'"))).Number);
                }
                await Execute(connection, "DELETE dbo.etl_usuario_permissao WHERE recurso='tela_jobs'");
                Assert.DoesNotContain("tela_jobs", (await repository.FindValidAsync(new string('a',64), default))!.Permissions);
                await Execute(connection, "DELETE dbo.etl_sessao WHERE token_hash=REPLICATE('a',64)");
                Assert.Null(await repository.FindValidAsync(new string('a',64), default));
                await Execute(connection, "DROP TABLE dbo.etl_usuario_permissao");
                Assert.Contains("tela_pipelines", (await repository.LoadAsync("SYNTHETIC", default)).Permissions);
                await restricted.CheckReadyAsync(default);
                await Execute(connection, "CREATE TABLE dbo.etl_usuario_permissao(matricula varchar(20))");
                await Assert.ThrowsAsync<DependencyUnavailableException>(() => repository.LoadAsync("SYNTHETIC", default));
                await Execute(connection, "DROP TABLE dbo.etl_perfil_permissao");
                await Assert.ThrowsAsync<DependencyUnavailableException>(() => repository.CheckReadyAsync(default));
            }
        }
        finally
        {
            SqlConnection.ClearAllPools();
            if (created)
                await Execute(master, $"ALTER DATABASE [{database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{database}]");
            if (loginCreated) await Execute(master, $"DROP LOGIN [{login}]");
        }
    }

    private static async Task Execute(SqlConnection connection, string sql)
    {
        await using var command = new SqlCommand(sql, connection) { CommandTimeout = 30 };
        await command.ExecuteNonQueryAsync();
    }
}
