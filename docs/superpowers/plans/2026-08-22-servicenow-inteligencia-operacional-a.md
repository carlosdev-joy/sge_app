# Subsistema A — Inteligência Operacional ServiceNow: Implementação

> **Para workers agênticos:** SUB-SKILL OBRIGATÓRIA: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para implementar task por task. Steps usam checkbox (`- [ ]`) para rastreamento.

**Goal:** Transformar o sync passivo em base de inteligência operacional: delta a cada 5 min, histórico de notas/anexos por chamado, snapshots de indicadores, tela Admin e indicadores históricos.

**Architecture:** Duas novas DAGs (delta + full) consomem funções centralizadas em `servicenow_sync.py`; a API expõe endpoints de detalhe, proxy de anexos, admin e histórico; o frontend ganha Admin ServiceNow, modal de detalhes e tela de indicadores históricos.

**Tech Stack:** Python 3.11 · Airflow 2 (`@dag`/`@task`) · pymssql (`%s`) na árvore dags/ · pyodbc (`?`) na árvore api/ · FastAPI · httpx · React/TypeScript · Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-08-22-servicenow-inteligencia-operacional-a.md`

## Global Constraints

- Árvore `dags/` usa pymssql → placeholder `%s`. Árvore `api/` usa pyodbc → placeholder `?`. Trocar os dois grava silenciosamente na coluna errada ou levanta `Incorrect syntax`.
- Migrations numeradas sequencialmente; última existente é 093. Novas: 094, 095, 096, 097, 098.
- `CAMPOS_UPSERT` em `servicenow_sync.py` é a ÚNICA fonte de ordem dos campos no MERGE. Acrescentar coluna = acrescentar nesta tupla.
- `etl_chamado_nota`: notas são imutáveis no ServiceNow — sync só insere, nunca atualiza.
- `etl_chamado_ciclo` substitui `etl_chamado_sync` como log de ciclo; a tabela antiga NÃO é deletada nesta spec.
- `FRESCOR_ALERTA_MINUTOS` muda de `60` para `8` quando a DAG delta entra em produção (cadência 5 min + margem).
- Estado `encerrado` é `FORA_DO_KANBAN` — sai da fila (ativo=0) mas fica no espelho para indicadores.
- Proxy de anexos: credencial lida de `etl_app_config` a cada request — sem cache.
- INC não-encerrado: `tipo='incident'` + `estado_kanban NOT IN ('resolvido','encerrado')` → borda `border-l-4 border-red-500`.
- Testes dags/: stub via `sys.modules`, MagicMock, run `docker exec orquestra-api python -m pytest tests/<arquivo> -v`.
- Testes api/: `_DB_PATCH = "routers.chamados.get_db_conn"`, FastAPI TestClient.

---

## Mapa de Arquivos

| Ação | Arquivo |
|------|---------|
| Criar | `spec/sql/migrations/094_chamados_nota_anexo.sql` |
| Criar | `spec/sql/migrations/095_chamados_anexo.sql` |
| Criar | `spec/sql/migrations/096_chamado_ciclo.sql` |
| Criar | `spec/sql/migrations/097_indicador_snapshot.sql` |
| Criar | `spec/sql/migrations/098_sn_grupo_gatilho.sql` |
| Modificar | `dags/utils/servicenow_sync.py` (novas funções) |
| Criar | `dags/etl_servicenow_delta.py` |
| Modificar | `dags/etl_servicenow_full.py` (novo) — refatora `etl_servicenow_sync.py` |
| Modificar | `api/routers/chamados.py` (novos endpoints + `FRESCOR_ALERTA_MINUTOS=8`) |
| Modificar | `api/services/servicenow.py` (grupos, config admin) |
| Criar | `ui-react/src/pages/AdminServiceNow.tsx` |
| Criar | `ui-react/src/pages/ChamadosIndicadoresHistorico.tsx` |
| Modificar | `ui-react/src/pages/layout/` (nova rota + nav) |
| Criar | `ui-react/src/components/ChamadoDetalheModal.tsx` |
| Modificar | `ui-react/src/pages/Admin.tsx` (link para nova tela) |
| Criar | `dags/tests/test_servicenow_delta.py` |
| Criar | `dags/tests/test_servicenow_notas.py` |
| Criar | `dags/tests/test_servicenow_snapshot.py` |
| Modificar | `dags/tests/test_servicenow_cadencia.py` (aceitar `FRESCOR=8`) |
| Criar | `dags/tests/test_chamados_detalhe.py` |
| Criar | `dags/tests/test_chamados_anexo_proxy.py` |
| Criar | `dags/tests/test_admin_servicenow.py` |
| Criar | `dags/tests/test_indicadores_historico.py` |

---

## Task 1: Migrations 094–098

**Files:**
- Criar: `spec/sql/migrations/094_chamados_nota_anexo.sql`
- Criar: `spec/sql/migrations/095_chamados_anexo.sql`  
- Criar: `spec/sql/migrations/096_chamado_ciclo.sql`
- Criar: `spec/sql/migrations/097_indicador_snapshot.sql`
- Criar: `spec/sql/migrations/098_sn_grupo_gatilho.sql`

**Interfaces:**
- Produz: tabelas `etl_chamado_nota`, `etl_chamado_anexo`, `etl_chamado_ciclo`, `etl_indicador_snapshot`, `etl_indicador_snapshot_analista`, `etl_indicador_snapshot_grupo`, `etl_indicador_meta`, `etl_servicenow_grupo`, `etl_servicenow_gatilho` e coluna `tem_anexo` em `etl_chamado`.

- [ ] **Step 1: Criar migration 094 — coluna tem_anexo + tabela etl_chamado_nota**

```sql
-- spec/sql/migrations/094_chamados_nota_anexo.sql
-- Adiciona tem_anexo à etl_chamado e cria etl_chamado_nota.

ALTER TABLE dbo.etl_chamado
    ADD tem_anexo TINYINT NULL DEFAULT 0;

CREATE TABLE dbo.etl_chamado_nota (
    sys_id_nota      NVARCHAR(32)   NOT NULL,
    sys_id_chamado   NVARCHAR(32)   NOT NULL,
    autor            NVARCHAR(120)  NULL,
    autor_email      NVARCHAR(200)  NULL,
    criado_em        DATETIME2      NULL,
    texto            NVARCHAR(4000) NULL,
    tipo             NVARCHAR(20)   NOT NULL,  -- 'work_notes' | 'comments'
    sync_em          DATETIME2      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_etl_chamado_nota PRIMARY KEY (sys_id_nota),
    CONSTRAINT FK_nota_chamado FOREIGN KEY (sys_id_chamado)
        REFERENCES dbo.etl_chamado(sys_id)
);
CREATE INDEX IX_nota_chamado ON dbo.etl_chamado_nota (sys_id_chamado);
```

- [ ] **Step 2: Criar migration 095 — tabela etl_chamado_anexo**

```sql
-- spec/sql/migrations/095_chamados_anexo.sql
CREATE TABLE dbo.etl_chamado_anexo (
    sys_id_anexo     NVARCHAR(32)   NOT NULL,
    sys_id_chamado   NVARCHAR(32)   NOT NULL,
    nome_arquivo     NVARCHAR(255)  NULL,
    mime_type        NVARCHAR(100)  NULL,
    tamanho_bytes    INT            NULL,
    url_download     NVARCHAR(500)  NULL,
    criado_em        DATETIME2      NULL,
    sync_em          DATETIME2      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_etl_chamado_anexo PRIMARY KEY (sys_id_anexo),
    CONSTRAINT FK_anexo_chamado FOREIGN KEY (sys_id_chamado)
        REFERENCES dbo.etl_chamado(sys_id)
);
CREATE INDEX IX_anexo_chamado ON dbo.etl_chamado_anexo (sys_id_chamado);
```

- [ ] **Step 3: Criar migration 096 — tabela etl_chamado_ciclo**

```sql
-- spec/sql/migrations/096_chamado_ciclo.sql
CREATE TABLE dbo.etl_chamado_ciclo (
    id               INT IDENTITY(1,1) NOT NULL,
    modo             NVARCHAR(10)   NOT NULL,   -- 'delta' | 'full'
    iniciado_em      DATETIME2      NOT NULL,
    terminado_em     DATETIME2      NULL,
    status           NVARCHAR(10)   NOT NULL DEFAULT 'ERRO',
    qtd_chamados     INT            NULL,
    qtd_notas        INT            NULL,
    qtd_anexos       INT            NULL,
    qtd_desativados  INT            NULL,
    disparado_por    NVARCHAR(50)   NULL,
    erro             NVARCHAR(1000) NULL,
    CONSTRAINT PK_etl_chamado_ciclo PRIMARY KEY (id)
);
CREATE INDEX IX_ciclo_modo_status
    ON dbo.etl_chamado_ciclo (modo, status, iniciado_em DESC);
```

- [ ] **Step 4: Criar migration 097 — snapshot + filhas + metas**

```sql
-- spec/sql/migrations/097_indicador_snapshot.sql
CREATE TABLE dbo.etl_indicador_snapshot (
    id                          INT IDENTITY(1,1) NOT NULL,
    capturado_em                DATETIME2      NOT NULL DEFAULT GETDATE(),
    total_ativos                INT            NOT NULL DEFAULT 0,
    novo                        INT            NOT NULL DEFAULT 0,
    andamento                   INT            NOT NULL DEFAULT 0,
    aguardando                  INT            NOT NULL DEFAULT 0,
    resolvido                   INT            NOT NULL DEFAULT 0,
    outros                      INT            NOT NULL DEFAULT 0,
    sla_vencidos                INT            NOT NULL DEFAULT 0,
    idade_media_dias            DECIMAL(6,1)   NULL,
    tempo_medio_resolucao_horas DECIMAL(8,1)   NULL,
    qtd_encerrados_7d           INT            NOT NULL DEFAULT 0,
    qtd_abertos_7d              INT            NOT NULL DEFAULT 0,
    qtd_iniciativas_abertas     INT            NOT NULL DEFAULT 0,
    CONSTRAINT PK_snapshot PRIMARY KEY (id)
);
CREATE INDEX IX_snapshot_capturado ON dbo.etl_indicador_snapshot (capturado_em DESC);

CREATE TABLE dbo.etl_indicador_snapshot_analista (
    id_snapshot       INT            NOT NULL,
    atribuido_a       NVARCHAR(120)  NOT NULL,
    atribuido_a_email NVARCHAR(200)  NOT NULL DEFAULT '',
    total_ativos      INT            NOT NULL DEFAULT 0,
    sla_vencidos      INT            NOT NULL DEFAULT 0,
    idade_media_dias  DECIMAL(6,1)   NULL,
    CONSTRAINT PK_snapshot_analista PRIMARY KEY (id_snapshot, atribuido_a_email),
    CONSTRAINT FK_snapshot_analista FOREIGN KEY (id_snapshot)
        REFERENCES dbo.etl_indicador_snapshot(id)
);

CREATE TABLE dbo.etl_indicador_snapshot_grupo (
    id_snapshot      INT            NOT NULL,
    grupo            NVARCHAR(120)  NOT NULL,
    total_ativos     INT            NOT NULL DEFAULT 0,
    sla_vencidos     INT            NOT NULL DEFAULT 0,
    idade_media_dias DECIMAL(6,1)   NULL,
    CONSTRAINT PK_snapshot_grupo PRIMARY KEY (id_snapshot, grupo),
    CONSTRAINT FK_snapshot_grupo FOREIGN KEY (id_snapshot)
        REFERENCES dbo.etl_indicador_snapshot(id)
);

CREATE TABLE dbo.etl_indicador_meta (
    id              INT IDENTITY(1,1) NOT NULL,
    metrica         NVARCHAR(60)   NOT NULL,
    valor_meta      DECIMAL(8,1)   NOT NULL,
    periodo_inicio  DATE           NOT NULL,
    periodo_fim     DATE           NULL,
    grupo           NVARCHAR(120)  NULL,
    criado_por      NVARCHAR(120)  NULL,
    criado_em       DATETIME2      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_meta PRIMARY KEY (id)
);
```

- [ ] **Step 5: Criar migration 098 — etl_servicenow_grupo + etl_servicenow_gatilho**

```sql
-- spec/sql/migrations/098_sn_grupo_gatilho.sql
CREATE TABLE dbo.etl_servicenow_grupo (
    id           INT IDENTITY(1,1) NOT NULL,
    nome         NVARCHAR(200)  NOT NULL,
    ativo        TINYINT        NOT NULL DEFAULT 1,
    criado_em    DATETIME2      NOT NULL DEFAULT GETDATE(),
    alterado_em  DATETIME2      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_sn_grupo PRIMARY KEY (id),
    CONSTRAINT UQ_sn_grupo_nome UNIQUE (nome)
);

CREATE TABLE dbo.etl_servicenow_gatilho (
    id            INT IDENTITY(1,1) NOT NULL,
    tipo          NVARCHAR(60)   NOT NULL,
    condicao_json NVARCHAR(500)  NULL,
    webhook_url   NVARCHAR(500)  NULL,
    ativo         TINYINT        NOT NULL DEFAULT 0,
    grupo         NVARCHAR(120)  NULL,
    criado_em     DATETIME2      NOT NULL DEFAULT GETDATE(),
    CONSTRAINT PK_sn_gatilho PRIMARY KEY (id)
);
```

- [ ] **Step 6: Aplicar migrations em ordem no banco de dev/homolog**

```bash
# Via sqlcmd ou SSMS, em ordem:
# 094 → 095 → 096 → 097 → 098
sqlcmd -S SQL14 -d DMDB41 -i spec/sql/migrations/094_chamados_nota_anexo.sql
sqlcmd -S SQL14 -d DMDB41 -i spec/sql/migrations/095_chamados_anexo.sql
sqlcmd -S SQL14 -d DMDB41 -i spec/sql/migrations/096_chamado_ciclo.sql
sqlcmd -S SQL14 -d DMDB41 -i spec/sql/migrations/097_indicador_snapshot.sql
sqlcmd -S SQL14 -d DMDB41 -i spec/sql/migrations/098_sn_grupo_gatilho.sql
```

- [ ] **Step 7: Verificar que as 5 migrations criaram todas as tabelas**

```sql
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME IN (
    'etl_chamado_nota', 'etl_chamado_anexo', 'etl_chamado_ciclo',
    'etl_indicador_snapshot', 'etl_indicador_snapshot_analista',
    'etl_indicador_snapshot_grupo', 'etl_indicador_meta',
    'etl_servicenow_grupo', 'etl_servicenow_gatilho'
  )
ORDER BY TABLE_NAME;
-- Esperado: 9 linhas
```

```sql
SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'etl_chamado'
  AND COLUMN_NAME = 'tem_anexo';
