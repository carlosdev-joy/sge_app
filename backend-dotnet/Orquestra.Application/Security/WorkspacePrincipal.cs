namespace Orquestra.Application.Security;

public sealed record WorkspacePrincipal(string Matricula, string Perfil, IReadOnlySet<string> Permissions);

public sealed class SessionRejectedException(int statusCode, string code, string detail) : Exception(detail)
{
    public int StatusCode { get; } = statusCode;
    public string Code { get; } = code;
}

public sealed class DependencyUnavailableException() : Exception("Dependência do workspace indisponível");

public interface ISessionRepository
{
    Task<WorkspacePrincipal?> FindValidAsync(string tokenHash, CancellationToken cancellationToken);
    Task<WorkspacePrincipal> LoadAsync(string matricula, CancellationToken cancellationToken);
    Task CheckReadyAsync(CancellationToken cancellationToken);
}

public interface IBasicIdentityClient
{
    Task<WorkspacePrincipal> AuthenticateAsync(string authorization, CancellationToken cancellationToken);
}
