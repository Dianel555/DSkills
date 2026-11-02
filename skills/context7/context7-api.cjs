#!/usr/bin/env node

/**
 * Context7 API Helper Script
 * Provides a stable CLI interface for Context7 docs lookup.
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

const API_BASE = 'https://context7.com/api/v3';
const MAX_RESPONSE_BYTES = 4 * 1024 * 1024;
const REQUEST_DEADLINE_MS = 30_000;

function loadApiKey() {
  if (process.env.CONTEXT7_API_KEY) {
    return process.env.CONTEXT7_API_KEY;
  }

  const envPath = path.join(__dirname, '.env');
  if (fs.existsSync(envPath)) {
    const envContent = fs.readFileSync(envPath, 'utf8');
    const match = envContent.match(/^CONTEXT7_API_KEY\s*=\s*(.+)$/m);
    if (match) {
      return match[1].trim().replace(/^["']|["']$/g, '');
    }
  }

  return null;
}

const API_KEY = loadApiKey();

function buildHeaders(apiKey = API_KEY) {
  const headers = {
    'User-Agent': 'Context7-Skill/1.1'
  };

  if (apiKey) {
    headers.Authorization = `Bearer ${apiKey}`;
  }

  return headers;
}

function makeRequest(requestPath, params = {}, apiKey = API_KEY) {
  return new Promise((resolve, reject) => {
    const queryString = new URLSearchParams(params).toString();
    const url = `${API_BASE}${requestPath}?${queryString}`;

    let request;
    let settled = false;
    const timer = setTimeout(() => fail(new Error('Context7 request timed out')), REQUEST_DEADLINE_MS);
    const fail = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(error);
      if (request) request.destroy();
    };
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      callback(value);
    };

    try {
      request = https.get(url, { headers: buildHeaders(apiKey) }, (res) => {
        const chunks = [];
        let size = 0;
        res.on('data', (chunk) => {
          if (settled) return;
          const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
          size += bytes.length;
          if (size > MAX_RESPONSE_BYTES) {
            fail(new Error('Context7 response too large'));
            return;
          }
          chunks.push(bytes);
        });
        res.on('aborted', () => fail(new Error('Context7 response aborted')));
        res.on('error', fail);
        res.on('end', () => {
          if (settled) return;
          let payload;
          try {
            payload = JSON.parse(Buffer.concat(chunks).toString('utf8'));
          } catch {
            if (res.statusCode === 200) {
              finish(reject, new Error('Context7 returned invalid JSON'));
              return;
            }
          }

          if (res.statusCode === 200) {
            finish(resolve, payload);
            return;
          }

          const error = new Error(`API Error ${res.statusCode}: ${payload?.message || payload?.error || res.statusMessage}`);
          error.statusCode = res.statusCode;
          error.code = payload?.error;
          finish(reject, error);
        });
      });
      request.on('error', fail);
    } catch (error) {
      fail(error);
    }
  });
}

function fixMsysPath(inputPath) {
  if (!inputPath) {
    return inputPath;
  }

  const msysPattern = /^[A-Za-z]:\/(?:Program Files(?:| \(x86\))\/Git|msys64|msys32|cygwin64|cygwin)\/(.+)$/i;
  const match = inputPath.match(msysPattern);
  if (match) {
    return `/${match[1]}`;
  }

  return inputPath;
}

function formatCodeList(codeList = []) {
  return codeList
    .map((block) => {
      if (!block || typeof block !== 'object' || !block.code) {
        return '';
      }

      if (!block.language) {
        return block.code;
      }

      return `\`\`\`${block.language}\n${block.code}\n\`\`\``;
    })
    .filter(Boolean)
    .join('\n\n');
}

function normalizeCodeSnippet(item = {}) {
  const content = [
    item.codeDescription,
    formatCodeList(Array.isArray(item.codeList) ? item.codeList : [])
  ].filter(Boolean).join('\n\n');

  return {
    title: item.codeTitle || item.pageTitle || 'Code snippet',
    content,
    source: item.codeId || item.sourceFile || item.pageTitle || '',
    libraryId: item.libraryId || '',
    relevance: item.relevance ?? null
  };
}

function normalizeInfoSnippet(item = {}) {
  return {
    title: item.title || item.pageTitle || 'Documentation snippet',
    content: item.content || item.text || item.description || '',
    source: item.pageId || item.source || item.url || item.pageTitle || '',
    libraryId: item.libraryId || '',
    relevance: item.relevance ?? null
  };
}

function normalizeDocumentationResponse(payload) {
  if (!payload || !Array.isArray(payload.codeSnippets) || !Array.isArray(payload.infoSnippets)) {
    throw new Error('Unexpected Context7 search response');
  }

  const results = [];

  if (Array.isArray(payload.codeSnippets)) {
    results.push(...payload.codeSnippets.map(normalizeCodeSnippet));
  }

  if (Array.isArray(payload.infoSnippets)) {
    results.push(...payload.infoSnippets.map(normalizeInfoSnippet));
  }

  return {
    ...payload,
    results
  };
}

async function searchDocumentation(query, options = {}, request = makeRequest) {
  const params = new URLSearchParams({ query, type: 'json' });
  for (const library of options.libraries || []) {
    params.append('library', fixMsysPath(library));
  }
  if (options.version) params.set('version', options.version);
  if (options.language) params.set('language', options.language);

  try {
    return normalizeDocumentationResponse(await request('/search', params));
  } catch (error) {
    if (error.statusCode === 404 && error.code === 'no_documentation_found') {
      return { codeSnippets: [], infoSnippets: [], results: [] };
    }
    throw error;
  }
}

function parseSearchOptions(args) {
  const options = { libraries: [] };
  for (let index = 0; index < args.length; index += 2) {
    const flag = args[index];
    const value = args[index + 1];
    if (!value || value.startsWith('--')) {
      throw new Error(`Missing value for ${flag}`);
    }
    if (flag === '--library') {
      options.libraries.push(value);
    } else if (flag === '--version') {
      options.version = value;
    } else if (flag === '--language') {
      options.language = value;
    } else {
      throw new Error(`Unknown option: ${flag}`);
    }
  }
  if (options.libraries.length > 4) {
    throw new Error('At most four --library hints are allowed');
  }
  if (options.version && !options.libraries.length) {
    throw new Error('--version requires --library');
  }
  return options;
}

async function runCli(argv, io = {}, deps = {}) {
  const stdout = io.stdout || console.log;
  const stderr = io.stderr || console.error;
  const search = deps.search || searchDocumentation;

  const [command, ...args] = argv;

  if (command === 'search') {
    const [query, ...flags] = args;
    if (!query || query.startsWith('--')) {
      stderr('Usage: context7-api.cjs search <query> [--library <name-or-id>] [--version <version>] [--language <language>]');
      return 1;
    }

    try {
      const result = await search(query, parseSearchOptions(flags));
      stdout(JSON.stringify(result, null, 2));
      return 0;
    } catch (error) {
      stderr(`Error searching documentation: ${error.message}`);
      return 1;
    }
  }

  if (command === 'context') {
    const [libraryId, query] = args;
    if (!libraryId || !query || args.length !== 2) {
      stderr('Usage: context7-api.cjs context <libraryId> <query>');
      return 1;
    }

    try {
      const result = await search(query, { libraries: [libraryId] });
      stdout(JSON.stringify(result, null, 2));
      return 0;
    } catch (error) {
      stderr(`Error searching documentation: ${error.message}`);
      return 1;
    }
  }

  stderr('Usage: context7-api.cjs <search|context> <args...>');
  return 1;
}

if (require.main === module) {
  runCli(process.argv.slice(2))
    .then((code) => {
      process.exit(code);
    })
    .catch((error) => {
      console.error(error.message);
      process.exit(1);
    });
}

module.exports = {
  API_BASE,
  buildHeaders,
  fixMsysPath,
  formatCodeList,
  loadApiKey,
  makeRequest,
  normalizeCodeSnippet,
  normalizeDocumentationResponse,
  normalizeInfoSnippet,
  parseSearchOptions,
  runCli,
  searchDocumentation
};
