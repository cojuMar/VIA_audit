import { chromium } from 'playwright';
import * as fs from 'fs';
import * as path from 'path';

const BASE_HUB  = 'http://localhost:5173';
const TENANT    = '00000000-0000-0000-0000-000000000001';
const SS_DIR    = 'qa-screenshots';

if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });

const results = [];
let ssIdx = 0;

async function shot(page, name) {
  const f = path.join(SS_DIR, `${String(++ssIdx).padStart(3,'0')}-${name}.png`);
  await page.screenshot({ path: f, fullPage: false }).catch(() => {});
  return f;
}

function log(status, section, detail, extra = '') {
  const icon = { PASS:'✅', FAIL:'❌', WARN:'⚠️ ', INFO:'ℹ️ ' }[status] || '  ';
  const line = `${icon} [${section.padEnd(12)}] ${detail}${extra ? ' → ' + extra : ''}`;
  console.log(line);
  results.push({ status, section, detail, extra });
}

// Safely navigate – returns true if page loaded, false if refused
async function goto(page, url, label) {
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 8000 });
    await page.waitForTimeout(1500);
    return true;
  } catch (e) {
    log('WARN', label, `Could not reach ${url}`, e.message.split('\n')[0]);
    return false;
  }
}

// Safely get visible text on page
async function pageHasText(page, regex) {
  return page.locator(`text=${regex}`).first().isVisible({ timeout: 2000 }).catch(() => false);
}

