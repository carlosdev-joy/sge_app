# 🛠️ Agentes pela tela — prompt editável e criação de agentes

**Compatibilidade:** a mesma dos agentes (`docs/release-notes/agentes.md`) — gateway de IA com identidade por usuário, SSH ao DataStage para quem usa ferramentas de servidor
**Migrations:** **120** (versões do prompt), **121** (cadastro de agentes + `etl_agente_fato.agente`) — etapa 6c, responder **s**. Idempotentes
**Spec:** `docs/spec-agentes-admin.md` (Fase A: prompt editável · Fase B: criação de agentes)
**Manual:** `docs/MANUAL_USUARIO.md` §3.12 (usar), §4.11 (administrar), §4.6 (deploy), §5 (FAQ)
**PRs:** #433 (spec) · #432 A0 · #434 A1 · #435 A2 + BK-1 · #436 B1 · #437 B2 · #438 B3 · B4 (esta nota, manual, smoke)

---

## 📋 Resumo

Até aqui, ajustar uma frase do prompt do agente DataStage exigia editar código, copiar
para o container e reiniciar a API — e foi assim que o prompt passou a ser corrigido
direto em produção, com cada correção portada à mão para o repositório. Criar um agente
novo era uma entrega de desenvolvimento inteira.

Agora, na aba **Admin › Agentes**:

- o administrador **edita o prompt** (a parte do domínio) e a mudança vale **na
  pergunta seguinte**, sem deploy nem restart — com **versões**, histórico e restauração;
- cada versão mostra **de quando a quando valeu**, quanto tempo ficou em uso, quantas
  respostas deu e o tempo médio delas;
- o administrador **cria agentes** — **só de conversa** (sem acesso a sistemas) ou com
  **parte das ferramentas** do DataStage —, escolhe **quem usa** (manual, usuário a
  usuário, ou por perfil) e liga quando estiver pronto.

```
Admin › Agentes
┌ Agentes ─────────────────────────────────────────────────────── [+ Novo agente] ┐
│ Agente                 Origem  Acesso                 Ferramentas        Ligado │
│ Mapeamento DataStage   código  manual · desenvolvedor projeto, base, …   sim    │
│ Assistente de padrões  tela    por perfil · analista  só conversa        [● ]   │
└────────────────────────────────────────────────────────────────────────────────┘
┌ Prompt — Mapeamento DataStage ─────────── Em uso: versão 3 · CVP123 · 23/09 14:02 ┐
│ Instruções do domínio                                                            │
│ ┌──────────────────────────────────────────────────────────────────────────────┐ │
│ │ Você é o agente de mapeamento de processos DataStage do Orquestra. …         │ │
│ └──────────────────────────────────────────────────────────────────────────────┘ │
│ Motivo da mudança [ agente pedia o projeto mesmo com o prefixo claro ] [Salvar]  │
│ ▸ Parte fixa montada pelo Orquestra (só leitura)                                 │
│ ▾ Histórico de versões                                                           │
│   Versão  Vigente de        Até               Duração  Respostas  Tempo médio    │
│   v3      23/09/2026 14:02  agora             2 h      14         38,2 s         │
│   v2      22/09/2026 09:10  23/09/2026 14:02  1 d 4 h  51         41,0 s         │
│   Padrão  deploy            22/09/2026 09:10  —        20         44,7 s         │
└──────────────────────────────────────────────────────────────────────────────────┘
```

> **Impacto para a engenharia ETL:** ajuste de prompt vira uma edição com motivo, que
> vale na hora e pode ser desfeita em um clique — sem esperar deploy, sem editar o
> container de produção.
>
> **Impacto para a operação:** agentes só de conversa não tocam o servidor DataStage; os
> que tocam passam pelos mesmos tetos (sessões SSH, extrações ISX, tempo) do DataStage.
>
> **Impacto para a segurança:** o protocolo e as regras de segurança do prompt **não são
> editáveis**; agente que toca o servidor é **só por concessão manual**; o perfil
> `consulta` nunca recebe agente; texto de prompt com cara de credencial é recusado.

---

## 🚚 O que entra

| Fase | PR | O quê |
|---|---|---|
| **A0** | #432 | O prompt do DataStage passa a ser **montado em blocos**: contexto da conversa → **domínio** (editável) → protocolo de ferramentas → regras → propostas → aprendizados. Conteúdo igual ao de antes, só reorganizado |
| **A1** | #434 | **Versões** do domínio (migration 120), lidas **a cada pergunta** (sem cache), endpoints de admin, validações, rastreio `prompt_versao`/`prompt_hash` em cada resposta |
| **A2** | #435 | Editor, parte fixa e histórico/restauração na aba; **BK-1**: vigência, duração, respostas e tempo médio por versão |
| **B1** | #436 | **Cadastro** de agentes (migration 121), catálogo que junta os do código e os da tela, acesso manual ou por perfil, uma regra de acesso só |
| **B2** | #437 | **Execução** dos agentes da tela: rotas por agente, só conversa, subconjunto de ferramentas, conversa/propostas/curadoria **por agente** |
| **B3** | #438 | A **tela** do cadastro; `/agentes` pelas rotas do agente; grants dos agentes da tela no Admin › Usuários |

