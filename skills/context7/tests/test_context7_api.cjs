const test = require('node:test');
const assert = require('node:assert/strict');

const {
  fixMsysPath,
  normalizeDocumentationResponse,
  runCli,
  searchDocumentation
} = require('../context7-api.cjs');

test('v3 search sends one JSON request with repeated library hints', async () => {
  const calls = [];
  const result = await searchDocumentation(
    'stream a response',
    { libraries: ['Next.js', '/openai/openai-node'], version: '15.4.0', language: 'TypeScript' },
    async (path, params) => {
      calls.push({ path, params });
      return { codeSnippets: [], infoSnippets: [] };
    }
  );

  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, '/search');
  assert.deepEqual([...calls[0].params.entries()], [
    ['query', 'stream a response'],
    ['type', 'json'],
    ['library', 'Next.js'],
    ['library', '/openai/openai-node'],
    ['version', '15.4.0'],
    ['language', 'TypeScript']
  ]);
  assert.deepEqual(result.results, []);
});

test('v3 snippets preserve library and source links in normalized results', () => {
  const payload = {
    codeSnippets: [{
      codeTitle: 'Cleanup',
      codeDescription: 'Disconnect on unmount.',
      codeId: 'https://example.com/code',
      libraryId: '/reactjs/react.dev',
      codeList: [{ language: 'javascript', code: 'return () => disconnect();' }]
    }],
    infoSnippets: [{
      content: 'The cleanup runs on unmount.',
      pageId: 'https://example.com/docs',
      libraryId: '/reactjs/react.dev'
    }]
  };

  const normalized = normalizeDocumentationResponse(payload);
  assert.equal(normalized.codeSnippets, payload.codeSnippets);
  assert.equal(normalized.infoSnippets, payload.infoSnippets);
  assert.equal(normalized.results[0].libraryId, '/reactjs/react.dev');
  assert.equal(normalized.results[0].source, 'https://example.com/code');
  assert.match(normalized.results[0].content, /disconnect/);
  assert.equal(normalized.results[1].libraryId, '/reactjs/react.dev');
  assert.equal(normalized.results[1].source, 'https://example.com/docs');
});

test('no_documentation_found is an empty result', async () => {
  const result = await searchDocumentation('unknown docs', {}, async () => {
    const error = new Error('No documentation found');
    error.statusCode = 404;
    error.code = 'no_documentation_found';
    throw error;
  });
  assert.deepEqual(result, { codeSnippets: [], infoSnippets: [], results: [] });
});

test('fixMsysPath rewrites Git Bash path-mangled library ids', () => {
  assert.equal(fixMsysPath('C:/Program Files/Git/reactjs/react.dev'), '/reactjs/react.dev');
  assert.equal(fixMsysPath('/reactjs/react.dev'), '/reactjs/react.dev');
});

test('CLI accepts v3 search hints and preserves the context alias', async () => {
  const calls = [];
  const output = [];
  const io = { stdout: (message) => output.push(message), stderr: () => {} };
  const deps = { search: async (query, options) => {
    calls.push({ query, options });
    return { codeSnippets: [], infoSnippets: [], results: [] };
  } };

  assert.equal(await runCli(['search', 'streaming', '--library', 'Next.js', '--library', 'OpenAI', '--version', '15.4.0', '--language', 'TypeScript'], io, deps), 0);
  assert.equal(await runCli(['context', '/vercel/next.js', 'routing'], io, deps), 0);
  assert.deepEqual(calls, [
    { query: 'streaming', options: { libraries: ['Next.js', 'OpenAI'], version: '15.4.0', language: 'TypeScript' } },
    { query: 'routing', options: { libraries: ['/vercel/next.js'] } }
  ]);
  assert.equal(output.length, 2);
});

test('CLI rejects a version without a library and reports request failures', async () => {
  const errors = [];
  const io = { stdout: () => {}, stderr: (message) => errors.push(message) };
  const deps = { search: async () => { throw new Error('boom'); } };

  assert.equal(await runCli(['search', 'routing', '--version', '15.4.0'], io, deps), 1);
  assert.equal(await runCli(['search', 'routing'], io, deps), 1);
  assert.match(errors.join('\n'), /requires --library/);
  assert.match(errors.join('\n'), /Error searching documentation: boom/);
});
