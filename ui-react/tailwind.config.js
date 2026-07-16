/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
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
    },
  },
  plugins: [],
}

