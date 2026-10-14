"""Contrato de alertas: preview sem transporte e identidade imutável por run."""
import copy
import json
from uuid import uuid4
import pytest
from fastapi import HTTPException
from services import pipeline_alerts as svc


def configured():
    return dict(schemaVersion=1, events=['success','warning','failure'], recipients=['fixture@example.invalid'],
                email=True, teamsPersonal=True, teamsChannel={'groupId': 1}, attemptMode='terminal')


def test_preview_three_destinations_and_channel_once():
    value = configured()
    value['recipients'] *= 2
    result = svc.preview(value,'failure')
    assert result['count'] == 3
    assert [d['channel'] for d in result['deliveries']] == ['email','teamsPersonal','teamsChannel']
    assert result['simulation'] and result['dispatch'] is False
    assert 'fixture@' not in json.dumps(result)
    value['recipients'].append('other@example.invalid')
    result = svc.preview(value,'success')
    assert result['count'] == 5
    assert len([d for d in result['deliveries'] if d['channel']=='teamsChannel']) == 1


def test_unselected_event_and_new_default_no_deliveries():
    value = configured(); value['events'] = ['failure']
    assert svc.preview(value,'success')['count'] == 0
    value.update(email=False, teamsPersonal=False, teamsChannel=None, recipients=[])
    assert svc.preview(value,'failure')['count'] == 0


@pytest.mark.parametrize('field,value', [
    ('schemaVersion',True), ('schemaVersion',2), ('events',['warning','warning']),
    ('events',[{}]), ('events','failure'), ('email',1), ('teamsPersonal','true'),
    ('recipients',[None]), ('recipients',['victim@example.invalid\r\nBcc:other@example.invalid']),
    ('recipients',['x@']), ('recipients',['x@example.invalid?token=secret']),
    ('recipients',[]), ('recipients',['x@example.invalid']*101),
    ('teamsChannel',{'webhook':'https://provider.invalid/secret'}),
    ('teamsChannel',{'groupId':True}), ('teamsChannel',{'groupId':-1}),
    ('teamsChannel',{'groupId':2147483648}), ('attemptMode','retry'),
])
def test_invalid_policy_fails_without_echo(field,value):
    obj = configured(); obj[field] = value
    with pytest.raises(HTTPException) as exc: svc.preview(obj,'failure')
    assert exc.value.status_code == 422
    assert exc.value.detail['code']=='alert_policy_invalid'
    assert 'example.invalid' not in json.dumps(exc.value.detail)


def test_unknown_fields_preserved_in_source_and_block_activation():
    value = configured(); value['future'] = {'protectedRef':str(uuid4())}
    before = copy.deepcopy(value)
    with pytest.raises(HTTPException): svc.policy(value)
    assert value == before


def test_policy_revision_original_after_new_publication(monkeypatch):
    from services import workspace_operations
    version = str(uuid4()); original = {'alertPolicy':configured()}
    published = copy.deepcopy(original); published['alertPolicy']['recipients']=['new@example.invalid']
    monkeypatch.setattr(workspace_operations,'execution_version',lambda pipeline,run:dict(versionId=version,definition=original))
    first = svc.policy_for_run('Fixture','run-1')
    new = svc.captured_policy(published,str(uuid4()))
    second = svc.policy_for_run('Fixture','run-1')
    assert first == second and first['policyRevision'] != new['policyRevision']
    one = svc.event_identity('Fixture','run-1',1,'failure',first['policyRevision'])
    two = svc.event_identity('Fixture','run-1',2,'failure',second['policyRevision'])
    assert one != two
    assert one == svc.event_identity('Fixture','run-1',1,'failure',first['policyRevision'])
    assert svc.delivery_identity(one,'email','ref:1') != svc.delivery_identity(one,'email','ref:2')
    assert svc.delivery_identity(one,'email','ref:1') != svc.delivery_identity(two,'email','ref:1')


@pytest.mark.parametrize('generation',[None,0,-1,True,'1',2147483648])
def test_missing_or_invalid_generation_never_inferred(generation):
    with pytest.raises(HTTPException):svc.event_identity('Fixture','run',generation,'warning','revision')


def test_legacy_no_retroactive_policy():
    assert svc.captured_policy({},str(uuid4())) == {'mode':'legacy','policyRevision':None,'policy':None}
    caps = svc.capabilities()
    assert all(not entry['available'] for entry in caps.values())
    assert caps['result']['source'] and caps['result']['cause']


def test_run_unbound_fails_closed(monkeypatch):
    from services import workspace_operations
    monkeypatch.setattr(workspace_operations,'execution_version',lambda *args:None)
    with pytest.raises(HTTPException) as exc:svc.policy_for_run('Fixture','old')
    assert exc.value.status_code==409


def test_preview_endpoint_uses_guarded_draft(monkeypatch):
    from routers import workspace_publication as routes
    from services import workspace_advisory
    monkeypatch.setattr(routes,'ENABLED',lambda:True)
    calls=[]
    def guard(*args):
        calls.append(args)
        return {'alertPolicy':configured()}
    monkeypatch.setattr(workspace_advisory,'guarded_draft',guard)
    result=routes.workspace_alerts_preview(uuid4(),{'expectedRevision':7,'fence':2,'event':'failure'},{},'Bearer fixture')
    assert result['count']==3 and len(calls)==1
    assert calls[0][1]['expectedRevision']==7


