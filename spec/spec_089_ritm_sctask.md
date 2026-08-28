# Spec 089 — RITM → SCTASK: Hierarquia de chamados no etl_chamado

## Contexto

A tabela `etl_chamado` no banco `DMDB41` espelha tickets do ServiceNow.
Ela armazena tanto `sc_req_item` (RITM) quanto `sc_task` (SCTASK) na mesma tabela plana,
mas não existe nenhum campo ligando a SCTASK ao seu RITM pai.

A DAG `etl_servicenow_sync.py` não busca o campo `request_item` das SCTASKs,
então a coluna `parent_sys_id` não existe e a hierarquia se perde.

## Problema

```
etl_chamado (atual)
├── RITM0094607  (sc_req_item) — sys_id = "abc123"
├── SCTASK001    (sc_task)     — sys_id = "def456", parent_sys_id = NULL  ← ERRADO
└── SCTASK002    (sc_task)     — sys_id = "ghi789", parent_sys_id = NULL  ← ERRADO
```

O campo `request_item` da API ServiceNow para `sc_task` contém o `sys_id` do RITM pai.

## Objetivo

```
etl_chamado (após fix)
├── RITM0094607  (sc_req_item) — sys_id = "abc123", parent_sys_id = NULL
├── SCTASK001    (sc_task)     — sys_id = "def456", parent_sys_id = "abc123"  ✓
└── SCTASK002    (sc_task)     — sys_id = "ghi789", parent_sys_id = "abc123"  ✓
```

---

## Alteração 1 — Migration SQL (nova migration após a 088)

Crie o arquivo `sge_app/sql/migrations/089_chamados_parent.sql`:

```sql
-- 089_chamados_parent.sql
-- Adiciona parent_sys_id em etl_chamado para ligar SCTASK ao RITM pai.

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.etl_chamado')
      AND name = 'parent_sys_id'
)
BEGIN
    ALTER TABLE dbo.etl_chamado
        ADD parent_sys_id VARCHAR(32) NULL;

    CREATE INDEX IX_etl_chamado_parent
        ON dbo.etl_chamado (parent_sys_id)
        WHERE parent_sys_id IS NOT NULL;
END
GO
```

---

## Alteração 2 — DAG `etl_servicenow_sync.py`

Arquivo: `sge_app/dags/etl_servicenow_sync.py`

### 2a. Corrigir mapeamento de estado para sc_req_item

Localizar o dict de estados e corrigir a chave `"3"`:

```python
# ANTES:
"3": "aguardando"

# DEPOIS:
"3": "outros"
```

### 2b. Adicionar campo `request_item` na lista de campos buscados para sc_task

Localizar onde os campos são definidos por tabela e adicionar:

```python
# Onde campos são montados, adicionar condicionalmente para sc_task:
campos = [
    "sys_id", "number", "short_description", "description",
    "state", "assigned_to", "assignment_group",
    "sys_created_on", "sys_updated_on",
    *( ["request_item"] if tabela == "sc_task" else [] )
]
```

### 2c. Adicionar `parent_sys_id` no dict de registros

Onde o dict `registro` é montado no loop de resultados:

```python
# Adicionar ao dict registro:
"parent_sys_id": (_val("request_item") or None) if tabela == "sc_task" else None,
```

> `_val()` é a função auxiliar que já existe na DAG para extrair o valor display/value do campo.

### 2d. Incluir `parent_sys_id` no MERGE (UPDATE e INSERT)

Localizar a query MERGE e adicionar:

**No UPDATE SET:**
```sql
parent_sys_id = %(parent_sys_id)s,
```

**No INSERT (colunas):**
```sql
parent_sys_id,
```

**No INSERT (valores):**
```sql
%(parent_sys_id)s,
```

---

## Alteração 3 — Backend API (`sge_app/api/`)

No endpoint que retorna chamados, adicionar `parent_sys_id` ao SELECT:

