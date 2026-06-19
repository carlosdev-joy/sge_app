# Avaliação — usar o XML (`<DSExport>`) para enriquecer o lineage de jobs (Governança)

> Pergunta: já que importamos o **export XML** do DataStage para a Malha, dá para
> usar o mesmo XML para preencher o **lineage** (origens/destinos/transformações,
> tabelas, SQL, colunas) com **mais dados**, dentro da Governança?
> Resposta curta: **SIM — CONFIRMADO (GO)**. Spike rodado num export real
> (`SeqSsdVidaGeralDiario.xml`, BI_VIDA, DS 11.7) extraiu origens, destinos,
> transformações, SQL e **lineage em nível de coluna**. Ver "Resultado do spike".

## Resultado do spike (CONFIRMADO em export real)
Um extrator de prova (ElementTree, ~50 linhas) rodou no export e tirou, por job:
- **Origem** (link `ODBCOutput`): tabela real (`TDDB00.dbo.TB_CARGA`), DSN (`STG_DES`),
  SELECT completo (`SqlPrimary`) e as colunas.
- **Lineage de coluna**: `MAX_NUM_CARGA ← TDDB00.dbo.TB_CARGA.NUM_CARGA` via
  `SourceColumn`/`ParsedDerivation` por coluna de saída.
- **Destino** (link `ODBCInput`): tabela (`GE_002_CARGA`) + `SqlInsert/SqlUpdate/SqlDelete`.
- **Transformação** (`TransformerStage`): a expressão real
  (`If Link_..._Lookup.IND_SITUACAO_CARGA = 3 And Not(Isnull(...)) Then 1 Else 0`).

Mapeamento confirmado dos elementos:
| Lineage             | Elemento/Property no XML (confirmado)                                  |
|---------------------|------------------------------------------------------------------------|
| stage + conexão     | `Record Type="ODBCStage"` → `Name`, `DSN` (parametrizada), `UserName`  |
| origem (leitura)    | `Record Type="ODBCOutput"` → `SqlPrimary` (SELECT), `TableNames`, `Columns` |
| destino (escrita)   | `Record Type="ODBCInput"` → `TableName`, `SqlInsert/SqlUpdate/SqlDelete` |
| transformação       | `Record Type="TransformerStage"` → `Collection StageVars` → `Expression` |
| colunas             | `Collection Name="Columns"` → SubRecord: `Name, SqlType, Precision, Scale, Nullable, KeyPosition` |
| lineage de coluna   | coluna → `SourceColumn` / `ParsedDerivation` (`db.schema.tabela.coluna`) |
| tabela/database real| coluna → `TableDef` (`ODBC\<DSN>\<db>.<schema>.<tabela>`) + FROM/INTO do SQL |
| link↔stage          | link `Partner="V0S21|V0S21P1"` → stage `Identifier` antes do `|`        |

Observações do spike (a tratar na implementação):
- A **tabela física real** sai melhor do `FROM`/`INSERT INTO` do SQL; o `TableDef`
  guarda a tabela *modelada* (nome de table-def pode diferir do nome físico).
- DSN/database costuma vir **parametrizado** (`#CONTROLE.ParmDbNameGE#`) — guardar o
  parâmetro como database_name e/ou resolver via ParameterSet quando possível.
- Há também `HashedFileStage`/`HashedInput` (arquivos hash) — mapear como origem/destino
  de arquivo (file_path).

## 1. Como o lineage é preenchido hoje
- **Fonte rica — DSX binário** (`dags/utils/dsx_engine.py`, DAG `etl_lineage_extract_dsx.py`):
  lê arquivos `.dsx` e extrai por stage: `stage_name`, `stage_type_raw`,
  `database_name`, `sql_expression` (Select/Write/Insert), `file_path`,
  `columns_json` (com tipo/precisão/nullable) e a `direction` (origem/destino/transf).
  Grava com `extraction_method = "dsx_auto"`.
- **Manual** — wizard de pipeline (`api/routers/jobs.py`, `sp_etl_job_lineage_upsert`):
  a pessoa informa origens/destinos/transformações na tela.
- **Normalização** — `etl_lineage_normalize.py` quebra `sql_expression` em 1 linha
  por tabela real.

O modelo (`etl_job_lineage`) já tem **todos os campos** que precisamos:
`direction, object_type, object_name, stage_name, stage_type_raw, database_name,
sql_expression, file_path, columns_json, dsx_source_file, extracted_at, extraction_method`.
E a tela **Governança** (`Governanca.tsx` → `GET /lineage`) já consome e exibe
esses campos (SQL expansível, colunas, database/arquivo).

## 2. O que o XML já nos dá vs. o que ignoramos
- O XML `<DSExport>` é XML bem-formado (`<Record>`, `<Collection>`, `<SubRecord>`,
  `<Property Name=...>`). Hoje `dags/utils/ds_xml_malha.py` lê **só** o necessário
  para a topologia: `StageType` (lista), parâmetros, e as chamadas
  sequence→job (`real_target`). **Não** extrai SQL, tabela, database nem coluna.
