# 🎼 Maestro — o assistente conversacional de parâmetros DataStage

**Compatibilidade:** Apache Airflow 2.x | SQL Server | provedor de IA já usado pelos assistentes do Caixa Seguro (Anthropic, OpenAI-compatível ou o gateway interno da Caixa) — configurado em Admin › Acessos & Comunicação › Caixa Seguro IA
**Migrations:** **110** (`110_maestro.sql`, F1) — deploy.sh etapa 6c, responder **s**
**Spec:** `docs/spec-maestro-parametros.md` (F1 = #382 · F2 = #383 · F3 = #384 · F4 = esta PR)
**Manual:** `docs/MANUAL_USUARIO.md` §3.11 (usar o Maestro), §4.9 (Admin: interruptor, catálogo, pedidos, retenção), §4.6 (deploy) e §5 (FAQ)
**Depende de:** parâmetros dos jobs DataStage em produção (migrations 107–109, `docs/release-notes/parametros-datastage.md`) e do provedor de IA com chave em *Caixa Seguro IA*

---

## 📋 Resumo

Os parâmetros dos jobs DataStage (release note anterior) exigem um vocabulário —
origem, meses, âncora, dias, formato, tipos — que a maioria dos usuários de
Etapas não domina. O **Maestro** é um avatar de chat na seção *Parâmetros do
job* (Etapas e Fluxos, o mesmo componente): a pessoa descreve o cenário e ele
responde **campo a campo** como preencher, com um cartão da proposta, a prévia
calculada pelo servidor e o botão **Aplicar no editor**. Ele nunca salva: quem
salva é o usuário.

Ele só promete o que está no **catálogo de cenários** do administrador e se
monta com o vocabulário dos parâmetros. Fora disso — dias úteis, feriados,
valor lido de tabela, condições — responde **não atendido**, orienta a
**procurar o administrador** e registra o pedido na aba Admin › Maestro.

> **Segurança do desenho.** A proposta do modelo vem num bloco JSON e passa
> pela **mesma régua do salvar** (`services/job_params`): proposta que a régua
> recusa vira "não atendido" com o erro, mesmo que o modelo diga que atende.
> Valores de parâmetros **Encrypted nunca saem do browser**, nunca vão ao
> provedor, nunca são gravados na conversa nem no catálogo (o contexto leva
> nome, tipo, origem, cálculo e o valor fixo dos parâmetros não-Encrypted). O
> prompt é gerado do vocabulário do código (teste anti-drift).

## 🔍 Como funciona

1. `GET /maestro/status` decide se o avatar aparece: interruptor ligado **e**
   provedor com chave. Fora disso, nada muda nas telas.
2. A cada mensagem, `POST /maestro/conversar` monta o system prompt — vocabulário
   de `job_params`, o que ele NÃO pode prometer, o catálogo (cenários ativos),
   os parâmetros que o job **declara** no lineage ISX (quando extraído), os
   defaults do pipeline e as linhas do editor sem valor Encrypted — e manda o
   histórico (até 12 mensagens, 6 rodadas) ao provedor de IA.
3. O servidor extrai o bloco JSON da resposta, valida com `normalizar_lista`,
   calcula a prévia com `resolver_preview` na referência do "Simular com a
   referência" da seção e devolve `atendido | nao_atendido | pergunta`, a
   proposta, a prévia e avisos (nome que o ISX não declara, tipo divergente,
   sem ISX).
4. Cada rodada vira uma linha em `dbo.etl_maestro_conversa` (sem segredo). Os
   `nao_atendido` são os **pedidos** do Admin.

## 🧩 Admin (F3)

Aba **Maestro** em *Acessos & Comunicação*: interruptor (ligar exige o provedor
com chave em *Caixa Seguro IA*); **catálogo** com editor de receita (marcadores
`<NOME>` que o Maestro troca pelo nome real, *Simular com a referência*, exemplos
— o 1º dos 4 primeiros cenários ativos vira sugestão de abertura do chat —,
ativo/inativo); **pedidos não
atendidos** (tratar/reabrir). A instalação vem com 10 cenários semeados pela
migration 110. Retenção: 180 dias, na DAG `etl_log_cleanup`.

## 🚀 Deploy

| Passo | O quê |
|---|---|
| 6c | Migration **110** → **s** (tabelas `etl_maestro_cenario` e `etl_maestro_conversa`, semente, `maestro_enabled = 0`). Sem ela: avatar oculto, aba do Admin diz que a migration falta, nada quebra |
| `api/` | `routers/maestro.py`, `services/maestro.py`, `services/caixa_ia.py` (conversa multi-rodada) → **sim** |
| `dags/` | `dags/etl_log_cleanup.py` (tarefa `limpar_conversas_maestro`) → **sim**; é arquivo de DAG, **não** exige restart do worker |
| `dist/` | **sim** (avatar/chat em Etapas e Fluxos; aba Maestro no Admin) |
| `.env` | nada novo: a chave do provedor já está cifrada em `etl_app_config` (`ORQUESTRA_CONN_KEY` da API) |
| `config/` | **n** (nginx de produção está à frente do repo) |
| Depois | Admin › Caixa Seguro IA: provedor com chave (e *Verificar* verde); Admin › **Maestro**: ligar. Nada aparece antes disso |

⚠️ **Provedor externo.** O que vai ao provedor: o system prompt (catálogo,
nomes e tipos dos parâmetros declarados no ISX, as linhas do editor e os
defaults do pipeline com nome, tipo, origem, cálculo **e o valor fixo dos
parâmetros não-Encrypted** — até 200 caracteres cada —, pipeline/job) e o texto
que o usuário digita. Valores Encrypted nunca. Se a política da instalação
exigir que nada saia da rede, use o gateway interno da Caixa.

## ✅ Conferência pós-deploy (spec §7)

a) Admin › Maestro: interruptor ligado com o provedor verificado; catálogo com os 10 cenários.
b) Etapas › etapa DataStage com ISX extraído: o avatar aparece ao lado de *Importar do DataStage*; em etapa storedproc não aparece.
c) "carga mensal do mês anterior, data inicial e final" → explicação campo a campo, cartão com `pDataIni`/`pDataFim` (nomes do ISX), prévia = 1º e último dia do mês passado; *Aplicar no editor* → linhas no editor; salvar → `GET /pipelines/{p}/fluxo` devolve o cálculo.
d) Fluxos › o mesmo job no painel da etapa: avatar e aplicar funcionam no dock.
e) "último dia útil do mês anterior" → não atendido + orientação; Admin › Maestro › *Pedidos* lista com pipeline/job/matrícula; marcar tratado remove da lista.
f) "o job precisa da senha do banco" → Encrypted **sem valor**; `SELECT proposta_json FROM dbo.etl_maestro_conversa` sem nenhum valor; log da API sem o valor.
g) Desligar no Admin → o avatar some (cache de 5 min ou F5); `POST /maestro/conversar` → 503.
h) Provedor com chave errada → o chat mostra o erro do provedor ("Chave de API inválida (Anthropic)" ou "(provedor)") e um toast; *Caixa Seguro IA › Verificar* nomeia a etapa. (Só erro de configuração interna — lib ausente, `ORQUESTRA_CONN_KEY` — vira "Maestro temporariamente indisponível — contate o administrador".)
i) Tema escuro: painel, bolhas e cartão legíveis; o painel fica acima do modal e abaixo dos toasts.
j) Gateway da Caixa com histórico: conversa de 2+ rodadas — a resposta não pode vir prefixada com "Assistente:" nem continuar o transcrito.
k) Anthropic com adaptive thinking: conversa de 2+ rodadas aceita.
l) Resposta longa (> 4.000 caracteres): a rodada seguinte continua funcionando.
m) Manhã seguinte: log da DAG `etl_log_cleanup`, task `limpar_conversas_maestro` → `{"tabela": "ok", "apagadas": N, "retencao_dias": 180}`.

**Conferido no DEV (2026-09-10, pela API, com um provedor OpenAI-compatível de mentira dentro do container; sem DataStage, sem provedor real, sem browser):** a — só a parte da API (`GET /maestro/status` com as 4 sugestões; a aba do Admin foi exercitada pela API na F3); c — só as prévias: os 10 cenários da semente atendidos com os valores certos na referência 2026-03-15 (nomes do ISX, *Aplicar* e salvar não conferidos: o job do DEV não tem ISX válido e não há browser); e — pela API `/maestro/admin/pedidos` (3 pedidos listados com pipeline/job/motivo, um tratado); f — só a tabela (`etl_maestro_conversa` sem nenhum valor; o log da API não foi inspecionado); g — 503 "desligado" e 503 "sem provedor" (F1); l — resposta longa truncada (F1); a função da retenção rodou no worker com a conexão pymssql real (F3). **Pendentes de ambiente real:** b, d, i (browser), h (chave inválida num provedor real), j, k (gateway da Caixa e Anthropic com histórico), m (DAG agendada).
