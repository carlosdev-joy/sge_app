# Agente Terminal — entrega na `main` (versão 2.6.13)

Roteiro de produção do agente **Terminal** (spec `docs/spec-agente-terminal.md`, fases F1–F5). Segue o caminho do PIO: o mesmo
código das PRs #538–#543 da `develop`, aplicado sobre a `main` **sem** trazer nada mais da `develop` (Workspace, EOC, Malha F16).
Detalhes de cada fase: `agente-terminal-f1.md` … `agente-terminal-f5.md` (os números de migration citados lá são os da `develop`).

## O que entra
- Agente **Terminal** em /agentes: chat em formato de terminal, em linguagem livre, sobre o DataStage (`dsjob`, só leitura), os
  servidores SSH configurados e os bancos que o admin liberar (só SELECT).
- **Leitura livre; escrita só com confirmação** no card (comando inteiro visível, hash de uso único, 2 minutos). Classificação
  determinística no backend — a IA não decide. Segredos, `sudo`, desligar servidor e parar containers do Orquestra: bloqueados
  quando escritos de forma reconhecível (a proteção é textual; a **conta SSH é o teto real**).
- RBAC: `agente_terminal` (uso) e `agente_terminal_escrita` (escrita). Interruptores `agente_terminal_enabled` e
  `agente_terminal_escrita_enabled` (este vale até para admin). **Nasce desligado.**
- Admin › IA › Agentes › Terminal: abas **Bancos** e **Auditoria**; retenção de 180 dias (30–3650) com purga automática.

## Migrations (etapa 6c do `deploy.sh`)
| main | develop | o quê |
|------|---------|-------|
| `153_agente_terminal` | `197_agente_terminal` | tabela `etl_agente_terminal_cmd` (auditoria), com guarda `IF OBJECT_ID` |
| `154_versao_agente_terminal` | `198`–`201` (versões) | versão **2.6.13** "Agente Terminal em /agentes" |

⚠️ Ao promover a `develop` um dia, reconciliar: a 153 e a 197 criam a mesma tabela (ambas idempotentes; o `migrate.py`
controla por nome) e as versões 198–201 da develop entram como registros históricos.

## Deploy em produção
0. **Antes do deploy (preparar no host):**
   - Conferir o que vai junto: `python sql/migrate.py --dry-run` deve listar só **153** e **154**. Se listar 143–152, os cards do
     PIO ainda não foram publicados e vão junto neste deploy.
   - Conferir que nenhum agente ou permissão já usa os ids reservados pelo Terminal:
     `SELECT agente_id FROM dbo.etl_agente WHERE agente_id IN ('terminal','escrita') OR agente_id LIKE '%[_]escrita'`
     e procurar `agente_terminal`/`agente_terminal_escrita` nas permissões de usuários e perfis (esperado: nada).
   - **known_hosts e chave precisam existir DENTRO do container** `orquestra-api`, que hoje só monta `dags/`, `dsx/` e `api/`.
     Ver como o Console DataStage resolve o `DS_SSH_KNOWN_HOSTS` hoje. Se estiver vazio (o Terminal **recusa** sem known_hosts),
     gerar o arquivo no host (`ssh-keyscan -p <porta> <host> > /opt/airflow/ssh/known_hosts`, conferindo a impressão digital
     com quem administra o servidor). Depois, montar a pasta só-leitura no serviço `orquestra-api` do `docker-compose.yaml` do
     servidor: `- /opt/airflow/ssh:/opt/orquestra/ssh:ro` em `volumes:`. As variáveis apontam para o caminho **do container**
     (`DS_SSH_KNOWN_HOSTS=/opt/orquestra/ssh/known_hosts`; `AF_SSH_KEY_FILE=/opt/orquestra/ssh/<chave>`, se usar chave).
   - Preencher o `.env` do host **antes** do passo 1 (assim o `up -d` da etapa 7 já sobe com elas):
     - `DS_SSH_*` já existem (Console DataStage).
     - `AF_SSH_HOST/PORT/USER/PASSWORD|KEY_FILE` e `AF_SSH_KNOWN_HOSTS` para o servidor Orquestra/Airflow. Sem elas, ele
       aparece "não configurado" e só o DataStage fica disponível.
     - Opcionais: `TERMINAL_RAIZES_<ID>` (pastas de leitura) e `TERMINAL_CONTAINERS_<ID>` (containers de `docker logs`).
     - **Nunca** `TERMINAL_SSH_AUTO_ADD=1` em produção. Conta SSH de **menor privilégio**, sem grupo `docker`.
1. `scripts/deploy.sh` (puxa a `main`):
   - migrations **153** e **154** na etapa 6c (`[s/N]` → **s**);
   - **"docker-compose.yaml mudou no repo. Sobrescrever?"** → **s**, com backup automático. Sem isso, as variáveis `AF_SSH_*` e
     `TERMINAL_*` **não chegam ao container**: o Airflow fica "não configurado" e as restrições `TERMINAL_CONTAINERS_*`/`RAIZES_*`
     são ignoradas em silêncio (viram "qualquer container"/pastas padrão). Se o compose do servidor tiver ajustes locais,
     responder **n** e copiar à mão o bloco "Agente Terminal" (variáveis do `orquestra-api`), mais o volume do passo 0;
   - `config/` → **n**;
   - API e **`dist/`** atualizados. Sem `dags/`, sem dependência nova (paramiko já existe).
2. Se o `.env` ou o compose forem mexidos **depois** do deploy: `docker compose up -d orquestra-api` (recria só a API).
   Conferir com `docker exec orquestra-api printenv | grep -c '^AF_SSH_\|^TERMINAL_'`, que só conta as variáveis, sem mostrar valores.
3. Ligar: Admin › IA › Agentes → Terminal (`agente_terminal_enabled`); escrita (`agente_terminal_escrita_enabled`) só se desejado.
   Conceder `agente_terminal` / `agente_terminal_escrita` aos usuários → **relogin**.

## Smoke em produção
a) Admin › Versões mostra **2.6.13 — Agente Terminal em /agentes**.
b) Usuário com `agente_terminal`: /agentes mostra o Terminal; os servidores configurados aparecem nos chips.
c) "liste os jobs do projeto X" / "últimas linhas do log Y" → leitura roda e a saída aparece redigida.
d) Pedido de escrita (ex.: criar arquivo numa pasta de teste) → card de confirmação; **Recusar** → nada roda; repetir e
   **Confirmar** → roda uma vez; o card mostra executado.
e) "mostre o .env" → bloqueado. `grep -r -l -e x /var/log` → não lista auth.log/secure/btmp.
f) Admin › Terminal › Auditoria lista os comandos acima com usuário, servidor e estado.

## Rollback
Desligar `agente_terminal_enabled` (efeito imediato). Código: voltar a `main` para o commit anterior ao merge e republicar
API + `dist/`. As migrations podem ficar (tabela nova sem uso; versão é só registro).
