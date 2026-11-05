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
1. `scripts/deploy.sh` (puxa a `main`): aplicar as migrations **153** e **154** (6c, `[s/N]` → s); atualizar **API** e **`dist/`**.
   `config/` → responder **n**. Sem `dags/`, sem dependência nova (paramiko já existe).
2. Variáveis da API (sem segredo no Git):
   - `DS_SSH_*` — já existem (Console DataStage). `AF_SSH_HOST/PORT/USER/PASSWORD|KEY_FILE` — servidor Orquestra/Airflow
     (sem elas aparece "não configurado").
   - `<PREFIXO>_SSH_KNOWN_HOSTS` (ou `DS_SSH_KNOWN_HOSTS`) — **obrigatório**: sem ele a conexão falha fechada.
     **Nunca** usar `TERMINAL_SSH_AUTO_ADD=1` em produção.
   - Opcionais: `TERMINAL_RAIZES_<ID>` (pastas de leitura), `TERMINAL_CONTAINERS_<ID>` (containers de `docker logs`).
   - Conta SSH de **menor privilégio**, sem grupo `docker`.
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
