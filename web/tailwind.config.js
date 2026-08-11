/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: { extend: {
    colors: {
      ink: 'rgb(var(--ink) / <alpha-value>)',
      muted: 'rgb(var(--muted) / <alpha-value>)',
      line: 'rgb(var(--line) / <alpha-value>)',
      canvas: 'rgb(var(--canvas) / <alpha-value>)',
      surface: 'rgb(var(--surface) / <alpha-value>)',
      primary: 'rgb(var(--primary) / <alpha-value>)',
      'primary-soft': 'rgb(var(--primary-soft) / <alpha-value>)',
      danger: 'rgb(var(--danger) / <alpha-value>)',
      'danger-line': 'rgb(var(--danger-line) / <alpha-value>)',
      'danger-soft': 'rgb(var(--danger-soft) / <alpha-value>)',
      warning: 'rgb(var(--warning) / <alpha-value>)',
      'warning-line': 'rgb(var(--warning-line) / <alpha-value>)',
      'warning-soft': 'rgb(var(--warning-soft) / <alpha-value>)',
    },
    fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'] },
  } },
  plugins: [],
}
