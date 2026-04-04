/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      typography: {
        DEFAULT: {
          css: {
            color: '#d1d5db',
            a: { color: '#818cf8' },
            strong: { color: '#f9fafb' },
            h1: { color: '#f9fafb' },
            h2: { color: '#f9fafb' },
            h3: { color: '#f9fafb' },
            h4: { color: '#f9fafb' },
            code: { color: '#a5b4fc', backgroundColor: '#1f2937', padding: '0.2em 0.4em', borderRadius: '0.25rem' },
            'code::before': { content: '""' },
            'code::after': { content: '""' },
            pre: { backgroundColor: '#111827', color: '#d1d5db' },
            blockquote: { color: '#9ca3af', borderLeftColor: '#4f46e5' },
            'ul > li::marker': { color: '#6366f1' },
            'ol > li::marker': { color: '#6366f1' },
            hr: { borderColor: '#374151' },
            th: { color: '#f9fafb' },
            td: { color: '#d1d5db' },
          },
        },
      },
    },
  },
  plugins: [
    // prose classes via inline styles to avoid needing @tailwindcss/typography plugin
  ],
}
