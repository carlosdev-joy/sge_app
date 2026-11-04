# Spec: Agente "Terminal" (chat estilo terminal) — Orquestra
Data: 2026-11-04 · Status: rascunho

Base: `origin/develop` (5739862a). Reaproveita `docs/spec-agentes-datastage.md`, `docs/spec-agentes-admin.md` e `docs/spec-agentes-ferramenta-banco.md`.

## 1. Visão
Hoje os agentes de `/agentes` só enxergam o que a spec de cada um libera (DataStage via `dsjob`/ISX/DSX, banco só-SELECT). Quem opera o Orquestra ainda precisa de acesso ao servidor para perguntas livres ("por que a DAG X falhou?", "o que tem no log Y?", "qual o estado do job Z?"). Esta feature adiciona um agente **Terminal**: chat com aparência de terminal em que o usuário logado digita livremente e o Claude, pelo provedor `ia_*` com a identidade do usuário, consulta o servidor do Orquestra/Airflow, o DataStage e os bancos cadastrados. **Leitura é livre; qualquer escrita só roda depois de "Confirmar" explícito do usuário, comando a comando, com auditoria completa.**

Decisões do usuário (04/11/2026): leitura livre + escrita com confirmação · herda o RBAC do Orquestra · novo agente dentro de `/agentes` · provedor `ia_*` atual + log completo.

## 2. Escopo
**IN**
- Agente `terminal` no catálogo (`api/services/agentes.py`), com recurso RBAC próprio e interruptor `agente_terminal_enabled`.
- Interface de terminal dentro de `ui-react/src/pages/Agentes.tsx` (componentes em `components/agentes/`): entrada livre, saída monoespaçada, histórico, cards de comando com SQL/linha de comando sempre visíveis.
- Ferramentas novas: `servidor_exec` (shell no servidor Orquestra/Airflow via SSH, credencial de `ssh_arquivos.servidores_disponiveis`), reuso de `dsjob`, `banco_estrutura`, `banco_consulta`, `base`.
- Classificador determinístico de comando: **leitura** (allowlist, roda direto) × **escrita** (qualquer outra coisa, exige confirmação) × **proibido** (nunca roda, nem com confirmação).
- Fluxo de confirmação: proposta → card Confirmar/Recusar → execução com token de uso único.
- Auditoria completa em tabela própria e tela de consulta para admin.
- Redação de segredos na entrada e saída (`agentes_ferramentas.redigir`).

**OUT (explícito)**
- Shell interativo real (PTY, `vim`, `top`, `ssh` aninhado, `sudo` interativo). É chat que executa comandos pontuais, não emulador de terminal.
- Escrita sem confirmação, "modo automático", "confirmar tudo", confirmação em lote.
- Escrita em banco (continua só-SELECT garantido pelo plano, como na spec de ferramenta de banco).
- Execução em produção/Caixa nesta entrega: nasce validada no DEV; produção só com autorização própria (air-gapped, "dev testa, produção manda").
- Concessão por perfil: a escrita é sempre usuário a usuário.
- Mudar o provedor/modelo de IA; mexer em `automatico/`; qualquer nome "caixa" no código novo.
- Upload/download de arquivos pelo chat; agendamento de comandos.

## 3. Telas (consultar `impeccable`, modo Operate)
Uma única tela: aba/agente **Terminal** em `/agentes`. Sem reordenar o que já existe na página.

