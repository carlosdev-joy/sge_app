"""Mesmo transporte stdlib, socket em RAM: nenhum DNS/TLS/rede externa."""
import io
import json
import logging
from http.client import HTTPSConnection

import httpx
import pytest

from services import alert_channels as c


class InMemorySocket:
    def __init__(self, status=202):
        self.sent = []
        self.response = io.BytesIO(f'HTTP/1.1 {status} Fixture\r\nContent-Length: 0\r\n\r\n'.encode())
        self.closed = False

    def sendall(self, value):
        self.sent.append(value)

    def makefile(self, *args, **kwargs):
        return self.response

    def close(self):
        self.closed = True


@pytest.mark.parametrize('status,outcome', [(202, 'Accepted'), (302, 'Failed'), (429, 'Failed')])
def test_signed_workflow_uses_exact_path_without_library_log_or_global_changes(monkeypatch, caplog, capsys, status, outcome):
    url = 'https://fixture.environment.api.powerplatform.com:443/powerautomate/automations/direct/cu/20/workflows/test/triggers/manual/paths/invoke?sig=fixture_signature%2B%2F&sv=1.0'
    target = c.Target('teamsChannel', url)
    monkeypatch.setattr(c, 'resolve', lambda *_, **kwargs: (target, {'event': 'failure', 'pipeline': '__eoc_f10_fixture', 'run': '__eoc_f10_run'}))
    socket = InMemorySocket(status)
    monkeypatch.setattr(HTTPSConnection, 'connect', lambda self: setattr(self, 'sock', socket))
    monkeypatch.setattr(HTTPSConnection, 'debuglevel', 1)
    logger = logging.getLogger('httpx')
    handlers, filters = tuple(logger.handlers), tuple(logger.filters)
    with caplog.at_level(logging.DEBUG):
        result = c.deliver(None, 'fixture', dry_run=False, authorized_test_fingerprint=target.fingerprint)
        with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as other:
            other.get('https://ordinary.example.invalid/context')
    assert result.outcome == outcome
    assert tuple(logger.handlers) == handlers and tuple(logger.filters) == filters
    assert 'ordinary.example.invalid/context' in caplog.text
    output = capsys.readouterr()
    assert all('fixture_signature' not in value for value in (caplog.text, output.out, output.err, repr(result)))
    request = b''.join(socket.sent)
    assert b'POST /powerautomate/automations/direct/cu/20/workflows/test/triggers/manual/paths/invoke?sig=fixture_signature%2B%2F&sv=1.0 HTTP/1.1' in request
    assert json.loads(socket.sent[-1])['attachments'][0]['content']['type'] == 'AdaptiveCard'
    assert socket.closed


@pytest.mark.parametrize('value', ['https://environment.api.powerplatform.com.evil.test/t', 'https://a.powerplatform.com/t', 'https://environment.api.powerplatform.com/t'])
def test_workflows_namespace_does_not_accept_lookalike(value):
    assert not c.valid_webhook(value)
