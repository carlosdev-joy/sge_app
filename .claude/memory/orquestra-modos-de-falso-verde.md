---
name: orquestra-modos-de-falso-verde
description: "Os 8 modos de teste que passa verde com o defeito intacto, catalogados na spec da corrida de malha — cada um custou um defeito real"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 80c9c0f8-d96b-4823-bfbd-f3a91475f9ad
  modified: 2026-08-06T20:10:32.122Z
---

Ao longo das 12 fases da spec da corrida de malha (`docs/spec-malha-execucao.md`),
**oito modos distintos de "teste verde com o defeito intacto"** apareceram — cada
um descoberto pagando um defeito real, vários deles ALTOS. Vale passar a lista
adiante em todo prompt de fase que escreva testes:

1. **Dublê que aplica por conta própria uma guarda que mora no `WHERE`** do SQL.
   A mutação "apaga a cláusula" passa verde: o teste prova a si mesmo. (F2, F4, F5)
2. **Dublê que devolve sempre UM caso** e nunca exercita lote — foi assim que
   dois defeitos ALTOS passaram verdes na F2 (o lote de duas madrugadas).
3. **Teste que afirma a MENSAGEM e não o COMPORTAMENTO.** Na F7 o hold do Início
   congelava a corrida em andamento com a suíte verde, porque o único teste do
   caso conferia só o texto do toast.
4. **Dublê que fabrica um dado que o servidor real nunca produz.** Na F8 uma
   guarda estava inerte (a consulta não trazia o campo) e o teste passava porque
   o dublê inventava o valor.
5. **Teste cujo CENÁRIO contradiz o próprio docstring** — e trava o defeito no
   lugar. Na F9 o "não abriu" acusava a malha que ABRIU, protegido por um teste
   cujo texto dizia uma coisa e cujo setup fazia outra.
6. **`grep` no `.tsx` provando texto que nenhum ramo renderiza.** A string existe
   no arquivo; a tela nunca a mostra. (F10)
7. **Dublê mais PERMISSIVO que o contrato** — aceita props que não existem, e o
   cenário fica verde provando uma tela que não existe. (F10)
8. **Teste que entra pela função que já limpa o dado antes**, deixando a guarda
   real nunca exercida. (F11 — e era a única defesa do caminho por onde o defeito
   apareceu.)

**Why:** em todos os casos a suíte estava verde e o defeito estava em produção
esperando. O padrão comum é o teste medir o próprio andaime em vez do sistema.

**How to apply:** depois de escrever um teste, **sabote o código de propósito** e
confirme que ele fica vermelho — e prefira sabotar do jeito que um colega
distraído faria, não do jeito que o teste espera. Para regra que mora em SQL, o
dublê tem de **ler o texto do statement** antes de aplicar a guarda. E todo
conserto precisa do **contraponto**: o teste que garante que a correção não virou
o defeito oposto (barra que some sempre, banner que nunca acende, crédito que
nunca é dado).

Ver [[orquestra-spec-corrida-malha]].
