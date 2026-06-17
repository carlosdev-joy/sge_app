# Agendamento "Dia + Hora Específico" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o novo agendamento `schedule_type = 'monthly_days_times'` ("Dia + Hora Específico") ponta a ponta: schema SQL, API FastAPI (validação/persistência/leitura), geração de DAG Airflow (cron + checagem em runtime) e wizard React de criação/edição de pipeline.

**Architecture:** Novo schedule_type isolado, sem alterar os tipos existentes (`daily`, `weekly`, `monthly`, `biweekly`, `hourly_n`, `custom`, `on_demand`). Persiste um campo JSON (`dias_horarios_mes`) seguindo o padrão de degradação graciosa já usado pelas migrations 017/018 (feature-detection via `INFORMATION_SCHEMA.COLUMNS`, UPDATE em try/except). A geração de DAG usa "cron superset + checagem em runtime", estendendo o `ShortCircuitOperator check_agenda` já existente (mesmo padrão usado hoje por `horarios_especificos`). O frontend adiciona um bloco de UI no wizard e funções puras de parse/validação/preview em `pipelineUtils.ts`, reaproveitando `parseCustomTimes`.

**Tech Stack:** FastAPI + pyodbc/SQL Server (`api/`), Airflow DAG codegen (`dags/etl_dag_factory.py`), React + TypeScript + Vite (`ui-react/`), pytest (testes Python).

## Global Constraints

- schedule_type novo: `monthly_days_times` (label UI: "Dia + Hora Específico")
- Campo novo: `dias_horarios_mes` (TEXT/JSON) — 1 a 5 dias (1–28, únicos), 1 a 5 horários por dia (HH:MM, únicos)
- Toda alteração de schema deve ser idempotente (`IF NOT EXISTS`) e toda leitura/escrita deve degradar graciosamente quando a coluna ainda não existir (feature-detection via `INFORMATION_SCHEMA.COLUMNS` ou try/except), seguindo exatamente o padrão das migrations 017/018 já presentes em `api/routers/pipelines.py` e `dags/etl_dag_factory.py`.
- Não modificar `dbo.sp_etl_pipeline_upsert` — campos avançados de agendamento são persistidos via `UPDATE` direto após a stored procedure, como já ocorre com `horarios_especificos`/`dias_semana`/`calendario_nome`.
- Não há test runner JS configurado neste projeto (sem Vitest/Jest) — verificação de frontend usa `npx tsc -b --noEmit` (type-check) e teste manual no navegador.
- Python 3.12 foi instalado nesta máquina em `C:\Users\carlo\AppData\Local\Programs\Python\Python312` (via winget) com `fastapi==0.115.5`, `httpx==0.27.2`, `python-dotenv==1.0.1`, `uvicorn[standard]==0.32.1`, `pytest`, `pytest-asyncio`, `anyio` instalados (sem `pyodbc` — `tests/conftest.py` já mocka esse módulo). O diretório foi adicionado ao `PATH` do usuário (persistente para novos terminais), mas sessões Bash já abertas precisam do prefixo `export PATH=".../Python312:.../Python312/Scripts:$PATH" &&` antes de comandos `python` — todos os comandos deste plano já incluem esse prefixo.
- 5 testes pré-existentes falham nesta máquina antes de qualquer mudança deste plano (`test_factory_preview_not_found`, `test_dashboard_requires_auth`, `test_register_pipeline_missing_fields`, `test_malha_requires_auth`, `test_pipelines_unauthenticated`) — causa raiz: o padrão `patch("api.routers.X.get_db_conn")` usado nesses testes não intercepta o módulo real (`routers.X`, carregado via `pythonpath=api`), e cursores mock não configurados retornam `MagicMock` truthy em `fetchone()`/`fetchall()`, produzindo um usuário-fantasma autenticado sem permissões (403) em vez do esperado 401. Pré-existente, fora do escopo deste plano — não tente "corrigir" isso ao rodar a suíte completa, apenas confirme que o número de falhas não aumenta.
- `dias_horarios_mes` não entra em `AUDIT_FIELDS` (linha 33-39 de `api/routers/pipelines.py`), mesmo padrão de `horarios_especificos`/`dias_semana`/`calendario_nome` (campos avançados não são auditados).

---

### Task 1: Migration SQL — coluna `dias_horarios_mes`

**Files:**
- Create: `sql/migrations/024_dias_horarios_mes.sql`

**Interfaces:**
- Produces: coluna `dbo.etl_pipeline.dias_horarios_mes VARCHAR(1000) NULL`, consumida pelas Tasks 2-7.

- [ ] **Step 1: Criar o arquivo de migration**

```sql
-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 024 — Agendamento "Dia + Hora Específico"
--   etl_pipeline:
--     dias_horarios_mes → JSON com até 5 dias do mês (1-28), cada um com até
--                          5 horários "HH:MM" independentes. Usado quando
--                          schedule_type = 'monthly_days_times'.
--                          Ex: [{"dia":1,"horarios":["09:00"]},
--                               {"dia":15,"horarios":["14:00","18:00"]}]
-- Idempotente — seguro para rodar mais de uma vez.
-- ═══════════════════════════════════════════════════════════════════════════

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
               WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='dias_horarios_mes')
BEGIN
    ALTER TABLE dbo.etl_pipeline ADD dias_horarios_mes VARCHAR(1000) NULL;
    PRINT '[OK] Coluna dias_horarios_mes adicionada em dbo.etl_pipeline';
END
GO
```

- [ ] **Step 2: Verificar consistência com o padrão das migrations existentes**

Run: `grep -c "^GO$" sql/migrations/024_dias_horarios_mes.sql && grep -c "IF NOT EXISTS" sql/migrations/024_dias_horarios_mes.sql`
Expected: ambos os comandos retornam `1` (um separador de batch `GO`, um guard de idempotência `IF NOT EXISTS`), igual ao padrão de `sql/migrations/018_horarios_multiplos.sql`.

- [ ] **Step 3: Commit**

```bash
git add sql/migrations/024_dias_horarios_mes.sql
git commit -m "feat(sql): add dias_horarios_mes column for monthly day+time scheduling"
```

---

### Task 2: Backend — função pura de validação `_validate_dias_horarios_mes`

**Files:**
- Modify: `api/routers/pipelines.py:1-6` (imports), `api/routers/pipelines.py:52-55` (nova função, entre `_build_cron` e `_get_valid_projects`)
- Test: `tests/test_pipelines_dias_horarios_mes.py` (novo)

**Interfaces:**
- Produces: `_validate_dias_horarios_mes(raw: str | None) -> str | None` — levanta `fastapi.HTTPException(422, detail=...)` em entrada inválida; retorna a string JSON normalizada (dias ordenados, horários ordenados/dedupe) ou `None` se `raw` for vazio/`None`. Consumida pela Task 3.

- [ ] **Step 1: Escrever os testes (falham — função não existe ainda)**

Create `tests/test_pipelines_dias_horarios_mes.py`:

```python
"""
Testes para a validação de dias_horarios_mes (schedule_type 'monthly_days_times').
Função pura — não depende de banco de dados.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from api.routers.pipelines import _validate_dias_horarios_mes


def test_none_returns_none():
    assert _validate_dias_horarios_mes(None) is None


def test_empty_string_returns_none():
    assert _validate_dias_horarios_mes("") is None
    assert _validate_dias_horarios_mes("   ") is None


def test_valid_single_day_single_time():
    raw = '[{"dia": 1, "horarios": ["09:00"]}]'
    assert _validate_dias_horarios_mes(raw) == '[{"dia": 1, "horarios": ["09:00"]}]'


def test_valid_multiple_days_normalizes_order():
    raw = ('[{"dia": 28, "horarios": ["10:00"]}, {"dia": 1, "horarios": ["9:0"]}, '
           '{"dia": 15, "horarios": ["18:00", "14:00"]}]')
    result = _validate_dias_horarios_mes(raw)
    assert result == (
        '[{"dia": 1, "horarios": ["09:00"]}, '
        '{"dia": 15, "horarios": ["14:00", "18:00"]}, '
        '{"dia": 28, "horarios": ["10:00"]}]'
    )


def test_max_5_days_5_horarios_accepted():
    dias = [{"dia": d, "horarios": [f"{h:02d}:00" for h in range(5)]} for d in [1, 5, 10, 15, 20]]
    assert _validate_dias_horarios_mes(json.dumps(dias)) is not None


def test_invalid_json_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes("not json")
    assert exc.value.status_code == 422


def test_day_zero_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 0, "horarios": ["09:00"]}]')
    assert exc.value.status_code == 422


def test_day_29_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 29, "horarios": ["09:00"]}]')
    assert exc.value.status_code == 422


def test_duplicate_day_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 1, "horarios": ["09:00"]}, {"dia": 1, "horarios": ["10:00"]}]')
    assert exc.value.status_code == 422


def test_invalid_time_format_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 1, "horarios": ["25:00"]}]')
    assert exc.value.status_code == 422


def test_invalid_time_text_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 1, "horarios": ["amanha"]}]')
    assert exc.value.status_code == 422


def test_duplicate_time_same_day_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 1, "horarios": ["09:00", "09:00"]}]')
    assert exc.value.status_code == 422


def test_more_than_5_days_raises_422():
    dias = [{"dia": d, "horarios": ["09:00"]} for d in [1, 2, 3, 4, 5, 6]]
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes(json.dumps(dias))
    assert exc.value.status_code == 422


def test_more_than_5_horarios_raises_422():
    horarios = [f"{h:02d}:00" for h in range(6)]
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes(json.dumps([{"dia": 1, "horarios": horarios}]))
    assert exc.value.status_code == 422


def test_empty_horarios_list_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes('[{"dia": 1, "horarios": []}]')
    assert exc.value.status_code == 422


def test_empty_array_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_dias_horarios_mes("[]")
    assert exc.value.status_code == 422
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `cd /c/Users/carlo/repos/sge_app && export PATH="/c/Users/carlo/AppData/Local/Programs/Python/Python312:/c/Users/carlo/AppData/Local/Programs/Python/Python312/Scripts:$PATH" && python -m pytest tests/test_pipelines_dias_horarios_mes.py -v`
Expected: erro de coleta `ImportError: cannot import name '_validate_dias_horarios_mes' from 'api.routers.pipelines'`

- [ ] **Step 3: Implementar a função**

In `api/routers/pipelines.py`, replace the import block:

old:
```python
import logging
from datetime import timezone, timedelta
from typing import Optional
```

new:
```python
import json
import logging
import re
from datetime import timezone, timedelta
from typing import Optional
```

Then, replace (insert helper between `_build_cron` and `_get_valid_projects`):

old:
```python
    if st == "biweekly":                       # quinzenal: dia D e D+15
        d = int(dom or 1)
        return f"{m} {h} {d},{d + 15} * *"
    return f"{m} {h} * * *"


