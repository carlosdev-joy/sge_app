# ORQUESTRA — Manual de Utilização por Perfil

> Versão do produto: v2.3.0 · Acesso: `http://<servidor>` na rede corporativa
> Login: **matrícula e senha de rede** (as mesmas do Airflow). Sem acesso? Solicite ao administrador.

---

## Perfis de acesso

| Perfil | Quem é | O que pode fazer |
|---|---|---|
| **Consulta** | Analistas, gestores, auditoria | Visualizar Dashboard, Logs, Malha, Governança (lineage/catálogo) e Monitor DataStage |
| **Operador** | Operação/Sustentação ETL | Tudo do Consulta + executar pipelines manualmente, reexecutar falhas, acompanhar SLA |
| **Desenvolvedor ETL** | Equipe de engenharia de dados | Tudo do Operador + cadastrar/editar pipelines, jobs, lineage, agendamentos, importar sequences DSX |
| **Administrador** | Responsável pela plataforma | Tudo + aba Admin: configurações, tipos de job, regenerar DAGs, excluir pipelines, calendários/blackout |

> **Como funciona:** todo usuário entra automaticamente no 1º login com perfil **consulta**. O administrador promove usuários e ajusta o que cada perfil acessa (telas e ações) em **Admin → Usuários & Perfis** — sem mexer no banco. A sessão sobrevive ao F5 e expira após o período configurado (padrão 12h); a senha nunca é armazenada, apenas um token de sessão revogável.

---

## 1. Perfil Consulta

### 1.1 Dashboard (aba ⌂)
Visão geral da saúde da malha:
- **KPIs do topo**: execuções do período, taxa de sucesso, falhas, duração média.
- **Executando agora**: pipelines em andamento em tempo real.
- **Últimas falhas**: as 5 mais recentes — clique para ver o log.
- **Alertas de performance**: execuções acima de 3h/6h/12h.
- **Gantt**: linha do tempo das execuções do dia.

### 1.2 Logs (aba 🗒)
Histórico completo de execuções:
1. Filtre por projeto, pipeline, status ou período.
2. Alterne entre **modo agregado** (uma linha por execução do pipeline) e **modo detalhe** (uma linha por job).
3. Clique numa execução para abrir o log de cada job (saída completa, código de retorno, duração).

### 1.3 Malha de Pipelines (aba ⊞)
Uma **malha** é um agrupamento de pipelines que rodam juntos como um processo só
— o equivalente à sequence mestre do DataStage ou a uma pasta SMART do Control-M.
A malha não executa nada por si: ela é a planta de como os pipelines se encadeiam.
O botão **“O que é a malha?”**, ao lado do título, abre essa explicação na tela.

> O inventário de pipelines (cards por projeto, cadeias de jobs e exportação CSV)
> mudou de endereço: vive em **Governança → Catálogo & Lineage** (§1.4).

**A lista (tela inicial).** Um card por malha. O que cada informação diz:

| No card | Significa |
|---|---|
| bolinha + **Ativa/Inativa** | malha inativa não emite mais notificações nem aviso de conclusão. Não apaga nada: dependências e agendamento já criados continuam valendo. |
| **criticidade** | a mais alta entre os pipelines da malha (Crítica > Alta > Média > Baixa). |
| ⚙ **N pipelines (M ativos) · E etapas** | o tamanho da malha: quantos pipelines participam, quantos estão ativos e o total de etapas (jobs) somando todos eles — é a leitura de complexidade. |
| 🕒 **gatilho** | a que horas a malha começa. Sai do agendamento da própria malha (o componente Início) quando existe; senão é derivado dos pipelines que disparam sozinhos — havendo horários diferentes, o card mostra o **mais cedo** e avisa que há outros. Sem ninguém agendado: **sob demanda**. Passe o mouse para ver de onde veio e quais pipelines disparam. |
| ▶ **última execução** | data e hora da corrida mais recente entre os pipelines da malha, com o status colorido — é o “quando isso foi usado pela última vez”. Sem corrida registrada, o card diz **sem execução registrada** (nunca inventa data). |
| 📅 **criada em** | quando a malha foi cadastrada. |

