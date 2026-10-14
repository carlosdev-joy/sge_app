"""Leitura exata do contrato F16. Não importa, publica ou resolve latest."""
import json

from fastapi import HTTPException

TABLES = (
    'etl_malha_versionamento', 'etl_malha_versao', 'etl_malha_versao_membro',
    'etl_malha_rascunho', 'etl_malha_corrida_versao',
)


def require_schema(cursor):
    for table in TABLES:
        if not cursor.execute("SELECT OBJECT_ID(?, 'U')", ('dbo.' + table,)).fetchone()[0]:
            raise HTTPException(503, 'Versionamento indisponível: migration 195_malha_versionada_schema pendente')


def capability(cursor, name):
    require_schema(cursor)
    if not cursor.execute('SELECT 1 FROM dbo.etl_malha WHERE malha_name=?', (name,)).fetchone():
        raise HTTPException(404, 'Malha não encontrada')
    row = cursor.execute(
        'SELECT malha_id, effective_version_id, revision, estado FROM dbo.etl_malha_versionamento WHERE malha_name=?',
        (name,),
    ).fetchone()
    return {
        'mode': row[3] if row else 'legacy_unversioned',
        'malha_id': str(row[0]) if row else None,
        'effective_version_id': str(row[1]) if row and row[1] else None,
        'revision': row[2] if row else None,
        'read_only': True, 'authoring_available': False,
        'activation_available': False,
        'reason': 'Autoria e ativação dependem da cobertura de guardas legadas/API/DAG/guardiã',
    }


def version(cursor, name, version_id):
    require_schema(cursor)
    row = cursor.execute(
        '''SELECT v.version_id, v.numero, v.schema_version, v.definition_json,
                  v.layout_json, v.definition_hash, v.layout_hash, v.criada_por, v.criada_em
           FROM dbo.etl_malha_versao v
           JOIN dbo.etl_malha_versionamento m ON m.malha_id=v.malha_id
           WHERE m.malha_name=? AND v.version_id=?''', (name, str(version_id)),
    ).fetchone()
    if not row:
        raise HTTPException(404, 'Versão exata da malha não encontrada; nenhuma substituição aplicada')
    members = cursor.execute(
        '''SELECT pipeline_name, pipeline_version_id, content_hash
           FROM dbo.etl_malha_versao_membro WHERE malha_version_id=? ORDER BY pipeline_name''',
        (str(version_id),),
    ).fetchall()
    return {
        'version_id': str(row[0]), 'numero': row[1], 'schema_version': row[2],
        'definition': json.loads(row[3]), 'layout': json.loads(row[4]),
        'definition_hash': row[5], 'layout_hash': row[6],
        'criada_por': row[7], 'criada_em': row[8],
        'members': [{'pipeline_name': m[0], 'pipeline_version_id': str(m[1]),
                     'content_hash': m[2]} for m in members],
        'read_only': True,
    }


def corrida(cursor, name, corrida_id):
    require_schema(cursor)
    row = cursor.execute(
        '''SELECT c.malha_version_id, c.definition_hash
           FROM dbo.etl_malha_execucao e
           LEFT JOIN dbo.etl_malha_corrida_versao c ON c.corrida_id=e.id
           WHERE e.id=? AND e.malha_name=?''', (corrida_id, name),
    ).fetchone()
    if not row:
        raise HTTPException(404, 'Corrida da malha não encontrada')
    if row[0] is None:
        return {'corrida_id': corrida_id, 'mode': 'legacy_unversioned',
                'version_id': None, 'definition_hash': None, 'members': None,
                'read_only': True}
    result = version(cursor, name, row[0])
    if result['definition_hash'] != row[1]:
        raise HTTPException(409, 'Hash da definição capturada diverge da versão imutável')
    return {'corrida_id': corrida_id, 'mode': 'versioned', 'definition': result,
            'version_id': str(row[0]), 'definition_hash': row[1], 'read_only': True}
