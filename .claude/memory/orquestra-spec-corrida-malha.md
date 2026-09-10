---
name: orquestra-spec-corrida-malha
description: "Spec da corrida de malha (etl_malha_execucao) — 🏁 F1–F12 EM PRODUÇÃO desde 2026-08-12 e o interruptor malha_corrida_ativa está LIGADO (=1); PRs #277–#288, migrations 085/086/087"
metadata: 
  node_type: memory
  type: project
  originSessionId: 80c9c0f8-d96b-4823-bfbd-f3a91475f9ad
  modified: 2026-08-13T02:39:28.810Z
---

**docs/spec-malha-execucao.md** — a malha ganhou um CICLO com identidade
(`etl_malha_execucao`): o Início abre, o Fim fecha, o ODATE é carimbado **uma
vez** e herdado. Nasceu do incidente `Carga_Vida`, cuja causa raiz é: *dependente
com DAG não republicada continua com cron e calcula o próprio ODATE*.

**Estado (2026-08-06): as 12 fases estão MERGEADAS na `main`** — PRs #277 a #288,
migrations **085** (modelo) e **086** (`app_base_url`). Suíte em **3173
passando**; as 5 vermelhas (`test_api_v2_4` ×4, `test_smoke` ×1) são
pré-existentes e de autenticação.

🏁 **EM PRODUÇÃO E LIGADA desde 2026-08-12** — o deploy do trem inteiro foi
feito e o interruptor **`malha_corrida_ativa` está em `1`**, com a corrida
rodando. Ver [[orquestra-deploy-trem-producao]]. Os 3 pré-requisitos listados
adiante (suíte com `ORQ_TEST_MSSQL_PASSWORD`, `GRANT SELECT` em `etl_malha_no`,
desvio de relógio) já não são porteiros — ficam como histórico do que se exigiu
para virar a chave.

**Depois da spec, na mesma `main` (também já em produção):**
- **PR #290 — o termo virou `ciclo` na tela.** `corrida` continua no modelo e no
  código (tabela, colunas, variáveis, componentes); só o que a pessoa lê mudou.
  A Decisão 74 foi INVERTIDA na spec com o motivo escrito.
- **PR #291 — o aviso do Teams por malha (migration 087).** `etl_malha.grupo_id`
  aponta para um canal do catálogo que já existia (`etl_msg_grupo`, migration
  049), e o nó Notificação ganhou tela (duplo clique) com canal, modelo,
  mensagem, placeholders e prévia renderizada pelo SERVIDOR. Degradação: malha
  sem canal, canal inativado ou sem webhook caem no canal global — o aviso sai.

✅ **DEPLOY FEITO (2026-08-12).** A ordem que se executou: etapa 5 (`dags/`) → 6c
(migrations 085, 086 e 087) → `api/`+front → **`force_all` disparado à parte, e
SÓ na F5** (o gesto não está no `deploy.sh`: é trigger de `etl_dag_factory` com
`conf={"force_all": true}`). Guardar como roteiro para o próximo deploy de malha.

**O que foi exigido antes de virar a chave** (§18 da spec — histórico):
- rodar a suíte **COM** `ORQ_TEST_MSSQL_PASSWORD` — 16 testes ao vivo pulam em
  silêncio sem ela, e são os únicos que provam que o corte do modo SEQUÊNCIA sai
  do `aberta_em` da corrida e não da janela de 12h (o comando está em
  `docs/ambiente-dev.md`);
- conferir `GRANT SELECT` em `etl_malha_no` para os **dois** logins (guardiã e
  API): sem ele, "adiar 5 min" vira "a corrida nunca fecha";
- **medir** o desvio de relógio worker × banco em produção (no dev são 3h, e em
  produção é *presumido* zero — `_fechar_dia_anterior` compara os dois).

**O que a spec mudou de comportamento** (resumo por fase): F1 modelo · F2 guardiã
abre/fecha · F3 disparo pela API abre e o operador encerra · F4 card e painel
param de mentir · F5 ⚠️ ODATE (a do `force_all`) · F6 janela = corrida · F7
hold/teto/atraso · F8 rerun reabre · F9 progresso no card e o "não abriu" · F10
faixa e painel de "o que está travando" · F11 Teams/Dashboard/filtro · F12
duração típica e histórico.

**O `%` que o usuário pediu existe** e é o da Decisão 56b: mede **TEMPO**
ponderado pela duração típica, com `≈`, piso `n ≥ 5`, sumindo sem histórico, e
sempre como SEGUNDO número. Percentual de **contagem** de pipelines é proibido em
toda superfície — inclusive via `aria-valuenow`/`valuemax`, que faz o leitor de
tela calcular "57%" sozinho (por isso `ui/Progress` exige `aria-valuetext`).

Ver [[orquestra-sge-app]], [[orquestra-malha-data-unica]], [[orquestra-no-aguarde]],
[[orquestra-deploy-trem-producao]].
