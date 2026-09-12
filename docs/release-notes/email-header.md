# Release note — Cabeçalho do e-mail no Outlook (F3)

Spec: `docs/spec-email-tabela-sql-e-ajustes.md` · Fase F3 · Migration **113**

## O defeito

O modelo institucional "Aviso de fim de carga" chegava quebrado no Outlook
desktop: o cabeçalho aparecia **cortado ao meio** — com "ORQUESTRA · Gestão de
Pipelines" encostando na barra laranja — e com uma **faixa de outra cor à
direita**. Três causas somadas, todas no mesmo bloco:

1. **`<v:textbox>` sem `mso-fit-shape-to-text:true`** e `<v:rect>` sem altura: o
   motor do Word dá à forma uma altura fixa e **clipa** o que não cabe.
2. **O corpo era enviado sem `<head>`**, portanto sem
   `<o:PixelsPerInch>96</o:PixelsPerInch>`. Sem isso o Word dimensiona VML com o
   **DPI do Windows**: numa tela a 125% (o padrão em notebook corporativo) a
   forma sai menor que a largura da mensagem — a tal faixa sobrando.
3. **Modo escuro**: o Outlook inverte `bgcolor` mas **não** inverte preenchimento
   VML, deixando dois azuis diferentes no mesmo cabeçalho.

## O que muda

- **No envio** (`api/services/email_mime.py` e `dags/utils/email_envio.py`, que
  são espelhos): o corpo HTML passa a ser embrulhado num documento completo —
  `<!DOCTYPE>`, `meta charset`, `color-scheme: light only` e o bloco
  `OfficeDocumentSettings/PixelsPerInch`. Corpo que **já é** documento volta
  intacto (embrulhar de novo criaria um segundo `<body>`, que o cliente
  descarta). O alternativo em texto simples continua saindo do corpo original,
  sem arrastar o `<head>`.
- **No modelo** (migration 113): cabeçalho sem VML e sem gradiente — cor sólida —
  e o logo montado com **células** em vez de `<div>` dimensionada, que o Word
  ignora.
- **`{linhas}` sem valor vira `—`**. Vazio deixava a célula "Linhas processadas"
  em branco, como se a carga não tivesse trazido nada; é o que se vê quando o nó
  de e-mail vem depois de um nó SQL, que não tem `rows_out` para somar.

## ⚠️ Se você editou o modelo pela tela

A migration **só corrige o corpo que ainda está idêntico ao semeado pela 112**
(confere o SHA2_256). Modelo editado fica **intacto** — e continua com o
cabeçalho quebrado. O log da migration diz qual caso foi o seu:

```
[OK] cabecalho do modelo institucional corrigido (sem VML, logo em celulas)
[--] modelo EDITADO (ou ja corrigido) — corpo preservado, nada alterado
```

Para aplicar o cabeçalho novo num modelo editado, em **Admin › E-mail ›
Modelos**, substitua no HTML o bloco que começa em
`<td bgcolor="#0F4C88"` e termina no `</td></tr>` anterior à barra laranja
(`<td bgcolor="#F26B00"`) pelo bloco correspondente da migration 113. O resto do
corpo — inclusive suas edições — permanece.

## Ordem do deploy

1. **Migration 113** na etapa **6c** do `deploy.sh`.
2. **`api/`** (o embrulho do corpo vive em `services/email_mime.py`).
3. **`dags/`** — e **reiniciar o worker**: `dags/utils/` é cacheado pelo
   processo, e sem o restart a task fica **verde** enviando com o código antigo
   ([[orquestra-worker-cacheia-dags-utils]]).
4. **`dist/`** (nada de front mudou nesta fase, mas o deploy é o mesmo).
5. `config/` → **n**.

## Conferência pós-deploy

a) Rodar a 113 e ler o log: precisa dizer `[OK] cabecalho … corrigido` (ou
   `[--] modelo EDITADO`, se for o seu caso — aí siga a seção acima).
b) Rodar a 113 **de novo**: a segunda vez precisa dizer `[--]` e não alterar
   nada.
c) **Admin › E-mail › Modelos**: abrir "Aviso de fim de carga" e conferir na
   prévia que o cabeçalho aparece inteiro.
d) Enviar um **e-mail de teste** e abrir no **Outlook desktop**: cabeçalho
   completo, sem corte e sem faixa de cor diferente à direita.
e) Repetir (d) com o **fundo da mensagem invertido** (o botão de modo escuro do
   Outlook): o cabeçalho precisa continuar legível, num tom só.
f) Rodar um fluxo cujo nó de e-mail **não** venha depois de uma etapa DataStage:
   a linha "Linhas processadas" precisa mostrar `—`, nunca vazia.
g) Abrir o mesmo e-mail no **Outlook Web** e no celular: o layout não pode ter
   regredido em quem já funcionava.

## Reversão

Voltar `api/` e `dags/` (com restart do worker) desfaz o embrulho e o `—`. O
**corpo do modelo não volta sozinho**: para restaurar o cabeçalho antigo é
preciso reexecutar o INSERT da 112 sobre a linha, ou editar o modelo pela tela.
Não há motivo prático para reverter só o modelo — o cabeçalho antigo é o que
está quebrado.