**Filtrar a lista.** A busca no topo casa **nome e descrição** (ignora
maiúsculas e acentos) e o seletor ao lado filtra por **Ativas / Inativas /
Todas**. As pílulas de contagem passam a mostrar “N de M malhas” enquanto
houver filtro; **Limpar** volta à lista inteira.

**Abrir uma malha** troca a lista pelo **diagrama** em tela cheia, com dois
modos: **Montagem** (desenhar — arrastar uma seta entre dois pipelines cadastra
a dependência de verdade) e **Execução** (acompanhar um dia: status de cada
pipeline, componentes acesos e o botão *Disparar malha*). Os componentes
Início, Aguarde, Notificação e Fim estão detalhados no §3.6.

⚠️ A dependência é **global**, não pertence à malha: se dois desenhos usam o
mesmo par de pipelines, é a mesma dependência. Por isso uma dependência criada
pelo componente de uma malha aparece **com cadeado** nas outras e só a malha que
a criou pode desfazê-la — e um pipeline só pode ser agendado pelo Início de uma
malha por vez.

### 1.4 Governança (aba ⚖)
- **Lineage**: para cada job, veja origens → transformação → destinos (tabelas, arquivos, colunas).
- **Catálogo**: busque qualquer tabela/arquivo, veja quais pipelines o produzem/consomem, classificação (PII, Confidencial...), dono (owner/steward) e tags.
- **Catálogo de pipelines**: o inventário que morava na tela Malha — cards por projeto, visão diagrama e exportação CSV.

### 1.5 Monitor DataStage (aba 🖥)
Fila e desempenho dos jobs DataStage: tempo em fila, duração, jobs filhos, histórico.

---

## 2. Perfil Operador

Tudo do Consulta, mais:

### 2.1 Executar um pipeline manualmente
1. Aba **Pipelines** → localize o pipeline (busca/filtros).
2. Clique em **▶ Executar agora**.
3. Acompanhe na aba Logs ou no Dashboard ("Executando agora").
> Execuções manuais **ignoram** calendário, blackout e filtro de horários — rodam imediatamente.

### 2.2 Reexecutar uma falha
1. Aba **Logs** → localize a execução com status `FAILED`.
2. Abra o detalhe, analise o log do job que falhou.
3. Use **Reexecutar** para disparar nova execução.

### 2.3 Alertas de SLA (Teams)
O monitor de SLA roda a cada 5 minutos e envia card no canal do Teams quando:
- **RISCO**: execução já consumiu ≥ 80% do SLA definido.
- **ESTOURO**: SLA ultrapassado.
Cada alerta é enviado uma única vez por execução (sem spam).

### 2.4 Janelas de blackout
Na aba **Pipelines → Agendamento**, consulte as janelas de blackout cadastradas (períodos em que execuções agendadas são suprimidas — ex.: fechamento contábil, manutenção de infra).

---

## 3. Perfil Desenvolvedor ETL

Tudo do Operador, mais:

### 3.1 Cadastrar um pipeline (wizard)
Aba **Pipelines → + Novo pipeline**. O wizard tem etapas:
1. **Identificação**: nome (padrão do projeto), projeto, domínio, descrição, tags.
2. **Classificação**: criticidade, SLA em minutos, ambiente, runbook.
3. **Agendamento** — tipos disponíveis:
   - **Diário** (hora:minuto), **Semanal** (dias da semana), **Mensal** (dia do mês), **De hora em hora**;
   - **Quinzenal**: escolha um dia de 1 a 15 — roda no dia D e no dia D+15 de cada mês;
   - **Horários específicos**: lista de horários exatos (ex.: 09:00, 10:30, 13:00...) + dias da semana (ex.: seg–sex). Ideal para cargas intradiárias;
   - Opções: **somente dias úteis**, **calendário** (feriados) e **dependência de
     outros pipelines** (§3.4) — esta última substitui o horário: o pipeline
     passa a ser disparado quando os antecessores concluem.
