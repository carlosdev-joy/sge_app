"""ds_stage_types.py — classificação de tipos de stage do DataStage (compartilhada).

Espelho em Python do que a tabela `dbo.etl_stage_type_map` guarda (o mapa em
banco é a FONTE quando existe; estes conjuntos são o fallback e a semente de
consistência — o teste anti-drift confere que contêm os do `dsx_engine`).

Spec docs/spec-lineage-isx.md (F1). `dsx_engine.py` mantém seus próprios
conjuntos por enquanto (mudar o DSX está fora daquela spec); o ISX usa daqui.
"""
from __future__ import annotations

TRANSFORM_TYPES: frozenset[str] = frozenset({
    "PxSort", "PxSortWithGroupBy", "PxRemDup", "PxFunnel",
    "PxLookup", "PxAggregator", "PxJoin", "PxMerge", "PxFilter",
    "PxModify", "CTransformerStage", "TransformerStage", "PxSwitch", "PxPivot",
    "PxSurrogateKeyGen", "PxChangeCapture", "PxChangeApply",
    "PxDifference", "PxChecksum", "PxColumnExport", "PxColumnImport",
    "PxNormalize", "PxDenormalize", "PxMakeSubrec", "PxSplitSubrec",
    "PxRowMerge", "PxEncode", "PxDecode", "PxSharedContainer",
    "LocalContainerStage", "PxPeek", "RowGenerator", "ColumnGenerator",
    "PxHead", "PxTail", "PxSample", "PxCopy",
})

# Atividades de sequence: viram "transformacao" no lineage; a de job vira filho.
SEQUENCE_TYPES: frozenset[str] = frozenset({
    "CJobActivity", "CNotificationActivity", "CExceptionHandler",
    "CExecCommandActivity", "CRoutineActivity", "CSequencerActivity",
    "CWaitForFileActivity", "CStartLoopActivity", "CEndLoopActivity",
    "CUserVariablesActivity",
})

DB_TYPES: frozenset[str] = frozenset({
    "ODBCConnectorPX", "ODBCConnector", "OracleConnector", "DB2Connector",
    "SQLServerConnector", "TeradataConnector", "JDBCConnector",
    "DRSStage", "StoredProcedureStage", "MS_OLEDB", "SybaseConnector", "InformixConnector",
})

FILE_TYPES: frozenset[str] = frozenset({
    "PxDataSet", "DataSetStage",
    "PxSequentialFile", "SequentialFile", "FileConnector",
    "FileSetStage", "PxFileSet", "PxLookupFileSet",
    "PxExternalSource", "PxExternalTarget",
    "XmlOutputFileStage", "XmlInputFileStage",
})

# Rótulos do documento original (§5.12): ODBC | Arquivo | Transformer | Sequence.
CATEGORIA_POR_CLASSE = {"banco": "ODBC", "arquivo": "Arquivo", "transformacao": "Transformer",
                        "sequence": "Sequence", "debug": "Transformer"}


def classe_do_tipo(stage_type: str, mapa: dict[str, dict] | None = None) -> tuple[str | None, str, bool]:
    """(classe, rótulo, reconhecido).

    classe: 'banco' | 'arquivo' | 'transformacao' | 'sequence' | None.
    Consulta o mapa (linhas de `etl_stage_type_map` pela coluna-chave, que é
    `type_raw` ou `stage_type` conforme o ambiente — ver migration 106) e cai nos
    conjuntos daqui; por último, tenta pelo nome (`Connector`, `DataSet`…). Não
    reconhecido = (None, stage_type, False) — o chamador registra."""
    st = stage_type or ""
    if mapa and st in mapa:
        m = mapa[st]
        return str(m.get("type_category") or "").lower() or None, str(m.get("type_label") or st), True
    if st in SEQUENCE_TYPES:
        return "sequence", CATEGORIA_POR_CLASSE["sequence"], True
    if st in TRANSFORM_TYPES:
        return "transformacao", CATEGORIA_POR_CLASSE["transformacao"], True
    if st in DB_TYPES:
        return "banco", CATEGORIA_POR_CLASSE["banco"], True
    if st in FILE_TYPES:
        return "arquivo", CATEGORIA_POR_CLASSE["arquivo"], True
    baixo = st.lower()
    if any(k in baixo for k in ("odbc", "oracle", "db2", "sqlserver", "teradata", "jdbc", "connector")):
        return "banco", CATEGORIA_POR_CLASSE["banco"], False
    if any(k in baixo for k in ("dataset", "sequential", "fileset", "file")):
        return "arquivo", CATEGORIA_POR_CLASSE["arquivo"], False
    return None, st, False


def direcao(classe: str | None, context: str | None, tem_entrada: bool, tem_saida: bool) -> str:
    """origem | transformacao | destino — mesma régua do DSX: transformação pelo
    tipo; banco/arquivo pelo Context do conector; senão pela topologia."""
    if classe in ("transformacao", "sequence", "debug"):
        return "transformacao"
    ctx = (context or "").strip().lower()
    if ctx == "source":
        return "origem"
    if ctx in ("target", "write", "sink"):
        return "destino"
    if tem_saida and not tem_entrada:
        return "origem"
    if tem_entrada and not tem_saida:
        return "destino"
    return "transformacao"
