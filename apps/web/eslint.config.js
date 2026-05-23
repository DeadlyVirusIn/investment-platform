// ESLint v9 flat config. Minimal: enables TS/TSX parsing so `npm run
// lint` runs without policy decisions. Rules intentionally empty —
// add project rules in a follow-up commit once team standards land.

import tsparser from '@typescript-eslint/parser';
import tseslint from '@typescript-eslint/eslint-plugin';
import reactHooks from 'eslint-plugin-react-hooks';

export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'scripts/**'],
  },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsparser,
      parserOptions: {
        ecmaVersion: 2020,
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      '@typescript-eslint': tseslint,
      'react-hooks': reactHooks,
    },
    // ESLint v9 defaults reportUnusedDisableDirectives to 'warn'. With
    // --max-warnings 0 in the npm script that fails the build for the
    // 4 pre-V2 inline disable directives. Turn off until rules land.
    linterOptions: {
      reportUnusedDisableDirectives: 'off',
    },
    rules: {},
  },
];
