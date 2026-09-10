---
name: orquestra-etapas-lista-tabela
description: "Tela Etapas (/jobs): busca sem filtro lista tudo, nome do pipeline copiável e colunas arrastáveis com largura lembrada"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8a380743-1bf5-4253-ace6-207c3d764c4b
  modified: 2026-09-02T14:44:00.640Z
---

Ajustes da tela **Etapas** (`/jobs`, `perm: tela_jobs`), visão **Lista** —
PR #355 mergeada 2026-09-02 (`0bf222d`), ⏳ **deploy do `dist/` pendente**.

## Onde a tela vive

| Arquivo | O que é |
|---|---|
| `ui-react/src/pages/Jobs.tsx` | a tela; toggle Lista ↔ Fluxo, filtros, tabela |
| `ui-react/src/components/etapas/FluxoEditor.tsx` | o canvas (@xyflow/react) |
| `ui-react/src/components/etapas/JobTypeFields.tsx` | campos por tipo — **fonte única**: vale na Lista E no Fluxo |
| `ui-react/src/pages/Fluxos.tsx` | rota `/fluxos`, o MESMO editor em tela dedicada |

## O que mudou

1. **Buscar sem filtro lista TUDO.** O botão ficava desabilitado e havia um
   toast "Informe ao menos um filtro". ⚠️ **O backend sempre aceitou filtro
   vazio** (`where_sql` só entra se houver filtro) — era só a tela que travava.
   Sem filtro, o rótulo do botão vira "Buscar todas as etapas".
2. **Nome do pipeline copiável** na Lista (a coluna Etapa já tinha; a Pipeline,
   que estoura mais, só tinha `title`).
3. **Colunas arrastáveis** — `components/ui/useColunasRedimensionaveis.tsx` +
   `AlcaColuna.tsx`, **reutilizáveis em outras tabelas**. Largura no
   localStorage por tabela (`orq.<id>.colunas`); duplo clique na alça restaura.

## ⚠️ Armadilhas do redimensionamento (valem para a próxima tabela)

- A alça mora DENTRO do `<th>`, ao lado do botão de ordenar: **sem
  `stopPropagation()` cada arrasto reordena a coluna**.
- `table-fixed` + `<colgroup>` são obrigatórios — sem eles o navegador
  redistribui as larguras e o arrasto não gruda.
- **`localStorage` LANÇA** em janela privada / site data bloqueado: `try/catch`
  na leitura E na escrita, senão a tela cai por causa de uma largura.
- Piso de 56px por coluna; sem ele o arrasto some com a coluna sem volta.
- Setas + `tabIndex` na alça: arrastar não pode ser a única forma.

🧪 `tests/test_etapas_lista.py` (11 testes). ⚠️ **Falso verde que aconteceu
aqui:** o teste do piso procurava `Math.max(MIN_PX` no arquivo inteiro e passava
mesmo com o arrasto sem piso, porque o handler de TECLADO usa a mesma expressão.
Teste que lê fonte precisa mirar o handler certo, não o arquivo.

⚠️ **Não há Chrome na VPS** — nenhuma validação visual automatizada é possível
aqui; o DEV (`dist/` é volume, aparece na hora) é o caminho para o usuário ver.
Ver [[orquestra-fluxo-etapas]] para o histórico do editor e o backlog de ondas.
