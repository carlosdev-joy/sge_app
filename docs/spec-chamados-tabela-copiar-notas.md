# Spec — Chamados: tabela alinhada, copiar o número, e as anotações que existem

**Estado:** rascunho para execução
**Origem:** três pedidos do dono do produto ao usar a tela de Chamados em dev
**Depende de:** o porte do módulo (`docs/spec-porte-chamados-producao.md`, F0–F5)

---

## 1. O que foi pedido

> "na lista de chamados resolvidos ou em qualquer outro local que aparece na
> formato de lista, deve ser colocado em formato de tabela, para garantir que o
> usuario sempre veja responsavel em 'coluna' responsavel. neste momento por
> exemplo tem uma demanda sem prazo, e acabou jogando o nome do responsavel
> para baixo do prazo, e os nomes ainda estão cortando. isso facilita a
> padronizar a informação na tela, permitir o usuario arrastar o tamanho da
> coluna para visualizar de forma melhor o que ele deseja."

> "nos cards, e todo local que tenha numero de chamado ou task, incluir um
> botão para copiar o numero, facilitando o dia a dia de quem vai questionar
> algo a alguém."

> "as anotações normalmente ficam vinculadas a task, porem não exibimos os
> detalhes da task no chamado no orquestra. vamos usar a parte de anotações
> para essa estrutura do chamado trazendo as anotações da sua task, assim
> ganhamos velocidade no entendimento no chamado, historico preenchido pelo
> responsavel ou cliente interno."

---

## 2. O que a investigação encontrou

Antes de desenhar, fui ao dado. O terceiro pedido revelou um defeito maior do
que ele.

### A1 — A aba "Anotações" nunca mostrou nada. Para ninguém.

```
total_notas    0          ← dbo.etl_chamado_nota
total_anexos  89          ← dbo.etl_chamado_anexo
total_chamados 3443
```

A tabela de notas está **vazia**, enquanto a de anexos — preenchida pelo mesmo
laço, no mesmo DAG, na mesma transação — tem 89 linhas. Não é ambiente de dev
mal carregado: o coletor roda e grava anexos.

**Causa.** `buscar_notas()` consulta `sys_journal_field`, e essa tabela é
**inacessível para a conta de integração**. Sondado contra a instância real:

```
journal element=work_notes (o que o motor usa)   HTTP 200  itens=0
journal SEM filtro de element                    HTTP 200  itens=0
campo work_notes/comments na própria tabela      HTTP 200  itens=1  ← o conteúdo está AQUI
```

O ServiceNow responde **200 com lista vazia** em vez de 403. Este é o modo de
falso verde mais caro do catálogo: a DAG fica **verde**, o contador do ciclo
grava `qtd_notas=0`, e a tela mostra "nenhuma anotação" — que é exatamente o
que ela mostraria se o chamado realmente não tivesse notas. Ninguém tinha como
distinguir as duas coisas.

⚠️ **Não é regressão do porte.** O motor sempre leu a tabela errada.

### A2 — O conteúdo existe, como diário concatenado no próprio registro

`work_notes` e `comments` chegam como texto único, com um cabeçalho por entrada:

```
28/08/2026 11:59:04 - Cristiane Gomes de Moura (Anotações de trabalho)
iniciativa
visão 360

26/08/2026 15:08:30 - Carlos Henrique de Oliveira (Comentários)
dia a dia
```

Formato: `dd/mm/aaaa HH:MM:SS - Autor (Rótulo)`, entradas separadas por linha em
branco, **mais recente primeiro**. O rótulo vem traduzido pela instância
(`Anotações de trabalho` = `work_notes`, `Comentários` = `comments`).

### A3 — A nota humana pode estar de qualquer lado, e o eco duplica

O ServiceNow espelha entre pai e task, com um texto de integração:

