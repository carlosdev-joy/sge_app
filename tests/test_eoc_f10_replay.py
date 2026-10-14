from contextlib import contextmanager
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from services import alert_replay as r


def harness(monkeypatch, *, schema=True, eligible=True, audit=True):
    conn = Mock();cur = Mock();cur.execute.return_value = cur
    cur.fetchone.side_effect = [(1,1,1), (200,1000,8) if schema else (None,None,None),
                               ('fixture',) if eligible else None]
    cur.rowcount = 1 if audit else 0
    @contextmanager
    def own():
        yield conn, cur
    monkeypatch.setattr(r, 'bounded_conn', own)
    return conn, cur


def test_replay_audit_and_state_single_commit(monkeypatch):
    conn, cur = harness(monkeypatch)
    assert r.replay_dry_run(str(uuid4()),actor='qa',reason='mock fixture rejected',expected_sequence=1)['dryRun']
    sql = [call.args[0] for call in cur.execute.call_args_list]
    assert 'UPDLOCK' in sql[2] and "('Failed','DryRun')" in sql[2] and 'e.dry_run=1' in sql[2]
    assert 'replay_at IS NULL' in sql[3] and 'SYSUTCDATETIME' in sql[3]
    assert cur.execute.call_args_list[3].args[1][:2] == ('qa','mock fixture rejected')
    assert "state='Pending'" in sql[4]
    conn.commit.assert_called_once()


@pytest.mark.parametrize('args,status', [({'actor':''},422),({'reason':None},422),
    ({'reason':'🚩'*251},422),({'actor':'a\nsecret'},422),
    ({'expected_sequence':True},409),({'expected_sequence':4},409),({'expected_sequence':0},409)])
def test_invalid_replay_no_db(monkeypatch,args,status):
    conn,_ = harness(monkeypatch)
    values=dict(actor='qa',reason='fixture',expected_sequence=1);values.update(args)
    with pytest.raises(HTTPException) as e:r.replay_dry_run(str(uuid4()),**values)
    assert e.value.status_code==status;conn.commit.assert_not_called()


@pytest.mark.parametrize('kwargs,status', [({'schema':False},503),({'eligible':False},409),({'audit':False},409)])
def test_conflict_or_schema_cannot_commit(monkeypatch,kwargs,status):
    conn,_ = harness(monkeypatch,**kwargs)
    with pytest.raises(HTTPException) as e:
        r.replay_dry_run(str(uuid4()),actor='qa',reason='fixture',expected_sequence=1)
    assert e.value.status_code==status;conn.commit.assert_not_called()
