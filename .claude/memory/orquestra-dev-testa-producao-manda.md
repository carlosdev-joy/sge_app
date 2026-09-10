---
name: orquestra-dev-testa-producao-manda
description: "REGRA do usuário (2026-08-02): testar na estrutura dev, mas TODAS as regras/padrões do ambiente de produção Caixa continuam mandando — deploy, componentes, degradação, auth"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f83b731c-0876-4438-b369-1dd4f50c0621
  modified: 2026-08-02T07:39:30.694Z
---

**REGRA (usuário, 2026-08-02), vale para a retomada F2–F6 e as fases F7–F9 da
malha do [[orquestra-dependencias-pipelines]] e qualquer trabalho no
[[orquestra-sge-app]]:** o ambiente dev da VPS serve para EXECUTAR e testar os
cenários; o código entregue segue as regras do ambiente de produção Caixa —
"para não quebrar nada, mantendo o padrão de deploy, uso de componentes e as
demais regras do app atual".

**Why:** a produção Caixa tem restrições que o dev não reproduz (pip offline,
LDAP, deploy por etapas com confirmação). Código que "funciona no dev" mas
ignora essas regras quebra silenciosamente no deploy real — exatamente a classe
de acidente que a reversão da F2–F6 ensinou.

**How to apply — checklist do que "regras de produção" significa aqui:**
- **Deploy**: pip OFFLINE (`--no-index --find-links=wheels`) — dep Python nova
  = wheel commitada em `api/wheels/`; `dist/` do front rebuildada e commitada;
  migration T-SQL idempotente numerada, aplicada pela etapa 6c do deploy.sh
  (default NÃO — documentar no PR); deploy parcial é realidade: código degrada
  quando coluna/tabela ainda não existe (padrão `INFORMATION_SCHEMA`/
  `OBJECT_ID` + try/except estreito).
- **Nada de dev vazando p/ produção**: Dockerfile.dev (PyPI), `.env.dev`,
  `webserver_config.dev.py` (DB auth; produção é LDAP), portas e loopback do
  compose dev — são exclusivos do dev e NÃO entram no caminho de produção.
- **Componentes/UI**: reusar os componentes existentes (`ui/Button`, `Modal`,
  `Toast`, painéis, tokens `ink/dim/panel/edge/canvas` nos DOIS temas, padrões
  do canvas React Flow); permissões via `tela_*`; pt-BR na interface.
- **Código**: placeholders por árvore (`dags/` %s pymssql, `api/` ? pyodbc);
  consts antes de helpers no dag_factory; chaves CI em junção cross-table por
  nome; testes com baseline (zero falhas NOVAS, nunca zero absoluto).
- **Processo**: branch por fase, PR com validação vs baseline + revisão
  adversarial, merge SÓ com autorização; smoke em produção continua sendo do
  usuário.
- **Validação da retomada**: cenário passa quando EXECUTADO no dev (DAG rodando
  de verdade), e o código ainda respeita tudo acima — as duas coisas, nunca só
  a primeira.