| Chamado | Onde está a nota humana | O que o outro lado recebe |
|---|---|---|
| RITM0100124 | **no RITM** (`iniciativa / visão 360`) | task: "Anotação de trabalho adicionada na solicitação RITM0100124:" |
| RITM0103367 | **na SCTASK** (`dia a dia`) | RITM: "Comentário adicionado na tarefa SCTASK0105181 …:" |

Duas consequências de desenho:

1. Ler só o pai **perde** notas; ler só a task também. É preciso ler **os dois**
   — que é precisamente o que o pedido descreve.
2. Unir os dois ingenuamente **duplica cada nota**, porque a mesma anotação
   existe nos dois diários com o mesmo autor e o mesmo instante. Some a isso o
   eco — autor `Usuário de Integração Interno`, corpo `Comentário adicionado na
   …` sem conteúdo próprio — e o histórico vira o dobro de linhas com metade da
   informação.

### A5 — Medido depois: a junção, hoje, não acrescenta uma nota sequer

⚠️ **Este achado contraria a premissa do pedido, e fica registrado por isso.**
Com o coletor consertado (996 notas onde havia 0), a junção foi medida sobre os
**182 pedidos que têm nota em alguma tarefa**:

```
pais com alguma nota em task:                182
pais que GANHAM nota por causa da juncao:      0
notas que so existem na task:                  0
```

O ServiceNow espelha **toda** anotação nos dois lados. O diário do pedido já
contém o que está na tarefa — então o que faltava na tela **não era a junção,
era a coleta** (A1).

A junção permanece, por duas razões que continuam valendo:

* é ela que garante o resultado quando o espelhamento **não** acontece
  (categoria com regra própria, tarefa de outro grupo, instância reconfigurada);
* agora que as notas existem dos dois lados **no nosso banco**, é o dedupe dela
  que impede o histórico de aparecer duplicado.

### A4 — A lista do painel desalinha quando falta um campo

Confirmado no código: `ListaDoBloco` é um `flex` onde prazo e data só são
renderizados quando existem. Chamado **sem prazo** perde duas células, e o
responsável escorrega para a posição delas. Some a isso `w-32 truncate`, e o
nome é cortado sem que exista qualquer forma de vê-lo inteiro.

---

## 3. As fases

### F1 — A lista vira tabela, com colunas que o usuário arrasta

Componente único `TabelaChamados`, usado nos **dois** lugares onde chamado
aparece por linha: a lista do bloco no Dashboard e a tabela de tempo de
atendimento nos Indicadores.

* **Coluna é posição, não sobra.** Célula sem valor renderiza vazia e **mantém
  a coluna** — é isso que garante "responsável sempre embaixo de Responsável".
* **Largura arrastável**, com alça entre os cabeçalhos; a escolha do usuário
  persiste em `localStorage` por tabela. Sem dependência nova: o deploy da Caixa
  é offline, e um pacote de grid custaria rede.
* **Largura mínima** por coluna, para o arrasto não produzir uma tela onde o
  conteúdo é inalcançável.
* `title` com o valor inteiro em toda célula truncada — enquanto o usuário não
  arrasta, ele ainda alcança o nome.

### F2 — Copiar o número, onde quer que ele apareça

Botão `Copiar` ao lado do número em: card do kanban, tasks filhas do card,
tabela do Dashboard, tabela dos Indicadores e cabeçalho do modal de detalhe.

* **Confirmação visível** ("copiado") por ~2 s. Cópia é uma ação sem efeito na
  tela: sem retorno, o usuário clica de novo por dúvida e não sabe se funcionou.
* **Degradação real:** `navigator.clipboard` exige contexto seguro (HTTPS ou
  localhost) e pode ser negado por permissão. No fracasso, o número é
  **selecionado** para o usuário copiar com o teclado — e o botão diz isso. Um
  botão que falha em silêncio é pior que a ausência dele.

### F3 — As anotações que existem, do chamado e da sua task

**Motor** (`dags/utils/servicenow_sync.py`)

* `buscar_notas` para de consultar `sys_journal_field` e passa a **parsear** o
  diário de `work_notes` + `comments` que já vem no registro.