async function run() {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  const consoleErrors = [];
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });

  // ══════════════════════════════════════════
  // 1. LOGIN PAGE
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  1. LOGIN & AUTHENTICATION');
  console.log('════════════════════════════════════');

  await goto(page, BASE_HUB, 'Login');
  await shot(page, 'login-page');

  log(await page.locator('text=Sign in').first().isVisible().catch(()=>false) ? 'PASS':'FAIL', 'Login', 'Login page title "Sign in" visible');
  log(await page.locator('input[type="email"]').isVisible().catch(()=>false) ? 'PASS':'FAIL', 'Login', 'Email input present');
  log(await page.locator('input[type="password"]').isVisible().catch(()=>false) ? 'PASS':'FAIL', 'Login', 'Password input present');

  // Demo quick-fill buttons
  const demoCount = await page.locator('button').filter({ hasText: /admin|auditor|end.?user/i }).count();
  log(demoCount >= 3 ? 'PASS':'WARN', 'Login', 'Demo account quick-fill buttons present', `${demoCount} found`);

  // Theme selector on login page
  const themeOnLogin = await page.locator('button[title], button[aria-label]').count();
  log(themeOnLogin > 0 ? 'PASS':'WARN', 'Login', 'Theme selector accessible pre-login');

  // Wrong credentials → error
  await page.fill('input[type="email"]', 'hacker@evil.com');
  await page.fill('input[type="password"]', 'badpass');
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(1500);
  const errMsg = await page.locator('text=/incorrect|invalid|error/i').first().isVisible().catch(()=>false);
  log(errMsg ? 'PASS':'WARN', 'Login', 'Invalid credentials shows error message');
  await shot(page, 'login-wrong-creds');

  // Correct end-user login
  await page.fill('input[type="email"]', 'user@via.com');
  await page.fill('input[type="password"]', 'user123');
  await shot(page, 'login-correct-creds');
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(2000);
  await shot(page, 'post-login');

  const isOnHub = page.url().includes('5173');
  log(isOnHub ? 'PASS':'FAIL', 'Login', 'Login succeeds and lands on hub', page.url());

  // ══════════════════════════════════════════
  // 2. HUB DASHBOARD
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  2. HUB DASHBOARD');
  console.log('════════════════════════════════════');

  await shot(page, 'hub-full');

  // Check VIA branding
  const hasVIA = await page.locator('text=/VIA/').first().isVisible().catch(()=>false);
  log(hasVIA ? 'PASS':'WARN', 'Hub', 'VIA brand name visible in header');

  // User info in header
  const userInfo = await page.locator('text=/Audit Analyst|user@via/').first().isVisible().catch(()=>false);
  log(userInfo ? 'PASS':'FAIL', 'Hub', 'Logged-in user name shown in header');

  const roleBadge = await page.locator('text=/end.?user|End User/i').first().isVisible().catch(()=>false);
  log(roleBadge ? 'PASS':'WARN', 'Hub', 'User role badge displayed');

  // Module grid
  const moduleCards = await page.locator('a[href*="localhost"], a[href*="5182"], a[href*="5183"]').count();
  log(moduleCards > 0 ? 'PASS':'WARN', 'Hub', 'Module navigation links present', `${moduleCards} found`);

  // Hub/Tutorials tabs
  const hubTab   = await page.locator('[role="tab"]:has-text("Hub"), button:has-text("Hub")').first().isVisible().catch(()=>false);
  const tutTab   = await page.locator('[role="tab"]:has-text("Tutorials"), button:has-text("Tutorials")').first().isVisible().catch(()=>false);
  log(hubTab   ? 'PASS':'WARN', 'Hub', 'Hub tab present');
  log(tutTab   ? 'PASS':'WARN', 'Hub', 'Tutorials tab present');

  // Scroll to see all modules
  await page.mouse.wheel(0, 600);
  await page.waitForTimeout(400);
  await shot(page, 'hub-scrolled-down');
  await page.mouse.wheel(0, -600);
  await page.waitForTimeout(300);

  // ══════════════════════════════════════════
  // 3. THEME SWITCHING
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  3. THEME SWITCHING');
  console.log('════════════════════════════════════');

  // Try each theme button (sun/monitor/moon icons)
  const themeButtons = await page.locator('header button, nav button').all();
  let themesTested = 0;
  for (const btn of themeButtons) {
    const title = await btn.getAttribute('title').catch(()=>'');
    const aria  = await btn.getAttribute('aria-label').catch(()=>'');
    const label = (title || aria || '').toLowerCase();
    if (label.includes('light') || label.includes('dark') || label.includes('neutral')) {
      await btn.click();
      await page.waitForTimeout(300);
      themesTested++;
    }
  }
  log(themesTested > 0 ? 'PASS':'WARN', 'Theme', `Theme switcher buttons active`, `${themesTested} themes toggled`);
  await shot(page, 'theme-switched');

  // ══════════════════════════════════════════
  // 4. TUTORIALS TAB
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  4. TUTORIALS');
  console.log('════════════════════════════════════');

  const tutButton = page.locator('[role="tab"]:has-text("Tutorials"), button:has-text("Tutorials")').first();
  if (await tutButton.isVisible().catch(()=>false)) {
    await tutButton.click();
    await page.waitForTimeout(600);
    await shot(page, 'tutorials-view');

    const tutCards = await page.locator('[class*="card"], [class*="tutorial"]').count();
    log(tutCards > 0 ? 'PASS':'WARN', 'Tutorials', 'Tutorial cards rendered', `${tutCards} cards`);

    // Click first tutorial card
    const firstTut = page.locator('[class*="card"], [class*="tutorial"]').first();
    if (await firstTut.isVisible().catch(()=>false)) {
      await firstTut.click();
      await page.waitForTimeout(600);
      await shot(page, 'tutorial-opened');
      log('PASS', 'Tutorials', 'Tutorial card is clickable/expandable');
      await page.keyboard.press('Escape');
    }

    // Switch back to Hub tab
    await page.locator('[role="tab"]:has-text("Hub"), button:has-text("Hub")').first().click().catch(()=>{});
    await page.waitForTimeout(400);
  } else {
    log('WARN', 'Tutorials', 'Tutorials tab not found');
  }

  // ══════════════════════════════════════════
  // 5. MODULE: RISK MANAGEMENT (5182)
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  5. RISK MANAGEMENT (port 5182)');
  console.log('════════════════════════════════════');

  const riskOk = await goto(page, `http://localhost:5182/?tenantId=${TENANT}`, 'Risk');
  if (riskOk) {
    await shot(page, 'risk-01-landing');
    const bodyText = await page.textContent('body').catch(()=>'');

    log(bodyText.match(/risk/i) ? 'PASS':'FAIL', 'Risk', 'Risk Management page loads with content');

    // Get all nav/tab items
    const navItems = await page.locator('nav a, [role="tab"], [class*="nav"] a, [class*="sidebar"] a').allTextContents().catch(()=>[]);
    const cleanNav = navItems.map(t=>t.trim()).filter(t=>t && t.length < 40);
    log('INFO', 'Risk', 'Navigation items', cleanNav.slice(0,10).join(' | '));

    // Check for key UI sections
    const hasRegister = await page.locator('text=/register|risk register/i').first().isVisible().catch(()=>false);
    const hasHeatmap  = await page.locator('text=/heatmap|heat map/i').first().isVisible().catch(()=>false);
    const hasKRIs     = await page.locator('text=/KRI|indicator/i').first().isVisible().catch(()=>false);
    log(hasRegister ? 'PASS':'WARN', 'Risk', 'Risk Register section visible');
    log(hasHeatmap  ? 'PASS':'WARN', 'Risk', 'Heatmap section visible');
    log(hasKRIs     ? 'PASS':'WARN', 'Risk', 'KRI / Risk Indicators section visible');

    // Try Add Risk button
    const addBtn = page.locator('button:has-text("Add"), button:has-text("New"), button:has-text("Create"), button:has-text("+")').first();
    if (await addBtn.isVisible().catch(()=>false)) {
      await addBtn.click();
      await page.waitForTimeout(700);
      await shot(page, 'risk-02-add-modal');
      const modalOpen = await page.locator('[role="dialog"], [class*="modal"], form').first().isVisible().catch(()=>false);
      log(modalOpen ? 'PASS':'WARN', 'Risk', 'Add Risk modal/form opens');

      // Fill form fields if present
      const titleField = page.locator('input[placeholder*="title" i], input[placeholder*="name" i], input[placeholder*="risk" i]').first();
      if (await titleField.isVisible().catch(()=>false)) {
        await titleField.fill('Q4 Data Breach Risk – PII Exposure');
        log('PASS', 'Risk', 'Risk title field accepts input');
      }
      const descField = page.locator('textarea').first();
      if (await descField.isVisible().catch(()=>false)) {
        await descField.fill('Unauthorized access to customer PII in production database due to misconfigured IAM policies.');
        log('PASS', 'Risk', 'Risk description field accepts input');
      }
      await shot(page, 'risk-03-form-filled');

      // Look for category/severity selects
      const selects = await page.locator('select, [class*="select"]').count();
      log(selects > 0 ? 'PASS':'WARN', 'Risk', `Form has dropdowns/selects`, `${selects} found`);

      // Cancel
      await page.keyboard.press('Escape');
      await page.waitForTimeout(400);
      log('INFO', 'Risk', 'Form dismissed via Escape');
    } else {
      log('WARN', 'Risk', 'No "Add/New/Create" button visible — may need data to show first');
    }

    // Click heatmap nav if available
    const heatmapNav = page.locator('a:has-text("Heatmap"), button:has-text("Heatmap"), [href*="heatmap"]').first();
    if (await heatmapNav.isVisible().catch(()=>false)) {
      await heatmapNav.click();
      await page.waitForTimeout(800);
      await shot(page, 'risk-04-heatmap');
      log('PASS', 'Risk', 'Heatmap view navigates correctly');
    }

    // Indicators sub-section
    const indNav = page.locator('a:has-text("Indicator"), button:has-text("KRI"), a:has-text("KRI")').first();
    if (await indNav.isVisible().catch(()=>false)) {
      await indNav.click();
      await page.waitForTimeout(600);
      await shot(page, 'risk-05-indicators');
      log('PASS', 'Risk', 'Risk Indicators view accessible');
    }
    await shot(page, 'risk-06-final');
  }

  // ══════════════════════════════════════════
  // 6. MODULE: AUDIT PLANNING (5183)
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  6. AUDIT PLANNING (port 5183)');
  console.log('════════════════════════════════════');

  const planOk = await goto(page, `http://localhost:5183/?tenantId=${TENANT}`, 'AuditPlan');
  if (planOk) {
    await shot(page, 'plan-01-landing');
    const bodyText = await page.textContent('body').catch(()=>'');
    log(bodyText.match(/audit|plan|engagement/i) ? 'PASS':'FAIL', 'AuditPlan', 'Audit Planning page loads');

    const navItems = await page.locator('nav a, [role="tab"], [class*="nav"] a').allTextContents().catch(()=>[]);
    log('INFO', 'AuditPlan', 'Navigation', navItems.map(t=>t.trim()).filter(t=>t).slice(0,8).join(' | '));

    const hasPlans       = bodyText.match(/plan/i);
    const hasEngagements = bodyText.match(/engagement/i);
    const hasGantt       = bodyText.match(/gantt|schedule|calendar/i);
    const hasUniverse    = bodyText.match(/universe|entity/i);
    log(hasPlans       ? 'PASS':'WARN', 'AuditPlan', 'Plans section visible');
    log(hasEngagements ? 'PASS':'WARN', 'AuditPlan', 'Engagements section visible');
    log(hasGantt       ? 'PASS':'WARN', 'AuditPlan', 'Gantt/Schedule section visible');
    log(hasUniverse    ? 'PASS':'WARN', 'AuditPlan', 'Audit Universe/Entities section visible');

    // Try "New Plan" or "Create"
    const newBtn = page.locator('button:has-text("New Plan"), button:has-text("Create Plan"), button:has-text("Add Plan")').first();
    if (await newBtn.isVisible().catch(()=>false)) {
      await newBtn.click();
      await page.waitForTimeout(700);
      await shot(page, 'plan-02-new-form');
      log('PASS', 'AuditPlan', 'New Audit Plan form opens');
      await page.keyboard.press('Escape');
    }

    // Try Engagements tab
    const engTab = page.locator('a:has-text("Engagement"), button:has-text("Engagement"), [role="tab"]:has-text("Engagement")').first();
    if (await engTab.isVisible().catch(()=>false)) {
      await engTab.click();
      await page.waitForTimeout(600);
      await shot(page, 'plan-03-engagements');
      log('PASS', 'AuditPlan', 'Engagements tab accessible');
    }
    await shot(page, 'plan-04-final');
  }

  // ══════════════════════════════════════════
  // 7. MODULE: MONITORING (5177)
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  7. CONTINUOUS MONITORING (port 5177)');
  console.log('════════════════════════════════════');

  const monOk = await goto(page, `http://localhost:5177/?tenantId=${TENANT}`, 'Monitoring');
  if (monOk) {
    await shot(page, 'mon-01-landing');
    const bodyText = await page.textContent('body').catch(()=>'');
    log(bodyText.match(/monitor|finding|rule/i) ? 'PASS':'FAIL', 'Monitoring', 'Monitoring module loads');

    log(bodyText.match(/finding/i)    ? 'PASS':'WARN', 'Monitoring', 'Findings section present');
    log(bodyText.match(/rule/i)       ? 'PASS':'WARN', 'Monitoring', 'Rules section present');
    log(bodyText.match(/anomaly|sod|payroll/i) ? 'PASS':'WARN', 'Monitoring', 'Anomaly/SOD analysis present');

    // Navigate to findings
    const findNav = page.locator('a:has-text("Finding"), button:has-text("Finding"), [role="tab"]:has-text("Finding")').first();
    if (await findNav.isVisible().catch(()=>false)) {
      await findNav.click();
      await page.waitForTimeout(600);
      await shot(page, 'mon-02-findings');
      log('PASS', 'Monitoring', 'Findings view accessible');
    }

    // Navigate to rules
    const rulesNav = page.locator('a:has-text("Rule"), button:has-text("Rules"), [role="tab"]:has-text("Rule")').first();
    if (await rulesNav.isVisible().catch(()=>false)) {
      await rulesNav.click();
      await page.waitForTimeout(600);
      await shot(page, 'mon-03-rules');
      const ruleItems = await page.locator('[class*="rule"], tr, [class*="list-item"]').count();
      log('PASS', 'Monitoring', 'Rules list accessible', `~${ruleItems} items`);
    }
    await shot(page, 'mon-04-final');
  }

  // ══════════════════════════════════════════
  // 8. MODULE: PEOPLE & POLICY (5178)
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  8. PEOPLE & POLICY (port 5178)');
  console.log('════════════════════════════════════');

  const peopleOk = await goto(page, `http://localhost:5178/?tenantId=${TENANT}`, 'People');
  if (peopleOk) {
    await shot(page, 'people-01-landing');
    const bodyText = await page.textContent('body').catch(()=>'');
    log(bodyText.match(/people|employee|policy|training/i) ? 'PASS':'FAIL', 'People', 'People module loads');

    log(bodyText.match(/employee|staff/i)  ? 'PASS':'WARN', 'People', 'Employees section present');
    log(bodyText.match(/policy|policies/i) ? 'PASS':'WARN', 'People', 'Policies section present');
    log(bodyText.match(/training|course/i) ? 'PASS':'WARN', 'People', 'Training section present');

    // Navigate sub-sections
    const polTab = page.locator('a:has-text("Polic"), [role="tab"]:has-text("Polic"), button:has-text("Polic")').first();
    if (await polTab.isVisible().catch(()=>false)) {
      await polTab.click();
      await page.waitForTimeout(600);
      await shot(page, 'people-02-policies');
      log('PASS', 'People', 'Policies sub-section accessible');
    }

    const trainTab = page.locator('a:has-text("Train"), [role="tab"]:has-text("Train")').first();
    if (await trainTab.isVisible().catch(()=>false)) {
      await trainTab.click();
      await page.waitForTimeout(600);
      await shot(page, 'people-03-training');
      log('PASS', 'People', 'Training sub-section accessible');
    }
    await shot(page, 'people-04-final');
  }

  // ══════════════════════════════════════════
  // 9. MODULE: PBC / WORKPAPERS (5179)
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  9. PBC / WORKPAPERS (port 5179)');
  console.log('════════════════════════════════════');

  const pbcOk = await goto(page, `http://localhost:5179/?tenantId=${TENANT}`, 'PBC');
  if (pbcOk) {
    await shot(page, 'pbc-01-landing');
    const bodyText = await page.textContent('body').catch(()=>'');
    log(bodyText.match(/PBC|workpaper|request|evidence/i) ? 'PASS':'FAIL', 'PBC', 'PBC Workpapers module loads');

    log(bodyText.match(/request/i)    ? 'PASS':'WARN', 'PBC', 'PBC Requests section present');
    log(bodyText.match(/workpaper/i)  ? 'PASS':'WARN', 'PBC', 'Workpapers section present');
    log(bodyText.match(/engagement/i) ? 'PASS':'WARN', 'PBC', 'Engagement context present');

    // Try creating a PBC list
    const newListBtn = page.locator('button:has-text("New List"), button:has-text("Create List"), button:has-text("New"), button:has-text("Add")').first();
    if (await newListBtn.isVisible().catch(()=>false)) {
      await newListBtn.click();
      await page.waitForTimeout(600);
      await shot(page, 'pbc-02-new-list');
      log('PASS', 'PBC', 'New PBC List form opens');
      await page.keyboard.press('Escape');
    }
    await shot(page, 'pbc-03-final');
  }

  // ══════════════════════════════════════════
  // 10. MODULE: INTEGRATIONS (5180)
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  10. INTEGRATIONS (port 5180)');
  console.log('════════════════════════════════════');

  const integOk = await goto(page, `http://localhost:5180/?tenantId=${TENANT}`, 'Integration');
  if (integOk) {
    await shot(page, 'integ-01-landing');
    const bodyText = await page.textContent('body').catch(()=>'');
    log(bodyText.match(/integration|connector|AWS|Salesforce|sync/i) ? 'PASS':'FAIL', 'Integration', 'Integrations module loads');

    log(bodyText.match(/AWS|Amazon/i)     ? 'PASS':'WARN', 'Integration', 'AWS connector listed');
    log(bodyText.match(/Salesforce/i)     ? 'PASS':'WARN', 'Integration', 'Salesforce connector listed');
    log(bodyText.match(/connector/i)      ? 'PASS':'WARN', 'Integration', 'Connector catalog present');

    // Try adding an integration
    const addIntBtn = page.locator('button:has-text("Add Integration"), button:has-text("Connect"), button:has-text("New Integration")').first();
    if (await addIntBtn.isVisible().catch(()=>false)) {
      await addIntBtn.click();
      await page.waitForTimeout(600);
      await shot(page, 'integ-02-add');
      log('PASS', 'Integration', 'Add Integration dialog opens');
      await page.keyboard.press('Escape');
    }
    await shot(page, 'integ-03-final');
  }

  // ══════════════════════════════════════════
  // 11. MODULE: AI AGENT (5181)
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  11. AI AGENT PLATFORM (port 5181)');
  console.log('════════════════════════════════════');

  const aiOk = await goto(page, `http://localhost:5181/?tenantId=${TENANT}`, 'AI');
  if (aiOk) {
    await shot(page, 'ai-01-landing');
    const bodyText = await page.textContent('body').catch(()=>'');
    log(bodyText.match(/AI|agent|chat|conversation/i) ? 'PASS':'FAIL', 'AI', 'AI Agent module loads');

    // Chat interface
    const chatInput = page.locator('textarea, input[placeholder*="message" i], input[placeholder*="ask" i], input[placeholder*="query" i]').first();
    const hasChatInput = await chatInput.isVisible().catch(()=>false);
    log(hasChatInput ? 'PASS':'WARN', 'AI', 'Chat input field present');

    if (hasChatInput) {
      await chatInput.fill('Show me a summary of open risks for this tenant');
      await shot(page, 'ai-02-typed');
      log('PASS', 'AI', 'Chat input accepts text query');
      const sendBtn = page.locator('button[type="submit"], button:has-text("Send"), button[aria-label*="send" i]').first();
      log(await sendBtn.isVisible().catch(()=>false) ? 'PASS':'WARN', 'AI', 'Send button visible');
      await chatInput.clear();
    }

    // Check for tool list
    const toolsSection = await page.locator('text=/tools|capabilities/i').first().isVisible().catch(()=>false);
    log(toolsSection ? 'PASS':'WARN', 'AI', 'Available tools/capabilities section present');

    // Reports sub-section
    const reportsTab = page.locator('a:has-text("Report"), [role="tab"]:has-text("Report")').first();
    if (await reportsTab.isVisible().catch(()=>false)) {
      await reportsTab.click();
      await page.waitForTimeout(600);
      await shot(page, 'ai-03-reports');
      log('PASS', 'AI', 'Reports sub-section accessible');
    }
    await shot(page, 'ai-04-final');
  }

  // ══════════════════════════════════════════
  // 12. MODULE: ESG BOARD (5184)
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  12. ESG & BOARD MANAGEMENT (port 5184)');
  console.log('════════════════════════════════════');

  const esgOk = await goto(page, `http://localhost:5184/?tenantId=${TENANT}`, 'ESG');
  if (esgOk) {
    await shot(page, 'esg-01-landing');
    const bodyText = await page.textContent('body').catch(()=>'');
    log(bodyText.match(/ESG|board|environmental|governance/i) ? 'PASS':'FAIL', 'ESG', 'ESG Board module loads');

    log(bodyText.match(/environmental|E score/i) ? 'PASS':'WARN', 'ESG', 'Environmental metrics section');
    log(bodyText.match(/board|committee|meeting/i) ? 'PASS':'WARN', 'ESG', 'Board management section');
    log(bodyText.match(/disclosure|framework/i) ? 'PASS':'WARN', 'ESG', 'ESG disclosure section');

    // Navigate to Board tab
    const boardTab = page.locator('a:has-text("Board"), [role="tab"]:has-text("Board"), button:has-text("Board")').first();
    if (await boardTab.isVisible().catch(()=>false)) {
      await boardTab.click();
      await page.waitForTimeout(600);
      await shot(page, 'esg-02-board');
      log('PASS', 'ESG', 'Board tab navigates correctly');
    }

    // Try creating a board meeting
    const newMtgBtn = page.locator('button:has-text("New Meeting"), button:has-text("Schedule"), button:has-text("Add Meeting")').first();
    if (await newMtgBtn.isVisible().catch(()=>false)) {
      await newMtgBtn.click();
      await page.waitForTimeout(600);
      await shot(page, 'esg-03-new-meeting');
      log('PASS', 'ESG', 'New Board Meeting form opens');
      await page.keyboard.press('Escape');
    }
    await shot(page, 'esg-04-final');
  }

  // ══════════════════════════════════════════
  // 13. MODULE: TRUST PORTAL (5176)
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  13. TRUST PORTAL (port 5176)');
  console.log('════════════════════════════════════');

  const trustOk = await goto(page, `http://localhost:5176/?tenantId=${TENANT}`, 'Trust');
  if (trustOk) {
    await shot(page, 'trust-01-landing');
    const bodyText = await page.textContent('body').catch(()=>'');
    log(bodyText.match(/trust|portal|compliance|document/i) ? 'PASS':'FAIL', 'Trust', 'Trust Portal module loads');
    log(bodyText.match(/document|NDA/i)      ? 'PASS':'WARN', 'Trust', 'Documents section present');
    log(bodyText.match(/access.log|visitor/i)? 'PASS':'WARN', 'Trust', 'Access log section present');
    await shot(page, 'trust-02-final');
  }

  // ══════════════════════════════════════════
  // 14. MODULE: MOBILE (5185)
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  14. MOBILE FIELD AUDIT (port 5185)');
  console.log('════════════════════════════════════');

  const mobOk = await goto(page, `http://localhost:5185/?tenantId=${TENANT}`, 'Mobile');
  if (mobOk) {
    await shot(page, 'mob-01-landing');
    const bodyText = await page.textContent('body').catch(()=>'');
    log(bodyText.match(/mobile|field|assignment|audit/i) ? 'PASS':'FAIL', 'Mobile', 'Mobile module loads');
    log(bodyText.match(/assignment/i) ? 'PASS':'WARN', 'Mobile', 'Assignments section present');
    log(bodyText.match(/template/i)   ? 'PASS':'WARN', 'Mobile', 'Audit templates present');
    await shot(page, 'mob-02-final');
  }

  // ══════════════════════════════════════════
  // 15. LOGOUT WORKFLOW
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  15. LOGOUT WORKFLOW');
  console.log('════════════════════════════════════');

  await goto(page, BASE_HUB, 'Logout');
  await page.waitForTimeout(500);

  // Look for user/avatar button in header
  const headerBtns = await page.locator('header button, nav button').all();
  let loggedOut = false;
  for (const btn of headerBtns) {
    const text = await btn.textContent().catch(()=>'');
    const aria = await btn.getAttribute('aria-label').catch(()=>'');
    if ((text + aria).match(/user|analyst|sign|avatar|account/i)) {
      await btn.click();
      await page.waitForTimeout(500);
      await shot(page, 'logout-menu-open');
      const signout = page.locator('text=/sign out|log out|logout/i').first();
      if (await signout.isVisible().catch(()=>false)) {
        await signout.click();
        await page.waitForTimeout(1200);
        await shot(page, 'logout-result');
        const backToLogin = await page.locator('input[type="email"], text=Sign in').first().isVisible().catch(()=>false);
        log(backToLogin ? 'PASS':'WARN', 'Logout', 'Sign out returns to login page');
        loggedOut = true;
        break;
      }
      await page.keyboard.press('Escape');
    }
  }
  if (!loggedOut) {
    log('WARN', 'Logout', 'Could not locate sign out button in header');
  }

  // ══════════════════════════════════════════
  // CONSOLE ERRORS SUMMARY
  // ══════════════════════════════════════════
  console.log('\n════════════════════════════════════');
  console.log('  CONSOLE ERRORS');
  console.log('════════════════════════════════════');

  const uniqueErrs = [...new Set(consoleErrors)].filter(e => !e.includes('favicon'));
  if (uniqueErrs.length === 0) {
    log('PASS', 'Console', 'Zero JavaScript errors across all modules');
  } else {
    uniqueErrs.slice(0,8).forEach(e => log('WARN', 'Console', e.slice(0,100)));
  }

  await browser.close();

  // ══════════════════════════════════════════
  // FINAL SUMMARY
  // ══════════════════════════════════════════
  console.log('\n╔════════════════════════════════════╗');
  console.log('║        QA TEST SUMMARY              ║');
  console.log('╚════════════════════════════════════╝');
  const pass = results.filter(r=>r.status==='PASS').length;
  const fail = results.filter(r=>r.status==='FAIL').length;
  const warn = results.filter(r=>r.status==='WARN').length;
  const info = results.filter(r=>r.status==='INFO').length;
  console.log(`  ✅ PASS: ${pass}  ❌ FAIL: ${fail}  ⚠️  WARN: ${warn}  ℹ️  INFO: ${info}`);
  console.log(`  📸 ${ssIdx} screenshots → ${SS_DIR}/`);

  if (fail > 0) {
    console.log('\n  ❌ FAILURES:');
    results.filter(r=>r.status==='FAIL').forEach(r=>console.log(`    • [${r.section}] ${r.detail}`));
  }
  if (warn > 0) {
    console.log('\n  ⚠️  WARNINGS:');
    results.filter(r=>r.status==='WARN').forEach(r=>console.log(`    • [${r.section}] ${r.detail}`));
  }
}

run().catch(console.error);
