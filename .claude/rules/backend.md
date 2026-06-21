---
paths:
  - "api/**"
---

# Regras de backend — ORQUESTRA

(Carregam só ao trabalhar em `api/`.)

- Endpoints usam `Depends(get_current_user | require_perm(PERM_*) | get_admin_user)`.
- Banco via `get_db_conn()`; **toda leitura degrada se a tabela não existir** (try/except → vazio).
- **Router novo → registrar em `api/main.py`** (import + lista de include).
- Migrations idempotentes, numeração sequencial (`sql/migrations/NNN_*.sql`), blocos com `GO`.
- Trabalho que precisa sobreviver a restart **não** usa BackgroundTask in-process: persista a
  intenção no banco e reconcilie (padrão `services/dag_reconcile.py`).
- Notificar usuário: `from services.notify import add_notificacao` (best-effort).
- Valide com `python -m pytest tests -q`.
