# 🤖 Agentes de IA — o agente de mapeamento DataStage

**Compatibilidade:** Apache Airflow 2.x | SQL Server | gateway de IA com identidade por usuário (provedor `caixa_gateway`) | acesso SSH ao servidor do DataStage (`DS_SSH_*`, o mesmo do Console) | extração ISX (a mesma do lineage, `docs/release-notes/lineage-isx.md`) | `.dsx` em `DSX_BASE_DIR` (opcional)
**Migrations:** **116** (IA desacoplada do Caixa), **117** (tabelas dos agentes), **118** (limpa títulos gravados antes da redação — **no mesmo deploy da F4**), **119** (semente dos aprendizados, só dados) — etapa 6c, responder **s**
**Spec:** `docs/spec-agentes-datastage.md` (F0–F7) · `docs/spec-agentes-feedback-progresso.md` (progresso em tempo real) · `docs/spec-agentes-admin.md` (✅ entregue — prompt editável e criação de agentes: ver `docs/release-notes/agentes-admin.md`)
**Manual:** `docs/MANUAL_USUARIO.md` §3.12 (usar), §4.11 (administrar), §4.6 (deploy), §5 (FAQ)
**PRs:** #417/#418 (spec) · #419 F0 · #420 F1 · #421 F2 · #422 F2b · #423 + #424 F3 · #425 F4 · #426 F5 · #427 F6 (+ port das melhorias de produção de 22/09) · #428 progresso SSE, duração, inferência do projeto, barra do topo · #429 ajustes de produção de 23/09, histórico sem corte · F7 (esta nota, manual, smoke)

---

## 📋 Resumo

Entender um fluxo DataStage que já existe — que jobs uma sequence chama, de que
tabela um job lê, que parâmetros ele recebe, como rodou ontem — era abrir o
Designer, ler ISX/DSX à mão, e o que um engenheiro descobria não ficava para o
próximo. A nova tela **Agentes** traz um agente que conversa sobre isso: lê primeiro
o que o Orquestra já sabe, consulta o DataStage ao vivo quando precisa (**sem
alterá-lo**), explica, mostra o grafo e **vai registrando** — o que as ferramentas
leram vira fato; o que ele conclui vira proposta que você aprova; o que ele aprende
sobre o ambiente passa por um curador.

```
Agentes › Mapeamento DataStage                 [Curadoria] [Histórico] [Nova conversa]
┌──────────────────────────┐ ┌──────────────────────────────────────────────────────┐
│ Conversas            (5) │ │ Projeto: BI_PRESTAMISTA  trocar projeto                │
│ [Buscar pelo título…   ] │ │                                                        │
│ HOJE                     │ │         quais jobs a SeqSsdPrs_ODS chama? ▐█████▌      │
│ ▌quais jobs existe na…   │ │ ┌────────────────────────────────────────────────────┐ │
│  BI_PRESTAMISTA    01:08 │ │ │ A sequence chama 8 jobs: SsdPrs_OdsPropostas_00…   │ │
│ ONTEM                    │ │ │ Consultei: projeto › extração ISX                  │ │
│  Conversa sem título     │ │ │ respondido em 42s                                  │ │
│  BI_PRESTAMISTA   22/09  │ │ └────────────────────────────────────────────────────┘ │
│                          │ │ ┌ Proposta de registro · lineage · SeqSsdPrs_ODS ────┐ │
│ As conversas ficam       │ │ │ O que será gravado   │ Evidência lida pelas ferr.  │ │
│ guardadas por 30 dias.   │ │ │ carrega o ODS de…    │ "children": [{"job_name"…   │ │
└──────────────────────────┘ │ │                         [Recusar] [Aprovar]        │ │
                             │ └────────────────────────────────────────────────────┘ │
                             │ ⠿ Extraindo a definição do job via istool — até 60 s…  │
                             └──────────────────────────────────────────────────────┘
```

> **Impacto para a engenharia ETL:** uma pergunta em português no lugar de horas
> no Designer; o que um descobre fica para o próximo (fatos, propostas aprovadas,
> aprendizados validados). O agente só **lê** — nenhuma alteração no DataStage.
>
> **Impacto para a operação:** o agente consulta o servidor DataStage com teto de
> sessões SSH (`agentes_ssh_max`, padrão 10), no máximo 2 extrações ISX por
> pergunta, cache pelo `lastModified`, e nunca repete uma chamada que já falhou de
> forma definitiva.
>
> **Impacto para a segurança:** acesso ao agente **usuário a usuário**, só perfil
> `desenvolvedor`, concedido pelo administrador; cada pergunta vai ao gateway com a
> **identidade do usuário** (`cvp-<matrícula>`), não a do app; segredos (senha,
> token, `{iisenc}`) são mascarados antes de gravar e antes de ir ao gateway.

---

## 🚚 O que entra