4. **Execução**: retries, retry delay, max active runs, pool.
5. **Jobs**: adicione os jobs com **ordem de execução**. Jobs com a **mesma ordem executam em paralelo**; a ordem seguinte só inicia quando todos da anterior terminam. Na edição, os jobs já cadastrados são carregados automaticamente. Remover uma linha aqui **não exclui** o job do banco — exclusão definitiva só na tela Jobs.
6. **Lineage** (opcional aqui; obrigatório se cadastrar pela tela Jobs).
7. **Revisão** → salvar. Depois clique em **Gerar DAG** para publicar no Airflow.

### 3.2 Gerenciar jobs (aba ⚙ Jobs)
- Cadastro/edição completa: tipo (`datastage`, `shell`, `python`, `storedproc`), comando, conexão SSH.
- **Reordenar** por arrastar-e-soltar.
- **Lineage obrigatório**: pelo menos 1 origem e 1 destino por job.
- **Extrair lineage do DSX**: para jobs DataStage, importe o `.dsx` e o sistema extrai origens/destinos automaticamente.

### 3.3 Importar sequence DataStage (.dsx)
Aba Pipelines → **Importar sequence**: faça upload do `.dsx`, revise o rascunho gerado (pipeline + jobs + ordem), ajuste e aprove. O ORQUESTRA cria tudo de uma vez.

### 3.4 Dependência entre pipelines

"PIPE_C depende de PIPE_A e PIPE_B" significa: C só roda depois que A **e** B
concluírem com sucesso **no mesmo dia de processamento** — e roda **em
segundos** após o último deles terminar, não no próximo horário cheio. Quem
depende de dois pipelines não é disparado pelo primeiro que termina; quem
dispara é o que **fecha a conta**.

#### As duas portas de cadastro (a mesma dependência)

1. **No cadastro do pipeline (wizard)** — passo **Agendamento**, botão
   **Escolher dependências** (ou **Editar dependências**). A escolha é feita
   numa lista com busca por nome e filtro por projeto — **não se digita nome
   livre**. Um pipeline **inativo** escolhido aparece com aviso: enquanto ele
   seguir assim, o dependente nunca será liberado. Uma escolha que criaria
   **ciclo** (A espera B que espera A) é bloqueada com a explicação na tela.
2. **Na tela Malha** — abra uma malha que contenha os dois pipelines e
   **desenhe a seta** entre eles no diagrama. Desenhar a aresta **é** cadastrar
   a dependência — ela é real e global, não um desenho: excluir a seta apaga a
   dependência de verdade (a tela pede confirmação), e a mesma aresta aparece
   em toda malha que contenha os dois pipelines.

Nas duas portas, a dependência é aplicada **na hora** — em edição, cancelar o
wizard depois não desfaz.

#### O horário deixa de valer; o DIA continua valendo

Com dependência, o pipeline **perde o horário próprio**: o gatilho passa a ser
a conclusão dos antecessores (os campos de hora ficam inertes na tela). Mas as
restrições de **dia** continuam valendo: dias da semana, dia do mês, somente
dias úteis e calendário de feriados seguem sendo respeitados — julgados pelo
**dia em que a malha rodou** (o "dia operacional", que os dependentes herdam
de quem os disparou), não pelo relógio da hora do disparo e não pelo rótulo da
data de referência. A diferença aparece nas cadeias com virada: com virada
20:00, o antecessor que conclui **sexta 21:00** carimba a data de referência de
**sábado** — mas o dia da malha é **sexta**, então um dependente "somente dias
úteis" **roda**. Um fechamento "todo dia 5" que depende de outro pipeline roda
quando o antecessor concluir **na malha do dia 5**.

#### Janela e hora-limite (bloco "Janela da liberação")

Dois campos opcionais aparecem junto das dependências:

- **Não iniciar antes de** — liberou às 07:10 mas o processo não deve começar
  antes das 08:00? Ele espera; o disparo sai na janela.
