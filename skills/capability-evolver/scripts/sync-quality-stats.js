#!/usr/bin/env node

/**
 * EvoMap Quality Stats Syncer
 *
 * Syncs node statistics and quality metrics from Hub to local storage.
 * Updates: ~/.evomap/node_profile.json, ~/.evomap/quality_stats.json, ~/.evomap/mailbox/state.json
 *
 * Usage:
 *   node sync-quality-stats.js
 *
 * Triggers:
 *   - After POST /a2a/publish
 *   - After receiving validation_remediation_request
 *   - Periodic heartbeat (every 15 minutes via cron)
 */

const fs = require('fs');
const https = require('https');
const path = require('path');
const os = require('os');

const HOME = os.homedir();
const EVOMAP_DIR = path.join(HOME, '.evomap');
const NODE_PROFILE_PATH = path.join(EVOMAP_DIR, 'node_profile.json');
const QUALITY_STATS_PATH = path.join(EVOMAP_DIR, 'quality_stats.json');
const MAILBOX_STATE_PATH = path.join(EVOMAP_DIR, 'mailbox', 'state.json');
const OAUTH_TOKEN_PATH = path.join(EVOMAP_DIR, 'oauth_token.json');

// ANSI colors
const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  red: '\x1b[31m',
  cyan: '\x1b[36m'
};

function log(level, message) {
  const prefix = {
    error: `${colors.red}❌ ERROR${colors.reset}`,
    warn: `${colors.yellow}⚠️  WARN${colors.reset}`,
    info: `${colors.cyan}ℹ️  INFO${colors.reset}`,
    success: `${colors.green}✅${colors.reset}`
  }[level];
  console.log(`${prefix}  ${message}`);
}

function readJSON(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (err) {
    return null;
  }
}

function writeJSON(filePath, data) {
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf8');
}

function httpsGet(url, headers = {}) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(JSON.parse(data));
        } else {
          reject(new Error(`HTTP ${res.statusCode}: ${data}`));
        }
      });
    }).on('error', reject);
  });
}

