# ORQUESTRA — Funcionalidades, Benefícios e Valor para a Área

> Versão de referência: v2.3.0 · Data: 2026-06-15
> Público: gestores, analistas, engenheiros de dados e stakeholders de negócio

---

## 1. Contexto: o problema que o ORQUESTRA resolve

Antes da ferramenta, a área de dados operava **sem visibilidade centralizada** sobre seus pipelines ETL. O cenário era:

| Situação anterior | Impacto prático |
|---|---|
| Pipelines cadastrados diretamente no Airflow por arquivo `.py` | Nenhum padrão; cada desenvolvedor usava convenções diferentes |
| Falhas descobertas pelo usuário final | Tempo de resposta alto; impacto nos relatórios de negócio |
| Sem rastreabilidade de origem/destino dos dados | Impossível saber "de onde veio esse número?" |
| Gestão de SLA inexistente | Prazos de entrega de dados eram cumpridos por acaso |
| Execuções manuais sem registro | Não havia como auditar "quem rodou o quê e quando" |
| Sem catálogo de dados | Redundância de desenvolvimento; dados sensíveis (PII) sem classificação |

O ORQUESTRA foi construído **sobre** o Airflow existente, adicionando uma camada de governança, operação e visibilidade sem substituir a orquestração técnica.

---

## 2. Mapa de funcionalidades por perfil

### 2.1 Perfil Consulta (analistas, gestores, auditoria)

#### Dashboard — saúde da malha em tempo real
- **KPIs executivos**: total de execuções no período, taxa de sucesso, contagem de falhas, duração média por pipeline.
- **Execuções em andamento**: lista ao vivo de pipelines rodando neste momento, com duração corrente.
- **Últimas falhas**: as 5 falhas mais recentes com link direto para o log — sem precisar acessar o Airflow.
- **Alertas de performance**: execuções que consumiram mais de 3h, 6h ou 12h são destacadas automaticamente.
- **Gantt do dia**: linha do tempo visual das execuções do dia corrente; permite ver sobreposições e gargalos de janela.
- **Atualização automática**: o Dashboard se atualiza periodicamente sem precisar de F5.

#### Logs — histórico completo de execuções
- Filtros por projeto, pipeline, status (`SUCCESS` / `FAILED` / `RUNNING`) e período.
- **Modo agregado**: uma linha por execução completa do pipeline (visão gerencial).
- **Modo detalhe**: uma linha por job dentro da execução (diagnóstico técnico).
- Clique em qualquer execução para abrir a saída completa de cada job: log de terminal, código de retorno, timestamps de início e fim, duração.
- Aba **Falhas recentes**: lista consolidada das últimas falhas para triagem rápida.
- Aba **Runs do factory**: histórico de geração de DAGs (quando o sistema reconstrói os arquivos do Airflow).

#### Malha — visão geral de todos os pipelines
- **Visão cards**: um card por pipeline mostrando projeto, horário de agendamento, criticidade, status da última execução e cadeia de jobs (jobs lado a lado = paralelo; setas = sequencial).
- **Visão diagrama**: fluxo visual das dependências entre pipelines.
- Filtros por nome, projeto, criticidade, status.
- **Exportar**: gera planilha Excel/CSV com toda a malha — útil para reuniões, planejamento de capacidade e auditoria.

#### Governança — lineage e catálogo de dados
- **Lineage por job**: para cada job, visualize graficamente origens → transformações → destinos (tabelas, arquivos, colunas). Responde "de onde esse dado veio?".
- **Catálogo de dados**: pesquise qualquer tabela ou arquivo; veja quais pipelines o produzem e quais o consomem, classificação (PII, Confidencial, Público), dono (owner/steward) e tags de negócio.
- **Análise de impacto de campo (DSX)**: importe um `.dsx` do DataStage e veja quais jobs/pipelines são afetados por uma mudança de coluna — antes de fazer a mudança.

### 2.2 Perfil Operador (operação/sustentação ETL)

Tudo do Consulta, mais:

- **Executar pipeline manualmente**: dispara imediatamente, ignorando calendário, blackout e restrições de horário.
- **Reexecutar falha**: localize a execução falha, analise o log e dispare nova tentativa com um clique.
- **Monitor de SLA**: o sistema verifica a cada 5 minutos se execuções estão dentro do SLA cadastrado e envia alertas no Microsoft Teams:
  - **RISCO** quando ≥ 80% do tempo de SLA foi consumido.
  - **ESTOURO** quando o SLA foi ultrapassado.
  - Cada alerta é enviado uma única vez (sem spam de mensagens repetidas).