* `sys_id_nota` é a PK e o diário não traz uma: usar **hash determinístico** de
  (chamado, data, tipo, texto). Estável entre execuções ⇒ o MERGE continua
  idempotente e não duplica a cada ciclo.
* O eco da integração é **descartado** na origem.
* ⚠️ Mudança em `dags/utils/` **exige restart do worker** no deploy — o worker
  cacheia o módulo e a task fica VERDE rodando código velho.

**API** (`GET /chamados/{sys_id}/detalhe`)

* Passa a devolver as notas **do chamado e das suas tasks**, cada uma marcada
  com o número de onde veio.
* Ordenação por data, **mais recente primeiro** (é o que se quer ler primeiro
  ao abrir um chamado).
* Dedupe por (data, tipo, texto): a mesma nota espelhada nos dois lados aparece
  **uma vez**.
* A degradação separada de notas/anexos que já existe **permanece**.

**Tela** (`ChamadoDetalheModal`)

* Cada nota diz de onde veio quando não é do próprio chamado ("via SCTASK…").
* O vazio continua **dito** e distinto da falha (`migration_ausente`).

---

## 4. O que NÃO fazer

* **Não** deduzir "sem anotações" de uma lista vazia sem antes distinguir falha
  de leitura — foi essa confusão que escondeu A1 por todo o tempo de vida do
  módulo.
* **Não** trocar a tabela de notas por um campo texto no chamado: `work_notes`
  é `NVARCHAR(4000)` (migration 091) e um diário longo trunca em silêncio.
* **Não** introduzir biblioteca de tabela/grid: deploy offline.
* **Não** medir o sucesso da F3 por "a DAG ficou verde". A prova é **contagem de
  notas > 0** no banco e a nota certa na tela do chamado certo.

## 5. Como cada fase se prova

Bancada que **renderiza e clica** (`tests/js/*.cjs` + pytest), como no resto do
módulo — e, para cada teste novo, a **sabotagem** correspondente conferida.

| Fase | O teste tem de cair quando… |
|---|---|
| F1 | uma célula vazia deixa de ocupar a coluna; o arrasto não muda a largura |
| F2 | o botão some; a falha da API de clipboard passa em silêncio |
| F3 | o eco volta a ser contado; a nota da task some do pai; o parser perde a última entrada do diário |

---

# Segunda rodada — filtros, badge e paginação

Pedidos que vieram ao usar a tela com a primeira rodada no ar.

## F4 — Os filtros do kanban

* **Tipo sem "Tarefa".** A tarefa não é um item da fila — é uma linha dentro do
  card do pedido —, então o seletor oferecia um recorte que a tela não
  representa. Os tipos passam a sair dos **cards**.
  ⚠️ Consequência assumida: uma task **órfã** vira card e deixa de ser
  alcançável por este filtro. Ela continua na fila, no "todos" e na busca —
  some do seletor, não da tela. (Em dev, hoje: **zero** tasks órfãs.)
* **Categoria** — Dia a dia · Iniciativa · Sem marcação · todas. Lista
  **fechada**: a derivação (`chamado_derivacoes`) só produz esses dois valores,
  e um seletor alimentado pelo banco mostraria erro de digitação como opção.
* **Sem atribuição** no filtro de responsável — o recorte do que ninguém pegou.
* **Badge de categoria no card**, com cor **e** palavra. Sem marcação **não**
  ganha badge: chip "sem marcação" em metade da fila é ruído que ensina a
  ignorar a linha inteira — quem procura o que falta classificar tem o filtro.

⚠️ **Tipo, categoria e "sem atribuição" falam do CARD**; busca, responsável
nomeado e prioridade continuam alcançando as tarefas dentro dele. Sem essa
separação, um card sem categoria apareceria filtrado como "iniciativa" **sem
badge nenhum** (porque a tarefa tinha a marca), e um pedido atribuído com uma
tarefa sem dono apareceria como "sem atribuição".

Medido em dev: **nenhum** RITM sem marcação tem tarefa marcada — o card basta.

