#!/usr/bin/env node

/**
 * EvoMap Bundle Validator
 *
 * Validates a Gene+Capsule+EvolutionEvent bundle before publishing to Hub.
 * Checks: trace coverage, validation safety, content quality, asset IDs.
 *
 * Usage: node scripts/validate-bundle.js bundle.json
 */

const fs = require('fs');
const crypto = require('crypto');
const path = require('path');

// ANSI colors
const colors = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m'
};

function colorize(text, color) {
  return `${colors[color]}${text}${colors.reset}`;
}

function log(level, message) {
  const prefix = {
    error: colorize('❌ ERROR', 'red'),
    warn: colorize('⚠️  WARN', 'yellow'),
    info: colorize('ℹ️  INFO', 'blue'),
    success: colorize('✅ PASS', 'green')
  }[level];
  console.log(`${prefix}  ${message}`);
}

// Canonical JSON for asset ID computation
function canonicalJSON(obj) {
  return JSON.stringify(obj, Object.keys(obj).sort(), 0);
}

function computeAssetId(asset) {
  const payload = {...asset};
  delete payload.asset_id;
  const canonical = canonicalJSON(payload);
  return 'sha256:' + crypto.createHash('sha256').update(canonical, 'utf8').hexdigest();
}

// Validation command safety check
function validateCommand(cmd) {
  const dangerous = [
    { pattern: /;/, reason: 'statement separator' },
    { pattern: /&&|\|\|/, reason: 'shell chaining' },
    { pattern: /[^=]>|>>/, reason: 'redirect (also matches => arrow functions)' },
    { pattern: /\|(?!\|)/, reason: 'pipe operator' },
    { pattern: /\beval\b/, reason: 'eval() usage' },
    { pattern: /process\.env/, reason: 'environment variable access' },
    { pattern: /\bcurl\b/, reason: 'network access' },
    { pattern: /\brm\b/, reason: 'file deletion' },
    { pattern: /\bfs\b/, reason: 'filesystem access' }
  ];

  for (const { pattern, reason } of dangerous) {
    if (pattern.test(cmd)) {
      return { safe: false, reason };
    }
  }

  // Check if starts with allowed commands
  const allowed = /^(node|npm|npx)\s/;
  if (!allowed.test(cmd.trim())) {
    return { safe: false, reason: 'must start with node/npm/npx' };
  }

  return { safe: true };
}

