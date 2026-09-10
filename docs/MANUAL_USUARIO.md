# ORQUESTRA — Manual de Utilização por Perfil

> Versão do produto: v2.3.0 · Acesso: `http://<servidor>` na rede corporativa
> Login: **matrícula e senha de rede** (as mesmas do Airflow). Sem acesso? Solicite ao administrador.

---

## Perfis de acesso

| Perfil | Quem é | O que pode fazer |
|---|---|---|
| **Consulta** | Analistas, gestores, auditoria | Visualizar Dashboard, Logs, Malha, Governança (lineage, catálogo e **Job DataStage**) e Monitor DataStage |
| **Operador** | Operação/Sustentação ETL | Tudo do Consulta + executar pipelines manualmente, reexecutar falhas, acompanhar SLA, **ver arquivos do servidor do DataStage** (Utilitários) |
| **Desenvolvedor ETL** | Equipe de engenharia de dados | Tudo do Operador + cadastrar/editar pipelines, jobs, lineage, agendamentos, importar sequences DSX, **criar e editar arquivos no servidor** (Utilitários), **extrair o lineage direto do DataStage** (Governança › Job DataStage) |
| **Administrador** | Responsável pela plataforma | Tudo + aba Admin: configurações, tipos de job, regenerar DAGs, excluir pipelines, calendários/blackout, **diretórios e extensões dos Utilitários**, **lote do lineage DataStage** |

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

**Republicar os pipelines da malha.** Desenhar uma seta, ligar um Aguarde ou
salvar o agendamento do Início grava a mudança na hora, mas **a DAG que o
Airflow executa continua sendo a versão anterior até ser gerada de novo**. Os
pipelines nessa situação ganham o chip âmbar **⟳ republicar** no card do
diagrama, e o botão **Republicar pipelines** (barra do modo Montagem) mostra
quantos são. Ao clicar, uma janela lista o que será publicado antes de
qualquer coisa acontecer:

- **primeira publicação** — o pipeline ainda não tem DAG no Airflow;
- **desatualizada** — o cadastro mudou depois da última publicação;
- **fora desta publicação** — pipelines **inativos**, que o gerador de DAGs não
  aceita: ative-os e republique para que recebam os vínculos.

Confirmar dispara o **gerador de DAGs** (o mesmo do botão *Publicar nova
versão* da tela Pipelines, uma vez para a malha inteira). Leva de alguns
segundos a poucos minutos; o andamento e os erros de cada pipeline ficam na
tela de **Publicação**. As corridas em andamento não são interrompidas —
a nova versão vale a partir da próxima execução. A janela também avisa quando
há pipelines **de fora da malha** pendentes de publicação: eles entram na
mesma execução do gerador, que é como ele sempre funcionou.

### 1.4 Governança (aba ⚖)
- **Lineage**: para cada job, veja origens → transformação → destinos (tabelas, arquivos, colunas).
- **Catálogo**: busque qualquer tabela/arquivo, veja quais pipelines o produzem/consomem, classificação (PII, Confidencial...), dono (owner/steward) e tags.
- **Catálogo de pipelines**: o inventário que morava na tela Malha — cards por projeto, visão diagrama e exportação CSV.
- **Job DataStage**: o lineage que o Orquestra extrai **sozinho** do DataStage (export ISX do próprio job): por job, o grafo dos stages, o SQL completo de cada origem e destino, as colunas, as expressões do Transformer e, nas sequences, os jobs chamados. Consulta livre para quem tem a tela; **extrair** é do Desenvolvedor ETL (§3.9).

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

**Reexecutar a partir de uma etapa, trocando um parâmetro (Fluxos › painel da
etapa › Reexecutar a partir daqui).** Quando as etapas DataStage que vão rodar
de novo têm parâmetros (§3.10), o modal mostra a seção **Parâmetros desta
reexecução**: para cada parâmetro, o **valor que iria ao DataStage** na data de
referência da corrida (com o cálculo por extenso, ex.: *referência 2026-09-09 →
-1 mês → fim do mês → 2026-08-31*) e um campo **Novo valor (só agora)**.
- O que você digitar vale **só nesta reexecução**; a corrida agendada seguinte
  volta ao cadastro. Deixe em branco para manter.
- Parâmetro **Encrypted** não se sobrepõe (aparece `***`, sem campo).
- Um default do pipeline aparece com "(se o job declarar)": se o job não
  declarar esse nome, a etapa falha antes de disparar, listando o que o job
  declara.
- Se uma reexecução anterior desta mesma corrida já tinha sobreposto algo, o
  modal avisa: **esses valores são descartados** pela nova reexecução — digite de
  novo o que quiser manter.
- O que foi enviado fica no detalhe da execução (bloco **Parâmetros enviados ao
  DataStage**, fonte *reexecução*) e no log da task.

### 2.3 Alertas de SLA (Teams)
O monitor de SLA roda a cada 5 minutos e envia card no canal do Teams quando:
- **RISCO**: execução já consumiu ≥ 80% do SLA definido.
- **ESTOURO**: SLA ultrapassado.
Cada alerta é enviado uma única vez por execução (sem spam).

### 2.4 Janelas de blackout
Na aba **Pipelines → Agendamento**, consulte as janelas de blackout cadastradas (períodos em que execuções agendadas são suprimidas — ex.: fechamento contábil, manutenção de infra).

### 2.5 Utilitários — ver um arquivo do servidor do DataStage
Menu **Operação → Utilitários**, aba **Ver arquivo**. Serve para ler um `.param`,
um log ou um arquivo de carga que está no servidor do DataStage, sem acesso SSH.
Só funciona **abaixo dos diretórios que o administrador liberou** (§4.7); a
tela avisa "Nenhum diretório liberado ainda" enquanto não houver nenhum.

1. **Servidor**: hoje só o Servidor DataStage.
2. **Pasta**: caminho absoluto no servidor (ex.: `/dados/bi/2026`). Ao digitar,
   o campo já diz *abaixo de /dados/bi* ou avisa em vermelho **Fora dos
   diretórios liberados** — nesse caso nem adianta clicar, o servidor vai negar.
   Sem saber o caminho, use **Navegar…** (abaixo).
3. **Nome do arquivo**: com a extensão (ex.: `parametros_carga.param`).
4. **Últimas N linhas** (opcional): para log grande, traz só o fim do arquivo.
5. **Iniciar**: abre o modal, que passa por *conectando* → *lendo* → conteúdo.

No modal: o conteúdo inteiro em fonte mono, rodapé com **linhas, tamanho,
codificação** (`utf-8` ou `latin-1`, detectada) e a data de modificação, e o
botão **Copiar conteúdo** — que diz *copiado*, *use Ctrl+C* (o texto já fica
selecionado: basta teclar Ctrl+C) ou *não copiou*.

