---
description: >
  Checklist de qualidade do ORQUESTRA antes de commitar/abrir PR. Use quando o usuário pedir
  "revisar", "checklist", "antes do PR", "validar mudanças".
---

# Revisão de qualidade — ORQUESTRA

Rode e reporte cada item. **Não abra PR sem o usuário pedir.**

## Migrations
- [ ] Numeração sequencial correta? Idempotente (`IF OBJECT_ID … IS NULL`) + `GO`?
- [ ] Leitura no backend degrada se a tabela não existir?

## Backend
- [ ] Router novo registrado em `api/main.py` (import + include)?
- [ ] `python -m pytest tests -q` — sem novas falhas (baseline: 5 falhas pré-existentes de auth).

## Frontend
- [ ] `npm run build` em `ui-react/` passa (tsc + vite) e `dist/` foi recommitado?
- [ ] Cores no padrão claro+escuro? Rode os greps de regressão (esperado: vazio, fora do log
  viewer `bg-gray-950` e do gradiente do header):
  ```bash
  grep -rnoE "[^:]bg-(green|red|amber|yellow|blue|orange|emerald|purple)-900" ui-react/src --include=*.tsx
  grep -rnoE "[^:]text-(green|red|amber|blue|purple)-(200|300)" ui-react/src --include=*.tsx
  ```

## Git
- [ ] Branch de feature (não `main`)? Commit claro no estilo do projeto?
- [ ] PR só se o usuário pediu.
