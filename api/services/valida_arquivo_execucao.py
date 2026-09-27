"""Leitura para acompanhamento, limitada ao diagnóstico público da validação."""
import json
from services import param_snapshot as ps

MIGRATION='Aplique a migration 132 de histórico Valida Arquivo.'


def disponivel(cur):
    cur.execute("SELECT CASE WHEN OBJECT_ID('dbo.etl_valida_arquivo_tentativa','U') IS NOT NULL AND OBJECT_ID('dbo.etl_valida_arquivo_resultado','U') IS NOT NULL AND OBJECT_ID('dbo.etl_valida_arquivo_conclusao','U') IS NOT NULL AND COL_LENGTH('dbo.etl_pipeline','liberar_dependentes_sem_movimento') IS NOT NULL AND COL_LENGTH('dbo.etl_pipeline','notificar_sem_movimento') IS NOT NULL AND COL_LENGTH('dbo.etl_pipeline','politica_sem_movimento_revisao') IS NOT NULL THEN 1 ELSE 0 END")
    row=cur.fetchone();return bool(row and row[0])


def ler(cur,pipeline,run):
    snapshot=ps.original(cur,pipeline,run)
    if snapshot is None or not snapshot.get('validadores'):
        return dict(original=False,validadores={},tentativas=[],conclusao=None)
    cur.execute('SELECT task_id,tentativa,revisao,resultado_json,criado_em FROM dbo.etl_valida_arquivo_tentativa WHERE pipeline_name=? AND run_id=? ORDER BY task_id,tentativa DESC',(pipeline,run))
    tentativas=[dict(task_id=r[0],tentativa=r[1],revisao=r[2],resultado=json.loads(r[3]),criado_em=r[4].isoformat() if r[4] else None) for r in cur.fetchall()]
    cur.execute('SELECT resultado,liberar_dependentes,notificar,detalhes_json,atualizado_em FROM dbo.etl_valida_arquivo_conclusao WHERE pipeline_name=? AND run_id=?',(pipeline,run))
    row=cur.fetchone()
    conclusao=(dict(resultado=row[0],liberar_dependentes=bool(row[1]),notificar=bool(row[2]),detalhes=json.loads(row[3]),atualizado_em=row[4].isoformat() if row[4] else None) if row else None)
    return dict(original=True,validadores=snapshot['validadores'],politica_sem_movimento=snapshot.get('politica_sem_movimento'),tentativas=tentativas,conclusao=conclusao)