**Baixar** (ao lado de Copiar) salva o arquivo inteiro no seu computador, como
está no servidor — vale também para **binários** e para arquivos acima do teto
de leitura: quando o Ver arquivo recusa com "não é texto" ou "acima do teto",
o próprio modal oferece **Baixar o arquivo**. O download vai até **50 MB**;
acima disso a resposta é "acima do teto de download". Uma faixa no canto
inferior direito mostra *conectando* → *baixando X de Y* → *baixado* (ou o
erro), um download por vez; o navegador salva com o nome do arquivo no
servidor (acentos preservados).

**Navegar…** (ao lado do campo Pasta) abre o navegador de pastas: a primeira
tela lista as raízes liberadas (com uma só, já abre nela); clique numa pasta
para descer, **Subir** ou **Backspace** para voltar (nunca acima da raiz), a
trilha no topo leva a qualquer nível. **Usar esta pasta** preenche o campo
Pasta; clicar num **arquivo** preenche pasta e nome, e o **ícone de download**
na ponta da linha baixa aquele arquivo sem fechar o navegador (dá para baixar
vários em sequência). Arquivos e pastas ocultos (nome começando com `.`) ficam
escondidos — ligue *mostrar ocultos* se precisar. Um link que aponta para fora
dos diretórios liberados aparece apagado, sem abrir.

Mensagens que você pode ver e o que fazem:

| Mensagem | O que significa |
|---|---|
| **Fora dos diretórios liberados.** | O caminho não está abaixo de nenhuma raiz cadastrada (inclusive quando passa por um link que sai da raiz). Peça ao administrador para liberar a pasta. |
| **Arquivo não encontrado: /…** | O caminho não existe no servidor. Confira maiúsculas e minúsculas — o servidor distingue. |
| **O usuário SSH não tem permissão para acessar /…** | A conta que o Orquestra usa no servidor não lê essa pasta ou arquivo. |
| **O arquivo não é texto (parece binário) — os Utilitários só abrem texto.** | Imagem, zip, executável: a tela não mostra. |
| **Arquivo de X, acima do teto de Y.** | Maior que o teto configurado pelo administrador. O modal oferece o campo **últimas N linhas** — informe (ex.: 200) e clique em **Ver o fim do arquivo**. |
| **O servidor não respondeu em 90 s.** / **Servidor não configurado nesta instância da API…** | O servidor demorou demais ou a API não tem as credenciais SSH; acione a sustentação. |

> Toda leitura, listagem e gravação fica registrada com sua matrícula, o
> caminho e o resultado (auditoria). O conteúdo do arquivo **não** é gravado.

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
4. **Execução**: retries, retry delay, max active runs, pool — e **Parâmetros
   DataStage do pipeline** (opcional): defaults com o mesmo vocabulário da etapa
   (§3.10), enviados a **toda etapa DataStage cujo job declarar o nome**; job que
   não declara ignora (o nome sai como *ignorado* no log da task). A etapa pode
   sobrepor pelo mesmo nome. Não exige republicar a DAG: o operador lê em runtime.
   O **Maestro** (§3.11) fica nesta seção também: descreva o cenário e ele propõe
   os defaults dizendo quais etapas vão herdá-los — ou pergunte como a herança
   funciona.
5. **Jobs**: adicione os jobs com **ordem de execução**. Jobs com a **mesma ordem executam em paralelo**; a ordem seguinte só inicia quando todos da anterior terminam. Na edição, os jobs já cadastrados são carregados automaticamente. Remover uma linha aqui **não exclui** o job do banco — exclusão definitiva só na tela Jobs.
6. **Lineage** (opcional aqui; obrigatório se cadastrar pela tela Jobs).
7. **Revisão** → salvar. Depois clique em **Gerar DAG** para publicar no Airflow.

### 3.2 Gerenciar jobs (aba ⚙ Jobs)
- Cadastro/edição completa: tipo (`datastage`, `shell`, `python`, `storedproc`), comando, conexão SSH.
- **Parâmetros do job** (etapa `datastage`): o que vai no `-param` do DataStage a cada execução — §3.10. O mesmo editor existe no painel da etapa em **Fluxos**.
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

### 3.7 Utilitários — criar ou editar um arquivo no servidor
Menu **Operação → Utilitários**, aba **Criar/editar arquivo**. Quem só lê
(operador) vê o editor desabilitado com a explicação; desenvolvedor e
administrador gravam. Só abaixo dos diretórios liberados e só com as
**extensões que o administrador liberou** (§4.7).

1. **Pasta**: como na aba Ver arquivo (ou **Navegar…**). A pasta precisa
   existir — a tela não cria pastas.
2. **Nome do arquivo (sem a extensão)** e **Extensão** (lista do admin). Colar
   `carga.sql` no nome separa a extensão sozinho. Pelo navegador, o clique num
   arquivo preenche os dois.
3. **Codificação**: `UTF-8` ou `Latin-1` (o servidor do DataStage costuma usar
   Latin-1). Em Latin-1, um caractere que não existe nela (ex.: `€`, emoji)
   desliga o Gravar e diz a linha e o caractere.
4. **Carregar existente**: traz o conteúdo do arquivo que já existe e troca a
   codificação para a detectada — gravar de volta mantém os bytes.
5. **Conteúdo**: editor em fonte mono com contador de linhas e bytes; *não
   gravado* aparece enquanto houver texto por gravar. **Ctrl+Enter** grava
   (Enter no nome ou na pasta não grava nada).
6. **Gravar**: abre o modal com o resultado — caminho, criado ou sobrescrito,
   tamanho, linhas, codificação, hash SHA-256 e a cópia de segurança — e o botão
   **Ver arquivo**, que abre o conteúdo gravado.

**Quando o arquivo já existe**, o modal mostra tamanho e data do atual e pede
**Sobrescrever**. Ao confirmar, o original vira `nome.ext.bak-<data-hora>` na
mesma pasta (se a cópia de segurança estiver ligada no Admin) e o novo entra
de uma vez — um job que leia no meio vê o antigo ou o novo, nunca meio arquivo.
As permissões do arquivo são preservadas; o dono passa a ser a conta SSH do
Orquestra.

O que a gravação faz com o texto: quebras de linha do Windows (CRLF) viram LF
e o arquivo termina com quebra de linha.

Mensagens que você pode ver:

| Mensagem | O que significa |
|---|---|
| **Seu perfil só lê…** | Sem a permissão de cadastrar/editar; peça ao administrador. |
| **Nenhuma extensão liberada** / **Extensão não liberada.** | O admin não incluiu essa extensão em Admin › Utilitários. |
| **Caractere fora do Latin-1 na linha N (…)** | Troque o caractere ou grave em UTF-8. |
| **O arquivo já existe. Confirme para gravar por cima.** | Escolha Sobrescrever ou Cancelar. |
| **O servidor recusou gravar em /…: o sistema de arquivos está montado somente leitura.** | A pasta é de uma montagem sem escrita; escolha outra pasta ou acione a sustentação. |
| **… não há espaço livre no disco.** | Disco cheio no servidor. |
| **O usuário SSH não tem permissão para gravar em /…** | A conta do Orquestra não escreve nessa pasta. |
| **Conteúdo de X, acima do teto de Y.** | O texto passa do teto por arquivo; divida o arquivo ou peça ao admin para subir o teto. |
| **"NOME" não segue o padrão nome + extensão em minúscula…** | O navegador escolheu um arquivo que o editor não consegue gravar (extensão maiúscula, sem extensão, espaço na ponta). Veja pela aba Ver arquivo ou renomeie no servidor. |