- **Objetivo:** perguntar em linguagem livre ou digitar um comando, ver o que foi executado e o resultado, com controle claro do que muda algo.
- **Layout:** painel único com fundo de terminal **sempre escuro** (exceção documentada em `docs/ui-temas-cores.md` §4, igual ao visualizador de log); moldura e cabeçalho com tokens `bg-panel/border-edge/text-ink`. Coluna única, entrada fixa embaixo, histórico rolável acima.
- **Cabeçalho:** servidor alvo (seletor, só os que o usuário pode), indicador "Somente leitura" (verde) ou "Escrita habilitada" (âmbar, só quem tem o recurso), botão "Nova conversa".
- **Mensagem do usuário:** linha com prompt `›`. **Resposta do Claude:** texto corrido. **Comando executado:** bloco com a linha de comando literal, selo `leitura`, duração, saída em monoespaçado com teto de linhas e "Mostrar tudo", botão Copiar.
- **Card de confirmação (escrita):** borda âmbar, texto "Este comando altera o servidor", comando literal, servidor, motivo dado pelo Claude, botões **Confirmar e executar** / **Recusar**; expira em 2 min; depois de usado vira bloco "executado por <usuário> às hh:mm" ou "recusado". Teclado: foco no card, Enter não confirma sozinho (exige foco no botão).
- **Estados:** vazio (3 exemplos clicáveis de leitura), carregando (indicador por ferramenta, reaproveita o progresso SSE de `spec-agentes-feedback-progresso.md`), erro (mensagem nomeada, nunca stack), sem permissão (mensagem `motivo_sem_acesso`), servidor indisponível, saída truncada, token expirado.
- **Responsivo:** em 375 px o card de confirmação ocupa a largura toda e os botões empilham; saída com rolagem horizontal, sem estourar a página.
- **Acessibilidade:** `role="log"` + `aria-live="polite"` no histórico, cores nunca como único sinal (texto "leitura"/"escrita"), contraste AA no tema escuro fixo, foco visível.
- **Copy:** pt-BR, direta ("Executei `tail -n 100 …`", "Preciso alterar X. Confirma?").
- **Admin:** em `/admin` (aba Agentes) lista de auditoria com filtro por usuário/período/estado e a lista de comandos de leitura permitidos (somente leitura, vem do código).

