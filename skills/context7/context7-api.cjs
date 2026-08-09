#!/usr/bin/env node

/**
 * Context7 API Helper Script
 * Provides a stable CLI interface for Context7 docs lookup.
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

const API_BASE = 'https://context7.com/api/v2';

function loadApiKey() {
  if (process.env.CONTEXT7_API_KEY) {
    return process.env.CONTEXT7_API_KEY;
  }

  const envPath = path.join(__dirname, '.env');
  if (fs.existsSync(envPath)) {
    const envContent = fs.readFileSync(envPath, 'utf8');
    const match = envContent.match(/CONTEXT7_API_KEY\s*=\s*(.+)/);
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

    https.get(url, { headers: buildHeaders(apiKey) }, (res) => {
      let data = '';

      res.on('data', (chunk) => {
        data += chunk;
      });

      res.on('end', () => {
        if (res.statusCode === 200) {
          try {
            resolve(JSON.parse(data));
          } catch {
            resolve(data);
          }
          return;
        }

        reject(new Error(`API Error ${res.statusCode}: ${data}`));
      });
    }).on('error', reject);
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

function normalizeSearchLibrary(item = {}) {
  return {
    id: item.id || item.libraryId || '',
    name: item.name || item.title || item.libraryName || '',
    description: item.description || '',
    trustScore: item.trustScore ?? null,
    versions: Array.isArray(item.versions) ? item.versions : []
  };
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
    relevance: item.relevance ?? null
  };
}

function normalizeInfoSnippet(item = {}) {
  return {
    title: item.title || item.pageTitle || 'Documentation snippet',
    content: item.content || item.text || item.description || '',
    source: item.source || item.url || item.pageTitle || '',
    relevance: item.relevance ?? null
  };
}

function normalizeSearchResponse(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return payload;
  }

  if (Array.isArray(payload.libraries)) {
    return payload;
  }

  if (Array.isArray(payload.results)) {
    return {
      ...payload,
      libraries: payload.results.map(normalizeSearchLibrary)
    };
  }

  return payload;
}

function normalizeContextResponse(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return payload;
  }

  if (Array.isArray(payload.results)) {
    return payload;
  }

  const results = [];

  if (Array.isArray(payload.codeSnippets)) {
    results.push(...payload.codeSnippets.map(normalizeCodeSnippet));
  }

  if (Array.isArray(payload.infoSnippets)) {
    results.push(...payload.infoSnippets.map(normalizeInfoSnippet));
  }

  if (!results.length) {
    return payload;
  }

  return {
    ...payload,
    results
  };
}

async function searchLibrary(libraryName, query) {
  const result = await makeRequest('/libs/search', { libraryName, query });
  return normalizeSearchResponse(result);
}

async function getContext(libraryId, query) {
  const result = await makeRequest('/context', {
    libraryId: fixMsysPath(libraryId),
    query,
    type: 'json'
  });

  return normalizeContextResponse(result);
}

async function runCli(argv, io = {}, deps = {}) {
  const stdout = io.stdout || console.log;
  const stderr = io.stderr || console.error;
  const search = deps.search || searchLibrary;
  const context = deps.context || getContext;

  const [command, ...args] = argv;

  if (command === 'search') {
    const [libraryName, query] = args;
    if (!libraryName || !query) {
      stderr('Usage: context7-api.cjs search <libraryName> <query>');
      return 1;
    }

    try {
      const result = await search(libraryName, query);
      stdout(JSON.stringify(result, null, 2));
      return 0;
    } catch (error) {
      stderr(`Error searching library: ${error.message}`);
      return 1;
    }
  }

  if (command === 'context') {
    const [libraryId, query] = args;
    if (!libraryId || !query) {
      stderr('Usage: context7-api.cjs context <libraryId> <query>');
      return 1;
    }

    try {
      const result = await context(libraryId, query);
      stdout(JSON.stringify(result, null, 2));
      return 0;
    } catch (error) {
      stderr(`Error getting context: ${error.message}`);
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
  getContext,
  loadApiKey,
  makeRequest,
  normalizeCodeSnippet,
  normalizeContextResponse,
  normalizeInfoSnippet,
  normalizeSearchLibrary,
  normalizeSearchResponse,
  runCli,
  searchLibrary
};
