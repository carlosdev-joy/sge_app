# Agente Terminal — F2: fundação

Segunda fase da spec `docs/spec-agente-terminal.md`. **Sem execução de comandos ainda.**

## O que muda
- Novo agente `terminal` no catálogo de Agentes, **desligado por padrão e travado como indisponível** (`disponivel: False`) até a F5: mesmo com os interruptores ligados e a permissão concedida ele não aparece nem abre a conversa (sem ferramentas ele inventaria comandos e saídas). O interruptor fica desabilitado em Admin › Agentes com o aviso “ainda não disponível”.
- Dois recursos RBAC, sempre concedidos **usuário a usuário** (nunca por perfil), só para o perfil `desenvolvedor` (e admin): `agente_terminal` (usar) e `agente_terminal_escrita` (confirmar comandos que alteram o servidor, a partir da F4). A escrita tem interruptor geral próprio, `agente_terminal_escrita_enabled`, que nasce desligado.
- Admin › Inteligência Artificial › Agentes: linha do Terminal com interruptor, concessão de uso e de escrita e o interruptor da escrita.
- Tabela de auditoria `etl_agente_terminal_cmd` e consulta `GET /agentes/terminal/auditoria` (só admin; filtros por usuário, estado, classe e período). Comandos e resumos entram redigidos, nunca com segredo — inclusive formas de linha de comando (`-pSENHA`, `user:senha@`, `Bearer`, `--password`, `KEY_PASS=`). Comando que continha segredo só pode ser registrado como proibido/bloqueado.
- Máquina de estados fechada no serviço **e** no banco (CHECKs): escrita nasce `proposto`, leitura `executando`, proibido `bloqueado`; `proposto → executando` só dentro do prazo e atômico (`iniciar`); finais por transições permitidas (`finalizar`). Prazos pelo relógio do banco (`GETDATE()`).
- `exigir_escrita()`: a checagem completa da F4 (kill switch da escrita vale até para o admin + recurso por usuário).
- Ids `*_escrita` ficam reservados para agentes criados pela tela (colidiriam com o recurso de escrita).

## Deploy
- Migrations **197** (auditoria) e **198** (versão), idempotentes, na etapa 6c do `deploy.sh`.
- Atualizar API e `dist/`. Sem `dags/`, sem dependências novas. Quem já tem sessão precisa de novo login para enxergar os recursos novos.
- Nada muda para usuários enquanto `agente_terminal_enabled` estiver desligado.
