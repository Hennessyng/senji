'use strict';

const express = require('express');
const { chromium } = require('playwright-core');

const PORT = parseInt(process.env.PORT || '3001', 10);
const RENDER_TIMEOUT_MS = parseInt(process.env.RENDER_TIMEOUT_MS || '30000', 10);
const CHROMIUM_PATH = process.env.CHROMIUM_PATH || '/usr/bin/chromium';

const log = {
  info: (...a) => console.log(new Date().toISOString(), 'INFO', ...a),
  error: (...a) => console.error(new Date().toISOString(), 'ERROR', ...a),
};

let browser = null;

async function getBrowser() {
  if (!browser || !browser.isConnected()) {
    log.info('Launching Chromium at', CHROMIUM_PATH);
    browser = await chromium.launch({
      executablePath: CHROMIUM_PATH,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
      ],
    });
    log.info('Chromium launched');
  }
  return browser;
}

async function renderUrl(url) {
  const b = await getBrowser();
  const page = await b.newPage();
  try {
    log.info('Rendering:', url);
    await page.goto(url, { waitUntil: 'networkidle', timeout: RENDER_TIMEOUT_MS });
    const html = await page.content();
    const finalUrl = page.url();
    log.info('Rendered OK:', finalUrl);
    return { html, finalUrl };
  } finally {
    await page.close();
  }
}

const app = express();
app.use(express.json({ limit: '10mb' }));

app.get('/health', (_req, res) => res.json({ status: 'ok' }));

app.post('/render', async (req, res) => {
  const { url } = req.body || {};
  if (!url || typeof url !== 'string') {
    return res.status(400).json({ error: 'url required' });
  }
  try {
    const result = await renderUrl(url);
    res.json(result);
  } catch (err) {
    log.error('Render failed:', err.message);
    res.status(502).json({ error: err.message });
  }
});

async function start() {
  try {
    await getBrowser();
  } catch (err) {
    log.error('Failed to launch Chromium:', err.message);
    process.exit(1);
  }
  app.listen(PORT, () => log.info(`senji-renderer listening on :${PORT}`));
}

start();

process.on('SIGTERM', async () => {
  log.info('SIGTERM — closing browser');
  if (browser) await browser.close().catch(() => {});
  process.exit(0);
});