def _get_valid_projects(cur):
```

new:
```python
    if st == "biweekly":                       # quinzenal: dia D e D+15
        d = int(dom or 1)
        return f"{m} {h} {d},{d + 15} * *"
    return f"{m} {h} * * *"


_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _validate_dias_horarios_mes(raw):
    """Valida e normaliza o JSON de dias_horarios_mes (schedule_type 'monthly_days_times').

    Formato esperado: [{"dia": 1, "horarios": ["09:00"]}, ...] — 1 a 5 dias
    (1-28, sem repetir), cada um com 1 a 5 horários HH:MM (sem repetir no
    mesmo dia). Retorna a string JSON normalizada (dias e horários
    ordenados) ou None se raw for vazio.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=422, detail="dias_horarios_mes deve ser um JSON válido")
    if not isinstance(data, list) or not (1 <= len(data) <= 5):
        raise HTTPException(status_code=422, detail="dias_horarios_mes deve ter entre 1 e 5 dias")
    seen_days: set[int] = set()
    normalized = []
    for entry in data:
        if not isinstance(entry, dict) or "dia" not in entry or "horarios" not in entry:
            raise HTTPException(status_code=422, detail="Cada entrada de dias_horarios_mes precisa de 'dia' e 'horarios'")
        dia = entry["dia"]
        if not isinstance(dia, int) or isinstance(dia, bool) or not (1 <= dia <= 28):
            raise HTTPException(status_code=422, detail=f"Dia do mês inválido: {dia!r} (use 1-28)")
        if dia in seen_days:
            raise HTTPException(status_code=422, detail=f"Dia {dia} duplicado em dias_horarios_mes")
        seen_days.add(dia)
        horarios = entry["horarios"]
        if not isinstance(horarios, list) or not (1 <= len(horarios) <= 5):
            raise HTTPException(status_code=422, detail=f"Dia {dia} deve ter entre 1 e 5 horários")
        seen_times: set[str] = set()
        norm_times = []
        for t in horarios:
            if not isinstance(t, str):
                raise HTTPException(status_code=422, detail=f"Horário inválido no dia {dia}: {t!r}")
            m = _TIME_RE.match(t.strip())
            if not m:
                raise HTTPException(status_code=422, detail=f"Horário inválido no dia {dia}: '{t}' (use HH:MM)")
            hh, mm = int(m.group(1)), int(m.group(2))
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise HTTPException(status_code=422, detail=f"Horário fora do intervalo no dia {dia}: '{t}'")
            norm = f"{hh:02d}:{mm:02d}"
            if norm in seen_times:
                raise HTTPException(status_code=422, detail=f"Horário duplicado no dia {dia}: '{norm}'")
            seen_times.add(norm)
            norm_times.append(norm)
        normalized.append({"dia": dia, "horarios": sorted(norm_times)})
    normalized.sort(key=lambda e: e["dia"])
    return json.dumps(normalized)


def _get_valid_projects(cur):
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd /c/Users/carlo/repos/sge_app && export PATH="/c/Users/carlo/AppData/Local/Programs/Python/Python312:/c/Users/carlo/AppData/Local/Programs/Python/Python312/Scripts:$PATH" && python -m pytest tests/test_pipelines_dias_horarios_mes.py -v`
Expected: 15 testes, todos `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipelines_dias_horarios_mes.py api/routers/pipelines.py
git commit -m "feat(api): add dias_horarios_mes validation helper"
```

---

### Task 3: Backend — wiring no POST /pipelines/register (validação + persistência)

**Files:**
- Modify: `api/routers/pipelines.py:373` (extrair/validar `dias_horarios_mes` do body), `api/routers/pipelines.py:427-434` (persistência)
- Test: `tests/test_pipelines_dias_horarios_mes.py` (acrescentar testes de integração)

**Interfaces:**
- Consumes: `_validate_dias_horarios_mes(raw) -> str | None` (Task 2)
- Produces: endpoint `POST /pipelines/register` aceita `schedule_type='monthly_days_times'` + `dias_horarios_mes` e os persiste em `dbo.etl_pipeline.dias_horarios_mes`.

> **Nota sobre técnica de teste:** o padrão `patch("api.routers.X.get_db_conn")` usado em `tests/test_api_v2_4.py` foi verificado (manualmente, fora deste plano) como **não confiável** — `api.main` carrega `routers.pipelines` (módulo top-level, via `pythonpath=api` do `pytest.ini`), enquanto `patch("api.routers.pipelines...")` cria um módulo `api.routers.pipelines` separado que o endpoint real nunca usa. É por isso que vários testes existentes toleram `(401, 422)`: a autenticação "Bearer fake" cai num cursor mock não configurado cujos métodos (`fetchone`/`fetchall`) retornam `MagicMock` truthy por padrão, autenticando um usuário-fantasma sem permissões — resultando em `403`, não `401`/`422`. Para evitar essa armadilha, os testes abaixo usam `app.dependency_overrides` sobre `get_current_user` (importado via `from deps import ...`, igual ao código do próprio endpoint), o que **substitui de fato** a dependência usada pela rota real.

- [ ] **Step 1: Escrever o teste de integração (falha — endpoint ainda não exige o campo)**

Append to `tests/test_pipelines_dias_horarios_mes.py`:

```python
from deps import get_current_user, PERM_EDITAR


@pytest.fixture
def auth_override(app):
    """Substitui get_current_user por um usuário com permissão de edição.

    Necessário porque autenticar via header Bearer real exigiria uma sessão
    válida em dbo.etl_sessao — aqui sobrescrevemos a dependency diretamente
    no app, contornando a autenticação para isolar a lógica do endpoint.
    """
    app.dependency_overrides[get_current_user] = lambda: {
        "matricula": "TESTER", "perfil": "admin", "permissoes": [PERM_EDITAR],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.api
def test_register_monthly_days_times_requires_dias_horarios_mes(client, auth_override):
    """schedule_type='monthly_days_times' sem dias_horarios_mes -> 422.

    A validação ocorre antes de qualquer chamada a get_db_conn (ver Step 3),
    então este teste não precisa mockar o banco.
    """
    r = client.post(
        "/pipelines/register",
        json={
            "pipeline_name": "TESTE_MDT", "scheduled_time": "09:00:00",
            "schedule_type": "monthly_days_times", "project_name": "BI_CVP", "domain": "TESTE",
        },
    )
    assert r.status_code == 422
    assert "dias_horarios_mes" in r.json()["detail"]


@pytest.mark.api
def test_register_monthly_days_times_invalid_dia_returns_error(client, auth_override):
    """dias_horarios_mes com dia fora do intervalo -> 422 com mensagem específica."""
    r = client.post(
        "/pipelines/register",
        json={
            "pipeline_name": "TESTE_MDT", "scheduled_time": "09:00:00",
            "schedule_type": "monthly_days_times", "project_name": "BI_CVP", "domain": "TESTE",
            "dias_horarios_mes": '[{"dia": 99, "horarios": ["09:00"]}]',
        },
    )
    assert r.status_code == 422
    assert "Dia do mês inválido" in r.json()["detail"]
```

- [ ] **Step 2: Rodar e confirmar que falham (a validação ainda não existe)**

Run: `cd /c/Users/carlo/repos/sge_app && python -m pytest tests/test_pipelines_dias_horarios_mes.py -v -k register`
Expected: ambos os testes falham com `assert 422 == <outro status>` — sem a validação implementada, o request cai em `_get_valid_projects` (que retorna vazio com cursor mock não configurado) e devolve 422 "project_name inválido" em vez do erro esperado de `dias_horarios_mes`.

- [ ] **Step 3: Implementar o wiring**

old (linha 373, fim do bloco de migration 018):
```python
    dias_semana = (body.get("dias_semana") or "").strip() or None

    if pipeline in depends_on_list:
```

new:
```python
    dias_semana = (body.get("dias_semana") or "").strip() or None
    # Migration 024 — agendamento "Dia + Hora Específico"
    dias_horarios_mes = _validate_dias_horarios_mes(body.get("dias_horarios_mes"))
    if schedule_type == "monthly_days_times" and not dias_horarios_mes:
        raise HTTPException(status_code=422, detail="dias_horarios_mes é obrigatório para schedule_type 'monthly_days_times'")

    if pipeline in depends_on_list:
```

old (bloco de persistência migration 018):
```python
        try:
            cur.execute(
                "UPDATE dbo.etl_pipeline SET horarios_especificos=?, dias_semana=?, "
                "updated_at=GETDATE() WHERE pipeline_name=?",
                (horarios_especificos, dias_semana, pipeline),
            )
        except Exception:
            pass  # colunas da migration 018 podem não existir ainda — degrada sem erro
        new_vals = {
```

new:
```python
        try:
            cur.execute(
                "UPDATE dbo.etl_pipeline SET horarios_especificos=?, dias_semana=?, "
                "updated_at=GETDATE() WHERE pipeline_name=?",
                (horarios_especificos, dias_semana, pipeline),
            )
        except Exception:
            pass  # colunas da migration 018 podem não existir ainda — degrada sem erro
        try:
            cur.execute(
                "UPDATE dbo.etl_pipeline SET dias_horarios_mes=?, "
                "updated_at=GETDATE() WHERE pipeline_name=?",
                (dias_horarios_mes, pipeline),
            )
        except Exception:
            pass  # coluna da migration 024 pode não existir ainda — degrada sem erro
        new_vals = {
```

- [ ] **Step 4: Rodar a suíte completa para checar regressão**

Run: `cd /c/Users/carlo/repos/sge_app && export PATH="/c/Users/carlo/AppData/Local/Programs/Python/Python312:/c/Users/carlo/AppData/Local/Programs/Python/Python312/Scripts:$PATH" && python -m pytest tests/ -v`
Expected: os mesmos 5 testes pré-existentes da nota em Global Constraints continuam falhando (baseline, não relacionado a esta mudança), nenhum teste NOVO falha, e nenhum teste que passava antes passa a falhar.

- [ ] **Step 5: Commit**

```bash
git add api/routers/pipelines.py tests/test_pipelines_dias_horarios_mes.py
git commit -m "feat(api): validate and persist dias_horarios_mes on pipeline register"
```

---

### Task 4: Backend — GET /pipelines lê `dias_horarios_mes`

**Files:**
- Modify: `api/routers/pipelines.py:248-256` (feature-detection), `api/routers/pipelines.py:296` (lista `cols`)

**Interfaces:**
- Produces: resposta de `GET /pipelines` inclui a chave `dias_horarios_mes` (string JSON ou `null`), consumida pelo frontend (Task 9, `pipelineToForm`).

- [ ] **Step 1: Implementar a leitura (mesmo padrão de feature-detection da migration 018)**

old:
```python
        # colunas da migration 018 (horários múltiplos) — degradam para NULL
        cur.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='horarios_especificos'
        """)
        if cur.fetchone()[0]:
            sched_cols += ", horarios_especificos, dias_semana"
        else:
            sched_cols += ", NULL AS horarios_especificos, NULL AS dias_semana"
