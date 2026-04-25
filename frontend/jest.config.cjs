/** @type {import('jest').Config} */
module.exports = {
  preset: 'jest-preset-angular',
  setupFilesAfterEnv: ['<rootDir>/src/setup-jest.ts'],
  testPathIgnorePatterns: ['<rootDir>/node_modules/', '<rootDir>/dist/'],
  testMatch: ['**/*.spec.ts'],
  moduleFileExtensions: ['ts', 'mjs', 'js', 'html'],
};
