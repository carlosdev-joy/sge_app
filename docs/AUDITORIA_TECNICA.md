# ORQUESTRA — Auditoria Técnica e Roadmap de Evolução

> Data: 2026-06-12 · Versão analisada: v2.3.0 · Escopo: código, arquitetura, segurança, processo
> Contexto operacional: rede corporativa **sem acesso à internet** (firewall externo bloqueado).
> Toda dependência nova precisa ser baixada previamente, versionada no Git (wheels/, vendor/) e instalada offline no servidor.

---

## 1. Fotografia atual (o que existe hoje)

| Camada | Componente | Situação |
|---|---|---|
| Frontend | `ui/index.html` — SPA vanilla JS | **11.545 linhas em 1 arquivo** (CSS + JS + HTML inline), 8 abas, zero dependência externa (ponto positivo p/ air-gap) |
| API | `api/main.py` — FastAPI 0.115 | **3.556 linhas em 1 arquivo**, 43 endpoints, pyodbc, sem camada de autenticação própria |
| Orquestração | Airflow 2.11.2 (CeleryExecutor) | Factory (`dags/etl_dag_factory.py`) gera DAGs como string Python em `dags/generated/` |
| Dados | SQL Server (DMDB41) + Postgres 13 (metadados Airflow) | 18 migrations manuais numeradas em `sql/migrations/` |
| Broker | Redis 7.2 | Sem senha |
| Proxy | nginx | Serve UI + proxy para API/Airflow |
| Alertas | Teams webhook + DAG `orquestra_sla_monitor` | Adaptive Cards, dedup em `etl_sla_alert` |

**Pontos fortes a preservar:** zero dependência de CDN (funciona 100% offline), SQL sempre parametrizado (sem SQL injection detectado), migrations idempotentes, healthchecks em todos os containers, wheels pré-baixadas no Git, detecção graciosa de colunas (UI nova funciona com banco antigo).

---

## 2. Gaps por severidade

### 2.1 CRÍTICO — Segurança

| # | Gap | Evidência | Risco |
|---|---|---|---|
| S1 | **API ORQUESTRA sem autenticação** | Endpoints `/pipelines/register`, `/admin` etc. não validam credencial; o "admin check" confia no campo `requested_by` enviado pelo cliente | Qualquer máquina da rede corporativa pode criar/apagar pipelines se forjar o header |
| S2 | **Admin hardcoded** | `ADMIN_USERS = {"CVT38571"}` em `api/main.py` (e duplicado no JS da UI) | Sem RBAC; troca de responsável exige deploy |
| S3 | **Senha em localStorage em texto claro** | UI grava `user`/`pass` no localStorage | Qualquer XSS ou acesso físico ao navegador expõe a credencial de rede do usuário |
| S4 | **CORS `allow_origins=["*"]`** | API e Airflow | Combinado com S1, permite chamadas de qualquer página interna |
| S5 | **`job_command` sem escape para shell** | `etl_dag_factory.py` interpola comando direto no `SSHOperator(command=...)` | Quem cadastra job pode injetar comando arbitrário no servidor DataStage — hoje aceitável (usuários confiáveis), inaceitável com mais perfis |
| S6 | **FERNET_KEY vazio no compose / Redis sem senha / Postgres airflow:airflow** | `docker-compose.yaml` | Conexões Airflow sem criptografia em repouso; defaults conhecidos |

### 2.2 ALTO — Arquitetura e manutenibilidade

| # | Gap | Impacto |
|---|---|---|
| A1 | UI monolítica de 11,5k linhas | Cada mudança arrisca quebrar o arquivo todo (já aconteceu: o `/` solto que derrubou o `<script>` inteiro). Merge de duas pessoas no mesmo arquivo é inviável |
| A2 | API monolítica de 3,5k linhas | Sem routers por domínio, sem service layer; conexão DB aberta/fechada manualmente em ~40 funções (sem pool, sem context manager) |
| A3 | Zero testes automatizados, zero CI | Toda regressão é descoberta em produção pelo usuário |
| A4 | Erros viram `HTTPException(500, str(e))` | Vaza detalhes internos e não gera log estruturado para diagnóstico |
| A5 | `--reload` no CMD do uvicorn em produção | Custo de CPU e risco de reload espúrio |
| A6 | `nginx:latest` sem pin | Quebra silenciosa em rebuild offline (imagem precisa estar pré-carregada com versão fixa) |

### 2.3 MÉDIO — Processo e operação

| # | Gap |
|---|---|
| P1 | Sem backup automatizado do volume Postgres (`postgres-db-volume`) nem rotina documentada de backup das tabelas `etl_*` no SQL Server |
| P2 | Migrations aplicadas manualmente via sqlcmd, sem tabela de controle (`schema_version`) — não há como saber o que já rodou em cada ambiente |
| P3 | Sem tags Git/semver — CHANGELOG existe mas releases não são marcadas |
| P4 | Pastas legadas duplicadas (`script/`, `scripts/`, `sql/`, arquivos `versao_*.html` na raiz) confundem onboarding |
| P5 | Documentação de usuário inexistente (resolvido nesta entrega: `docs/MANUAL_USUARIO.md`) |

