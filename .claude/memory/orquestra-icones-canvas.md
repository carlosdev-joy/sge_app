---
name: orquestra-icones-canvas
description: "Auditoria de ícones do canvas de Etapas — PRs #237/#238/#249 EM PRODUÇÃO (medalhão Hourglass no Aguarde, Split/Table2/DatabaseZap, shell slate-600, WCAG -600, handles encostados, orientação da malha); backlog: Malha, badges da Lista, ChipTipo"
metadata: 
  node_type: memory
  type: project
  originSessionId: f83b731c-0876-4438-b369-1dd4f50c0621
  modified: 2026-08-13T02:40:24.007Z
---

Auditoria completa dos ícones do canvas de Etapas do [[orquestra-sge-app]],
nascida do feedback "nó Aguarde apareceu sem ícone interno" (a barra BPMN pura
falhou com o operador). ✅ **PR #237 MERGEADA em 2026-08-02** (main 89bf4e4).

**Identidades vigentes** (paleta=canvas=painel=minimapa): datastage Database
azul · shell Terminal **slate-600** (saiu do âmbar: 3 significados) · python
FileCode2 green-600 · storedproc **DatabaseZap** roxo · http Globe orange-600 ·
sql **Table2** violeta · decisao **Split** índigo (GitBranch ficou SÓ no chip
do Pipeline) · notificacao BellRing teal-600 · aguarde **Hourglass** em
medalhão sobre barra âmbar-600 (validado pelo usuário; Clock/Timer foram
descartados por insinuar espera por horário). Chips -600 = contraste WCAG
3:1 do glifo branco. Transversal: hover dark, outline tracejado em isNew,
handles 14px, ponto de pendência no Aguarde, fallback de tipo no EtapaNode.

**Gotcha de processo:** `TYPE_META['sql']` era entrada MORTA (interceptações
hardcoded antes dela); agora documenta a identidade canônica — nós especiais
seguem hardcoded por superfície, mudar identidade = tocar paleta, nó, painel e
minimapa.

✅ PR #237 deployada e validada pelo usuário em 2026-08-02. Na sequência, o
feedback "pontos de conexão muito longe" virou a **PR #238 (MERGEADA
2026-08-02, main 3eaeaf9)**: invólucro dos 5 nós encolheu de 128→48px (w-12)
para os handles encostarem no desenho; rótulos mantêm 128px transbordando
centrados. Encolhimento UNIFORME preserva layouts salvos (posição top-left);
hit-test conferido por conta na revisão adversarial (área clicável = invólucro
antigo deslocado −40px). GOTCHA de geometria: handles ancoram na borda do
BOUNDING BOX do nó, não no visual — largura do invólucro é o que define onde a
aresta chega.

✅ #237/#238 deployadas e validadas pelo usuário. **PR #249 (2026-08-03,
mergeada): orientação do diagrama da malha** — horizontal|vertical por malha,
persistida no servidor (migration 074 etl_malha.orientacao); toggle ⇄/⇅ na
Montagem; handles/arestas acompanham; Execução herda; layoutGrafo com eixo
paramétrico PURO (FluxoEditor byte-idêntico, provado mecanicamente). GOTCHA:
revert de erro de mutation deve usar UMA fonte (o valor exibido pré-gesto),
nunca servidor+oposto-da-tentativa (estado híbrido em sessão degradada).
✅ **Deploy FEITO em 2026-08-12** (074 na 6c + api + front, sem regerar DAGs) —
ver [[orquestra-deploy-trem-producao]]. Variante "direita→esquerda" fica como
opção futura se o usuário confirmar.

📌 **BACKLOG (fora da PR de propósito):** alinhar `JOB_COLORS` da Malha aos hex
do TYPE_META (shell verde, python violeta lá — ensina outra língua); badges do
modo Lista sem os tipos especiais + dark-only (junto da "opção B" em
[[orquestra-grafia-pipeline-name]]); extrair componente `ChipTipo` (4 hardcodes);
export órfão `pipelineUtils.typeBadgeColor` divergente.
