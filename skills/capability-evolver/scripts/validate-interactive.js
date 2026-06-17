#!/usr/bin/env node

/**
 * Interactive Bundle Validator
 *
 * Interactive step-by-step validation with explanations and fix suggestions.
 *
 * Usage: node scripts/validate-interactive.js [bundle.json]
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { validateBundle, validateCommand, computeAssetId } = require('./validate-bundle.js');

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function question(query) {
  return new Promise(resolve => rl.question(query, resolve));
}

const colors = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
  magenta: '\x1b[35m'
};

function colorize(text, color) {
  return `${colors[color]}${text}${colors.reset}`;
}

function box(title, content) {
  const width = 70;
  const border = '─'.repeat(width);
  console.log(`┌${border}┐`);
  console.log(`│ ${colorize(title, 'bright').padEnd(width + 9)} │`);
  console.log(`├${border}┤`);
  content.split('\n').forEach(line => {
    const padding = ' '.repeat(Math.max(0, width - line.length));
    console.log(`│ ${line}${padding} │`);
  });
  console.log(`└${border}┘`);
}

async function interactiveValidation(bundle) {
  console.clear();
  console.log(colorize('\n🎯 Interactive Bundle Validator\n', 'bright'));
  console.log('This tool will guide you through validating your GEP-A2A bundle step by step.\n');

  await question('Press Enter to start...');

  // Step 1: Bundle structure
  console.clear();
  box('Step 1: Bundle Structure', 'Checking for Gene + Capsule + EvolutionEvent...');
  console.log('');

  const payload = bundle.payload || bundle;
  const assets = payload.assets || [];

  const gene = assets.find(a => a.type === 'Gene');
  const capsule = assets.find(a => a.type === 'Capsule');
  const event = assets.find(a => a.type === 'EvolutionEvent');

  if (!gene) {
    console.log(colorize('❌ Gene asset is MISSING', 'red'));
    console.log('   A Gene defines the reusable strategy template.');
    console.log('   Every bundle must include a Gene.\n');
  } else {
    console.log(colorize('✅ Gene asset found', 'green'));
  }

  if (!capsule) {
    console.log(colorize('❌ Capsule asset is MISSING', 'red'));
    console.log('   A Capsule is the validated fix produced by applying the Gene.');
    console.log('   Every bundle must include a Capsule.\n');
  } else {
    console.log(colorize('✅ Capsule asset found', 'green'));
  }

  if (!event) {
    console.log(colorize('⚠️  EvolutionEvent is MISSING', 'yellow'));
    console.log('   Not required but strongly recommended.');
    console.log('   Missing EvolutionEvent results in -6.7% GDI score penalty.\n');
  } else {
    console.log(colorize('✅ EvolutionEvent found', 'green'));
  }

  await question('\nPress Enter to continue...');

  // Step 2: Gene validation
  if (gene) {
    console.clear();
    box('Step 2: Gene Validation', 'Checking Gene structure and required fields...');
    console.log('');

    // Strategy
    if (!gene.strategy || gene.strategy.length < 2) {
      console.log(colorize('❌ Gene.strategy is missing or has < 2 items', 'red'));
      console.log('   Hub ENFORCES this: bundles without 2+ strategy items are rejected.');
      console.log('   Error code: gene_strategy_required\n');
      console.log('   Fix: Add at least 2 actionable steps (each ≥15 chars)');
      console.log('   Example:');
      console.log('     "strategy": [');
      console.log('       "Wrap the failing call in a bounded retry helper",');
      console.log('       "Apply exponential backoff with jitter between attempts"');
      console.log('     ]\n');
    } else {
      console.log(colorize(`✅ Gene.strategy has ${gene.strategy.length} items`, 'green'));
      console.log('   Strategy steps:');
      gene.strategy.forEach((s, i) => console.log(`     ${i + 1}. ${s}`));
      console.log('');
    }

    // Validation
    if (!gene.validation || gene.validation.length === 0) {
      console.log(colorize('❌ Gene.validation is missing or empty', 'red'));
      console.log('   Hub ENFORCES this: bundles without validation are rejected.');
      console.log('   Error code: gene_validation_required\n');
      console.log('   Fix: Add at least 1 self-contained validation command');
      console.log('   Example:');
      console.log('     "validation": ["node -e \\"if (1 + 1 !== 2) process.exit(1)\\"]\n');
    } else {
      console.log(colorize(`✅ Gene.validation has ${gene.validation.length} command(s)`, 'green'));
      let allSafe = true;
      gene.validation.forEach((cmd, i) => {
        const check = validateCommand(cmd);
        if (!check.safe) {
          allSafe = false;
          console.log(colorize(`   ❌ Command ${i + 1} is DANGEROUS: ${check.reason}`, 'red'));
          console.log(`      "${cmd}"`);
          console.log('      Hub will reject with: validation_command_dangerous\n');
        } else {
          console.log(colorize(`   ✅ Command ${i + 1} is safe`, 'green'));
        }
      });

      if (!allSafe) {
        console.log('   Forbidden patterns: ; && || > >> eval process.env curl rm');
        console.log('   Use pure arithmetic validation:');
        console.log('     node -e "if (350 !== 50 + 300) process.exit(1)"\n');
      }
    }

    // Signals
    if (!gene.signals_match || gene.signals_match.length === 0) {
      console.log(colorize('❌ Gene.signals_match is missing or empty', 'red'));
    } else {
      console.log(colorize(`✅ Gene.signals_match has ${gene.signals_match.length} signal(s)`, 'green'));
    }

    await question('\nPress Enter to continue...');
  }

  // Step 3: Capsule validation
  if (capsule) {
    console.clear();
    box('Step 3: Capsule Validation', 'Checking Capsule content and quality thresholds...');
    console.log('');

    // Outcome score
    if (capsule.outcome && typeof capsule.outcome.score === 'number') {
      if (capsule.outcome.score < 0.7) {
        console.log(colorize(`❌ outcome.score is ${capsule.outcome.score} < 0.7`, 'red'));
        console.log('   Hub requires outcome.score >= 0.7 for promotion.');
        console.log('   This Capsule will be rejected.\n');
      } else {
        console.log(colorize(`✅ outcome.score is ${capsule.outcome.score} >= 0.7`, 'green'));
      }
    } else {
      console.log(colorize('❌ outcome.score is missing or invalid', 'red'));
    }

    // Blast radius
    if (!capsule.blast_radius || capsule.blast_radius.files === 0 || capsule.blast_radius.lines === 0) {
      console.log(colorize('❌ blast_radius.files or .lines is 0', 'red'));
      console.log('   Hub requires both > 0 for eligibility.');
      console.log('   Even a 1-line change should be: {files: 1, lines: 1}\n');
    } else {
      console.log(colorize(`✅ blast_radius: ${capsule.blast_radius.files} file(s), ${capsule.blast_radius.lines} line(s)`, 'green'));
    }

    // Trace coverage
    if (capsule.execution_trace && gene && gene.strategy) {
      const trace = capsule.execution_trace;
      const strategy = gene.strategy;
      const coverage = trace.length / strategy.length;
      const coveragePct = (coverage * 100).toFixed(1);

      console.log('');
      console.log(colorize('Trace Coverage Analysis:', 'cyan'));
      console.log(`  Trace steps: ${trace.length}`);
      console.log(`  Strategy items: ${strategy.length}`);
      console.log(`  Coverage: ${coveragePct}%`);

      if (trace.length < 2) {
        console.log(colorize('  ❌ Trace has < 2 steps (minimum required)', 'red'));
      } else if (coverage < 0.5) {
        console.log(colorize(`  ❌ Coverage ${coveragePct}% < 50%`, 'red'));
        console.log('     Hub will reject with: trace_under_covers_strategy');
        console.log('     Fix: Add more execution steps OR reduce strategy items\n');
      } else if (coverage < 0.8) {
        console.log(colorize(`  ⚠️  Coverage ${coveragePct}% is acceptable but < 80% (optimal)`, 'yellow'));
      } else {
        console.log(colorize(`  ✅ Coverage ${coveragePct}% is excellent`, 'green'));
      }

      console.log('');
      console.log('  Execution steps:');
      trace.forEach((step, i) => {
        const hasAction = !!step.action;
        const hasResult = !!step.result;
        const status = hasAction && hasResult ? colorize('✅', 'green') : colorize('⚠️ ', 'yellow');
        console.log(`    ${status} Step ${i + 1}: ${step.action || '(no action)'}`);
        if (!hasResult) {
          console.log(`        (missing result field - recommended)`);
        }
      });
    } else if (!capsule.execution_trace) {
      console.log('');
      console.log(colorize('⚠️  execution_trace is missing', 'yellow'));
      console.log('   Hub will evaluate trace quality on publish.');
      console.log('   Missing trace may result in trace_missing flag.\n');
    }

    await question('\nPress Enter to continue...');
  }

  // Step 4: Asset IDs
  console.clear();
  box('Step 4: Asset ID Verification', 'Checking content-addressable hashes...');
  console.log('');

  let idErrors = 0;
  [gene, capsule, event].forEach(asset => {
    if (!asset) return;
    const type = asset.type;
    if (!asset.asset_id) {
      console.log(colorize(`❌ ${type}: asset_id is missing`, 'red'));
      idErrors++;
    } else {
      const computed = computeAssetId(asset);
      if (computed !== asset.asset_id) {
        console.log(colorize(`❌ ${type}: asset_id MISMATCH`, 'red'));
        console.log(`   Declared: ${asset.asset_id}`);
        console.log(`   Computed: ${computed}`);
        console.log('   Hub will reject with: asset_id_mismatch\n');
        idErrors++;
      } else {
        console.log(colorize(`✅ ${type}: asset_id verified`, 'green'));
        console.log(`   ${asset.asset_id.slice(0, 50)}...`);
      }
    }
  });

  if (idErrors > 0) {
    console.log('');
    console.log('Fix: Recompute asset_id using canonical JSON (sorted keys, no whitespace)');
    console.log('See docs/skill-structures.md for Python example.\n');
  }

  await question('\nPress Enter to see final summary...');

  // Final summary
  console.clear();
  const result = validateBundle(bundle);

  box('📊 Final Validation Report', `Errors: ${result.errors.length} | Warnings: ${result.warnings.length}`);
  console.log('');

  if (result.errors.length > 0) {
    console.log(colorize('Errors:', 'red'));
    result.errors.forEach(e => console.log(`  ❌ ${e}`));
    console.log('');
  }

  if (result.warnings.length > 0) {
    console.log(colorize('Warnings:', 'yellow'));
    result.warnings.forEach(w => console.log(`  ⚠️  ${w}`));
    console.log('');
  }

  if (result.valid) {
    console.log(colorize('✅ Bundle is READY to publish!', 'green'));
    console.log('');
    console.log('Next steps:');
    console.log('  1. (Optional) Dry-run with Hub: curl -X POST /a2a/validate');
    console.log('  2. Publish: curl -X POST /a2a/publish');
    console.log('');
  } else {
    console.log(colorize('❌ Bundle has ERRORS that must be fixed before publishing.', 'red'));
    console.log('');
    console.log('See docs/skill-structures.md and docs/skill-troubleshooting.md for guidance.');
    console.log('');
  }

  const answer = await question('Would you like to see detailed fix suggestions? (y/n): ');
  if (answer.toLowerCase() === 'y') {
    console.log('');
    console.log(colorize('💡 Fix Suggestions:', 'cyan'));
    console.log('');

    if (result.errors.some(e => e.includes('trace_under_covers_strategy') || e.includes('trace coverage'))) {
      console.log('📌 Trace Coverage Issue:');
      console.log('   Add more detailed execution steps to your Capsule.execution_trace.');
      console.log('   Each step should include:');
      console.log('     - action: what was done (string, >= 20 chars)');
      console.log('     - result: outcome of the action ("success" | "failure")');
      console.log('   Aim for trace.length / strategy.length >= 0.5 (50%)\n');
    }

    if (result.errors.some(e => e.includes('validation_command_dangerous'))) {
      console.log('📌 Dangerous Validation Command:');
      console.log('   Remove shell operators from validation commands.');
      console.log('   Forbidden: ; && || > >> eval process.env curl rm');
      console.log('   Use pure arithmetic validation:');
      console.log('     node -e "if (Math.sqrt(16) !== 4) process.exit(1)"\n');
    }

    if (result.errors.some(e => e.includes('outcome.score'))) {
      console.log('📌 Low Outcome Score:');
      console.log('   Increase confidence in your fix before publishing.');
      console.log('   Hub requires outcome.score >= 0.7');
      console.log('   Only publish Capsules that genuinely solved the problem.\n');
    }

    if (result.errors.some(e => e.includes('blast_radius'))) {
      console.log('📌 Zero Blast Radius:');
      console.log('   Ensure blast_radius reflects actual changes.');
      console.log('   Even a 1-line change should have:');
      console.log('     "blast_radius": { "files": 1, "lines": 1 }\n');
    }
  }

  rl.close();
}

async function main() {
  const args = process.argv.slice(2);

  let filePath;
  if (args.length === 0) {
    // Interactive file picker
    console.log(colorize('🎯 Interactive Bundle Validator\n', 'bright'));
    filePath = await question('Enter path to bundle JSON file: ');
    filePath = filePath.trim().replace(/^["']|["']$/g, ''); // Remove quotes
  } else {
    filePath = args[0];
  }

  filePath = path.resolve(filePath);

  if (!fs.existsSync(filePath)) {
    console.log(colorize(`\n❌ File not found: ${filePath}`, 'red'));
    rl.close();
    process.exit(1);
  }

  let bundle;
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    bundle = JSON.parse(content);
  } catch (err) {
    console.log(colorize(`\n❌ Failed to parse JSON: ${err.message}`, 'red'));
    rl.close();
    process.exit(1);
  }

  await interactiveValidation(bundle);
}

if (require.main === module) {
  main().catch(err => {
    console.error(colorize(`\n❌ Error: ${err.message}`, 'red'));
    rl.close();
    process.exit(1);
  });
}

module.exports = { interactiveValidation };
