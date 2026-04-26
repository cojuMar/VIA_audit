/**
 * Sprint 27 a11y smoke harness — @axe-core/playwright across each UI's primary route.
 *
 * Runs against the live dev stack. The acceptance criterion is:
 *   "axe-core reports zero serious/critical violations on the smoke-tested routes."
 *
 * To run locally:
 *   1. `make up` (or `docker compose up -d`) so each UI is reachable.
 *   2. `npm install -D @playwright/test @axe-core/playwright`
 *   3. `npx playwright test tests/a11y`
 *
 * In CI this runs after the infra-up + flyway steps in .github/workflows/ci.yml.
 */
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// Route maps to (UI name, dev URL, primary route to scan).
// `primary route` is the page a freshly-logged-in user would land on.
const ROUTES = [
  { ui: 'hub-ui',            url: 'http://localhost:5173/' },
  { ui: 'framework-ui',      url: 'http://localhost:5174/' },
  { ui: 'tprm-ui',           url: 'http://localhost:5175/' },
  { ui: 'trust-portal-ui',   url: 'http://localhost:5176/' },
  { ui: 'monitoring-ui',     url: 'http://localhost:5177/' },
  { ui: 'people-ui',         url: 'http://localhost:5178/' },
  { ui: 'pbc-ui',            url: 'http://localhost:5179/' },
  { ui: 'integration-ui',    url: 'http://localhost:5180/' },
  { ui: 'ai-agent-ui',       url: 'http://localhost:5181/' },
  { ui: 'risk-ui',           url: 'http://localhost:5182/' },
  { ui: 'audit-planning-ui', url: 'http://localhost:5183/' },
  { ui: 'esg-board-ui',      url: 'http://localhost:5184/' },
  { ui: 'dashboard-ui',      url: 'http://localhost:5185/' },
];

for (const { ui, url } of ROUTES) {
  test(`${ui} primary route — no serious/critical axe violations`, async ({ page }) => {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15_000 });

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    const blocking = results.violations.filter(
      (v) => v.impact === 'serious' || v.impact === 'critical',
    );

    if (blocking.length > 0) {
      console.error(
        `[a11y] ${ui} (${url}) has ${blocking.length} serious/critical violation(s):`,
      );
      for (const v of blocking) {
        console.error(`  - ${v.id} (${v.impact}): ${v.help}`);
        for (const node of v.nodes.slice(0, 3)) {
          console.error(`      ${node.target.join(' ')}`);
        }
      }
    }

    expect(blocking, `axe found ${blocking.length} blocking violation(s) on ${ui}`).toEqual([]);
  });
}
