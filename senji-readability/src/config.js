const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');

const DEFAULTS = {
  port: 3000,
  body_size_limit: '10mb',
};

const YAML_PATH =
  process.env.SENJI_CONFIG_YAML ||
  path.resolve(__dirname, '..', '..', 'config.yaml');

function loadYamlBlock() {
  if (!fs.existsSync(YAML_PATH)) {
    console.warn(
      JSON.stringify({
        level: 'WARN',
        module: 'readability.config',
        msg: 'config.yaml not found, using defaults',
        path: YAML_PATH,
        ts: new Date().toISOString(),
      })
    );
    return {};
  }
  const raw = yaml.load(fs.readFileSync(YAML_PATH, 'utf8'));
  if (!raw || typeof raw !== 'object') return {};
  const block = raw.readability;
  return block && typeof block === 'object' ? block : {};
}

function applyEnvOverrides(cfg) {
  const out = { ...cfg };
  if (process.env.READABILITY_PORT) {
    const n = Number(process.env.READABILITY_PORT);
    if (!Number.isFinite(n)) {
      throw new Error(
        `READABILITY_PORT must be numeric, got: ${process.env.READABILITY_PORT}`
      );
    }
    out.port = n;
  }
  if (process.env.READABILITY_BODY_SIZE_LIMIT) {
    out.body_size_limit = process.env.READABILITY_BODY_SIZE_LIMIT;
  }
  return out;
}

const config = applyEnvOverrides({ ...DEFAULTS, ...loadYamlBlock() });

module.exports = config;
