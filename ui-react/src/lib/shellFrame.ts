// Moldura do conteúdo do AppShellV2, decidida pela rota.
// - bleed: a página pinta a tela inteira (tema/fundo próprios); sem a moldura
//   sobra uma faixa clara (bg-canvas) ao redor do conteúdo escuro.
// - wide: workspace de um Pipeline. O canvas usa a largura disponível da área de
//   conteúdo, com margem lateral compacta (12 px no celular, 16 px a partir de
//   sm), nunca maior que o p-6 da moldura anterior em nenhuma resolução; os
//   destinos sem canvas limitam o próprio conteúdo à largura anterior
//   (WORKSPACE_FRAMED_CONTENT).
// - framed: demais telas, centralizadas em até 1600 px, como antes.
export type ShellFrame = 'bleed' | 'wide' | 'framed'

const FULL_BLEED_PREFIXES = ['/caixa-seguro']

export function shellFrame(pathname: string): ShellFrame {
 if (FULL_BLEED_PREFIXES.some(p => pathname === p || pathname.startsWith(p + '/'))) return 'bleed'
 const [first, second] = pathname.split('/').filter(Boolean)
 return first === 'pipelines' && !!second && second !== 'novo' ? 'wide' : 'framed'
}

export const SHELL_FRAME_CLASS: Record<ShellFrame, string> = {
 bleed: 'min-h-full',
 wide: 'min-w-0 px-3 sm:px-4 py-6',
 framed: 'p-6 max-w-[1600px] mx-auto',
}

// Largura útil da moldura anterior (1600 px menos o p-6): Visão geral,
// Configuração e Versões não mudam de largura no workspace amplo.
export const WORKSPACE_FRAMED_CONTENT = 'max-w-[1552px]'