Trocar de aba com texto por gravar pergunta antes de descartar.

### 3.8 Utilitários — enviar um arquivo do seu computador para o servidor
Menu **Operação → Utilitários**, aba **Enviar arquivo**. Para levar ao servidor
do DataStage um arquivo que está na sua máquina — uma planilha de parâmetros,
um `.dsx` exportado, um arquivo de carga — sem cliente SFTP. Mesma permissão
da gravação: quem só lê vê o formulário desabilitado. Só abaixo dos
diretórios liberados e só com **extensão da lista do administrador** (§4.7);
o conteúdo pode ser **binário**.

1. **Pasta**: como nas outras abas (ou **Navegar…**). Precisa existir.
2. **Escolher arquivo…**: abre o seletor do seu computador. Ao lado aparece o
   nome e o tamanho escolhidos; o teto é **50 MB** por envio.
3. **Nome no servidor**: começa igual ao nome do arquivo escolhido e fica como
   você digitar (maiúsculas e espaços inclusive); só a **última** extensão
   precisa estar na lista, comparada em minúsculas (`RELATORIO.TXT` entra com
   `txt` liberada; `README`, sem extensão, não entra). Pelo navegador, clicar
   num arquivo existente preenche pasta e nome — é o jeito de "ir por cima"
   daquele arquivo.
4. **Enviar**: abre o modal com a **barra de progresso** e o botão
   **Cancelar**. Enter num campo não envia nada.

**Quando o arquivo já existe**, o modal mostra tamanho e data do atual e pede
**Sobrescrever** — o mesmo arquivo sobe de novo; o original vira
`nome.ext.bak-<data-hora>` na mesma pasta (se a cópia de segurança estiver
ligada no Admin), o novo entra de uma vez e as permissões do arquivo são
preservadas. Um arquivo **novo** nasce sem permissão de execução.

**Cancelar** só vale enquanto o arquivo está subindo. Assim que ele chega
inteiro, o botão some e o modal diz *gravando… aguarde*: nessa fase o servidor
vai gravar de qualquer forma, e fechar o modal (X, Esc ou clique fora) não
interrompe nada — a resposta chega em segundos (até 4 minutos numa gravação
muito lenta). Se você cancelou antes disso, nada foi gravado.

Ao terminar: caminho real, criado ou sobrescrito, tamanho, hash SHA-256 e a
cópia de segurança.

Mensagens que você pode ver:

| Mensagem | O que significa |
|---|---|
| **Extensão X não está na lista do admin.** / **Arquivo sem extensão** | Só entram extensões liberadas em Admin › Utilitários; renomeie ou peça a inclusão. |
| **Arquivo de X, acima do teto de 50,0 MB para envio.** | Divida o arquivo ou envie por outro meio; o teto é fixo. |
| **O arquivo já existe. Confirme para gravar por cima.** | Escolha Sobrescrever ou Cancelar. |
| **O servidor recusou gravar em /…: o sistema de arquivos está montado somente leitura.** | A pasta é de uma montagem sem escrita; escolha outra pasta. |
| **O usuário SSH não tem permissão para gravar em /…** | A conta do Orquestra não escreve nessa pasta (ou não pode substituir um arquivo de outro dono). |
| **Há transferências em andamento — tente de novo em instantes.** | Duas transferências ao mesmo tempo por instância da API; espere uma terminar. |
| **O envio parou no meio** / **O envio chegou incompleto** | A conexão caiu durante o envio; envie de novo. |
| **O servidor não respondeu a tempo. Confira na pasta antes de reenviar…** | A gravação pode ter terminado depois da resposta: veja pela aba Ver arquivo ou pelo navegador antes de mandar de novo. |
| **O envio foi cancelado, mas o arquivo já tinha chegado inteiro…** | Você cancelou depois de o arquivo subir; confira na pasta — ele pode ter sido gravado. |

### 3.9 Lineage automático do job DataStage (Governança › Job DataStage)
Até aqui o lineage de um job DataStage vinha de um `.dsx` exportado à mão (§3.2) ou
do cadastro manual — e ficava defasado do job em produção. A aba **Job DataStage**
faz o Orquestra **exportar o job por conta própria** (o `istool` do Information
Server, formato ISX, via SSH no servidor do DataStage), ler a definição e gravar
por stage o **SQL completo**, o banco/DSN, o caminho do arquivo, as **colunas com
tipo e tamanho**, as **expressões coluna a coluna** do Transformer, o código APT e o
**fluxo** entre os stages.

**Regra da casa: job só com pipeline.** A extração vale para um job que já está
mapeado num pipeline do Orquestra (aba ⚙ Jobs), e o projeto do DataStage é o
`project_name` cadastrado no pipeline. Job fora de pipeline não se extrai — mapeie
primeiro. O nome do job é **exatamente** o do DataStage (maiúsculas e minúsculas
contam lá).

**Passo a passo**
1. Governança → aba **Job DataStage**. Escolha o pipeline (a lista sugere os
   cadastrados) e clique **Carregar**. O cabeçalho mostra o projeto DataStage, quantos
   jobs o pipeline tem e quantos já têm lineage ISX.
2. A lista à esquerda traz cada job com o estado: **extraído** (data e quem extraiu),
   **não extraído**, **erro** (a frase da última tentativa) ou **não é job DataStage**
   (nós http, decisão, shell… não existem no DataStage e ficam sem botão).
3. Clique **Extrair** no job (ou **Atualizar**, quando já há lineage). A tela mostra
   *Extraindo … do DataStage… (istool, até 60 s)* — normalmente leva de 3 a 10 s. Uma
   extração por vez na tela. Duas extrações simultâneas do mesmo job (dois usuários, ou
   você e o lote) rodam dois istool e a última a gravar vence; só se as gravações
   coincidirem a segunda responde *Outra extração … em andamento*.
4. Com o lineage carregado aparecem, de cima para baixo:
   - **Cabeçalho**: projeto, pasta no DataStage, tipo (PARALLEL/SEQUENCE), última
     modificação no DataStage, extraído em/por, duração e tamanho do `.isx`,
     descrição (a longa fica recolhida em *Ver descrição completa*) e o badge
     **dados do cache** ou **extraído agora do DataStage**.
   - **Grafo**: um nó por stage, colorido pela direção — **origem** (verde),
     **transformação** (azul), **destino** (âmbar) — e as setas com o nome do link.
     Clique (ou Enter) no nó para abrir o painel do stage. Zoom e deslocamento
     (arrastar o fundo) como no editor de fluxo; os nós não se movem.
   - **Tabela de stages**: nome, tipo, direção, banco/arquivo (DSN, tabela ou arquivo)
     e a contagem de colunas; clicar na linha abre o mesmo painel.
   - **Painel do stage** (lateral): o SQL/consulta completo, banco/DSN, arquivo,
     colunas de saída e de entrada com tipo e tamanho, as expressões
     `saída ← expressão (origem)` e o código APT (recolhido). Parâmetros do job
     (`#PSet.Param#`) viram um badge com a explicação — o valor real só existe em
     tempo de execução.