## 4. Arquitetura proposta
- **Front:** `pages/Agentes.tsx` ganha o agente `terminal` (renderiza `components/agentes/TerminalChat.tsx`, `ComandoBloco.tsx`, `ConfirmarComando.tsx`); lógica pura em `src/lib/terminalComando.ts` (formatar saída, truncar, estados do card) testada na bancada `tests/js/`.
- **Back:** `api/services/agentes_terminal.py` novo: `classificar(comando) -> leitura|escrita|proibido`, `executar(...)`, tokens de confirmação, redação. Registro da ferramenta `servidor_exec` em `agentes.py` (`FERRAMENTAS_SERVIDOR`, só concessão manual). Rotas novas em `api/routers/agentes.py` (já registrado em `main.py`): `POST /agentes/terminal/confirmar` e `POST /agentes/terminal/recusar`; a conversa usa o `POST` de conversa existente (SSE).
- **Servidor "Orquestra/Airflow":** SSH via paramiko (já dependência) pelo mesmo mecanismo de `ssh_arquivos.credencial(servidor)`; nada de montar socket do Docker na API. Servidores exibidos = `servidores_disponiveis()`.
- **Classificador (o ponto crítico):** a IA **não decide** se é leitura. O backend parseia o comando (`shlex`) e só chama de leitura se: um único comando, sem `; & | > < $( \` ` e sem `&&`/`||` (pipe só para `grep|head|tail|wc|sort|uniq|cut` de allowlist), binário em allowlist (`ls cat head tail grep wc df du ps docker ps/logs/inspect/stats airflow dags list/list-runs/state/…`, `dsjob` de leitura, `stat`, `find` sem `-exec/-delete`, `journalctl`, `uptime`, `free`), argumentos sem caminhos fora das raízes permitidas (`raiz_proibida`, `normalizar_diretorio`), `cat`/`tail` nunca em `.env*`, chaves, `/etc/shadow`, `~/.ssh`. Qualquer coisa fora da allowlist = **escrita** (confirmável). Lista **proibida** (nunca roda): `rm -rf /`, `mkfs`, `dd` em dispositivo, `shutdown/reboot`, `chmod -R /`, `curl|sh`, leitura de segredos, `docker rm/stop` do próprio `orquestra-api`/banco, `pkill`/`killall` por nome (regra do ambiente: matar por PID).
- **Confirmação:** o Claude propõe `{comando, servidor, motivo}`; backend grava `etl_agente_terminal_cmd` (estado `proposto`), devolve `cmd_id` + `hash`. Confirmar exige: mesmo usuário da proposta, recurso de escrita, `hash` igual ao do comando gravado (nunca o texto vindo do front), não expirado (2 min), estado `proposto` (uso único, `UPDATE … WHERE estado='proposto'` atômico). O front não pode alterar o comando.
- **RBAC:** `agente_terminal` (leitura; elegível a `desenvolvedor`, concessão manual por usuário, admin sempre) e `agente_terminal_escrita` (só admin concede, usuário a usuário, nunca por perfil; `require_agente` já ignora recurso vindo do perfil). Cada ferramenta ainda checa o que o usuário já tem (conexões de banco do agente, `acao_editar` etc.). `consulta` nunca recebe.
- **Auditoria:** toda proposta, confirmação, recusa, execução e bloqueio vira linha com usuário, matrícula, servidor, comando (já redigido), classe, estado, código de saída, duração, bytes, `conversa_id`, IP. Saída armazenada só resumida/redigida (teto 8 KB).
- **IA:** provedor `ia_*` (`ia_provedor.py`) com `identidade_gateway()`; prompt do agente versionado como os demais (`agentes_prompt.py`). Sem chave/segredo no prompt.
- **Contrato do comando para o front (fixado na F1, `lib/terminalComando.ts`):** estados `proposto → executando → executado|falhou`, `proposto → recusado|expirado`, `bloqueado` (classe proibido, nasce assim); `falhou` vale também para leitura. Datas sempre ISO-8601 em UTC com sufixo `Z`; o front formata no fuso local. Para não depender do relógio do navegador, a resposta traz `segundos_restantes` (o front soma ao seu relógio) além de `expira_em`. `cmd_id` é UUID gerado no servidor. O servidor é a única autoridade: a UI só esconde botões, e a confirmação repete as checagens (usuário, recurso, hash, prazo, estado). Limite de saída do servidor: 64 KB / 2000 linhas (o front mostra 40 linhas + "Mostrar tudo").
- **Alternativas descartadas:** tela `/terminal` independente (duplica RBAC/auditoria); PTY/xterm.js (superfície enorme, fora do pedido); IA classificando leitura×escrita (injeção de prompt contorna); `docker exec` pela API (concede o host).

## 5. Modelo de dados
Migration de dados da F2 (`NNN_agente_terminal.sql`, **próximo número livre no momento do merge** — conferir `origin/develop` e as worktrees `/root/orquestra-*`; as 197–200 estavam reservadas pela Malha F16 em andamento; a numeração não admite lacuna), idempotente, aplicada na etapa 6c do `deploy.sh`:
- `etl_agente_terminal_cmd`: `cmd_id UNIQUEIDENTIFIER PK`, `conversa_id`, `matricula VARCHAR(20)`, `servidor VARCHAR(60)`, `comando NVARCHAR(2000)` (contar UTF-16 — `cortar_utf16`), `hash CHAR(64)`, `classe VARCHAR(10)` (leitura/escrita/proibido), `estado VARCHAR(12)` (proposto/confirmado/recusado/expirado/executado/falhou/bloqueado), `motivo NVARCHAR(500)`, `codigo_saida INT NULL`, `duracao_ms INT NULL`, `saida_resumo NVARCHAR(4000) NULL`, `ip VARCHAR(45)`, `criado_em`, `decidido_em`, `executado_em`. Índices por `(matricula, criado_em)` e `(conversa_id)`.
- Recurso `agente_terminal` e `agente_terminal_escrita`: entram em `RBAC_RECURSOS` **e** na lista espelhada do front (DOIS lugares; exige relogin). Chaves de config: `agente_terminal_enabled` (padrão desligado), `agente_terminal_escrita_enabled` (padrão desligado — kill switch).
- Migration de versão a partir da F2 (nome sem a palavra "enviar"), segundo número +1; a F1 (só front simulado, fora do catálogo) não registra versão.
- API e UI degradam se a tabela não existir (503 nomeando a migration).