- **Consulta de blackout**: visualize as janelas de bloqueio ativas (fechamento contábil, manutenção de infra) para antecipar impactos.

### 2.3 Perfil Desenvolvedor ETL (engenharia de dados)

Tudo do Operador, mais:

#### Wizard de cadastro de pipeline (6 etapas)
1. **Identificação**: nome, projeto, domínio, descrição, tags livres.
2. **Classificação**: criticidade (Alta/Média/Baixa), SLA em minutos, ambiente, link para runbook.
3. **Agendamento** — 7 modalidades:
   - Diário (hora:minuto)
   - Semanal (dias da semana)
   - Mensal (dia do mês)
   - Quinzenal (dia D e D+15 de cada mês)
   - De hora em hora (a cada N horas)
   - Horários específicos: lista de horários exatos + dias da semana (ex.: seg–sex às 09:00, 10:30, 13:00) — ideal para cargas intradiárias
   - Sob demanda (sem agendamento automático)
   - Opções: somente dias úteis, calendário de feriados, trigger por dependência (dispara quando pipeline antecessor conclui)
4. **Parâmetros de execução**: retries, delay entre retries, máximo de execuções simultâneas, pool de workers.
5. **Jobs**: adicione jobs com ordem de execução. Mesma ordem = execução paralela; ordem crescente = sequencial. Suporta tipos: `datastage`, `shell`, `python`, `storedproc` e outros.
6. **Lineage**: cadastre origens e destinos de cada job.
7. **Revisão**: tela de confirmação antes de salvar.
8. **Gerar DAG**: publica o pipeline no Airflow com um clique.

#### Gerenciamento de jobs (aba Jobs)
- Cadastro e edição completa: tipo, comando/job DataStage, conexão SSH, parâmetros.
- Reordenar por arrastar-e-soltar.
- Diagrama de execução: visualize a ordem e paralelismo dos jobs antes de salvar.
- Lineage obrigatório por job.
- **Extração automática de lineage do DSX**: importe o arquivo `.dsx` e o sistema extrai origens e destinos automaticamente.

#### Importar sequence DataStage (.dsx)
- Upload do `.dsx` → ORQUESTRA gera automaticamente o rascunho do pipeline com todos os jobs, ordem de execução e lineage.
- Revise, ajuste e aprove — tudo criado de uma vez.

#### Planos de ajuste / change plans
- Registre mudanças planejadas em jobs e pipelines antes de executá-las.
- Rastreamento de status (pendente/aprovado/executado) com histórico de aprovações.

### 2.4 Perfil Administrador

Tudo dos demais, mais a aba **Admin**:

- **Configurações da aplicação**: parâmetros chave/valor (URL do Teams, TTL de sessão, etc.) — sem redeploy.
- **Tipos de job**: CRUD dos tipos aceitos no cadastro.
- **Manutenção de DAGs**: regenerar todos os DAGs a partir do banco (pós-migration ou correção de factory); excluir pipeline com todos os seus jobs e DAG.
- **Calendários e blackout**: cadastre feriados nacionais/ANBIMA/corporativos e janelas de bloqueio (globais ou por pipeline).
- **Usuários & Perfis**: promova usuários, ajuste permissões por tela e ação, crie perfis personalizados (ex.: `auditoria`), configure TTL de sessão.
- **Projetos**: CRUD dos projetos disponíveis para categorização de pipelines.
- **Relatório diário automático**: geração e envio automático de relatório de execuções do dia anterior.

---

## 3. Benefícios diretos e insights habilitados

### 3.1 Visibilidade que antes não existia

| Pergunta de negócio | Como o ORQUESTRA responde |
|---|---|
| "Meus dados já estão prontos?" | Dashboard → Executando agora; Logs → status da carga |
| "Por que o relatório de hoje está errado?" | Logs → detalhe do job → saída completa + código de retorno |
| "Qual pipeline alimenta essa tabela?" | Governança → Catálogo → produtores/consumidores |
| "Se mudar essa coluna, o que quebra?" | Análise de impacto de campo (DSX) |
| "Quantas cargas falharam no mês?" | Dashboard → KPI de falhas; Logs → filtro por período |
| "Esse dado é sensível?" | Governança → Catálogo → classificação PII/Confidencial |

