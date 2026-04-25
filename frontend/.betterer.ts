import { angular } from '@betterer/angular';

/**
 * Incremental quality gates (see https://phenomnomnominal.github.io/betterer).
 * Tracks adopting `strictTemplates` in the compiler without having to turn it on everywhere at once.
 * Run `ng lint` separately; `@betterer/eslint` is omitted because Betterer 5.x targets ESLint 8 (legacy
 * config) while this app uses ESLint 9 with `eslint.config.js` flat config.
 */
export default {
  'stricter template compilation': () =>
    angular('./tsconfig.app.json', { strictTemplates: true }).include(
      './src/**/*.ts',
      './src/**/*.html',
    ),
};
