---
name: orquestra-chamados-tabela-copiar-notas
description: "Orquestra/Chamados: lista virou tabela arrastável, número copiável, e o conserto da coleta de anotações (PR #340)"
metadata:
  type: project
---

Trabalho de 2026-08-28 na tela de Chamados. Spec em
`docs/spec-chamados-tabela-copiar-notas.md` (F1–F11). **PRs #338–#343
MERGEADAS na main** (2026-08-28) — ver [[gotcha-squash-prs-empilhadas]] para como o squash
das empilhadas foi resolvido.

1. **Tabela no lugar da lista.** `TabelaChamados` serve painel e indicadores:
   célula vazia mantém a coluna (era isso que jogava o responsável para a
   posição do prazo), largura arrastável com piso e memória por tabela em
   `localStorage`. Sem biblioteca de grid — deploy offline.
2. **Copiar o número** no card, tasks filhas, nas duas tabelas e no detalhe.
   Degradação real: sem `navigator.clipboard`, cai no `execCommand`; falhando,
   seleciona o número e diz "use Ctrl+C".
3. **As anotações.** ⚠️ Descoberta: elas **nunca foram coletadas** — ver
   [[gotcha-servicenow-tabela-inacessivel]]. Motor passa a parsear o diário de
   `work_notes`/`comments` pela tabela-mãe `task`, em lote. Em dev: 0 → 996
   notas, idempotente.

Também nesta leva: filtros de tipo/categoria/sem-atribuição no kanban, badge de
categoria, paginação de 10 nas tabelas, filtro de responsáveis por marcação
múltipla, incidente com destaque e topo da fila, raia "Outros" só quando tem
card — e o card repintado com `bg-panel` (estava com `bg-canvas`, o token do
FUNDO da página: era isso que os fazia parecer "quadrados jogados").

Também entraram: solicitante no card/modal/tabelas/filtros (⚠️ o campo muda de
nome por tabela — `requested_for` no RITM, `caller_id` no incidente) e a saída
do "tipo de demanda", que repetia o título.

### ✅ Deploy em produção FEITO em 2026-08-28
Migrations **094–100** aplicadas (produção estava na 093, zero drift), `dags/`
sincronizado, worker reiniciado. Confirmado pelo usuário: **as notas aparecem**
(a tabela vivia com 0 linhas — ver
[[gotcha-servicenow-tabela-inacessivel]]) e **os solicitantes também**.

⚠️ Ao deploy respondeu-se **NÃO** para `config/` e `docker-compose.yaml`:
produção tem um `nginx.conf` À FRENTE do repo — com `location /shell/`
(terminal web + chat IA, processo do host na porta 8765) e
`location = / { return 302 /v2/; }`. Sobrescrever mataria o `/shell/`.
**Enquanto o repo não receber esses blocos, todo deploy vai perguntar isso — e
um "s" distraído derruba o terminal.** O usuário ia trazer o nginx.conf e o
compose de produção para portar. O `return 302 /v2/` parece LEGADO (o React
monta em `/`, sem `basename` nem rota `/v2`) e merece decisão consciente.

O deploy final (só `api/`, a #343) foi feito e **confirmado pelo usuário**:
solicitante na lista do painel e frescor apontando para a `delta`. 🏁 **Tudo
desta leva está em produção e validado.**

**Pendências que sobraram:**
1. portar `nginx.conf` + `docker-compose.yaml` de produção para o repo — o
   usuário ia trazer os arquivos;
2. a F6 do porte (smoke, manual, revisão adversarial de fecho) —
   ver [[orquestra-porte-chamados-producao]].

### Roteiro do deploy (confirmado 2026-08-28)
O script usado é **`/opt/git/deploy.sh`** (o `deploy_prod.sh` existe mas não é
o usado). Ele **se auto-atualiza** do repo antes de rodar, faz `--dry-run` das
migrations na **etapa 6c**, lista as pendentes e **pergunta** antes de aplicar;
`set -e` aborta se alguma falhar, deixando a API antiga no ar.
⚠️ Esta leva mexe em `dags/utils/servicenow_sync.py` ⇒ **restart do worker**
(o próprio deploy.sh detecta e oferece, desde a #313).
Depois: rodar um delta e conferir `SELECT COUNT(*) FROM dbo.etl_chamado_nota`
(era 0) e `demandante` preenchido nos incidentes.

Ver [[orquestra-porte-chamados-producao.md]] para o porte que contém isto.
