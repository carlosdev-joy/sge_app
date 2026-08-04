# Spec: data de referência ÚNICA por malha

Data: 2026-08-04 · Status: ✅ **F1, F2 e F3 no código** (branch
`feat/malha-republicar-pipelines`) · 🔜 F4 e F5 (mexem no fonte gerado,
exigem `force_all` no deploy)
Origem: incidente de produção na malha `Carga_Vida` (2026-08-04) — o Aguarde
liberou os dependentes com os predecessores em datas de referência diferentes
(parte no dia 3, parte no dia 4) e as execuções seguintes saíram erradas.

---

## 1. O que aconteceu (diagnóstico, não hipótese)

A data de referência (ODATE) é calculada **só por quem roda por agenda**
(`dags/utils/data_referencia.py`): com virada diferente de 00:00, quem começa
depois da virada carimba o **dia seguinte**. Numa malha que roda em torno desse
corte — a `Carga_Vida` começa 01:10 — pipelines separados por minutos caem em
dias diferentes.

Na malha, três casos:

| Quem | Como recebe a data | Diverge? |
|---|---|---|
| Raiz ligada ao Início | o Início copia `hora_virada` junto do agendamento (`api/routers/malhas.py:1342`) | não |
| Dependente publicado | `schedule=None`, **herda** a data do pai pelo push | não — nem calcula |
| **Dependente ainda com cron** (DAG não republicada) | roda no horário dele e **calcula a própria data** | **sim** |

A liberação (`dags/utils/dependencias.py:336`) compara **só o ODATE**: se os
predecessores têm SUCESSO naquela data, libera — mesmo que um deles tenha
produzido esse sucesso em outro dia real. A guardiã detecta a divergência mas
**só alerta** (`DATA_DIVERGENTE`), e o **push do pai — que é quem dispara na
cascata — não faz essa checagem** (`dags/etl_dag_factory.py:1743-1757`).

**Causa raiz:** pipeline com dependência cadastrada cuja DAG ainda não foi
republicada. Ele roda fora da malha, carimba a própria data e mistura a corrida.
É a mesma causa dos "dependentes em verde fora de ordem" relatados no mesmo dia.

Consultas de confirmação: `docs/diagnostico-liberacao-datas.sql`.

## 2. O que NÃO vamos fazer

**Remover a data de referência e rodar a malha como sequência pura.** Ela é
parte do índice único da corrida (`ux_pipe_exec`) e aparece em 326 pontos de 34
arquivos — claim, liberação, guardiã, visão de execução, eventos e pausa de
etapa. Removê-la é refazer o motor e perder o caso que originou a spec original:
a corrida que atravessa a meia-noite. O ajuste abaixo é uma fração do custo.

## 3. Decisões do usuário (2026-08-04)

1. **Virada única por malha.** Os membros não podem ter horas de virada
   diferentes entre si — a malha manda.
2. **Validação ANTES de o Início partir.** Data divergente entre os membros →
   **bloqueia a execução e gera alerta** (não é aviso: é recusa).
3. **Equalização automática, por malha (opção).** Malha marcada como
   "equalizar data" NÃO para o operador: ao encontrar datas diferentes no
   ciclo, **atribui a data da malha a todos e segue a execução**. Sem a marca,
   vale a regra 2 (bloqueio).

## 4. Modelo

`etl_malha` ganha (migration nova):

| Coluna | Tipo | Significado |
|---|---|---|
| `hora_virada` | TIME NULL | a virada da MALHA. NULL = usa a global. É ela que define o ODATE do ciclo. |
| `equalizar_data` | BIT NOT NULL DEFAULT 0 | 1 = ao divergir, carimba todos com a data da malha e segue; 0 = bloqueia e alerta. |

Nada de coluna nova em `etl_pipeline`: a virada continua morando lá (é o que o
motor lê), e a malha é quem a **compila** para os membros — o mesmo mecanismo do
agendamento do Início (F13), estendido dos filhos-raiz para todos os membros.

## 5. Fases

### F1 — Bloqueio no disparo + o aviso que precede o estrago ✅
- `POST /malhas/{m}/disparo` passa a **recusar** (422) quando algum membro tem
  execução no dia com data de referência diferente da data do ciclo, ou corrida
  em aberto. Hoje isso é aviso no modal. A recusa nomeia os pipelines e a data
  de cada um.
- Aviso forte e permanente na malha quando existir **membro com dependência
  ainda disparando por agenda** (`schedule_type <> 'on_demand'` com predecessor
  cadastrado) — com o botão *Republicar pipelines* ao lado.
- **Aceite:** malha com um membro carimbando D-1 não dispara pela tela; a
  mensagem diz quem e qual data. Com todos na mesma data, dispara como hoje.

### F2 — Virada única por malha ✅
- Campo de virada no painel da malha (ao lado do agendamento do Início).
- Ao salvar/publicar, a virada é copiada para **todos os membros** (hoje só as
  raízes assinadas recebem), com carimbo de publicação pendente em cada um.
- Divergência detectada na tela vira **erro** com o botão "equalizar agora".
- **Aceite:** membro com virada diferente aparece em vermelho antes de qualquer
  execução; após "equalizar", `hora_virada` é idêntica em todos e os cards
  pedem republicação.

### F3 — Equalização automática (a opção do §3.3) ✅
- Marca `equalizar_data` no cadastro da malha.
- No início do ciclo, quando há divergência: em vez de bloquear, **recarimba
  para a data da malha** as execuções do ciclo corrente que estiverem em outra
  data e segue o disparo.
- ⚠️ **Recarimbar é escrita em linha de execução** — as guardas:
  - só linhas do **ciclo corrente** (janela: da virada corrente para cá), nunca
    histórico antigo;
  - só linhas de membros **daquela malha**;
  - nunca sobrescreve uma linha que já exista na data-alvo para o mesmo
    pipeline com corrida viva (evita duas corridas do mesmo dia);
  - grava evento `DATA_EQUALIZADA` com a lista `pipeline: de → para`, e o
    `motivo` da linha registra a origem — histórico não pode mudar em silêncio.
- **Aceite:** malha marcada, um membro em D-1 → o disparo equaliza, o painel
  mostra o evento com o de/para e a corrida anda; malha não marcada → bloqueio
  da F1.

### F4 — Push com a mesma trava da guardiã
- O push do pai (fonte gerado do `dag_factory`) recusa disparar quando os
  predecessores do filho estão em datas divergentes, gravando `DATA_DIVERGENTE`
  — hoje só a guardiã faz isso, e o push é quem dispara.
- ⚠️ Exige **regerar as DAGs** no deploy (`force_all`).
- **Aceite:** cenário reproduzido no dev com dois pais em datas diferentes: o
  filho não é disparado e o evento aparece no painel.

### F5 — Validação no gatilho automático
- O `check_agenda` da raiz consulta a malha antes de partir: com membro em
  execução no dia ou data divergente, **não parte** (PULADO com motivo) ou
  equaliza, conforme a marca da malha.
- ⚠️ Também exige regerar as DAGs. É a fase que fecha o caso do disparo por
  cron — sem ela, a proteção vale só para o disparo pela tela.

## 6. Ordem e risco

F1 e F2 são API + front (deploy leve, sem regerar DAG) e já cobrem o caso
operacional. F3 é a que escreve em execução — vai depois, com o smoke dedicado.
F4 e F5 mexem no fonte gerado e entram juntas, com `force_all`.

**Enquanto nada disso sobe:** republicar os pipelines da malha já corta a fonte
da divergência (o dependente para de rodar por cron e passa a herdar a data).
