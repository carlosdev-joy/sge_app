# Percepção visual e direção para toda a ferramenta

## Intenção

O público inclui autores de pipelines, operadores e responsáveis por processos. A interface precisa ajudar cada pessoa a localizar o trabalho, reconhecer o contexto e agir com segurança. Uma ferramenta premium pode oferecer funções avançadas sem exigir que o usuário compreenda toda a arquitetura para começar.

Objetivos: hierarquia perceptível em poucos segundos; conteúdo legível; ações previsíveis; espaço útil para o fluxo; mesma linguagem em todos os módulos; operação com teclado; temas claro/escuro completos. Estas são metas de projeto, a medir com usuários, não resultados já comprovados.

## O que a observação externa sugere

| Referência | Percepção observada | Aproveitar no Orquestra | Refinamento necessário |
|---|---|---|---|
| Informatica Explore | Catálogo orientado a tabela, filtros e localização | Encontrar antes de editar; breadcrumb e filtros claros | Tornar caminhos e identidade menos dispersos; testar legibilidade/densidade |
| Informatica Taskflow | Biblioteca esquerda, grafo central e propriedades inferiores | Configuração contextual e separação entre passos | Preservar canvas dominante e inspector lateral previsto no Orquestra; não copiar um painel que comprima o desenho |
| Informatica Monitor | Estrutura própria para histórico e detalhe da instância | Contexto da corrida e subtarefas | Evidenciar diferença entre definição e instância; My Jobs não representa todo o histórico |
| Databricks Tasks/Runs | Tarefas no desenho e sidebar de configuração; Graph/Timeline/List na corrida | Exposição progressiva e múltiplas leituras da mesma instância | Limitar largura dos painéis, evitar excesso de seção sempre aberta e manter identidade ao alternar visão |
| Control-M Planning | Biblioteca, canvas, propriedades laterais e diagnóstico inferior | Domínios de autoria/operação e validação acessível | Reduzir competição entre barras e ícones; agrupar ações conforme responsabilidade |
| Control-M Forecast/Monitoring | Estado, previsão e causa/impacto da espera | Explicar situação e consequência | Diferenciar fato, previsão e simulação; cor sozinha não comunica a causa |

Estas são interpretações do recorte examinado, não avaliação integral da acessibilidade ou do design dos fornecedores. Control-M foi visto em tours, não em tenant operacional. Não foi obtida uma captura atual completa do DEV Orquestra nesta rodada; a avaliação local se baseia em fonte, documentos e mockups referenciados.

## Identidade visual recomendada

**Assinatura:** uma trilha de contexto operacional que deixa sempre claro objeto, versão, ambiente e modo. O canvas usa superfícies calmas e nós com hierarquia previsível. O painel de diagnóstico explica o que precisa acontecer, com links ao objeto e à corrida corretos.

Usar a identidade ORQ e os tokens de marca já existentes. O azul identifica ação/seleção; o estado operacional tem semântica própria. Um pipeline selecionado não passa a parecer em execução. Formas, ícones e texto distinguem objetos sem exigir memorizar uma paleta para cada tipo.

Títulos e ações alinhados à esquerda; números operacionais alinhados à direita e com dígitos tabulares. O topo oferece uma ação principal por contexto e poucas ações secundárias. Espaço vazio separa grupos; cards são usados para unidades realmente independentes, não para cada campo.

## O que significa facilidade de uso

- Nome do objeto e modo explícitos: “Editando rascunho”, “Versão publicada” ou “Execução de 12/10”.
- Primeiro nível oferece tarefas frequentes; opções avançadas aparecem por expansão, mantendo os valores configurados visíveis no resumo.
- Botões informam o efeito: “Salvar rascunho”, “Publicar versão”, “Abrir execução”, conforme contrato real. Não trocar nomes operacionais existentes sem validar o processo.
- Mesma ação mantém nome, ícone e posição relativa em telas equivalentes.
- Estado vazio orienta uma próxima ação disponível; erro descreve causa conhecida e alternativa. Se a fonte não informou causa, declarar isso.
- Mudar tema, densidade ou layout não muda dependência, agenda, permissão ou parâmetros.
- Retornar à lista conserva filtros; voltar de um pipeline à malha conserva corrida e seleção.

## Critério de percepção para a revisão

Em cada prancha/tela, o agente deve responder: qual é o objeto? Em qual contexto estou? Qual a situação atual? Qual ação é principal? O que posso investigar? Qual informação secundária pode ser recolhida? Se isso depender de ler várias barras ou tooltips, rever a hierarquia.

Na avaliação com usuários, medir conclusão das jornadas, erros de alvo/ação, necessidade de ajuda e perda de contexto. Não definir “premium” por efeitos decorativos ou quantidade de elementos na tela.
