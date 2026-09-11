---
name: orquestra-spec-email-modelos-navegacao
description: "Spec APROVADA 2026-09-11: prévia do corpo na tela (F1 mergeada), catálogo de modelos institucionais (F2 em revisão) e seletor de arquivo do anexo no nó de e-mail do Orquestra"
metadata:
  node_type: memory
  type: project
  originSessionId: 55c7dc0b-089c-4e39-9b3c-c60297f1190c
  modified: 2026-09-11T16:10:46.008Z
---

**Spec:** `docs/spec-email-modelos-e-navegacao.md` (✅ **APROVADA 2026-09-11**; ✅ F1 mergeada; 🔧 **F2 em revisão**). Continuação de [[orquestra-spec-notificacao-email]], que entregou o canal (F1–F4, PRs #388–#391, concluída). Esta trata de **como as pessoas escrevem o aviso**.

**Pedido do usuário (2026-09-11), depois de aprovar um modelo HTML institucional que montamos e validamos numa prévia:** (1) visualizador do corpo direto na tela de configuração; (2) o modelo como opção, "algo que force todos utilizarem o mesmo modelo de comunicação"; (3) no anexo, a mesma navegação dos Utilitários — clica na pastinha, desce da raiz até o arquivo, e o clique já atribui.

**Fases:** F1 prévia (iframe isolado) · F2 catálogo `etl_email_modelo` + migration 112 + interruptor *exigir modelo* · F3 seletor de arquivo reusando `NavegadorPastas` · F4 docs.

**Decisões de arquitetura que o levantamento fixou:**
- **Prévia = `<iframe sandbox srcdoc>` sem `allow-scripts` nem `allow-same-origin`** — é o PRIMEIRO iframe do produto. O repo não tem CSP (`config/nginx.conf` só tem Cache-Control) nem biblioteca de sanitização (`dompurify` existe só como transitivo do `jspdf`).
- **Vínculo VIVO, não cópia**: o nó guarda `modelo_id` e o corpo é lido no envio — trocar o layout no Admin vale para todos sem republicar. O modelo institucional ocupa **24% do limite de corpo** (4.854 de 20.000), e copiar deixaria N cópias para manter.
- **Navegação reusa o que existe**: `NavegadorPastas.tsx` é apresentação PURA e o estado vive em `useNavegadorPastas.ts`. Muda só o endpoint (`GET /email/anexo/listar`, reusando `ssh_arquivos`), porque as raízes do e-mail são outra lista e a permissão é a de editar pipeline.

**✅ Decisão do usuário: "EXIGIDO COM ESCAPE".** O corpo é escolhido numa lista (modelos ativos + **Corpo livre**). O interruptor *exigir modelo* é o endurecimento opcional, desligado por padrão.

**F1 — PR #393 MERGEADA `35bbe2f`:** prévia no painel do nó (`PreviaEmail.tsx` + `previaEmailDados.ts`). A revisão adversarial REPROVOU com 7 defeitos — nenhum de segurança (o isolamento resistiu a script, `javascript:`, top-nav, form, meta-refresh, download e vazamento de CSS). ⚠️ LIÇÕES: `bg-white` cru no escuro = 1,87:1 (usar tokens); altura 300 num dock de 280 nasce fora da tela; embrulhar corpo que já é documento faz o navegador DESCARTAR os atributos do 2º `<body>`; trocar `srcdoc` a cada tecla recarrega o iframe; foco dentro de iframe de origem opaca não devolve teclado ao pai; `fieldset[disabled]` desliga `<button>` descendente (usar `span role=button`); teste de paridade por regex fica VERDE quando a chave é escrita de outra forma.

**F2 — catálogo (branch `feat/email-modelos-f2`):** migration 112 (`etl_email_modelo` + chave `email_exigir_modelo` + semente do modelo institucional como padrão), `api/services/email_modelos.py`, 6 rotas em `routers/email.py`, Admin › E-mail › Modelos com a prévia ao lado, `Select` de modelo no painel do nó, `_ler_modelo` no `EmailOperator`.

**⚠️ DUAS RODADAS de revisão adversarial — a 1ª REPROVOU (6 defeitos + 2 sugestões), a 2ª aprovou com ressalvas depois de 1 defeito NOVO. As regras que sobraram valem para qualquer catálogo:**
1. **Régua do salvar aceita INATIVO, recusa só o INEXISTENTE.** Desativar é o gesto que a API recomenda no 409 da exclusão; recusar inativo no salvar tornaria **insalvável** todo fluxo que usa o modelo (mexer em qualquer outro nó passaria a dar 422).
2. **Interruptor de padronização só vale COM catálogo.** A chave é gravada por MERGE em `etl_app_config` e **não depende da tabela**: ligada sem a 112, o nó novo ficaria insalvável **sem gesto possível na tela**, porque o painel não renderiza a lista quando o catálogo está indisponível. As duas pontas (`GET /email/modelos` e `_config_email_do_admin`) precisam fazer a mesma conta.
3. **Cache de react-query em editor de recurso COMPARTILHADO reverte edição alheia**: reabrir o modelo trazia o corpo velho e o Salvar seguinte desfazia a edição para todos os fluxos. `staleTime: 0` + `gcTime: 0` + `refetchOnMount: 'always'` + invalidar a chave do detalhe — e **desabilitar Salvar enquanto o corpo não chegou** (a lista não traz o corpo, só o tamanho).
4. **LIKE em JSON casa no DELIMITADOR**: `%"modelo_id": 4,%` e `%"modelo_id": 4}%`, senão o 4 casa com o 40. E **falha de leitura PROPAGA** — devolver `[]` diria "não está em uso" e deixaria apagar modelo que N fluxos usam.
5. **Guarda de semente por CATÁLOGO VAZIO, nunca por nome**: renomeado o modelo, a guarda por nome reinsere e cria dois `padrao=1`. Provado no DEV: renomeei, reapliquei, não duplicou.
6. **A tela não afirma o que não sabe**: modelo fora da lista pode ter sido desativado (segue enviando) ou removido (a corrida falha) — a mensagem diz os dois. E toda query que pode falhar precisa de caminho de erro: catálogo que não respondeu não pode sumir em silêncio deixando o backend exigindo o que a tela não oferece.
7. **`len()` onde a coluna é NVARCHAR** deixa emoji estourar — `utf16_len` ([[gotcha-nvarchar-utf16]]).
8. **Teste tautológico**: `assert X == b"" if hasattr(...) else True` vira `assert True` quando o atributo não existe — o Python lê como `(X == b"") if ... else True`.

**Validação da F2:** pytest **5283 passed** + as 8 falhas pré-existentes; `tsc -b` limpo; eslint **195 = 195**; `dist/` refeita; migração aplicada 6× no DEV (5 lotes, 0 erros); **smoke de 22 verificações no ambiente, todas OK** (`smoke_modelos_f2.py` no scratchpad), com o operador rodando dentro do worker.

**Pendências:** F3 (seletor de arquivo do anexo) e F4 (docs). Deploy da F2: migração **112** na 6c, `api/`, `dist/`, `dags/` **com restart do worker** (`email_operator.py` mudou e `dags/utils/` é cacheado — [[orquestra-worker-cacheia-dags-utils]]), `config/` → **n**. Questão aberta da §8: excluir o modelo padrão deixa o catálogo sem padrão (o nó novo volta a nascer em Corpo livre, em silêncio).
