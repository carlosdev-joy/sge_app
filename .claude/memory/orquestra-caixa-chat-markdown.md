---
name: orquestra-caixa-chat-markdown
description: "Chat dos assistentes (Diego/Lari/Léo) do /caixa-seguro mostrava Markdown cru na bolha e no PDF, com emoji virando lixo — PR #326 (um parser, dois desenhistas)"
metadata: 
  node_type: memory
  type: project
  originSessionId: d72d0d73-1cb6-41fb-a79f-c44793f12b3e
  modified: 2026-08-21T14:49:54.714Z
---

✅ **PR #326 MERGEADA na main em 2026-08-21** (squash `8bea325`), sobre
`/caixa-seguro`. ⏳ **Deploy PENDENTE — o usuário leva para produção.** É só
front (`dist/` commitada): sem migration, sem `dags/`, sem dependência nova.
A revisão adversarial achou **8 defeitos** — todos corrigidos no commit
`63886a9`; a prova passou de 25 para 37 asserções. Os que valem lembrar:

⚠️ **`_` no MEIO de palavra não é ênfase.** Sem a borda do GFM,
`NUM_CPF_CNPJ` virava `NUMCPFCNPJ` e `SEQSSDVIDA6SINISTRO_carga_diaria` virava
`SEQSSDVIDA6SINISTROcargadiaria` — com os underscores APAGADOS. Num ambiente
que fala de coluna, job e pipeline, esse é o caso comum, não a borda.

⚠️ **`splitTextToSize` com largura NEGATIVA devolve uma letra por linha.** Uma
célula longa sem teto de peso levava a largura toda e o cabeçalho virava uma
coluna vertical de letras sobre a vizinha.

⚠️ **Tailwind v3 não gera alfa sobre `currentColor`** (`border-current/40`): a
classe é descartada em SILÊNCIO e a borda cai no cinza do preflight. Conferir
no CSS gerado — e o grep tem que escapar a barra (`border-white\/50`), senão
a verificação diz "ausente" sobre classe que existe.
(ver [[orquestra-caixa-seguro-poc]], que estava fechada — esta é correção, não
fase nova).

**O defeito:** o modelo responde em Markdown por conta própria — o system
prompt de `api/routers/caixa_chat.py` **nem pede** — e os dois consumidores
mostravam cru. A bolha usava `whitespace-pre-wrap`, então o operador lia
`## Status Principais`, `**Emitida**` e tabelas em cano. O PDF exportado tinha
o mesmo problema **mais** emoji virando lixo.

⚠️ **GOTCHA — jsPDF escreve em WinAnsi.** Com as fontes padrão, todo caractere
fora dela vira bytes ilegíveis: `📋` saía **`Ø=ÜË`** e `✅` saía **`'L`**. Não
é bug do texto nem do encoding do banco — é a fonte do PDF. Embutir fonte com
emoji custaria megabytes, então o emoji **sai do PDF e fica na tela**.
Cuidado ao limpar: acentos, travessão (—) e aspas curvas **funcionam** (a
WinAnsi tem as posições 0x80–0x9F), então um corte "acima de U+00FF" levaria
os dois últimos junto. Seta/✓/✗ viram ASCII antes do corte — carregam sentido.

**A forma:** **um parser, dois desenhistas** — `caixa/lib/markdown.ts` lê uma
vez e devolve blocos tipados; `MensagemMarkdown.tsx` desenha em JSX e
`caixa/lib/conversaPdf.ts` desenha no jsPDF. Dois parsers voltariam a
divergir. Sem dependência nova (`react-markdown` só resolveria a tela e o
bundle já passa de 2,8 MB); nada de HTML por string, porque o texto vem de LLM.

💡 **Tirar o desenho do PDF de dentro do `onClick`** foi o que tornou a
exportação verificável: um script Node importa `montarConversaPdf` e gera o
arquivo de verdade. A prova ad-hoc (25 asserções contra a resposta REAL) pegou
**2 defeitos**: `**a *b* c**` não casava (miolo do negrito precisa aceitar
asterisco solto) e o negrito da célula saía em redondo (a regra virou MAIORIA
de caracteres, porque `| ✅ **Emitida** |` tem o emoji fora do negrito).

⚠️ **O front do projeto não tem runner de teste JS** (sem vitest/jest no
`package.json`) — a prova roda por fora, via `npx esbuild` + `node`. Adicionar
`vitest` seria PR à parte; **pendente de decisão do usuário**.

⚠️ **SSH do GitHub caiu de novo nesta VPS** (`kex_exchange_identification`, nas
portas 22 e 443). O contorno que funcionou:
`git -c url."https://github.com/".insteadOf="git@github.com:" push` — usa a
credencial do `gh`. Mesmo sintoma de [[nexxafarma-saneamento-produtos]].