---

## ⚙️ Como funciona

**Prompt em blocos (A0–A2).**

| Bloco | Origem | Editável |
|---|---|---|
| 1. Contexto da conversa (projeto) | código | não |
| 2. **Domínio** — quem é o agente, ordem de uso, armadilhas, como responder | versão ativa do banco; sem versão, o padrão do código | **sim** |
| 3. Protocolo de ferramentas (bloco JSON, ferramentas do agente, comandos do `dsjob` tirados da allowlist) | código | não |
| 4. Regras que valem sempre | código | não |
| 5. Propostas e aprendizados | código | não |
| 6. Aprendizados validados | curadoria | não |

- **Versões só acrescentam.** Gravar cria a versão seguinte; restaurar grava o texto
  antigo como versão **nova**. Nada é apagado nem sobrescrito. Sem versão gravada vale a
  **versão 0** (padrão do código), que acompanha as PRs.
- **Sem cache.** A versão ativa é lida a cada pergunta (a API roda com 2 processos): o que
  o admin grava vale na pergunta seguinte, nos dois. Se a leitura falhar, o DataStage usa
  o padrão do código e o chat não cai.
- **Dois admins ao mesmo tempo.** A gravação carrega a versão em que o rascunho
  **começou**; se outro admin gravou antes, a tela avisa e o texto digitado não se perde.
- **Vigência (BK-1).** Início = quando a versão foi gravada; fim = quando a seguinte foi
  gravada (derivado — nada é atualizado). Respostas e tempo médio contam as conversas
  ainda guardadas (a limpeza diária apaga as de mais de 30 dias).

**Agentes criados pela tela (B1–B3).**

- **Só conversa** (nenhuma ferramenta): uma chamada à IA com o domínio e regras
  genéricas; sem projeto, sem grafo, sem propostas, sem curadoria. Um bloco de
  ferramenta que o modelo mande é descartado.
- **Com ferramentas**: um subconjunto de `resolver_projeto`, `base`, `dsx_consulta`,
  `dsjob`, `isx_extrair` — ferramenta nova continua **só por desenvolvimento**. Pedir uma
  ferramenta fora do conjunto é recusado antes de tocar o servidor (aparece como
  *(indisponível)*). Tudo o mais — projeto, tetos, guarda, propostas, aprendizados — igual
  ao DataStage, **separado por agente**.
- **Acesso.** Nos dois modos o usuário precisa ser de um dos **perfis escolhidos** e ter a
  **tela Agentes**. *Manual*: além disso, o admin libera usuário a usuário. *Por perfil*:
  basta isso. **Por perfil não vale** com ferramenta que toca o servidor (`dsjob`,
  `isx_extrair`, `dsx_consulta`); o perfil `consulta` nunca.
- **Curadoria** só em agente com ferramentas, com grant próprio (`agente_<id>_curador`).
- O agente nasce **desligado**; o interruptor geral (`agentes_enabled`) derruba todos.
- Não existe exclusão: desligar mantém conversas, propostas e aprendizados, e o id nunca
  é reaproveitado.

---

## 🔒 Como a segurança funciona

- **Protocolo fora do alcance.** O admin edita só o domínio; protocolo, regras e formato
  de propostas são montados pelo código **depois** dele. O texto não pode imitar o
  protocolo (`"ferramenta":`, `<aprendizados`… → recusado).