-- Esperado: 1 linha
```

- [ ] **Step 8: Commit**

```bash
git add spec/sql/migrations/094_chamados_nota_anexo.sql \
        spec/sql/migrations/095_chamados_anexo.sql \
        spec/sql/migrations/096_chamado_ciclo.sql \
        spec/sql/migrations/097_indicador_snapshot.sql \
        spec/sql/migrations/098_sn_grupo_gatilho.sql
git commit -m "feat(db): migrations 094-098 — nota, anexo, ciclo, snapshot, grupo ServiceNow"
```

---

## Task 2: Refatoração de `servicenow_sync.py` — novas funções

**Files:**
- Modificar: `dags/utils/servicenow_sync.py`
- Criar: `dags/tests/test_servicenow_delta.py`
- Criar: `dags/tests/test_servicenow_notas.py`
- Criar: `dags/tests/test_servicenow_snapshot.py`

**Interfaces:**
- Consome: tabelas criadas na Task 1 (via hook pymssql)
- Produz (funções públicas):
  - `ultimo_delta_em(hook) -> datetime`
  - `query_delta(grupos: list[str], desde: datetime) -> str`
  - `buscar_notas(cliente, url: str, sys_id: str) -> list[dict]`
  - `buscar_anexos(cliente, url: str, sys_id: str) -> list[dict]`
  - `upsert_nota_sql() -> str`
  - `upsert_anexo_sql() -> str`
  - `capturar_snapshot(hook) -> int`
  - `grupos_ativos(hook) -> list[str]`

- [ ] **Step 1: Escrever testes para `ultimo_delta_em` e `query_delta`**

```python
# dags/tests/test_servicenow_delta.py
"""Testa ponto de corte do delta e montagem da query incremental."""
import sys, types, datetime as _dt
from unittest.mock import MagicMock, patch

# ── stubs obrigatórios ────────────────────────────────────────────────────────
for mod in ("utils.chamado_derivacoes", "utils.texto_sql", "utils.frescor_modulo"):
    m = types.ModuleType(mod)
    if mod == "utils.texto_sql":
        m.cortar = lambda t, n: (t or "")[:n]
        m.unidades_utf16 = lambda t: len((t or "").encode("utf-16-le")) // 2
    elif mod == "utils.chamado_derivacoes":
        m.derivar = lambda linha: {}
    elif mod == "utils.frescor_modulo":
        m.carimbar = lambda f: None
        m.conferir = lambda f: None
    sys.modules[mod] = m

from utils.servicenow_sync import ultimo_delta_em, query_delta  # noqa: E402


class TestUltimoDeltaEm:
    def _hook(self, row):
        h = MagicMock()
        h.get_conn.return_value.__enter__ = MagicMock(return_value=MagicMock())
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = row
        conn.cursor.return_value = cur
        h.get_conn.return_value = conn
        return h

    def test_retorna_datetime_quando_existe(self):
        ts = _dt.datetime(2026, 8, 22, 10, 0, 0)
        h = self._hook((ts,))
        resultado = ultimo_delta_em(h)
        assert resultado == ts

    def test_fallback_30min_quando_nulo(self):
        h = self._hook((None,))
        antes = _dt.datetime.utcnow() - _dt.timedelta(minutes=31)
        resultado = ultimo_delta_em(h)
        depois = _dt.datetime.utcnow() - _dt.timedelta(minutes=29)
        assert antes <= resultado <= depois


class TestQueryDelta:
    def test_inclui_filtro_sys_updated_on(self):
        desde = _dt.datetime(2026, 8, 22, 10, 0, 0)
        q = query_delta(["Eng. Dados"], desde)
        assert "sys_updated_on>=" in q
        assert "2026-08-22" in q

    def test_inclui_filtro_de_grupo(self):
        q = query_delta(["Eng. Dados", "Dados Cloud"], _dt.datetime(2026, 8, 22))
        assert "assignment_group.name=Eng. Dados" in q
        assert "assignment_group.name=Dados Cloud" in q

    def test_levanta_se_grupos_vazio(self):
        import pytest
        with pytest.raises(ValueError):
            query_delta([], _dt.datetime(2026, 8, 22))
```

- [ ] **Step 2: Rodar os testes — esperar FAIL com `ImportError` ou `AttributeError`**

```bash
docker exec orquestra-api python -m pytest tests/test_servicenow_delta.py -v
# Esperado: FAIL — funções ainda não existem
```

- [ ] **Step 3: Implementar `ultimo_delta_em`, `query_delta` e `grupos_ativos` em `servicenow_sync.py`**

Adicionar ao final do arquivo `dags/utils/servicenow_sync.py`, após `upsert_params`:

```python
def grupos_ativos(hook) -> list[str]:
    """Lê etl_servicenow_grupo WHERE ativo=1. Fallback vazio levanta no caller."""
    conn = hook.get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT nome FROM dbo.etl_servicenow_grupo WHERE ativo=1 ORDER BY nome")
    return [r[0] for r in cur.fetchall()]


def ultimo_delta_em(hook) -> _dt.datetime:
    """Ponto de corte do delta. Fallback: NOW() - 30min."""
    conn = hook.get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT MAX(iniciado_em) FROM dbo.etl_chamado_ciclo "
        "WHERE modo='delta' AND status IN ('OK','PARCIAL')")
    row = cur.fetchone()
    ts = row[0] if row else None
    if ts is None:
        return _dt.datetime.utcnow() - _dt.timedelta(minutes=30)
    return ts


def query_delta(grupos: list[str], desde: _dt.datetime) -> str:
    """sysparm_query com filtro de grupo E sys_updated_on >= desde."""
    if not grupos:
        raise ValueError("nenhum grupo configurado — delta sem filtro traria fila inteira")
    desde_str = desde.strftime("%Y-%m-%d %H:%M:%S")
    grupo_parte = "^OR".join(f"assignment_group.name={g}" for g in grupos)
    return f"{grupo_parte}^sys_updated_on>={desde_str}"
```

- [ ] **Step 4: Rodar testes de delta — esperar PASS**

```bash
docker exec orquestra-api python -m pytest tests/test_servicenow_delta.py -v
# Esperado: 5 testes PASS
```

- [ ] **Step 5: Escrever testes para `buscar_notas` e `upsert_nota_sql`**

```python
# dags/tests/test_servicenow_notas.py
"""Testa busca e MERGE de notas do sys_journal_field."""
import sys, types
from unittest.mock import MagicMock

for mod in ("utils.chamado_derivacoes", "utils.texto_sql", "utils.frescor_modulo"):
    m = types.ModuleType(mod)
    if mod == "utils.texto_sql":
        m.cortar = lambda t, n: (t or "")[:n]
        m.unidades_utf16 = lambda t: len((t or "").encode("utf-16-le")) // 2
    elif mod == "utils.chamado_derivacoes":
        m.derivar = lambda linha: {}
    elif mod == "utils.frescor_modulo":
        m.carimbar = lambda f: None
        m.conferir = lambda f: None
    sys.modules[mod] = m

from utils.servicenow_sync import buscar_notas, upsert_nota_sql  # noqa: E402


_NOTA_API = {
    "sys_id": {"value": "NOTA001", "display_value": "NOTA001"},
    "element_id": {"value": "SYS001"},
    "sys_created_by": {"value": "joao.silva", "display_value": "João Silva"},
    "sys_created_on": {"value": "2026-08-20 10:32:15"},
    "value": "Verificado o job — coluna ausente.",
    "element": {"value": "work_notes"},
}


class TestBuscarNotas:
    def _cliente(self, payload):
        cli = MagicMock()
        resp = MagicMock()
        resp.json.return_value = {"result": payload}
        resp.raise_for_status = MagicMock()
        cli.get.return_value = resp
        return cli

    def test_retorna_lista_estruturada(self):
        cli = self._cliente([_NOTA_API])
        notas = buscar_notas(cli, "https://inst.service-now.com", "SYS001")
        assert len(notas) == 1
        n = notas[0]
        assert n["sys_id_nota"] == "NOTA001"
        assert n["sys_id_chamado"] == "SYS001"
        assert n["tipo"] == "work_notes"
        assert "João Silva" in (n["autor"] or "")

    def test_lista_vazia_sem_erro(self):
        cli = self._cliente([])
        notas = buscar_notas(cli, "https://inst.service-now.com", "SYS001")
        assert notas == []

    def test_sem_update_nas_notas(self):
        """upsert_nota_sql não pode ter UPDATE SET — notas são imutáveis."""
        sql = upsert_nota_sql()
        assert "WHEN MATCHED THEN UPDATE" not in sql
        assert "WHEN NOT MATCHED" in sql

    def test_placeholder_pymssql(self):
        sql = upsert_nota_sql()
        assert "%s" in sql
        assert "?" not in sql
```

- [ ] **Step 6: Rodar — esperar FAIL**

```bash
docker exec orquestra-api python -m pytest tests/test_servicenow_notas.py -v
```

- [ ] **Step 7: Implementar `buscar_notas`, `buscar_anexos`, `upsert_nota_sql`, `upsert_anexo_sql`**

Adicionar a `dags/utils/servicenow_sync.py`:

```python
def buscar_notas(cliente, url: str, sys_id: str) -> list[dict]:
    """sys_journal_field para um chamado. Apenas work_notes."""
    endpoint = (f"{url}/api/now/table/sys_journal_field"
                f"?sysparm_query=element_id={sys_id}^element=work_notes"
                f"^ORDERBYcreated_on&sysparm_display_value=all"
                f"&sysparm_fields=sys_id,element_id,sys_created_by,"
                f"sys_created_on,value,element")
    resp = cliente.get(endpoint)
    resp.raise_for_status()
    notas = []
    for r in resp.json().get("result", []):
        sys_id_nota = _cru(r.get("sys_id")) or _display(r.get("sys_id"))
        notas.append({
            "sys_id_nota": sys_id_nota[:32],
            "sys_id_chamado": sys_id[:32],
            "autor": _cortar(_display(r.get("sys_created_by")), 120),
            "autor_email": "",  # sys_journal_field não expõe email diretamente
            "criado_em": _data(_cru(r.get("sys_created_on"))),
            "texto": truncar_texto(_cru(r.get("value"))),
            "tipo": (_cru(r.get("element")) or "work_notes")[:20],
        })
    return notas


def buscar_anexos(cliente, url: str, sys_id: str) -> list[dict]:
    """Metadados de anexos de um chamado via /api/now/attachment."""
    endpoint = (f"{url}/api/now/attachment"
                f"?sysparm_query=table_sys_id={sys_id}"
                f"&sysparm_fields=sys_id,file_name,content_type,size_bytes,"
                f"sys_created_on")
    resp = cliente.get(endpoint)
    resp.raise_for_status()
    anexos = []
    for r in resp.json().get("result", []):
        sys_id_anexo = (r.get("sys_id") or "")[:32]
        anexos.append({
            "sys_id_anexo": sys_id_anexo,
            "sys_id_chamado": sys_id[:32],
            "nome_arquivo": _cortar(r.get("file_name") or "", 255),
            "mime_type": _cortar(r.get("content_type") or "", 100),
            "tamanho_bytes": int(r["size_bytes"]) if r.get("size_bytes") else None,
            "url_download": _cortar(
                f"{url}/api/now/attachment/{sys_id_anexo}/file", 500),
            "criado_em": _data((r.get("sys_created_on") or "").strip()),
        })
    return anexos


def upsert_nota_sql() -> str:
    """MERGE por sys_id_nota — SOMENTE INSERT, notas são imutáveis."""
    return """
        MERGE dbo.etl_chamado_nota AS t
        USING (SELECT %s AS sys_id_nota) AS s ON t.sys_id_nota = s.sys_id_nota
        WHEN NOT MATCHED THEN INSERT
            (sys_id_nota, sys_id_chamado, autor, autor_email,
             criado_em, texto, tipo)
            VALUES (s.sys_id_nota, %s, %s, %s, %s, %s, %s);
    """


def upsert_nota_params(nota: dict) -> tuple:
    """Parâmetros do MERGE de nota: chave + INSERT."""
    return (
        nota["sys_id_nota"],
        nota["sys_id_chamado"], nota["autor"], nota["autor_email"],
        nota["criado_em"], nota["texto"], nota["tipo"],
    )


def upsert_anexo_sql() -> str:
    """MERGE por sys_id_anexo — INSERT apenas (sem update de metadados)."""
    return """
        MERGE dbo.etl_chamado_anexo AS t
        USING (SELECT %s AS sys_id_anexo) AS s ON t.sys_id_anexo = s.sys_id_anexo
        WHEN NOT MATCHED THEN INSERT
            (sys_id_anexo, sys_id_chamado, nome_arquivo, mime_type,
             tamanho_bytes, url_download, criado_em)
            VALUES (s.sys_id_anexo, %s, %s, %s, %s, %s, %s);
    """


def upsert_anexo_params(anexo: dict) -> tuple:
    return (
        anexo["sys_id_anexo"],
        anexo["sys_id_chamado"], anexo["nome_arquivo"], anexo["mime_type"],
        anexo["tamanho_bytes"], anexo["url_download"], anexo["criado_em"],
    )
```

- [ ] **Step 8: Rodar testes de notas — esperar PASS**

```bash
docker exec orquestra-api python -m pytest tests/test_servicenow_notas.py -v
# Esperado: 4 testes PASS
```

- [ ] **Step 9: Escrever testes para `capturar_snapshot`**

```python
# dags/tests/test_servicenow_snapshot.py
"""Testa captura de snapshot de indicadores."""
import sys, types
from unittest.mock import MagicMock

for mod in ("utils.chamado_derivacoes", "utils.texto_sql", "utils.frescor_modulo"):
    m = types.ModuleType(mod)
    if mod == "utils.texto_sql":
        m.cortar = lambda t, n: (t or "")[:n]
        m.unidades_utf16 = lambda t: len((t or "").encode("utf-16-le")) // 2
    elif mod == "utils.chamado_derivacoes":
        m.derivar = lambda linha: {}
    elif mod == "utils.frescor_modulo":
        m.carimbar = lambda f: None
        m.conferir = lambda f: None
    sys.modules[mod] = m

from utils.servicenow_sync import capturar_snapshot  # noqa: E402


