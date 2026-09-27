"""Contrato v2 do catálogo de parâmetros (migration 129).

O contrato v1 continua vendo/editando apenas defaults DataStage. Seus saves
preservam parâmetros Orquestra e os metadados que a interface antiga não vê.
Valores e cálculos continuam usando job_params; este módulo não decifra.
"""
from services import job_params as jp

META = ("param_destino", "param_procedencia", "param_import_project",
        "param_import_job", "param_descricao")
PADRAO = dict(zip(META, ("datastage", "manual", None, None, None)))
COLS = ("param_name", "param_type", "param_value", "param_order", "param_source",
        "param_offset_meses", "param_ancora", "param_offset_dias", "param_formato")
ERRO_MIGRATION = "Catálogo de parâmetros exige a migration 129 (parametros_pipeline_origem)."


class SchemaIncompleto(RuntimeError):
    pass


def tem_catalogo(cur):
    cur.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline_param' "
                "AND COLUMN_NAME IN ('param_destino', 'param_procedencia', "
                "'param_import_project', 'param_import_job', 'param_descricao')")
    row = cur.fetchone()
    count = row[0] if row else 0
    if count not in (0, len(META)):
        raise SchemaIncompleto(ERRO_MIGRATION)
    return count == len(META)


def ler(cur, pipeline, *, bloquear=False):
    lock = " WITH (UPDLOCK, HOLDLOCK)" if bloquear else ""
    cur.execute("SELECT " + ", ".join(COLS + META) +
                " FROM dbo.etl_pipeline_param" + lock +
                " WHERE pipeline_name=? ORDER BY param_order", (pipeline,))
    return [dict(zip(COLS + META, row)) for row in cur.fetchall()]


def metadados(raw):
    erros = []
    meta = {}
    for campo, limite in zip(META, (16, 16, 128, 128, 500)):
        value = raw.get(campo, PADRAO[campo])
        if value is not None and (not isinstance(value, str) or
                                  any(0xD800 <= ord(c) <= 0xDFFF for c in value) or
                                  len(value.encode('utf-16-le')) // 2 > limite or
                                  any(c in value for c in ('\x00', '\r', '\n'))):
            erros.append(f"{campo}: texto inválido ou acima de {limite} caracteres UTF-16")
        else:
            meta[campo] = value
    if erros:
        return {}, erros
    if meta['param_destino'] not in ('datastage', 'orquestra'):
        erros.append('param_destino deve ser datastage ou orquestra')
    if meta['param_procedencia'] not in ('manual', 'datastage'):
        erros.append('param_procedencia deve ser manual ou datastage')
    imported = meta['param_procedencia'] == 'datastage'
    for campo in ('param_import_project', 'param_import_job'):
        v = meta[campo]
        if imported and (not v or not jp.NOME_RE.fullmatch(v)):
            erros.append(f'{campo} obrigatório e deve ser um identificador válido')
        elif not imported and v is not None:
            erros.append(f'{campo} só vale para procedência datastage')
    return meta, erros


def preparar(raw, existentes, versao, preparar_valores):
    """Valida antes do DELETE; mantém linhas ORQ invisíveis a clientes v1."""
    por_nome = {p['param_name']: p for p in existentes}
    enriquecidos, erros = [], []
    if len(raw) > 1000:
        return [], ['máximo de 1000 parâmetros por pipeline']
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            erros.append(f'parâmetro #{i + 1}: esperado objeto')
            continue
        # Não aceitar objetos/listas no lugar de valores, nem NUL no shell.
        for campo in ('param_name', 'param_type', 'param_source', 'param_value'):
            v = item.get(campo)
            if v is not None and (not isinstance(v, str) or '\x00' in v):
                erros.append(f'parâmetro #{i + 1}: {campo} deve ser texto sem NUL')
        nome = item.get('param_name')
        anterior = por_nome.get(nome.strip()) if isinstance(nome, str) else None
        if versao == 1:
            if any(k in item for k in META):
                erros.append('metadados exigem parametros_versao=2')
            if anterior and anterior['param_destino'] != 'datastage':
                erros.append('nome já reservado a parâmetro Orquestra; use parametros_versao=2')
            meta = {k: anterior[k] for k in META} if anterior else dict(PADRAO)
        else:
            meta, errs = metadados(item)
            erros.extend(f'parâmetro #{i + 1}: {e}' for e in errs)
        enriquecidos.append(dict(item, **meta))
    if erros:
        return [], erros
    tokens = {p['param_name']: p['param_value'] for p in existentes
              if p['param_type'] == 'Encrypted' and p['param_value']}
    linhas, erros = preparar_valores(enriquecidos, tokens)
    metas = {p['param_name'].strip(): {k: p[k] for k in META}
             for p in enriquecidos if isinstance(p.get('param_name'), str)}
    for p in linhas:
        p.update(metas[p['param_name']])
    if versao == 1:
        linhas.extend(dict(p) for p in existentes if p['param_destino'] == 'orquestra')
    for i, p in enumerate(linhas):
        p['param_order'] = i
    return linhas, erros


def gravar(cur, pipeline, linhas):
    cur.execute('DELETE FROM dbo.etl_pipeline_param WHERE pipeline_name=?', (pipeline,))
    cols = ('pipeline_name',) + COLS + META
    sql = ('INSERT INTO dbo.etl_pipeline_param (' + ', '.join(cols) + ') VALUES (' +
           ', '.join('?' for _ in cols) + ')')
    for p in linhas:
        cur.execute(sql, (pipeline,) + tuple(p[k] for k in COLS + META))