5. **Sequence**: além do grafo e da tabela (as atividades são os stages), a seção
   *Jobs chamados por esta sequence* lista os jobs chamados. Filho mapeado no mesmo
   pipeline vira link (abre o job) e ganha o seu
   **Extrair**; filho de fora aparece marcado *(fora deste pipeline)* — só informado,
   pela regra acima.

**Cache.** A extração só roda o `istool` quando o job **mudou no DataStage** (a data
de modificação que a API REST do DataStage informa é a chave). Sem mudança, a
resposta vem do banco em menos de um segundo com o badge *dados do cache*.
**Atualizar** força a reextração mesmo sem mudança.

**Convivência com o lineage antigo.** As linhas cadastradas à mão ou vindas do `.dsx`
continuam no banco; reextrair só substitui as linhas ISX do job. A aba **Lineage**
passa a mostrar o lineage ISX quando ele existe para o job (senão, o que havia).

**Mensagens que você pode ver**

| Mensagem | O que significa / o que fazer |
|---|---|
| **O job … não está mapeado no pipeline …** | Regra *job só com pipeline*: mapeie o job na aba ⚙ Jobs do pipeline e tente de novo. |
| **O pipeline … não tem projeto DataStage (project_name) cadastrado.** | Edite o pipeline e informe o projeto do DataStage. |
| **O nó … é do tipo …, não um job DataStage** | Só jobs `datastage` têm ISX. |
| **Job … não encontrado no projeto … do DataStage (a API REST não o acha em nenhuma pasta de Jobs).** | Nome com caixa diferente, job em outro projeto, ou apagado/renomeado no DataStage. |
| **Job não encontrado no repositório do DataStage pelo istool — confira projeto, pasta e nome.** | A API REST achou o job, mas o export não: o job foi movido ou renomeado entre a busca e o export, ou a pasta tem um nome que o istool não aceita. |
| **Outra extração do job … está em andamento — tente de novo em instantes.** | Alguém (ou o lote do admin) está extraindo o mesmo job; espere terminar. |
| **A extração não terminou em 60 s — tente de novo.** | O servidor do DataStage está lento. O cabeçalho fica com *erro* e o resultado tardio é descartado; quando o servidor aliviar, clique **Atualizar** de novo — o lineage anterior (se havia) continua visível. |
| **Lineage ISX não configurado nesta instância da API — defina …** e outros *503* | O lineage ISX não está configurado nesta instalação — chame o administrador (§4.8). |
| **N stage(s) com tipo fora do mapa: …** | Aviso no cabeçalho: o parser não classificou esses tipos de stage; o lineage do resto está completo. O administrador inclui o tipo no mapa (§4.8) e você clica **Atualizar**. |
| **… — os dados abaixo são da última extração que deu certo.** | A última tentativa falhou (a frase diz por quê), mas o lineage anterior continua válido e visível. |

> Caminhos e nomes com acento fora da collation do banco podem aparecer com `?` na
> tabela de stages (limitação das colunas atuais); o caso fica anotado no aviso de
> não reconhecidos.

---

### 3.10 Parâmetros dos jobs DataStage (o `-param` a cada execução)
Até esta versão o Orquestra disparava o job DataStage **sem nenhum parâmetro**: o
job rodava com os defaults do design e do Parameter Set. Agora a etapa `datastage`
(tela **Etapas**, modal da etapa; ou **Fluxos**, painel do nó) tem a seção
**Parâmetros do job (opcional)**, e o operador do Orquestra envia cada um como
`-param nome=valor` no `dsjob -run`.

**Cada parâmetro tem:**
- **Nome** — exatamente como o job declara (o DataStage distingue maiúsculas de
  minúsculas). Membro de Parameter Set: `PSet.Param`.
- **Tipo** — o do DataStage: String, Integer, Float, Date, Time, Timestamp,
  Pathname (caminho absoluto), List ou **Encrypted**.
- **Origem** — de onde vem o valor a cada execução:
  - **Valor fixo**: o que você digitar.
  - **Data de referência**: o ODATE da corrida (a mesma data que rege a malha e
    as dependências, §1.3). É a origem recomendada para datas.
  - **Data lógica (Airflow)** e **Data da execução** (relógio do disparo).
  - **Run id da corrida**: o identificador da corrida no Airflow (rastreabilidade).
- **Cálculo** (só nas origens de data), sempre nesta ordem: **meses → âncora →
  dias → formato**. O deslocamento em meses trunca o dia ao último válido
  (31/03 −1 mês = 28/02); a âncora leva ao início/fim do mês, trimestre, ano ou
  semana (seg–dom); o formato é o do `strftime` (`%Y-%m-%d`, `%Y%m%d`,
  `%d/%m/%Y`…).

| Caso | Meses | Âncora | Dias | Formato | Com referência 2026-09-09 |
|------|------:|--------|-----:|---------|---------------------------|
| Primeiro dia do mês anterior | −1 | início do mês | 0 | `%Y-%m-%d` | 2026-08-01 |
| Último dia do mês anterior | −1 | fim do mês | 0 | `%Y-%m-%d` | 2026-08-31 |
| D−1 compacto | 0 | — | −1 | `%Y%m%d` | 20260908 |
| Ano-mês de referência | 0 | — | 0 | `%Y%m` | 202609 |

A coluna **Prévia** mostra o valor que iria ao DataStage com a data de
**Simular com a referência** (padrão: hoje) — use 31/03 ou 29/02 para conferir
bordas antes de salvar. A prévia é calculada pelo servidor, pela mesma rotina
que roda no disparo.

**Importar do DataStage.** Se o job já tem lineage ISX extraído (§3.9), o botão
lê os parâmetros que o job **declara** e acrescenta os que faltam na lista, com
tipo e default como valor fixo — confira valor e origem antes de salvar. Um
Parameter Set aparece só como conjunto no ISX: cadastre os membros como
`PSet.Param`. Nomes fora da regra do Orquestra (ex.: variáveis `$APT_…` que o
job declara como parâmetro) são ignorados, e o aviso os lista. Sem lineage
extraído, o botão orienta a extrair primeiro; se a última extração falhou, ele
avisa e não importa nada (reextraia antes). O botão aparece na etapa já salva.

**Encrypted.** O valor é cifrado no banco (a mesma chave das conexões) e nunca
aparece em log ou tela; o campo mostra *mantido — digite para trocar*. Vazio com
valor gravado = manter. ⚠️ Use Encrypted no Orquestra **só para parâmetro
Encrypted no job**: o DataStage grava os parâmetros recebidos no log do job e só
mascara os que forem Encrypted no Designer — um Encrypted enviado a um parâmetro
String do job aparece em claro no `dsjob -logsum`.