---

## 3. Decisão de stack frontend: React?

**Recomendação: sim, migrar — mas para Vite + React vendorizado, de forma incremental, e só depois de resolver S1–S4.**

### Por que o HTML puro chegou ao limite
- 11,5k linhas num arquivo é o teto prático de manutenção; o bug do regex que derrubou o login inteiro é sintoma direto.
- Não há componentização: o card de pipeline, a tabela de jobs e os filtros são copiados/colados entre telas.
- Não há build → não há lint, minificação, tree-shaking, nem detecção de erro antes do deploy.

### Como fazer React num ambiente air-gapped (o ponto crítico)
O build acontece **fora do servidor** (na máquina de desenvolvimento ou neste fluxo Git). O servidor nunca precisa de npm/internet:

1. Projeto `ui-react/` com **Vite + React + TypeScript**. `package-lock.json` versionado.
2. `npm run build` gera `ui-react/dist/` — **commitar o `dist/` no Git** (artefato estático, igual ao index.html de hoje). O nginx passa a servir `dist/` em vez de `ui/`.
3. O servidor só faz `git pull` + `docker compose restart ui-nginx`. Zero dependência de rede, exatamente como hoje.
4. Opcional: vendorizar o cache npm (`npm ci --offline` com `.npm-cache/` no Git) caso um dia o build precise rodar dentro da rede.

### Estratégia incremental (sem big bang)
- **Fase A**: extrair o JS atual do index.html para módulos (`ui/js/api.js`, `ui/js/malha.js`...) e o CSS para `ui/css/app.css`. Sem framework ainda — só dividir o monólito. Ganho imediato de manutenção, risco quase zero.
- **Fase B**: criar o app React e migrar **uma tela por vez**, começando pela Malha (mais nova, mais isolada). As duas UIs coexistem atrás do nginx (`/` = legado, `/app` = React).
- **Fase C**: migrar Dashboard, Pipelines (wizard), Jobs, Logs, Governança, Admin. Desligar o legado.

Stack sugerida (tudo vendorizável, sem chamadas externas em runtime): React 18 + TypeScript + Vite + TanStack Query (cache/polling de API) + Zustand (estado) + Tailwind (build-time, não CDN). Para o diagrama da Malha: `@xyflow/react` (React Flow).

---

## 4. Roadmap recomendado

### Fase 1 — Segurança e fundação (antes de qualquer migração de UI)
1. **Autenticação na API**: middleware FastAPI que valida o Basic Auth contra o Airflow (mesma credencial de hoje) em **todos** os endpoints de escrita; emite e valida um token de sessão curto em vez de guardar a senha no localStorage.
2. **RBAC simples em banco**: tabela `etl_usuario_perfil (matricula, perfil)` com perfis `admin | operador | leitura`. Substituir `ADMIN_USERS` hardcoded. UI esconde/mostra ações conforme perfil retornado no login.
3. **Restringir CORS** à origem do nginx; senha no Redis; FERNET_KEY obrigatória no `.env` (já é o padrão da casa — só validar no startup e recusar subir sem ela).
4. **Escape de `job_command`** no factory (`shlex.quote` para shell, validação de whitelist para módulo Python).
5. Remover `--reload` do uvicorn; pinar `nginx:1.27`.

### Fase 2 — Qualidade e processo
6. **Tabela `etl_schema_version`** + script `sql/migrate.py` que aplica migrations pendentes em ordem (roda offline via pyodbc, sem dependência nova).
7. **Testes**: pytest para a API (sqlite/mock para unit, smoke contra ambiente dev) + `python -m py_compile` dos DAGs gerados como gate. Vendorizar wheels do pytest no Git.
8. **Refatorar API** em routers (`routers/pipelines.py`, `routers/agenda.py`...) + `db.py` com context manager e pool — sem mudar contrato dos endpoints.
9. Tags Git por release (`v2.3.0`) e limpeza das pastas legadas.

### Fase 3 — Frontend
10. Fase A da migração (modularizar o index.html atual).
11. Fases B/C (React incremental, dist/ no Git).

### Fase 4 — Operação madura
12. Backup automatizado: `pg_dump` agendado do Postgres + rotina BACKUP DATABASE/bcp das tabelas `etl_*` documentada com o DBA.
13. Métricas: expor `/metrics` (Prometheus client vendorizado) ou ao menos endpoint de estatísticas para monitoração interna.
14. Relatórios com anexo (SharePoint/Graph) conforme discutido — adiado por decisão.

---

## 5. Regras de ouro para o ambiente air-gapped (formalização do que já praticamos)

1. Nenhum runtime pode depender de internet: sem CDN, sem `pip install` no servidor, sem fonts externas.
2. Toda dependência nova entra no Git **antes** do deploy: wheels em `wheels/`, imagens Docker salvas/pré-carregadas com versão pinada, `dist/` de frontend buildado.
3. Segredos (`MSSQL_CONN_STR`, `FERNET_KEY`, futura senha do Redis) vivem **somente** em `/opt/airflow/.env` no servidor — nunca no Git.
4. Deploy = `git pull` + migration via sqlcmd + `docker compose build/up` — nada além disso pode ser necessário.
