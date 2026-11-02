const test = require('node:test');
const assert = require('node:assert/strict');
const https = require('node:https');
const { EventEmitter } = require('node:events');
const { makeRequest } = require('../context7-api.cjs');

function fakeRequest(t) {
  let respond;
  const req = new EventEmitter();
  req.destroyed = false;
  req.destroy = () => { req.destroyed = true; };
  t.mock.method(https, 'get', (_url, _options, callback) => {
    respond = callback;
    return req;
  });
  const res = new EventEmitter();
  res.statusCode = 200;
  res.destroy = () => { res.destroyed = true; };
  return { req, res, respond: () => respond(res) };
}

test('valid UTF-8 JSON is preserved across chunk boundaries', async (t) => {
  const fake = fakeRequest(t);
  const result = makeRequest('/search', {}, null);
  fake.respond();
  const body = Buffer.from('{"message":"你好"}');
  const split = body.indexOf(Buffer.from('你')) + 1;
  fake.res.emit('data', body.subarray(0, split));
  fake.res.emit('data', body.subarray(split));
  fake.res.emit('end');
  assert.deepEqual(await result, { message: '你好' });
});

test('response size is bounded by bytes and closes the request', async (t) => {
  const fake = fakeRequest(t);
  const result = makeRequest('/search', {}, null);
  fake.respond();
  fake.res.emit('data', Buffer.alloc(4 * 1024 * 1024 + 1, 32));
  fake.res.emit('end');
  await assert.rejects(result, /too large/i);
  assert.equal(fake.req.destroyed, true);
});

test('aborted response rejects instead of hanging', async (t) => {
  const fake = fakeRequest(t);
  const result = makeRequest('/search', {}, null);
  fake.respond();
  fake.res.emit('aborted');
  fake.res.emit('end');
  await assert.rejects(result, /abort/i);
});

test('response stream errors reject the request', async (t) => {
  const fake = fakeRequest(t);
  const result = makeRequest('/search', {}, null);
  fake.respond();
  const error = new Error('synthetic stream failure');
  // Add a test listener so the baseline produces a normal assertion failure.
  fake.res.on('error', () => {});
  fake.res.emit('error', error);
  fake.res.emit('end');
  await assert.rejects(result, /synthetic stream failure/);
});

test('request has an absolute deadline that destroys a stalled request', async (t) => {
  const fake = fakeRequest(t);
  let deadline;
  t.mock.method(global, 'setTimeout', (callback) => { deadline = callback; return { unref() {} }; });
  t.mock.method(global, 'clearTimeout', () => {});
  const result = makeRequest('/search', {}, null);
  assert.equal(typeof deadline, 'function');
  deadline();
  await assert.rejects(result, /timed? ?out|deadline/i);
  assert.equal(fake.req.destroyed, true);
});
