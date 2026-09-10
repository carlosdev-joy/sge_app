---
name: orquestra-malha-componentes
description: "Componentes de malha (Início/Aguarde/Notificação/Fim) — 🏁 FEATURE COMPLETA, ACEITA E EM PRODUÇÃO desde 2026-08-12 (F10–F15, PRs #250–#257; migrations 075+076); aceitação E1–E15 passou no dev"
metadata:
  node_type: memory
  type: project
  originSessionId: f83b731c-0876-4438-b369-1dd4f50c0621
  modified: 2026-08-13T02:39:44.061Z
---

Feature **componentes de malha** do [[orquestra-sge-app]]: Início, Aguarde,
Notificação e Fim como nós do desenho da malha — **açúcar de compilação, zero
executor novo** (Início→agendamento copiado às raízes; Aguarde→expansão N×M na
067 assinada por `origem_no`; Notificação/Fim→eventos da guardiã com marcador
`#no:{id}`). CONTRATO: `docs/malha-componentes-desenho.md` (16 decisões, fases
no §10, cenários E1–E15 no §14). Nasce da [[orquestra-dependencias-pipelines]].

🏁 **COMPLETA NO CÓDIGO E ACEITA (2026-08-03), main 5ab803e.** PRs #250 (F10
modelo/075 + `expandir` canônico+port), #251 (F11 compilador), #252 (F12
canvas), #253 (F13 Início/agendamento), #254 (F14 guardiã/076), #255 (F15
execução+disparo manual), #256 (fix do roteiro), #257 (ordem de deploy).
Suíte final: **1550 passed**, 5 falhas pré-existentes (test_api_v2_4 ×4 +
test_smoke ×1 — batem na API viva) + 1 skip; front tsc 0 / eslint 184-12 /
dist commitada == fonte (provado por diff).

✅ **EM PRODUÇÃO desde 2026-08-12** (ver [[orquestra-deploy-trem-producao]]) —
o trem foi inteiro. O roteiro executado, guardado como referência do próximo
deploy de malha: ordem consolidada no preâmbulo de
`docs/spec-dependencias-pipelines.md` (motor + malha + componentes vão JUNTOS):
migrations **067 e 070–077** na 6c (a **077** veio depois, na PR #258 — índice
da última execução; prompt padrão-NÃO → `s`); dags/ + api + front; consulta do
CSV órfão ANTES do force_all; force_all; GETDATE do SQL antes de despausar a
guardiã; TZ da API ("s" no prompt do compose + recriar + `docker exec date` →
-03); prompt de rebuild do Airflow = **N**; smoke §7 (motor) +
`docs/smoke-malha-componentes.md` (componentes — execução item a item não
confirmada nesta sessão). ⚠️ **A conferência que não mente para a 076**:
`SELECT COUNT(*) FROM sys.foreign_keys WHERE name='FK_dep_evento_pipeline'`
→ tem de vir **0**; sem a 076 a feature sobe MUDA e o smoke ainda "passa" nos
primeiros passos.

## Aceitação final (2026-08-03) — passou inteira
Matriz **E1–E15 do §14 toda PASS** + smoke integrado com malha criada do zero
(Início→2 raízes→Aguarde→2 dependentes→Notificação+Fim: compilar, dry_run,
descompilar/transferir, 422 das 3 portas, agendar, republicar, disparar pela
tela, cascata por push com mesmo ODATE, guardiã acendendo os observadores) +
roteiro de produção validado passo a passo. Provas em UI real (Chromium
headless com login). Gramática §2.1 conferida célula a célula; §12 (inativar
silencia só observadores) provado ao vivo; E6 provou as 2 raízes no MESMO
tick do scheduler.

## Ajustes da tela de LISTA (PR #258, mergeada 2026-08-03, main 531bf9b)
A pedido do usuário, o card da lista passou a responder "essa malha ainda é
usada? qual o tamanho? que horas começa?": **última execução** (instante real
da corrida — NÃO a data_referencia, que é dia de processamento e mostraria
outro dia), **etapas** somadas (etl_pipeline_job) ao lado dos pipelines, e
**gatilho** com precedência honesta (agenda da malha só se VIGENTE = existe
nó Início E raiz com `agenda_no` → senão membros ATIVOS sem dependência →
senão "sob demanda"; agendamento salvo sem Início vira aviso, nunca horário).
Mais: filtros de busca (texto sem acento + status; `normalizeBusca` extraída
p/ `ui-react/src/lib/busca.ts`), remoção do banner do catálogo, e botão
**"O que é a malha?"** com modal explicativo (MANUAL §1.3 reescrito e alinhado
ao modal). **Migration 077** (índice de apoio) + consulta reescrita como
`CROSS APPLY` top-1 por pipeline: o plano saiu de **scan integral de
etl_pipeline_execucao** (tabela SEM expurgo, a cada GET /malhas com refetch
on focus) para **seek coberto**. 17 testes novos; suíte 1567.
⚠️ **Revisão reprovou a 1ª rodada com 2 GRAVES de "o card mente"**: (1) malha
com Início EXCLUÍDO seguia anunciando o horário guardado — e não há rota p/
limpar `agendamento_json`, então seria permanente; (2) pipeline INATIVO (DAG
pausada) contava como gatilho e mandava no card (malha das 08:00 exibindo
06:00). Corrigidos e provados vivos.