```

new:
```python
        # colunas da migration 018 (horários múltiplos) — degradam para NULL
        cur.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='horarios_especificos'
        """)
        if cur.fetchone()[0]:
            sched_cols += ", horarios_especificos, dias_semana"
        else:
            sched_cols += ", NULL AS horarios_especificos, NULL AS dias_semana"

        # coluna da migration 024 (dia + hora específico) — degrada para NULL
        cur.execute("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' AND COLUMN_NAME='dias_horarios_mes'
        """)
        if cur.fetchone()[0]:
            sched_cols += ", dias_horarios_mes"
        else:
            sched_cols += ", NULL AS dias_horarios_mes"
```

old (lista `cols`, linha 289-298):
```python
        cols = [
            "pipeline_name", "project_name", "domain", "tags", "scheduled_time",
            "schedule_type", "schedule_hour", "schedule_minute", "schedule_dow", "schedule_dom",
            "active", "dag_criada", "envia_msg_inicio", "envia_msg_fim", "envia_msg_erro",
            "depends_on", "dag_start_date", "descricao", "criticidade", "sla_minutos",
            "ambiente", "max_active_runs", "retries_count", "retry_delay_seconds",
            "pool_name", "runbook_md", "calendario_nome", "somente_dias_uteis",
            "trigger_por_dependencia", "horarios_especificos", "dias_semana",
            "last_execution", "created_at", "updated_at",
        ]
```

new:
```python
        cols = [
            "pipeline_name", "project_name", "domain", "tags", "scheduled_time",
            "schedule_type", "schedule_hour", "schedule_minute", "schedule_dow", "schedule_dom",
            "active", "dag_criada", "envia_msg_inicio", "envia_msg_fim", "envia_msg_erro",
            "depends_on", "dag_start_date", "descricao", "criticidade", "sla_minutos",
            "ambiente", "max_active_runs", "retries_count", "retry_delay_seconds",
            "pool_name", "runbook_md", "calendario_nome", "somente_dias_uteis",
            "trigger_por_dependencia", "horarios_especificos", "dias_semana",
            "dias_horarios_mes", "last_execution", "created_at", "updated_at",
        ]