## 6. Fases (front primeiro, com `impeccable` como portão)
### F1 — Terminal no front com dados simulados
- Entregável: `TerminalChat`, `ComandoBloco`, `ConfirmarComando` e `lib/terminalComando.ts` com mock tipado do contrato (SSE + cards) atrás do `apiFetch`, ligado ao agente `terminal` só com flag de mock.
- Aceite: todos os estados da §3 renderizam; tema claro e escuro; 375/768/1280 px sem rolagem horizontal da página; teclado e leitor de tela ok; confirmação mock não executa nada.
- Validação: `tsc -b`, eslint (baseline, zero novo), `npm run build` (`dist/` por último), pytest comparado com a base, `impeccable` critique + audit + polish, Chrome nos 2 temas. **Sem aprovação do `impeccable` o backend não começa.**
- Revisão adversarial (`qa-adversarial`) antes da PR. PR: `feat: terminal do agente — interface (dados simulados)`.

### F2 — Fundação: catálogo, RBAC, auditoria
- Entregável: migration de dados + migration de versão (a F1 não registrou versão; **próximos números livres no momento do merge**, sequenciais sem lacuna); agente `terminal` no catálogo; recursos RBAC; interruptores; modelo de dados; endpoint de auditoria admin (leitura).
- Aceite: usuário sem recurso recebe `motivo_sem_acesso`; perfil `consulta` nunca elegível; `agente_terminal_escrita` não é concedido por perfil (teste espelhando o de `agente_datastage`); migration roda 2×.
- Validação: pytest completo (8 falhas pré-existentes, zero novas), `tests/test_migrations_idempotentes.py`, QA adversarial. PR: `feat: agente terminal — fundação e auditoria`.

### F3 — Leitura no servidor
- Entregável: `agentes_terminal.classificar`, `servidor_exec` (somente classe leitura), redação, truncamento, timeout e semáforo SSH, integração ao loop `conversar()` e ao SSE.
- Aceite: allowlist executa; qualquer metacaractere, binário fora da lista, `.env`, caminho fora da raiz ou `find -exec` **não** roda como leitura; proibido registra `bloqueado`; saída sem segredos; limite de tempo/tamanho respeitado.
- Validação: bateria de testes de bypass (injeção, quoting, unicode, `$IFS`, here-doc, symlink, `--` e opções longas), pytest, `auditor-seguranca`, QA adversarial (teto de 2 rodadas). PR: `feat: agente terminal — leitura no servidor`.

### F4 — Escrita com confirmação
- Entregável: proposta → confirmação/recusa → execução com token de uso único e hash; expiração; kill switch; bloco "executado por".
- Aceite: confirmar com outro usuário, hash alterado, token expirado ou reutilizado falha; sem `agente_terminal_escrita` o botão nem aparece e o endpoint recusa (403); prompt injection vinda da saída de um comando não gera execução sem confirmação; proibido nunca executa.
- Validação: testes de concorrência (duplo clique = 1 execução), `auditor-seguranca`, pytest, QA adversarial. PR: `feat: agente terminal — escrita com confirmação`.

### F5 — Integração e polimento
- Entregável: trocar mock pelo real, ferramentas `dsjob`/banco no mesmo chat, tela de auditoria no Admin, prompt versionado, release note e `docs/MANUAL_USUARIO.md`.
- Aceite: smoke da §8 passa no DEV; sem regressão nos agentes existentes.
- Validação: tudo acima + `/simplify`, `dist/` recompilada por último. PR: `feat: agente terminal — integração e auditoria no Admin`.

