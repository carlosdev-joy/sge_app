---
name: orquestra-porte-chamados-producao
description: "Porte do módulo ServiceNow desenvolvido direto em produção — spec #329 mergeada, F0 (migrations) na PR #333, fila e indicadores já na main"
metadata: 
  node_type: memory
  type: project
  originSessionId: 80eeec2c-39eb-4217-a273-e34383d916bf
  modified: 2026-08-28T11:01:32.668Z
---

Em 2026-08-27 apareceu a branch `backup/producao-20260827`: um módulo ServiceNow
**desenvolvido direto no servidor de produção**, sem PR e sem migration. Spec:
`docs/spec-porte-chamados-producao.md` (**PR #329 MERGEADA**).

**A foto NÃO podia ser mesclada** — pai de 14/06, 806 commits atrás da main; mesclar
apagaria 495 arquivos. É porte, não merge. Método que separou trabalho de resíduo:
comparar cada arquivo com TODAS as versões do histórico → dos 129, **23 não existiam em
versão nenhuma** (5.138 linhas). Ferramenta: [[orquestra-coletar-producao]].

**Preservação:** tags `foto-producao-20260827`, `-v2`, `-v3` + 3 bundles em
`/root/backups-orquestra/`. A branch pública foi removida do GitHub (levava
`dump_prod.sql`, `prod_info` e o endereço do proxy corporativo para repo público).

## Onde está (2026-08-28)

**Na main:** #330 (fix da 1ª senha do Admin), #331 (fila agrupada), #332 (indicadores
aderentes), #329 (spec). **PR #333 ABERTA** = F0, as migrations 094–099.

**Falta:** F1 motor de sync (+ correção do mapa de estados), F2/F3 API com RBAC, F4
front (aba Dashboard), F6 fecho e o deploy único.

## Achados que viraram fase

1. **Mapa de estados — a main está ERRADA.** `sc_req_item` cru `3` é *Closed Complete*;
   produção mapeia para `encerrado`, a main para `aguardando`. Medido no dev: **1556
   registros** com estado errado (todos inativos — o impacto é nas contas por
   `estado_kanban` sobre o espelho inteiro, não na fila). Entra na F1.
2. ⚠️ **As 10 rotas `/admin/servicenow/*` de produção exigem só autenticação** —
   qualquer usuário logado lê e GRAVA a config da integração. Exposição **viva**; fecha
   na F3 com teste de 403.
3. **`PUT /admin/servicenow/config` descarta `proxy` e `grupos` em silêncio** (não estão
   na lista de campos válidos): responde `{"ok": true}` e não grava.
4. **A aba Dashboard de produção está quebrada**: o `DshPanel` foi injetado à mão no
   bundle `index-CeXrH6tU.js`, mas o `index.html` carrega `index-DPNIUJB9.js` — um
   rebuild posterior deixou o bundle bom órfão. Spec do usuário para reimplementar:
   `docs/superpowers/specs/2026-08-28-dashboard-chamados.md` (na foto v3+).
5. **Duas linhagens de migration colidem em número** (089 e 093). As de produção entram
   renumeradas a partir da 094 — e com o MESMO NOME das de lá, porque
   `etl_schema_version` rastreia por nome e produção já as tem registradas.

## Medições reais (dev contra a instância, 2026-08-28)

3439 chamados espelhados · 95 ativos · **59 cards na fila = 59 nos indicadores** · 36
tarefas dentro dos cards · **zero órfãs**. A divergência Fila × Indicadores é hipótese
preventiva, não defeito ativo.

⚠️ **NENHUM deploy até o porte fechar:** o `deploy.sh` sobrescreve `api/` sem perguntar e
a `dist` inteira — hoje isso REMOVERIA de produção o dashboard, o detalhe, os anexos e as
10 rotas admin. Ver [[orquestra-coletar-producao]].

## 🏁 F6 ENTREGUE — a spec fechou (2026-08-28)

- **Manual:** `docs/manual-chamados.md`
- **Smoke:** `scripts/smoke_chamados.sh` — 11 verificações MEDIDAS (não lista
  para conferir a olho). Rodar no servidor: `cd /opt/airflow && bash
  scripts/smoke_chamados.sh`. Em dev: 11/11.
- **Revisão adversarial:** dois defeitos reais achados e corrigidos —
  1. `total`/`por_coluna` de `/chamados` contavam REGISTROS (90 para 57
     trabalhos; `novo` 34 onde a tela mostra 17). Era entrega da F5 que ficou
     por fazer. A tela não exibia nenhum dos dois, então nada aparecia errado.
  2. ⚠️ **A idade do frescor misturava dois relógios** — achado pelo SMOKE, não
     por teste (todo dublê responde com o mesmo relógio). O worker grava
     `iniciado_em` em `-03`, o SQL Server responde `GETDATE()` em UTC → o
     carimbo dizia 180 min para um ciclo de 1 min, e o alarme de "integração
     parada" disparava para sempre. ⚠️ NÃO consertar gravando com `GETDATE()`:
     `ultimo_delta_em()` usa esse `MAX(iniciado_em)` como janela do delta, e a
     empurraria 3h para o FUTURO — o delta pararia de trazer registros, com a
     DAG verde. A idade é calculada em Python.
- **Fio solto DECLARADO:** `aberto_em`/`encerrado_em` vêm do ServiceNow e são
  comparados com `GETDATE()` (aging, fluxo, histórico) — mesma mistura, num
  terceiro fuso. Granularidade de DIAS, só morde perto da virada. Corrigir
  exige saber o fuso da instância — pergunta para quem administra o ServiceNow.
- **§7.1 (órfãs):** virou o passo [4] do smoke. Em dev: zero órfãs, 57 = 57.
