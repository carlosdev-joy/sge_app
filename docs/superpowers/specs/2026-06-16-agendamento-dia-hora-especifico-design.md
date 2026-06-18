# Agendamento "Dia + Hora Específico" — Design

Data: 2026-06-16
Status: Aguardando aprovação (requisito a ser publicado no Confluence)

## 1. Objetivo

Adicionar uma nova opção de agendamento na criação/edição de pipeline: **"Dia + Hora Específico"**. Permite selecionar **N dias do mês** (até 5), onde **cada dia tem seu próprio conjunto independente de N horários** (até 5 horários por dia).

Exemplo de configuração: dia 1 às 09:00; dia 15 às 14:00 e 18:00; dia 28 às 10:00.

Diferença em relação ao que já existe hoje:
- `monthly`: apenas 1 dia do mês + 1 horário.
- `custom` ("Horários específicos"): dias da **semana** (não do mês) + horários compartilhados por todos os dias selecionados.
- `monthly_days_times` (novo): dias do **mês**, com horários **independentes por dia**.

## 2. Modelo de dados

Novo `schedule_type`: `monthly_days_times`, adicionado a `SCHEDULE_TYPES` e `SCHEDULE_LABELS` (label: "Dia + Hora Específico") em `ui-react/src/.../pipelineUtils.ts`.

Novo campo persistido (nova migration, seguindo o padrão das migrations 017/018): `dias_horarios_mes` (TEXT, nullable), serializado como JSON:

```json
[
  {"dia": 1, "horarios": ["09:00"]},
  {"dia": 15, "horarios": ["14:00", "18:00"]},
  {"dia": 28, "horarios": ["10:00"]}
]
```

Regras:
- Array com 1 a 5 entradas (dias). Dias únicos, inteiros entre 1 e 28 (mesmo limite já usado em `monthly`/`biweekly`, evita ambiguidade em meses curtos).
- Cada entrada tem 1 a 5 horários, formato `HH:MM`, únicos dentro do mesmo dia.
- Campo é exclusivo do `schedule_type = 'monthly_days_times'`; não interfere nos campos existentes (`horarios_especificos`, `dias_semana`, `schedule_dom`, etc.), que continuam servindo os demais tipos.

## 3. UI/UX (Passo 1 — Agendamento do wizard)

Em `PipelineFormModal.tsx`, nova opção no seletor de tipo de agendamento. Ao selecionar "Dia + Hora Específico":

- Lista dinâmica de blocos "Dia do mês": botão "+ Adicionar dia" (até 5 blocos); cada bloco tem um select de dia (1–28, sem permitir repetir dia já adicionado) e botão de remover.
- Dentro de cada bloco, lista de horários: botão "+ Adicionar horário" (até 5 por dia); cada horário é um input `HH:MM`, sem permitir repetir horário já adicionado naquele dia.
- Texto-resumo (preview) abaixo do bloco, seguindo o padrão visual já usado nas outras opções de agendamento, ex: "Dia 1 às 09:00 · Dia 15 às 14:00, 18:00 · Dia 28 às 10:00".
- Validação client-side: bloqueia salvar com 0 dias, dia sem horário, ou limites excedidos — mensagens de erro inline consistentes com o restante do formulário.

## 4. Backend — validação e persistência

Em `api/routers/pipelines.py`, endpoint `POST /pipelines/register`, novo bloco de validação (análogo ao de `horarios_especificos`, linhas 356–372 atuais) quando `schedule_type == 'monthly_days_times'`:

- `dias_horarios_mes` obrigatório e não vazio.
- JSON válido; 1–5 entradas; `dia` inteiro 1–28 sem duplicados; 1–5 `horarios` por dia, formato `HH:MM` válido, sem duplicados no mesmo dia.
- Erro `422` com mensagem específica indicando qual regra foi violada.

Persistência via `sp_etl_pipeline_upsert`, mesmo padrão dos demais campos avançados (degrada para `NULL` se a coluna ainda não existir no ambiente, evitando quebra em deploys parciais).

## 5. Tradução para Airflow (`dags/etl_dag_factory.py`)

Novo branch em `_build_cron(pipeline)` para `monthly_days_times`:

1. Parseia `dias_horarios_mes`, extrai o conjunto de dias únicos e o conjunto de minutos/horas únicos (união de todos os horários de todos os dias).
2. Gera cron superset: `"{minutos_unicos} {horas_unicas} {dias_unicos} * *"` — garante que o Airflow dispare em todos os horários possíveis de qualquer um dos dias configurados.
3. Retorna também a lista completa de combinações válidas `[(dia, "HH:MM"), ...]`, igual ao padrão já usado para `custom`/`hourly_n`.

