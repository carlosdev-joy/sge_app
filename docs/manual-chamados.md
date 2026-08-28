# Chamados — manual de uso

A tela **Chamados** é um espelho somente-leitura do ServiceNow. Ela lê; não
escreve. Mover um card aqui não move nada lá — por isso o quadro não tem
arrastar-e-soltar: um card que se arrasta prometeria uma ação que não existe.

Para **agir** no chamado (assumir, comentar, resolver), use o link
**ServiceNow** que cada card e cada linha oferecem.

---

## 1. As três abas

| Aba | Responde | Para quem |
|---|---|---|
| **Fila** | "o que está na minha mão agora?" | quem executa |
| **Dashboard** | "como está o conjunto hoje?" | quem coordena |
| **Indicadores** | "estamos melhorando ou piorando?" | quem analisa |

---

## 2. Fila — o quadro

### O que é um card

**Um card é um trabalho, não um registro.** No ServiceNow, um pedido (RITM)
costuma vir com uma tarefa (SCTASK) atrelada — dois registros para uma coisa
só. Aqui o pedido é o card, e a tarefa aparece como **linha dentro dele**
(`↳ SCTASK…`).

É por isso que a contagem daqui pode ser menor que a do ServiceNow: lá são
registros, aqui são trabalhos. Os dois números estão certos, só respondem a
perguntas diferentes.

> Uma tarefa **sem pedido pai** (órfã) vira card próprio — ela existe e não
> pode sumir da vista só porque o parentesco não veio.

### Ler um card

- **Título** — o que é o chamado. É o elemento maior, e clicar nele abre o
  conteúdo.
- **detalhes** — abre descrição, histórico de anotações e anexos.
- **⧉** — abre o chamado no ServiceNow, em aba nova.
- **⧉ (copiar)** ao lado do número — leva o número para a área de
  transferência. Se o navegador recusar (acontece fora de HTTPS), o número é
  **selecionado** e o botão avisa `use Ctrl+C`.
- **de _Fulano_** — quem **pediu**. Abaixo, quem **atende**. São pessoas
  diferentes: uma para saber a quem responder, outra a quem cobrar.
- **prazo** com a data e o que ela significa (`faltam 5d`, `vence hoje`,
  `atrasado 3d`).
- **idade** (`12d`) com rótulo quando preocupa (`atenção`, `parado`).

> Card **resolvido** não mostra idade nem prazo. Alarme sobre trabalho feito
> não pede ação nenhuma — e é o que ensina a ignorar os outros.

### As marcas

| Marca | Significa |
|---|---|
| **Incidente** (vermelho) | interrupção — algo que funcionava parou |
| RITM / Tarefa | pedido de trabalho planejado |
| **dia a dia** / **iniciativa** | categoria marcada pela equipe nas work notes |
| SLA vencido | o ServiceNow marcou o SLA como estourado |
| PODE INICIAR / FALTA INFO | veredito da triagem. `~` = veio de regra de texto, não de IA |

**Incidente em curso fica destacado e sobe para o topo da coluna.** Ele perde
as duas coisas ao ser resolvido.

### Os filtros

- **Buscar** — número, título, responsável. Alcança também o número da tarefa
  dentro do card.
- **Tipo** — RITM, Incidente. *(Tarefa não aparece: ela não é um item da fila,
  é uma linha dentro do card.)*
- **Categoria** — Dia a dia, Iniciativa, **Sem marcação**. A terceira é a lista
  do que ainda falta classificar.
- **Solicitante** — quem pediu.
- **Responsável** — inclui **sem atribuição**: o que ninguém pegou.
- **Prioridade**.

Os filtros se **somam**. Quando algum está ativo aparece **Limpar**.

> Se a fila ficar vazia por causa de um filtro, a tela **diz** que foi o filtro
> — para você não procurar defeito na integração.

### A raia "Outros"

