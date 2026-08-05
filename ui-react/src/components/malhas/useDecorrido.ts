// O hook do relógio LOCAL da corrida (Decisão 60). Fica à parte de
// `tempoCorrida.ts` de propósito: aquele módulo é puro e testável com o
// relógio deslocado, e um import de React ali tiraria dele exatamente a
// propriedade que o torna confiável.
import { useEffect, useState } from 'react'

/** Cadência do redesenho com corrida em voo. Grossa por dois motivos: o texto
 *  tem granularidade de minuto (§9.4), e o alarme de dado velho (90 s)
 *  precisa aparecer com atraso de no máximo um tique. */
const TIQUE_VIVO_MS = 10_000
/** Sem nada em voo o relógio continua andando — só devagar. Parar o tique
 *  faria o carimbo de frescor congelar em "agora" numa aba aberta há 20 min,
 *  que é exatamente a mentira que a Decisão 60 existe para matar. */
const TIQUE_PARADO_MS = 60_000

/** `Date.now()` que re-renderiza a cada tique.
 *
 *  É o único relógio que o DECORRIDO ("há 42 min") e o FRESCOR ("atualizado
 *  agora") consultam — os dois derivam dele com as funções puras de
 *  `tempoCorrida.ts`, e nenhum dos dois toca `apurado_em`. */
export function useDecorrido(ativo: boolean): number {
  const [agora, setAgora] = useState(() => Date.now())
  useEffect(() => {
    const ms = ativo ? TIQUE_VIVO_MS : TIQUE_PARADO_MS
    const id = setInterval(() => setAgora(Date.now()), ms)
    return () => clearInterval(id)
  }, [ativo])
  return agora
}