## Lições desta feature (valem além dela)
- **Gesto de remoção que reconcilia estado é também porta de CRIAÇÃO** — toda
  guarda de criação vale nele (F11: remoções recompilavam e gravaram ciclo
  real na 067 com HTTP 200).
- **Porta de UI nova mais permissiva que a validada** = defeito de produção
  (F13: modal do Início aceitava quinzenal dia 14–28 → cron "dia 35" →
  Broken DAG; o wizard antigo bloqueava).
- **Doc de deploy que esquece migration deixa a feature MUDA com smoke verde**
  (F15: release note e smoke citavam só a 075).
- **Semáforo que o dado não sustenta é mentira** (F15: Início acendia verde
  contando PULADO/FALHA; observador sem entradas prometia evento que a
  guardiã nunca emitiria; PR #258: card anunciando gatilho de agendamento
  guardado-mas-inerte e contando pipeline inativo). **Regra que emergiu: todo
  campo agregado num card precisa responder "isso é verdade AGORA?" — dado
  guardado para uso futuro e dado desligado não contam.**
- Roteiro de smoke deve ser EXECUTADO no dev antes de virar guia de produção
  (a aceitação achou "apagar a malha" — gesto inexistente — e um passo
  anti-ruído que daria falso-positivo por avaliar data futura).

## GOTCHAs registrados
- pymssql: `LIKE '#no:%%'` precisa do escape duplo.
- 076 derruba `FK_dep_evento_pipeline` (desvio consciente do "zero DDL em
  eventos" do desenho): a FK tornava o marcador impossível e o CASCADE
  apagava histórico de evento.
- Migration aplicada à mão não fica registrada em `etl_schema_version` — a
  6c reaplica (idempotente, inócuo), mas a conferência correta é pelo objeto.
- Ruído único ACEITO: reativar malha inativa pode emitir evento do dia na 1ª
  avaliação (não há carimbo de reativação para cortar).

## Backlog (fora do trem)
- **Register cru edita agenda de raiz assinada sem aviso de divergência** — o
  desenho manda proteger dependências (Decisão 4) mas cala sobre agenda;
  decidir com o usuário: proteção (chip travado) ou aviso de contradição.
- `update_malha` (rename) não migra `etl_malha_no`/`etl_malha_aresta` —
  estoura FK com 500/rollback (não corrompe) ou cascateia nós sem arestas.
- Dois arquivos gerados com o MESMO dag_id quando o pipeline troca de
  projeto/domínio (o factory não remove o caminho antigo) — pré-existente,
  visto em `generated/SMOKE_F10/{dev,Geral}/DEV_F10_C.py`.
- Cópias residuais do bug do domingo (`int(dow or 1)`) em `api/routers/
  sequence.py` e `dags/etl_sequence_import_approve.py` (pré-existentes; o
  `_build_cron` de pipelines.py foi corrigido na F13).
- `_mesma_agenda` não compara `scheduled_time` (inalcançável pelo wizard).

## Ambiente dev (bancada da feature)
UI http://<IP-da-VPS-DEV>:8090 · Airflow :8082 · API :8000 — login `admin` /
senha em `.env.dev` (`DEV_AIRFLOW_PASSWORD`); o login do app valida no
Airflow, perfil ADMIN. SQL só em loopback (túnel SSH). O nginx serve
`ui-react/dist` da árvore e a API roda a imagem de main (realinhada na
aceitação). Fixtures preservadas: malhas SMOKE_F10 / SMOKE_F11_M2 /
SMOKE_F11_E5 / SMOKE_F12 (esta é a malha completa com os 4 componentes) e
pipelines DEV_F10_A..D. **Factory e guardiã ficam PAUSADAS.**
