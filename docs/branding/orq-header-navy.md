# Header ORQ Navy — entrega independente

Fonte: [spec aprovada](https://app.notion.com/p/3da9f9fc3e22816fa9c1f5ece718cd4a),
cópia em orq-header-navy-spec.md. Baseline main39555e6 após F1/F2/F3.

Produção altera somente HeaderV2: fundo sólido via --brand-navy (4 20 60),
igual ao login nos dois temas. Altura52+filete4, todos os breakpoints, logo,
CAIXA, controles, dropdowns, foco, APIs e navegação preservados. Nenhuma nova
cor ou asset. Documentos históricos F1/F2/F3 não foram modificados; somente a
expectativa da superfície no smoke ativo acompanha a nova decisão visual.

## Contraste medido

Medições de estilos computados em Chromium, alpha composto com o fundo.
No gradiente anterior, usa-se o menor contraste entre seus três stops (limite
conservador, não amostragem da posição exata). Navy sólido permite medida exata.
Valores iguais nos dois temas. Script reproduzível: smoke_orq_header_contrast.py.

| Elemento | Gradiente anterior (mínimo) | Navy |
|---|---:|---:|
| Branco principal / logo branco | 6,47:1 | 17,94:1 |
| Versão (branco75%) | 4,40:1 | 10,30:1 |
| Título (branco90%) | 5,58:1 | 14,57:1 |
| Busca, tema, sino e nome (branco80%) | 4,78:1 | 11,62:1 |
| Iniciais sobre avatar translúcido | 4,19:1 | 9,81:1 |
| Foco branco2px | 6,47:1 | 17,94:1 |
| Contador branco/vermelho | 3,76:1 | 3,76:1 |

Hover final: busca17,94:1, tema/sino/perfil13,82:1. Divisor decorativo CAIXA|ORQ:
2,19:1 no Navy; não comunica estado nem é controle. Logo e marca CAIXA também
conferidos visualmente; assets/fallback/tamanho não mudaram.

Limitação preexistente: texto9px do contador vermelho permanece abaixo de4,5:1.
A troca de fundo não muda a relação branco/vermelho; não se declara conformidade
AA global do header. Correção do contador exige decisão em ajuste separado,
pois a spec limita mudanças de controles à perda de contraste causada pelo Navy.
A análise do script cobre elementos sobre o header e os fundos diretos; não
substitui auditoria de todas as superfícies descendentes dos dropdowns.

## Validação

- Build TypeScript/Vite aprovado; dist atualizado.
- Baseline recente da main39555e6 reutilizado da validação final F3 (mesmo
  conteúdo versionado): ESLint193; pytest5405pass/50skip/8falhas.
- Alteração: ESLint193, zero novos; pytest5405pass/50skip e mesmas8falhas.
- Smokes F1/F2/F3 aprovados, incluindo dez larguras1440/1280/1100/1024/900/
  768/767/640/360/320 nos dois temas, SPA/RBAC, perfil/notificações/teclado,
  histórico e logout. Sem alteração no código do login.
- Inspeção visual desktop e320px aprovada; fundo none + rgb(4,20,60) conferido.
- Revisão adversarial aprovada; sem perda de contraste causada pela mudança.

## Deploy

Frontend dist apenas, sem migration/dependência/backend. DEV para avaliação;
produção pendente. Conferência manual: comparar header com painel de marca do
login, alternar tema, redimensionar janela e navegar pelos controles por Tab.
Merge da PR independente somente com autorização do usuário.

## Ajuste solicitado pelo usuário após avaliação do DEV

O pedido seguinte substitui as restrições anteriores de preservar a variante
monocromática do header e o gradiente do perfil. Brand agora consome a mesma
variante white usada no login: orbital colorido e letras brancas, com o asset
original e dimensões existentes. Dropdown do usuário usa o mesmo token Navy
sólido do header nos dois temas. Sem alteração nos dados/teclado/logout.
Smokes verificam ausência de filtro monocromático, máscara branca das letras e
fundo Navy no perfil. Esta complementação integra a PR411 ainda aberta.
