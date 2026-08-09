const test = require('node:test');
const assert = require('node:assert/strict');

const {
  fixMsysPath,
  normalizeContextResponse,
  normalizeSearchResponse,
  runCli
} = require('../context7-api.cjs');

test('normalizeSearchResponse adds libraries alias for current search payloads', () => {
  const payload = {
    results: [
      {
        id: '/react/react',
        title: 'React',
        description: 'A JavaScript library for building user interfaces.',
        trustScore: 8.3,
        versions: ['v19.2.7', 'v18.2.0']
      }
    ],
    searchFilterApplied: false
  };

  const normalized = normalizeSearchResponse(payload);

  assert.equal(normalized.results, payload.results);
  assert.deepEqual(normalized.libraries, [
    {
      id: '/react/react',
      name: 'React',
      description: 'A JavaScript library for building user interfaces.',
      trustScore: 8.3,
      versions: ['v19.2.7', 'v18.2.0']
    }
  ]);
});

test('normalizeContextResponse builds results from code and info snippets', () => {
  const payload = {
    codeSnippets: [
      {
        codeTitle: 'Corrected Effect with Cleanup Function',
        codeDescription: 'Adds cleanup to avoid leaked connections.',
        codeId: 'https://github.com/reactjs/react.dev/blob/main/src/content/reference/react/StrictMode.md',
        codeList: [
          {
            language: 'javascript',
            code: 'useEffect(() => connection.disconnect(), []);'
          }
        ]
      }
    ],
    infoSnippets: [
      {
        title: 'Cleanup overview',
        content: 'Cleanup runs before the effect re-runs and on unmount.',
        source: 'react.dev/useEffect'
      }
    ]
  };

  const normalized = normalizeContextResponse(payload);

  assert.equal(normalized.results.length, 2);
  assert.equal(normalized.results[0].title, 'Corrected Effect with Cleanup Function');
  assert.match(normalized.results[0].content, /Adds cleanup/);
  assert.match(normalized.results[0].content, /useEffect/);
  assert.equal(normalized.results[1].title, 'Cleanup overview');
  assert.equal(normalized.results[1].content, 'Cleanup runs before the effect re-runs and on unmount.');
});

test('fixMsysPath rewrites Git Bash path-mangled library ids', () => {
  assert.equal(fixMsysPath('C:/Program Files/Git/reactjs/react.dev'), '/reactjs/react.dev');
  assert.equal(fixMsysPath('/reactjs/react.dev'), '/reactjs/react.dev');
});

test('runCli returns non-zero on request failures', async () => {
  const stdout = [];
  const stderr = [];
  const code = await runCli(
    ['search', 'react', 'useEffect'],
    {
      stdout: (message) => stdout.push(message),
      stderr: (message) => stderr.push(message)
    },
    {
      search: async () => {
        throw new Error('boom');
      },
      context: async () => {
        throw new Error('unused');
      }
    }
  );

  assert.equal(code, 1);
  assert.deepEqual(stdout, []);
  assert.match(stderr.join('\n'), /Error searching library: boom/);
});