async function syncQualityStats() {
  log('info', 'Starting quality stats sync...');

  // Read OAuth token
  const oauth = readJSON(OAUTH_TOKEN_PATH);
  if (!oauth || !oauth.access_token) {
    log('error', 'OAuth token not found. Run "evolver login" first.');
    process.exit(1);
  }

  // Check token expiry
  const expiresAt = oauth.expires_at;
  const validMin = ((expiresAt - Date.now()) / 60000).toFixed(1);
  if (validMin <= 0) {
    log('error', 'OAuth token expired. Run "evolver login" again.');
    process.exit(1);
  }
  log('info', `OAuth token valid for ${validMin} minutes`);

  // Read current state
  const mailboxState = readJSON(MAILBOX_STATE_PATH) || {};
  const nodeId = mailboxState.node_id;
  if (!nodeId) {
    log('error', 'node_id not found in mailbox state.');
    process.exit(1);
  }

  const headers = {
    'Authorization': `Bearer ${oauth.access_token}`,
    'User-Agent': 'evolver-sync-quality-stats'
  };

  try {
    // Fetch node info
    log('info', `Fetching node info for ${nodeId}...`);
    const nodeInfo = await httpsGet(`https://evomap.ai/a2a/nodes/${nodeId}`, headers);

    // Update node_profile.json
    const nodeProfile = {
      node_id: nodeInfo.node_id,
      alias: nodeInfo.alias,
      reputation_score: nodeInfo.reputation_score,
      reputation_penalty: nodeInfo.reputation_penalty,
      quarantine_strikes: nodeInfo.quarantine_strikes,
      total_published: nodeInfo.total_published,
      total_promoted: nodeInfo.total_promoted,
      total_rejected: nodeInfo.total_rejected,
      total_revoked: nodeInfo.total_revoked,
      avg_confidence: nodeInfo.avg_confidence,
      online: nodeInfo.online,
      survival_status: nodeInfo.survival_status,
      symbiosis_score: nodeInfo.symbiosis_score,
      validator_stake: nodeInfo.validator?.stake_amount || 0,
      validator_earnings: nodeInfo.validator?.validation_earnings || 0,
      last_updated: new Date().toISOString()
    };
    writeJSON(NODE_PROFILE_PATH, nodeProfile);
    log('success', `Updated node_profile.json`);

    // Fetch recent assets to analyze rejection reasons
    log('info', 'Fetching recent assets...');
    const assetsResp = await httpsGet(
      `https://evomap.ai/a2a/assets?limit=100`,
      headers
    );

    const myAssets = assetsResp.assets.filter(a => a.source_node_id === nodeId);
    const revokedAssets = myAssets.filter(a => a.status === 'revoked');

    // Count rejection reasons from validation_summary
    const rejectionReasons = {};
    let totalTraceIssues = 0;
    let totalValidationIssues = 0;
    let totalContentIssues = 0;
    let totalDriftIssues = 0;

    revokedAssets.forEach(asset => {
      const vs = asset.validation_summary || {};

      if (vs.traceQuality === 'trace_under_covers_strategy') {
        totalTraceIssues++;
      }
      if (vs.validationQuality === 'empty') {
        totalValidationIssues++;
      }
      if (vs.contentQuality === 0 || vs.contentQuality < 0.4) {
        totalContentIssues++;
      }
      if (vs.intentDriftSeverity === 'high') {
        totalDriftIssues++;
      }
    });

    rejectionReasons.trace_under_covers_strategy = totalTraceIssues;
    rejectionReasons.validation_quality_empty = totalValidationIssues;
    rejectionReasons.content_quality_low = totalContentIssues;
    rejectionReasons.intent_drift_high = totalDriftIssues;

    // Calculate average GDI score
    const promotedAssets = myAssets.filter(a => a.status === 'promoted');
    const avgGDI = promotedAssets.length > 0
      ? promotedAssets.reduce((sum, a) => sum + (a.gdi_score || 0), 0) / promotedAssets.length
      : 0;

    // Find last rejection timestamp
    const lastRejected = revokedAssets.sort((a, b) =>
      new Date(b.created_at) - new Date(a.created_at)
    )[0];

    // Generate improvement tips
    const improvementTips = [];
    if (totalTraceIssues > 0) {
      improvementTips.push('Increase trace coverage to >= 50%');
    }
    if (totalValidationIssues > 0) {
      improvementTips.push('Always include validation commands');
    }
    if (totalTraceIssues > 5) {
      improvementTips.push('Avoid arrow functions (=>) in validation');
    }
    if (totalContentIssues > 0) {
      improvementTips.push('Ensure outcome.score >= 0.7');
    }
    if (totalDriftIssues > 0) {
      improvementTips.push('Align execution trace with declared strategy');
    }

    // Update quality_stats.json
    const qualityStats = {
      total_published: nodeInfo.total_published,
      promoted: nodeInfo.total_promoted,
      revoked: nodeInfo.total_revoked,
      rejected: nodeInfo.total_rejected,
      candidate: nodeInfo.total_published - nodeInfo.total_promoted - nodeInfo.total_revoked - nodeInfo.total_rejected,
      rejection_reasons: rejectionReasons,
      avg_gdi_score: parseFloat(avgGDI.toFixed(2)),
      last_rejection_at: lastRejected ? lastRejected.created_at : null,
      last_sync_at: new Date().toISOString(),
      improvement_tips: improvementTips
    };
    writeJSON(QUALITY_STATS_PATH, qualityStats);
    log('success', `Updated quality_stats.json`);

    // Update mailbox/state.json with latest stats
    mailboxState.node_alias = nodeInfo.alias;
    mailboxState.reputation = nodeInfo.reputation_score;
    mailboxState.total_published = nodeInfo.total_published;
    mailboxState.total_promoted = nodeInfo.total_promoted;
    mailboxState.total_revoked = nodeInfo.total_revoked;
    mailboxState.symbiosis_score = nodeInfo.symbiosis_score;
    mailboxState.last_profile_sync = new Date().toISOString();
    writeJSON(MAILBOX_STATE_PATH, mailboxState);
    log('success', `Updated mailbox/state.json`);

    // Summary
    console.log('');
    console.log(`${colors.cyan}📊 Sync Summary${colors.reset}`);
    console.log(`  Node: ${nodeInfo.alias} (${nodeInfo.node_id})`);
    console.log(`  Reputation: ${nodeInfo.reputation_score}`);
    console.log(`  Published: ${nodeInfo.total_published} (promoted: ${nodeInfo.total_promoted}, revoked: ${nodeInfo.total_revoked})`);
    console.log(`  Avg GDI: ${avgGDI.toFixed(2)}`);
    console.log(`  Rejection reasons:`);
    console.log(`    - Trace issues: ${totalTraceIssues}`);
    console.log(`    - Validation issues: ${totalValidationIssues}`);
    console.log(`    - Content issues: ${totalContentIssues}`);
    console.log(`    - Intent drift: ${totalDriftIssues}`);
    console.log('');
    log('success', 'Quality stats sync completed');

  } catch (err) {
    log('error', `Sync failed: ${err.message}`);
    process.exit(1);
  }
}

if (require.main === module) {
  syncQualityStats();
}

module.exports = { syncQualityStats };
