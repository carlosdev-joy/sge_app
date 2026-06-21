# Catálogo — skills e subagents do ORQUESTRA

## Skills (`.claude/skills/`)
| Skill | O que faz |
|---|---|
| `/nova-migration` | Cria migration idempotente no padrão (próximo NNN, `IF OBJECT_ID`, `GO`) |
| `/deploy` | Roteiro de deploy (`deploy.sh --no-deps`, migrations antes do restart) |
| `/revisao-pr` | Checklist de qualidade (tema, migrations, pytest, build, commits) |
| `/backlog` | Registra item em `dbo.etl_backlog` + gera script |

## Subagents (`.claude/agents/`)
| Agent | Papel |
|---|---|
| `orquestra-backend` | FastAPI/MSSQL/Airflow; migrations, routers, services |
| `orquestra-frontend` | React/Tailwind; tokens de tema; react-query; componentes `ui/` |
| `orquestra-datastage` | operador DS; polling SSH; wave/attach; heartbeat/órfã |
| `orquestra-deploy` | `deploy.sh`; `--no-deps`; migrations; risco postgres/rede |
| `orquestra-reviewer` | gate de qualidade read-only (tema, migrations, testes, build) |

## Built-ins do Claude (sem precisar criar)
`/code-review` · `/security-review` · `/verify`

## Config & regras
- `.claude/settings.json` — allowlist de permissões + `env` (afine com `/update-config`).
- `.claude/rules/{backend,frontend}.md` — regras escopadas por path.

## Convenções (ver `CLAUDE.md`)
- Migrations idempotentes; leitura degrada sem a tabela.
- Cores sempre claro + escuro (`docs/ui-temas-cores.md`).
- **Nunca abrir PR sem o usuário pedir; nunca commitar segredo.**
- `.claude/` e `CLAUDE.md` ficam só no repo (guards de `.gitignore`/`.dockerignore`).
