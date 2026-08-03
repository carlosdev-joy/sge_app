// Metadados dos COMPONENTES de malha (F12 — desenho §10): tipo → rótulo,
// chip/cor de identidade, type do React Flow e ícone. Módulo puro (sem
// componente React) de propósito: é importado pelos nós do canvas, pela
// paleta e pelo minimapa do MalhaEditor — o componente não muda de cara entre
// o arrasto e o desenho (regra da paleta das Etapas), e o react-refresh segue
// funcionando nos arquivos de componente.
//
// Identidades (família do canvas de Etapas + escolhas registradas na F12):
//   • Aguarde     — âmbar-600 + Hourglass (idêntico ao Aguarde das Etapas);
//   • Notificação — teal-600 + BellRing (idêntico ao das Etapas);
//   • Início      — emerald-600 + Play (o desenho não fixa o glifo; Play é a
//                   partida e verde é o start do BPMN; contraste 3.8:1);
//   • Fim         — slate-600 + Flag (bandeira de chegada; slate é o terminal
//                   NEUTRO de propósito — vermelho leria como FALHA na visão
//                   de execução; contraste 7.6:1).
// Chips em -600: o glifo branco precisa de 3:1 (WCAG 1.4.11).
import { BellRing, Flag, Hourglass, Play } from 'lucide-react'

export type TipoComponente = 'inicio' | 'aguarde' | 'notificacao' | 'fim'

export const COMPONENTE_META: Record<TipoComponente, {
  rotulo: string
  chip: string        // classes do tile/chip (paleta e card)
  cor: string         // cor sólida p/ o minimapa
  nodeType: string    // type registrado no React Flow
  Icon: typeof Play
}> = {
  inicio: {
    rotulo: 'Início', chip: 'bg-emerald-600 text-white', cor: '#059669',
    nodeType: 'malhaInicio', Icon: Play,
  },
  aguarde: {
    rotulo: 'Aguarde', chip: 'bg-amber-600 text-white', cor: '#d97706',
    nodeType: 'malhaAguarde', Icon: Hourglass,
  },
  notificacao: {
    rotulo: 'Notificação', chip: 'bg-teal-600 text-white', cor: '#0d9488',
    nodeType: 'malhaNotificacao', Icon: BellRing,
  },
  fim: {
    rotulo: 'Fim', chip: 'bg-slate-600 text-white', cor: '#475569',
    nodeType: 'malhaFim', Icon: Flag,
  },
}
