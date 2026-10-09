using System.Net;
using Orquestra.Infrastructure.Security;
using Orquestra.Application.Security;
using Xunit;

namespace Orquestra.Tests;

public sealed class LegacyBasicTests
{
    [Fact]
    public async Task DeadlineIncludesResponseBodyAfterHeaders()
    {
        using var http = new HttpClient(new HangingBodyHandler()) { BaseAddress = new Uri("http://legacy.invalid/") };
        var request = new LegacyBasicIdentityClient(http).AuthenticateAsync("Basic synthetic", default);
        await Assert.ThrowsAsync<DependencyUnavailableException>(() => request.WaitAsync(TimeSpan.FromSeconds(8)));
    }

    private sealed class HangingBodyHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StreamContent(new HangingStream()) });
    }

    private sealed class HangingStream : Stream
    {
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            return 0;
        }
        public override void Flush() => throw new NotSupportedException();
        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }

    [Fact]
    public async Task PermissionUnionFromLegacyIsPreservedAndHeaderNotReturned()
    {
        var handler = new Stub(HttpStatusCode.OK, """{"matricula":"SYNTHETIC","perfil":"consulta","permissoes":["tela_pipelines","tela_jobs","tela_pipelines"]}""");
        using var http = new HttpClient(handler) { BaseAddress = new Uri("http://legacy.invalid/") };
        var principal = await new LegacyBasicIdentityClient(http).AuthenticateAsync("Basic c3ludGhldGljOnRlc3Q=", default);
        Assert.Equal(2, principal.Permissions.Count); Assert.Equal("/me", handler.Path);
        Assert.Equal("Basic c3ludGhldGljOnRlc3Q=", handler.Authorization);
    }

    [Theory]
    [InlineData(401)] [InlineData(403)]
    public async Task LegacyRejectionPreservesStatusWithoutForwardingBody(int code)
    {
        using var http = new HttpClient(new Stub((HttpStatusCode)code, "internal-secret")) { BaseAddress = new Uri("http://legacy.invalid/") };
        var failure = await Assert.ThrowsAsync<SessionRejectedException>(() => new LegacyBasicIdentityClient(http).AuthenticateAsync("Basic synthetic", default));
        Assert.Equal(code, failure.StatusCode); Assert.DoesNotContain("internal-secret", failure.Message);
    }

    [Theory]
    [InlineData(500, "internal-secret")] [InlineData(302, "redirect")]
    [InlineData(200, "{}")] [InlineData(200, "not-json")]
    [InlineData(200, "{\"matricula\":\"S\",\"perfil\":\"consulta\",\"permissoes\":null}")]
    public async Task BadDependencyFailsClosed(int code, string body)
    {
        using var http = new HttpClient(new Stub((HttpStatusCode)code, body)) { BaseAddress = new Uri("http://legacy.invalid/") };
        await Assert.ThrowsAsync<DependencyUnavailableException>(() => new LegacyBasicIdentityClient(http).AuthenticateAsync("Basic synthetic", default));
    }

    private sealed class Stub(HttpStatusCode status, string body) : HttpMessageHandler
    {
        public string? Path { get; private set; }
        public string? Authorization { get; private set; }
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Path = request.RequestUri?.AbsolutePath;
            Authorization = request.Headers.GetValues("Authorization").Single();
            return Task.FromResult(new HttpResponseMessage(status) { Content = new StringContent(body) });
        }
    }
}
