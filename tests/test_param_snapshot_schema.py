"""Contrato com a migration real: a identidade do Airflow chama-se execution_id."""
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def test_guardas_usam_coluna_real_da_execucao():
    migration=(ROOT/'sql/migrations/067_dependencias_pipeline.sql').read_text()
    schema=re.search(r'CREATE TABLE dbo.etl_pipeline_execucao \((.*?)\n    \);',migration,re.S).group(1)
    assert re.search(r'\bexecution_id\s+VARCHAR',schema)
    assert not re.search(r'\brun_id\s+(?:N?VARCHAR)',schema)
    for path in ['api/services/param_snapshot.py','dags/utils/param_snapshot.py']:
        source=(ROOT/path).read_text()
        assert 'e.execution_id COLLATE Latin1_General_BIN2=s.run_id' in source
        assert 'e.run_id COLLATE' not in source
