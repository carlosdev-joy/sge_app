using System.Net;
using System.Text.Json;
using Orquestra.Application.Security;

namespace Orquestra.Infrastructure.Security;

public sealed class LegacyBasicIdentityClient(HttpClient client) : IBasicIdentityClient
{
    public async Task<WorkspacePrincipal> AuthenticateAsync(string authorization, CancellationToken cancellationToken)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(5));
        var dependencyCancellation = deadline.Token;
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Get, "me");
            request.Headers.TryAddWithoutValidation("Authorization", authorization);
            using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, dependencyCancellation);
            if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
                throw new SessionRejectedException((int)response.StatusCode, "session_denied", "Sessão não autorizada");
            if (!response.IsSuccessStatusCode || response.Content.Headers.ContentLength > 32768) throw new DependencyUnavailableException();
            // Limite real também para resposta chunked; nunca encaminhar o body/detail legado ao usuário.
            await using var stream = await response.Content.ReadAsStreamAsync(dependencyCancellation);
            using var buffer = new MemoryStream();
            var bytes = new byte[4096]; int count;
            while ((count = await stream.ReadAsync(bytes, dependencyCancellation)) > 0)
            {
                if (buffer.Length + count > 32768) throw new DependencyUnavailableException();
                buffer.Write(bytes, 0, count);
            }
            using var document = JsonDocument.Parse(buffer.ToArray());
            var root = document.RootElement;
            var matricula = root.GetProperty("matricula").GetString();
            var perfil = root.GetProperty("perfil").GetString();
            if (string.IsNullOrWhiteSpace(matricula) || matricula.Length > 20 || string.IsNullOrWhiteSpace(perfil) || perfil.Length > 30)
                throw new DependencyUnavailableException();
            var permissions = new HashSet<string>(StringComparer.Ordinal);
            foreach (var resource in root.GetProperty("permissoes").EnumerateArray())
            {
                var value = resource.GetString();
                if (string.IsNullOrEmpty(value) || value.Length > 50) throw new DependencyUnavailableException();
                permissions.Add(value);
            }
            return new(matricula, perfil, permissions);
        }
        catch (HttpRequestException) { throw new DependencyUnavailableException(); }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested) { throw new DependencyUnavailableException(); }
        catch (JsonException) { throw new DependencyUnavailableException(); }
        catch (KeyNotFoundException) { throw new DependencyUnavailableException(); }
        catch (InvalidOperationException) { throw new DependencyUnavailableException(); }
    }
}
