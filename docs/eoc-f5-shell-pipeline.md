# EOC-F5 — Shell e piloto visual Pipeline

Base: DEV2.23.0, `120cced561060776b323938925ff991bef7ca97c`. Referências: SPEC consolidada §EOC-F5, contrato/matriz Pipeline52c0c589, pacote de análise41ac369 e design-global (pranchas claro/escuro). Mantém identidade ORQ/navy, fonte/tokens/densidade da F4 e todos os contratos de execução/configuração.

## Inventário e decisão do menu

`src/lib/nav.ts` é a autoridade vigente:23destinos registrados nos grupos Operação, Construção, Governança & Dados, BI, Caixa Seguro, Agentes e Administração. `App.tsx` deriva as rotas; `useVisibleNav` filtra RBAC/capabilities. Jobs/Fluxos conservam aliases e concessões, ocultos na navegação contextual habilitada. Ordens, destinos, filtros RBAC e pós-login são preservados byte a byte nesta fase; não há evidência atual de frequência por público para inventar outra ordem. O vocabulário Projetar/Operar das pranchas é candidato, não autorização de remapeamento.

A apresentação passa a ter grupos legíveis, nomes completos, rótulos acessíveis mesmo recolhida, menu224px expandido/56px recolhido e targets44px. No mobile fechado, o drawer é inert; aberto tem diálogo, Esc, ciclo de Tab e retorno de foco. Botões exclusivos de desktop/mobile são montados somente no modo correto para evitar focáveis ocultos no trap.

## Tese espacial e contexto

Objeto/ambiente/definição/mode e ação no cabeçalho → cinco destinos → ferramenta/canvas/lista → propriedades. Margem horizontal workspace12/16px e vertical16px, sem moldura repetida. Títulos/breadcrumbs longos quebram; controles/ações se reorganizam no mobile. O main tem min-width0 para conter overflow local. Catálogo reaproveita títulos e controles F4; filtros e retorno permanecem nas mesmas queries.

Montagem oferece **Desenho/Lista**. Lista é o padrão inicial abaixo768px; desktop mantém desenho. Mostra etapas/tipo/entradas reais da definição e usa a mesma seleção/guard do inspector. Não cria outro editor ou payload. O canvas permanece montado/oculto na alternância; viewport/seleção não são descartados. Biblioteca/propriedades continuam recolhíveis sem remontar formulários; staging continua independente de alterações aplicadas/salvas. Lista permite consultar/configurar sem depender de drag. Biblioteca é inicialmente recolhida abaixo1024px como já era na base.

Execução conserva Gráfico/Tabela e corrida/etapa/tentativa nas URLs. Cinco abas, aliases, rotas, permissões e ações primárias reais permanecem. A fase não implementa motor, envia alertas ou altera dependências.

## Evidência e limites

TypeScript/build final aprovados, lint sem assinatura nova. Suíte7915PASS/mesmos8IDs de falha/51SKIP;271dirigidos de contexto/montagem/execução/inspector/catálogo/nav/migrations. Fontes alteradas sem NUL; NAV/App/aliases/backend/motor sem alteração.

Navegador sobre fixture DEV própria sem publicação/execução:1440/1280/947/390×temas, cinco abas, ação Iniciar edição visível, lista selecionável pelo teclado, painéis preservando seleção, menu mobile com ciclo/Esc. O smoke de staging/save usa a mesma sessão/fence e espera a resposta real PUT, decodificando sql_json quando o formulário usa sua representação legada string. Evidência final em `/root/orquestra-eoc-evidencias/f5/native.json` e cleanup.json. Revisão independente em independent-review.md; scanner de layout antes/depois sem achados.

Capturas só de dados sintéticos/fixture própria. A evidência de navegador não substitui piloto dos públicos externos ou métricas de grande volume da F6. Nem matrizes desta fase autorizam main/produção. Roteiro da2.24.0 inclui backup DEV, migration175 idempotente, hashes/health/versão e smoke pós-deploy.