- **Avisar se não liberar até** — passou desse horário sem liberar, sai um
  alerta no Teams. **Não trava e não falha**: o pipeline fica pendente,
  aguardando — se o antecessor concluir depois, a corrida ainda roda.

#### Data de referência (ODATE — o dia de processamento)

Cada execução carrega uma **data de referência**: o dia de negócio a que ela
pertence, que não é necessariamente a data do relógio. É ela que define o que é
"a mesma corrida": um pipeline só é liberado quando **todas** as dependências
concluíram com sucesso **na mesma data de referência**. Sucesso de ontem não
libera a corrida de hoje. (Pipeline que roda várias vezes ao dia: vale a
pergunta "existe sucesso **nesta data**?" — as execuções extras não atrapalham.)

Por padrão, a data de referência é a data do calendário. Para cadeias que
**atravessam a meia-noite**, informe a **Hora de virada do dia (ODATE)** no
passo Agendamento: com virada às **20:00**, o que roda 31/07 às 23:30 e o que
roda 01/08 às 00:40 pertencem ambos ao dia **01/08** — e portanto conversam
entre si. O campo mostra ao lado a data que **seria** carimbada agora, para
conferência.

Quem é disparado por dependência **herda** a data de referência de quem o
disparou — não recalcula. É isso que mantém a corrida coerente quando ela cruza
a meia-noite.

#### A guardiã: o que os avisos significam

Uma rotina de vigilância (a cada 5 minutos) confere se alguma corrida ficou
presa e emite **eventos** — cada um com um significado e uma ação:

| Evento | O que aconteceu | O que fazer |
|---|---|---|
| **JANELA_ESTOUROU** | Passou do "Avisar se não liberar até" e a corrida não liberou | Verifique o antecessor que falta; o pipeline segue **pendente**, não falhado — liberou depois, roda |
| **DATA_DIVERGENTE** | Um antecessor concluiu com **outra** data de referência (o aviso cita as duas) | Quase sempre é virada de dia mal configurada — confira a Hora de virada dos dois pipelines |
| **PREDECESSOR_FALHOU** | Um antecessor **falhou** na data | Trate a falha do antecessor (§2.2); ao reprocessar, a cadeia anda sozinha |
| **NAO_LIBEROU** | O dia de processamento terminou sem a corrida liberar | A corrida foi **fechada** — não redispara sozinha; ver reprocesso abaixo |

**Onde ver:** na tela **Malha**, abra a malha e alterne para o modo
**Execução** — cada pipeline aparece colorido pelo status da data de referência
escolhida (aguardando dependência / executando / sucesso / falha / pulado / não
liberou), com os eventos da guardiã; no **Dashboard**, o painel **"Aguardando
dependência"** lista quem espera o quê ("esperando PIPE_B · data ref 01/08").
Os alertas também chegam como card no canal do Teams.

#### Reprocesso: como a cadeia anda de novo

- **Antecessor falhou?** Corrija a causa e reexecute a falha (§2.2 — Clear no
  Airflow ou Reexecutar na aba Logs). Quando ele terminar verde, **a cadeia é
  empurrada automaticamente**: os dependentes daquela mesma data de referência
  disparam sozinhos — não é preciso rodar um por um.
- **Corrida fechada como NAO_LIBEROU?** Ela não redispara sozinha (o dia dela
  acabou). Para rodá-la mesmo assim, dispare o pipeline manualmente
  **informando a data de referência**: no Airflow, *Trigger DAG w/ config* com
  `{"data_referencia": "AAAA-MM-DD"}`. O botão **▶ Executar agora** da tela
  dispara com a data de referência de **agora** (calculada pela virada).

#### Depois de mexer em dependência: republique

Criar ou remover dependência **muda a DAG** do dependente (o agendamento por
horário vira disparo por evento). Até republicar, a DAG no Airflow continua
rodando a **versão anterior** do cadastro — o pipeline fica com o badge âmbar
**"publicação pendente"** na aba Pipelines. Clique em **Publicar nova versão**
para atualizar. O badge some quando a publicação conclui.

