---
description: >
  Cria uma nova migration SQL do ORQUESTRA no padrão idempotente do projeto. Use quando for
  adicionar/alterar tabela ou schema, ou quando o usuário disser "nova migration",
  "criar tabela", "alterar schema", "migration".
argument-hint: "[nome_curto]"
---

# Nova migration — ORQUESTRA

Siga exatamente o padrão de `sql/migrations/`.

1. **Número**: pegue o maior `NNN` em `sql/migrations/` e some 1 (3 dígitos, zero-padded).
2. **Arquivo**: `sql/migrations/NNN_<nome_curto>.sql` com cabeçalho-comentário explicando a
   intenção e a frase "Idempotente — seguro para rodar mais de uma vez."
3. **Idempotência** (tabela nova):
   ```sql
   IF OBJECT_ID('dbo.<tabela>','U') IS NULL
   BEGIN
       CREATE TABLE dbo.<tabela> ( ... );
       CREATE NONCLUSTERED INDEX IX_... ON dbo.<tabela> (...);
       PRINT '[OK] Tabela dbo.<tabela> criada';
   END
   GO
   ```
   Coluna nova: `IF COL_LENGTH('dbo.<tabela>','<col>') IS NULL ALTER TABLE dbo.<tabela> ADD …`.
4. **Degradação graciosa**: todo SELECT/endpoint que ler a tabela fica em try/except e retorna
   vazio se ela ainda não existir (a migration só roda no deploy).
5. **Backend**: se criou router novo, registre em `api/main.py` (import + include).
6. **Validação**: `python -m pytest tests -q` (raiz). Opcional: `python sql/migrate.py --status`.
7. **Avise o usuário**: a migration é aplicada no deploy (`deploy_prod.sh` → `sql/migrate.py`),
   não automaticamente.

Exemplos a copiar: `sql/migrations/032_notificacoes.sql`, `034_dag_pendente.sql`.