| Fase | O quê |
|---|---|
| **F0** | Camada de IA **desacoplada do módulo Caixa** (`ia_provedor.py`, chaves `ia_*`, aba **IA**); Caixa Seguro, triagem e Maestro seguem funcionando (migration 116 copia, não apaga) |
| **F1** | Tabelas (117), RBAC por agente (`require_agente`), identidade por usuário no gateway e a sonda de cadastro |
| **F2 / F2b** | Ferramentas: `resolver_projeto`, `base`, `dsjob` (5 comandos só-leitura), `isx_extrair` (mesmo executor do botão da Governança), `dsx_consulta` (só leitura dos `.dsx`) — orquestradas pelo backend, com allowlist em código |
| **F3** | A tela: seletor, chat, aviso de cadastro, grafo, links; **Admin › Agentes** |
| **F4** | Histórico de 30 dias com busca e retomada (118 limpa títulos antigos) |
| **F5** | **Fatos** gravados pelo que as ferramentas leem; **propostas** do modelo com evidência literal, aprovadas pelo dono da conversa |
| **F6** | **Aprendizados**, guarda de reexecução e **curadoria** (119 = semente em rascunho) |
| **#428** | Progresso em tempo real (SSE), duração de cada resposta, inferência do projeto pelo prefixo do job, barra do topo |
| **#429** | Ajustes feitos em produção em 23/09 (4 ferramentas por pergunta, filhos de sequence direto no ISX, anti-alucinação), filhos de sequence registrados como fatos, histórico sem corte, curadoria × histórico |

---

## ⚙️ Como funciona

- **Uma pergunta = uma rodada orquestrada no backend** (o gateway não tem tool-calling):
  o modelo pede uma ferramenta num bloco JSON, o backend confere a allowlist, executa e
  devolve o resultado como **dado delimitado**. Até **4 ferramentas**, até **2 extrações
  ISX**, **240 s** por relógio (abaixo dos 300 s do nginx).
- **Projeto primeiro.** Nenhuma consulta ao DataStage sem projeto **validado** contra a
  base e os `.dsx`. O agente infere pelo prefixo do job ou lista os projetos conhecidos.
- **Base primeiro.** A `base` devolve a lineage ISX gravada e os **fatos** (com idade;
  `dsjob` vence em `agentes_fato_validade_dias`, ISX/DSX pela data do job/arquivo).
- **Fatos × propostas.** O que a ferramenta leu grava direto (retrato por origem, com
  obsolescência). O que o modelo conclui só grava se o **dono da conversa aprovar** — e
  a evidência tem de ser trecho literal de uma leitura daquela pergunta.
- **Aprendizados.** Erro/acesso/grafia viram aprendizado validado automaticamente, com
  texto **gerado por código** (a mensagem da ferramenta fica só na evidência, que o
  modelo nunca recebe). Sugestões do modelo entram em rascunho e só valem depois que um
  **curador** valida. Até 5 aprendizados relevantes vão ao prompt.
- **Guarda de reexecução.** Chamada que falhou de forma permanente não roda de novo — na
  conversa e, com o erro validado e vigente, para ninguém.
- **Progresso.** `POST /agentes/datastage/conversar/stream` emite o passo atual; o endpoint
  JSON segue existindo (a tela cai nele se a API ainda não tiver o stream).

---

## 🔒 Como a segurança funciona

- **Tela × agente.** `tela_agentes` é um recurso normal (perfil ∪ overrides). O **agente**
  exige perfil `desenvolvedor` **e** o recurso em `permissoes_extra` — o que vier de perfil
  é ignorado (risco 26). O admin passa sempre.
- **Identidade.** Sempre da sessão, nunca do corpo; sem matrícula não chama o gateway;
  nunca cai para `cvp-orquestra`.
- **Segredos.** `redigir()` + máscara estrutural de parâmetros + `{iisenc}` por formato,
  antes de gravar (mensagem, título, fato, proposta, evidência, aprendizado) e antes de ir
  ao modelo. Limite conhecido: formato real do `dsjob` ainda não confirmado (D-07).
- **Injeção persistente.** Saída de ferramenta vai delimitada (`</ferramenta>` escapado);
  aprendizados de ferramenta com texto fixo; interpretação aprovada chega ao modelo
  rotulada ("aprovada por um usuário, não lida por ferramenta"), sem a matrícula.
- **Sem IDOR.** Conversa, proposta e aprendizado alheios dão 404 igual ao inexistente.
- **No navegador.** A conversa aberta fica guardada por usuário (a chave leva a matrícula)
  e é apagada no logout e na sessão expirada.
- **Dado pessoal.** O nome de quem criou/alterou o job vai ao modelo (para a resposta), mas
  **não** à evidência (de proposta e de aprendizado), que não vence — lá fica só a matrícula.
  O modelo ainda pode citar o nome no *valor* de uma proposta: o manual orienta a não
  aprovar proposta com nome de pessoa (a régua não filtra nomes).