- Ou seja: **a informação de stage já passa pelo nosso parser**, só não é aproveitada
  para lineage. O `dsx_engine` já tem a *lógica* de extração (regex de
  `SelectStatement`/`TableName`/colunas) — dá para adaptar ao formato XML.

## 3. Premissa (RESOLVIDA pelo spike)
A pergunta era: **o `<DSExport>` traz as propriedades de design-time de SQL/tabela/
coluna por stage?** O spike no export real **confirmou que SIM** (export "com
design", DS 11.7) — ver "Resultado do spike" acima, com os caminhos exatos.
Atenção operacional: a riqueza depende de o export ser gerado **com design** (não
"executável enxuto"); vale padronizar como os exports são tirados.

## 4. Proposta (se a premissa se confirmar)
**Opção recomendada — novo extrator XML de lineage**, paralelo ao DSX:
- `dags/etl_lineage_extract_xml.py` (espelha `etl_lineage_extract_dsx.py`) e/ou
  estender `ds_xml_malha.py` com uma função `extract_lineage(parsed)` que, por job,
  varre os stages e devolve origens/destinos/transformações com
  `stage_name/stage_type_raw/database_name/sql_expression/file_path/columns_json`.
- Grava via `sp_etl_job_lineage_upsert` com `extraction_method = "xml_export"`.
- **Reaproveita a importação que já fazemos** (mesmo arquivo da malha → POST
  `/malha-ds/import`): um upload, dois produtos (malha + lineage).

**Mapeamento XML → lineage (a confirmar com export real):**
| Lineage            | Origem no XML (provável)                                   |
|--------------------|------------------------------------------------------------|
| `stage_type_raw`   | `Property Name="StageType"` (já lido na malha)             |
| `direction`        | Context do stage / topologia input/output pins             |
| `object_name`/tabela | `SelectStatement`/`WriteStatement` (FROM/INTO) ou `TableName` |
| `database_name`    | `DataSource` / `ParmDb*`                                    |
| `file_path`        | propriedades de dataset/sequential file                    |
| `columns_json`     | `OutputPins`/`InputPins` (SubRecord com SqlType/Precision) |

## 5. Custo-benefício e riscos
**A favor**
- Uma única ingestão (o XML que já subimos para a malha) alimenta também o lineage.
- Pode cobrir jobs que o caminho DSX não cobre e **preencher campos hoje esparsos**
  (stage_type_raw, sql_expression, database_name, columns_json).
- Lógica de parsing de SQL/colunas já existe no `dsx_engine` (adaptável).

**Riscos / decisões**
- **Premissa do conteúdo do export** (seção 3) — é o risco número 1.
- **Conflito de fontes**: como mesclar `xml_export` com `dsx_auto`/manual?
  Sugestão: não sobrescrever lineage manual; para o automático, definir precedência
  (ex.: DSX > XML, ou o mais recente por `extracted_at`) e usar `extraction_method`
  como desempate/origem visível.
- **Direction** no XML pode ser menos explícita que no DSX (precisa inferir por
  topologia de pins) — validar a qualidade.
- **Versão do export** varia por servidor — mapear pode exigir tolerância a variações.

## 6. Próximos passos (spike concluído — GO)
1. ~~Spike go/no-go~~ — **FEITO**: confirmado em export real (seção "Resultado do spike").
2. **Implementar `extract_lineage(parsed)`** no parser XML (ODBCOutput→origem,
   ODBCInput→destino, TransformerStage→transformação, Hashed*→arquivo), preferindo
   a tabela física do `FROM`/`INTO` do SQL e anexando `columns_json` + lineage de coluna.
3. **Carga**: estender o import da malha (`POST /malha-ds/import`) para também gravar
   lineage via `sp_etl_job_lineage_upsert` com `extraction_method="xml_export"` —
   um upload, dois produtos.
4. **Merge de fontes**: não sobrescrever lineage **manual**; entre automáticos definir
   precedência (sugestão: o mais recente por `extracted_at`, com `extraction_method`
   visível). Decisão a tomar antes de gravar.
5. **UI Governança**: mostrar a **origem do dado** (`extraction_method`), os **tipos
   de coluna** (hoje só nomes) e o **lineage de coluna** (coluna→coluna origem).

## Referências de código
- Lineage model: `sql/schema_prod_dev.sql` (`etl_job_lineage`), `script/proc/sp_etl_job_lineage_upsert.sql`.
- Extrator DSX (lógica a reusar): `dags/utils/dsx_engine.py`, `dags/etl_lineage_extract_dsx.py`.
- Parser XML atual (a estender): `dags/utils/ds_xml_malha.py`.
- API/UX: `api/routers/lineage.py`, `api/routers/catalogo.py`, `ui-react/src/pages/Governanca.tsx`.