```

- [ ] **Step 2: Verificar sintaxe e regressão**

Run: `cd /c/Users/carlo/repos/sge_app && export PATH="/c/Users/carlo/AppData/Local/Programs/Python/Python312:/c/Users/carlo/AppData/Local/Programs/Python/Python312/Scripts:$PATH" && python -m py_compile api/routers/pipelines.py && python -m pytest tests/ -v`
Expected: compila sem erro; mesma baseline de 5 falhas pré-existentes (ver Global Constraints), nenhuma falha nova (a coluna `cols` agora tem 34 entradas em vez de 33, em paridade 1:1 com a query SQL — a ordem de inserção em `sched_cols`/`data_sql`/`cols` deve permanecer idêntica entre si).

- [ ] **Step 3: Commit**

```bash
git add api/routers/pipelines.py
git commit -m "feat(api): include dias_horarios_mes in GET /pipelines response"
```

---

### Task 5: Airflow — `_build_cron` traduz `monthly_days_times` para cron superset

**Files:**
- Modify: `dags/etl_dag_factory.py:54-102` (`_build_cron`), `dags/etl_dag_factory.py:266` (call site em `_generate_dag_source`)
- Test: `tests/test_dag_factory_monthly_days_times.py` (novo)

**Interfaces:**
- Produces: `_build_cron(pipeline: dict) -> tuple[str, list[str] | None, dict[int, list[str]] | None]` — 3ª posição é `{dia: [horarios]}` quando `schedule_type == 'monthly_days_times'`, `None` nos demais tipos. Consumida pela Task 6.

- [ ] **Step 1: Escrever os testes (falham — assinatura ainda retorna 2-tupla)**

Create `tests/test_dag_factory_monthly_days_times.py`:

```python
"""
Testes para a tradução de 'monthly_days_times' em DAGs gerados pelo etl_dag_factory.
Os módulos do Airflow não estão instalados neste ambiente de teste — são
stubados via sys.modules antes do import, mesmo princípio do mock de pyodbc
em tests/conftest.py. _build_cron e _generate_dag_source são funções puras
(constroem strings a partir de dicts), não tocam Airflow/banco em runtime.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_AIRFLOW_STUBS = [
    "airflow", "airflow.models", "airflow.operators", "airflow.operators.python",
    "airflow.providers", "airflow.providers.microsoft", "airflow.providers.microsoft.mssql",
    "airflow.providers.microsoft.mssql.hooks", "airflow.providers.microsoft.mssql.hooks.mssql",
    "pendulum",
]
for _mod in _AIRFLOW_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


def _load_factory():
    path = Path(__file__).parent.parent / "dags" / "etl_dag_factory.py"
    spec = importlib.util.spec_from_file_location("etl_dag_factory_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def factory():
    return _load_factory()


def _base_pipeline(**overrides):
    base = {
        "pipeline_name": "TESTE_MDT", "project_name": "BI_CVP", "domain": "TESTE",
        "tags": "ETL", "scheduled_time": "06:00:00",
        "envia_msg_inicio": 0, "envia_msg_fim": 0, "envia_msg_erro": 0,
        "ambiente": "DEV", "schedule_type": "monthly_days_times",
        "horarios_especificos": None, "dias_semana": None,
    }
    base.update(overrides)
    return base


def _job():
    return {"job_name": "job_teste", "job_type": "python", "job_command": "pkg.mod", "execution_order": 1}


def test_build_cron_monthly_days_times_superset(factory):
    pipeline = _base_pipeline(dias_horarios_mes=(
        '[{"dia": 1, "horarios": ["09:00"]}, '
        '{"dia": 15, "horarios": ["14:00", "18:00"]}, '
        '{"dia": 28, "horarios": ["10:00"]}]'
    ))
    cron, horarios_list, dias_horarios = factory._build_cron(pipeline)
    assert cron == "0 9,10,14,18 1,15,28 * *"
    assert horarios_list is None
    assert dias_horarios == {1: ["09:00"], 15: ["14:00", "18:00"], 28: ["10:00"]}


def test_build_cron_other_types_return_none_dias_horarios(factory):
    pipeline = _base_pipeline(schedule_type="daily", dias_horarios_mes=None)
    cron, horarios_list, dias_horarios = factory._build_cron(pipeline)
    assert dias_horarios is None
    assert cron == "0 6 * * *"


def test_build_cron_custom_type_unaffected(factory):
    pipeline = _base_pipeline(schedule_type="custom", dias_horarios_mes=None,
                               horarios_especificos="09:00,10:30", dias_semana="1,3,5")
    cron, horarios_list, dias_horarios = factory._build_cron(pipeline)
    assert dias_horarios is None
    assert horarios_list == ["09:00", "10:30"]
```

- [ ] **Step 2: Rodar e confirmar que falham**

Run: `cd /c/Users/carlo/repos/sge_app && export PATH="/c/Users/carlo/AppData/Local/Programs/Python/Python312:/c/Users/carlo/AppData/Local/Programs/Python/Python312/Scripts:$PATH" && python -m pytest tests/test_dag_factory_monthly_days_times.py -v`
Expected: `ValueError: not enough values to unpack (expected 3, got 2)` nos testes que desempacotam 3 valores.

- [ ] **Step 3: Implementar a extensão de `_build_cron`**

Replace the entire function (`dags/etl_dag_factory.py:54-102`):

old:
```python
def _build_cron(pipeline):
    """Monta o cron a partir do agendamento do pipeline.

    Retorna (cron, horarios) onde horarios é a lista normalizada "HH:MM" quando
    o pipeline usa horários específicos (None caso contrário). Como um único
    cron não expressa horários arbitrários (ex: 09:00 e 10:30 geram também
    09:30 e 10:00), o cron dispara na união minuto×hora e o check_agenda
    pula as combinações que não estão na lista.
    """
    sched = str(pipeline.get("scheduled_time") or "06:00:00")
    stype = (pipeline.get("schedule_type") or "daily").lower().strip()
    horarios_raw = (pipeline.get("horarios_especificos") or "").strip()
    dias_semana  = (pipeline.get("dias_semana") or "").strip()
    parts = sched.split(":")
    h = int(parts[0]) if parts[0].isdigit() else 6
    m = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    dow_expr = dias_semana if dias_semana else "*"

    if horarios_raw:
        times = []
        for t in horarios_raw.split(","):
            t = t.strip()
            if not t:
                continue
            tp = t.split(":")
            try:
                times.append((int(tp[0]), int(tp[1]) if len(tp) > 1 else 0))
            except ValueError:
                continue
        if times:
            mins  = sorted({mm for _, mm in times})
            hours = sorted({hh for hh, _ in times})
            cron = (f"{','.join(map(str, mins))} {','.join(map(str, hours))} "
                    f"* * {dow_expr}")
            return cron, sorted(f"{hh:02d}:{mm:02d}" for hh, mm in times)

    if stype == "hourly":
        return f"{m} * * * *", None
    if stype == "weekly":
        dow = pipeline.get("schedule_dow")
        return f"{m} {h} * * {int(dow) if dow is not None else 1}", None
    if stype == "monthly":
        dom = pipeline.get("schedule_dom")
        return f"{m} {h} {int(dom) if dom is not None else 1} * *", None
    if stype == "biweekly":  # quinzenal: dia D e D+15 de cada mês
        dom = pipeline.get("schedule_dom")
        d = int(dom) if dom is not None else 1
        return f"{m} {h} {d},{d + 15} * *", None
    return f"{m} {h} * * {dow_expr}", None
```

new:
```python
def _build_cron(pipeline):
    """Monta o cron a partir do agendamento do pipeline.

    Retorna (cron, horarios, dias_horarios_mes):
      - horarios: lista normalizada "HH:MM" quando o pipeline usa horários
        específicos (tipo 'custom'), None caso contrário.
      - dias_horarios_mes: dict {dia_do_mes: ["HH:MM", ...]} quando o tipo é
        'monthly_days_times', None caso contrário.
    Como um único cron não expressa horários arbitrários (ex: 09:00 e 10:30
    geram também 09:30 e 10:00), o cron dispara na união minuto×hora(×dia) e
    o check_agenda pula as combinações que não estão na lista configurada.
    """
    sched = str(pipeline.get("scheduled_time") or "06:00:00")
    stype = (pipeline.get("schedule_type") or "daily").lower().strip()
    horarios_raw = (pipeline.get("horarios_especificos") or "").strip()
    dias_semana  = (pipeline.get("dias_semana") or "").strip()
    dias_horarios_raw = (pipeline.get("dias_horarios_mes") or "").strip()
    parts = sched.split(":")
    h = int(parts[0]) if parts[0].isdigit() else 6
    m = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    dow_expr = dias_semana if dias_semana else "*"

    if stype == "monthly_days_times" and dias_horarios_raw:
        import json
        try:
            entries = json.loads(dias_horarios_raw)
        except (ValueError, TypeError):
            entries = []
        dias_horarios = {}
        all_days, all_hours, all_mins = set(), set(), set()
        for entry in entries:
            try:
                dia = int(entry["dia"])
            except (KeyError, TypeError, ValueError):
                continue
            times = []
            for t in entry.get("horarios", []):
                tp = str(t).split(":")
                try:
                    hh, mm = int(tp[0]), int(tp[1]) if len(tp) > 1 else 0
                except ValueError:
                    continue
                times.append(f"{hh:02d}:{mm:02d}")
                all_hours.add(hh)
                all_mins.add(mm)
            if times:
                dias_horarios[dia] = sorted(times)
                all_days.add(dia)
        if dias_horarios:
            cron = (f"{','.join(map(str, sorted(all_mins)))} {','.join(map(str, sorted(all_hours)))} "
                    f"{','.join(map(str, sorted(all_days)))} * *")
            return cron, None, dias_horarios

    if horarios_raw:
        times = []
        for t in horarios_raw.split(","):
            t = t.strip()
            if not t:
                continue
            tp = t.split(":")
            try:
                times.append((int(tp[0]), int(tp[1]) if len(tp) > 1 else 0))
            except ValueError:
                continue
        if times:
            mins  = sorted({mm for _, mm in times})
            hours = sorted({hh for hh, _ in times})
            cron = (f"{','.join(map(str, mins))} {','.join(map(str, hours))} "
                    f"* * {dow_expr}")
            return cron, sorted(f"{hh:02d}:{mm:02d}" for hh, mm in times), None

    if stype == "hourly":
        return f"{m} * * * *", None, None
    if stype == "weekly":
        dow = pipeline.get("schedule_dow")
        return f"{m} {h} * * {int(dow) if dow is not None else 1}", None, None
    if stype == "monthly":
        dom = pipeline.get("schedule_dom")
        return f"{m} {h} {int(dom) if dom is not None else 1} * *", None, None
    if stype == "biweekly":  # quinzenal: dia D e D+15 de cada mês
        dom = pipeline.get("schedule_dom")
        d = int(dom) if dom is not None else 1
        return f"{m} {h} {d},{d + 15} * *", None, None
    return f"{m} {h} * * {dow_expr}", None, None
```

Then update the call site:

old (`dags/etl_dag_factory.py:266`):
```python
    cron, horarios_list = _build_cron(pipeline)
```

new:
```python
    cron, horarios_list, dias_horarios_mes = _build_cron(pipeline)
```

- [ ] **Step 4: Rodar e confirmar que passam**

Run: `cd /c/Users/carlo/repos/sge_app && export PATH="/c/Users/carlo/AppData/Local/Programs/Python/Python312:/c/Users/carlo/AppData/Local/Programs/Python/Python312/Scripts:$PATH" && python -m pytest tests/test_dag_factory_monthly_days_times.py -v`
Expected: 3 testes `PASS` (a chamada em `_generate_dag_source` ainda usa a variável `dias_horarios_mes` sem consumi-la — isso é normal nesta etapa; será usada na Task 6).

- [ ] **Step 5: Rodar a suíte completa para checar regressão**

Run: `cd /c/Users/carlo/repos/sge_app && export PATH="/c/Users/carlo/AppData/Local/Programs/Python/Python312:/c/Users/carlo/AppData/Local/Programs/Python/Python312/Scripts:$PATH" && python -m pytest tests/ -v`
Expected: testes de `test_dag_factory_monthly_days_times.py` todos `PASS`; resto da suíte na mesma baseline de 5 falhas pré-existentes (ver Global Constraints), incluindo `test_dag_compile.py` que continua `PASS` (a função `_generate_dag_source` ainda não foi alterada na sua saída, só ganhou uma variável local nova).

- [ ] **Step 6: Commit**

```bash
git add dags/etl_dag_factory.py tests/test_dag_factory_monthly_days_times.py
git commit -m "feat(dags): translate monthly_days_times into cron superset"
```

---

### Task 6: Airflow — `_generate_dag_source` grava `DIAS_HORARIOS_MES` e estende `check_agenda`

**Files:**
- Modify: `dags/etl_dag_factory.py:329` (nova constante gerada), `dags/etl_dag_factory.py:585-591` (template de `check_agenda`)
- Test: `tests/test_dag_factory_monthly_days_times.py` (acrescentar)

**Interfaces:**
- Consumes: `dias_horarios_mes` (3º valor de `_build_cron`, Task 5)
- Produces: arquivo DAG gerado contém `DIAS_HORARIOS_MES = {...}` e `check_agenda` pula a execução quando `(dia, "HH:MM")` atual não está na configuração.

- [ ] **Step 1: Escrever os testes (falham — constante/checagem ainda não existem na saída)**

Append to `tests/test_dag_factory_monthly_days_times.py`:

```python
def test_generate_dag_source_includes_dias_horarios_mes_constant(factory):
    pipeline = _base_pipeline(dias_horarios_mes='[{"dia": 1, "horarios": ["09:00"]}]')
    source = factory._generate_dag_source(pipeline, [_job()])
    assert "DIAS_HORARIOS_MES = {1: ['09:00']}" in source


def test_generate_dag_source_other_types_have_empty_dias_horarios_mes(factory):
    pipeline = _base_pipeline(schedule_type="daily", dias_horarios_mes=None)
    source = factory._generate_dag_source(pipeline, [_job()])
    assert "DIAS_HORARIOS_MES = None" in source


def test_generate_dag_source_check_agenda_validates_dia_e_horario(factory):
    pipeline = _base_pipeline(dias_horarios_mes='[{"dia": 1, "horarios": ["09:00"]}]')
    source = factory._generate_dag_source(pipeline, [_job()])
    assert "DIAS_HORARIOS_MES.get(_dia" in source


def test_generate_dag_source_compiles(factory):
    pipeline = _base_pipeline(dias_horarios_mes=(
        '[{"dia": 1, "horarios": ["09:00"]}, {"dia": 15, "horarios": ["14:00", "18:00"]}]'
    ))
    source = factory._generate_dag_source(pipeline, [_job()])
    ast.parse(source)  # levanta SyntaxError se o código gerado for inválido
```

- [ ] **Step 2: Rodar e confirmar que falham**

Run: `cd /c/Users/carlo/repos/sge_app && export PATH="/c/Users/carlo/AppData/Local/Programs/Python/Python312:/c/Users/carlo/AppData/Local/Programs/Python/Python312/Scripts:$PATH" && python -m pytest tests/test_dag_factory_monthly_days_times.py -v -k generate_dag_source`
Expected: `AssertionError` (a string `DIAS_HORARIOS_MES` ainda não aparece na saída gerada)

- [ ] **Step 3: Implementar a constante gerada**

old (`dags/etl_dag_factory.py:326-330`):
```python
        f'RUNBOOK_MD    = {repr(runbook_val)}',
        f'CALENDARIO_NOME    = {repr(calendario_val)}',
        f'SOMENTE_DIAS_UTEIS = {dias_uteis_val}',
        f'HORARIOS_ESPECIFICOS = {repr(horarios_list)}',
        f'DATASET_URI   = "orq://pipeline/{pname}"',
```

new:
```python
        f'RUNBOOK_MD    = {repr(runbook_val)}',
        f'CALENDARIO_NOME    = {repr(calendario_val)}',
        f'SOMENTE_DIAS_UTEIS = {dias_uteis_val}',
        f'HORARIOS_ESPECIFICOS = {repr(horarios_list)}',
        f'DIAS_HORARIOS_MES = {repr(dias_horarios_mes)}',
        f'DATASET_URI   = "orq://pipeline/{pname}"',
```

- [ ] **Step 4: Implementar a checagem em `check_agenda`**

old (`dags/etl_dag_factory.py:583-591`):
```python
        "    # Horários específicos: o cron dispara na união minuto×hora;",
        "    # só executa se o horário agendado estiver na lista configurada.",
        "    if HORARIOS_ESPECIFICOS and not str(context.get('run_id', '')).startswith('manual'):",
        "        _die = context.get('data_interval_end') or context.get('logical_date')",
        "        if _die is not None:",
        "            _hhmm = _die.in_timezone(LOCAL_TZ).strftime('%H:%M')",
        "            if _hhmm not in HORARIOS_ESPECIFICOS:",
        "                print(f\"[AGENDA] {_hhmm} fora dos horarios configurados {HORARIOS_ESPECIFICOS} — execucao pulada.\")",
        "                return False",
        "    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
```

new:
```python
        "    # Horários específicos: o cron dispara na união minuto×hora;",
        "    # só executa se o horário agendado estiver na lista configurada.",
        "    if HORARIOS_ESPECIFICOS and not str(context.get('run_id', '')).startswith('manual'):",
        "        _die = context.get('data_interval_end') or context.get('logical_date')",
        "        if _die is not None:",
        "            _hhmm = _die.in_timezone(LOCAL_TZ).strftime('%H:%M')",
        "            if _hhmm not in HORARIOS_ESPECIFICOS:",
        "                print(f\"[AGENDA] {_hhmm} fora dos horarios configurados {HORARIOS_ESPECIFICOS} — execucao pulada.\")",
        "                return False",
        "    # Dia + hora específico: o cron dispara na união dia×minuto×hora;",
        "    # só executa se (dia, horario) atual estiver configurado para aquele dia.",
        "    if DIAS_HORARIOS_MES and not str(context.get('run_id', '')).startswith('manual'):",
        "        _die = context.get('data_interval_end') or context.get('logical_date')",
        "        if _die is not None:",
        "            _local = _die.in_timezone(LOCAL_TZ)",
        "            _dia = _local.day",
        "            _hhmm = _local.strftime('%H:%M')",
        "            if _hhmm not in DIAS_HORARIOS_MES.get(_dia, []):",
        "                print(f\"[AGENDA] dia {_dia} as {_hhmm} fora da configuracao {DIAS_HORARIOS_MES} — execucao pulada.\")",
        "                return False",
        "    hook = MsSqlHook(mssql_conn_id=MSSQL_CONN_ID)",
```

- [ ] **Step 5: Rodar e confirmar que passam**

Run: `cd /c/Users/carlo/repos/sge_app && export PATH="/c/Users/carlo/AppData/Local/Programs/Python/Python312:/c/Users/carlo/AppData/Local/Programs/Python/Python312/Scripts:$PATH" && python -m pytest tests/test_dag_factory_monthly_days_times.py -v`
Expected: 7 testes `PASS`

- [ ] **Step 6: Rodar a suíte completa**

Run: `cd /c/Users/carlo/repos/sge_app && export PATH="/c/Users/carlo/AppData/Local/Programs/Python/Python312:/c/Users/carlo/AppData/Local/Programs/Python/Python312/Scripts:$PATH" && python -m pytest tests/ -v`
Expected: `test_dag_factory_monthly_days_times.py` todos `PASS`; resto da suíte na mesma baseline de 5 falhas pré-existentes (ver Global Constraints)

- [ ] **Step 7: Commit**

```bash
git add dags/etl_dag_factory.py tests/test_dag_factory_monthly_days_times.py
git commit -m "feat(dags): write DIAS_HORARIOS_MES constant and extend check_agenda"
```

---

### Task 7: Airflow — supplement query do factory inclui `dias_horarios_mes`

**Files:**
- Modify: `dags/etl_dag_factory.py:915-922` (feature-detection na função `gerar_dags`)

**Interfaces:**
- Produces: o dict `pipeline` passado a `_build_cron`/`_generate_dag_source` (Tasks 5-6) inclui a chave `dias_horarios_mes` quando a coluna existir no banco.

- [ ] **Step 1: Implementar (mesmo padrão de feature-detection da migration 018)**

old (`dags/etl_dag_factory.py:915-922`):
```python
        # colunas da migration 018 (horários múltiplos) — degradam se ausentes
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' "
            "AND COLUMN_NAME='horarios_especificos'"
        )
        if cursor.fetchone()[0]:
            sched_cols += ", horarios_especificos, dias_semana"
```

new:
```python
        # colunas da migration 018 (horários múltiplos) — degradam se ausentes
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' "
            "AND COLUMN_NAME='horarios_especificos'"
        )
        if cursor.fetchone()[0]:
            sched_cols += ", horarios_especificos, dias_semana"
        # coluna da migration 024 (dia + hora específico) — degrada se ausente
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='etl_pipeline' "
            "AND COLUMN_NAME='dias_horarios_mes'"
        )
        if cursor.fetchone()[0]:
            sched_cols += ", dias_horarios_mes"
```

- [ ] **Step 2: Verificar sintaxe e regressão**

Run: `cd /c/Users/carlo/repos/sge_app && export PATH="/c/Users/carlo/AppData/Local/Programs/Python/Python312:/c/Users/carlo/AppData/Local/Programs/Python/Python312/Scripts:$PATH" && python -m py_compile dags/etl_dag_factory.py && python -m pytest tests/ -v`
Expected: compila sem erro; mesma baseline de 5 falhas pré-existentes (ver Global Constraints), nenhuma falha nova (esta função (`gerar_dags`) não é chamada diretamente por nenhum teste — apenas verificada por compilação, mesmo padrão do projeto para esta função).

- [ ] **Step 3: Commit**

```bash
git add dags/etl_dag_factory.py
git commit -m "feat(dags): fetch dias_horarios_mes column in factory pipeline supplement query"
```

---

### Task 8: Frontend — tipos e helpers (`pipeline.ts`, `pipelineUtils.ts`)

**Files:**
- Modify: `ui-react/src/types/pipeline.ts:33-38`
- Modify: `ui-react/src/components/pipelines/pipelineUtils.ts` (constantes, `ScheduleConfig`, `computeNextRuns`/`dayMatches`/`runsPerDay`, `buildCron`, novos helpers `parseMonthDaysTimes`/`serializeMonthDaysTimes`)

**Interfaces:**
- Produces:
  - `Pipeline.dias_horarios_mes?: string | null`
  - `MonthDayEntry = { dia: number; horariosRaw: string }`
  - `parseMonthDaysTimes(raw: string | null | undefined): MonthDayEntry[]`
  - `serializeMonthDaysTimes(entries: MonthDayEntry[]): string`
  - `ScheduleConfig.monthDays: { dia: number; horarios: string[] }[]`
- Consumed by: Task 9 (`PipelineFormModal.tsx`)

Sem test runner JS configurado — verificação via `npx tsc -b --noEmit` (type-check) após cada mudança.

- [ ] **Step 1: Adicionar o campo ao tipo `Pipeline`**

old (`ui-react/src/types/pipeline.ts:33-38`):
```typescript
  // scheduling avançado (migrations 017/018) — podem vir ausentes
  horarios_especificos?: string | null
  dias_semana?: string | null
  somente_dias_uteis?: number | null
  calendario_nome?: string | null
  trigger_por_dependencia?: number | null
```

new:
```typescript
  // scheduling avançado (migrations 017/018/024) — podem vir ausentes
  horarios_especificos?: string | null
  dias_semana?: string | null
  somente_dias_uteis?: number | null
  calendario_nome?: string | null
  trigger_por_dependencia?: number | null
  dias_horarios_mes?: string | null
```

- [ ] **Step 2: Verificar tipos**

Run: `cd /c/Users/carlo/repos/sge_app/ui-react && npx tsc -b --noEmit`
Expected: sem erros novos (campo opcional, não quebra consumidores existentes)

- [ ] **Step 3: Adicionar constantes e tipo `SCHEDULE_TYPES`/`SCHEDULE_LABELS`**

old (`ui-react/src/components/pipelines/pipelineUtils.ts:1-7`):
```typescript
// ── constants ──────────────────────────────────────────────────────────────

export const SCHEDULE_TYPES = ['daily', 'weekly', 'monthly', 'biweekly', 'hourly_n', 'custom', 'on_demand'] as const
export const SCHEDULE_LABELS: Record<string, string> = {
  daily: 'Diário', weekly: 'Semanal', monthly: 'Mensal', biweekly: 'Quinzenal',
  hourly_n: 'A cada N horas', custom: 'Horários específicos', on_demand: 'Sob demanda',
}
```

new:
```typescript
// ── constants ──────────────────────────────────────────────────────────────

export const SCHEDULE_TYPES = ['daily', 'weekly', 'monthly', 'biweekly', 'hourly_n', 'custom', 'monthly_days_times', 'on_demand'] as const
export const SCHEDULE_LABELS: Record<string, string> = {
  daily: 'Diário', weekly: 'Semanal', monthly: 'Mensal', biweekly: 'Quinzenal',
  hourly_n: 'A cada N horas', custom: 'Horários específicos',
  monthly_days_times: 'Dia + Hora Específico', on_demand: 'Sob demanda',
}
export const MAX_MONTH_DAYS = 5
```

- [ ] **Step 4: Estender `ScheduleConfig` e adicionar tipo/helpers de dia+horário**

old (`ui-react/src/components/pipelines/pipelineUtils.ts`, interface `ScheduleConfig`):
```typescript
// Descreve a configuração de agendamento de forma normalizada para preview/payload
export interface ScheduleConfig {
  type: string
  hour: number
  minute: number
  dow: number
  dom: number
  intervalH: number
  startH: number
  endH: number
  customTimes: string
  weekdays: number[]      // dias da semana selecionados (custom)
  businessDaysOnly: boolean
}
```

new:
```typescript
// Descreve a configuração de agendamento de forma normalizada para preview/payload
export interface ScheduleConfig {
  type: string
  hour: number
  minute: number
  dow: number
  dom: number
  intervalH: number
  startH: number
  endH: number
  customTimes: string
  weekdays: number[]      // dias da semana selecionados (custom)
  businessDaysOnly: boolean
  monthDays: { dia: number; horarios: string[] }[]  // dias do mês + horários (monthly_days_times)
}

// Uma entrada de "Dia + Hora Específico" no formulário (horariosRaw é texto
// livre "HH:MM, HH:MM" — parse/validação via parseCustomTimes, igual ao
// campo de horários do tipo 'custom')
export interface MonthDayEntry {
  dia: number
  horariosRaw: string
}
```

- [ ] **Step 5: Adicionar `parseMonthDaysTimes`/`serializeMonthDaysTimes` (após `parseCustomTimes`)**

old:
```typescript
// Calcula as próximas N execuções, respeitando dia da semana / dia do mês / janela / dias úteis
export function computeNextRuns(cfg: ScheduleConfig, count = 5): string[] {
```

new:
```typescript
// Serializa os blocos de "Dia + Hora Específico" para o JSON persistido
// (dias_horarios_mes). Descarta dias sem nenhum horário válido.
export function serializeMonthDaysTimes(entries: MonthDayEntry[]): string {
  const days = entries
    .map(e => ({ dia: e.dia, horarios: parseCustomTimes(e.horariosRaw) }))
    .filter(e => e.horarios.length > 0)
    .sort((a, b) => a.dia - b.dia)
  return JSON.stringify(days)
}

// Parse do JSON persistido (dias_horarios_mes) de volta para os blocos do formulário
export function parseMonthDaysTimes(raw: string | null | undefined): MonthDayEntry[] {
  if (!raw) return []
  try {
    const data = JSON.parse(raw)
    if (!Array.isArray(data)) return []
    return data
      .filter((e: any) => e && typeof e.dia === 'number' && Array.isArray(e.horarios))
      .map((e: any) => ({ dia: e.dia, horariosRaw: e.horarios.join(', ') }))
  } catch {
    return []
  }
}

// Calcula as próximas N execuções, respeitando dia da semana / dia do mês / janela / dias úteis
export function computeNextRuns(cfg: ScheduleConfig, count = 5): string[] {
```

- [ ] **Step 6: Estender `computeNextRuns` (horários por dia variável)**

old:
```typescript
export function computeNextRuns(cfg: ScheduleConfig, count = 5): string[] {
  if (cfg.type === 'on_demand') return []
  const results: Date[] = []
  const now = new Date()

  function timesForDay(): { h: number; m: number }[] {
    if (cfg.type === 'hourly_n') return hourlyTimes(cfg).map(t => ({ h: +t.slice(0, 2), m: +t.slice(3) }))
    if (cfg.type === 'custom')   return parseCustomTimes(cfg.customTimes).map(t => ({ h: +t.slice(0, 2), m: +t.slice(3) }))
    return [{ h: cfg.hour, m: cfg.minute }]
  }

  function dayMatches(d: Date): boolean {
    const wd = d.getDay(); const dom = d.getDate()
    if (cfg.businessDaysOnly && (wd === 0 || wd === 6)) return false
    switch (cfg.type) {
      case 'daily':    return true
      case 'hourly_n': return true
      case 'weekly':   return wd === cfg.dow
      case 'monthly':  return dom === cfg.dom
      case 'biweekly': return dom === cfg.dom || dom === cfg.dom + 15
      case 'custom':   return cfg.weekdays.length === 0 ? true : cfg.weekdays.includes(wd)
      default:         return true
    }
  }

  const times = timesForDay()
  if (times.length === 0) return []

  const cur = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  for (let dayOffset = 0; dayOffset < 366 && results.length < count; dayOffset++) {
    const d = new Date(cur.getTime() + dayOffset * 86400_000)
    if (!dayMatches(d)) continue
    for (const t of times) {
      const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate(), t.h, t.m, 0)
      if (dt > now) { results.push(dt); if (results.length >= count) break }
    }
  }
  return results.map(d =>
    d.toLocaleString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }),
  )
}
```

new:
```typescript
export function computeNextRuns(cfg: ScheduleConfig, count = 5): string[] {
  if (cfg.type === 'on_demand') return []
  const results: Date[] = []
  const now = new Date()

  function timesForDay(d: Date): { h: number; m: number }[] {
    if (cfg.type === 'hourly_n') return hourlyTimes(cfg).map(t => ({ h: +t.slice(0, 2), m: +t.slice(3) }))
    if (cfg.type === 'custom')   return parseCustomTimes(cfg.customTimes).map(t => ({ h: +t.slice(0, 2), m: +t.slice(3) }))
    if (cfg.type === 'monthly_days_times') {
      const entry = cfg.monthDays.find(e => e.dia === d.getDate())
      return entry ? entry.horarios.map(t => ({ h: +t.slice(0, 2), m: +t.slice(3) })) : []
    }
    return [{ h: cfg.hour, m: cfg.minute }]
  }

  function dayMatches(d: Date): boolean {
    const wd = d.getDay(); const dom = d.getDate()
    if (cfg.businessDaysOnly && (wd === 0 || wd === 6)) return false
    switch (cfg.type) {
      case 'daily':    return true
      case 'hourly_n': return true
      case 'weekly':   return wd === cfg.dow
      case 'monthly':  return dom === cfg.dom
      case 'biweekly': return dom === cfg.dom || dom === cfg.dom + 15
      case 'custom':   return cfg.weekdays.length === 0 ? true : cfg.weekdays.includes(wd)
      case 'monthly_days_times': return cfg.monthDays.some(e => e.dia === dom)
      default:         return true
    }
  }

  const cur = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  for (let dayOffset = 0; dayOffset < 366 && results.length < count; dayOffset++) {
    const d = new Date(cur.getTime() + dayOffset * 86400_000)
    if (!dayMatches(d)) continue
    const times = timesForDay(d)
    for (const t of times) {
      const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate(), t.h, t.m, 0)
      if (dt > now) { results.push(dt); if (results.length >= count) break }
    }
  }
  return results.map(d =>
    d.toLocaleString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }),
  )
}
```

- [ ] **Step 7: Estender `buildCron` (helper de exibição do ViewModal)**

old (`ui-react/src/components/pipelines/pipelineUtils.ts:212-223`):
```typescript
// CRON simplificado para exibição (ViewModal) — pipelines já persistidos
export function buildCron(type: string, h: number, m: number, dow: number, dom: number) {
  const t = (type || 'daily').toLowerCase()
  if (t === 'on_demand') return '(sem agendamento automático)'
  if (t === 'hourly')    return `${m} * * * *`
  if (t === 'daily')     return `${m} ${h} * * *`
  if (t === 'weekly')    return `${m} ${h} * * ${dow}`
  if (t === 'monthly')   return `${m} ${h} ${dom} * *`
  if (t === 'biweekly')  return `${m} ${h} ${dom},${dom + 15} * *`
  if (t === 'custom')    return '(horários específicos)'
  return `${m} ${h} * * *`
}
```

new:
```typescript
// CRON simplificado para exibição (ViewModal) — pipelines já persistidos
export function buildCron(type: string, h: number, m: number, dow: number, dom: number) {
  const t = (type || 'daily').toLowerCase()
  if (t === 'on_demand') return '(sem agendamento automático)'
  if (t === 'hourly')    return `${m} * * * *`
  if (t === 'daily')     return `${m} ${h} * * *`
  if (t === 'weekly')    return `${m} ${h} * * ${dow}`
  if (t === 'monthly')   return `${m} ${h} ${dom} * *`
  if (t === 'biweekly')  return `${m} ${h} ${dom},${dom + 15} * *`
  if (t === 'custom')    return '(horários específicos)'
  if (t === 'monthly_days_times') return '(dia + hora específico)'
  return `${m} ${h} * * *`
}
```

- [ ] **Step 8: Verificar tipos**

Run: `cd /c/Users/carlo/repos/sge_app/ui-react && npx tsc -b --noEmit`
Expected: sem erros (a Task 9 ainda vai construir `ScheduleConfig.monthDays`; até lá, qualquer chamador existente de `computeNextRuns`/`buildCron` continua funcionando pois os novos campos/branches são aditivos)

- [ ] **Step 9: Commit**

```bash
git add ui-react/src/types/pipeline.ts ui-react/src/components/pipelines/pipelineUtils.ts
git commit -m "feat(ui): add monthly_days_times type, parsing and preview helpers"
```

---

### Task 9: Frontend — wizard `PipelineFormModal.tsx`

**Files:**
- Modify: `ui-react/src/components/pipelines/PipelineFormModal.tsx` (FormState, defaultForm, pipelineToForm, schedCfg, showBizToggle, validateStep, buildSchedulePayload, JSX do Step 1, preview do Step 5)

**Interfaces:**
- Consumes: `MonthDayEntry`, `parseMonthDaysTimes`, `serializeMonthDaysTimes`, `MAX_MONTH_DAYS` (Task 8)

- [ ] **Step 1: Adicionar campo ao `FormState` e a `defaultForm`**

old (`ui-react/src/components/pipelines/PipelineFormModal.tsx:11-17`, import):
```typescript
import {
  SCHEDULE_TYPES, SCHEDULE_LABELS, CRITICIDADES, AMBIENTES,
  JOB_TYPES, OBJECT_TYPES, DOW_LABELS,
  type WizJobType, type ScheduleConfig,
  hourlyTimes, parseCustomTimes, computeNextRuns, runsPerDay,
  typeBadgeColor, critColor, buildCron,
} from './pipelineUtils'
```

new:
```typescript
import {
  SCHEDULE_TYPES, SCHEDULE_LABELS, CRITICIDADES, AMBIENTES, MAX_MONTH_DAYS,
  JOB_TYPES, OBJECT_TYPES, DOW_LABELS,
  type WizJobType, type ScheduleConfig, type MonthDayEntry,
  hourlyTimes, parseCustomTimes, computeNextRuns, runsPerDay,
  typeBadgeColor, critColor, buildCron, parseMonthDaysTimes, serializeMonthDaysTimes,
} from './pipelineUtils'
```

old (`ui-react/src/components/pipelines/PipelineFormModal.tsx:54-55`):
```typescript
  schedule_custom_times: string
  schedule_weekdays: number[]
```

new:
```typescript
  schedule_custom_times: string
  schedule_weekdays: number[]
  schedule_month_days: MonthDayEntry[]
```

old (`ui-react/src/components/pipelines/PipelineFormModal.tsx:80`):
```typescript
  schedule_custom_times: '', schedule_weekdays: [1, 2, 3, 4, 5],
```

new:
```typescript
  schedule_custom_times: '', schedule_weekdays: [1, 2, 3, 4, 5], schedule_month_days: [],
```

- [ ] **Step 2: Carregar `schedule_month_days` ao editar (`pipelineToForm`)**

old (`ui-react/src/components/pipelines/PipelineFormModal.tsx:89-107`):
```typescript
function pipelineToForm(p: Pipeline): FormState {
  const horarios = (p.horarios_especificos ?? '').trim()
  const diasRaw  = (p.dias_semana ?? '').trim()
  const weekdays = diasRaw ? diasRaw.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n)) : [1, 2, 3, 4, 5]
  const schedType = horarios ? 'custom' : (p.schedule_type ?? 'daily')
  return {
    ...defaultForm(),
    pipeline_name:           p.pipeline_name,
    project_name:            p.project_name ?? '',
    domain:                  p.domain ?? '',
    tags_list:               p.tags ? p.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
    descricao:               p.descricao ?? '',
    schedule_type:           schedType,
    schedule_hour:           p.schedule_hour ?? 6,
    schedule_minute:         p.schedule_minute ?? 0,
    schedule_dow:            p.schedule_dow ?? 1,
    schedule_dom:            p.schedule_dom ?? 1,
    schedule_custom_times:   horarios,
    schedule_weekdays:       weekdays,
```

new:
```typescript
function pipelineToForm(p: Pipeline): FormState {
  const horarios = (p.horarios_especificos ?? '').trim()
  const diasRaw  = (p.dias_semana ?? '').trim()
  const weekdays = diasRaw ? diasRaw.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n)) : [1, 2, 3, 4, 5]
  const monthDays = parseMonthDaysTimes(p.dias_horarios_mes)
  const schedType = monthDays.length > 0 ? 'monthly_days_times' : (horarios ? 'custom' : (p.schedule_type ?? 'daily'))
  return {
    ...defaultForm(),
    pipeline_name:           p.pipeline_name,
    project_name:            p.project_name ?? '',
    domain:                  p.domain ?? '',
    tags_list:               p.tags ? p.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
    descricao:               p.descricao ?? '',
    schedule_type:           schedType,
    schedule_hour:           p.schedule_hour ?? 6,
    schedule_minute:         p.schedule_minute ?? 0,
    schedule_dow:            p.schedule_dow ?? 1,
    schedule_dom:            p.schedule_dom ?? 1,
    schedule_custom_times:   horarios,
    schedule_weekdays:       weekdays,
    schedule_month_days:     monthDays,
```

- [ ] **Step 3: Verificar tipos**

Run: `cd /c/Users/carlo/repos/sge_app/ui-react && npx tsc -b --noEmit`
Expected: sem erros

- [ ] **Step 4: Conectar `schedCfg` e `showBizToggle`**

old (`ui-react/src/components/pipelines/PipelineFormModal.tsx:300-310`):
```typescript
  const schedCfg: ScheduleConfig = {
    type: form.schedule_type,
    hour: form.schedule_hour, minute: form.schedule_minute,
    dow: form.schedule_dow, dom: form.schedule_dom,
    intervalH: form.schedule_interval_hours,
    startH: form.schedule_start_hour, endH: form.schedule_end_hour,
    customTimes: form.schedule_custom_times,
    weekdays: form.schedule_weekdays,
    businessDaysOnly: form.somente_dias_uteis,
  }
  const showBizToggle = !['custom', 'on_demand'].includes(form.schedule_type)
```

new:
```typescript
  const schedCfg: ScheduleConfig = {
    type: form.schedule_type,
    hour: form.schedule_hour, minute: form.schedule_minute,
    dow: form.schedule_dow, dom: form.schedule_dom,
    intervalH: form.schedule_interval_hours,
    startH: form.schedule_start_hour, endH: form.schedule_end_hour,
    customTimes: form.schedule_custom_times,
    weekdays: form.schedule_weekdays,
    businessDaysOnly: form.somente_dias_uteis,
    monthDays: form.schedule_month_days.map(e => ({ dia: e.dia, horarios: parseCustomTimes(e.horariosRaw) })),
  }
  const showBizToggle = !['custom', 'on_demand', 'monthly_days_times'].includes(form.schedule_type)
```

- [ ] **Step 5: Validação do Step 1 (`validateStep`)**

old (`ui-react/src/components/pipelines/PipelineFormModal.tsx:338-340`):
```typescript
      } else if (t === 'custom') {
        if (parseCustomTimes(form.schedule_custom_times).length === 0) e.push('Informe ao menos um horário válido (HH:MM)')
        if (form.schedule_weekdays.length === 0) e.push('Selecione ao menos um dia da semana')
      } else {
```

new:
```typescript
      } else if (t === 'custom') {
        if (parseCustomTimes(form.schedule_custom_times).length === 0) e.push('Informe ao menos um horário válido (HH:MM)')
        if (form.schedule_weekdays.length === 0) e.push('Selecione ao menos um dia da semana')
      } else if (t === 'monthly_days_times') {
        if (form.schedule_month_days.length === 0) e.push('Adicione ao menos um dia do mês')
        const seenDias = new Set<number>()
        form.schedule_month_days.forEach(entry => {
          if (seenDias.has(entry.dia)) e.push(`Dia ${entry.dia} duplicado`)
          seenDias.add(entry.dia)
          const times = parseCustomTimes(entry.horariosRaw)
          if (times.length === 0) e.push(`Dia ${entry.dia}: informe ao menos um horário válido (HH:MM)`)
          if (times.length > 5) e.push(`Dia ${entry.dia}: no máximo 5 horários`)
        })
      } else {
```

- [ ] **Step 6: Verificar tipos**

Run: `cd /c/Users/carlo/repos/sge_app/ui-react && npx tsc -b --noEmit`
Expected: sem erros

- [ ] **Step 7: `buildSchedulePayload`**

old (`ui-react/src/components/pipelines/PipelineFormModal.tsx:376-408`):
```typescript
  function buildSchedulePayload() {
    const t = form.schedule_type
    const h = String(form.schedule_hour).padStart(2, '0')
    const m = String(form.schedule_minute).padStart(2, '0')
    const base: Record<string, unknown> = {
      schedule_dow: form.schedule_dow,
      schedule_dom: form.schedule_dom,
      somente_dias_uteis: form.somente_dias_uteis ? 1 : 0,
      calendario_nome: form.calendario_nome.trim() || null,
      horarios_especificos: null,
      dias_semana: null,
    }
    if (t === 'hourly_n') {
      return {
        ...base,
        scheduled_time: `${String(form.schedule_start_hour).padStart(2, '0')}:${m}:00`,
        schedule_type: 'custom',
        schedule_hour: form.schedule_start_hour,
        schedule_minute: form.schedule_minute,
        horarios_especificos: hourlyTimes(schedCfg).join(','),
      }
    }
    if (t === 'custom') {
      return {
        ...base,
        scheduled_time: `${(parseCustomTimes(form.schedule_custom_times)[0] ?? '06:00')}:00`,
        schedule_type: 'custom',
        schedule_hour: parseInt((parseCustomTimes(form.schedule_custom_times)[0] ?? '06:00').slice(0, 2)),
        schedule_minute: parseInt((parseCustomTimes(form.schedule_custom_times)[0] ?? '06:00').slice(3)),
        horarios_especificos: parseCustomTimes(form.schedule_custom_times).join(','),
        dias_semana: [...form.schedule_weekdays].sort((a, b) => a - b).join(','),
      }
    }
    return {
      ...base,
      scheduled_time: `${h}:${m}:00`,
      schedule_type: t,
      schedule_hour: form.schedule_hour,
      schedule_minute: form.schedule_minute,
    }
  }
```

new:
```typescript
  function buildSchedulePayload() {
    const t = form.schedule_type
    const h = String(form.schedule_hour).padStart(2, '0')
    const m = String(form.schedule_minute).padStart(2, '0')
    const base: Record<string, unknown> = {
      schedule_dow: form.schedule_dow,
      schedule_dom: form.schedule_dom,
      somente_dias_uteis: form.somente_dias_uteis ? 1 : 0,
      calendario_nome: form.calendario_nome.trim() || null,
      horarios_especificos: null,
      dias_semana: null,
      dias_horarios_mes: null,
    }
    if (t === 'hourly_n') {
      return {
        ...base,
        scheduled_time: `${String(form.schedule_start_hour).padStart(2, '0')}:${m}:00`,
        schedule_type: 'custom',
        schedule_hour: form.schedule_start_hour,
        schedule_minute: form.schedule_minute,
        horarios_especificos: hourlyTimes(schedCfg).join(','),
      }
    }
    if (t === 'custom') {
      return {
        ...base,
        scheduled_time: `${(parseCustomTimes(form.schedule_custom_times)[0] ?? '06:00')}:00`,
        schedule_type: 'custom',
        schedule_hour: parseInt((parseCustomTimes(form.schedule_custom_times)[0] ?? '06:00').slice(0, 2)),
        schedule_minute: parseInt((parseCustomTimes(form.schedule_custom_times)[0] ?? '06:00').slice(3)),
        horarios_especificos: parseCustomTimes(form.schedule_custom_times).join(','),
        dias_semana: [...form.schedule_weekdays].sort((a, b) => a - b).join(','),
      }
    }
    if (t === 'monthly_days_times') {
      const serialized = serializeMonthDaysTimes(form.schedule_month_days)
      const firstTime = schedCfg.monthDays.find(e => e.horarios.length > 0)?.horarios[0] ?? '06:00'
      return {
        ...base,
        scheduled_time: `${firstTime}:00`,
        schedule_type: 'monthly_days_times',
        schedule_hour: parseInt(firstTime.slice(0, 2)),
        schedule_minute: parseInt(firstTime.slice(3)),
        dias_horarios_mes: serialized,
      }
    }
    return {
      ...base,
      scheduled_time: `${h}:${m}:00`,
      schedule_type: t,
      schedule_hour: form.schedule_hour,
      schedule_minute: form.schedule_minute,
    }
  }
```

- [ ] **Step 8: Verificar tipos**

Run: `cd /c/Users/carlo/repos/sge_app/ui-react && npx tsc -b --noEmit`
Expected: sem erros

- [ ] **Step 9: JSX do Step 1 — bloco de dia + horário**

old (`ui-react/src/components/pipelines/PipelineFormModal.tsx:694`, fim do bloco `custom`):
```typescript
            )}

            {!['on_demand', 'hourly_n', 'custom'].includes(form.schedule_type) && (
```

new:
```typescript
            )}

            {form.schedule_type === 'monthly_days_times' && (
              <div className="flex flex-col gap-3">
                {form.schedule_month_days.map((entry, di) => {
                  const usedDays = new Set(form.schedule_month_days.map(x => x.dia))
                  const times = parseCustomTimes(entry.horariosRaw)
                  return (
                    <div key={di} className="bg-canvas border border-edge rounded-lg p-3 flex flex-col gap-2">
                      <div className="flex items-center gap-2">
                        <label className="text-xs text-dim font-medium shrink-0">Dia do mês</label>
                        <select value={entry.dia}
                          onChange={e => {
                            const dia = parseInt(e.target.value)
                            f('schedule_month_days', form.schedule_month_days.map((x, i) => i === di ? { ...x, dia } : x))
                          }}
                          className="bg-panel border border-edge text-ink rounded-md px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500">
                          {Array.from({ length: 28 }, (_, i) => i + 1)
                            .filter(d => d === entry.dia || !usedDays.has(d))
                            .map(d => <option key={d} value={d}>{d}</option>)}
                        </select>
                        <button type="button"
                          onClick={() => f('schedule_month_days', form.schedule_month_days.filter((_, i) => i !== di))}
                          className="ml-auto text-xs text-red-400 hover:text-red-300">Remover dia</button>
                      </div>
                      <input type="text" value={entry.horariosRaw}
                        onChange={e => f('schedule_month_days', form.schedule_month_days.map((x, i) =>
                          i === di ? { ...x, horariosRaw: e.target.value } : x))}
                        placeholder="ex: 09:00, 14:00, 18:00"
                        className="bg-panel border border-edge text-ink rounded-md px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-500" />
                      <p className="text-[10px] text-dim">
                        {times.length > 0
                          ? `${times.length} horário${times.length > 1 ? 's' : ''}: ${times.join(', ')}`
                          : 'Informe ao menos um horário válido (HH:MM)'}
                      </p>
                    </div>
                  )
                })}
                {form.schedule_month_days.length < MAX_MONTH_DAYS && (
                  <button type="button"
                    onClick={() => {
                      const used = new Set(form.schedule_month_days.map(x => x.dia))
                      const nextDia = Array.from({ length: 28 }, (_, i) => i + 1).find(d => !used.has(d)) ?? 1
                      f('schedule_month_days', [...form.schedule_month_days, { dia: nextDia, horariosRaw: '' }])
                    }}
                    className="self-start text-xs text-blue-400 hover:text-blue-300 font-medium border border-edge rounded-md px-3 py-1.5">
                    + Adicionar dia
                  </button>
                )}
                <p className="text-[10px] text-dim">Até 5 dias do mês, cada um com até 5 horários próprios (ex: dia 1 às 09:00 · dia 15 às 14:00 e 18:00).</p>
              </div>
            )}

            {!['on_demand', 'hourly_n', 'custom', 'monthly_days_times'].includes(form.schedule_type) && (
```

- [ ] **Step 10: Verificar tipos**

Run: `cd /c/Users/carlo/repos/sge_app/ui-react && npx tsc -b --noEmit`
Expected: sem erros

- [ ] **Step 11: Preview final (Step 5) — resumo do agendamento**

old (`ui-react/src/components/pipelines/PipelineFormModal.tsx:1070-1072`):
```typescript
                {form.schedule_type === 'custom' && (
                  <div className="col-span-2"><span className="text-dim">Horários:</span> <span className="font-mono text-ink">{parseCustomTimes(form.schedule_custom_times).join(', ') || '—'}</span> <span className="text-dim">· dias:</span> <span className="text-ink">{form.schedule_weekdays.length ? form.schedule_weekdays.slice().sort((a,b)=>a-b).map(d => DOW_LABELS.find(([v])=>v===d)?.[1]).join(', ') : '—'}</span></div>
                )}
```

new:
```typescript
                {form.schedule_type === 'custom' && (
                  <div className="col-span-2"><span className="text-dim">Horários:</span> <span className="font-mono text-ink">{parseCustomTimes(form.schedule_custom_times).join(', ') || '—'}</span> <span className="text-dim">· dias:</span> <span className="text-ink">{form.schedule_weekdays.length ? form.schedule_weekdays.slice().sort((a,b)=>a-b).map(d => DOW_LABELS.find(([v])=>v===d)?.[1]).join(', ') : '—'}</span></div>
                )}
                {form.schedule_type === 'monthly_days_times' && (
                  <div className="col-span-2 flex flex-col gap-0.5">
                    <span className="text-dim">Dias e horários:</span>
                    {schedCfg.monthDays.length > 0 ? schedCfg.monthDays.map(e => (
                      <span key={e.dia} className="text-ink font-mono text-[11px]">Dia {e.dia} às {e.horarios.join(', ')}</span>
                    )) : <span className="text-dim/60 italic text-xs">—</span>}
                  </div>
                )}
```

- [ ] **Step 12: Verificar tipos e build completo**

Run: `cd /c/Users/carlo/repos/sge_app/ui-react && npx tsc -b --noEmit && npm run lint`
Expected: sem erros de tipo nem de lint

- [ ] **Step 13: Commit**

```bash
git add ui-react/src/components/pipelines/PipelineFormModal.tsx
git commit -m "feat(ui): add monthly_days_times day+time builder to pipeline wizard"
```

---

### Task 10: Verificação manual no navegador

**Files:** nenhum (apenas execução)

- [ ] **Step 1: Subir o ambiente de desenvolvimento**

Run: `cd /c/Users/carlo/repos/sge_app/ui-react && npm run dev`
Expected: Vite inicia em `http://localhost:5173` (ou porta similar reportada no terminal)

- [ ] **Step 2: Testar o cenário feliz**

No navegador: abrir o wizard de criação de pipeline → Passo 1 (Agendamento) → selecionar "Dia + Hora Específico" → adicionar dia 1 com horário "09:00", dia 15 com horários "14:00, 18:00", dia 28 com horário "10:00" → confirmar que o resumo "Próximas execuções" aparece corretamente → avançar até o Passo 5 (Revisão) e confirmar que "Dias e horários" lista as 3 entradas → salvar.
Expected: pipeline salvo sem erro; ao reabrir para edição, os 3 dias e seus horários aparecem exatamente como configurados.

- [ ] **Step 3: Testar validações**

No wizard: tentar avançar do Passo 1 com "Dia + Hora Específico" selecionado e nenhum dia adicionado → deve bloquear com mensagem "Adicione ao menos um dia do mês". Adicionar um dia sem preencher horários → deve bloquear com "informe ao menos um horário válido (HH:MM)". Tentar adicionar um 6º dia → botão "+ Adicionar dia" deve desaparecer ao atingir 5.
Expected: todas as validações de UI bloqueiam o avanço como esperado, sem erros no console do navegador.

- [ ] **Step 4: Encerrar o servidor de desenvolvimento**

Run: parar o processo do `npm run dev` (Ctrl+C ou finalizar o processo em background)