### 3.5 Nó Aguarde (esperar duas pernas antes de seguir)

No editor de fluxo, arraste **Aguarde** (grupo *Fluxo* da paleta) quando um
passo só puder acontecer depois que **várias etapas paralelas** terminarem.

O caso clássico: dois processos rodam ao mesmo tempo usando os **mesmos arquivos
de trabalho**, e a remoção desses arquivos só é segura quando os dois acabaram.
Apagar antes corrompe quem ainda está lendo.

```
   ┌── Carga_Clientes ──┐
───┤                    ├── ▮ Aguarde ── Limpa_Arquivos
   └── Carga_Contratos ─┘
```

O nó é desenhado como uma **barra vertical**, atravessada no caminho: é o sinal
visual de que ali as pernas se encontram.

**Ele espera só quem está ligado nele.** O que não tiver uma linha chegando no
Aguarde não é esperado. Se você tem várias pontas soltas no fluxo e quer todas
esperando, use o botão **Prender as pontas soltas** no painel do nó — ele
desenha as ligações de uma vez, e elas ficam visíveis no canvas.

#### Escolher o que acontece quando uma perna falha

No painel do Aguarde há duas opções, e a diferença importa:

| Opção | Quando usar |
|---|---|
| **Só seguir se todas derem certo** (padrão) | O passo seguinte depende do resultado. Se qualquer perna falhar, ele não roda. |
| **Seguir assim que todas terminarem, mesmo com falha** | O passo seguinte é **limpeza**. Os arquivos temporários precisam sair do disco mesmo que uma das cargas tenha quebrado. |

⚠️ A segunda opção **não deixa o pipeline verde**. A etapa que falhou continua
marcada como falha, o alerta de erro sai normalmente e o pipeline termina em
erro. A única coisa que muda é que o passo seguinte ao Aguarde roda assim mesmo.
Se você está procurando um jeito de "fazer o pipeline passar", esta opção não é
isso — e nenhuma outra é.

#### Erros comuns

- **Aguarde sem nenhuma etapa ligada** — o fluxo não salva. Sem entrada, ele não
  tem o que esperar.
- **Aguarde com uma etapa só** — salva, mas aparece o aviso âmbar no nó: um ponto
  de encontro com uma perna só não junta nada.
- **Aguarde sem nada na saída** — salva, com aviso: ele não está segurando
  ninguém.

> **Depois de mexer no fluxo, republique o pipeline.** O desenho salvo só vira
> execução quando a DAG é gerada de novo.

### 3.6 Componentes de malha (Início · Aguarde · Notificação · Fim)

Na tela **Malha**, o diagrama de montagem tem uma paleta de **componentes** —
quatro peças que transformam o desenho da malha na "sequence mestre" que o
DataStage tinha: ondas de pipelines em paralelo, pontos de espera entre as
ondas, aviso no meio do caminho e a conclusão registrada no fim.

**Nenhum componente executa nada.** Eles são atalhos de desenho que viram as
peças que já existem: agendamento nas raízes, dependências reais entre
pipelines e avisos da guardiã. Quem roda continua sendo o scheduler do Airflow
e o disparo por dependência — por isso não existe um "motor da malha" para
quebrar.

O exemplo clássico (duas ondas com espera no meio):

```
            ┌── Carga_Clientes ──┐                      ┌── Relatorio_A ──┐
▶ Início ──┤                     ├── ▮ Aguarde ────────┤                  ├── ⚑ Fim
            └── Carga_Contratos ─┘        │             └── Relatorio_B ──┘
                                          └── 🔔 Notificação ("cargas ok")
```