Recolhe estados que o mapa do ServiceNow não conhece. **Ela só aparece quando
tem card** — e quando aparece, é sinal de que algo merece investigação.

---

## 3. Dashboard — o painel do dia

Blocos com o número e a cor de cada situação: backlog, abertas, em andamento,
pendentes, resolvidas, e os alertas de prazo (vencem hoje, vencem na semana,
vencidas).

**Clique num bloco** e a lista dele abre embaixo, em tabela. Cada coluna tem
posição fixa — o responsável está sempre embaixo de *Responsável*, mesmo quando
o chamado não tem prazo.

- **Arraste a borda** entre dois cabeçalhos para alargar uma coluna. A largura
  fica guardada no seu navegador, por tabela.
- Nome cortado? O valor inteiro aparece ao pousar o cursor.
- **10 linhas por página**; a régua embaixo diz o intervalo e o total
  (`11–20 de 25`).
- **Clique no número** para abrir o conteúdo do chamado sem sair da tela.

As quatro visões no topo (**Geral**, **Meu painel**, **Dia a dia**,
**Iniciativas**) recortam **todos** os blocos de uma vez.

---

## 4. Indicadores — a análise

- **Idade dos chamados na fila** — só os que **ainda esperam**. É o que mostra
  se há coisa velha parada.
- **Tipo × Estado** — onde a fila se acumula.
- **Entradas × Saídas** (14 dias) — se a fila cresce ou drena.
- **Carga por responsável**.
- **O que a fila está pedindo** — tipo de demanda deduzido do título.
- **Categoria** — dia a dia, iniciativa e **sem marcação**, os três juntos.
- **Resolvidos nos últimos N dias** — em tabela paginada, com o tempo de
  atendimento.

### Filtrar por responsável

O seletor no topo aceita **vários nomes ao mesmo tempo** — marque quantos
quiser. Há também **sem responsável**, que se soma aos nomes marcados (pergunta
pelos dois conjuntos, não pela interseção).

Feche a caixa clicando fora, com **Esc**, ou no botão **fechar**.

> ⚠️ O filtro vale para **toda a aba**. Enquanto estiver ativo, a tela avisa em
> âmbar de quem são os números. Sem esse aviso, um print desta tela vira "a fila
> tem 16 chamados" quando são 16 de uma pessoa.

---

## 5. O conteúdo do chamado

Clicar em **detalhes** (ou no título, ou no número na tabela) abre:

- **Solicitante** e responsável, estado, grupo, datas e o estado **na origem**
  (é ele que explica um card em "Outros");
- **descrição** completa;
- **histórico de anotações**, mais recentes primeiro, **incluindo as das
  tarefas** do chamado — marcadas com `via SCTASK…` quando vêm de lá;
- **anexos**, que baixam pelo Orquestra (a credencial do ServiceNow não vai
  para o navegador).

Cada anotação diz se é **nota interna** (fica na equipe) ou **comentário ao
solicitante** (o solicitante lê). A distinção não é decorativa.

---

## 6. "Isso está atualizado?"

No topo da Fila há o carimbo de sincronização (`sincronizado há 7 min`). Ele
fica **âmbar quando atrasa** e diz **de qual motor** veio o número.

Se aparecer **erro**, a tela avisa: a fila pode não refletir o ServiceNow.

---

## 7. Quando algo parecer errado

| Sintoma | O que provavelmente é |
|---|---|
| "Sistema em atualização" | as migrations do banco ainda não passaram |
| Fila vazia com aviso âmbar | a sincronização falhou — não é que não há chamados |
| Cards sem categoria/veredito | as colunas derivadas ainda não existem no banco |
| Nenhuma anotação em nenhum chamado | a coleta não está rodando — **não** é ausência de notas |
| Carimbo com muitas horas | a DAG de sincronização parou |
| Tela ou permissão nova não aparece | **saia e entre de novo** — as permissões só atualizam no login |

Nada disso se resolve pela tela: são avisos para acionar quem cuida do
Orquestra.