A constante `HORARIOS_ESPECIFICOS` gerada na DAG passa a registrar essas combinações `(dia, horário)` quando o tipo for `monthly_days_times`.

O `ShortCircuitOperator` (`check_agenda`) já existente é estendido: quando `schedule_type == 'monthly_days_times'`, valida a tupla `(dia_do_mes_atual, "HH:MM_atual")` contra a lista de combinações válidas — pulando a execução (skip) quando a tupla não corresponde a nenhuma combinação configurada. Isso é o mesmo padrão de "cron amplo + checagem em runtime" já usado pelo sistema, só que agora a checagem cruza dia × horário em vez de validar apenas o horário.

## 6. Compatibilidade e riscos

- Pipelines existentes não usam o novo campo (`NULL`) — sem impacto em comportamento atual.
- Execuções "fantasmas" (disparadas pelo cron superset e puladas pelo `check_agenda`) aparecem no histórico do Airflow como `skipped` — comportamento já existente hoje para o tipo `custom`, não é uma regressão introduzida por esta feature.
- Limite de 5 dias × 5 horários (25 combinações) mantém o cron superset pequeno e legível.

## 7. Cenários de teste (QA)

### Criação — casos válidos
1. 1 dia, 1 horário (mínimo permitido).
2. 5 dias, cada um com 5 horários (máximo permitido — 25 combinações).
3. Dias e horários fora de ordem na entrada (ex: 28, 1, 15) — deve persistir e exibir ordenado.
4. Dias com quantidades diferentes de horários entre si (ex: dia 1 com 1 horário, dia 15 com 5).

### Criação — casos inválidos (devem falhar com erro claro)
5. Dia do mês `0` ou `29+` → erro de validação.
6. Dia duplicado no array (ex: dia 1 aparece duas vezes) → erro.
7. Horário inválido (ex: `25:00`, `09:60`, texto livre) → erro.
8. Horário duplicado dentro do mesmo dia → erro.
9. Mais de 5 dias no array → erro.
10. Mais de 5 horários em um mesmo dia → erro.
11. Array vazio ou campo ausente com `schedule_type = 'monthly_days_times'` → erro.
12. Dia sem nenhum horário (`horarios: []`) → erro.

### Edição
13. Pipeline existente de outro `schedule_type` (ex: `monthly`) editado para `monthly_days_times` → salva corretamente e UI recarrega os novos campos.
14. Pipeline `monthly_days_times` editado de volta para outro tipo (ex: `daily`) → campo `dias_horarios_mes` é limpo/ignorado, sem deixar resíduo causando comportamento inesperado.
15. Edição apenas adicionando um horário a um dia já existente, sem alterar os demais dias.
16. Edição removendo um dia inteiro da configuração.

### Geração de DAG / Execução Airflow
17. Cron superset gerado contém exatamente a união de todos os dias e todos os horários (minutos/horas) configurados — nenhum a mais, nenhum a menos.
18. Execução no `(dia, horário)` configurado → pipeline dispara normalmente (não é pulado pelo `check_agenda`).
19. Execução em um `(dia, horário)` do superset que NÃO está na lista de combinações válidas (ex: dia 1 às 14:00, quando dia 1 só tem 09:00 configurado, mas 14:00 existe por causa do dia 15) → `check_agenda` deve pular (skip), não executar o pipeline.
20. Execução em dia/horário totalmente fora do superset → Airflow nem dispara (comportamento padrão de cron).

### Persistência / Regressão
21. Campo `dias_horarios_mes` é `NULL` para pipelines com outros `schedule_type` — sem erros em listagem/edição desses pipelines.
22. Reload da página/edição do pipeline `monthly_days_times` reidrata corretamente todos os blocos de dia e horários a partir do JSON salvo.
23. Ambiente com a migration ainda não aplicada: tentativa de salvar `monthly_days_times` degrada para `NULL` na coluna (mesmo padrão dos demais campos avançados), sem quebrar a request.

## 8. Fora de escopo

- Hora "específica" não inclui timezone customizado por dia (segue o timezone global já configurado no pipeline).
- Não há suporte a "todo dia do mês exceto X" ou expressões negativas — apenas seleção positiva explícita de dias.
- Não estende o tipo `custom` (dias da semana) — é uma feature nova e independente.