### 3.2 Redução de tempo de resposta a incidentes

- **Antes**: analista percebe dado errado → abre chamado → time de TI acessa Airflow → navega entre DAGs → encontra log → diagnóstico.
- **Depois**: analista acessa ORQUESTRA → Logs → clica na falha → lê o erro em segundos. Tempo médio de diagnóstico reduzido de horas para minutos.

### 3.3 SLA como compromisso mensurável

Antes do ORQUESTRA, SLA de pipelines era um conceito informal. Agora:
- Cada pipeline tem SLA cadastrado em minutos.
- Alertas automáticos no Teams avisam a equipe **antes** do estouro (80% consumido).
- Histórico de execuções permite calcular aderência ao SLA no período.

### 3.4 Auditoria e rastreabilidade

- Toda execução (agendada ou manual) é registrada com usuário, horário de início/fim, status e log.
- Quem disparou a execução fica registrado — importante para compliance.
- Lineage documenta o fluxo completo dos dados: da origem ao destino final.
- Catálogo com classificação PII facilita auditorias de LGPD/privacidade.

### 3.5 Padronização do trabalho de engenharia

- Todos os pipelines seguem o mesmo modelo de cadastro (wizard).
- Convenções de nomenclatura, criticidade e domínio são aplicadas no cadastro.
- Dependências entre pipelines são gerenciadas pela ferramenta (Dataset do Airflow) — sem scripts ad-hoc.
- Import de `.dsx` reduz tempo de onboarding de jobs DataStage de horas para minutos.

### 3.6 Blackout e calendário como proteção operacional

- Fechamentos contábeis, manutenções programadas e feriados são cadastrados uma vez e aplicados automaticamente.
- Sem necessidade de pausar pipelines manualmente ou lembrar de despausar depois.

### 3.7 Independência de rede (air-gap)

- Funciona 100% dentro da rede corporativa sem depender de internet, CDN ou serviços externos.
- Todos os recursos (JS, CSS, fontes, ícones) são servidos localmente.

---

## 4. Arquitetura simplificada

```
┌─────────────────────────────────────────────┐
│              Navegador do usuário            │
│         React 19 + TypeScript (SPA)         │
│        Servida por nginx (offline-first)     │
└────────────────────┬────────────────────────┘
                     │ HTTP / JSON
┌────────────────────▼────────────────────────┐
│           API ORQUESTRA (FastAPI)            │
│  43+ endpoints: pipelines, jobs, execuções  │
│  governança, admin, SLA, relatórios          │
└──────┬─────────────────────┬────────────────┘
       │                     │
┌──────▼──────┐    ┌─────────▼──────────────┐
│  SQL Server │    │  Apache Airflow 2.11    │
│  (DMDB41)   │    │  CeleryExecutor        │
│  tabelas    │    │  DAGs gerados           │
│  etl_*      │    │  automaticamente        │
└─────────────┘    └────────────────────────┘
```

- **Frontend**: SPA React sem CDN externo; build commitado no Git; nginx serve estático.
- **Backend**: FastAPI com 16 routers; autenticação delegada ao Airflow (mesma senha de rede).
- **Orquestração**: DAGs gerados automaticamente pelo factory a partir do banco de dados.
- **Banco**: SQL Server para dados ETL + Postgres para metadados do Airflow.
- **Alertas**: Teams via webhook; alertas de SLA enviados uma única vez por execução.

---

## 5. Glossário rápido

| Termo | Significado no ORQUESTRA |
|---|---|
| **Pipeline** | Conjunto de jobs orquestrados, com agendamento e SLA definidos |
| **Job** | Unidade de trabalho dentro de um pipeline (script shell, job DataStage, procedure, etc.) |
| **DAG** | Arquivo Python que o Airflow executa; gerado automaticamente pelo ORQUESTRA |
| **Lineage** | Rastreamento de origem → transformação → destino dos dados |
| **Catálogo** | Inventário de tabelas e arquivos com classificação e dono |
| **Blackout** | Janela de tempo em que execuções agendadas são suspensas |
| **SLA** | Tempo máximo esperado para conclusão de um pipeline |
| **Factory** | Componente que converte cadastros do banco em DAGs do Airflow |
| **DSX** | Arquivo de export de sequence do IBM DataStage |
| **Pool** | Recurso do Airflow para limitar execuções concorrentes |
| **Dataset** | Mecanismo do Airflow para trigger por dependência entre DAGs |
