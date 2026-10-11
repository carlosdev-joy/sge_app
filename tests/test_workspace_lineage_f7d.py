import copy
import pytest
from services.workspace_publication import materialize,PublicationBlocked,sync_rows,lineage_column_diagnostics


def definition(captured=True,rows=None):
 return {'identity':{'pipelineName':'PIPE'},'metadata':{'legacyPipeline':{'project_name':'Project','domain':'Domain'},**({'workspaceLineageVersion':1} if captured else {})},'nodes':[{'id':'NODE','type':'shell','configuration':{'legacyJob':{'job_command':'true'},**({'etl_job_lineage':rows if rows is not None else []} if captured else {})}}],'edges':[]}


def test_known_empty_and_historical_unknown_are_distinct():
 assert materialize(definition(),{'nodes':{}},{})['etl_job_lineage']==[]
 assert 'etl_job_lineage' not in materialize(definition(False),{'nodes':{}},{'etl_job_lineage':[{'object_name':'keep'}]})


def test_lineage_roundtrip_preserves_duplicates_unknown_fields_and_canonical_scope():
 row={'pipeline_name':'other','job_name':'other','direction':'origem','object_name':'DB.TABLE','apt_code':'code','expressions_json':'[]','extra':{'retained':True}}
 result=materialize(definition(rows=[row,copy.deepcopy(row)]),{'nodes':{}},{})['etl_job_lineage']
 assert result==[{**row,'pipeline_name':'PIPE','job_name':'NODE'}]*2
 assert row['pipeline_name']=='other'


@pytest.mark.parametrize('marker',[True,'1',2,None])
def test_marker_requires_exact_contract(marker):
 value=definition();value['metadata']['workspaceLineageVersion']=marker
 with pytest.raises(PublicationBlocked,match='Contrato de lineage'):materialize(value,{'nodes':{}},{})


@pytest.mark.parametrize('rows',[None,{},[None],['row']])
def test_missing_or_invalid_rows_never_infer_active_lineage(rows):
 value=definition();value['nodes'][0]['configuration']['etl_job_lineage']=rows
 with pytest.raises(PublicationBlocked):materialize(value,{'nodes':{}},{'etl_job_lineage':[{'object_name':'active'}]})


def test_historical_contract_cannot_mutate_lineage():
 value=definition(False);value['nodes'][0]['configuration']['etl_job_lineage']=[]
 with pytest.raises(PublicationBlocked):materialize(value,{'nodes':{}},{})


class Cursor:
 def __init__(self):self.statements=[]
 def execute(self,sql,args=()):self.statements.append((sql,args));return self
 def fetchall(self):return [('pipeline_name',),('job_name',),('direction',),('object_name',),('extracted_at',)]


def test_sync_has_no_invented_functional_key_and_keeps_duplicates():
 cur=Cursor();rows=[{'pipeline_name':'PIPE','job_name':'NODE','direction':'origem','object_name':'TABLE','id':9,'extracted_at':'old'}]*2
 sync_rows(cur,'etl_job_lineage','PIPE',rows)
 inserts=[(sql,args) for sql,args in cur.statements if sql.startswith('INSERT')]
 assert len(inserts)==2 and inserts[0]==inserts[1]
 assert all('[id]' not in sql and '[extracted_at]' not in sql for sql,args in inserts)
 assert any(sql=='DELETE FROM dbo.etl_job_lineage WHERE pipeline_name=?' for sql,args in cur.statements)


def test_lineage_column_validation_uses_real_capacity_and_encoding():
 class SchemaCursor(Cursor):
  def fetchall(self):return [('object_name','nvarchar',10,False,False,False,0),('stage_name','varchar',3,True,False,False,0)]
 assert not lineage_column_diagnostics(SchemaCursor(),[{'object_name':'😀ab','stage_name':'é'}])
 assert len(lineage_column_diagnostics(SchemaCursor(),[{'object_name':'😀😀ab','stage_name':'😀'}]))==2
 assert len(lineage_column_diagnostics(SchemaCursor(),[{}]))==1