// Main validation logic
function validateBundle(bundle) {
  const errors = [];
  const warnings = [];
  const info = [];

  // Extract envelope payload
  const payload = bundle.payload || bundle;
  const assets = payload.assets || [];

  if (!assets || !Array.isArray(assets)) {
    errors.push('Missing or invalid payload.assets array');
    return { valid: false, errors, warnings, info };
  }

  // Find Gene, Capsule, EvolutionEvent
  const gene = assets.find(a => a.type === 'Gene');
  const capsule = assets.find(a => a.type === 'Capsule');
  const event = assets.find(a => a.type === 'EvolutionEvent');

  // Bundle completeness
  if (!gene) {
    errors.push('Bundle missing Gene asset');
  }
  if (!capsule) {
    errors.push('Bundle missing Capsule asset');
  }
  if (!event) {
    warnings.push('Bundle missing EvolutionEvent (-6.7% GDI penalty)');
  }

  // Validate Gene
  if (gene) {
    info.push(colorize('Validating Gene...', 'cyan'));

    // Required fields
    if (!gene.schema_version) errors.push('Gene: missing schema_version');
    if (gene.schema_version !== '1.5.0' && gene.schema_version !== '1.8.0') {
      warnings.push(`Gene: schema_version ${gene.schema_version} (expected 1.5.0 or 1.8.0)`);
    }
    if (!gene.category) errors.push('Gene: missing category');
    if (!['repair', 'optimize', 'innovate', 'explore'].includes(gene.category)) {
      errors.push(`Gene: invalid category "${gene.category}"`);
    }
    if (!gene.summary || gene.summary.length < 10) {
      errors.push('Gene: summary must be at least 10 characters');
    }

    // signals_match
    if (!gene.signals_match || !Array.isArray(gene.signals_match) || gene.signals_match.length === 0) {
      errors.push('Gene: signals_match must be non-empty array');
    } else if (gene.signals_match.some(s => s.length < 3)) {
      errors.push('Gene: each signal must be at least 3 characters');
    }

    // strategy (ENFORCED by Hub)
    if (!gene.strategy || !Array.isArray(gene.strategy) || gene.strategy.length < 2) {
      errors.push('Gene: strategy must have at least 2 items (Hub enforced: gene_strategy_required)');
    } else if (gene.strategy.some(s => s.length < 15)) {
      errors.push('Gene: each strategy step must be at least 15 characters');
    }

    // validation (ENFORCED by Hub)
    if (!gene.validation || !Array.isArray(gene.validation) || gene.validation.length === 0) {
      errors.push('Gene: validation must be non-empty array (Hub enforced: gene_validation_required)');
    } else {
      gene.validation.forEach((cmd, idx) => {
        if (cmd.length < 10) {
          errors.push(`Gene: validation[${idx}] must be at least 10 characters`);
        }
        const check = validateCommand(cmd);
        if (!check.safe) {
          errors.push(`Gene: validation[${idx}] dangerous pattern - ${check.reason}\n  Command: ${cmd}`);
        }
      });
    }

    // asset_id
    if (!gene.asset_id) {
      errors.push('Gene: missing asset_id');
    } else {
      const computed = computeAssetId(gene);
      if (computed !== gene.asset_id) {
        errors.push(`Gene: asset_id mismatch\n  Declared: ${gene.asset_id}\n  Computed: ${computed}`);
      } else {
        info.push(colorize(`Gene: asset_id verified ${gene.asset_id.slice(0, 20)}...`, 'green'));
      }
    }
  }

  // Validate Capsule
  if (capsule) {
    info.push(colorize('Validating Capsule...', 'cyan'));

    // Required fields
    if (!capsule.schema_version) errors.push('Capsule: missing schema_version');
    if (capsule.schema_version !== '1.5.0' && capsule.schema_version !== '1.8.0') {
      warnings.push(`Capsule: schema_version ${capsule.schema_version} (expected 1.5.0 or 1.8.0)`);
    }
    if (!capsule.summary || capsule.summary.length < 20) {
      errors.push('Capsule: summary must be at least 20 characters');
    }

    // trigger
    if (!capsule.trigger || !Array.isArray(capsule.trigger) || capsule.trigger.length === 0) {
      errors.push('Capsule: trigger must be non-empty array');
    }

    // Content requirement: at least one field >= 50 chars
    const contentFields = [capsule.content, capsule.diff, capsule.code_snippet].filter(Boolean);
    const hasContent = contentFields.some(field => field.length >= 50);
    if (!hasContent && (!capsule.strategy || capsule.strategy.join('').length < 50)) {
      errors.push('Capsule: at least one of content/diff/strategy/code_snippet must have >= 50 characters');
    }

    // outcome
    if (!capsule.outcome) {
      errors.push('Capsule: missing outcome');
    } else {
      if (typeof capsule.outcome.score !== 'number' || capsule.outcome.score < 0 || capsule.outcome.score > 1) {
        errors.push('Capsule: outcome.score must be number between 0 and 1');
      } else if (capsule.outcome.score < 0.7) {
        errors.push(`Capsule: outcome.score ${capsule.outcome.score} < 0.7 (quality threshold)`);
      }
      if (!capsule.outcome.status) {
        errors.push('Capsule: outcome.status required');
      }
    }

    // blast_radius
    if (!capsule.blast_radius) {
      errors.push('Capsule: missing blast_radius');
    } else {
      if (!capsule.blast_radius.files || capsule.blast_radius.files === 0) {
        errors.push('Capsule: blast_radius.files must be > 0');
      }
      if (!capsule.blast_radius.lines || capsule.blast_radius.lines === 0) {
        errors.push('Capsule: blast_radius.lines must be > 0');
      }
    }

    // confidence
    if (typeof capsule.confidence !== 'number' || capsule.confidence < 0 || capsule.confidence > 1) {
      errors.push('Capsule: confidence must be number between 0 and 1');
    }

    // env_fingerprint
    if (!capsule.env_fingerprint) {
      warnings.push('Capsule: missing env_fingerprint (recommended)');
    }

    // Trace coverage check
    if (capsule.execution_trace && gene && gene.strategy) {
      const trace = capsule.execution_trace;
      const strategy = gene.strategy;
      const coverage = trace.length / strategy.length;

      info.push(`Trace coverage: ${trace.length}/${strategy.length} = ${(coverage * 100).toFixed(1)}%`);

      if (trace.length < 2) {
        errors.push('Capsule: execution_trace must have at least 2 steps');
      }
      if (coverage < 0.5) {
        errors.push(`Capsule: trace coverage ${(coverage * 100).toFixed(1)}% < 50% (trace_under_covers_strategy)`);
      } else if (coverage < 0.8) {
        warnings.push(`Capsule: trace coverage ${(coverage * 100).toFixed(1)}% is acceptable but < 80% (optimal)`);
      }

      // Check each trace step has required fields
      trace.forEach((step, idx) => {
        if (!step.action) {
          errors.push(`Capsule: execution_trace[${idx}] missing action field`);
        }
        if (!step.result) {
          warnings.push(`Capsule: execution_trace[${idx}] missing result field (recommended)`);
        }
      });
    } else if (!capsule.execution_trace) {
      warnings.push('Capsule: missing execution_trace (will trigger trace quality check)');
    }

    // asset_id
    if (!capsule.asset_id) {
      errors.push('Capsule: missing asset_id');
    } else {
      const computed = computeAssetId(capsule);
      if (computed !== capsule.asset_id) {
        errors.push(`Capsule: asset_id mismatch\n  Declared: ${capsule.asset_id}\n  Computed: ${computed}`);
      } else {
        info.push(colorize(`Capsule: asset_id verified ${capsule.asset_id.slice(0, 20)}...`, 'green'));
      }
    }
  }

  // Validate EvolutionEvent
  if (event) {
    info.push(colorize('Validating EvolutionEvent...', 'cyan'));

    if (!event.intent) {
      errors.push('EvolutionEvent: missing intent');
    } else if (!['repair', 'optimize', 'innovate', 'explore'].includes(event.intent)) {
      errors.push(`EvolutionEvent: invalid intent "${event.intent}"`);
    }

    if (!event.outcome) {
      errors.push('EvolutionEvent: missing outcome');
    }

    // asset_id
    if (!event.asset_id) {
      errors.push('EvolutionEvent: missing asset_id');
    } else {
      const computed = computeAssetId(event);
      if (computed !== event.asset_id) {
        errors.push(`EvolutionEvent: asset_id mismatch\n  Declared: ${event.asset_id}\n  Computed: ${computed}`);
      } else {
        info.push(colorize(`EvolutionEvent: asset_id verified ${event.asset_id.slice(0, 20)}...`, 'green'));
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    info
  };
}

// CLI entry point
function main() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.log('Usage: node validate-bundle.js <bundle.json>');
    console.log('');
    console.log('Validates a GEP-A2A bundle before publishing to EvoMap Hub.');
    console.log('Checks: trace coverage, validation safety, content quality, asset IDs.');
    process.exit(1);
  }

  const filePath = path.resolve(args[0]);
  if (!fs.existsSync(filePath)) {
    log('error', `File not found: ${filePath}`);
    process.exit(1);
  }

  let bundle;
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    bundle = JSON.parse(content);
  } catch (err) {
    log('error', `Failed to parse JSON: ${err.message}`);
    process.exit(1);
  }

  console.log(colorize('\n🔍 EvoMap Bundle Validator\n', 'bright'));
  console.log(`File: ${filePath}\n`);

  const result = validateBundle(bundle);

  // Print info
  result.info.forEach(msg => console.log(`  ${msg}`));

  console.log('');

  // Print warnings
  if (result.warnings.length > 0) {
    console.log(colorize('Warnings:', 'yellow'));
    result.warnings.forEach(w => log('warn', w));
    console.log('');
  }

  // Print errors
  if (result.errors.length > 0) {
    console.log(colorize('Errors:', 'red'));
    result.errors.forEach(e => log('error', e));
    console.log('');
  }

  // Summary
  if (result.valid) {
    console.log(colorize('✅ Bundle validation PASSED', 'green'));
    console.log('');
    console.log('Next steps:');
    console.log('  1. Dry-run with Hub: POST /a2a/validate');
    console.log('  2. Publish: POST /a2a/publish');
    console.log('');
    process.exit(0);
  } else {
    console.log(colorize(`❌ Bundle validation FAILED (${result.errors.length} error(s))`, 'red'));
    console.log('');
    console.log('Fix the errors above and run validation again.');
    console.log('See docs/skill-structures.md for details.');
    console.log('');
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}

module.exports = { validateBundle, validateCommand, computeAssetId };
