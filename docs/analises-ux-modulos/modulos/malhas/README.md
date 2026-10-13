# Malha

Malha é a composição de pipelines e suas condições de negócio/execução. O grafo entre pipelines e o grafo de etapas dentro do pipeline possuem níveis e autoridades distintos.

Leia [conceitos e reestruturação](conceitos-e-reestruturacao.md), [referência Control-M](../../referencias/control-m/jornadas-e-limites.md), [glossário](../../geral/glossario-e-nomenclatura.md) e a documentação local vigente da corrida de malha antes de desenhar substituições.

O estudo propõe correlacionar dependências pela data de negócio/corrida, separar agenda de evento e recurso, explicar bloqueio e preservar snapshots. Eventos AND/OR, calendários, recursos globais, SLA/forecast e reutilização são candidatos sujeitos aos contratos do motor. A ampliação para Malha foi solicitada pelo usuário; não é parte automática da SPEC Pipeline.

Perguntas para o agente: sucesso de qual instância libera qual sucessor? Como tratar predecessor não agendado? Quem ocupa o recurso? O que uma recuperação repetirá? Como retornar da corrida do pipeline à mesma instância da malha?