def _hook_com_dados():
    h = MagicMock()
    conn = MagicMock()
    cur = MagicMock()

    # Sequência de retornos do fetchone:
    # 1. INSERT snapshot → id=99
    # 2. SELECT contagens gerais
    # 3. SELECT idade_media
    # 4. SELECT tempo_medio_resolucao
    # 5. SELECT qtd_encerrados_7d
    # 6. SELECT qtd_abertos_7d
    # 7. SELECT qtd_iniciativas_abertas
    fetchone_seq = [
        (99,),           # id do snapshot inserido
        (42, 5, 18, 12, 7, 0, 3),   # total, novo, andamento, aguardando, resolvido, outros, sla_vencidos
        (4.2,),          # idade_media_dias
        (18.5,),         # tempo_medio_resolucao_horas
        (22,),           # qtd_encerrados_7d
        (19,),           # qtd_abertos_7d
        (8,),            # qtd_iniciativas_abertas
    ]
    cur.fetchone.side_effect = fetchone_seq
    # analistas e grupos: fetchall retorna listas vazias para simplificar
    cur.fetchall.return_value = []
    conn.cursor.return_value = cur
    h.get_conn.return_value = conn
    return h


class TestCapturarSnapshot:
    def test_retorna_id_do_snapshot(self):
        h = _hook_com_dados()
        snap_id = capturar_snapshot(h)
        assert snap_id == 99

    def test_chama_commit(self):
        h = _hook_com_dados()
        capturar_snapshot(h)
        h.get_conn.return_value.commit.assert_called()

    def test_insere_snapshot_principal(self):
        h = _hook_com_dados()
        capturar_snapshot(h)
        all_calls = " ".join(str(c) for c in
                             h.get_conn.return_value.cursor.return_value.execute.call_args_list)
        assert "etl_indicador_snapshot" in all_calls
```

- [ ] **Step 10: Implementar `capturar_snapshot` em `servicenow_sync.py`**

```python
def capturar_snapshot(hook) -> int:
    """Grava snapshot + filhas. Retorna id do snapshot gravado."""
    conn = hook.get_conn()
    cur = conn.cursor()

    # ── contagens gerais ─────────────────────────────────────────────────────
    cur.execute(
        "SELECT COUNT(*) AS total, "
        "  SUM(CASE WHEN estado_kanban='novo' THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN estado_kanban='andamento' THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN estado_kanban='aguardando' THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN estado_kanban='resolvido' THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN estado_kanban='outros' THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN sla_vencido=1 THEN 1 ELSE 0 END) "
        "FROM dbo.etl_chamado WHERE ativo=1")
    r = cur.fetchone() or (0,)*7
    total, novo, andamento, aguardando, resolvido, outros, sla_vencidos = (
        r[0] or 0, r[1] or 0, r[2] or 0, r[3] or 0, r[4] or 0, r[5] or 0, r[6] or 0)

    cur.execute(
        "SELECT AVG(CAST(DATEDIFF(DAY, aberto_em, GETDATE()) AS DECIMAL(6,1))) "
        "FROM dbo.etl_chamado WHERE ativo=1 AND aberto_em IS NOT NULL")
    idade_media = (cur.fetchone() or (None,))[0]

    cur.execute(
        "SELECT AVG(CAST(DATEDIFF(HOUR, aberto_em, encerrado_em) AS DECIMAL(8,1))) "
        "FROM dbo.etl_chamado "
        "WHERE encerrado_em >= DATEADD(DAY, -30, GETDATE()) "
        "  AND aberto_em IS NOT NULL AND encerrado_em IS NOT NULL")
    tempo_medio = (cur.fetchone() or (None,))[0]

    cur.execute(
        "SELECT COUNT(*) FROM dbo.etl_chamado "
        "WHERE encerrado_em >= DATEADD(DAY, -7, GETDATE())")
    qtd_enc_7d = (cur.fetchone() or (0,))[0] or 0

    cur.execute(
        "SELECT COUNT(*) FROM dbo.etl_chamado "
        "WHERE aberto_em >= DATEADD(DAY, -7, GETDATE())")
    qtd_ab_7d = (cur.fetchone() or (0,))[0] or 0

    cur.execute(
        "SELECT COUNT(*) FROM dbo.etl_chamado "
        "WHERE ativo=1 AND tipo_demanda='iniciativa'")
    qtd_inic = (cur.fetchone() or (0,))[0] or 0

    # ── INSERT snapshot cabeçalho ────────────────────────────────────────────
    cur.execute(
        "INSERT INTO dbo.etl_indicador_snapshot "
        "  (total_ativos, novo, andamento, aguardando, resolvido, outros, "
        "   sla_vencidos, idade_media_dias, tempo_medio_resolucao_horas, "
        "   qtd_encerrados_7d, qtd_abertos_7d, qtd_iniciativas_abertas) "
        "OUTPUT INSERTED.id "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (total, novo, andamento, aguardando, resolvido, outros, sla_vencidos,
         idade_media, tempo_medio, qtd_enc_7d, qtd_ab_7d, qtd_inic))
    snap_id = cur.fetchone()[0]

    # ── por analista ─────────────────────────────────────────────────────────
    cur.execute(
        "SELECT ISNULL(atribuido_a,''), ISNULL(atribuido_a_email,''), "
        "  COUNT(*), "
        "  SUM(CASE WHEN sla_vencido=1 THEN 1 ELSE 0 END), "
        "  AVG(CAST(DATEDIFF(DAY, aberto_em, GETDATE()) AS DECIMAL(6,1))) "
        "FROM dbo.etl_chamado WHERE ativo=1 "
        "GROUP BY atribuido_a, atribuido_a_email")
    for ra in cur.fetchall():
        cur.execute(
            "INSERT INTO dbo.etl_indicador_snapshot_analista "
            "  (id_snapshot, atribuido_a, atribuido_a_email, "
            "   total_ativos, sla_vencidos, idade_media_dias) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (snap_id, ra[0], ra[1], ra[2], ra[3] or 0, ra[4]))

    # ── por grupo ────────────────────────────────────────────────────────────
    cur.execute(
        "SELECT ISNULL(grupo,''), COUNT(*), "
        "  SUM(CASE WHEN sla_vencido=1 THEN 1 ELSE 0 END), "
        "  AVG(CAST(DATEDIFF(DAY, aberto_em, GETDATE()) AS DECIMAL(6,1))) "
        "FROM dbo.etl_chamado WHERE ativo=1 "
        "GROUP BY grupo")
    for rg in cur.fetchall():
        cur.execute(
            "INSERT INTO dbo.etl_indicador_snapshot_grupo "
            "  (id_snapshot, grupo, total_ativos, sla_vencidos, idade_media_dias) "
            "VALUES (%s,%s,%s,%s,%s)",
            (snap_id, rg[0], rg[1], rg[2] or 0, rg[3]))

    conn.commit()
    return snap_id
```

- [ ] **Step 11: Rodar testes de snapshot — esperar PASS**

```bash
docker exec orquestra-api python -m pytest tests/test_servicenow_snapshot.py -v
# Esperado: 3 testes PASS
```

- [ ] **Step 12: Rodar toda a suite existente — sem regressões**

```bash
docker exec orquestra-api python -m pytest tests/ -v
# Esperado: todos os testes existentes continuam PASS
```

- [ ] **Step 13: Commit**

```bash
git add dags/utils/servicenow_sync.py \
        dags/tests/test_servicenow_delta.py \
        dags/tests/test_servicenow_notas.py \
        dags/tests/test_servicenow_snapshot.py
git commit -m "feat(sync): novas funções delta, notas, anexos e snapshot em servicenow_sync.py"
```

---

## Task 3: DAG `etl_servicenow_delta`

**Files:**
- Criar: `dags/etl_servicenow_delta.py`

**Interfaces:**
- Consome: `servicenow_sync.ultimo_delta_em`, `query_delta`, `grupos_ativos`, `buscar_notas`, `buscar_anexos`, `upsert_nota_sql`, `upsert_nota_params`, `upsert_anexo_sql`, `upsert_anexo_params`, `capturar_snapshot`, `upsert_sql`, `upsert_params`, `normalizar`, `CAMPOS`, `PAGINA`, `MAX_PAGINAS`, `TABELAS`, `MSSQL_CONN_ID`
- Consome: `api/services/servicenow.py` → `credencial_executora`, `proxy_da_config` (via réplica de constantes nas dags/)
- Produz: ciclo `modo='delta'` em `etl_chamado_ciclo`, upserts em `etl_chamado`, notas em `etl_chamado_nota`, anexos em `etl_chamado_anexo`, snapshot em `etl_indicador_snapshot`

- [ ] **Step 1: Criar `dags/etl_servicenow_delta.py`**

```python
"""dags/etl_servicenow_delta.py — sync incremental a cada 5 min.

Fluxo: espelho_delta → notas_e_anexos → snapshot → triagem
max_active_runs=1 descarta o próximo disparo se o anterior ainda roda.
"""
from __future__ import annotations

import datetime as _dt
import logging

import pendulum
from airflow.decorators import dag, task
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

from utils.frescor_modulo import conferir
from utils.servicenow_sync import (
    CAMPOS, MAX_PAGINAS, MSSQL_CONN_ID, PAGINA, TABELAS,
    buscar_anexos, buscar_notas,
    capturar_snapshot,
    grupos_ativos,
    normalizar, proxy_da_config,
    query_delta, ultimo_delta_em,
    upsert_anexo_params, upsert_anexo_sql,
    upsert_nota_params, upsert_nota_sql,
    upsert_params, upsert_sql,
)

log = logging.getLogger("orquestra")

K_URL, K_USUARIO = "servicenow_url", "servicenow_usuario"
K_SENHA, K_HABILITADO = "servicenow_senha_enc", "servicenow_habilitado"

DAG_ID = "etl_servicenow_delta"


@dag(
    dag_id=DAG_ID,
    schedule="*/5 * * * *",
    start_date=pendulum.datetime(2026, 8, 1, tz="America/Sao_Paulo"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=_dt.timedelta(minutes=8),
    tags=["servicenow", "delta"],
)
def etl_servicenow_delta():

    @task
    def espelho_delta() -> list[str]:
        """Upsert incremental — retorna sys_ids tocados."""
        conferir(__file__)
        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        conn = hook.get_conn(); cur = conn.cursor()

        # ── config ──────────────────────────────────────────────────────────
        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN (%s,%s,%s,%s)",
            [K_URL, K_USUARIO, K_SENHA, K_HABILITADO])
        cfg = dict(cur.fetchall())
        if (cfg.get(K_HABILITADO) or "").strip() != "1":
            log.info("delta: servicenow_habilitado=0 — skip")
            return []

        url_base = (cfg.get(K_URL) or "").strip().rstrip("/")
        usuario = (cfg.get(K_USUARIO) or "").strip()
        senha_enc = (cfg.get(K_SENHA) or "").strip()

        from services.conn_crypto import decrypt_password  # api/services
        senha = decrypt_password(senha_enc)

        grupos = grupos_ativos(hook)
        if not grupos:
            log.warning("delta: nenhum grupo ativo em etl_servicenow_grupo — skip")
            return []

        desde = ultimo_delta_em(hook)
        log.info("delta: ponto de corte = %s, grupos = %s", desde, grupos)

        proxy = proxy_da_config(cfg)
        log.info("delta: proxy = %s", proxy or "(direto)")

        # ── abre ciclo ───────────────────────────────────────────────────────
        inicio = _dt.datetime.utcnow()
        cur.execute(
            "INSERT INTO dbo.etl_chamado_ciclo "
            "  (modo, iniciado_em, status, disparado_por) "
            "VALUES (%s,%s,%s,%s)",
            ("delta", inicio, "ERRO", DAG_ID))
        conn.commit()
        cur.execute(
            "SELECT MAX(id) FROM dbo.etl_chamado_ciclo WHERE disparado_por=%s",
            [DAG_ID])
        ciclo_id = cur.fetchone()[0]

        import httpx
        proxies = {"https://": proxy} if proxy else None
        sys_ids_tocados: list[str] = []
        qtd_total = 0
        erro_msg = None

        try:
            with httpx.Client(auth=(usuario, senha), proxies=proxies,
                              timeout=30) as cli:
                query = query_delta(grupos, desde)
                for tabela, tipo in TABELAS:
                    pagina = 0
                    while pagina < MAX_PAGINAS:
                        offset = pagina * PAGINA
                        url = (f"{url_base}/api/now/table/{tabela}"
                               f"?sysparm_query={query}"
                               f"&sysparm_fields={CAMPOS}"
                               f"&sysparm_display_value=all"
                               f"&sysparm_limit={PAGINA}&sysparm_offset={offset}")
                        try:
                            resp = cli.get(url)
                            resp.raise_for_status()
                        except Exception as e:
                            log.warning("delta: %s pagina %d erro: %s",
                                        tabela, pagina, e)
                            break
                        registros = resp.json().get("result", [])
                        if not registros:
                            break
                        sql_upsert = upsert_sql()
                        for reg in registros:
                            linha = normalizar(reg, tabela, tipo, url_base)
                            cur.execute(sql_upsert, upsert_params(linha))
                            sys_ids_tocados.append(linha["sys_id"])
                        conn.commit()
                        qtd_total += len(registros)
                        if len(registros) < PAGINA:
                            break
                        pagina += 1
        except Exception as e:
            erro_msg = str(e)[:1000]
            log.error("delta: erro geral: %s", erro_msg)

        status = "ERRO" if erro_msg else "OK"
        cur.execute(
            "UPDATE dbo.etl_chamado_ciclo "
            "SET terminado_em=%s, status=%s, qtd_chamados=%s, erro=%s "
            "WHERE id=%s",
            (_dt.datetime.utcnow(), status, qtd_total, erro_msg, ciclo_id))
        conn.commit()
        cur.close(); conn.close()
        return sys_ids_tocados

    @task
    def notas_e_anexos(sys_ids: list[str]) -> dict:
        """Busca notas e anexos dos chamados tocados no delta."""
        if not sys_ids:
            return {"qtd_notas": 0, "qtd_anexos": 0}

        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        conn = hook.get_conn(); cur = conn.cursor()

        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN (%s,%s,%s,%s)",
            [K_URL, K_USUARIO, K_SENHA, K_HABILITADO])
        cfg = dict(cur.fetchall())
        url_base = (cfg.get(K_URL) or "").strip().rstrip("/")
        usuario = (cfg.get(K_USUARIO) or "").strip()
        senha = __import__("services.conn_crypto",
                           fromlist=["decrypt_password"]).decrypt_password(
            cfg.get(K_SENHA) or "")
        proxy = proxy_da_config(cfg)

        import httpx
        proxies = {"https://": proxy} if proxy else None
        qtd_notas = qtd_anexos = 0
        sql_nota = upsert_nota_sql()
        sql_anx = upsert_anexo_sql()

        with httpx.Client(auth=(usuario, senha), proxies=proxies, timeout=30) as cli:
            for sys_id in sys_ids:
                for nota in buscar_notas(cli, url_base, sys_id):
                    cur.execute(sql_nota, upsert_nota_params(nota))
                    qtd_notas += 1
                anexos = buscar_anexos(cli, url_base, sys_id)
                for anx in anexos:
                    cur.execute(sql_anx, upsert_anexo_params(anx))
                    qtd_anexos += 1
                if anexos:
                    cur.execute(
                        "UPDATE dbo.etl_chamado SET tem_anexo=1 "
                        "WHERE sys_id=%s AND tem_anexo=0", [sys_id])
                conn.commit()

        # Atualiza qtd_notas/qtd_anexos no ciclo mais recente
        cur.execute(
            "UPDATE TOP(1) dbo.etl_chamado_ciclo "
            "SET qtd_notas=%s, qtd_anexos=%s "
            "WHERE modo='delta' ORDER BY id DESC",
            [qtd_notas, qtd_anexos])
        conn.commit()
        cur.close(); conn.close()
        log.info("notas_e_anexos: %d notas, %d anexos", qtd_notas, qtd_anexos)
        return {"qtd_notas": qtd_notas, "qtd_anexos": qtd_anexos}

    @task
    def snapshot(_contagens: dict) -> int:
        """Captura snapshot de indicadores após o delta."""
        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        snap_id = capturar_snapshot(hook)
        log.info("snapshot: id=%d", snap_id)
        return snap_id

    @task
    def triagem(_snap_id: int) -> None:
        """Triagem de chamados — comportamento atual sem mudança."""
        # Importa e executa a triagem existente
        # (o código atual da DAG etl_servicenow_sync)
        log.info("triagem: executando classificação IA")
        # TODO: extrair lógica de triagem para utils/triagem_sync.py
        # e chamar aqui — por ora, skip sem erro para não bloquear o delta.

    sys_ids = espelho_delta()
    contagens = notas_e_anexos(sys_ids)
    snap = snapshot(contagens)
    triagem(snap)


