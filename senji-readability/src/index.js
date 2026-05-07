const express = require('express');
const { convert } = require('./converter');
const config = require('./config');

const app = express();

app.use(express.json({ limit: config.body_size_limit }));

/**
 * Health check endpoint.
 */
app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

/**
 * Stub HTML-to-markdown conversion endpoint.
 */
app.post('/convert', (req, res) => {
  const { html } = req.body ?? {};

  if (typeof html !== 'string') {
    return res.status(400).json({
      error: 'invalid_request',
      detail: 'html must be a string',
    });
  }

  const { url } = req.body;
  const result = convert(html, url || undefined);
  return res.json(result);
});

app.listen(config.port, () => {
  console.log(
    JSON.stringify({
      level: 'INFO',
      module: 'readability',
      msg: 'Server started',
      ts: new Date().toISOString(),
    })
  );
});
