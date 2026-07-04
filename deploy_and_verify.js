/**
 * deploy_and_verify.js — 部署前校验 + 推送 + 远程验收
 *
 * 流程：
 *   1. 语法校验（node validate_index_html.js）
 *   2. git push 触发 GitHub Pages 部署
 *   3. 如失败自动重试 2 次（间隔 45s）
 *   4. 部署后拉取远程页面做验收
 *   5. 写入状态文件
 *
 * 用法: node deploy_and_verify.js
 *   返回值: 0 = 验收通过，非 0 = 部署或验收失败
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const https = require('https');
const http = require('http');

const REPO_DIR = __dirname;
const INDEX_HTML = path.join(REPO_DIR, 'index.html');
const STATUS_FILE = path.join(REPO_DIR, 'workbuddy_news_update_status.json');

const DEPLOY_URL = 'https://berniezhu86.github.io/daily-news/';
const MAX_RETRIES = 2;
const RETRY_INTERVAL_MS = 45 * 1000;

// ============================================================
// 工具函数
// ============================================================

function now() {
  return new Date().toISOString();
}

function cnNow() {
  var d = new Date();
  return d.getFullYear() + '-' +
    String(d.getMonth()+1).padStart(2,'0') + '-' +
    String(d.getDate()).padStart(2,'0') + ' ' +
    String(d.getHours()).padStart(2,'0') + ':' +
    String(d.getMinutes()).padStart(2,'0');
}

function sleep(ms) {
  return new Promise(function(resolve) { setTimeout(resolve, ms); });
}

function exec(cmd) {
  try {
    return execSync(cmd, { cwd: REPO_DIR, timeout: 60000, stdio: ['pipe', 'pipe', 'pipe'] }).toString().trim();
  } catch(e) {
    return { error: e.stderr ? e.stderr.toString().trim() : e.message };
  }
}

function getCommitHash() {
  var r = exec('git rev-parse --short HEAD');
  return typeof r === 'string' ? r : 'unknown';
}

function getContentVersion() {
  try {
    var html = fs.readFileSync(INDEX_HTML, 'utf-8');
    var m = html.match(/content_version["\s:=]+["']([^"']+)["']/);
    if (m) return m[1];
    m = html.match(/\bversion["\s:=]+["']([^"']+)["']/);
    if (m) return m[1];
    m = html.match(/\bv(\d{8}v\d+)/);
    if (m) return m[1];
    return '';
  } catch(e) { return ''; }
}

function fetchUrl(url) {
  return new Promise(function(resolve, reject) {
    var client = url.startsWith('https') ? https : http;
    client.get(url, { timeout: 30000 }, function(resp) {
      var data = '';
      resp.on('data', function(chunk) { data += chunk; });
      resp.on('end', function() {
        resolve({ status: resp.statusCode, body: data });
      });
    }).on('error', function(e) {
      reject(e);
    });
  });
}

function writeStatus(statusObj) {
  statusObj.checked_at = cnNow();
  try {
    var existing = {};
    try { existing = JSON.parse(fs.readFileSync(STATUS_FILE, 'utf-8')); } catch(e) {}
    var merged = Object.assign({}, existing, statusObj);
    fs.writeFileSync(STATUS_FILE, JSON.stringify(merged, null, 2), 'utf-8');
    console.log('状态文件已更新');
  } catch(e) {
    console.error('写状态文件失败:', e.message);
  }
}

// ============================================================
// 主流程
// ============================================================

async function main() {
  console.log('=== deploy_and_verify.js 启动 ===\n');

  // ---- 步骤1: 语法校验 ----
  console.log('▶ 步骤1: JS语法校验');
  var validateResult = exec('node validate_index_html.js');
  if (validateResult.error) {
    console.error('❌ 语法校验失败:');
    console.error(validateResult.error);
    writeStatus({
      deploy_status: 'failed',
      deploy_error: '语法校验失败: ' + validateResult.error,
    });
    process.exit(1);
  }
  console.log('✅ 语法校验通过\n');

  // ---- 步骤2: 获取当前信息 ----
  var commitHash = getCommitHash();
  var contentVer = getContentVersion();
  console.log('▶ 提交: ' + commitHash);
  console.log('▶ 内容版本: ' + contentVer);

  // ---- 步骤3: 推送 ----
  console.log('\n▶ 步骤2: 推送至 GitHub');
  var pushResult = exec('git push origin main');
  if (pushResult.error) {
    console.error('❌ 推送失败:', pushResult.error);
    writeStatus({
      deploy_status: 'push_failed',
      deploy_error: pushResult.error,
      commit: commitHash,
    });
    process.exit(1);
  }
  console.log('✅ 推送成功\n');

  // ---- 步骤4: 部署轮询 + 重试 ----
  console.log('▶ 步骤3: 等待 GitHub Pages 部署...');

  var deployed = false;
  var lastError = '';

  for (var attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (attempt > 0) {
      console.log('\n⏳ 第 ' + attempt + ' 次重试部署（等待 ' + (RETRY_INTERVAL_MS/1000) + ' 秒）...');
      // 重新推送触发部署
      var retryPush = exec('git push origin main');
      if (retryPush.error) {
        console.error('  ⚠️ 重试推送失败:', retryPush.error);
        lastError = retryPush.error;
      }
    }

    // 等待部署
    var waitTime = attempt === 0 ? 60000 : RETRY_INTERVAL_MS;
    console.log('  等待 ' + (waitTime/1000) + ' 秒后验收...');
    await sleep(waitTime);

    // ---- 步骤5: 远程验收 ----
    console.log('  验收中...');
    var verifyUrl = DEPLOY_URL + '?v=' + commitHash;
    try {
      var resp = await fetchUrl(verifyUrl);
      var body = resp.body || '';
      var statusCode = resp.status;

      // 检查1: 页面可访问
      if (statusCode !== 200) {
        lastError = 'HTTP ' + statusCode;
        console.log('  ⚠️ HTTP状态码: ' + statusCode + '（期望 200）');
        continue;
      }

      // 检查2: HTML 包含内容版本
      var hasVersion = contentVer && body.indexOf(contentVer) >= 0;
      if (!hasVersion) {
        lastError = '内容版本 ' + contentVer + ' 未在远程页面中找到';
        console.log('  ⚠️ 未找到内容版本 ' + contentVer);
        continue;
      }

      // 检查3: 核心数据不为空（检查几个关键数组标记）
      var hasDomestic = body.indexOf('mockHotNewsDomestic') >= 0;
      var hasTracking = body.indexOf('mockTrackingEvents') >= 0;
      var hasStock = body.indexOf('mockStockIndices') >= 0;

      if (!hasDomestic || !hasTracking || !hasStock) {
        var missing = [];
        if (!hasDomestic) missing.push('mockHotNewsDomestic');
        if (!hasTracking) missing.push('mockTrackingEvents');
        if (!hasStock) missing.push('mockStockIndices');
        lastError = '远程页面缺少核心数据: ' + missing.join(', ');
        console.log('  ⚠️ ' + lastError);
        continue;
      }

      // 全部通过
      deployed = true;
      console.log('✅ 远程验收通过');
      console.log('  - HTTP 200 ✓');
      console.log('  - 内容版本 ' + contentVer + ' ✓');
      console.log('  - 核心数据完整 ✓');

      writeStatus({
        deploy_status: 'success',
        deploy_commit: commitHash,
        deploy_content_version: contentVer,
        deploy_url: DEPLOY_URL,
        deploy_verified_at: cnNow(),
        pushed_to_github: true,
      });

      console.log('\n=== 部署成功 ===');
      console.log('远程地址: ' + DEPLOY_URL);
      process.exit(0);
      return;

    } catch(e) {
      lastError = e.message;
      console.log('  ⚠️ 请求失败: ' + e.message);
    }
  }

  // ---- 部署失败 ----
  console.error('\n❌ 部署验收失败（已重试 ' + MAX_RETRIES + ' 次）');
  console.error('最后错误: ' + lastError);

  writeStatus({
    deploy_status: 'failed',
    deploy_error: lastError,
    deploy_commit: commitHash,
    deploy_content_version: contentVer,
    pushed_to_github: true,
  });

  console.error('\n⚠️ 代码已推送到仓库，但远程页面验收未通过。');
  console.error('请手动检查: ' + DEPLOY_URL);
  process.exit(1);
}

main().catch(function(e) {
  console.error('脚本异常:', e);
  writeStatus({ deploy_status: 'error', deploy_error: e.message });
  process.exit(1);
});