- **Credencial no prompt.** Texto com **valor** de credencial (`senha=…`,
  `DB_PASSWORD=…`, `"senha": "…"`, chaves `sk-…`, `Bearer …`, blocos de chave) é recusado;
  referências de ParameterSet (`#PS_X.Y#`, `$PS_X.Y`) e texto normal ("nunca peça a
  senha") passam. Regra linear (sem risco de travar a API com texto grande).
- **Acesso numa régua só** (`motivo_sem_acesso`), a mesma no catálogo, nas rotas e no
  DataStage. Agente da tela exige a **tela Agentes**. Uma linha editada à mão no banco
  **não amplia nada**: ferramenta fora da allowlist e o perfil `consulta` são descartados,
  acesso por perfil com ferramenta de servidor vira manual, id inválido ou reservado é
  ignorado.
- **Isolamento por agente.** Conversa, proposta e aprendizado de outro agente dão 404; o
  curador de um agente não cura outro.
- **Ids reservados.** `datastage`, as palavras das rotas e `curador`/`*_curador` — para um
  grant nunca dar dois papéis.
- **Rastreio.** Cada resposta grava a versão e o hash do prompt usado; a interpretação
  aprovada guarda **qual agente** a propôs; a extração ISX de um agente da tela é
  registrada como `agente:<id>`.

---

## 🚀 Deploy

Sobe junto com o que ainda não foi para produção dos agentes (**#429 a #438**).

| Passo | O quê |
|---|---|
| Antes | Conferir se há commits novos na branch `feat/agente-datastage-melhorias` (correções feitas direto no container) — **portar para o repositório antes** do deploy, ou somem |
| 6c | Migrations **120** e **121** → **s** |
| `api/` | **sim** |
| `dags/` | não |
| `dist/` | **sim** |
| `.env` | nada novo |
| `config/` | **n** |
| Depois | Nada obrigatório: o DataStage segue com o prompt padrão (versão 0) até alguém gravar uma versão. Criar agentes é opcional |

---

## ✅ Conferência pós-deploy

```sql
-- as duas migrations
SELECT OBJECT_ID('dbo.etl_agente_prompt'), OBJECT_ID('dbo.etl_agente'),
       COL_LENGTH('dbo.etl_agente_fato', 'agente');          -- três valores não nulos
-- cada resposta registra a versão do prompt (0 = padrão do código) — a partir da 1ª
-- pergunta DEPOIS do deploy; as mensagens antigas não têm o campo
SELECT TOP 5 criada_em, artefatos_json FROM dbo.etl_agente_mensagem
 WHERE papel = 'assistant' ORDER BY id DESC;
-- versões gravadas e agentes criados
SELECT agente_id, versao, criado_por, criado_em, motivo FROM dbo.etl_agente_prompt ORDER BY agente_id, versao;
SELECT agente_id, acesso, perfis_json, ferramentas_json, ativo FROM dbo.etl_agente;
```

**Validar a A0 com as perguntas reais** (o DEV não tem o gateway nem o DataStage). Logo
depois do deploy, no agente DataStage: (1) filhos de uma sequence; (2) colunas de um job
PARALLEL; (3) status da última execução; (4) um job `SsdPrs_*` sem informar o projeto. Se
alguma resposta piorar:
- **Na hora:** grave uma versão do domínio (Admin › Agentes › Prompt) que reforce a
  instrução que piorou — por exemplo, repetindo perto do `dsjob` a frase dos comandos, que
  a A0 levou para o bloco de protocolo. Vale na próxima pergunta.
- **Definitivo:** uma PR que ajuste a montagem dos blocos (`partes_fixas`/`_prompt_sistema`).
- ⚠️ **Não reverta a #432:** as PRs #434–#438 usam o que ela criou (`PROMPT_DOMINIO_PADRAO`,
  os blocos); o revert não aplica e, forçado, deixa **todo** agente — inclusive o
  DataStage — respondendo 503 `agente_prompt_indisponivel`.

**Smoke automatizado:** `scripts/smoke_agentes.py` — com um usuário **admin** roda também
os itens do prompt e do cadastro (só leitura e recusas; confere também que a tabela da
121 existe); com `SMOKE_AGENTE=<id>` conversa com um agente criado pela tela. O roteiro
manual no fim do script lista o que depende da tela — atenção ao item *o*: agente criado
não se exclui.

---

## ⚠️ Dúvidas ainda abertas e limites conhecidos

- **Grant que volta a valer.** Quando o admin tira um perfil de um agente, o grant de um
  usuário desse perfil continua gravado (sem dar acesso). Se o perfil voltar a ser
  elegível, **o acesso volta sozinho**, e o modal de permissões mostra o checkbox marcado
  sem indicar que hoje ele não vale. Opções em aberto: manter, sinalizar "sem efeito" ou
  apagar o grant quando o perfil sai do agente.
- **Validação da A0** só em produção (acima).
- **Cadastro sem controle de versão.** Dois admins editando o **mesmo agente** ao mesmo
  tempo: vale o último. (O prompt tem controle de versão; o cadastro não.)
- **Respostas por versão** contam só as conversas ainda guardadas (a `etl_log_cleanup`
  apaga as de mais de 30 dias; se ela não rodar, entram também as mais antigas).
- **Agentes não se excluem** e o id não volta: para testar, use um id de teste e desligue
  ao fim.
- A **versão 0** (padrão do código) não tem data de início: vale desde o deploy.

## 🧭 Próximos passos (backlog)

- Decisão sobre o grant que volta a valer (acima).
- Comparar versões do prompt lado a lado (diff), se o histórico pedir.
- Ler o que entra e sai das conversas para gerar funcionalidades (B-07, exige política).
