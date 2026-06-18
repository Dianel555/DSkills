#!/usr/bin/env node

/**
 * EvoMap Bundle Builder
 *
 * Computes content-addressable asset_ids and assembles a GEP-A2A publish
 * envelope from a spec file. Complements validate-bundle.js (which only checks
 * hashes — nothing else computes them).
 *
 * The canonicalJSON below is byte-identical to validate-bundle.js and the Hub.
 *
 * Spec file: { "gene": {...}, "capsule": {...}, "event": {...} } with NO asset_id
 * fields. Cross-references are derived automatically (content-addressed):
 *   capsule.gene      = <gene asset_id>
 *   event.capsule_id  = <capsule asset_id>
 *   event.genes_used  = [<gene asset_id>]
 *
 * Usage: node build-bundle.js <spec.json> [--out bundle.json] [--node-id node_xxx]
 * node-id falls back to $A2A_NODE_ID. Then validate: node validate-bundle.js <out>
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// Canonical JSON for asset ID computation: recursive key sort, compact
// separators, ensure_ascii=False -- byte-identical to the Hub's serialization.
function canonicalJSON(obj) {
  if (obj === null || typeof obj !== 'object') return JSON.stringify(obj);
  if (Array.isArray(obj)) return '[' + obj.map(canonicalJSON).join(',') + ']';
  return '{' + Object.keys(obj).sort()
    .map(k => JSON.stringify(k) + ':' + canonicalJSON(obj[k])).join(',') + '}';
}

function computeAssetId(asset) {
  const payload = { ...asset };
  delete payload.asset_id;
  return 'sha256:' + crypto.createHash('sha256').update(canonicalJSON(payload), 'utf8').digest('hex');
}

function buildBundle(spec, nodeId) {
  const gene = spec.gene;
  const capsule = spec.capsule;
  const event = spec.event;
  if (!gene || !capsule) throw new Error('spec must contain at least a gene and a capsule');

  gene.asset_id = computeAssetId(gene);

  capsule.gene = gene.asset_id;            // derived cross-reference
  capsule.asset_id = computeAssetId(capsule);

  const assets = [gene, capsule];
  if (event) {
    event.capsule_id = capsule.asset_id;   // derived cross-references
    event.genes_used = [gene.asset_id];
    event.asset_id = computeAssetId(event);
    assets.push(event);
  }

  return {
    protocol: 'gep-a2a',
    protocol_version: '1.0.0',
    message_type: 'publish',
    message_id: 'msg_' + Date.now(),
    sender_id: nodeId,
    timestamp: new Date().toISOString(),
    payload: { assets },
  };
}

function main() {
  const args = process.argv.slice(2);
  const specPath = args.find(a => !a.startsWith('--'));
  const outArg = args.find(a => a.startsWith('--out='));
  const nodeArg = args.find(a => a.startsWith('--node-id='));
  const out = outArg ? outArg.slice('--out='.length) : 'bundle.json';
  const nodeId = nodeArg ? nodeArg.slice('--node-id='.length) : (process.env.A2A_NODE_ID || '');

  if (!specPath) {
    console.log('Usage: node build-bundle.js <spec.json> [--out bundle.json] [--node-id node_xxx]');
    console.log('Spec: { "gene": {...}, "capsule": {...}, "event": {...} } with no asset_id fields.');
    process.exit(1);
  }
  if (!nodeId) {
    console.error('ERROR: no node id — pass --node-id=node_xxx or set $A2A_NODE_ID');
    process.exit(1);
  }

  const spec = JSON.parse(fs.readFileSync(path.resolve(specPath), 'utf8'));
  const bundle = buildBundle(spec, nodeId);
  fs.writeFileSync(path.resolve(out), JSON.stringify(bundle, null, 2), 'utf8');

  for (const a of bundle.payload.assets) console.log(`${a.type.padEnd(15)} ${a.asset_id}`);
  console.log('wrote ' + path.resolve(out));
  console.log('next: node validate-bundle.js ' + out);
}

if (require.main === module) main();

module.exports = { buildBundle, computeAssetId, canonicalJSON };
