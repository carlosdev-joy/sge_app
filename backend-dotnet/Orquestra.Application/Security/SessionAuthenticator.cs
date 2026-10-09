using System.Security.Cryptography;
using System.Text;

namespace Orquestra.Application.Security;

public sealed class SessionAuthenticator(ISessionRepository sessions, IBasicIdentityClient basic)
{
    public async Task<WorkspacePrincipal> AuthenticateAsync(string? authorization, CancellationToken cancellationToken)
    {
        if (string.IsNullOrEmpty(authorization) || authorization.Length > 4096 || authorization.Contains('\r') || authorization.Contains('\n'))
            throw InvalidSession();
        if (authorization.StartsWith("Bearer ", StringComparison.Ordinal))
        {
            var token = authorization[7..]; // Não trim: os mesmos bytes usados pelo legado.
            if (token.Length == 0) throw InvalidSession();
            var hash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(token)));
            return (await sessions.FindValidAsync(hash, cancellationToken) ?? throw InvalidSession()) with { SessionHash = hash };
        }
        if (authorization.StartsWith("Basic ", StringComparison.Ordinal))
        {
            try
            {
                var decoded = Encoding.UTF8.GetString(Convert.FromBase64String(authorization[6..]));
                if (!decoded.Contains(':') || string.IsNullOrWhiteSpace(decoded.Split(':', 2)[0])) throw InvalidSession();
            }
            catch (FormatException) { throw InvalidSession(); }
            var identity = await basic.AuthenticateAsync(authorization, cancellationToken);
            // O legado pode devolver permissões vazias quando o SQL falha. Recarregar
            // o RBAC garante indisponibilidade explícita e usuário/permissões atuais.
            return await sessions.LoadAsync(identity.Matricula, cancellationToken);
        }
        throw InvalidSession();
    }

    private static SessionRejectedException InvalidSession() => new(401, "session_invalid", "Sessão expirada ou inválida");
}
