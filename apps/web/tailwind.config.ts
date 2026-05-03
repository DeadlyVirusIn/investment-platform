import type { Config } from 'tailwindcss';

/**
 * Phase UI4+ — Elite Design System Tokens (EXACT SPEC).
 *
 * Strict palette (no other colors allowed):
 *   bg-primary    #0B0F17
 *   bg-surface    #121826
 *   bg-elevated   #172033
 *   border-subtle rgba(255,255,255,0.06)
 *   text-primary   #E6EAF2
 *   text-secondary #9AA4B2
 *   text-muted     #6B7380
 *   accent         #3B82F6
 *   success        #22C55E
 *   danger         #EF4444
 *   warning        #F59E0B
 */
const config: Config = {
  darkMode: 'class',
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // Phase 4 — colors point at CSS vars defined in index.css under
      // [data-theme="dark"] and [data-theme="light"]. This makes every
      // existing `bg-surface-*`, `border-surface-*`, `text-text-*` class
      // theme-aware without per-call-site rewrites.
      colors: {
        surface: {
          DEFAULT: 'var(--bg)',
          card:    'var(--surface-1)',
          elev:    'var(--surface-2)',
          muted:   'var(--bg)',
          hover:   'var(--surface-2)',
          border:  'var(--border-subtle)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          hover:   'var(--accent-hover)',
          muted:   'var(--accent-muted)',
          subtle:  'var(--accent-subtle)',
        },
        text: {
          primary:   'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted:     'var(--text-muted)',
          faint:     'var(--text-muted)',
        },
        success: {
          DEFAULT: 'var(--success)',
          muted:   'var(--success-soft)',
        },
        warning: {
          DEFAULT: 'var(--warning)',
          muted:   'var(--warning-soft)',
        },
        danger: {
          DEFAULT: 'var(--danger)',
          muted:   'var(--danger-soft)',
        },
        info: {
          DEFAULT: 'var(--accent)',
          muted:   'var(--accent-soft)',
        },
      },
      fontFamily: {
        sans: ['"Inter"', '-apple-system', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"SF Mono"', 'Menlo', 'Monaco', 'monospace'],
      },
      fontSize: {
        'micro':    ['10px', { lineHeight: '14px', letterSpacing: '0.20em' }],
        'tiny':     ['11px', { lineHeight: '16px', letterSpacing: '0.02em' }],
        'label':    ['12px', { lineHeight: '16px', letterSpacing: '0.01em' }],
        'body':     ['14px', { lineHeight: '22px' }],
        'body-lg':  ['15px', { lineHeight: '24px' }],
        'num-sm':   ['14px', { lineHeight: '18px', letterSpacing: '-0.01em' }],
        'num-md':   ['18px', { lineHeight: '22px', letterSpacing: '-0.015em' }],
        'num-lg':   ['30px', { lineHeight: '34px', letterSpacing: '-0.02em' }],
        'num-xl':   ['36px', { lineHeight: '40px', letterSpacing: '-0.025em' }],
        'headline': ['24px', { lineHeight: '30px', letterSpacing: '-0.015em' }],
      },
      borderRadius: {
        'sm':  '6px',
        'md':  '10px',
        'lg':  '12px',
        'xl':  '16px',
      },
      boxShadow: {
        'card':
          '0 1px 2px rgba(0,0,0,0.22), inset 0 0 0 1px rgba(255,255,255,0.03)',
        'card-hover':
          '0 4px 16px rgba(0,0,0,0.32), inset 0 0 0 1px rgba(59,130,246,0.28)',
        'elevated':
          '0 8px 28px rgba(0,0,0,0.38), inset 0 0 0 1px rgba(255,255,255,0.04)',
        'status-glow':
          '0 0 40px rgba(34, 197, 94, 0.08)',
      },
      transitionTimingFunction: {
        'out-quint': 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
    },
  },
  plugins: [],
};

export default config;
