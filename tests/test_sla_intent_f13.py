"""Falhas depois de persistir não apagam a intenção nem reenviam incertos."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sla_intent', ROOT / 'dags/utils/sla_intent.py')
sla = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sla)


def test_enqueue_preserves_card_and_no_secret_or_network():
    hook = Mock()
    card = dict(title='Risco', facts=[dict(title='Pipeline', value='próprio')])
    sla.enqueue(hook, 'fixture', 'próprio', 'PREDICT', 5, 1, card)
    document = json.loads(hook.run.call_args.kwargs['parameters'][5])
    assert document['card'] == card
    assert document['destinationRef'] == 'TEAMS_WEBHOOK_URL_CVP'


def test_invalid_event_never_writes():
    hook = Mock()
    with pytest.raises(ValueError):
        sla.enqueue(hook, 'fixture', 'own', 'SUCCESS', 5, 1, {})
    hook.run.assert_not_called()


@pytest.mark.parametrize('outcome', ['Accepted', 'Failed', 'Unknown', 'bogus', TimeoutError()])
def test_claim_committed_before_sender_and_uncertainty_is_not_pending(outcome):
    hook = Mock()
    document = dict(schemaVersion=1, destinationRef='TEAMS_WEBHOOK_URL_CVP', card={})
    hook.get_first.side_effect = [(8, json.dumps(document)), (8,), None]

    def sender(fence):
        assert hook.run.call_count == 2  # recuperação + claim durável
        assert fence()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    sla.drain(hook, sender)
    finish = hook.run.call_args_list[2]
    expected = outcome if outcome in ('Accepted', 'Failed', 'Unknown') else 'Unknown'
    assert finish.kwargs['parameters'][0] == expected
    assert 'lease_until>SYSUTCDATETIME()' in finish.args[0]


def test_empty_pending_never_calls_provider():
    hook = Mock()
    hook.get_first.return_value = None
    sender = Mock()
    assert sla.drain(hook, sender) == 0
    sender.assert_not_called()


def test_missing_or_changed_destination_never_falls_back():
    hook = Mock()
    hook.get_first.side_effect = [(8, json.dumps(dict(schemaVersion=1,
        destinationRef='other', card={}))), None]
    sender = Mock()
    sla.drain(hook, sender)
    sender.assert_not_called()
    assert hook.run.call_args_list[2].kwargs['parameters'][0] == 'Failed'


def test_finish_uses_one_lease_decision_for_intent_and_attempt():
    hook = Mock()
    hook.get_first.side_effect = [(8, json.dumps(dict(schemaVersion=1,
        destinationRef='TEAMS_WEBHOOK_URL_CVP', card={}))), None]
    sla.drain(hook, lambda **kwargs: 'Accepted')
    sql = hook.run.call_args_list[2].args[0]
    assert sql.count('lease_until>SYSUTCDATETIME()') == 1
    assert 'OUTPUT INSERTED.id,DELETED.claim_token INTO @finished' in sql
    assert 'JOIN @finished' in sql
