# Agente Terminal — F5: tela real e integração

Última fase da spec `docs/spec-agente-terminal.md`. **O Terminal deixa de ser travado** (`disponivel: True`), mas **nada muda para ninguém até o administrador ligar** o interruptor do agente (`agente_terminal_enabled`, nasce desligado) e conceder `agente_terminal` usuário a usuário. A escrita tem interruptor e permissão próprios, também desligados por padrão.

## O que muda
- **Tela real** em `/agentes` (agente Terminal): o chat em formato de terminal (F1) ligado à API — leitura com o comando e a saída (redigida), card de confirmação para o que altera o servidor (o comando inteiro, **onde** roda, a alegação do assistente marcada como **não verificada**, prazo com aviso aos 30 s, Recusar acima no celular), consultas ao **DataStage** (`dsjob`) e aos **bancos** como notas com o SQL, selos de estado com ícone (executado/falhou/bloqueado/recusado/expirado), "Parar" durante uma resposta longa. Reaproveita a sonda do gateway, o descarte de resposta atrasada e o fallback do stream do chat dos agentes. Depois de qualquer recusa da API, o card é reidratado pelo `GET /agentes/terminal/comandos/{id}`.
- **DataStage e bancos no Terminal** (decisão do usuário, 05/11/2026): o Terminal recebe `resolver_projeto` + `dsjob` (a ferramenta de leitura já endurecida) e as de banco (só-SELECT garantido pelo plano). Os bancos são escolhidos pelo admin em **Admin › Agentes › Terminal › Bancos** (mesmo seletor e mesma conferência no servidor dos agentes da tela; `PUT /agentes/admin/terminal/bancos`); sem banco marcado, as ferramentas de banco nem entram no prompt.
- **Auditoria no Admin** (aba Auditoria): todos os comandos, filtros por matrícula/estado/classe/período, paginação, motivo e resumo da saída.
- **Retenção** (decisão do usuário: 180 dias, purga automática): `agente_terminal_retencao_dias` (30–3650). A purga apaga só linhas em estado final, ao consultar a auditoria e no máximo uma vez por hora nas confirmações.
- `GET /agentes/terminal/servidores` (id/rótulo/configurado, nunca host/usuário). O resultado de cada leitura vai no artefato da conversa (`comando_executado`, saída redigida e cortada em 4000 caracteres).
- Manual do usuário: seções 3.13 (Terminal) e 4.12 (Admin do Terminal). A prévia `?simulado=1` da F1 foi removida.

## Endurecimento antes da liberação (auditoria da superfície inteira + QA)
- **Busca recursiva** (`grep -r`) passou a excluir EXATAMENTE o que a denylist proíbe ler direto: fonte única de nomes, sem diferenciar maiúsculas (o `--exclude` do GNU grep diferencia, mesmo com `-i`: `Secrets.json`, `APP.ENV`, `.SSH/` vazavam) e com os nomes que faltavam (`secret.txt`, `credential.json`, `client_secret.json`, `.bash_history`, `authorized_keys`…). Teste de equivalência + execução real do GNU grep provam.
- **O Terminal não grava na base de conhecimento**: sem curadoria, não grava aprendizados nem interpretações (`propostas`) — antes, com o `dsjob`, um usuário só do Terminal conseguia gravar "interpretação aprovada" vista pelo agente DataStage.
- Decisão em voo depois de "Nova conversa" não injeta mais o card na conversa nova; o card que está **executando** não vira "expirado · nada foi executado" quando o prazo passa durante a execução; o mesmo comando em execução bloqueia uma nova proposta (sem execução dupla).
- Retenção automática de verdade: a purga roda também ao conversar com o Terminal e antes da checagem de escrita (antes dependia de abrir a auditoria).
- A prévia do prompt e a lista do Admin mostram os bancos reais do Terminal; `PUT` de bancos sem a chave `bancos` preserva os pares.
- **Risco aceito por desenho, agora declarado** (manual §3.13): a denylist é textual — comando ofuscado (curinga, `$( … )`, aspas no meio do verbo) não é reconhecido e cai em escrita **confirmável**; quem confirma responde pelo texto do card, e a conta SSH é o teto real.
- Limite conhecido: "Parar" (ou Nova conversa) enquanto o agente propõe deixa a proposta pendente no servidor até expirar (2 min); repropor o mesmo comando nesse intervalo é recusado como "já aguardando".

## Deploy
- Migration **201** (versão), idempotente, na etapa 6c (as anteriores do Terminal: 197 auditoria, 198–200 versões).
- Atualizar API e **`dist/`**. Sem `dags/`, sem dependências. Quem já tem sessão precisa de novo login para ver o agente.
- Variáveis (desde a F3): `AF_SSH_*`, `*_SSH_KNOWN_HOSTS` (obrigatório), `TERMINAL_SSH_AUTO_ADD=1` **só no DEV**, `TERMINAL_RAIZES_<ID>`, `TERMINAL_CONTAINERS_<ID>`.
- **Numeração:** a Malha F16 (`/root/orquestra-eoc-f16-autoria`, 197–200 sem commit) colide agora com **197–201** do Terminal e precisa renumerar para **202+**.

## Pendências (fora desta entrega)
- **DEV**: não publicado (sem autorização). O smoke da §8 da spec depende de `TERMINAL_SSH_AUTO_ADD=1` e de um servidor `AF_SSH_*` no `.env.dev`.
- **Servidor do Orquestra/Airflow**: host e conta SSH de menor privilégio ainda não definidos.
- Histórico/retomada de conversas do Terminal (o chat recomeça a cada visita; os comandos ficam na auditoria).