## 7. Riscos e mitigações
| # | Risco | Impacto | Mitigação |
|---|-------|---------|-----------|
| 1 | Injeção de prompt (texto de log/arquivo manda o Claude propor algo destrutivo) | Execução indevida | Classificador determinístico no backend; escrita sempre confirmada; saída tratada como dado, delimitada no prompt; proibido nunca roda |
| 2 | Bypass da allowlist (`;`, `$()`, `find -exec`, `cat` de `.env`, symlink) | Vazamento de segredo ou escrita "como leitura" | Parse com `shlex`, rejeição por padrão, bateria de bypass na F3, `auditor-seguranca`, raízes e arquivos sensíveis bloqueados |
| 3 | Segredos na saída (envs, senhas em logs) vão ao provedor de IA e ao log | Vazamento | `redigir()` na entrada e saída antes de IA/auditoria; `saida_resumo` truncada; nunca ler `.env*`/chaves |
| 4 | Confirmação burlada (front altera comando, replay, duplo clique) | Executar comando diferente do aprovado | Comando e hash gravados no servidor; `UPDATE … WHERE estado='proposto'` atômico; mesmo usuário; expiração 2 min |
| 5 | Comando que derruba o próprio Orquestra/banco | Indisponibilidade | Lista proibida inclui parar/remover `orquestra-api`, banco, worker; kill switch `agente_terminal_escrita_enabled`; piloto só no DEV |
| 6 | Credencial SSH com poder maior que o desejado | Escalada | Usuário de serviço de menor privilégio no servidor alvo; documentar o usuário necessário; sem `sudo` no allowlist |
| 7 | Carga/lentidão (comandos longos, saída enorme) | Trava a API | Timeout por comando, teto de bytes, semáforo SSH, orçamento da rodada (`ORCAMENTO_AGENTE_S`) |
| 8 | `docker` no host exposto pela leitura (`docker inspect` mostra env com segredos) | Vazamento | `docker inspect` fora da allowlist ou com redação de `Env`; testado na F3 |

## 8. Smoke pós-deploy (DEV)
a) Admin habilita `agente_terminal_enabled`, concede `agente_terminal` a um usuário `desenvolvedor`; relogin; o agente aparece no catálogo.
b) Usuário sem o recurso não vê o agente e a API devolve 403.
c) "Mostre as últimas 50 linhas do log da DAG X": bloco com `tail` literal, selo leitura, saída sem segredos.
d) "Liste os jobs do projeto P no DataStage": usa `dsjob`, resultado coerente com `/jobs`.
e) "Quantas execuções falharam hoje?": usa `banco_consulta`, SQL visível.
f) Pedir `cat .env`: recusado/bloqueado, linha `bloqueado` na auditoria.
g) Pedir algo que altera (ex.: reiniciar uma DAG): aparece card; **Recusar** não executa; nova proposta, **Confirmar** executa uma vez e mostra "executado por".
h) Duplo clique em Confirmar: uma única execução. Esperar 2 min: card expira.
i) Usuário sem `agente_terminal_escrita` não vê botão de confirmar.
j) Admin vê todas as linhas na auditoria com usuário, comando redigido, estado e duração.
k) Desligar `agente_terminal_escrita_enabled`: propostas de escrita viram aviso, nada executa.
l) Tema claro/escuro e celular (375 px) conferidos.

## 9. Pendências e decisões em aberto
1. Qual **servidor/usuário SSH** representa "servidor do Orquestra/Airflow" no DEV (host, usuário de serviço, privilégios)? Hoje só há `DS_SSH_*` (DataStage).
2. Lista inicial exata de comandos de leitura (proponho a da §4; ajustar no QA da F3).
3. Retenção da auditoria (proponho 180 dias) e se `saida_resumo` deve ser guardada ou só metadados.
4. Quem concede `agente_terminal_escrita` (proponho apenas admin).
5. Produção/Caixa: fora desta spec; exige decisão de segurança própria.
