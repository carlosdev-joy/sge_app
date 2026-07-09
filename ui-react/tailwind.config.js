import colors from 'tailwindcss/colors'
import animate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  // Toggle de tema via classe html.dark (igual à UI legada).
  darkMode: 'class',
  theme: {
    // Usado só pela seção Caixa Seguro (src/caixa); nenhuma outra tela usa .container.
    container: {
      center: true,
      padding: '2rem',
      screens: { '2xl': '1400px' },
    },
    extend: {
      colors: {
        // ── Tokens shadcn da seção Caixa Seguro (src/caixa) ─────────────
        // Resolvem para CSS vars escopadas em .caixa-theme (src/caixa/theme.css);
        // fora da seção as vars não existem — não usar em telas do Orquestra.
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
        secondary: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--secondary-foreground))' },
        destructive: { DEFAULT: 'hsl(var(--destructive))', foreground: 'hsl(var(--destructive-foreground))' },
        muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
        accent: { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--accent-foreground))' },
        popover: { DEFAULT: 'hsl(var(--popover))', foreground: 'hsl(var(--popover-foreground))' },
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
        caixa: {
          blue: 'hsl(var(--caixa-blue))',
          orange: 'hsl(var(--caixa-orange))',
          black: 'hsl(var(--caixa-black))',
          aqua: 'hsl(var(--caixa-aqua))',
          gray: 'hsl(var(--caixa-gray))',
        },
        // DEFAULT/foreground do tema CAIXA + escala numerada padrão preservada
        // (o Orquestra usa blue-400, green-500 etc. — o spread mantém tudo).
        blue:   { ...colors.blue,   DEFAULT: 'hsl(var(--blue))',   foreground: 'hsl(var(--blue-foreground))' },
        orange: { ...colors.orange, DEFAULT: 'hsl(var(--orange))', foreground: 'hsl(var(--orange-foreground))' },
        yellow: { ...colors.yellow, DEFAULT: 'hsl(var(--yellow))', foreground: 'hsl(var(--yellow-foreground))' },
        green:  { ...colors.green,  DEFAULT: 'hsl(var(--green))',  foreground: 'hsl(var(--green-foreground))' },
        // Superfícies semânticas — trocam com o tema (ver index.css).
        canvas:  'rgb(var(--canvas) / <alpha-value>)',
        panel:   'rgb(var(--panel) / <alpha-value>)',
        edge:    'rgb(var(--edge) / <alpha-value>)',
        ink:     'rgb(var(--ink) / <alpha-value>)',
        dim:     'rgb(var(--dim) / <alpha-value>)',
        orq: {
          bg:      '#0f1117',
          surface: '#1a1d27',
          border:  '#2a2d3a',
          primary: '#4f8ef7',
          success: '#22c55e',
          warning: '#f59e0b',
          error:   '#ef4444',
          text:    '#e2e8f0',
          muted:   '#94a3b8',
        },
        cvp: {
          blue:  '#1A5FA8',
          blued: '#0D3D6B',
          mid:   '#0F4C88',
        },
      },
      // Gradientes do tema CAIXA (vars escopadas em .caixa-theme/theme.css).
      // Sem estes, bg-gradient-primary não resolvia e os botões que o usam
      // (Localizar PDF, Compartilhar no painel de IA…) ficavam brancos.
      backgroundImage: {
        'gradient-primary': 'var(--gradient-primary)',
        'gradient-dark': 'var(--gradient-dark)',
      },
    },
  },
  // tailwindcss-animate: utilitários animate-in/out usados pelos shadcn de src/caixa.
  plugins: [animate],
}

