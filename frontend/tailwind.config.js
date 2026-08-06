/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Semantic tokens driven by CSS custom properties in index.css, so a
        // single `dark` class on <html> re-themes the whole application
        // without duplicating a palette per mode.
        surface: {
          DEFAULT: 'rgb(var(--surface) / <alpha-value>)',
          raised: 'rgb(var(--surface-raised) / <alpha-value>)',
          sunken: 'rgb(var(--surface-sunken) / <alpha-value>)',
        },
        edge: 'rgb(var(--edge) / <alpha-value>)',
        content: {
          DEFAULT: 'rgb(var(--content) / <alpha-value>)',
          muted: 'rgb(var(--content-muted) / <alpha-value>)',
          subtle: 'rgb(var(--content-subtle) / <alpha-value>)',
        },
        brand: {
          50: '#eef4ff',
          100: '#dce7ff',
          200: '#c0d3ff',
          300: '#96b6ff',
          400: '#6b8dff',
          500: '#4a66f5',
          600: '#3546e8',
          700: '#2c36cc',
          800: '#2831a5',
          900: '#283282',
        },
        success: { DEFAULT: '#10b981', soft: '#064e3b' },
        warning: { DEFAULT: '#f59e0b', soft: '#4a2d05' },
        danger: { DEFAULT: '#ef4444', soft: '#4c1111' },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in': {
          from: { opacity: '0', transform: 'translateX(-8px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        'pulse-ring': {
          '0%': { boxShadow: '0 0 0 0 rgb(74 102 245 / 0.4)' },
          '70%': { boxShadow: '0 0 0 8px rgb(74 102 245 / 0)' },
          '100%': { boxShadow: '0 0 0 0 rgb(74 102 245 / 0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.25s ease-out',
        'slide-in': 'slide-in 0.25s ease-out',
        shimmer: 'shimmer 1.6s infinite',
        'pulse-ring': 'pulse-ring 2s infinite',
      },
    },
  },
  plugins: [],
};
