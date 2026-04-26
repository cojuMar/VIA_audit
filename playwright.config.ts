import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config — drives the Sprint 27 a11y smoke harness in tests/a11y/.
 *
 * The UIs must already be reachable on their dev ports before this runs.
 * In CI, `make up` brings the stack up first.
 */
export default defineConfig({
  testDir: './tests/a11y',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  reporter: process.env.CI ? [['list'], ['junit', { outputFile: 'a11y-junit.xml' }]] : 'list',
  use: {
    headless: true,
    ignoreHTTPSErrors: true,
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
