from services.workspace_dependencies import dependency_diagnostics


class Cursor:
    def __init__(self, graph=(), catalog=None):
        self.graph = graph
        self.catalog = catalog or [('P', 1), ('A', 1), ('B', 1), ('Inactive', 0)]
        self.calls = []
    def execute(self, query):
        self.calls.append(query)
        self.result = self.catalog if 'SELECT pipeline_name,active' in query else self.graph
        return self
    def fetchall(self):
        return self.result


def projection(names, rows=None):
    return {'etl_pipeline': [{'pipeline_name': 'P', 'depends_on': ','.join(names)}], 'etl_pipeline_dependencia': rows if rows is not None else [{'pipeline_name': 'P', 'depende_de': name, 'tipo': 'PIPELINE', 'origem_no': None} for name in names]}


def codes(result):
    return {row['code'] for row in result}


def test_dependency_draft_validates_complete_casefolded_graph_under_lock():
    cur = Cursor(graph=[('A', 'B'), ('B', 'p')])
    assert 'dependency_cycle' in codes(dependency_diagnostics(cur, 'P', projection(['a']), {}, lock=True))
    assert len(cur.calls) == 2 and all('UPDLOCK,HOLDLOCK' in query for query in cur.calls)
    assert not dependency_diagnostics(Cursor(), 'P', projection(['A', 'B']), {})


def test_dependency_draft_rejects_missing_inactive_self_and_mirror_divergence():
    assert {'dependency_missing', 'dependency_inactive', 'dependency_self'} <= codes(dependency_diagnostics(Cursor(), 'P', projection(['Missing', 'Inactive', 'P']), {}))
    value = projection(['A']); value['etl_pipeline'][0]['depends_on'] = 'B'
    assert 'dependency_mirror' in codes(dependency_diagnostics(Cursor(), 'P', value, {}))


def test_compiled_dependencies_cannot_be_removed_forged_or_transferred():
    signed = {'pipeline_name': 'P', 'depende_de': 'A', 'tipo': 'PIPELINE', 'origem_no': 7, 'id': 1, 'criado_em': 'ignored'}
    existing = projection(['A'], [signed])
    assert 'compiled_dependency' in codes(dependency_diagnostics(Cursor(), 'P', projection([]), existing))
    forged = {**signed, 'origem_no': 8}
    assert 'compiled_dependency' in codes(dependency_diagnostics(Cursor(), 'P', projection(['A'], [forged]), existing))
    clean = {key: value for key, value in signed.items() if key not in ('id', 'criado_em')}
    cur = Cursor()
    assert not dependency_diagnostics(cur, 'P', projection(['A'], [clean]), existing)
    assert not cur.calls


def test_long_graph_cannot_hide_cycle_beyond_legacy_search_limit():
    graph = [('N'+str(i), 'N'+str(i+1)) for i in range(502)] + [('N502', 'P')]
    cur = Cursor(graph=graph, catalog=[('P',1),('N0',1)])
    assert 'dependency_cycle' in codes(dependency_diagnostics(cur, 'P', projection(['N0']), {}))


def test_noncanonical_dependency_type_cannot_bypass_sql_case_insensitive_graph():
    row={'pipeline_name':'P','depende_de':'A','tipo':'pipeline'}
    assert 'dependency_type' in codes(dependency_diagnostics(Cursor(graph=[('A','P')]),'P',projection([], [row]),{}))
    row['tipo']='JOB'
    assert 'dependency_type' in codes(dependency_diagnostics(Cursor(),'P',projection([], [row]),{}))
