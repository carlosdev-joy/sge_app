using System.Data;
using Microsoft.Data.SqlClient;
using Orquestra.Application.Security;

namespace Orquestra.Infrastructure.Security;

public sealed record WorkspaceSqlOptions(string Server, string Database, string User, string Password, bool TrustServerCertificate = false)
{
    public string ConnectionString()
    {
        if (new[] { Server, Database, User, Password }.Any(string.IsNullOrWhiteSpace)) throw new DependencyUnavailableException();
        return new SqlConnectionStringBuilder
        {
            DataSource = Server, InitialCatalog = Database, UserID = User, Password = Password,
            Encrypt = SqlConnectionEncryptOption.Mandatory, TrustServerCertificate = TrustServerCertificate,
            ConnectTimeout = 5, ApplicationName = "Orquestra.Workspace", PersistSecurityInfo = false
        }.ConnectionString;
    }
    // Redige representação textual; estas opções não devem ser serializadas.
    public override string ToString() => "WorkspaceSqlOptions [redigido]";
}

public sealed class SqlSessionRepository(WorkspaceSqlOptions options) : ISessionRepository
{
    private static SqlCommand Command(SqlConnection connection, string text) => new(text, connection) { CommandTimeout = 5 };

    public async Task<WorkspacePrincipal?> FindValidAsync(string tokenHash, CancellationToken cancellationToken)
    {
        try
        {
            await using var connection = new SqlConnection(options.ConnectionString());
            await connection.OpenAsync(cancellationToken);
            await using var command = Command(connection, """
                SELECT COALESCE(u.matricula, s.matricula), COALESCE(u.perfil_nome, 'consulta'), u.ativo
                FROM dbo.etl_sessao s LEFT JOIN dbo.etl_usuario u ON u.matricula = s.matricula
                WHERE s.token_hash = @hash AND s.expira_em > GETDATE()
                """);
            command.Parameters.Add("@hash", SqlDbType.Char, 64).Value = tokenHash;
            string matricula; string perfil;
            await using (var reader = await command.ExecuteReaderAsync(cancellationToken))
            {
                if (!await reader.ReadAsync(cancellationToken)) return null;
                matricula = reader.GetString(0); perfil = reader.GetString(1);
                if (!reader.IsDBNull(2) && !reader.GetBoolean(2))
                    throw new SessionRejectedException(403, "user_inactive", "Usuário desativado no ORQUESTRA");
            }
            return await LoadPermissionsAsync(connection, matricula, perfil, cancellationToken);
        }
        catch (SqlException) { throw new DependencyUnavailableException(); }
        catch (InvalidOperationException) { throw new DependencyUnavailableException(); }
    }

    public async Task<WorkspacePrincipal> LoadAsync(string matricula, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(matricula) || matricula.Length > 20)
            throw new SessionRejectedException(401, "session_invalid", "Sessão expirada ou inválida");
        try
        {
            await using var connection = new SqlConnection(options.ConnectionString());
            await connection.OpenAsync(cancellationToken);
            await using var command = Command(connection,
                "SELECT matricula, perfil_nome, ativo FROM dbo.etl_usuario WHERE matricula = @matricula");
            command.Parameters.Add("@matricula", SqlDbType.VarChar, 20).Value = matricula;
            var perfil = "consulta";
            await using (var reader = await command.ExecuteReaderAsync(cancellationToken))
            {
                if (await reader.ReadAsync(cancellationToken))
                {
                    matricula = reader.GetString(0); perfil = reader.GetString(1);
                    if (!reader.GetBoolean(2))
                        throw new SessionRejectedException(403, "user_inactive", "Usuário desativado no ORQUESTRA");
                }
            }
            return await LoadPermissionsAsync(connection, matricula, perfil, cancellationToken);
        }
        catch (SqlException) { throw new DependencyUnavailableException(); }
        catch (InvalidOperationException) { throw new DependencyUnavailableException(); }
    }

    private static async Task<WorkspacePrincipal> LoadPermissionsAsync(SqlConnection connection, string matricula,
        string perfil, CancellationToken cancellationToken)
    {
        var permissions = new HashSet<string>(StringComparer.Ordinal);
        await using var profileCommand = Command(connection, "SELECT recurso FROM dbo.etl_perfil_permissao WHERE perfil_nome = @perfil");
        profileCommand.Parameters.Add("@perfil", SqlDbType.VarChar, 30).Value = perfil;
        await using (var reader = await profileCommand.ExecuteReaderAsync(cancellationToken))
            while (await reader.ReadAsync(cancellationToken)) permissions.Add(reader.GetString(0));

        // SELECT direto distingue tabela ausente (208) de acesso negado (229).
        // OBJECT_ID sozinho não distingue ausência de invisibilidade de metadata.
        try
        {
            await using var extras = Command(connection,
                "SELECT recurso FROM dbo.etl_usuario_permissao WHERE matricula = @matricula");
            extras.Parameters.Add("@matricula", SqlDbType.VarChar, 20).Value = matricula;
            await using var reader = await extras.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken)) permissions.Add(reader.GetString(0));
        }
        catch (SqlException exception) when (exception.Number == 208) { }
        return new(matricula, perfil, permissions);
    }

    public async Task CheckReadyAsync(CancellationToken cancellationToken)
    {
        try
        {
            await using var connection = new SqlConnection(options.ConnectionString());
            await connection.OpenAsync(cancellationToken);
            await using var command = Command(connection, """
                SELECT TOP 0 s.token_hash, s.matricula, s.expira_em, u.perfil_nome, u.ativo, p.recurso
                FROM dbo.etl_sessao s CROSS JOIN dbo.etl_usuario u CROSS JOIN dbo.etl_perfil_permissao p
                """);
            await using (var reader = await command.ExecuteReaderAsync(cancellationToken)) { }
            try
            {
                await using var extras = Command(connection, "SELECT TOP 0 matricula, recurso FROM dbo.etl_usuario_permissao");
                await using var reader = await extras.ExecuteReaderAsync(cancellationToken);
            }
            catch (SqlException exception) when (exception.Number == 208) { }
        }
        catch (SqlException) { throw new DependencyUnavailableException(); }
        catch (InvalidOperationException) { throw new DependencyUnavailableException(); }
    }
}
