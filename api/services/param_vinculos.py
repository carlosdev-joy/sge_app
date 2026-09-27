"""Contrato explícito de referência. Valores diretos da etapa têm prioridade."""
import json
from services import job_params as jp
from services import pipeline_params as pp

ERRO_MIGRATION = 'Aplique a migration 130 de vínculos e snapshot de parâmetros.'
CAMPOS_PYTHON = {'script_path', 'destino_dir'}


def normalizar(raw, tipo, catalogo, python=None):
    if raw is None:
        return {}
    if not isinstance(raw, dict) or len(raw) > 100:
        raise ValueError('Vínculos devem ser um objeto com até 100 campos.')
    if raw and tipo not in ('datastage', 'python'):
        raise ValueError('Vínculos disponíveis somente em DataStage e Python.')
    por_nome = {p['param_name']: p for p in catalogo}
    out = {}
    for alvo, nome in raw.items():
        if not isinstance(alvo, str) or not isinstance(nome, str):
            raise ValueError('Campo e referência devem ser nomes.')
        if len(alvo) > 128 or not jp.NOME_RE.fullmatch(alvo):
            raise ValueError('Nome de destino inválido.')
        if nome not in por_nome:
            raise ValueError(f"Parâmetro de pipeline '{nome}' não encontrado.")
        p = por_nome[nome]
        if tipo == 'datastage' and p.get('param_destino') != 'datastage':
            raise ValueError('Parâmetro exclusivo Orquestra não pode ser enviado ao DataStage.')
        if tipo == 'python':
            modo = (python or {}).get('modo')
            permitido = 'script_path' if modo == 'arquivo' else 'destino_dir' if modo == 'codigo' else None
            if alvo != permitido:
                raise ValueError('Python permite referência apenas no caminho do script ou diretório de publicação do modo ativo.')
            if p.get('param_type') not in ('String', 'Pathname') or p.get('param_source') != 'fixo':
                raise ValueError('Caminho Python exige parâmetro String/Pathname fixo, sem segredo.')
        out[alvo] = nome
    return out


def disponivel(cur):
    cur.execute("SELECT COL_LENGTH('dbo.etl_pipeline_job','param_vinculos_json')")
    row = cur.fetchone()
    if not row or not row[0]:
        return False
    cur.execute("SELECT CASE WHEN COL_LENGTH('dbo.etl_pipeline','param_snapshot_ativo') IS NOT NULL AND OBJECT_ID('dbo.etl_parametro_snapshot','U') IS NOT NULL THEN 1 ELSE 0 END")
    row = cur.fetchone()
    return bool(row and row[0])


def preparar(cur, pipeline, node):
    if not disponivel(cur):
        if node.get('param_vinculos'):
            raise ValueError(ERRO_MIGRATION)
        return None
    cur.execute('SELECT job_type, python_json, param_vinculos_json FROM dbo.etl_pipeline_job WHERE pipeline_name=? AND job_name=?',
                (pipeline, node.get('job_name', '').strip()))
    old = cur.fetchone()
    tipo = (node.get('job_type') or (old[0] if old else 'datastage')).strip().lower()
    if 'python' in node:
        python = node['python']
    elif 'python_json' in node:
        python = json.loads(node['python_json']) if node['python_json'] else None
    else:
        python = json.loads(old[1]) if old and old[1] else None
    raw = node.get('param_vinculos') if 'param_vinculos' in node else (json.loads(old[2]) if old and old[2] else {})
    if not raw:
        return None
    # O mesmo estado validado deve chegar à gravação, inclusive no endpoint legado.
    node.setdefault('job_type', tipo)
    if tipo == 'python':
        node['python'] = python
    catalogo = pp.ler(cur, pipeline)
    refs = normalizar(raw, tipo, catalogo, python)
    return json.dumps(refs, ensure_ascii=False)


def gravar(cur, pipeline, job, raw):
    if raw:
        cur.execute('UPDATE dbo.etl_pipeline SET param_snapshot_ativo=1 WHERE pipeline_name=?', (pipeline,))
    cur.execute('UPDATE dbo.etl_pipeline_job SET param_vinculos_json=? WHERE pipeline_name=? AND job_name=?',
                (raw, pipeline, job))


def ler_todos(cur, pipeline):
    if not disponivel(cur):
        return {}
    cur.execute('SELECT job_name, param_vinculos_json FROM dbo.etl_pipeline_job WHERE pipeline_name=?',
                (pipeline,))
    return {r[0]: json.loads(r[1]) if r[1] else {} for r in cur.fetchall()}


def validar_catalogo(cur, pipeline, catalogo):
    """Recusa remoção de referência viva ou tipo incompatível antes do replace-all."""
    if not disponivel(cur):
        return
    cur.execute('SELECT job_type, python_json, param_vinculos_json FROM dbo.etl_pipeline_job WHERE pipeline_name=? AND param_vinculos_json IS NOT NULL',
                (pipeline,))
    for tipo, py, refs in cur.fetchall():
        normalizar(json.loads(refs), tipo, catalogo, json.loads(py) if py else None)
