/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
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
      },
    },
  },
  plugins: [],
}

