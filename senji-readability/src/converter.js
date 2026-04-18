const { JSDOM } = require('jsdom');
const { Readability } = require('@mozilla/readability');
const TurndownService = require('turndown');
const { gfm } = require('turndown-plugin-gfm');

const EMPTY_RESULT = { markdown: '', title: 'Untitled' };

function log(msg, extra = {}) {
  console.log(JSON.stringify({
    level: 'INFO',
    module: 'readability.convert',
    msg,
    ts: new Date().toISOString(),
    ...extra,
  }));
}

function logError(msg, err) {
  console.log(JSON.stringify({
    level: 'ERROR',
    module: 'readability.convert',
    msg,
    error: err.message,
    ts: new Date().toISOString(),
  }));
}

function createTurndown() {
  const td = new TurndownService({
    headingStyle: 'atx',
    codeBlockStyle: 'fenced',
    bulletListMarker: '-',
  });
  td.use(gfm);
  return td;
}

function convert(html, url = 'http://localhost') {
  if (!html || typeof html !== 'string') {
    return EMPTY_RESULT;
  }

  const trimmed = html.trim();
  if (!trimmed) {
    return EMPTY_RESULT;
  }

  let dom;
  try {
    dom = new JSDOM(trimmed, { url });
  } catch (err) {
    logError('JSDOM parse failed', err);
    return EMPTY_RESULT;
  }

  const doc = dom.window.document;
  const cloneForReadability = doc.cloneNode(true);

  let articleHtml = null;
  let title = 'Untitled';

  try {
    const parsed = new Readability(cloneForReadability).parse();
    if (parsed && parsed.content) {
      articleHtml = parsed.content;
      title = parsed.title || 'Untitled';
      log('Readability extracted article', { title, contentLength: articleHtml.length });
    }
  } catch (err) {
    logError('Readability parse failed, falling back to body', err);
  }

  if (!articleHtml) {
    const body = doc.body;
    if (!body || !body.innerHTML.trim()) {
      return EMPTY_RESULT;
    }
    articleHtml = body.innerHTML;
    log('Readability returned null, using full body');
  }

  try {
    const td = createTurndown();
    const markdown = td.turndown(articleHtml).trim();
    log('Conversion complete', { markdownLength: markdown.length });
    return { markdown, title };
  } catch (err) {
    logError('Turndown conversion failed', err);
    return { markdown: '', title };
  }
}

module.exports = { convert };
