---
name: orquestra-chamados-triagem-ia
description: "Spec de triagem de chamados com o gateway de IA da Caixa — F1–F4 COMPLETAS e MERGEADAS na main (PRs #322/#323/#324); deploy em produção só parcial: dags/ e restart do worker ficaram para a janela"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5f271463-f62f-424c-b6a1-1e07dbd2b1dc
  modified: 2026-08-21T11:11:28.871Z
---

Porta para o produto o que o painel `ritm_geresd_ed.html` (repo **`sge`**, pasta
`chamado` — privado, é o depósito de insumos do usuário) já fazia na estação.
Spec em `docs/spec-chamados-triagem-ia.md` (nasce na PR #322).

**Estado em 2026-08-21 — F1–F4 MERGEADAS na main** (`6f4f203` → `c8b8e1c` →
`93edc0c`), na ordem **#322 → #323 → #324**. Suíte após os merges: **3473
passam**, as mesmas 5 falhas pré-existentes, zero novas.

⏳ **Deploy de produção rodado PARCIAL, de propósito** (havia processos críticos
em execução): migrations + API + UI sim; **`dags/` respondeu `n`** e o worker
NÃO reiniciou. Enquanto isso: sync grava pelo código velho, colunas novas ficam
`NULL`, painéis novos aparecem vazios, triagem desligada. **Falta na janela sem
jobs:** deploy com `s` na etapa 5 → restart do worker → ligar
`chamados_triagem_habilitada` em Admin > ServiceNow → os 3 smokes da #324.
Junto vai a **F0 do ciclo fechado (PR #303)**, que também mora em `dags/`.
- **#322 (F1)** — provedor `caixa_gateway` em `services/caixa_ia.py` +
  verificação de conexão visível no Admin.
- **#323 (F2+F3)** — migrations 091/092, conteúdo do chamado no espelho,
  derivações e contadores na tela, `/chamados/historico`, e a **guarda de
  frescor** de `dags/utils/` (ver [[orquestra-worker-cacheia-dags-utils]]).
- **#324 (F4)** — migration 093, `dags/utils/triagem_ia.py`, task `triagem`
  separada do ciclo, laudo no card + modal, `/chamados/sugestoes`, interruptor
  próprio `chamados_triagem_habilitada` (**nasce desligada**).
- **#321** — instalador offline do Claude Code (ver [[orquestra-claude-code-offline]]).

⚠️ **O squash da PR base fez a empilhada conflitar** — confirmado de novo aqui,
e desta vez em **8 arquivos de CÓDIGO**, não só na `dist/`. É ruído: a main após
o squash era idêntica ao topo da branch base nesses 8 (conferir com
`git diff <main> <topo-da-base> -- <arquivos>` **antes** de resolver), então
ficar com a versão da branch é o certo. A `dist/` nunca se resolve arquivo a
arquivo — remover e `npm run build` (ver [[orquestra-ajustes-malha-inventario]]).

💡 **Prova de que a resolução estava certa:** preparei a mesma entrega por duas
vias (rebase `--onto` e merge com resolução manual) e comparei —
`git diff` entre as duas deu **árvore idêntica**. Vale sempre que houver dúvida
sobre uma resolução de conflito grande.

⚠️ **Worktree de sessão anterior não tem `node_modules`** (não é versionado), e
`npm run build` morre com `tsc: not found`. Symlink do repo principal resolve,
desde que `package.json`/lock não tenham mudado: `ln -s
/opt/orquestra-dev/ui-react/node_modules <worktree>/ui-react/node_modules`.

📌 **PR #315 (card único + botão "Sincronizar agora") foi FECHADA em 2026-08-21**
a pedido — o conceito será refeito nos moldes dos arquivos novos. A branch
`feat/chamados-card-unico` (`c665335`) ficou preservada no remoto porque o
**`POST /chamados/sincronizar` nasceu lá e não existe em nenhuma PR mergeada**.

## O gateway de IA interno da Caixa
`http://servicosstdev.caixavidaeprevidencia.intranet/api/claude/chat/completions`,
header **`x-api-key`** (chave `<chave do gateway>`), modelo `claude-sonnet-4-6`,
resposta no formato **Anthropic** (`content[0].text`) apesar da rota
`chat/completions`, e **sem proxy** — é intranet. Não cabia em `anthropic` nem
em `openai_compat`; daí o provedor próprio.

⚠️ **Pode mudar o plano do Claude Code no servidor** ([[orquestra-claude-code-offline]]):
se o gateway expuser `/v1/messages`, o `ANTHROPIC_BASE_URL` dispensaria liberar
`api.anthropic.com` no proxy.

⚠️ **O repo `sge` tem credencial de produção em texto claro** (usuário
`user.power_bi` do `cvpsnprod.service-now.com`, com senha, em
`validar_prompt.py`, `buscar_jeferson.py`, `buscar_ritm_bucc.py`) e a chave do
gateway. Está no histórico do git — editar o arquivo não resolve; precisa
rotacionar. **Pendente de decisão do usuário.**

## GOTCHAs que estas PRs pagaram para aprender
- **Proxy tem que ser MEDIDO, não deduzido.** Deduzir de flag + env erra nos
  dois sentidos: `NO_PROXY` isenta o host com a opção ligada, e provedores com
  `trust_env` atravessam o proxy com ela desligada. Use
  `services.servicenow.proxy_efetivo`, que lê o transporte montado.
- **`trust_env=False` desliga também `SSL_CERT_FILE`/`SSL_CERT_DIR`** — CA
  corporativa para de valer e o erro chega como `ConnectError`, com cara de
  DNS/rota.
- **`NVARCHAR(n)` conta unidades UTF-16, não caracteres**: emoji fora do BMP
  vale 2. Truncar por `len()` do Python passa no teste e estoura com Msg 8152.
- **Regex de nome de objeto precisa de borda dos DOIS lados**: `TB_[A-Z_]+`
  captura `TB_CLIENTE2` como `TB_CLIENTE` e `DBTB_VENDAS` como `TB_VENDAS` —
  nomes de objetos que existem.
- **`\s*` casa quebra de linha**: num journal, a captura pula para a linha
  seguinte. Use `[^\S\n]*`.
- **`x or DEFAULT` com número**: `dias=0` virava o default de 10.
- **Gravação no upsert precisa do seu próprio `try`**: sem ele, coluna ausente
  (migrations ainda não aplicadas) faz a exceção escapar e o ciclo fica órfão
  em "em andamento" para sempre.
- **Teto de QUANTIDADE não protege o `dagrun_timeout`**: 20 chamados × 45 s de
  timeout já passam dos 10 min da DAG. Quem protege é orçamento de TEMPO
  (`ORCAMENTO_TRIAGEM_S`), e um gateway *lento* (não caído) leva junto o sync
  do espelho por causa do `max_active_runs=1`.
- **Hash de "já processei" congela o retrabalho**: gravado também quando o
  laudo saiu do fallback, uma queda de 20 min do gateway deixaria dezenas de
  chamados no veredito heurístico para sempre — o texto deles nunca mais muda.
  Erro de FALHA re-enfileira; erro de CONFIGURAÇÃO não.
- **`x or DEFAULT` e `body.get(campo)` para booleano**: chave ausente vira
  `False` e desliga a feature em silêncio. Só gravar o que veio no corpo.
- **A regra do corte UTF-16 mora em `dags/utils/texto_sql.py`** — escrita duas
  vezes, saiu errada duas vezes.