| Componente | O que faz ao ser ligado |
|---|---|
| **▶ Início** | Guarda o agendamento **da malha** (um calendário só, com hora de virada única) e o copia para cada pipeline ligado a ele — as raízes. Todas disparam **no mesmo tick**, em paralelo. |
| **▮ Aguarde** | Ponto de espera entre ondas: cada saída passa a **depender de todo mundo que entra** — são dependências reais, criadas na hora (o efeito é mostrado **antes** de gravar). |
| **🔔 Notificação** | A guardiã avisa (painel + card no Teams) quando **todas as entradas tiverem SUCESSO no mesmo dia de processamento**. |
| **⚑ Fim** | Registra a **conclusão da malha** no dia: quando todos os ligados a ele tiverem SUCESSO, sai o evento e o modo Execução mostra o banner verde. O card no Teams é opcional (desligado por padrão). |

**A semântica é sempre "todas com sucesso"**: Aguarde, Notificação e Fim olham
para o mesmo critério — todas as entradas com SUCESSO **na mesma data de
referência**. Falha segura a malha e a guardiã alerta; não existe opção de
"seguir mesmo com falha" na malha.

#### Modo Execução: ler a malha rodando

O botão **Execução** abre a malha numa data de referência. Além das cores dos
pipelines, os componentes contam o dia:

- **Início** — como as raízes terminaram na data: `todas com sucesso (2)` em
  verde, `1 raiz com falha` em vermelho, `2 puladas` (regra de agenda barrou o
  dia — sábado, blackout), `1/2 com sucesso` ou `sem execução na data`. Verde
  só aparece quando **todas** deram certo. O tooltip abre o detalhe por status
  e mostra a próxima execução do agendamento (orientação — quem manda é o
  scheduler);
- **Aguarde** — **satisfeito** (verde: todas as entradas com sucesso),
  **aguardando** (âmbar: o tooltip diz quem falta) ou **bloqueado** (vermelho:
  o tooltip nomeia quem falhou);
- **Notificação** — "emitida às HH:MM" quando o aviso do dia saiu; senão
  "aguardando" — ou **"sem entradas — não emite"** se nenhum pipeline chega
  ao nó (aí ele nunca vai emitir: ligue as entradas);
- **Fim** — "concluída às HH:MM" + o banner verde no topo; senão "em
  andamento" (idem: "sem entradas — não conclui").

Componente sem dado na data fica **neutro** — a tela não inventa estado.

#### Disparar a malha manualmente

No modo Execução, o botão **▶ Disparar malha** roda a malha fora do horário
(reprocesso, teste, atraso do dia). Antes de qualquer coisa, a confirmação
mostra **o que será disparado**: as raízes ligadas ao Início, a data de
referência usada e o que o gesto atropela — raiz com a etiqueta **"tem
dependência"** (o disparo manual não espera o predecessor: a corrida parte por
cima dele) ou **"já rodou (N)"** (a raiz já tem corrida nessa data e vai rodar
de novo). Ao confirmar:

1. cada raiz é disparada no Airflow com a **mesma data de referência** — o
   mesmo gesto do botão "rodar" da tela Pipelines, uma vez por raiz;
2. o restante da malha anda **sozinho**, pelo disparo por dependência,
   herdando a data — ninguém precisa disparar o meio da cadeia;
3. quem disparou fica registrado na corrida (coluna "disparado por");
4. erros são reportados **por raiz** — uma raiz recusada não impede as outras.

Requer a permissão **Executar** (a mesma do botão de rodar pipeline).

#### Erros comuns

- **"raiz não pode ter dependência"** — quem tem dependência não é raiz: o
  motor espera o predecessor e o agendamento plantado seria mentira. Chegue a
  esse pipeline por um Aguarde.
- **"já é agendado pelo Início da malha X"** — um pipeline só tem **um** dono
  de agendamento por vez. Desligue-o na malha dona antes.
- **Desligar uma raiz do Início** deixa o pipeline **sob demanda** — nunca
  devolve o agendamento antigo. Reagendar é gesto seu, consciente.
- **"compilada pelo Aguarde X da malha M"** — dependência criada por um
  Aguarde só se edita pelo desenho da malha dona (a aresta aparece com
  cadeado nas outras).
