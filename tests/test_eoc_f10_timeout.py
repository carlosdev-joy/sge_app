from unittest.mock import Mock
from services import alert_channels as c


def test_teams_timeout_unknown_no_retry(monkeypatch):
    target=c.Target('teamsChannel','https://fixture.webhook.office.com/test')
    monkeypatch.setattr(c,'resolve',lambda *_:(target,dict(event='failure',pipeline='fixture',run='fixture')))
    client=Mock();client.request.side_effect=TimeoutError('fixture-private-webhook')
    monkeypatch.setattr(c,'HTTPSConnection',Mock(return_value=client))
    result=c.deliver(None,'fixture',dry_run=False,authorized_test_fingerprint=target.fingerprint)
    assert result==c.Result('Unknown','transport_uncertain')
    assert client.request.call_count==1
    client.close.assert_called_once()