## F5 — "Categorias do dia a dia" vira "Categoria"

O nome estava errado por dois motivos: a classificação é **categoria** (dia a
dia *é* uma delas, ao lado de iniciativa), e o gráfico escondia o terceiro
grupo — o dos **sem marcação** —, que é o maior e o único acionável. Com ele de
fora, um gráfico com 18 classificados parecia a fila inteira, e a única pista
era uma frase na descrição.

## F6 — Paginação, 10 por página

Em `TabelaChamados`, então vale para os **dois** lugares de uma vez.

⚠️ A página é **corrigida**, não obedecida: ela vive em estado e a lista muda
por baixo dela (o usuário filtra, o bloco do painel troca). Obedecer uma página
3 sobre uma lista que encolheu para 4 itens renderiza tabela **vazia** —
indistinguível de "não há nada aqui".

A régua diz o **intervalo e o total** ("11–20 de 25"): "página 2 de 3" sozinho
não responde "quantos são?", que é a pergunta de quem abriu a lista para
conferir um número do painel.

## F7 — Responsáveis por marcação múltipla

A gestão compara duas ou três pessoas; com seletor único isso vira olhar uma,
guardar o número de cabeça, olhar a outra — apagando justamente o número que se
queria comparar.

* `_filtro_responsavel` passa a aceitar lista, com os nomes em `IN (?, …)` e
  "sem responsável" como **condição** (`IS NULL`), somados por **OR**.
* ⚠️ A cláusula vai **parentizada**. Sem os parênteses, `AND a OR b` faz o OR
  engolir todo o WHERE anterior — inclusive `ativo = 1` e o recorte de
  trabalhos —, e a aba passaria a contar encerrados sem nada mudar de aparência.
* A URL **repete** o parâmetro (`?responsavel=A&responsavel=B`). Juntar com
  vírgula produziria um nome "A,B", que não casa com ninguém — e a resposta
  viria vazia parecendo "estas pessoas não têm chamados".
* O aviso de recorte vem do **estado local**, não da resposta: com
  `placeholderData` a tela ainda mostra os dados anteriores enquanto a consulta
  corre, e ler o filtro da resposta deixaria o aviso um passo atrás.

## F8 — Correção: a caixa de responsáveis travava a tela

> "no filtro de responsavel por nome quando escolho qualquer opção o modal não
> some ao clicar fora, ele fica travado ocupando a tela e só com atualização de
> tela que some mas ai não consigo valir os dados."

⚠️ **Defeito introduzido pela F7, com um argumento errado por escrito.** A
escolha do `<details>` foi justificada assim: *"não precisa de listener de
clique-fora — que é onde um menu feito à mão costuma quebrar"*. Só que
`<details>` fecha **apenas pelo próprio gatilho**. Depois de marcar um nome, a
caixa ficava sobre o conteúdo — e o conteúdo é justamente o que a pessoa acabou
de filtrar para ver. A saída era recarregar a página, o que levava o filtro
junto.

A correção não é "não usar `<details>`". É que uma camada flutuante precisa de
uma forma de fechar que **não exija acertar o gatilho de novo**, e são três —
nenhuma opcional:

* **clicar fora**, por uma camada `fixed inset-0` invisível **abaixo** da caixa;
* **Esc**, para quem está no teclado e não tem "fora" para clicar;
* o **gatilho**, que continua alternando — mais um "fechar" **dito**, porque o
  clique fora funciona mas não se anuncia.

**Marcar uma opção NÃO fecha**: o filtro é de múltipla escolha, e fechar a cada
marca obrigaria a reabrir para cada nome — matando o que a F7 entregou.

## F9 — Incidente: destaque e topo da fila

> "quando for incidente o card deve ter um destaque e sempre deve estar no
> inicio da fila que ele estiver, pois ele deve ser prioridade, ele só perde
> este destaque e top da fila quando vai para resolvido."

