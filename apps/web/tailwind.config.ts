import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Neutral palette for dark-first UI
        surface: {
          DEFAULT: '#0f1117',
          card: '#161b27',
          hover: '#1e2535',
          border: '#2a3347',
        },
        accent: {
          DEFAULT: '#4f7ef8',
          hover: '#6b93f9',
          muted: '#1e3a8a',
        },
        text: {
          primary: '#e8eaf0',
          secondary: '#8892a4',
          muted: '#4b5568',
        },
        success: '#22c55e',
        warning: '#f59e0b',
        danger: '#ef4444',
        info: '#38bdf8',
      },
    },
  },
  plugins: [],
};

export default config;
