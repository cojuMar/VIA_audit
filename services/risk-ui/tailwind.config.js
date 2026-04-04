/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        risk: {
          critical: '#dc2626',
          high: '#ea580c',
          medium: '#ca8a04',
          low: '#16a34a',
        },
      },
    },
  },
  plugins: [],
};