Incidente é **interrupção**: alguma coisa que funcionava parou. No meio de
pedidos de trabalho planejado ele some — e some justamente quando é o que
deveria ser lido primeiro. Quem abre o kanban lê de cima para baixo e para
quando acha o que procura; um incidente na décima posição de uma coluna que
rola é um incidente que ninguém viu.

* **Destaque**: borda esquerda e fundo próprios, **mais** o rótulo "Incidente"
  em tom de alerta. Cor nunca sozinha.
* **Topo da coluna**, com ordenação **estável** — dentro de cada grupo a ordem
  do servidor é preservada, senão dois cards "iguais" trocam de lugar entre
  renderizações e a fila dança sob o olho de quem lê.
* **Acaba no resolvido**, como pedido — e pela mesma razão que o rodapé cala
  idade e prazo: alarme sobre trabalho FEITO não pede ação nenhuma, e é o que
  ensina a ignorar os outros.

⚠️ "Ainda em curso" passou a ter **um dono só** (`emCurso`, em
`prazoChamados`), de onde `mostraPrazo` também bebe. Uma segunda lista de
estados terminais à mão significaria um lugar parando de alertar enquanto o
outro continua, sem nada na tela denunciando — o mesmo padrão do
`RBAC_RECURSOS`.

**Limite assumido:** o destaque é testado na DECISÃO (`destacaIncidente`,
`ordenarColuna`), não no card renderizado. `CardChamado` vive dentro de
`pages/Chamados.tsx`, que importa react-query, e nenhuma bancada o monta. A
ligação entre a decisão e a classe do card é uma expressão só, coberta por
`tsc -b` e conferida a olho em dev.

## F10 — O quadro: era defeito de token, não gosto

> "o fundo dos cards no kanban, gostaria de algo com uma visiblidade melhor,
> algo mais proximo de ferramentas que utilizam esse formato de card com visual
> mais moderno também parece que são quadrados jogados."

⚠️ **A causa é literal.** O card vinha pintado com **`bg-canvas`** — o token do
**fundo da página** (`--canvas`) — em vez de `bg-panel`, o de superfície. O
cartão tinha exatamente a mesma cor do que estava atrás dele, e o que separava
um card do outro era uma borda de 1px. "Quadrados jogados" descreve o que
estava na tela: eram **contornos**, não superfícies. `--panel` é o token que
`Painel`, o `Dashboard` e os modais já usavam.

Somava-se a isso a **coluna sem superfície nenhuma**: os cards flutuavam direto
sobre o fundo da página, sem nada dizendo onde uma coluna termina e a outra
começa.

O que mudou:

* **Card em `bg-panel`**, com `rounded-lg`, sombra leve e realce ao passar o
  mouse.
* **Raia** por coluna, **rebaixada** (mais escura que o card, não mais clara) —
  é o que faz o card parecer estar *sobre* ela. Cabeçalho com ponto colorido,
  nome e a contagem em pílula.
* **Hierarquia invertida no card**: o título passa a ser o elemento maior e em
  tom cheio; o número, menor e apagado. O título é o que se **lê** na fila; o
  número serve para **citar** o chamado a outra pessoa. Antes os dois tinham o
  mesmo peso e o olho não sabia onde pousar.
* **Uma fileira de marcas, não duas.** O conteúdo é o mesmo — nada saiu —, mas
  as duas linhas empilhadas davam ao card a silhueta de formulário. Todas as
  marcas com a mesma altura e o mesmo raio.
* **A barra do incidente é sobreposta**, não borda grossa: borda muda o tamanho
  da caixa e desalinha o card dos vizinhos. E o destaque muda a **borda**, não a
  superfície — card vermelho inteiro na coluna vira alarme constante.

O estilo saiu para `lib/estiloKanban` porque **defeito de token não aparece em
teste de comportamento**: a tela renderiza, os dados estão certos, e o card só
não se distingue do fundo. Agora a escolha do token é uma afirmação
verificável — e a sabotagem que devolve `bg-canvas` derruba o teste.
