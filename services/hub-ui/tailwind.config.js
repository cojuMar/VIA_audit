/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Semantic surface colors — driven by CSS variables, theme-aware
        surface: {
          base:    'var(--surface-base)',
          raised:  'var(--surface-raised)',
          overlay: 'var(--surface-overlay)',
          sunken:  'var(--surface-sunken)',
        },
        // Semantic text colors
        ink: {
          primary:   'var(--ink-primary)',
          secondary: 'var(--ink-secondary)',
          muted:     'var(--ink-muted)',
          inverse:   'var(--ink-inverse)',
        },
        // Semantic border colors
        line: {
          DEFAULT: 'var(--line)',
          focus:   'var(--line-focus)',
          strong:  'var(--line-strong)',
        },
        // Brand / accent
        brand: {
          DEFAULT:  'var(--brand)',
          hover:    'var(--brand-hover)',
          muted:    'var(--brand-muted)',
          text:     'var(--brand-text)',
          subtle:   'var(--brand-subtle)',
        },
        // Status colors (theme-aware)
        status: {
          success: 'var(--status-success)',
          warning: 'var(--status-warning)',
          danger:  'var(--status-danger)',
          info:    'var(--status-info)',
        },
      },
      boxShadow: {
        card:     'var(--shadow-card)',
        'card-lg': 'var(--shadow-card-lg)',
        input:    'var(--shadow-input)',
      },
      ringColor: {
        brand: 'var(--brand)',
      },
    },
  },
  plugins: [],
};