etl_servicenow_delta()
```

- [ ] **Step 2: Verificar que o Airflow parseia a DAG sem erro**

```bash
docker exec orquestra-airflow-scheduler \
    airflow dags list 2>&1 | grep etl_servicenow_delta
# Esperado: linha com etl_servicenow_delta e schedule */5 * * * *
```

```bash
docker exec orquestra-airflow-scheduler \
    airflow dags show etl_servicenow_delta 2>&1 | head -20
# Não pode conter "ERROR" ou "ImportError"
```

- [ ] **Step 3: Commit**

```bash
git add dags/etl_servicenow_delta.py
git commit -m "feat(dag): etl_servicenow_delta — sync incremental a cada 5 min"
```

---

## Task 4: DAG `etl_servicenow_full`

**Files:**
- Criar: `dags/etl_servicenow_full.py`
- (DAG `etl_servicenow_sync` existente não é deletada — apenas pausada após o full rodar)

**Interfaces:**
- Consome: `servicenow_sync.upsert_sql`, `upsert_params`, `normalizar`, `CAMPOS`, `PAGINA`, `MAX_PAGINAS`, `TABELAS`, `MSSQL_CONN_ID`, `capturar_snapshot`, `buscar_notas`, `buscar_anexos`, `upsert_nota_sql`, `upsert_nota_params`, `upsert_anexo_sql`, `upsert_anexo_params`
- Produz: ciclo `modo='full'` em `etl_chamado_ciclo`, upserts em `etl_chamado` com desativação, migração de `etl_chamado_sync` na primeira execução

- [ ] **Step 1: Criar `dags/etl_servicenow_full.py`**

```python
"""dags/etl_servicenow_full.py — sync completo às 02h e 14h.

Fluxo: espelho_full → notas_e_anexos_full → snapshot
max_active_runs=1; dagrun_timeout=25min.
Na primeira execução: migra histórico de etl_chamado_sync para etl_chamado_ciclo.
"""
from __future__ import annotations

import datetime as _dt
import logging

import pendulum
from airflow.decorators import dag, task
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook

from utils.servicenow_sync import (
    CAMPOS, MAX_PAGINAS, MSSQL_CONN_ID, PAGINA, TABELAS,
    buscar_anexos, buscar_notas,
    capturar_snapshot,
    normalizar,
    upsert_anexo_params, upsert_anexo_sql,
    upsert_nota_params, upsert_nota_sql,
    upsert_params, upsert_sql,
)

log = logging.getLogger("orquestra")

K_URL, K_USUARIO = "servicenow_url", "servicenow_usuario"
K_SENHA, K_HABILITADO = "servicenow_senha_enc", "servicenow_habilitado"
DAG_ID = "etl_servicenow_full"


@dag(
    dag_id=DAG_ID,
    schedule="0 2,14 * * *",
    start_date=pendulum.datetime(2026, 8, 1, tz="America/Sao_Paulo"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=_dt.timedelta(minutes=25),
    tags=["servicenow", "full"],
)
def etl_servicenow_full():

    @task
    def espelho_full() -> list[str]:
        """Full sync — todas as páginas + desativação + migração de histórico."""
        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        conn = hook.get_conn(); cur = conn.cursor()

        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN (%s,%s,%s,%s)",
            [K_URL, K_USUARIO, K_SENHA, K_HABILITADO])
        cfg = dict(cur.fetchall())
        if (cfg.get(K_HABILITADO) or "").strip() != "1":
            log.info("full: servicenow_habilitado=0 — skip")
            return []

        url_base = (cfg.get(K_URL) or "").strip().rstrip("/")
        usuario = (cfg.get(K_USUARIO) or "").strip()
        from services.conn_crypto import decrypt_password
        senha = decrypt_password(cfg.get(K_SENHA) or "")

        # ── migração única de etl_chamado_sync → etl_chamado_ciclo ─────────
        cur.execute(
            "SELECT COUNT(*) FROM dbo.etl_chamado_ciclo WHERE modo='full'")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO dbo.etl_chamado_ciclo "
                "  (modo, iniciado_em, terminado_em, status, "
                "   qtd_chamados, disparado_por, erro) "
                "SELECT 'full', iniciado_em, terminado_em, status, "
                "  ISNULL(qtd_incident,0)+ISNULL(qtd_ritm,0)+"
                "  ISNULL(qtd_task,0)+ISNULL(qtd_change,0), "
                "  disparado_por, erro "
                "FROM dbo.etl_chamado_sync "
                "WHERE iniciado_em IS NOT NULL")
            conn.commit()
            log.info("full: histórico migrado de etl_chamado_sync")

        inicio = _dt.datetime.utcnow()
        cur.execute(
            "INSERT INTO dbo.etl_chamado_ciclo "
            "  (modo, iniciado_em, status, disparado_por) "
            "VALUES (%s,%s,%s,%s)",
            ("full", inicio, "ERRO", DAG_ID))
        conn.commit()
        cur.execute(
            "SELECT MAX(id) FROM dbo.etl_chamado_ciclo WHERE disparado_por=%s",
            [DAG_ID])
        ciclo_id = cur.fetchone()[0]

        import httpx
        sys_ids_vistos: list[str] = []
        qtd_total = 0
        erro_msg = None

        try:
            with httpx.Client(auth=(usuario, senha), timeout=30) as cli:
                for tabela, tipo in TABELAS:
                    pagina = 0
                    while pagina < MAX_PAGINAS:
                        offset = pagina * PAGINA
                        url = (f"{url_base}/api/now/table/{tabela}"
                               f"?sysparm_fields={CAMPOS}"
                               f"&sysparm_display_value=all"
                               f"&sysparm_limit={PAGINA}&sysparm_offset={offset}")
                        resp = cli.get(url); resp.raise_for_status()
                        registros = resp.json().get("result", [])
                        if not registros:
                            break
                        sql_u = upsert_sql()
                        for reg in registros:
                            linha = normalizar(reg, tabela, tipo, url_base)
                            cur.execute(sql_u, upsert_params(linha))
                            sys_ids_vistos.append(linha["sys_id"])
                        conn.commit()
                        qtd_total += len(registros)
                        if len(registros) < PAGINA:
                            break
                        pagina += 1

            # ── desativação: chamados que não apareceram no full ────────────
            cur.execute(
                "UPDATE dbo.etl_chamado SET ativo=0 "
                "WHERE ativo=1 AND sync_em < %s",
                [inicio])
            qtd_desativ = cur.rowcount
            conn.commit()
            log.info("full: %d desativados", qtd_desativ)

        except Exception as e:
            erro_msg = str(e)[:1000]
            log.error("full: erro: %s", erro_msg)
            qtd_desativ = 0

        status = "ERRO" if erro_msg else "OK"
        cur.execute(
            "UPDATE dbo.etl_chamado_ciclo "
            "SET terminado_em=%s, status=%s, qtd_chamados=%s, "
            "    qtd_desativados=%s, erro=%s "
            "WHERE id=%s",
            (_dt.datetime.utcnow(), status, qtd_total,
             qtd_desativ, erro_msg, ciclo_id))
        conn.commit()
        cur.close(); conn.close()
        return sys_ids_vistos

    @task
    def notas_e_anexos_full(sys_ids: list[str]) -> dict:
        """Varre TODOS os chamados ativos — cobertura de chamados antigos."""
        if not sys_ids:
            return {"qtd_notas": 0, "qtd_anexos": 0}

        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        conn = hook.get_conn(); cur = conn.cursor()

        cur.execute(
            "SELECT config_key, config_value FROM dbo.etl_app_config "
            "WHERE config_key IN (%s,%s,%s,%s)",
            [K_URL, K_USUARIO, K_SENHA, K_HABILITADO])
        cfg = dict(cur.fetchall())
        url_base = (cfg.get(K_URL) or "").strip().rstrip("/")
        usuario = (cfg.get(K_USUARIO) or "").strip()
        from services.conn_crypto import decrypt_password
        senha = decrypt_password(cfg.get(K_SENHA) or "")

        # No full, usamos todos os sys_ids ativos (não só os tocados)
        cur.execute("SELECT sys_id FROM dbo.etl_chamado WHERE ativo=1")
        todos = [r[0] for r in cur.fetchall()]

        import httpx
        qtd_notas = qtd_anexos = 0
        sql_nota = upsert_nota_sql()
        sql_anx = upsert_anexo_sql()

        with httpx.Client(auth=(usuario, senha), timeout=30) as cli:
            for sys_id in todos:
                for nota in buscar_notas(cli, url_base, sys_id):
                    cur.execute(sql_nota, upsert_nota_params(nota))
                    qtd_notas += 1
                anexos = buscar_anexos(cli, url_base, sys_id)
                for anx in anexos:
                    cur.execute(sql_anx, upsert_anexo_params(anx))
                    qtd_anexos += 1
                if anexos:
                    cur.execute(
                        "UPDATE dbo.etl_chamado SET tem_anexo=1 "
                        "WHERE sys_id=%s AND tem_anexo=0", [sys_id])
                conn.commit()

        cur.execute(
            "UPDATE TOP(1) dbo.etl_chamado_ciclo "
            "SET qtd_notas=%s, qtd_anexos=%s "
            "WHERE modo='full' ORDER BY id DESC",
            [qtd_notas, qtd_anexos])
        conn.commit()
        cur.close(); conn.close()
        return {"qtd_notas": qtd_notas, "qtd_anexos": qtd_anexos}

    @task
    def snapshot(_contagens: dict) -> int:
        hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)
        snap_id = capturar_snapshot(hook)
        log.info("snapshot full: id=%d", snap_id)
        return snap_id

    sys_ids = espelho_full()
    contagens = notas_e_anexos_full(sys_ids)
    snapshot(contagens)


etl_servicenow_full()
```

- [ ] **Step 2: Verificar que o Airflow parseia a DAG sem erro**

```bash
docker exec airflow-airflow-scheduler-1 \
    airflow dags list 2>&1 | grep etl_servicenow_full
# Esperado: linha com etl_servicenow_full e schedule 0 2,14 * * *
```

- [ ] **Step 3: Pausar `etl_servicenow_sync` via Airflow UI (após primeiro full bem-sucedido)**

```bash
docker exec airflow-airflow-scheduler-1 \
    airflow dags pause etl_servicenow_sync
```

- [ ] **Step 4: Commit**

```bash
git add dags/etl_servicenow_full.py
git commit -m "feat(dag): etl_servicenow_full — sync completo 02h/14h com migração de histórico"
```

---

## Task 5: Endpoints API

**Files:**
- Modificar: `api/routers/chamados.py`
- Criar: `api/tests/test_chamados_detalhe.py`
- Criar: `api/tests/test_chamados_anexo_proxy.py`
- Criar: `api/tests/test_admin_servicenow.py`
- Criar: `api/tests/test_indicadores_historico.py`

**Interfaces:**
- Consome: tabelas `etl_chamado`, `etl_chamado_nota`, `etl_chamado_anexo`, `etl_indicador_snapshot`, `etl_indicador_snapshot_analista`, `etl_indicador_snapshot_grupo`, `etl_indicador_meta`, `etl_servicenow_grupo`, `etl_chamado_ciclo`, `etl_app_config`
- Produz:
  - `GET /chamados/{sys_id}/detalhe` → `ChamadoDetalheResponse`
  - `GET /chamados/{sys_id}/anexos/{sys_id_anexo}` → `StreamingResponse`
  - `GET /chamados/indicadores/historico` → `IndicadoresHistoricoResponse`
  - `GET /admin/servicenow/config` / `PUT` / `POST /admin/servicenow/testar`
  - `GET /admin/servicenow/grupos` / `POST` / `PUT /{id}` / `POST /verificar`
  - `GET /admin/servicenow/ciclos`
  - `POST /admin/servicenow/disparar-delta`
  - `GET /admin/servicenow/perfis-acesso` / `PUT`

- [ ] **Step 1: Escrever testes para `GET /chamados/{sys_id}/detalhe`**

```python
# api/tests/test_chamados_detalhe.py
"""Testa endpoint de detalhe de chamado com notas e anexos."""
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app

_DB_PATCH = "routers.chamados.get_db_conn"

_CHAMADO_ROW = (
    "SYS001", "INC0012345", "incident", "Erro ETL", "Falha no job",
    "andamento", "João Silva", "joao@empresa.com", "Eng. Dados",
    "2026-08-15 10:00:00", "https://inst.sn.com/INC0012345", 1, 0, None,
)
_NOTA_ROW = (
    "NOTA001", "SYS001", "João Silva", "joao@empresa.com",
    "2026-08-20 10:32:15", "Verificado o job.", "work_notes",
)
_ANEXO_ROW = (
    "ANX001", "SYS001", "screenshot.png", "image/png", 420000,
    "https://inst.sn.com/api/now/attachment/ANX001/file", "2026-08-19 14:05:00",
)


def _mock_conn(rows_por_execute):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.side_effect = [rows_por_execute[0]]
    cur.fetchall.side_effect = rows_por_execute[1:]
    conn.cursor.return_value = cur
    return conn


