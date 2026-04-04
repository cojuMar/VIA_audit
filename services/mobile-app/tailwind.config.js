/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  safelist: [
    // Severity badge dynamic classes
    'bg-red-100', 'border-red-500', 'text-red-900', 'text-red-700', 'bg-red-50', 'border-red-400',
    'bg-orange-100', 'border-orange-500', 'text-orange-900', 'text-orange-700', 'bg-orange-50',
    'bg-yellow-100', 'border-yellow-500', 'text-yellow-900', 'text-yellow-700', 'bg-yellow-50',
    'bg-blue-100', 'border-blue-500', 'text-blue-900', 'text-blue-700', 'bg-blue-50',
    'bg-green-100', 'border-green-500', 'text-green-900', 'text-green-700', 'bg-green-50',
    // Priority badge classes
    'bg-red-600', 'bg-orange-500', 'bg-yellow-500', 'bg-green-500', 'bg-gray-400',
    // Risk level ring colors
    'ring-red-500', 'ring-orange-500', 'ring-yellow-500', 'ring-green-500',
    // Finding border classes
    'finding-critical', 'finding-high', 'finding-medium', 'finding-low',
  ],
  theme: {
    extend: {
      screens: {
        xs: '375px',
      },
      minHeight: {
        'tap': '44px',
      },
    },
  },
  plugins: [],
}
