---
name: orquestra-spec-chamados-servicenow
description: "Spec dos chamados da engenharia (ServiceNow → Orquestra) — docs/spec-chamados-servicenow.md, RASCUNHO na PR #297; espelho read-only via DAG 3/3h + tela /chamados (kanban) + indicadores; construção SÓ depois do deploy da malha"
metadata: 
  node_type: memory
  type: project
  originSessionId: afee62fa-1c2e-4d5f-ba52-084b20f5cf9e
  modified: 2026-08-14T00:41:23.234Z
---

**docs/spec-chamados-servicenow.md** (PR #297, 2026-08-09, RASCUNHO aguardando
aprovação) — a engenharia enxerga hoje os chamados do ServiceNow da empresa
inteira misturados; a spec cria o recorte do grupo num painel próprio DENTRO do
Orquestra (decisão da entrevista: intranet-only → Orquestra já tem login/RBAC/
deploy; painel externo e Visual Task Board nativo foram descartados).

**Desenho:** DAG `etl_servicenow_sync` (3/3h, Table API, filtro por
`assignment_group`, upsert por `sys_id`) → espelho `etl_chamado` +
`etl_chamado_sync` (migration 088) → tela `/chamados` (RBAC `tela_chamados`,
kanban SOMENTE-LEITURA por estado unificado: novo·andamento·aguardando·
resolvido·outros) + filtros + aba de indicadores (aging, tipo×estado,
entradas×saídas, carga por responsável) + aba ServiceNow no Admin (credencial
mascarada como as `caixa_ia_*`, testar conexão, sincronizar agora).

**5 fases**: F1 migration+DAG · F2 tela/kanban · F3 filtros+aging ·
F4 indicadores · F5 Admin+polimento.

**Decisões da entrevista (2026-08-09):** só leitura na v1 (write-back OUT);
cadência 3h; ~50 abertos; colunas = estados do ServiceNow (fluxo próprio = v2);
equipe + gestão; **construção só DEPOIS do deploy do trem da malha** — o
usuário pediu "só especificar por enquanto".

