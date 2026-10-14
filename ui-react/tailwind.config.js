/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}', './examples/**/*.{html,tsx}'],
  // Toggle de tema via classe html.dark (igual à UI legada).
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Superfícies semânticas — trocam com o tema (ver index.css).
        canvas:  'rgb(var(--canvas) / <alpha-value>)',
        panel:   'rgb(var(--panel) / <alpha-value>)',
        edge:    'rgb(var(--edge) / <alpha-value>)',
        ink:     'rgb(var(--ink) / <alpha-value>)',
        dim:     'rgb(var(--dim) / <alpha-value>)',
        action: 'rgb(var(--action) / <alpha-value>)',
        'action-strong': 'rgb(var(--action-strong) / <alpha-value>)',
        'control-border': 'rgb(var(--control-border) / <alpha-value>)',
        focus: 'rgb(var(--control-focus) / <alpha-value>)',
        'primary-control': 'rgb(var(--primary-control) / <alpha-value>)',
        'primary-control-strong': 'rgb(var(--primary-control-strong) / <alpha-value>)',
        'on-action': 'rgb(var(--on-action) / <alpha-value>)',
        success: { DEFAULT: 'rgb(var(--success-ink) / <alpha-value>)', surface: 'rgb(var(--success-surface) / <alpha-value>)' },
        warning: { DEFAULT: 'rgb(var(--warning-ink) / <alpha-value>)', surface: 'rgb(var(--warning-surface) / <alpha-value>)' },
        error: { DEFAULT: 'rgb(var(--error-ink) / <alpha-value>)', surface: 'rgb(var(--error-surface) / <alpha-value>)' },
        info: { DEFAULT: 'rgb(var(--info-ink) / <alpha-value>)', surface: 'rgb(var(--info-surface) / <alpha-value>)' },
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
      // Etapa em execução confirmada: ciclo suave de 1,6 s, só opacidade e
      // escala do anel (sem deslocar layout). Use com `motion-safe:`.
      keyframes: {
        'run-indicator': {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.35', transform: 'scale(0.82)' },
        },
      },
      animation: {
        'run-indicator': 'run-indicator 1.6s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}

