"""Validação das dependências versionadas, sem escrita no cadastro ativo."""
from __future__ import annotations


def dependency_diagnostics(cur, name, projection, existing, *, lock=False):
    if not projection:
        return []
    desired = projection.get('etl_pipeline_dependencia', [])
    previous = existing.get('etl_pipeline_dependencia', [])
    pipeline = projection['etl_pipeline'][0]
    if not dependency_changes(projection, existing):
        return []
    issues = []
    def error(code, message):
        issues.append({'nodeId': None, 'field': 'depends_on', 'code': code, 'message': message})
    # Propriedade da malha não pode ser criada, removida ou transferida pelo draft.
    for old in previous:
        if old.get('origem_no') is not None and not any(_configuration(row) == _configuration(old) for row in desired):
            error('compiled_dependency', 'Dependência compilada deve ser editada pela malha dona.')
    for row in desired:
        if row.get('origem_no') is not None and not any(_configuration(row)==_configuration(old) for old in previous):
            error('compiled_dependency', 'O rascunho não pode criar ou alterar assinaturas de malha.')
    for row in desired:
        if row.get('tipo') not in ('PIPELINE', 'JOB'):
            error('dependency_type', 'Tipo de dependência inválido; use PIPELINE.')
        elif row.get('tipo') == 'JOB' and not any(_configuration(row)==_configuration(old) for old in previous):
            error('dependency_type', 'Dependências entre jobs não são editadas neste fluxo.')
    names = [str(row.get('depende_de') or '').strip() for row in desired if row.get('tipo') == 'PIPELINE']
    csv = [part.strip() for part in str(pipeline.get('depends_on') or '').split(',') if part.strip()]
    if len({x.casefold() for x in names}) != len(names) or {x.casefold() for x in names} != {x.casefold() for x in csv}:
        error('dependency_mirror', 'A seleção de predecessores e o cadastro devem corresponder.')
    hint = ' WITH(UPDLOCK,HOLDLOCK)' if lock else ''
    cur.execute('SELECT pipeline_name,active FROM dbo.etl_pipeline'+hint)
    catalog = {str(row[0]).strip().casefold(): bool(row[1]) for row in cur.fetchall()}
    previous_names = {str(row.get('depende_de') or '').strip().casefold() for row in previous}
    for parent in names:
        key = parent.casefold()
        if not parent or key == name.casefold():
            error('dependency_self', 'Selecione um predecessor diferente do próprio pipeline.')
        elif key not in catalog:
            error('dependency_missing', 'Predecessor não encontrado: '+parent)
        elif not catalog[key] and key not in previous_names:
            error('dependency_inactive', 'Selecione um predecessor ativo: '+parent)
    cur.execute("SELECT pipeline_name,depende_de FROM dbo.etl_pipeline_dependencia"+hint+" WHERE tipo='PIPELINE'")
    graph = {}
    for child, parent in cur.fetchall():
        graph.setdefault(str(child).strip().casefold(), []).append(str(parent).strip().casefold())
    graph[name.casefold()] = [x.casefold() for x in names]
    from routers.pipelines import _check_circular_grafo
    try:
        _check_circular_grafo(name.casefold(), graph[name.casefold()], lambda child: graph.get(child, []), fail_closed=True)
    except ValueError as exc:
        error('dependency_cycle', str(exc))
    return issues


def _configuration(row):
    return {key:value for key,value in row.items() if key not in {'id','criado_em','criado_por','created_at','updated_at','atualizado_em'}}


def dependency_changes(projection, existing):
    if not projection:
        return False
    desired = projection.get('etl_pipeline_dependencia', [])
    previous = existing.get('etl_pipeline_dependencia', [])
    old_pipeline = next(iter(existing.get('etl_pipeline', [])), {})
    return ([_configuration(row) for row in desired] != [_configuration(row) for row in previous]
            or projection['etl_pipeline'][0].get('depends_on') != old_pipeline.get('depends_on'))