**⚠️ Restrição-chave:** o dev NÃO alcança o ServiceNow da empresa — F1 testa
com HTTP stubado e o aceite real é o smoke §7 em produção ("dev testa,
produção manda").

**Sonda de validação (2026-08-10):** instância = `cvpsnprod.service-now.com`,
**alcançável da VPS** (401 sem credencial, sem bloqueio de IP). Endpoint
`POST /admin/servicenow/diagnostico` + aba "ServiceNow (sonda)" no Admin —
valida auth, busca grupos, acesso às 4 tabelas com estados reais e volumetria
do grupo; credencial só na chamada, nunca gravada/logada.
✅ **MERGEADA na main (PR #300, squash, 2026-08-11)** por ordem do usuário,
junto com o modo @limpar do reset da malha (PR #299) — validação conjunta.
Bancada dev pronta: working tree de /opt/orquestra-dev na `main`, **imagem da
API rebuildada** (a api/ NÃO é montada no container — rota conferida viva,
401 sem auth) e front servido da `dist/` montada. Falta o usuário RODAR a
sonda com credencial real e trazer os achados (grupo, estados, auth) para
fechar a spec.

**Proxy corporativo (2026-08-13, branch `fix/servicenow-proxy-corporativo` →
main, commits b0fea69 · 40fae0a · 7b73c9a):** da rede da Caixa a sonda dava
`ConnectError` — o compose passou a injetar `HTTPS_PROXY`/`HTTP_PROXY` no
serviço **orquestra-api** (não no Airflow) e a sonda lê `os.environ`.
⚠️ Pré-requisito: as duas variáveis precisam existir no `.env` do servidor
(`http://webproxycvp.adcorp.intranet/`), senão o compose passa string vazia,
`_proxy` vira `None` e nada de proxy é aplicado — sem erro nenhum.

**⚠️ GOTCHA httpx + proxy corporativo — corrigido na PR #304 (2026-08-13,
`1c82b04`), medido dentro do container orquestra-api (httpx 0.27.2):**

1. `proxy=` e `proxies=` **ambos existem** no 0.27.2 — `proxy=` sem aviso,
   `proxies=` com DeprecationWarning (é `proxies` que some no 0.28+). A
   justificativa do 7b73c9a ("`proxy=` só existe no 0.28+") era falsa.
2. **O que importa de verdade:** passar o proxy por parâmetro — em QUALQUER
   das formas — faz o httpx **ignorar o `NO_PROXY`**. Sem parâmetro
   (`trust_env`, o padrão) ele lê `HTTPS_PROXY`/`HTTP_PROXY` E respeita o
   `NO_PROXY`. Num ambiente Caixa o NO_PROXY é o mecanismo de exceção.
3. **O parâmetro nunca foi o que faltava:** o fix real foi o `b0fea69`
   injetar as variáveis no container pelo compose. O `ConnectError` vinha
   da variável ausente, não de parâmetro ignorado.

A PR #304 removeu o parâmetro, pôs `NO_PROXY` + `SERVICENOW_URL` no compose,
tirou a instância do hardcode do `Admin.tsx` (agora `GET
/admin/servicenow/config`) e fez a sonda **reportar a rota na tela** —
`via proxy <url>` ou `conexão direta` com o motivo, porque variável-ausente
e host-isento davam o mesmo sintoma por causas opostas.
`tests/test_admin_servicenow.py` (14 casos) trava a regressão no HANDLER
(não só na regra do httpx) — conferido por mutação.

**🚧 EXECUÇÃO DA SPEC (2026-08-13) — ordem TROCADA a pedido do usuário:** a
configuração, que era F5, virou fundação, porque a credencial salva é o
**executor** do sync.

- ✅ **F1 MERGEADA (PR #305, `eadf581`)** — migration 088 (`etl_chamado`,
  `etl_chamado_sync`, seeds `servicenow_*`, RBAC `tela_chamados`);
  `api/services/servicenow.py` com o domínio (`load_config`,
  `credencial_executora` que NOMEIA o que falta, `url_valida` anti-SSRF);
  aba **ServiceNow** no Admin = credencial executora (senha Fernet, nunca
  volta à tela, senha vazia MANTÉM a atual) + sonda de descoberta, e o
  resultado diz de qual das duas veio a credencial testada.
  ⚠️ 2 defeitos corrigidos no caminho: `mask_secret` não pegava
  `servicenow_senha_enc` (chave sem secret/password/token → token cifrado
  sairia inteiro no `config_list`) e habilitar sem credencial completa era
  aceito. Migration conferida no SQL Server do dev: aplicada, remarcada e
  REAPLICADA com config preenchida — valores sobreviveram, RBAC não duplicou.
- ✅ **F2 MERGEADA (PR #306, `1a1723a`)** — DAG `etl_servicenow_sync` (3h),
  cada tabela independente (ACL por tabela), desativação SÓ dos tipos que
  sincronizaram bem (senão ACL negada zera a fila com cara de "tudo
  resolvido"), ciclo gravado ANTES da 1ª chamada, parcial não falha a task.
  Carregada no Airflow real via DagBag. `dags/utils/servicenow_sync.py` (%s,
  pymssql). Entrou no `CATALOGO_DAGS` (teste anti-drift).
- ✅ **F3 MERGEADA (PR #307, `ecb65a9`)** — `GET /chamados` + tela com kanban
  somente-leitura (sem drag-and-drop: a v1 não escreve). Carimbo de frescor
  (âmbar > 6h) e as TRÊS caras da fila vazia (sync OK / sync em ERRO / nunca
  sincronizou) separadas na resposta. Componente `Aviso` local — o
  `InfoBanner` da casa é azul e DISPENSÁVEL, errado para erro.
- ✅ **F4 MERGEADA (PR #308, `fd31d2d`)** — filtros client-side (opções saem
  do que ESTÁ na fila, não de lista fixa), busca, aging com cor E rótulo,
  "x de y" no cabeçalho e aviso quando o FILTRO zera a fila.
- ✅ **F5 MERGEADA (PR #309, `fbfbc4d`)** — aba Indicadores, SVG puro.
  Paleta validada pelo script da skill `dataviz` nos dois modos (CVD ΔE 24.7
  claro / 26.8 escuro). Zero explícito nas faixas de aging, 14 pontos na
  série mesmo sem movimento, corte do top-10 DECLARADO.

🏁 **SPEC IMPLEMENTADA DE PONTA A PONTA.** Falta o smoke §7 em produção.

**🚦 ENTRADA EM OPERAÇÃO (2026-08-13, produção) — a sequência real:**
1. tela apareceu no menu só depois de logout+login
   ([[orquestra-permissao-nova-exige-relogin]]);
2. faltava o checkbox no cadastro de perfis — PR #310
   ([[orquestra-rbac-recursos-lista-dupla]]);
3. flag ligada 15:44, mas a run lida era a das 15:00 — o cron era `0 */3 * * *`
   e `etl_chamado_sync` VAZIA confirmou (a DAG retorna ANTES de registrar o
   ciclo quando desabilitada);
4. 1º ciclo real morreu com `Connection reset by peer` nas 4 tabelas em 1s →
   **proxy ausente no worker** ([[orquestra-proxy-worker-vs-api]]).

🏁 **2026-08-13: DEPLOY FEITO, SYNC RODOU E TROUXE OS CHAMADOS REAIS.** A
integração está EM OPERAÇÃO em produção — proxy na config resolveu. Passou a
fase de "fazer funcionar"; a fase atual é **usabilidade da apresentação**
(o usuário analisando a tela com dados reais).

✅ **PR #311 MERGEADA (`c7dd6dd`).** Traz: rota de saída em
`servicenow_proxy` (migration **089**) + campo no Admin; DAG imprime a rota
(`via proxy X` / `conexão direta`); **cadência 3h → 15 min** com
`FRESCOR_ALERTA_MINUTOS=60`, `dagrun_timeout=10min`, `retry_delay=2min` e
`tests/test_servicenow_cadencia.py` prendendo a coerência dos quatro.
(Deploy: migration 089 aplicada e proxy preenchido em Admin > ServiceNow.)

**📊 FASE USABILIDADE (2026-08-13, com dados reais do TI_CVP_GERESD_ED):**

⚠️ **A fila conta cada trabalho DUAS vezes** — todo RITM gera uma `sc_task`
filha e o espelho trazia as duas como cards independentes. Pares exatos
denunciaram: 36/36 "Em aberto", 10/10 "Trabalho em andamento", 3/3 "Pendente"
(113 itens para ~60 trabalhos). A task nasce com título `RITM0096880 -
<assunto>` — dá para inferir, mas é convenção de texto.

✅ **PR #312 MERGEADA (`25a2731`) — FALTA DEPLOY (migration 090).** O espelho
grava `pai_sys_id`/`pai_numero` (de `request_item`, com fallback `parent`;
`sysparm_display_value=all` traz número E sys_id sem chamada extra) e
`estado_cru`.

🔜 **DECISÃO DE APRESENTAÇÃO JÁ TOMADA pelo usuário:** *um card por trabalho,
task DENTRO do card do RITM* (nº, estado e responsável dela como linha
interna). Card sem pai continua sozinho. É a PR seguinte, junto com o botão
"Sincronizar agora".

✅ **MAPA DE ESTADOS CORRIGIDO com número MEDIDO (PR #314, `ab6dd0a`) — FALTA
DEPLOY.** Valores confirmados na instância cvpsnprod (grupo TI_CVP_GERESD_ED):
`1`=Em aberto→novo · `2`=Trabalho em andamento→andamento · `6`=Resolvido→
resolvido · **`-5`=Pendente**. Só o `-5` estava errado: em `sc_task` apontava
para `novo` (pior — chamado PARADO com cara de recém-chegado, ninguém
desconfia) e em `sc_req_item` nem existia (caía em `outros`). A coluna
Aguardando ficava vazia. O mapa agora marca ✅ o que foi conferido e diz que o
resto segue assumido.

📋 **BACKLOG combinado:** botão **"Sincronizar agora" na tela de Chamados**
(não no Admin) — dispara a DAG na hora. Endpoint genérico
`POST /airflow/dags/{dag_id}/dagRuns` já existe (perm `acao_executar`), e
`conf: {disparado_por}` CHEGA em `context["params"]` mesmo sem declarar
`params` na DAG (medido no Airflow 2.11.2: `ParamsDict.update` cria chave
nova).

**🩹 Rabo solto do RBAC — ✅ PR #310 MERGEADA (`4cc38c0`, squash, 2026-08-13),
FALTA DEPLOY:** a migration 088 concedia `tela_chamados` a
admin/desenvolvedor/operador e a rota exigia o recurso, mas o **checkbox nunca
existiu** no Admin → Perfis e Permissões: a lista `RBAC_RECURSOS` de
`pages/Admin.tsx` é uma SEGUNDA lista, à mão, e ficou para trás. Permissão sem
interruptor — ninguém mais podia ser habilitado nem revogado. A PR acrescenta o
par e cria `tests/test_rbac_recursos_admin.py` (anti-drift NAV ↔ RBAC_RECURSOS,
conferido por mutação). Detalhe do gotcha em
[[orquestra-rbac-recursos-lista-dupla]].

**PENDÊNCIAS do usuário (§8 da spec) — SEGUEM ABERTAS:** rodar a sonda com a
credencial salva e trazer o nome exato do(s) grupo(s) e os **valores reais de
estado das 4 tabelas** (o dict `ESTADOS` da F2 está com os valores ASSUMIDOS
da spec); tipo de auth (assumido Basic); se "aberto" inclui
resolvidos-não-fechados. O desenho tolera: grupo é config e estado não
mapeado cai em `outros` VISÍVEL.

Ver [[orquestra-sge-app]], [[orquestra-ajustes-malha-inventario]].
