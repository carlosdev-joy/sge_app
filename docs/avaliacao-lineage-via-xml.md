# Avaliação — usar o XML (`<DSExport>`) para enriquecer o lineage de jobs (Governança)

> Pergunta: já que importamos o **export XML** do DataStage para a Malha, dá para
> usar o mesmo XML para preencher o **lineage** (origens/destinos/transformações,
> tabelas, SQL, colunas) com **mais dados**, dentro da Governança?
> Resposta curta: **provavelmente sim e com bom custo-benefício**, mas há **uma
> premissa a confirmar** com um export real antes de investir.

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

## 3. A premissa que precisa ser confirmada (bloqueante)
**O `<DSExport>` que recebemos contém as propriedades de design-time de SQL/tabela/
coluna por stage?** Isso depende de **como o export foi gerado** no DataStage:
- Export "com componentes/design" → traz as propriedades dos stages (Select/Write
  statement, TableName, DataSource, colunas) — **dá para extrair lineage**.
- Export "executável/runtime" ou enxuto → pode trazer só o esqueleto (o que basta
  para a malha, mas **não** para lineage de coluna).

> ⚠️ Não há export XML real no repositório (só um fixture sintético de teste), então
> **não dá para afirmar** os caminhos exatos dos elementos (ex.: onde fica o
> `SelectStatement` no XML). **Ação primeira**: pegar 1 export real (ex.: `BI_VIDA.xml`)
> e inspecionar 1 job ODBC/Sequential para mapear os `Property Name=...` reais.

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

## 6. Próximos passos sugeridos (incremental)
1. **Spike (1–2 dias)**: pegar 1 export real, mapear os `Property` de 2–3 jobs
   (ODBC origem, Sequential destino, Transformer) e provar que dá para extrair
   tabela + SQL + colunas. **Decide go/no-go.**
2. Se **go**: implementar `extract_lineage` no parser XML + DAG/endpoint de carga,
   com `extraction_method="xml_export"` e estratégia de merge definida.
3. UI: na Governança, mostrar a **origem do dado** (`extraction_method`) e os
   **tipos de coluna** (hoje só mostramos os nomes) — ganho direto de "mais dados".

## Referências de código
- Lineage model: `sql/schema_prod_dev.sql` (`etl_job_lineage`), `script/proc/sp_etl_job_lineage_upsert.sql`.
- Extrator DSX (lógica a reusar): `dags/utils/dsx_engine.py`, `dags/etl_lineage_extract_dsx.py`.
- Parser XML atual (a estender): `dags/utils/ds_xml_malha.py`.
- API/UX: `api/routers/lineage.py`, `api/routers/catalogo.py`, `ui-react/src/pages/Governanca.tsx`.