- **Notificação/Fim sem entradas** — não avaliam nada e não emitem nada (o
  aviso âmbar fica no banner até você ligar as entradas).

> **Depois de mexer nos componentes, republique os pipelines afetados.** O
> modal de cada gesto lista quem precisa (`Republicação necessária`) — sem
> republicar, a DAG continua com o agendamento/dependência antigos.

---

## 4. Perfil Administrador

Tudo dos demais, mais a aba **Admin** (visível apenas para administradores):

### 4.1 Configurações da aplicação
Chave/valor em `etl_app_config` (ex.: URL do webhook Teams, parâmetros de monitor). Alterações valem sem redeploy.

### 4.2 Tipos de job
CRUD dos tipos de job aceitos no cadastro (nome, descrição, lineage habilitado, status).

### 4.3 Manutenção de DAGs
- **Regenerar todos os DAGs**: reconstrói os arquivos em `dags/generated/` a partir do banco (use após migrations ou correções no factory).
- **Excluir pipeline**: remove pipeline + jobs + DAG gerado. **Irreversível** — confira duas vezes.

### 4.4 Calendários e blackout
- **Calendários** (ex.: feriados nacionais/ANBIMA): cadastre datas; pipelines vinculados não rodam nessas datas.
- **Blackout**: janelas início/fim em que execuções agendadas são suprimidas globalmente ou por pipeline.

### 4.5 Usuários & Perfis (Admin → 👤 Usuários & Perfis)
- **Usuários**: lista quem já acessou (matrícula, nome — preenchido automaticamente com os dados do Airflow no 1º login —, perfil, último login). Altere o perfil pelo formulário; mudar o perfil derruba as sessões ativas do usuário (ele só precisa logar de novo). Remover um usuário faz com que ele volte ao perfil `consulta` se logar novamente.
- **Perfis**: marque por checkbox quais telas (Dashboard, Pipelines, Jobs, Logs, DS Monitor, Governança, Malha, Admin) e ações (Executar, Cadastrar/Editar, Administração) cada perfil possui. Crie perfis novos se precisar (ex.: `auditoria`). Os perfis `admin` e `consulta` são protegidos contra exclusão, e o `admin` nunca perde a permissão de administração.
- O TTL da sessão é configurável pela chave `session_ttl_hours` em Admin → Configurações.

### 4.6 Rotina de deploy (servidor air-gapped)
```bash
cd /opt/airflow && git pull
# se houver migration nova:
sqlcmd -S SQL14 -d DMDB41 -i sql/migrations/0XX_*.sql
docker compose build orquestra-api && docker compose up -d --no-deps orquestra-api
docker compose restart ui-nginx
# se o factory mudou: Admin → Regenerar todos os DAGs
```
Lembretes:
- Segredos só em `/opt/airflow/.env` (nunca no Git).
- Dependências novas chegam via Git (`wheels/`), nunca via pip/internet no servidor.

---

## 5. Perguntas frequentes

**O pipeline não rodou no horário. Por quê?** Verifique, nesta ordem: (1) pipeline ativo? (2) data está num calendário de feriado ou blackout? (3) tipo "horários específicos": o horário consta na lista? (4) DAG gerado/atualizado após a última edição? (5) DAG despausado no Airflow?

**Editei o pipeline e nada mudou.** Edições de agendamento exigem **Gerar DAG** novamente.

**Jobs em paralelo não rodam juntos.** Confirme que têm exatamente a mesma ordem de execução e que há workers Celery disponíveis.

**Execução manual rodou em feriado.** Comportamento esperado: execuções manuais ignoram calendário/blackout/horários.

**Não vejo a aba Admin (ou outra aba).** Seu perfil não tem acesso a essa tela — solicite ao administrador em Admin → Usuários & Perfis.

**Apertei F5 e continuei logado — é normal?** Sim. A sessão usa um token salvo no navegador (a senha nunca fica armazenada) e expira automaticamente após o período configurado (padrão 12h). Para encerrar antes, use Sair.
