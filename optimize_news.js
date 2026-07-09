/**
 * optimize_news.js — 优化新闻标题和摘要
 *
 * 仅优化未在 news_pool.json 中出现过的新新闻。
 * 优化策略：
 *   标题：移除冗余标点（【】「」等）、精简 ETF 后缀、移除多余空格
 *   摘要：截断过长摘要（>120字截断至120字+…）、移除尾部残缺句、移除多余空格
 *
 * 用法: node optimize_news.js
 */

const fs = require('fs');
const path = require('path');

const REPO_DIR = __dirname;
const NEWS_JSON = path.join(REPO_DIR, 'news_data.json');
const POOL_FILE = path.join(REPO_DIR, 'news_pool.json');

function readJSON(fp) {
  try { return JSON.parse(fs.readFileSync(fp, 'utf-8')); } catch (e) { return null; }
}

function normalizeUrl(url) {
  return (url || '').replace(/[?#].*$/, '').replace(/\/+$/, '').trim();
}

// 构建现有池中所有 URL 的集合
function buildPoolUrlSet(pool) {
  var set = {};
  for (var key in pool) {
    var items = pool[key] || [];
    for (var i = 0; i < items.length; i++) {
      var url = normalizeUrl(items[i].url);
      if (url) set[url] = true;
      // 也按标准化标题记录
      var t = (items[i].title || '').replace(/\s+/g, '').substring(0, 30);
      if (t) set['__t:' + t] = true;
    }
  }
  return set;
}

function isNew(poolUrlSet, item) {
  var url = normalizeUrl(item.url);
  if (url && poolUrlSet[url]) return false;
  var t = (item.title || '').replace(/\s+/g, '').substring(0, 30);
  if (t && poolUrlSet['__t:' + t]) return false;
  return true;
}

// ============================================================
// 优化函数
// ============================================================

// 优化标题
function optimizeTitle(title) {
  if (!title) return title;
  var t = title;
  // 1. 移除冗余标点符号：开头或结尾的【】「」『』等
  t = t.replace(/^[「」『』【】〔〕《》\[\]\(\)""''「」]+/, '');
  t = t.replace(/[「」『』【】〔〕《》\[\]\(\)""''「」]+$/, '');
  // 2. 精简 ETF 标题：移除"ETF天弘""ETF华夏"等指向性不强的后缀
  t = t.replace(/ETF（[^）]+）/g, 'ETF');
  t = t.replace(/ETF\([^\)]+\)/g, 'ETF');
  // 3. 移除连续空格
  t = t.replace(/\s+/g, ' ').trim();
  // 4. 截断过长的标题（>50字）
  if (t.length > 50) t = t.substring(0, 47) + '...';
  return t;
}

// 优化摘要
function optimizeSummary(summary) {
  if (!summary) return summary;
  var s = summary;
  // 1. 移除冗余前缀
  s = s.replace(/^(北京报道|北京[^，]*电|北京[^，]*讯|中新社[^，]*电|新华社[^，]*电)\s*/g, '');
  s = s.replace(/^编者按[：:]\s*/g, '');
  s = s.replace(/^核心摘要\s*/g, '');
  // 2. 截断尾部残缺句（以「的」「了」「在」「为」「和」「与」「对」「从」结尾的截断）
  s = s.replace(/[，,][^，。!！?？]*[的在了为和与对从]$/, '');
  // 3. 移除多余空格
  s = s.replace(/\s+/g, ' ').trim();
  // 4. 截断过长摘要（>150字）
  if (s.length > 150) {
    // 尝试在 120-150 字间的句号处截断
    var cutPos = s.lastIndexOf('。', 145);
    if (cutPos > 120) s = s.substring(0, cutPos + 1);
    else s = s.substring(0, 147) + '...';
  }
  return s;
}

// ============================================================
// 主流程
// ============================================================

function main() {
  console.log('=== optimize_news.js 启动 ===\n');

  // 1. 读取 news_data.json
  var data = readJSON(NEWS_JSON);
  if (!data || !data.sections) {
    console.error('ERROR: news_data.json 不存在或格式无效');
    process.exit(1);
  }

  // 2. 读取现有池，构建 URL 集合
  var pool = readJSON(POOL_FILE) || {};
  var poolUrlSet = buildPoolUrlSet(pool);

  // 3. 遍历各版块
  var totalNew = 0;
  var totalOptimized = 0;

  for (var sectionKey in data.sections) {
    var items = data.sections[sectionKey] || [];
    var sectionNew = 0;
    var sectionOpt = 0;

    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var isNewItem = isNew(poolUrlSet, item);

      if (isNewItem) {
        sectionNew++;
        totalNew++;

        var origTitle = item.title;
        var origSummary = item.summary;
        var newTitle = optimizeTitle(origTitle);
        var newSummary = optimizeSummary(origSummary);

        if (newTitle !== origTitle || newSummary !== origSummary) {
          item.title = newTitle;
          item.summary = newSummary;
          sectionOpt++;
          totalOptimized++;
        }
      }
    }

    console.log('  ' + sectionKey + ': 新新闻 ' + sectionNew + ' 条, 优化 ' + sectionOpt + ' 条');
  }

  // 4. 写回
  fs.writeFileSync(NEWS_JSON, JSON.stringify(data, null, 2), 'utf-8');
  console.log('\n✅ 优化完成');
  console.log('  新新闻总计: ' + totalNew + ' 条');
  console.log('  实际优化: ' + totalOptimized + ' 条');
  console.log('  news_data.json 已更新');
}

main();
