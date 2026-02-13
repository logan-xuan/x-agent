/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'dark-bg': '#0f172a',
        'dark-card': '#1e293b',
        'dark-border': '#334155',
        'neon-blue': '#38bdf8',
        'neon-purple': '#a78bfa',
        'neon-green': '#34d399',
      },
      boxShadow: {
        'neon': '0 0 15px rgba(59, 130, 246, 0.5)',
        'neon-purple': '0 0 15px rgba(167, 139, 250, 0.5)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }
    },
  },
  plugins: [],
}