@pytest.mark.parametrize('status',[401,403,409,503])
def test_endpoint_propagates_guard_failure(monkeypatch,status):
    from routers import workspace_publication as routes
    from services import workspace_advisory
    monkeypatch.setattr(routes,'ENABLED',lambda:True)
    def deny(*args):raise HTTPException(status,'gate')
    monkeypatch.setattr(workspace_advisory,'guarded_draft',deny)
    monkeypatch.setattr(svc,'preview',lambda *args:pytest.fail('No preview after denied gate'))
    with pytest.raises(HTTPException) as exc:routes.workspace_alerts_preview(uuid4(),{}, {},'Bearer fixture')
    assert exc.value.status_code==status


@pytest.mark.parametrize('address', ['.x@example.invalid', 'x.@example.invalid', 'x..y@example.invalid', 'x@'+'a'*64+'.invalid'])
def test_invalid_email_structure(address):
    value=configured();value['recipients']=[address]
    with pytest.raises(HTTPException):svc.policy(value)


def test_disabled_default_is_independent_and_legacy_is_not_null_policy():
    first=svc.disabled_policy();first['events'].append('failure')
    assert svc.disabled_policy()['events']==[]
    assert svc.preview(svc.disabled_policy(),'failure')['count']==0
    with pytest.raises(HTTPException):svc.captured_policy({'alertPolicy':None},str(uuid4()))


def observed():
    return dict(schemaVersion=1,pipeline='Fixture',run='workspace__fixture',cycleGeneration=1,
                event='failure',policyRevision=svc.captured_policy({'alertPolicy':configured()},str(uuid4()))['policyRevision'],
                source='pipeline-result',sourceStatus='FAILED',sourceAt='2026-10-14T12:00:00Z',receivedAt='2026-10-14T12:00:01+00:00')


def test_event_envelope_retains_source_times_and_generation():
    value=observed();before=copy.deepcopy(value);first=svc.event_contract(value)
    value['cycleGeneration']=2;second=svc.event_contract(value)
    assert first['sourceAt']==before['sourceAt'] and first['receivedAt']==before['receivedAt']
    assert first['eventKey']!=second['eventKey']
    assert svc.event_contract(before)==first
    assert 'priority' not in first and 'deliveryState' not in first


@pytest.mark.parametrize('field,value', [
    ('schemaVersion',True),('pipeline','x\n'),('pipeline','😀'*101),('run',''),
    ('source',''),('cycleGeneration',None),('cycleGeneration',True),
    ('sourceStatus','UP_FOR_RETRY'),('sourceStatus','SUCCESS'),('sourceStatus',[]),
    ('sourceAt',None),('sourceAt','2026-10-14 12:00:00'),('sourceAt','2026-10-14T12:00:00-03:00'),
    ('receivedAt','2026-13-99T12:00:00Z'),('policyRevision','current'),
])
def test_event_rejects_transient_or_unproven_identity(field,value):
    envelope=observed();envelope[field]=value
    with pytest.raises(HTTPException) as exc:svc.event_contract(envelope)
    assert exc.value.status_code==422


def test_event_warning_does_not_follow_transport_failure():
    envelope=observed();envelope.update(event='warning',sourceStatus='WARNING')
    assert svc.event_contract(envelope)['event']=='warning'
    envelope['sourceStatus']='DELIVERY_FAILED'
    with pytest.raises(HTTPException):svc.event_contract(envelope)
    assert svc.capabilities()['result']['available'] is False  # envelope válido não certifica a fonte


def test_run_snapshot_failure_does_not_leak(monkeypatch):
    from services import workspace_operations
    def broken(*args):raise RuntimeError('connection password=private')
    monkeypatch.setattr(workspace_operations,'execution_version',broken)
    with pytest.raises(HTTPException) as exc:svc.policy_for_run('Fixture','run')
    assert exc.value.status_code==503 and 'private' not in json.dumps(exc.value.detail)


def test_policy_publication_preserves_legacy_and_custom_task_configuration():
    from services.workspace_publication import materialize,PublicationBlocked
    from tests.test_workspace_publication_f4 import flow,LAYOUT
    definition=flow();definition['alertPolicy']=configured()
    definition['metadata']['legacyPipeline']['notify_on_failure']=True
    before=copy.deepcopy(definition);projection=materialize(definition,LAYOUT,{})
    assert projection['etl_pipeline'][0]['notify_on_failure'] is True
    assert definition==before and 'alertPolicy' not in projection['etl_pipeline'][0]
    definition['alertPolicy']['teamsChannel']={'webhook':'https://private.invalid/token'}
    with pytest.raises(PublicationBlocked) as exc:materialize(definition,LAYOUT,{})
    assert exc.value.code=='alert_policy_invalid'


def test_preview_rejects_unknown_body_and_explicit_null_policy(monkeypatch):
    from routers import workspace_publication as routes
    from services import workspace_advisory
    monkeypatch.setattr(routes,'ENABLED',lambda:True)
    monkeypatch.setattr(workspace_advisory,'guarded_draft',lambda *args:{})
    for body in ({'policy':None,'event':'failure'},{'event':'failure','send':True}):
        with pytest.raises(HTTPException) as exc:routes.workspace_alerts_preview(uuid4(),body,{},'Bearer fixture')
        assert exc.value.status_code==422