**Defaults do pipeline.** Cadastrados no wizard do pipeline (§3.1, passo
Execução), valem para toda etapa DataStage cujo job declarar o nome; a etapa
sobrepõe pelo mesmo nome. O painel da etapa mostra *Defaults do pipeline: … ·
sobreposto pela etapa*.

**O que acontece no disparo.** Com parâmetro cadastrado (na etapa ou no
pipeline), o operador consulta `dsjob -lparams` e:
- parâmetro **da etapa** que o job não declara → a etapa **falha antes de
  disparar**, listando o que o job declara (confira a grafia);
- default **do pipeline** que o job não declara → ignorado e listado no log;
- data de referência indisponível (corrida sem registro) → falha antes de
  disparar, nunca "a data de hoje";
- sem banco → falha antes de disparar, nunca "sem os parâmetros".
Sem parâmetro cadastrado, o comando é exatamente o de sempre.

**Rastro.** O que foi enviado fica em três lugares, sempre com o mesmo texto: a
linha `[DS] parâmetros:` no log da task (nome=valor, fonte e o cálculo por
extenso), o bloco **Parâmetros enviados ao DataStage** no detalhe da execução
(Logs › log DataStage) e a coluna `params_json` de `etl_ds_job_log`. Encrypted
aparece sempre como `***`.

Para preencher tudo isso sem decorar o vocabulário, descreva o cenário ao
**Maestro** (§3.11) — ele propõe as linhas e você aplica no editor.

### 3.11 Maestro — o assistente de parâmetros (Etapas e Fluxos)
O **Maestro** é um chat que ajuda a preencher os parâmetros do §3.10 sem decorar
o vocabulário: você descreve o cenário e ele diz como preencher cada campo. O
botão com o avatar (um regente conduzindo as linhas do pipeline) fica em três
lugares: na seção **Parâmetros do job** da etapa `datastage`, ao lado de
*Importar do DataStage* — na tela **Etapas** e no painel do nó em **Fluxos** —
e na seção **Parâmetros DataStage do pipeline** do cadastro do pipeline (§3.1,
passo Execução). Ele só aparece quando o administrador liga o Maestro (§4.9) e o
provedor de IA está configurado.

**No pipeline, ele sabe que está cadastrando defaults.** O que ele propõe ali
vale para toda etapa DataStage cujo job declarar o nome, sem configurar nada nas
etapas; quando o pipeline já tem etapas com lineage ISX, o cartão da proposta
diz **quais etapas vão herdar** cada parâmetro e quais vão ignorá-lo (por não
declarar o nome), e avisa as que não têm lineage.

**Ele também explica.** Pergunte "se eu cadastrar no pipeline, todas as etapas
usam?", "as etapas herdam ou preciso configurar algo nelas?" ou "rodando todo
dia 05, ele manda o mês anterior?" — o Maestro responde com as regras do §3.10
(herança para quem declara o nome, sobreposição pela etapa, recálculo a cada
disparo pela data de referência da corrida, reexecução com a referência daquela
corrida, *Simular*, rastro) sem propor nada.

**Como usar.**
1. Abra o chat e descreva o cenário em português — por exemplo, *"carga mensal
   do mês anterior com data inicial e final"*. As sugestões de abertura são o
   primeiro exemplo dos **quatro primeiros cenários ativos** do catálogo (§4.9);
   os demais cenários o Maestro conhece, mas não sugere.
2. O Maestro responde explicando **campo a campo** (nome, tipo, origem, meses,
   âncora, dias, formato ou valor) e mostra um **cartão com a proposta**: cada
   parâmetro com a prévia *com a referência X* — a mesma data do *Simular com a
   referência* da seção. Se ele precisar de algo (os nomes dos parâmetros, por
   exemplo), pergunta antes de propor.
3. **Aplicar no editor** coloca as linhas na lista de parâmetros — o que já
   existia com o mesmo nome é substituído no lugar, o resto fica como está.
   Confira e **salve a etapa** (ou o pipeline): o Maestro nunca salva nada.

**O que ele sabe.** O vocabulário do §3.10 (tipos, origens, âncoras, a ordem
meses → âncora → dias → formato), o **catálogo de cenários** mantido pelo
administrador e, quando o job tem lineage ISX (§3.9), os parâmetros que o job
**declara** — ele usa esses nomes e avisa se propuser um que o job não declara.
Sem lineage, ele pede os nomes ou propõe nomes convencionais e avisa que
precisam ser iguais aos do Designer. Toda proposta passa pela **mesma régua do
salvar**: o que a régua recusa nunca chega ao botão *Aplicar*.

**Quando o cenário não existe.** Dias úteis, feriados, valor lido de tabela ou
arquivo, condições, qualquer coisa fora do catálogo e do vocabulário: o Maestro
diz que **não atende**, orienta a **procurar o administrador** e o pedido fica
registrado — o administrador vê a lista em Admin › Maestro › *Pedidos não
atendidos* (§4.9) e decide se cria o cenário.

**Encrypted e o que sai da tela.** O Maestro nunca pede nem repete senhas: para
um parâmetro Encrypted ele propõe a linha **sem valor** e você digita no editor.
O que já está no editor (e os defaults do pipeline) vai ao provedor de IA como
contexto — nome, tipo, origem, cálculo e **o valor fixo dos parâmetros
não-Encrypted** (até 200 caracteres cada); o **valor de um Encrypted nunca sai da
sua tela**. Não cole segredos no chat nem em valores fixos.

**Conversas.** *Nova conversa* recomeça; o ícone de histórico reabre as suas
conversas anteriores (sem as propostas — peça de novo se quiser aplicar).
Mensagens de até 4.000 caracteres. Esc fecha o chat sem fechar a etapa.

⚠️ A proposta aplicada é um **cadastro como outro qualquer**: a conferência
definitiva continua sendo a do disparo (`dsjob -lparams`, §3.10) — nome que o
job não declara falha antes de disparar.

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
- **Parâmetros dos jobs DataStage (§3.10)**: migrations **107, 108 e 109** na
  etapa 6c; `dags/utils/` mudou → **reiniciar o worker** do Airflow (ele cacheia
  `dags/utils/`); `ORQUESTRA_CONN_KEY` também no **worker** (parâmetro Encrypted é
  decifrado no disparo). Roteiro e conferência pós-deploy em
  `docs/release-notes/parametros-datastage.md`.
- **Maestro (§3.11 / §4.9)**: migration **110** na etapa 6c; `dags/etl_log_cleanup.py`
  ganhou a limpeza das conversas (arquivo de DAG — **sem** restart do worker);
  o provedor de IA é o de *Caixa Seguro IA* (chave cifrada com `ORQUESTRA_CONN_KEY`
  na API); ligar em Admin › Acessos & Comunicação › **Maestro**. Roteiro em
  `docs/release-notes/maestro.md`.