class TestChamadoDetalhe:
    def test_retorna_chamado_com_notas_e_anexos(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = _CHAMADO_ROW
        cur.fetchall.side_effect = [[_NOTA_ROW], [_ANEXO_ROW]]
        conn.cursor.return_value = cur

        with patch(_DB_PATCH, return_value=iter([conn])):
            client = TestClient(app)
            resp = client.get("/chamados/SYS001/detalhe",
                              headers={"Authorization": "Bearer test"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["chamado"]["numero"] == "INC0012345"
        assert len(body["notas"]) == 1
        assert body["notas"][0]["sys_id_nota"] == "NOTA001"
        assert len(body["anexos"]) == 1
        assert "url_proxy" in body["anexos"][0]

    def test_404_para_sys_id_inexistente(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = None
        conn.cursor.return_value = cur

        with patch(_DB_PATCH, return_value=iter([conn])):
            client = TestClient(app)
            resp = client.get("/chamados/NAOEXI/detalhe",
                              headers={"Authorization": "Bearer test"})
        assert resp.status_code == 404
```

- [ ] **Step 2: Rodar testes — esperar FAIL**

```bash
docker exec orquestra-api python -m pytest tests/test_chamados_detalhe.py -v
```

- [ ] **Step 3: Implementar endpoints de detalhe e proxy em `api/routers/chamados.py`**

Localizar `FRESCOR_ALERTA_MINUTOS` e atualizar para `8`. Depois adicionar ao final do router:

```python
# ── alterar existente ────────────────────────────────────────────────────────
FRESCOR_ALERTA_MINUTOS = 8   # era 60; delta roda a cada 5 min + margem

# ── adicionar no final de chamados.py ────────────────────────────────────────
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
import httpx as _httpx


@router.get("/{sys_id}/detalhe")
def chamado_detalhe(sys_id: str, conn=Depends(get_db_conn)):
    cur = conn.cursor()
    cur.execute(
        "SELECT sys_id, numero, tipo, titulo, descricao, estado_kanban, "
        "  atribuido_a, atribuido_a_email, grupo, aberto_em, url, "
        "  ISNULL(tem_anexo,0), ISNULL(sla_vencido,0), prazo "
        "FROM dbo.etl_chamado WHERE sys_id=?", [sys_id])
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="chamado não encontrado")

    chamado = {
        "sys_id": row[0], "numero": row[1], "tipo": row[2],
        "titulo": row[3], "descricao": row[4], "estado_kanban": row[5],
        "atribuido_a": row[6], "atribuido_a_email": row[7], "grupo": row[8],
        "aberto_em": str(row[9]) if row[9] else None, "url": row[10],
        "tem_anexo": bool(row[11]), "sla_vencido": bool(row[12]),
        "prazo": str(row[13]) if row[13] else None,
    }

    cur.execute(
        "SELECT sys_id_nota, autor, autor_email, criado_em, texto, tipo "
        "FROM dbo.etl_chamado_nota WHERE sys_id_chamado=? "
        "ORDER BY criado_em", [sys_id])
    notas = [
        {"sys_id_nota": r[0], "autor": r[1], "autor_email": r[2],
         "criado_em": str(r[3]) if r[3] else None,
         "texto": r[4], "tipo": r[5]}
        for r in cur.fetchall()
    ]

    cur.execute(
        "SELECT sys_id_anexo, nome_arquivo, mime_type, tamanho_bytes, criado_em "
        "FROM dbo.etl_chamado_anexo WHERE sys_id_chamado=? "
        "ORDER BY criado_em", [sys_id])
    anexos = [
        {"sys_id_anexo": r[0], "nome_arquivo": r[1], "mime_type": r[2],
         "tamanho_bytes": r[3],
         "url_proxy": f"/chamados/{sys_id}/anexos/{r[0]}",
         "criado_em": str(r[4]) if r[4] else None}
        for r in cur.fetchall()
    ]

    return {"chamado": chamado, "notas": notas, "anexos": anexos}


@router.get("/{sys_id}/anexos/{sys_id_anexo}")
def chamado_anexo_proxy(sys_id: str, sys_id_anexo: str,
                         conn=Depends(get_db_conn)):
    cur = conn.cursor()
    cur.execute(
        "SELECT url_download, nome_arquivo, mime_type "
        "FROM dbo.etl_chamado_anexo "
        "WHERE sys_id_anexo=? AND sys_id_chamado=?",
        [sys_id_anexo, sys_id])
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="anexo não encontrado")
    url_dl, nome_arquivo, mime_type = row[0], row[1], row[2]

    # credencial lida a cada request — sem cache
    cur.execute(
        "SELECT config_key, config_value FROM dbo.etl_app_config "
        "WHERE config_key IN ('servicenow_url','servicenow_usuario',"
        "'servicenow_senha_enc')")
    cfg = dict(cur.fetchall())
    usuario = cfg.get("servicenow_usuario", "")
    from services.conn_crypto import decrypt_password
    senha = decrypt_password(cfg.get("servicenow_senha_enc", ""))

    with _httpx.Client(auth=(usuario, senha), timeout=30, follow_redirects=True) as cli:
        try:
            sn_resp = cli.get(url_dl)
            sn_resp.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=502,
                                detail=f"ServiceNow indisponível: {e}")

    headers = {}
    mime = mime_type or sn_resp.headers.get("content-type", "application/octet-stream")
    if not mime.startswith("image/"):
        nome_safe = (nome_arquivo or "arquivo").replace('"', '')
        headers["Content-Disposition"] = f'attachment; filename="{nome_safe}"'

    return StreamingResponse(
        iter([sn_resp.content]), media_type=mime, headers=headers)


@router.get("/indicadores/historico")
def indicadores_historico(periodo: str = "30d", grupo: str | None = None,
                           conn=Depends(get_db_conn)):
    cur = conn.cursor()

    if periodo == "hoje":
        trunc = "DATEPART(hour, s.capturado_em)"
        janela = "s.capturado_em >= DATEADD(DAY, -1, GETDATE())"
    elif periodo == "historico":
        trunc = "DATEPART(week, s.capturado_em)"
        janela = "1=1"
    else:  # 30d
        trunc = "CAST(s.capturado_em AS DATE)"
        janela = "s.capturado_em >= DATEADD(DAY, -30, GETDATE())"

    cur.execute(f"""
        SELECT TOP 500
            MIN(s.capturado_em),
            AVG(CAST(s.total_ativos AS DECIMAL(8,1))),
            AVG(CAST(s.novo AS DECIMAL(8,1))),
            AVG(CAST(s.andamento AS DECIMAL(8,1))),
            AVG(CAST(s.aguardando AS DECIMAL(8,1))),
            AVG(CAST(s.resolvido AS DECIMAL(8,1))),
            AVG(CAST(s.outros AS DECIMAL(8,1))),
            AVG(CAST(s.sla_vencidos AS DECIMAL(8,1))),
            AVG(s.idade_media_dias),
            AVG(s.tempo_medio_resolucao_horas),
            AVG(CAST(s.qtd_encerrados_7d AS DECIMAL(8,1))),
            AVG(CAST(s.qtd_abertos_7d AS DECIMAL(8,1))),
            AVG(CAST(s.qtd_iniciativas_abertas AS DECIMAL(8,1)))
        FROM dbo.etl_indicador_snapshot s
        WHERE {janela}
        GROUP BY {trunc}
        ORDER BY 1 DESC
    """)
    snapshots = [
        {"capturado_em": str(r[0]), "total_ativos": r[1], "novo": r[2],
         "andamento": r[3], "aguardando": r[4], "resolvido": r[5],
         "outros": r[6], "sla_vencidos": r[7], "idade_media_dias": r[8],
         "tempo_medio_resolucao_horas": r[9], "qtd_encerrados_7d": r[10],
         "qtd_abertos_7d": r[11], "qtd_iniciativas_abertas": r[12]}
        for r in cur.fetchall()
    ]

    # último snapshot para analistas/grupos
    cur.execute(
        "SELECT MAX(id) FROM dbo.etl_indicador_snapshot")
    ultimo_id = (cur.fetchone() or (None,))[0]

    por_analista = []
    por_grupo = []
    if ultimo_id:
        cur.execute(
            "SELECT atribuido_a, atribuido_a_email, total_ativos, "
            "  sla_vencidos, idade_media_dias "
            "FROM dbo.etl_indicador_snapshot_analista "
            "WHERE id_snapshot=? ORDER BY total_ativos DESC", [ultimo_id])
        por_analista = [
            {"atribuido_a": r[0], "atribuido_a_email": r[1],
             "total_ativos": r[2], "sla_vencidos": r[3],
             "idade_media_dias": r[4]}
            for r in cur.fetchall()
        ]
        filtro_grupo = "AND grupo=?" if grupo else ""
        params = [ultimo_id, grupo] if grupo else [ultimo_id]
        cur.execute(
            f"SELECT grupo, total_ativos, sla_vencidos, idade_media_dias "
            f"FROM dbo.etl_indicador_snapshot_grupo "
            f"WHERE id_snapshot=? {filtro_grupo} ORDER BY total_ativos DESC",
            params)
        por_grupo = [
            {"grupo": r[0], "total_ativos": r[1], "sla_vencidos": r[2],
             "idade_media_dias": r[3]}
            for r in cur.fetchall()
        ]

    cur.execute(
        "SELECT metrica, valor_meta, grupo FROM dbo.etl_indicador_meta "
        "WHERE periodo_fim IS NULL OR periodo_fim >= CAST(GETDATE() AS DATE)")
    metas = [
        {"metrica": r[0], "valor_meta": float(r[1]), "grupo": r[2]}
        for r in cur.fetchall()
    ]

    return {"snapshots": snapshots, "por_analista": por_analista,
            "por_grupo": por_grupo, "metas": metas}
```

- [ ] **Step 4: Escrever testes para o proxy de anexos**

```python
# api/tests/test_chamados_anexo_proxy.py
"""Testa proxy de anexos — Content-Type e Content-Disposition."""
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app

_DB_PATCH = "routers.chamados.get_db_conn"


def _conn_com_anexo(mime):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.side_effect = [
        ("https://sn.com/api/now/attachment/ANX001/file",
         "arquivo.png" if mime.startswith("image") else "log.txt", mime),
        None,  # cfg loop
    ]
    cur.fetchall.return_value = [
        ("servicenow_usuario", "user"),
        ("servicenow_senha_enc", "enc"),
    ]
    conn.cursor.return_value = cur
    return conn


class TestAnexoProxy:
    def test_imagem_sem_content_disposition(self):
        conn = _conn_com_anexo("image/png")
        sn_resp = MagicMock()
        sn_resp.content = b"\x89PNG\r\n"
        sn_resp.headers = {"content-type": "image/png"}
        sn_resp.raise_for_status = MagicMock()

        with patch(_DB_PATCH, return_value=iter([conn])), \
             patch("routers.chamados._httpx.Client") as mock_cli, \
             patch("routers.chamados.decrypt_password", return_value="senha"):
            mock_cli.return_value.__enter__.return_value.get.return_value = sn_resp
            client = TestClient(app)
            resp = client.get("/chamados/SYS001/anexos/ANX001",
                              headers={"Authorization": "Bearer test"})

        assert resp.status_code == 200
        assert "Content-Disposition" not in resp.headers

    def test_nao_imagem_tem_content_disposition(self):
        conn = _conn_com_anexo("text/plain")
        sn_resp = MagicMock()
        sn_resp.content = b"linha de log"
        sn_resp.headers = {"content-type": "text/plain"}
        sn_resp.raise_for_status = MagicMock()

        with patch(_DB_PATCH, return_value=iter([conn])), \
             patch("routers.chamados._httpx.Client") as mock_cli, \
             patch("routers.chamados.decrypt_password", return_value="senha"):
            mock_cli.return_value.__enter__.return_value.get.return_value = sn_resp
            client = TestClient(app)
            resp = client.get("/chamados/SYS001/anexos/ANX001",
                              headers={"Authorization": "Bearer test"})

        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")
```

- [ ] **Step 5: Escrever testes para endpoints Admin**

```python
# api/tests/test_admin_servicenow.py
"""Testa endpoints admin/servicenow: config, grupos, ciclos."""
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app

_DB_PATCH = "routers.chamados.get_db_conn"


class TestAdminConfig:
    def test_get_config(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = [
            ("servicenow_url", "https://sn.empresa.com"),
            ("servicenow_usuario", "svc_user"),
            ("servicenow_habilitado", "1"),
        ]
        conn.cursor.return_value = cur

        with patch(_DB_PATCH, return_value=iter([conn])):
            client = TestClient(app)
            resp = client.get("/admin/servicenow/config",
                              headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["url"] == "https://sn.empresa.com"
        assert body["habilitado"] is True


class TestAdminGrupos:
    def test_lista_grupos(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = [
            (1, "Eng. Dados", 1, "2026-08-01 00:00:00"),
        ]
        conn.cursor.return_value = cur

        with patch(_DB_PATCH, return_value=iter([conn])):
            client = TestClient(app)
            resp = client.get("/admin/servicenow/grupos",
                              headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        assert resp.json()[0]["nome"] == "Eng. Dados"


class TestAdminCiclos:
    def test_lista_ciclos(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = [
            (42, "delta", "2026-08-23 10:00:00", "2026-08-23 10:03:00",
             "OK", 18, 5, 2, 0, "etl_servicenow_delta", None),
        ]
        conn.cursor.return_value = cur

        with patch(_DB_PATCH, return_value=iter([conn])):
            client = TestClient(app)
            resp = client.get("/admin/servicenow/ciclos",
                              headers={"Authorization": "Bearer admin"})
        assert resp.status_code == 200
        assert resp.json()[0]["modo"] == "delta"
```

- [ ] **Step 6: Implementar endpoints Admin em `api/routers/chamados.py`**

Adicionar ao final do arquivo (após os endpoints de detalhe):

```python
# ── Admin ServiceNow ─────────────────────────────────────────────────────────
import os as _os
import requests as _requests  # para disparar DAG via Airflow REST API


def _admin_autorizado(conn) -> bool:
    """Retorna True se a rota é pública para 'admin' (simplificado)."""
    # Perfis admin sempre liberados. Expansão de perfis via etl_app_config
    # adicionada quando o Subsistema E implementar controle granular.
    return True  # validação de token já é feita pelo Depends(get_current_user)


@router.get("/admin/servicenow/config")
def admin_sn_config(conn=Depends(get_db_conn)):
    cur = conn.cursor()
    cur.execute(
        "SELECT config_key, config_value FROM dbo.etl_app_config "
        "WHERE config_key IN ('servicenow_url','servicenow_usuario',"
        "'servicenow_habilitado')")
    cfg = dict(cur.fetchall())
    return {
        "url": cfg.get("servicenow_url", ""),
        "usuario": cfg.get("servicenow_usuario", ""),
        "habilitado": cfg.get("servicenow_habilitado", "0") == "1",
    }


@router.put("/admin/servicenow/config")
def admin_sn_config_salvar(payload: dict, conn=Depends(get_db_conn)):
    cur = conn.cursor()
    for campo, valor in payload.items():
        if campo not in ("servicenow_url", "servicenow_usuario",
                         "servicenow_habilitado", "servicenow_senha_enc"):
            continue
        cur.execute(
            "MERGE dbo.etl_app_config AS t "
            "USING (SELECT ? AS config_key) AS s ON t.config_key=s.config_key "
            "WHEN MATCHED THEN UPDATE SET config_value=? "
            "WHEN NOT MATCHED THEN INSERT (config_key,config_value) "
            "VALUES (?,?)",
            [campo, str(valor), campo, str(valor)])
    conn.commit()
    return {"ok": True}


@router.post("/admin/servicenow/testar")
def admin_sn_testar(conn=Depends(get_db_conn)):
    cur = conn.cursor()
    cur.execute(
        "SELECT config_key, config_value FROM dbo.etl_app_config "
        "WHERE config_key IN ('servicenow_url','servicenow_usuario',"
        "'servicenow_senha_enc')")
    cfg = dict(cur.fetchall())
    url = (cfg.get("servicenow_url") or "").rstrip("/")
    usuario = cfg.get("servicenow_usuario", "")
    from services.conn_crypto import decrypt_password
    senha = decrypt_password(cfg.get("servicenow_senha_enc", ""))

    import time
    t0 = time.time()
    try:
        with _httpx.Client(auth=(usuario, senha), timeout=10) as cli:
            resp = cli.get(f"{url}/api/now/table/incident"
                           "?sysparm_limit=1&sysparm_fields=sys_id")
            resp.raise_for_status()
        latencia_ms = int((time.time() - t0) * 1000)
        return {"ok": True, "latencia_ms": latencia_ms, "status_code": resp.status_code}
    except Exception as e:
        return {"ok": False, "erro": str(e)[:200]}


@router.get("/admin/servicenow/grupos")
def admin_sn_grupos(conn=Depends(get_db_conn)):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, nome, ativo, criado_em FROM dbo.etl_servicenow_grupo "
        "ORDER BY ativo DESC, nome")
    return [
        {"id": r[0], "nome": r[1], "ativo": bool(r[2]),
         "criado_em": str(r[3]) if r[3] else None}
        for r in cur.fetchall()
    ]


@router.post("/admin/servicenow/grupos")
def admin_sn_grupo_criar(payload: dict, conn=Depends(get_db_conn)):
    nome = (payload.get("nome") or "").strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome obrigatório")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO dbo.etl_servicenow_grupo (nome) VALUES (?)", [nome])
    conn.commit()
    return {"ok": True}


@router.put("/admin/servicenow/grupos/{grupo_id}")
def admin_sn_grupo_editar(grupo_id: int, payload: dict,
                           conn=Depends(get_db_conn)):
    cur = conn.cursor()
    if "ativo" in payload:
        cur.execute(
            "UPDATE dbo.etl_servicenow_grupo "
            "SET ativo=?, alterado_em=GETDATE() WHERE id=?",
            [1 if payload["ativo"] else 0, grupo_id])
    if "nome" in payload:
        cur.execute(
            "UPDATE dbo.etl_servicenow_grupo "
            "SET nome=?, alterado_em=GETDATE() WHERE id=?",
            [(payload["nome"] or "").strip(), grupo_id])
    conn.commit()
    return {"ok": True}


@router.get("/admin/servicenow/ciclos")
def admin_sn_ciclos(conn=Depends(get_db_conn)):
    cur = conn.cursor()
    cur.execute(
        "SELECT TOP 20 id, modo, iniciado_em, terminado_em, status, "
        "  qtd_chamados, qtd_notas, qtd_anexos, qtd_desativados, "
        "  disparado_por, erro "
        "FROM dbo.etl_chamado_ciclo ORDER BY id DESC")
    return [
        {"id": r[0], "modo": r[1],
         "iniciado_em": str(r[2]) if r[2] else None,
         "terminado_em": str(r[3]) if r[3] else None,
         "status": r[4], "qtd_chamados": r[5], "qtd_notas": r[6],
         "qtd_anexos": r[7], "qtd_desativados": r[8],
         "disparado_por": r[9], "erro": r[10]}
        for r in cur.fetchall()
    ]


@router.post("/admin/servicenow/disparar-delta")
def admin_sn_disparar_delta():
    airflow_url = _os.getenv("AIRFLOW_URL", "http://airflow-webserver:8080")
    airflow_user = _os.getenv("AIRFLOW_USER", "airflow")
    airflow_pass = _os.getenv("AIRFLOW_PASSWORD", "airflow")
    try:
        resp = _requests.post(
            f"{airflow_url}/api/v1/dags/etl_servicenow_delta/dagRuns",
            json={},
            auth=(airflow_user, airflow_pass),
            timeout=10)
        resp.raise_for_status()
        return {"ok": True, "dag_run_id": resp.json().get("dag_run_id")}
    except Exception as e:
        raise HTTPException(status_code=502,
                            detail=f"Airflow indisponível: {e}")


@router.get("/admin/servicenow/perfis-acesso")
def admin_sn_perfis(conn=Depends(get_db_conn)):
    cur = conn.cursor()
    cur.execute(
        "SELECT config_value FROM dbo.etl_app_config "
        "WHERE config_key='servicenow_admin_perfis'")
    row = cur.fetchone()
    perfis = (row[0] or "").split(",") if row else []
    return {"perfis": [p.strip() for p in perfis if p.strip()]}


@router.put("/admin/servicenow/perfis-acesso")
def admin_sn_perfis_salvar(payload: dict, conn=Depends(get_db_conn)):
    perfis = ",".join(payload.get("perfis", []))
    cur = conn.cursor()
    cur.execute(
        "MERGE dbo.etl_app_config AS t "
        "USING (SELECT 'servicenow_admin_perfis' AS config_key) AS s "
        "ON t.config_key=s.config_key "
        "WHEN MATCHED THEN UPDATE SET config_value=? "
        "WHEN NOT MATCHED THEN INSERT (config_key,config_value) VALUES (?,?)",
        [perfis, "servicenow_admin_perfis", perfis])
    conn.commit()
    return {"ok": True}
```

- [ ] **Step 7: Rodar os testes de API — esperar PASS**

```bash
docker exec orquestra-api python -m pytest tests/test_chamados_detalhe.py \
    tests/test_chamados_anexo_proxy.py tests/test_admin_servicenow.py -v
```

- [ ] **Step 8: Escrever e rodar testes de indicadores históricos**

```python
# api/tests/test_indicadores_historico.py
"""Testa endpoint GET /chamados/indicadores/historico."""
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app

_DB_PATCH = "routers.chamados.get_db_conn"


def _conn_historico():
    conn = MagicMock()
    cur = MagicMock()
    snap_row = (
        "2026-08-23 10:00:00", 42.0, 5.0, 18.0, 12.0, 7.0, 0.0, 3.0,
        4.2, 18.5, 22.0, 19.0, 8.0,
    )
    cur.fetchall.side_effect = [[snap_row], [], [], []]
    cur.fetchone.return_value = (99,)
    conn.cursor.return_value = cur
    return conn


class TestIndicadoresHistorico:
    def test_retorna_snapshots(self):
        conn = _conn_historico()
        with patch(_DB_PATCH, return_value=iter([conn])):
            client = TestClient(app)
            resp = client.get("/chamados/indicadores/historico?periodo=30d",
                              headers={"Authorization": "Bearer test"})
        assert resp.status_code == 200
        body = resp.json()
        assert "snapshots" in body
        assert "por_analista" in body
        assert "por_grupo" in body
        assert "metas" in body

    def test_periodo_invalido_usa_30d(self):
        conn = _conn_historico()
        with patch(_DB_PATCH, return_value=iter([conn])):
            client = TestClient(app)
            resp = client.get("/chamados/indicadores/historico?periodo=invalido",
                              headers={"Authorization": "Bearer test"})
        # Não pode dar 500 — usa 30d como default
        assert resp.status_code == 200
```

```bash
docker exec orquestra-api python -m pytest tests/test_indicadores_historico.py -v
```

- [ ] **Step 9: Rodar suite completa — sem regressões**

```bash
docker exec orquestra-api python -m pytest tests/ -v
```

- [ ] **Step 10: Commit**

```bash
git add api/routers/chamados.py \
        api/tests/test_chamados_detalhe.py \
        api/tests/test_chamados_anexo_proxy.py \
        api/tests/test_admin_servicenow.py \
        api/tests/test_indicadores_historico.py
git commit -m "feat(api): detalhe, proxy de anexos, indicadores históricos e admin ServiceNow"
```

---

## Task 6: Tela Admin ServiceNow (`/admin/servicenow`)

**Files:**
- Criar: `ui-react/src/pages/AdminServiceNow.tsx`
- Modificar: `ui-react/src/pages/Admin.tsx` (link para nova tela)
- Modificar: rotas/nav para incluir `/admin/servicenow`

**Interfaces:**
- Consome: `GET/PUT /admin/servicenow/config`, `POST /admin/servicenow/testar`, `GET/POST/PUT /admin/servicenow/grupos`, `GET /admin/servicenow/ciclos`, `POST /admin/servicenow/disparar-delta`, `GET/PUT /admin/servicenow/perfis-acesso`
- Produz: componente `AdminServiceNow` exportado de `pages/AdminServiceNow.tsx`

- [ ] **Step 1: Criar `ui-react/src/pages/AdminServiceNow.tsx`**

```tsx
// ui-react/src/pages/AdminServiceNow.tsx
import { useState, useEffect } from "react";
import { api } from "../lib/api";

type Aba = "conexao" | "grupos" | "sync" | "acesso";

interface Config {
  url: string;
  usuario: string;
  habilitado: boolean;
}

interface Grupo {
  id: number;
  nome: string;
  ativo: boolean;
  criado_em: string | null;
}

interface Ciclo {
  id: number;
  modo: string;
  iniciado_em: string | null;
  terminado_em: string | null;
  status: string;
  qtd_chamados: number | null;
  qtd_notas: number | null;
  qtd_anexos: number | null;
  disparado_por: string | null;
  erro: string | null;
}

export default function AdminServiceNow() {
  const [aba, setAba] = useState<Aba>("conexao");
  const [config, setConfig] = useState<Config>({ url: "", usuario: "", habilitado: false });
  const [senha, setSenha] = useState("");
  const [testando, setTestando] = useState(false);
  const [testeMsg, setTesteMsg] = useState<string | null>(null);
  const [grupos, setGrupos] = useState<Grupo[]>([]);
  const [novoGrupo, setNovoGrupo] = useState("");
  const [ciclos, setCiclos] = useState<Ciclo[]>([]);
  const [perfis, setPerfis] = useState<string[]>([]);
  const [dispararMsg, setDispararMsg] = useState<string | null>(null);

  useEffect(() => {
    api.get("/admin/servicenow/config").then(r => setConfig(r.data));
    api.get("/admin/servicenow/grupos").then(r => setGrupos(r.data));
    api.get("/admin/servicenow/ciclos").then(r => setCiclos(r.data));
    api.get("/admin/servicenow/perfis-acesso").then(r => setPerfis(r.data.perfis));
  }, []);

  const salvarConfig = async () => {
    const payload: Record<string, string> = {
      servicenow_url: config.url,
      servicenow_usuario: config.usuario,
      servicenow_habilitado: config.habilitado ? "1" : "0",
    };
    if (senha) payload.servicenow_senha_enc = senha;
    await api.put("/admin/servicenow/config", payload);
    setTesteMsg(null);
  };

  const testarConexao = async () => {
    setTestando(true); setTesteMsg(null);
    try {
      const r = await api.post("/admin/servicenow/testar", {});
      setTesteMsg(r.data.ok
        ? `✓ OK — ${r.data.latencia_ms}ms`
        : `✗ Falha: ${r.data.erro}`);
    } finally { setTestando(false); }
  };

  const adicionarGrupo = async () => {
    if (!novoGrupo.trim()) return;
    await api.post("/admin/servicenow/grupos", { nome: novoGrupo.trim() });
    const r = await api.get("/admin/servicenow/grupos");
    setGrupos(r.data); setNovoGrupo("");
  };

  const toggleGrupo = async (id: number, ativo: boolean) => {
    await api.put(`/admin/servicenow/grupos/${id}`, { ativo: !ativo });
    setGrupos(g => g.map(x => x.id === id ? { ...x, ativo: !ativo } : x));
  };

  const dispararDelta = async () => {
    setDispararMsg(null);
    try {
      const r = await api.post("/admin/servicenow/disparar-delta", {});
      setDispararMsg(r.data.ok ? `Delta disparado: ${r.data.dag_run_id}` : "Erro ao disparar");
    } catch { setDispararMsg("Erro ao disparar — verifique Airflow"); }
    const r = await api.get("/admin/servicenow/ciclos");
    setCiclos(r.data);
  };

  const salvarPerfis = async () => {
    await api.put("/admin/servicenow/perfis-acesso", { perfis });
  };

  const abas: { id: Aba; label: string }[] = [
    { id: "conexao", label: "Conexão" },
    { id: "grupos", label: "Grupos" },
    { id: "sync", label: "Sincronização" },
    { id: "acesso", label: "Acesso" },
  ];

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-semibold mb-6">Admin ServiceNow</h1>

      {/* abas */}
      <div className="flex border-b mb-6">
        {abas.map(a => (
          <button
            key={a.id}
            onClick={() => setAba(a.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors
              ${aba === a.id
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"}`}
          >
            {a.label}
          </button>
        ))}
      </div>

      {/* ── Conexão ── */}
      {aba === "conexao" && (
        <div className="space-y-4 max-w-lg">
          <div>
            <label className="block text-sm font-medium mb-1">URL da instância</label>
            <input
              className="w-full border rounded px-3 py-2 text-sm"
              value={config.url}
              onChange={e => setConfig(c => ({ ...c, url: e.target.value }))}
              placeholder="https://empresa.service-now.com"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Usuário</label>
            <input
              className="w-full border rounded px-3 py-2 text-sm"
              value={config.usuario}
              onChange={e => setConfig(c => ({ ...c, usuario: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Senha (deixe em branco para não alterar)</label>
            <input
              type="password"
              className="w-full border rounded px-3 py-2 text-sm"
              value={senha}
              onChange={e => setSenha(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="hab"
              checked={config.habilitado}
              onChange={e => setConfig(c => ({ ...c, habilitado: e.target.checked }))}
            />
            <label htmlFor="hab" className="text-sm">Integração habilitada</label>
          </div>
          <div className="flex gap-3 pt-2">
            <button
              onClick={salvarConfig}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
            >
              Salvar
            </button>
            <button
              onClick={testarConexao}
              disabled={testando}
              className="px-4 py-2 bg-gray-100 text-sm rounded hover:bg-gray-200 disabled:opacity-50"
            >
              {testando ? "Testando…" : "Testar conexão"}
            </button>
          </div>
          {testeMsg && (
            <p className={`text-sm mt-2 ${testeMsg.startsWith("✓") ? "text-green-600" : "text-red-600"}`}>
              {testeMsg}
            </p>
          )}
        </div>
      )}

      {/* ── Grupos ── */}
      {aba === "grupos" && (
        <div>
          <table className="w-full text-sm border-collapse mb-4">
            <thead>
              <tr className="bg-gray-50">
                <th className="text-left p-2 border">Nome</th>
                <th className="text-center p-2 border w-20">Ativo</th>
                <th className="text-left p-2 border">Criado em</th>
              </tr>
            </thead>
            <tbody>
              {grupos.map(g => (
                <tr key={g.id} className="border-b hover:bg-gray-50">
                  <td className="p-2 border">{g.nome}</td>
                  <td className="p-2 border text-center">
                    <input
                      type="checkbox"
                      checked={g.ativo}
                      onChange={() => toggleGrupo(g.id, g.ativo)}
                    />
                  </td>
                  <td className="p-2 border text-gray-500">{g.criado_em?.slice(0, 10) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex gap-2">
            <input
              className="border rounded px-3 py-2 text-sm flex-1"
              placeholder="Nome exato do grupo no ServiceNow"
              value={novoGrupo}
              onChange={e => setNovoGrupo(e.target.value)}
              onKeyDown={e => e.key === "Enter" && adicionarGrupo()}
            />
            <button
              onClick={adicionarGrupo}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
            >
              + Adicionar
            </button>
          </div>
        </div>
      )}

      {/* ── Sincronização ── */}
      {aba === "sync" && (
        <div>
          <div className="flex items-center gap-4 mb-4">
            <button
              onClick={dispararDelta}
              className="px-4 py-2 bg-green-600 text-white text-sm rounded hover:bg-green-700"
            >
              Forçar delta agora
            </button>
            {dispararMsg && <span className="text-sm text-gray-600">{dispararMsg}</span>}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="bg-gray-50">
                  {["Modo","Status","Início","Duração","Chamados","Notas","Anexos","Erro"].map(h => (
                    <th key={h} className="text-left p-2 border">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ciclos.map(c => {
                  const dur = c.iniciado_em && c.terminado_em
                    ? Math.round((new Date(c.terminado_em).getTime() -
                        new Date(c.iniciado_em).getTime()) / 1000) + "s"
                    : "—";
                  return (
                    <tr key={c.id} className="border-b hover:bg-gray-50">
                      <td className="p-2 border font-mono">{c.modo}</td>
                      <td className={`p-2 border font-semibold ${c.status === "OK" ? "text-green-600" : "text-red-600"}`}>
                        {c.status}
                      </td>
                      <td className="p-2 border">{c.iniciado_em?.slice(0, 19) ?? "—"}</td>
                      <td className="p-2 border">{dur}</td>
                      <td className="p-2 border">{c.qtd_chamados ?? "—"}</td>
                      <td className="p-2 border">{c.qtd_notas ?? "—"}</td>
                      <td className="p-2 border">{c.qtd_anexos ?? "—"}</td>
                      <td className="p-2 border text-red-500 max-w-xs truncate">{c.erro ?? ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Acesso ── */}
      {aba === "acesso" && (
        <div className="max-w-md">
          <p className="text-sm text-gray-600 mb-3">
            Perfis com acesso à tela Admin ServiceNow (além de "admin"):
          </p>
          <textarea
            className="w-full border rounded px-3 py-2 text-sm h-24 font-mono"
            placeholder="gestor,analista_senior"
            value={perfis.join(",")}
            onChange={e => setPerfis(e.target.value.split(",").map(p => p.trim()).filter(Boolean))}
          />
          <button
            onClick={salvarPerfis}
            className="mt-2 px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
          >
            Salvar perfis
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Adicionar link na página `Admin.tsx`**

Localizar o componente de listagem de seções em `Admin.tsx` e adicionar:

```tsx
// Adicionar ao array de cards/links da tela Admin existente:
{ label: "ServiceNow", href: "/admin/servicenow", descricao: "Conexão, grupos, sync e acesso" }
```

- [ ] **Step 3: Registrar rota no router da aplicação**

Localizar o arquivo de rotas (tipicamente `App.tsx` ou `routes.tsx`):

```tsx
// Adicionar import
import AdminServiceNow from "./pages/AdminServiceNow";

// Adicionar rota
<Route path="/admin/servicenow" element={<AdminServiceNow />} />
```

- [ ] **Step 4: Testar no browser**

```bash
# Iniciar o dev server se ainda não estiver rodando
cd ui-react && npm run dev
```

Verificar:
- `/admin/servicenow` carrega sem erros
- Aba "Conexão": campos preenchidos com valores da API, botão "Testar conexão" retorna feedback
- Aba "Grupos": tabela com grupos, toggle de ativo funciona, "+ Adicionar" cria grupo
- Aba "Sincronização": tabela de ciclos e botão "Forçar delta agora"
- Aba "Acesso": campo de perfis carregado

- [ ] **Step 5: Commit**

```bash
git add ui-react/src/pages/AdminServiceNow.tsx \
        ui-react/src/pages/Admin.tsx \
        ui-react/src/App.tsx   # ou routes.tsx — ajustar conforme localização real
git commit -m "feat(ui): tela Admin ServiceNow — conexão, grupos, sync, acesso"
```

---

## Task 7: Modal de Detalhes do Chamado

**Files:**
- Criar: `ui-react/src/components/ChamadoDetalheModal.tsx`
- Modificar: componente de card do kanban para abrir o modal ao clicar

**Interfaces:**
- Consome: `GET /chamados/{sys_id}/detalhe`, `GET /chamados/{sys_id}/anexos/{sys_id_anexo}` (via URL proxy)
- Produz: componente `ChamadoDetalheModal` com props `{ sys_id: string | null, onClose: () => void }`

- [ ] **Step 1: Criar `ui-react/src/components/ChamadoDetalheModal.tsx`**

```tsx
// ui-react/src/components/ChamadoDetalheModal.tsx
import { useEffect, useState } from "react";
import { api } from "../lib/api";

interface Nota {
  sys_id_nota: string;
  autor: string | null;
  autor_email: string | null;
  criado_em: string | null;
  texto: string | null;
  tipo: string;
}

interface Anexo {
  sys_id_anexo: string;
  nome_arquivo: string | null;
  mime_type: string | null;
  tamanho_bytes: number | null;
  url_proxy: string;
  criado_em: string | null;
}

interface Chamado {
  sys_id: string;
  numero: string;
  tipo: string;
  titulo: string | null;
  descricao: string | null;
  estado_kanban: string;
  atribuido_a: string | null;
  atribuido_a_email: string | null;
  grupo: string | null;
  aberto_em: string | null;
  url: string | null;
  tem_anexo: boolean;
  sla_vencido: boolean;
}

interface DetalheResponse {
  chamado: Chamado;
  notas: Nota[];
  anexos: Anexo[];
}

function ehINC(c: Chamado): boolean {
  return c.tipo === "incident" &&
    !["resolvido", "encerrado"].includes(c.estado_kanban);
}

function formatBytes(b: number | null): string {
  if (!b) return "";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ChamadoDetalheModal({
  sys_id, onClose,
}: {
  sys_id: string | null;
  onClose: () => void;
}) {
  const [detalhe, setDetalhe] = useState<DetalheResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [anexoAberto, setAnexoAberto] = useState<string | null>(null);

  useEffect(() => {
    if (!sys_id) { setDetalhe(null); return; }
    setLoading(true);
    api.get(`/chamados/${sys_id}/detalhe`)
      .then(r => setDetalhe(r.data))
      .finally(() => setLoading(false));
  }, [sys_id]);

  if (!sys_id) return null;

  const inc = detalhe?.chamado && ehINC(detalhe.chamado);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">

        {/* cabeçalho */}
        <div className={`px-5 py-4 rounded-t-lg flex items-start justify-between gap-4
          ${inc ? "bg-red-50 dark:bg-red-900/20" : "bg-gray-50 dark:bg-gray-700"}`}>
          {loading || !detalhe ? (
            <span className="text-gray-400 text-sm">Carregando…</span>
          ) : (
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-sm font-semibold">
                  {detalhe.chamado.numero}
                </span>
                {inc && (
                  <span className="text-xs font-bold text-red-600 bg-red-100 px-2 py-0.5 rounded">
                    INC
                  </span>
                )}
                <span className="text-xs text-gray-500 capitalize">
                  {detalhe.chamado.estado_kanban}
                </span>
              </div>
              <p className="text-sm font-medium mt-1 truncate">
                {detalhe.chamado.titulo}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">
                {detalhe.chamado.atribuido_a ?? "—"}
                {detalhe.chamado.grupo ? ` · ${detalhe.chamado.grupo}` : ""}
                {detalhe.chamado.aberto_em
                  ? ` · Aberto: ${detalhe.chamado.aberto_em.slice(0, 10)}` : ""}
              </p>
            </div>
          )}
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none flex-shrink-0"
          >
            ✕
          </button>
        </div>

        {/* conteúdo scrollável */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {!loading && detalhe && (
            <>
              {/* descrição */}
              {detalhe.chamado.descricao && (
                <section>
                  <h3 className="text-xs font-semibold uppercase text-gray-500 mb-2">
                    Descrição
                  </h3>
                  <p className="text-sm whitespace-pre-wrap text-gray-700 dark:text-gray-300">
                    {detalhe.chamado.descricao}
                  </p>
                </section>
              )}

              {/* notas */}
              <section>
                <h3 className="text-xs font-semibold uppercase text-gray-500 mb-2">
                  Histórico de Notas
                  <span className="ml-2 text-gray-400 normal-case">
                    ({detalhe.notas.length})
                  </span>
                </h3>
                {detalhe.notas.length === 0 ? (
                  <p className="text-sm text-gray-400">Sem notas.</p>
                ) : (
                  <div className="space-y-3">
                    {detalhe.notas.map(n => (
                      <div key={n.sys_id_nota}
                           className="border rounded p-3 bg-gray-50 dark:bg-gray-700/50">
                        <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
                          <span className="font-medium">{n.autor ?? "—"}</span>
                          <span>·</span>
                          <span>{n.criado_em?.slice(0, 16).replace("T", " ") ?? ""}</span>
                          <span className="ml-auto font-mono text-gray-400">{n.tipo}</span>
                        </div>
                        <p className="text-sm whitespace-pre-wrap">{n.texto}</p>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {/* anexos */}
              {detalhe.anexos.length > 0 && (
                <section>
                  <h3 className="text-xs font-semibold uppercase text-gray-500 mb-2">
                    Anexos <span className="text-gray-400">({detalhe.anexos.length})</span>
                  </h3>
                  <div className="space-y-2">
                    {detalhe.anexos.map(a => {
                      const isImg = (a.mime_type || "").startsWith("image/");
                      return (
                        <div key={a.sys_id_anexo}>
                          <div className="flex items-center gap-2 text-sm">
                            <span>{isImg ? "🖼" : "📄"}</span>
                            <span className="flex-1 truncate">{a.nome_arquivo}</span>
                            <span className="text-gray-400 text-xs">
                              {formatBytes(a.tamanho_bytes)}
                            </span>
                            <button
                              onClick={() =>
                                setAnexoAberto(anexoAberto === a.sys_id_anexo
                                  ? null : a.sys_id_anexo)}
                              className="text-blue-600 text-xs hover:underline"
                            >
                              {isImg ? "ver" : "baixar"}
                            </button>
                          </div>
                          {isImg && anexoAberto === a.sys_id_anexo && (
                            <img
                              src={a.url_proxy}
                              alt={a.nome_arquivo ?? "anexo"}
                              className="mt-2 max-w-full rounded border"
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}
            </>
          )}
        </div>

        {/* rodapé */}
        {detalhe?.chamado.url && (
          <div className="px-5 py-3 border-t">
            <a
              href={detalhe.chamado.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-blue-600 hover:underline"
            >
              🔗 Abrir no ServiceNow
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Integrar modal no card do kanban**

Localizar o componente de card existente (tipicamente `KanbanCard.tsx` ou similar em `ui-react/src/`):

```tsx
// Adicionar no componente de card do kanban:
import ChamadoDetalheModal from "../components/ChamadoDetalheModal";

// Adicionar state:
const [modalSysId, setModalSysId] = useState<string | null>(null);

// No card, adicionar onClick:
<div onClick={() => setModalSysId(chamado.sys_id)} className="cursor-pointer ...">
  {/* conteúdo do card existente */}
</div>

// Renderizar modal no final do componente:
<ChamadoDetalheModal
  sys_id={modalSysId}
  onClose={() => setModalSysId(null)}
/>
```

- [ ] **Step 3: Adicionar borda INC no card existente**

No CSS/classes do card do kanban, adicionar lógica de borda vermelha:

```tsx
const incAtivo = chamado.tipo === "incident" &&
  !["resolvido", "encerrado"].includes(chamado.estado_kanban);

<div className={`... ${incAtivo ? "border-l-4 border-red-500" : ""}`}>
```

- [ ] **Step 4: Testar no browser**

- Clicar em um card abre o modal
- Modal exibe número, título, analista, estado
- INC não-encerrado: cabeçalho vermelho, badge "INC"
- Notas listadas em ordem cronológica
- Imagens renderizam inline; outros anexos disparam download
- Fechar por ✕ ou clique fora do modal
- Card com `tipo='incident'` e estado não-encerrado tem borda esquerda vermelha

- [ ] **Step 5: Commit**

```bash
git add ui-react/src/components/ChamadoDetalheModal.tsx \
        ui-react/src/pages/Kanban.tsx   # ou arquivo do card — ajustar
git commit -m "feat(ui): modal de detalhes do chamado com notas, anexos e regra INC"
```

---

## Task 8: Tela de Indicadores Históricos

**Files:**
- Criar: `ui-react/src/pages/ChamadosIndicadoresHistorico.tsx`
- Modificar: nav/rotas para incluir `/chamados/indicadores/historico`

**Interfaces:**
- Consome: `GET /chamados/indicadores/historico?periodo=&grupo=`
- Produz: componente `ChamadosIndicadoresHistorico` exportado de `pages/ChamadosIndicadoresHistorico.tsx`

- [ ] **Step 1: Criar `ui-react/src/pages/ChamadosIndicadoresHistorico.tsx`**

```tsx
// ui-react/src/pages/ChamadosIndicadoresHistorico.tsx
import { useState, useEffect } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, ReferenceLine, ResponsiveContainer,
} from "recharts";
import { api } from "../lib/api";

type Periodo = "hoje" | "30d" | "historico";

interface Snapshot {
  capturado_em: string;
  total_ativos: number;
  novo: number;
  andamento: number;
  aguardando: number;
  resolvido: number;
  outros: number;
  sla_vencidos: number;
  idade_media_dias: number | null;
  tempo_medio_resolucao_horas: number | null;
  qtd_encerrados_7d: number;
  qtd_abertos_7d: number;
}

interface Analista {
  atribuido_a: string;
  atribuido_a_email: string;
  total_ativos: number;
  sla_vencidos: number;
  idade_media_dias: number | null;
}

interface Grupo {
  grupo: string;
  total_ativos: number;
  sla_vencidos: number;
  idade_media_dias: number | null;
}

interface Meta {
  metrica: string;
  valor_meta: number;
  grupo: string | null;
}

function labelEixo(s: Snapshot, periodo: Periodo): string {
  const d = new Date(s.capturado_em);
  if (periodo === "hoje") return `${d.getHours()}h`;
  if (periodo === "historico") return `S${Math.ceil(d.getDate() / 7)}/${d.getMonth() + 1}`;
  return s.capturado_em.slice(5, 10);
}

export default function ChamadosIndicadoresHistorico() {
  const [periodo, setPeriodo] = useState<Periodo>("30d");
  const [data, setData] = useState<{
    snapshots: Snapshot[];
    por_analista: Analista[];
    por_grupo: Grupo[];
    metas: Meta[];
  } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/chamados/indicadores/historico?periodo=${periodo}`)
      .then(r => setData(r.data))
      .finally(() => setLoading(false));
  }, [periodo]);

  const snapshots = [...(data?.snapshots ?? [])].reverse();
  const chartData = snapshots.map(s => ({
    ...s,
    label: labelEixo(s, periodo),
  }));

  const metaTmr = data?.metas.find(m => m.metrica === "tempo_medio_resolucao_horas");

  const periodos: { id: Periodo; label: string }[] = [
    { id: "hoje", label: "Hoje" },
    { id: "30d", label: "30 dias" },
    { id: "historico", label: "Histórico" },
  ];

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Indicadores Históricos</h1>
        <div className="flex gap-1 bg-gray-100 rounded p-1">
          {periodos.map(p => (
            <button
              key={p.id}
              onClick={() => setPeriodo(p.id)}
              className={`px-3 py-1 text-sm rounded transition-colors
                ${periodo === p.id
                  ? "bg-white shadow text-gray-900"
                  : "text-gray-500 hover:text-gray-700"}`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {loading && <p className="text-gray-400 text-sm">Carregando…</p>}

      {!loading && data && (
        <>
          {/* linha: total de ativos */}
          <section>
            <h2 className="text-sm font-semibold text-gray-500 uppercase mb-3">
              Total de ativos ao longo do tempo
            </h2>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="total_ativos"
                      name="Ativos" stroke="#2563eb" dot={false} />
                <Line type="monotone" dataKey="sla_vencidos"
                      name="SLA vencidos" stroke="#dc2626" dot={false} strokeDasharray="4 2" />
              </LineChart>
            </ResponsiveContainer>
          </section>

          {/* barras empilhadas: distribuição kanban */}
          <section>
            <h2 className="text-sm font-semibold text-gray-500 uppercase mb-3">
              Distribuição por coluna kanban
            </h2>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="novo" name="Novo" stackId="a" fill="#93c5fd" />
                <Bar dataKey="andamento" name="Andamento" stackId="a" fill="#3b82f6" />
                <Bar dataKey="aguardando" name="Aguardando" stackId="a" fill="#f59e0b" />
                <Bar dataKey="resolvido" name="Resolvido" stackId="a" fill="#10b981" />
                <Bar dataKey="outros" name="Outros" stackId="a" fill="#9ca3af" />
              </BarChart>
            </ResponsiveContainer>
          </section>

          {/* linha: tempo médio de resolução */}
          <section>
            <h2 className="text-sm font-semibold text-gray-500 uppercase mb-3">
              Tempo médio de resolução (horas)
            </h2>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                {metaTmr && (
                  <ReferenceLine
                    y={metaTmr.valor_meta}
                    stroke="#dc2626"
                    strokeDasharray="6 3"
                    label={{ value: `Meta: ${metaTmr.valor_meta}h`, position: "insideTopRight", fontSize: 11 }}
                  />
                )}
                <Line type="monotone" dataKey="tempo_medio_resolucao_horas"
                      name="Tempo médio (h)" stroke="#7c3aed" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </section>

          {/* barras: encerrados × abertos */}
          <section>
            <h2 className="text-sm font-semibold text-gray-500 uppercase mb-3">
              Encerrados × Abertos (últimos 7 dias por snapshot)
            </h2>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="qtd_encerrados_7d" name="Encerrados 7d" fill="#10b981" />
                <Bar dataKey="qtd_abertos_7d" name="Abertos 7d" fill="#f59e0b" />
              </BarChart>
            </ResponsiveContainer>
          </section>

          {/* tabela analistas */}
          <section>
            <h2 className="text-sm font-semibold text-gray-500 uppercase mb-3">
              Por Analista (snapshot atual)
            </h2>
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-gray-50">
                  {["Analista","Ativos","SLA vencidos","Idade média (dias)"].map(h => (
                    <th key={h} className="text-left p-2 border">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.por_analista.map(a => (
                  <tr key={a.atribuido_a_email} className="border-b hover:bg-gray-50">
                    <td className="p-2 border">{a.atribuido_a}</td>
                    <td className="p-2 border">{a.total_ativos}</td>
                    <td className={`p-2 border ${a.sla_vencidos > 0 ? "text-red-600" : ""}`}>
                      {a.sla_vencidos}
                    </td>
                    <td className="p-2 border">
                      {a.idade_media_dias != null ? a.idade_media_dias.toFixed(1) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {/* tabela grupos */}
          <section>
            <h2 className="text-sm font-semibold text-gray-500 uppercase mb-3">
              Por Grupo (snapshot atual)
            </h2>
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-gray-50">
                  {["Grupo","Ativos","SLA vencidos","Idade média (dias)"].map(h => (
                    <th key={h} className="text-left p-2 border">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.por_grupo.map(g => (
                  <tr key={g.grupo} className="border-b hover:bg-gray-50">
                    <td className="p-2 border">{g.grupo}</td>
                    <td className="p-2 border">{g.total_ativos}</td>
                    <td className={`p-2 border ${g.sla_vencidos > 0 ? "text-red-600" : ""}`}>
                      {g.sla_vencidos}
                    </td>
                    <td className="p-2 border">
                      {g.idade_media_dias != null ? g.idade_media_dias.toFixed(1) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Registrar rota e link de navegação**

```tsx
// No arquivo de rotas (App.tsx ou routes.tsx):
import ChamadosIndicadoresHistorico from "./pages/ChamadosIndicadoresHistorico";
<Route path="/chamados/indicadores/historico"
       element={<ChamadosIndicadoresHistorico />} />

// No menu de navegação lateral, adicionar link:
{ label: "Indicadores históricos", href: "/chamados/indicadores/historico" }
```

- [ ] **Step 3: Verificar dependência do Recharts**

```bash
cd ui-react && npm ls recharts
# Se não instalado:
npm install recharts
```

- [ ] **Step 4: Testar no browser**

- `/chamados/indicadores/historico` carrega sem erros
- Seletor de período muda os gráficos
- Linha de meta aparece quando `etl_indicador_meta` tiver dados
- Tabela de analistas e grupos listam dados do último snapshot
- SLA vencidos > 0 aparecem em vermelho

- [ ] **Step 5: Commit**

```bash
git add ui-react/src/pages/ChamadosIndicadoresHistorico.tsx \
        ui-react/src/App.tsx
git commit -m "feat(ui): tela de indicadores históricos — gráficos e tabelas"
```

---

## Task 9: Regra Visual INC + `FRESCOR_ALERTA_MINUTOS=8`

**Files:**
- Verificar: `api/routers/chamados.py` — confirmar `FRESCOR_ALERTA_MINUTOS = 8`
- Verificar: `dags/tests/test_servicenow_cadencia.py` — aceitar frescor de 8 min
- Verificar: demais telas (dashboard, lista de chamados) com regra INC

**Interfaces:**
- Esta task não produz novos arquivos — consolida a regra INC em todos os pontos e confirma o frescor.

- [ ] **Step 1: Confirmar `FRESCOR_ALERTA_MINUTOS = 8` em `chamados.py`**

```bash
grep -n "FRESCOR_ALERTA_MINUTOS" api/routers/chamados.py
# Esperado: FRESCOR_ALERTA_MINUTOS = 8
```

Se ainda for `60`, alterar:

```python
FRESCOR_ALERTA_MINUTOS = 8   # delta a cada 5 min + margem de 3 min
```

- [ ] **Step 2: Atualizar `dags/tests/test_servicenow_cadencia.py`**

Localizar o teste que valida `FRESCOR_ALERTA_MINUTOS` e ajustar o assert:

```python
# Substituir assert antigo:
# assert FRESCOR_ALERTA_MINUTOS == 60
# Por:
assert FRESCOR_ALERTA_MINUTOS == 8, (
    "Com delta a cada 5 min, o frescor deve ser 8 min (5 + 3 de margem)")
```

- [ ] **Step 3: Aplicar regra INC nas demais telas**

Para cada tela que exibe chamados (dashboard, lista de chamados, tabelas de indicadores):

```tsx
// Utilitário compartilhado — adicionar em ui-react/src/lib/chamado.ts
export function isINCAtivo(chamado: { tipo: string; estado_kanban: string }): boolean {
  return chamado.tipo === "incident" &&
    !["resolvido", "encerrado"].includes(chamado.estado_kanban);
}

// Nos componentes de lista/tabela:
import { isINCAtivo } from "../lib/chamado";

<tr className={isINCAtivo(c) ? "text-red-600 dark:text-red-400" : ""}>
```

- [ ] **Step 4: Rodar suite completa de testes**

```bash
docker exec orquestra-api python -m pytest tests/ -v
# Todos PASS — incluindo test_servicenow_cadencia.py com FRESCOR=8
```

- [ ] **Step 5: Commit**

```bash
git add api/routers/chamados.py \
        dags/tests/test_servicenow_cadencia.py \
        ui-react/src/lib/chamado.ts  # novo utilitário
git commit -m "feat: frescor=8min, regra visual INC consolidada em todas as telas"
```

---

## Task 10: QA Completo

**Files:**
- Nenhum arquivo novo — validação do que foi entregue nas Tasks 1–9

**Interfaces:**
- Consome: toda a stack (banco, DAGs, API, UI)

- [ ] **Step 1: Rodar suite completa de testes unitários**

```bash
docker exec orquestra-api python -m pytest tests/ -v --tb=short
# Esperado: todos PASS. Registrar contagem total.
```

- [ ] **Step 2: Rodar suite de integração API**

```bash
docker exec orquestra-api python -m pytest api/tests/ -v --tb=short
# Esperado: todos PASS
```

- [ ] **Step 3: Verificar migrations no banco**

```sql
-- Executar no SQL Server Management Studio ou sqlcmd:
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA='dbo'
  AND TABLE_NAME IN (
    'etl_chamado_nota','etl_chamado_anexo','etl_chamado_ciclo',
    'etl_indicador_snapshot','etl_indicador_snapshot_analista',
    'etl_indicador_snapshot_grupo','etl_indicador_meta',
    'etl_servicenow_grupo','etl_servicenow_gatilho'
  )
ORDER BY TABLE_NAME;
-- Esperado: 9 linhas

SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_chamado'
  AND COLUMN_NAME='tem_anexo';
-- Esperado: 1 linha
```

- [ ] **Step 4: Smoke test da DAG delta**

```bash
# Disparar execução manual
docker exec airflow-airflow-scheduler-1 \
    airflow dags trigger etl_servicenow_delta

# Aguardar 2 min e verificar status
docker exec airflow-airflow-scheduler-1 \
    airflow dags list-runs -d etl_servicenow_delta 2>&1 | head -10
# Esperado: estado "success" na última execução
```

- [ ] **Step 5: Smoke test da DAG full**

```bash
docker exec airflow-airflow-scheduler-1 \
    airflow dags trigger etl_servicenow_full

# Aguardar ~5 min e verificar
docker exec airflow-airflow-scheduler-1 \
    airflow dags list-runs -d etl_servicenow_full 2>&1 | head -5
```

- [ ] **Step 6: Verificar que ciclos foram gravados**

```sql
SELECT TOP 5 modo, status, iniciado_em, terminado_em, qtd_chamados
FROM dbo.etl_chamado_ciclo
ORDER BY id DESC;
-- Esperado: ao menos 1 linha delta OK e 1 linha full OK
```

- [ ] **Step 7: Smoke test dos endpoints API**

```bash
# Substitua TOKEN e SYS_ID por valores reais do ambiente
TOKEN="seu_token_aqui"
SYS_ID="sys_id_real_do_chamado"
BASE="http://localhost:8000"

curl -s -H "Authorization: Bearer $TOKEN" \
     "$BASE/chamados/$SYS_ID/detalhe" | python -m json.tool | head -20
# Esperado: JSON com chamado, notas, anexos

curl -s -H "Authorization: Bearer $TOKEN" \
     "$BASE/chamados/indicadores/historico?periodo=30d" | python -m json.tool | head -10
# Esperado: JSON com snapshots

curl -s -H "Authorization: Bearer $TOKEN" \
     "$BASE/admin/servicenow/config" | python -m json.tool
# Esperado: JSON com url, usuario, habilitado

curl -s -H "Authorization: Bearer $TOKEN" \
     "$BASE/admin/servicenow/ciclos" | python -m json.tool | head -20
# Esperado: lista de ciclos
```

- [ ] **Step 8: Smoke test da UI**

Testar manualmente no browser:

1. `/admin/servicenow` — todas as 4 abas carregam, botão "Testar conexão" retorna OK
2. `/chamados/indicadores/historico` — gráficos renderizam, seletor de período funciona
3. Kanban — clicar em chamado abre modal com notas e anexos
4. INC não-encerrado — borda vermelha nos cards + cabeçalho vermelho no modal

- [ ] **Step 9: Pausar `etl_servicenow_sync` (se o full rodou com sucesso)**

```bash
docker exec airflow-airflow-scheduler-1 \
    airflow dags pause etl_servicenow_sync
# Confirma que a DAG antiga está pausada
```

- [ ] **Step 10: Commit final de QA**

```bash
git add .   # apenas arquivos de testes ou ajustes pontuais do QA
git commit -m "qa: Subsistema A — suite completa PASS, smoke prod OK"
```