- **Carga.** Até **2 perguntas em andamento por usuário em cada processo da API** (a
  seguinte recebe 429 `rodadas_simultaneas` — não entra em fila); com os 2 processos de
  hoje (`--workers 2`), até 4 no total. A vaga volta quando a rodada termina.

---

## 🚀 Deploy

| Passo | O quê |
|---|---|
| 6c | Migrations **116, 117, 118, 119** → **s**. ⚠️ A **118** tem de ir no **mesmo** deploy que sobe a F4 (zera os títulos gravados antes da redação; adiada, zeraria também os títulos já corretos). Todas idempotentes |
| `api/` | **sim** (rotas e serviços dos agentes, `ia_provedor`) |
| `dags/` | **sim** — `etl_log_cleanup.py` (`limpar_conversas_agentes`, F4), `utils/triagem_ia.py` + `etl_servicenow_sync.py` (F0, já em produção desde 22/09) e `utils/isx_engine.py` (#427: `+` e `..` no caminho da API REST — a **API** o lê pelo mount de `dags/`). O `deploy.sh` pergunta pelo restart do worker por causa de `dags/utils/`: **s** é inofensivo (nenhuma DAG importa o `isx_engine`) |
| `dist/` | **sim** (tela Agentes, Admin › Agentes, aba IA) |
| `.env` | nada novo |
| `config/` | **n** — o SSE usa `X-Accel-Buffering: no` na própria resposta; o nginx não muda |
| Depois | Admin › **IA**: provedor `caixa_gateway` e *Verificar* verde · Admin › **Agentes**: preencher *Campo da identidade no gateway* (contrato do gateway), texto do aviso, ligar os dois interruptores · Usuários & Perfis: **liberar a tela Agentes** (`tela_agentes` nasce só no admin — marcar *Agentes* no perfil `desenvolvedor` ou nas permissões extras de quem vai usar; sem ela o menu não aparece) e *Identidade no gateway de IA* para quem não segue `CVP`+dígitos · Admin › Agentes: conceder o agente **um a um** (só desenvolvedores) e escolher curadores · quem recebeu: **sair e entrar** · curador: validar as 5 sementes na Curadoria |

⚠️ **Correções feitas direto no container de produção** somem no deploy seguinte se
não forem portadas para o repositório. As de 22 e 23/09 (branch
`feat/agente-datastage-melhorias`) estão portadas até o commit `5526de5` (#427–#429).

---

## ✅ Conferência pós-deploy

```sql
-- quem tem a TELA (sem ela, o menu não aparece mesmo com o agente concedido)
SELECT perfil FROM dbo.etl_perfil_permissao WHERE recurso = 'tela_agentes';
-- migrations aplicadas
SELECT COUNT(*) FROM dbo.etl_agente_aprendizado WHERE origem = 'semente';  -- 5
SELECT config_value FROM dbo.etl_app_config WHERE config_key = 'agentes_titulo_redigido_em';  -- marca da 118
SELECT COUNT(*) FROM dbo.etl_agente_conversa WHERE titulo IS NOT NULL;  -- 0 logo após a 118
```

**Smoke automatizado:** `scripts/smoke_agentes.py` (itens pela API — catálogo, sonda,
stream com progresso chegando aos poucos, duração, histórico, régua de decisão,
curadoria) — ver o cabeçalho do script para as variáveis. Os itens que dependem de
tela, de dois usuários ou do servidor DataStage são impressos como roteiro manual no
fim (spec §7).

---

## ⚠️ Dúvidas ainda abertas e limites conhecidos

- **D-07** — formato real da saída do `dsjob` (e do parâmetro Encrypted nela): a redação
  é conservadora; colher uma amostra real antes de mexer em `redigir()`.
- **D-08** — não há data de modificação pelo `dsjob`: fatos de `dsjob` vencem por prazo.
- **D-09** — capacidade de sessões SSH do servidor: teto 10 por padrão, configurável.
- **D-19** — o que a pasta DSX de produção contém e quão atual está.
- **D-01 a D-03** — contrato de identidade do gateway: fica em configuração
  (`agentes_gateway_campo_usuario`) até ser validado; na troca do gateway, revalidar.
- O fluxo de filhos de sequence usa as 4 ferramentas; pergunta que ainda precisa
  resolver o projeto pode terminar em "limite de passos".
- Teto da fila do curador é global (100), não por usuário.

## 🧭 Próximos passos (backlog)

- ~~Tela de criação de agentes e prompt editável sem deploy~~ — **entregue** (#432–#438):
  `docs/release-notes/agentes-admin.md`.
- ~~Agentes que consultam banco~~ — **entregue** (#443–#445 e a C3): `docs/release-notes/agentes-banco.md`.
- Ler o que entra e sai das conversas para gerar funcionalidades (B-07, exige política).
