// The same sites and checks in another Chromium browser (Chromium of the
// engine's version, Brave...), through Playwright:
//   node baseline.js <browser executable> <sites.json> <out dir> [extra switches]
// The check runs in an isolated world, as I.K.E.'s probe does.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const [exe, sitesFile, outDir, extra] = process.argv.slice(2);
  const sites = JSON.parse(fs.readFileSync(sitesFile, 'utf8'));
  const probe = fs.readFileSync(path.join(__dirname, 'probe.js'), 'utf8');
  fs.mkdirSync(outDir, { recursive: true });
  const proxy = process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY, bypass: 'localhost,127.0.0.1' } : undefined;
  const ctx = await chromium.launchPersistentContext(fs.mkdtempSync('/tmp/bl-'), {
    executablePath: exe, headless: !process.env.DISPLAY, proxy, viewport: { width: 1366, height: 900 },
    args: ['--no-sandbox', ...(extra || '').split(' ').filter(Boolean)],
  });
  const results = [];
  for (const site of sites) {
    const t0 = Date.now(), rec = { key: site.key, url: site.url, console: [], failed: [] };
    const page = await ctx.newPage();
    page.on('console', (m) => { if (m.type() === 'error' && rec.console.length < 200) rec.console.push(m.text().slice(0, 300)); });
    page.on('requestfailed', (r) => { if (rec.failed.length < 200) rec.failed.push([r.resourceType(), r.url().slice(0, 160), (r.failure() || {}).errorText]); });
    try { await page.goto(site.url, { timeout: 30000, waitUntil: 'domcontentloaded' }); } catch (e) { rec.gotoErr = String(e).slice(0, 200); }
    await page.waitForTimeout(site.wait || 14000);
    try {
      const js = probe.split('__CHECK__').join(site.check || 'null').split('__TAG__').join('p1');
      const cdp = await ctx.newCDPSession(page);
      const { frameTree } = await cdp.send('Page.getFrameTree');
      const { executionContextId } = await cdp.send('Page.createIsolatedWorld', { frameId: frameTree.frame.id, worldName: 'bl' });
      // a check that never ends (a video that never starts) must not stop the run
      await Promise.race([cdp.send('Runtime.evaluate', { expression: js, contextId: executionContextId, awaitPromise: true }),
        new Promise((r) => setTimeout(r, 25000))]);
      const r = await cdp.send('Runtime.evaluate', { expression: 'window.__ikeProbe_p1 || null', contextId: executionContextId, returnByValue: true });
      rec.probe = JSON.parse(r.result.value || 'null');
    } catch (e) { rec.probeErr = String(e).slice(0, 200); }
    try { await page.screenshot({ path: path.join(outDir, site.key + '.png') }); } catch (e) {}
    rec.final_url = page.url(); rec.title = (await page.title().catch(() => '')).slice(0, 120);
    rec.secs = (Date.now() - t0) / 1000;
    results.push(rec);
    fs.writeFileSync(path.join(outDir, 'results.json'), JSON.stringify(results, null, 1));
    await page.close();
  }
  await ctx.close();
})();
