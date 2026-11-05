# Agente Terminal — F3: leitura no servidor

Terceira fase da spec `docs/spec-agente-terminal.md`. **O agente continua travado como indisponível** (`disponivel: False`) até a F5: nenhum usuário consegue usá-lo ainda. Esta fase entrega o motor de leitura, já auditado e testado contra um SSH real.

## O que muda
- Ferramenta `servidor_exec`: executa UM comando de **leitura** no servidor pedido e devolve a saída.
- **Classificador determinístico** (`services/agentes_terminal_classe.py`): `leitura` / `escrita` / `proibido`. A IA não decide. Só roda o que está numa lista de comandos **e** passa nas regras de argumento (nada de `tail -f`, `sort -o`, `find -exec`, `docker inspect`…). O shell remoto recebe os **tokens classificados, re-citados** — nunca a string crua. Sem pipe, `;`, `&&`, `>`, `$`, crase; o filtro da saída (`filtrar`/`primeiras`/`ultimas`) é feito em Python.
- **Escrita não roda nesta fase** (nem é registrada): a confirmação é a F4. **Proibido** (segredos, `sudo`, `rm -rf /`, desligar, `env`…) nunca roda e fica registrado como `bloqueado`.
- **Sem auditoria, sem execução**: o comando é registrado antes de rodar; se o registro falhar, não executa. Linhas que a API não chegou a fechar viram `falhou` ("interrompido") após 5 min.
- **Segredos**: caminhos sensíveis (`.env*`, chaves, `*.cfg`, `*.conf`, `docker-compose*`, `.git/config`, `/var/log/auth.log`…) nunca são lidos diretamente; na busca recursiva (`grep -r`) os mesmos nomes são excluídos (a partir da F5: fonte única, sem diferenciar maiúsculas, com teste de equivalência). A denylist é por NOME — o conteúdo de arquivos com outros nomes depende da conta SSH e da redação da saída. A saída passa por redação (campos, formas de linha de comando, JWT, chaves AWS/GitHub/Slack, chave privada, valor na linha seguinte) **antes** de qualquer corte. O `comando` no artefato da conversa também é redigido.
- **Executor SSH** (`services/agentes_terminal_ssh.py`): registro **próprio** de servidores (não aparece nos Utilitários), limite de tempo (30 s) e de bytes (64 KB), stdin fechado, semáforo de sessões, e `timeout -k 2` no servidor para o processo morrer de verdade (fechar o canal sem pty não o mata).
- Nenhum outro agente consegue usar a ferramenta (gate em `conversar` + checagem no despacho).

## Variáveis de ambiente (novas — repassadas pelo `docker-compose.yaml`)
| Variável | Para quê |
|---|---|
| `AF_SSH_HOST/PORT/USER/PASSWORD/KEY_FILE` | Servidor do Orquestra/Airflow. Vazio = "não configurado". O `datastage` reaproveita as `DS_SSH_*`. |
| `AF_SSH_KNOWN_HOSTS` (ou `DS_SSH_KNOWN_HOSTS`) | **Obrigatório**: sem known_hosts a conexão falha (a senha não segue para host impostor). |
| `TERMINAL_SSH_AUTO_ADD=1` | **Só DEV**: aceita qualquer host key (o `sshd-amostra` não tem known_hosts). Nunca em produção. |
| `TERMINAL_RAIZES_<ID>` | Pastas liberadas para leitura (vírgula). Vazio = `/opt,/var/log,/srv,/data` (sem `/tmp`). |
| `TERMINAL_CONTAINERS_<ID>` | Containers liberados para `docker logs/stats`. Vazio = qualquer container do host. |

## Riscos que dependem de configuração (leia antes de ligar a F5)
- **A conta SSH é o teto real.** O classificador só restringe; o que é lido é o que a **conta de serviço** enxerga, e ela é **compartilhada**: um desenvolvedor lê o que a conta lê, mesmo sem ter esse acesso. Use conta de **menor privilégio**, **sem o grupo `docker`** (equivale a root) e restrinja `TERMINAL_RAIZES_*` a pastas de aplicação e `TERMINAL_CONTAINERS_*` aos containers necessários. A denylist de nomes de arquivo é só conforto.
- **Servidor sem `timeout` (ex.: AIX):** o comando roda sem o limite remoto; só o fechamento do canal vale (um `grep`/`find` pesado pode seguir órfão no servidor). Prefira conta com `ulimit`/cgroup nesses hosts.
- **Retenção:** `saida_resumo` (até 4000 caracteres, redigida) e o histórico da conversa ficam no banco e podem conter dados pessoais de logs. A purga/retenção (proposta: 180 dias) entra na F5.
- O prompt do agente e a tela ainda são de "só conversa": o texto do chat para esse agente é dívida da F5.

## Deploy
- Migration **199** (versão), idempotente, na etapa 6c. A auditoria (197) já foi na F2.
- Atualizar API (código + compose com as variáveis novas). **Sem `dist/` novo de comportamento** (só um rótulo no Admin), sem `dags/`, sem dependências (paramiko já existe).
- No **DEV**: definir `TERMINAL_SSH_AUTO_ADD=1` no `.env.dev` para o Terminal conectar ao `sshd-amostra`.
- Prova no SSH real: `scripts/prova_agente_terminal_ssh.py` (bateria de canários) — rode de novo se mexer no classificador, no executor ou nas listas.
