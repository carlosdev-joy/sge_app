"""Identidade ORQ: logo CID offline, anexo preservado e migration protegida."""
import email.policy
import hashlib
import inspect
import re
import sys
from email.parser import BytesParser
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))
from services import email_mime as api
from utils import email_envio as worker

ROOT=Path(__file__).resolve().parents[1]
CID='orq-logo@orquestra'

@pytest.mark.parametrize('module',[api,worker])
@pytest.mark.parametrize('scheme',['cid','CID'])
def test_logo_incorporado_sem_dependencia_externa_e_anexo_preservado(module,scheme):
    raw=module.montar_mensagem('origem@example.com',['destino@example.com'],'ORQ',
        f'<h1>ORQ</h1><img src="{scheme}:{CID}" alt="ORQ"><p>Resultado</p>',html=True,
        anexo_nome='resultado.csv',anexo_bytes=b'a;b\n1;2')
    msg=BytesParser(policy=email.policy.default).parsebytes(raw)
    assert msg.get_content_type()=='multipart/mixed'
    alternative=msg.get_payload(0)
    assert alternative.get_content_type()=='multipart/alternative'
    related=alternative.get_payload(1)
    assert related.get_content_type()=='multipart/related'
    html=related.get_payload(0)
    assert f'{scheme}:{CID}' in html.get_content()
    image=related.get_payload(1)
    assert image.get_content_type()=='image/png'
    assert image['Content-ID']==f'<{CID}>'
    assert image.get_content_disposition()=='inline'
    assert image.get_payload(decode=True)==(ROOT/'api/services/assets/orq-email-logo.png').read_bytes()
    assert msg.get_payload(1).get_payload(decode=True)==b'a;b\n1;2'
    assert 'ORQ' in alternative.get_payload(0).get_content()
    assert len(raw)<100_000

@pytest.mark.parametrize('module',[api,worker])
@pytest.mark.parametrize('html,body',[(False,f'cid:{CID}'),(True,'<p>Modelo próprio</p>'),(True,'<img src="cid:outro">')])
def test_nao_altera_modelos_sem_o_logo_reservado(module,html,body):
    msg=BytesParser(policy=email.policy.default).parsebytes(module.montar_mensagem('a@example.com',['b@example.com'],'s',body,html=html))
    assert not any(p.get_content_maintype()=='image' for p in msg.walk())


def test_assets_e_montagem_iguais_no_worker_api_e_previa():
    paths=['api/services/assets/orq-email-logo.png','dags/utils/assets/orq-email-logo.png','ui-react/public/images/orq/email-logo.png']
    assert len({hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})==1
    assert inspect.getsource(api.montar_mensagem)==inspect.getsource(worker.montar_mensagem)


def corpo_antigo(number):
    s=(ROOT/f'sql/migrations/{number}_email_modelo_header.sql').read_text()
    return s.split("SET corpo = N'",1)[1].split("',\n               atualizado_em",1)[0].replace("''", "'")


def test_migration_so_atualiza_modelo_original_e_repete_guarda():
    s=(ROOT/'sql/migrations/114_email_identidade_orq.sql').read_text()
    old=corpo_antigo('113')
    digest=hashlib.sha256(old.encode('utf-16-le')).hexdigest().upper()
    assert s.count(digest)==2
    update=s.split('UPDATE dbo.etl_email_modelo',1)[1]
    assert "WHERE nome = N'Aviso de fim de carga'" in update
    assert "HASHBYTES('SHA2_256', corpo)" in update
    assert "OBJECT_ID('dbo.etl_email_modelo', 'U')" in s


def test_modelo_compativel_com_email_preserva_marcadores():
    s=(ROOT/'sql/migrations/114_email_identidade_orq.sql').read_text()
    body=s.split("SET corpo = N'",1)[1].split("',\n               atualizado_em",1)[0].replace("''", "'")
    assert len(body)<api.LIMITE_CORPO
    assert 'bgcolor="#04143C"' in body
    assert f'src="cid:{CID}"' in body
    assert 'ORQUESTRA' not in body and 'Gestão de Pipelines' not in body
    assert 'Plataforma de Orquestração de Dados, Processos e Inteligência' in body
    for marker in ['pipeline','data','status','linhas','inicio','duracao','odate','job','execution_id']:
        assert '{'+marker+'}' in body
    assert '<v:' not in body and 'linear-gradient' not in body and '<script' not in body
    assert 'height="4"' in body
    assert not re.search(r'<(?:div|img)[^>]*filter\s*:',body)