```python
# Adicionar parent_sys_id no SELECT da query de chamados
SELECT
    sys_id, number, short_description, state,
    assigned_to, assignment_group,
    sys_created_on, sys_updated_on,
    parent_sys_id   -- NOVO
FROM dbo.etl_chamado
```

Criar novo endpoint para buscar tarefas de um RITM:

```python
@router.get("/chamados/{sys_id}/tasks")
async def get_tasks(sys_id: str, db=Depends(get_db)):
    rows = db.execute(
        "SELECT * FROM dbo.etl_chamado WHERE parent_sys_id = ?", sys_id
    ).fetchall()
    return [dict(r) for r in rows]
```

---

## Alteração 4 — Frontend React (`sge_app/ui-react/src/`)

### 4a. Adicionar `parent_sys_id` ao tipo TypeScript de Chamado

```typescript
// Em types/chamado.ts ou similar:
export interface Chamado {
  // ... campos existentes
  parent_sys_id?: string | null;
}
```

### 4b. Agrupar chamados por hierarquia na listagem

```typescript
// Monta mapa de RITMs por sys_id
const ritmBySysId = new Map(
  chamados
    .filter(c => c.number.startsWith("RITM"))
    .map(c => [c.sys_id, c])
);

// Separa tasks com pai conhecido e tasks soltas (sem pai no conjunto)
const tasksComPai = chamados.filter(
  c => c.number.startsWith("SCTASK") && c.parent_sys_id && ritmBySysId.has(c.parent_sys_id)
);
const tasksSoltas = chamados.filter(
  c => c.number.startsWith("SCTASK") && (!c.parent_sys_id || !ritmBySysId.has(c.parent_sys_id))
);
```

### 4c. Exibir badge de tasks no card do RITM

```tsx
{tasksComPai.filter(t => t.parent_sys_id === ritm.sys_id).length > 0 && (
  <span className="badge-tasks">
    {tasksComPai.filter(t => t.parent_sys_id === ritm.sys_id).length} tasks
  </span>
)}
```

---

## Ordem de aplicação

1. Rodar migration `089_chamados_parent.sql` no banco `DMDB41`
2. Deploy do backend API (novo campo no SELECT + novo endpoint `/tasks`)
3. Deploy do frontend React (`npm run build` + copiar `dist/`)
4. Deploy da DAG atualizada (arquivo já é lido pelo volume montado)
5. Acionar sync manual: trigger da DAG `etl_servicenow_sync` no Airflow
6. Validar com as queries abaixo

---

## Validação

```sql
-- Checar que SCTASKs agora têm parent_sys_id preenchido
SELECT
    number,
    LEFT(short_description, 60) AS descricao,
    parent_sys_id
FROM dbo.etl_chamado
WHERE number LIKE 'SCTASK%'
ORDER BY sys_updated_on DESC;

-- Checar hierarquia completa de um RITM específico
SELECT
    pai.number  AS ritm,
    filho.number AS sctask,
    filho.state,
    filho.assigned_to
FROM dbo.etl_chamado pai
JOIN dbo.etl_chamado filho ON filho.parent_sys_id = pai.sys_id
WHERE pai.number = 'RITM0094607';

-- Quantos SCTASKs ainda sem pai após o sync
SELECT COUNT(*) AS sem_pai
FROM dbo.etl_chamado
WHERE number LIKE 'SCTASK%'
  AND parent_sys_id IS NULL;
```

---

## Checklist de conclusão

- [ ] Migration 089 aplicada no DMDB41
- [ ] Campo `parent_sys_id` visível no banco (`SELECT TOP 1 parent_sys_id FROM dbo.etl_chamado`)
- [ ] DAG `etl_servicenow_sync` deployada com as 4 alterações
- [ ] Sync manual rodado com sucesso no Airflow
- [ ] SCTASKs com `parent_sys_id` preenchido na query de validação
- [ ] Endpoint `/chamados/{sys_id}/tasks` retornando tasks do RITM
- [ ] Frontend exibindo badge de tasks nos cards de RITM