### 4.7 Utilitários (Admin → Sistema → Utilitários)
É aqui que se decide **o que** a tela Utilitários (§2.5, §3.7 e §3.8) alcança
no servidor do DataStage. Nada vem de fábrica: sem raiz cadastrada, ninguém
lê, baixa, grava nem envia.

**Diretórios-raiz.** Cadastre a pasta absoluta (ex.: `/dados/bi`) — tudo
abaixo dela fica navegável. Pode haver várias raízes. Pastas do sistema
(`/etc`, `/usr`, `/dev`, `/root`, `/var/run`…) e a barra (`/`) são recusadas
no cadastro **e** quando uma raiz aponta para elas por link no servidor.
Na linha de cada raiz:
- **Testar** — pergunta ao servidor: a pasta existe? é pasta? a conta SSH do
  Orquestra consegue listá-la? Se a raiz for um link, mostra para onde ("é um
  link para /u01/dados"). Uma raiz que aponta para pasta do sistema aparece
  como **NÃO vale**.
- **Editar** (lápis) — corrige o caminho sem criar outra raiz (Enter salva,
  Esc cancela).
- **Desativar** / **Reativar** — raiz desativada não abre mais nada abaixo
  dela; o histórico de auditoria fica.

> ⚠️ **Toda raiz ativa vale para ler, baixar, gravar E enviar.** Não cadastre
> diretórios de projeto que contenham `.param` com credencial de banco: quem
> tem a permissão de cadastrar/editar poderia sobrescrevê-los. E lembre que o
> **download entrega qualquer arquivo** abaixo da raiz, inclusive binários que
> o Ver arquivo recusava (hashed files do DataStage, dumps): não cadastre a
> instalação nem as pastas de projeto do InformationServer. Enquanto não
> existir "raiz só de leitura", a decisão é não cadastrar.

**Extensões graváveis e enviáveis.** Uma lista só, que vale para a aba
Criar/editar **e** para a aba Enviar arquivo (`txt`, `sql`, `param`, `cfg`,
`conf`, `properties`, `csv`, `json`, `yml`…); ler e baixar não dependem dela.
No envio, só a **última** extensão do nome conta, comparada em minúsculas
(`RELATORIO.TXT` entra com `txt`). Incluir uma extensão de **script** (`sh`,
`bash`, `ksh`, `csh`, `zsh`, `py`, `pl`) pede confirmação: permite gravar
scripts que um job pode executar. Incluir extensão de **binário executável**
(`jar`, `so`, `class`, `exe`) libera o envio desses arquivos pela tela — e a
sobrescrita preserva a permissão de execução do arquivo que já existia. Um
arquivo novo nunca nasce executável.
Excluir pede confirmação e vale na hora — quem já está com o editor aberto
recebe "extensão não liberada" ao gravar.

**Limites.** *Teto por arquivo (KB)* — acima disso a leitura pede "últimas N
linhas" e a gravação de texto é recusada (padrão 2.048 KB, máximo 16.384).
O **teto do download e do envio é fixo em 50 MB** e não segue esse valor.
*Guardar cópia de segurança ao sobrescrever* — liga o `.bak-<data-hora>` na
mesma pasta (ligado por padrão), na gravação e no envio. Lembre que ninguém
expurga os `.bak` e que um envio de 50 MB sobrescrito com cópia ocupa 100 MB:
combine a limpeza com a sustentação.

**Permissão.** Em Admin → Usuários & Perfis, a tela **Utilitários** é um
checkbox por perfil (admin, desenvolvedor e operador já vêm marcados pela
migration 105). Gravar exige, além da tela, a ação **Cadastrar/Editar**. A
permissão só aparece para o usuário depois de **sair e entrar de novo**.

**Auditoria.** `dbo.etl_utilitario_arquivo_log`: matrícula, servidor, ação
(`ler`, `listar`, `gravar`, `testar`, `raiz`, `baixar`, `enviar`), caminho
real no servidor, tamanho, hash SHA-256, resultado (`ok`, `negado`, `erro`),
detalhe e duração. Sem conteúdo de arquivo. No `baixar`, `ok` quer dizer que a
API leu o arquivo do servidor (a entrega ao navegador não é confirmável). No
`enviar`, o detalhe diz `criado` ou `sobrescrito; backup …`; um envio que
estourou o tempo (504) ganha uma **segunda linha** quando a gravação termina
depois — `concluído após o 504 — o arquivo FOI gravado` ou `falhou após o
504` — para a auditoria dizer a verdade que a tela não pôde dizer. Consulta
útil:
```sql
SELECT TOP 50 executado_em, usuario, acao, resultado, caminho, LEFT(detalhe, 120) AS detalhe
FROM dbo.etl_utilitario_arquivo_log ORDER BY id DESC
```

**Ambiente.** A API usa as mesmas variáveis SSH do Console DataStage
(`DS_SSH_HOST`, `DS_SSH_USER`, `DS_SSH_PASSWORD` ou `DS_SSH_KEY_FILE`). Com
`DS_SSH_KNOWN_HOSTS` definida, só a host key conhecida do servidor entra
(recomendado em produção). O caminho é lido **de dentro do container da API**:
guarde o arquivo em `dsx/` (montado como `/opt/airflow/dsx`) e aponte
`DS_SSH_KNOWN_HOSTS=/opt/airflow/dsx/known_hosts` — um caminho do host que o
container não enxerga deixa a tela inteira em "arquivo que a API não consegue
ler".

### 4.8 Lineage ISX (DataStage): configuração, lote e mapa de tipos
A aba Job DataStage (§3.9) só funciona depois que o administrador configura o
acesso ao `istool` e à API REST do DataStage. Nada disso vem de fábrica e **nenhuma
credencial fica no Orquestra além do `.env`**: sem configuração, Extrair responde
503 "não configurado" e ninguém extrai — nada mais quebra.

**Migration.** A **106** (`sql/migrations/106_lineage_isx.sql`, etapa 6c do deploy)
cria `dbo.etl_ds_job_isx` (cabeçalho por job), as colunas novas de
`etl_job_lineage` e completa o mapa de tipos `dbo.etl_stage_type_map`. Idempotente.

**`.env` da API** (bloco "Lineage ISX"; modelo em `.env.dev.example`):

| Variável | Para quê |
|---|---|
| `DS_ENGINE` | Nome (FQDN) do engine do DataStage, como o istool exige no `-datastage` |
| `DS_API_URL` | URL da API REST do DataStage (`https://<host>:<porta>/ibm/iis/ds/api`); **sem** `usuario:senha@` — se vier, a API recusa |
| `DS_API_USER` / `DS_API_PASSWORD` | Credencial da API REST (Basic); só leitura da árvore de pastas e do `lastModified` |
| `DS_API_VERIFY_SSL` | `true`, o caminho de uma CA interna, ou `false` (funciona, mas a API avisa a cada arranque) |
| `DS_ISTOOL_HOME` | Raiz do Information Server no servidor (padrão `/opt/IBM/InformationServer`) |
| `DS_ISTOOL_LAUNCHER` | JAR do launcher do istool, relativo ao home (o padrão é o da versão 11.7) |
| `DS_ISTOOL_DOMAIN` | `host:porta` dos serviços (services tier) |
| `DS_ISTOOL_AUTHFILE` | Caminho, **no servidor do DataStage**, do arquivo de credencial do istool (abaixo) |
| `DS_ISTOOL_TMP` / `DS_ISTOOL_CFG` | Pastas privadas do usuário SSH para o `.isx` temporário e a `configuration/` do istool (padrão `~/.orquestra/…`) |
| `DS_SSH_KNOWN_HOSTS` | Já usada pelos Utilitários (o Console ainda aceita qualquer host key): sem ela o SSH do ISX também aceita qualquer host key — e o canal transporta o `.isx`, que traz credenciais de conexão dos jobs |

O SSH é o mesmo do Console e dos Utilitários (`DS_SSH_HOST/PORT/USER/PASSWORD`).
Depois de mudar o `.env`, recriar o container da API.

**Arquivo de credencial do istool (`-authfile`).** Criado pela sustentação **no
servidor do DataStage**, na pasta do usuário SSH do Orquestra, com duas linhas na
grafia chave=valor — `user=<usuário do istool>` e `password=<senha>` — e permissão
**600** desse usuário. A grafia com hífen (`-user` numa linha e a senha na seguinte,
como nos parâmetros de linha de comando) o istool 11.7 recusa com *user name not
found* (medido em produção). Em `DS_ISTOOL_AUTHFILE` vai o caminho no servidor —
absoluto (`/home/<usuário ssh>/.orquestra/istool.auth`) ou com `~/`, que o
Orquestra traduz para o home do usuário SSH. O Orquestra usa esse caminho no
`-authfile` e nunca `-password` na linha de comando (a senha apareceria no `ps` e
no log). Sem a variável, Extrair
responde 503 *Lineage ISX não configurado nesta instância da API — defina
DS_ISTOOL_AUTHFILE*; com a variável apontando para um arquivo que não existe no
servidor, o istool falha e a resposta é 502 *O istool falhou ao exportar o job* — o
motivo fica no log da API.

**Lote — botão "Extrair todos (lote)".** Só o administrador vê o botão na aba
(§3.9). Ele dispara a DAG **`etl_lineage_extract_isx`** para os jobs DataStage do
pipeline carregado; a linha abaixo do filtro acompanha a run a cada 5 s e resume
*N job(s): x extraído(s), y em cache, z com erro* — "ver erros" mostra job a job. A
run termina **verde mesmo com erros individuais** (um job apagado no DataStage não
derruba os outros — e falha de istool/SSH em todos os jobs também deixa a run verde
com N erros: veja "ver erros"). A run só **falha** quando nenhum job chega à API (API
fora do ar, credencial de serviço recusada, ISX não configurado) ou quando o filtro não
encontra job DataStage (pipeline inativo, só `CopyOf*`, só nós que não são DataStage).
A DAG
chama a API do Orquestra por job com um **usuário de serviço** com `acao_editar`,
definido no `.env` do Airflow em `AIRFLOW_CONN_ORQUESTRA_API`
(`http://<usuario>:<senha>@orquestra-api:8000/http`) — pelo ambiente do worker, não
pelo banco do Airflow (assim não aparece nem se edita na UI do Airflow). Pela API:
`POST /lineage/isx/lote {pipeline_name, jobs?, force?}` (vazio = todos os
pipelines com projeto) e `GET /lineage/isx/lote/{run_id}`. Cada job é uma JVM do
istool (3–5 s) no servidor do DataStage, 4 de cada vez: prefira horário sem carga.

**Mapa de tipos de stage.** Quando o cabeçalho avisa *N stage(s) com tipo fora do
mapa*, o tipo (ex.: `PxAlienStage`) não está em `dbo.etl_stage_type_map`. Inclua
por SQL — a coluna-chave se chama `stage_type` ou `type_raw`, conforme o ambiente
(confira com `COL_LENGTH`) — informando `type_label`, `type_category`
(`banco`, `arquivo`, `transformacao`, `sequence` ou `debug`) e `role_hint`; depois o
usuário clica **Atualizar** no job. Não há tela para isso ainda (backlog).

**O que mudou para quem consome a API.** `GET /lineage` (a aba Lineage) **passa a
exigir o token** da sessão — scripts externos que liam o lineage sem autenticação
param de funcionar. A extração unitária exige `acao_editar`; o lote, admin; o
disparo genérico de DAGs da API também exige admin para esta DAG.

### 4.9 Maestro (Admin → Acessos & Comunicação → Maestro)
A aba governa o assistente de parâmetros do §3.11. Exige a migration **110**
(sem ela a aba diz isso em vez de carregar).

**Interruptor.** *Maestro ligado/desligado*. Ligar exige o **provedor de IA com
chave** configurado em *Caixa Seguro IA* (o mesmo provedor dos assistentes do
Caixa: Anthropic, OpenAI-compatível ou o gateway interno; o interruptor dos
assistentes do Caixa é independente). Desligado — ou ligado sem chave — o
avatar não aparece para ninguém. Ao lado, o provedor, o modelo, se a chave está
configurada e as contagens (cenários ativos, pedidos em aberto, retenção).

**Catálogo de cenários.** É o que o Maestro **pode prometer**. Cada cenário tem:
- **Código** (`mensal_anterior`…): identificador, citado no rastro da conversa.
- **Título** e **descrição** — a descrição é o que o Maestro lê para reconhecer
  o cenário: diga quando usar e o que cada parâmetro representa.
- **Receita**: um parâmetro por linha, no vocabulário do §3.10. O nome pode ser
  um **marcador** entre `< >` (`<DATA_INICIAL>`): o Maestro o troca pelo nome
  real do job (do lineage ISX ou informado pelo usuário). *Simular com a
  referência* mostra a prévia com os marcadores e os erros da régua — a receita
  passa pela **mesma régua do salvar** da etapa, então o catálogo não promete o
  que o Orquestra recusaria. Parâmetro Encrypted entra **sem valor** (o
  usuário digita na etapa); marcador repetido é recusado.
- **Exemplos de pedido**: uma frase por linha; o primeiro exemplo dos **quatro
  primeiros cenários ativos** (ordem de criação) vira sugestão de abertura do
  chat — os demais o Maestro conhece pelo catálogo, mas não sugere.
- **Ativo**: inativo some do Maestro sem apagar o cadastro.
A instalação vem com 10 cenários (mês anterior, mês corrente, diário, D-1,
semana anterior, trimestre anterior, ano anterior, competência AAAAMM, run id,
caminho fixo) — edite, desative ou crie os seus. Excluir é definitivo (dois
cliques).

**Pedidos não atendidos.** Cada vez que o Maestro responde *não atendido*, o
pedido entra aqui com quem pediu, pipeline/etapa, o texto e o motivo. É a
demanda que o catálogo ainda não cobre: crie o cenário (se o vocabulário
permite) ou registre o backlog, e marque **tratado** (dá para reabrir; a caixa
*mostrar os já tratados* lista o histórico).

**Retenção.** As conversas ficam em `etl_maestro_conversa` por **180 dias**; a
DAG `etl_log_cleanup` (03h) apaga o que passa disso — inclusive os pedidos não
atendidos, tratados ou não. Um pedido que mereça virar cenário deve ser tratado
(ou registrado no backlog) antes disso.

---

## 5. Perguntas frequentes

**O pipeline não rodou no horário. Por quê?** Verifique, nesta ordem: (1) pipeline ativo? (2) data está num calendário de feriado ou blackout? (3) tipo "horários específicos": o horário consta na lista? (4) DAG gerado/atualizado após a última edição? (5) DAG despausado no Airflow?

**Editei o pipeline e nada mudou.** Edições de agendamento exigem **Gerar DAG** novamente. (Parâmetros DataStage — da etapa ou do pipeline — **não** exigem: o operador os lê a cada disparo.)

**A etapa falhou antes de disparar: "o job NÃO declara o(s) parâmetro(s)…".** O nome cadastrado não existe no job, ou está com outra caixa (`pdata` ≠ `pData`) — a mensagem lista o que o job declara. Corrija na etapa (§3.10) ou use **Importar do DataStage** para trazer os nomes certos.

**A etapa falhou com "data de referência indisponível".** A etapa tem parâmetro com origem *Data de referência* e a corrida não tem registro (DAG publicada antes da migration 067, ou disparo fora do fluxo normal). Republique a DAG; para um disparo avulso, informe `data_referencia` no conf.

**Salvei um parâmetro e a API respondeu "exigem a migration 107/108/109".** O banco desse ambiente ainda não recebeu a migration — rode a etapa 6c do deploy (§4.6).

**O valor Encrypted apareceu no log do DataStage.** O DataStage só mascara parâmetros Encrypted **no job**; um Encrypted do Orquestra enviado a um parâmetro String do job sai em claro no `dsjob -logsum`. Troque o tipo do parâmetro no Designer ou não use Encrypted ali (§3.10).

**Jobs em paralelo não rodam juntos.** Confirme que têm exatamente a mesma ordem de execução e que há workers Celery disponíveis.

**Execução manual rodou em feriado.** Comportamento esperado: execuções manuais ignoram calendário/blackout/horários.

**Não vejo a aba Admin (ou outra aba).** Seu perfil não tem acesso a essa tela — solicite ao administrador em Admin → Usuários & Perfis.

**Apertei F5 e continuei logado — é normal?** Sim. A sessão usa um token salvo no navegador (a senha nunca fica armazenada) e expira automaticamente após o período configurado (padrão 12h). Para encerrar antes, use Sair.

**Utilitários diz "Fora dos diretórios liberados", mas a pasta existe.** Existir não basta: a pasta precisa estar abaixo de uma raiz cadastrada e ativa em Admin → Sistema → Utilitários (§4.7). Se o caminho passa por um link que sai da raiz, a resposta é a mesma.

**Cancelei o envio e o arquivo apareceu no servidor mesmo assim.** O Cancelar só interrompe enquanto o arquivo está subindo do seu computador. Depois que ele chega inteiro (o botão some e o modal diz *gravando… aguarde*), o servidor grava de qualquer forma — por isso a mensagem de cancelamento pede para conferir na pasta. Para desfazer, sobrescreva com a versão certa: a cópia de segurança `.bak-<data-hora>` guarda o que estava lá antes (§3.8).

**O Enviar arquivo diz "somente leitura" numa pasta que existe.** A pasta é uma montagem sem escrita no servidor (no ambiente de DEV, a pasta extra montada do disco da VPS é assim de propósito). Use uma pasta abaixo de uma raiz gravável — no DEV, `/dados/bi` ou `/dados/param`.

**Utilitários: o acento veio errado.** O rodapé do modal mostra a codificação detectada (`utf-8` ou `latin-1`). Ao editar, escolha a mesma codificação antes de gravar — "Carregar existente" já faz isso.

**Gravei um arquivo e o job passou a falhar por permissão.** A gravação preserva as permissões do arquivo anterior, mas o **dono** passa a ser a conta SSH do Orquestra. Se o job depende do dono, peça à sustentação para ajustar; a cópia `.bak-<data-hora>` na mesma pasta tem o conteúdo anterior.

**Job DataStage diz que o job não está mapeado no pipeline.** É a regra do lineage ISX: só se extrai job que está num pipeline do Orquestra, e o projeto vem do cadastro do pipeline. Mapeie o job na aba ⚙ Jobs (§3.2) e volte à aba (§3.9).

**Job DataStage: "não encontrado no projeto … do DataStage".** O DataStage distingue maiúsculas de minúsculas e o Orquestra não — confira a grafia exata do job, o projeto cadastrado no pipeline e se o job não foi movido de pasta, renomeado ou apagado. Se o job mudou de nome no DataStage, corrija o nome na aba ⚙ Jobs.

**Cliquei em Extrair na lista de filhos da sequence e veio "dados do cache".** *Extrair* (na lista de filhos e no lote) só reextrai quando o job mudou no DataStage; sem mudança, o resultado vem do banco — é o esperado. *Atualizar* na lista de jobs sempre força a reextração. Veja a data em *Modificado no DS* no cabeçalho.

**O lineage que eu cadastrei à mão sumiu da aba Lineage?** Não: ele continua no banco. Quando o job tem lineage ISX, a aba Lineage mostra o ISX (mais completo) no lugar do manual/DSX; o Job DataStage mostra só o ISX.

**Não vejo o botão "Extrair todos (lote)".** Ele é só do administrador (§4.8); a extração unitária pede a permissão de cadastrar/editar (Desenvolvedor ETL).

**O botão do Maestro não aparece na seção de parâmetros.** Ele só existe em etapa `datastage`, e só quando o administrador ligou o Maestro **e** o provedor de IA tem chave (Admin › Maestro, §4.9). Depois de ligar, quem já estava com a tela aberta pode precisar de F5 (o status é lido a cada 5 min). Sem a migration 110 o Maestro fica oculto.

**O Maestro disse que "não atende" o meu cenário.** Ele só promete o que está no catálogo e se monta com o vocabulário do §3.10 (dias úteis, feriados e valor vindo de tabela ficam de fora). O pedido já ficou registrado para o administrador (§4.9); se o cenário for viável, ele cria o cenário no catálogo e o Maestro passa a atender.

**Apliquei a proposta do Maestro e a etapa falhou no disparo ("o job NÃO declara…").** O Maestro não fala com o DataStage: sem lineage ISX ele usa os nomes que você informou ou nomes convencionais e avisa para conferir no Designer. Extraia o lineage (§3.9) para ele usar os nomes declarados, ou corrija a grafia na etapa.

**O Maestro pediu a senha de um parâmetro Encrypted?** Não deveria — ele é instruído a nunca pedir nem repetir segredos e propõe a linha sem valor. Nunca digite a senha no chat: digite no campo Encrypted do editor, que é cifrado.
