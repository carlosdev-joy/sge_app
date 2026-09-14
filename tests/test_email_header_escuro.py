"""Header ORQ rasterizado: identidade fora da inversão CSS do Outlook."""
import hashlib
import re
from email import policy
from email.parser import BytesParser
from pathlib import Path
import pytest
from services import email_mime as api
from tests.test_email_identidade_orq import worker

ROOT = Path(__file__).resolve().parents[1]
CID = 'orq-header@orquestra'

@pytest.mark.parametrize('module', [api, worker])
def test_header_inline_preserva_assinatura_textual_e_anexo(module):
    body = '<img src="CID:orq-header@orquestra" alt="ORQ — Plataforma de Orquestração"><p>Status: INFO</p>'
    msg = BytesParser(policy=policy.default).parsebytes(module.montar_mensagem(
        'a@example.com', ['b@example.com'], 'Teste', body, html=True,
        anexo_nome='dados.csv', anexo_bytes=b'coluna\n1'))
    images = [p for p in msg.walk() if p.get_content_type() == 'image/png']
    assert len(images) == 1
    assert images[0]['Content-ID'] == f'<{CID}>'
    assert images[0].get_payload(decode=True) == (ROOT/'api/services/assets/orq-email-header.png').read_bytes()
    plain = next(p for p in msg.walk() if p.get_content_type() == 'text/plain').get_content()
    assert 'ORQ — Plataforma de Orquestração' in plain and 'Status: INFO' in plain
    assert msg.get_payload(1).get_payload(decode=True) == b'coluna\n1'


def test_migration_115_preserva_personalizados_e_corpo_da_114():
    old_sql = (ROOT/'sql/migrations/114_email_identidade_orq.sql').read_text()
    old = old_sql.split("SET corpo = N'", 1)[1].split("',\n               atualizado_em", 1)[0].replace("''", "'")
    sql = (ROOT/'sql/migrations/115_email_header_modo_escuro.sql').read_text()
    digest = hashlib.sha256(old.encode('utf-16-le')).hexdigest().upper()
    assert sql.count(digest) == 2
    body = sql.split("SET corpo = N'", 1)[1].split("',\n               atualizado_em", 1)[0].replace("''", "'")
    assert body == (ROOT/'docs/branding/orq-email-modelo.html').read_text()
    assert body[body.index('  <tr>\n    <td bgcolor="#F26B00"'):] == old[old.index('  <tr>\n    <td bgcolor="#F26B00"'):]
    assert 'src="cid:orq-header@orquestra"' in body and 'alt="ORQ — Plataforma' in body
    assert 'max-width:600px;height:auto' in body
    assert '<v:' not in body and 'linear-gradient' not in body
    assert "WHERE nome = N'Aviso de fim de carga'" in sql.split('UPDATE dbo.etl_email_modelo', 1)[1]


def test_header_asset_igual_em_todos_os_runtimes():
    data = [(ROOT/p).read_bytes() for p in ['api/services/assets/orq-email-header.png', 'dags/utils/assets/orq-email-header.png', 'ui-react/public/images/orq/email-header.png']]
    assert data[0] == data[1] == data[2]
    assert len(data[0]) < 150_000
