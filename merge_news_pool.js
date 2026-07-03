/**
 * merge_news_pool.js — 滚动新闻池合并脚本
 *
 * 将 extract_news.js 输出的 news_data.json 合并进 news_pool.json，
 * 去重、评分、淘汰、容量控制，输出合并后的数据给 apply_news.js。
 *
 * 用法: node merge_news_pool.js
 */

const fs = require('fs');
const path = require('path');

const REPO_DIR = __dirname;
const POOL_FILE = path.join(REPO_DIR, 'news_pool.json');
const NEWS_JSON = path.join(REPO_DIR, 'news_data.json');
const STATUS_FILE = path.join(REPO_DIR, 'workbuddy_news_update_status.json');
const HISTORY_FILE = path.join(REPO_DIR, 'workbuddy_news_update_history.jsonl');

// ============================================================
// 配置
// ============================================================
const CAPACITY = {
  domestic: 200,
  international: 200,
  ai: 200,
  entertainment: 200,
  stock: 200,
  henan: 50,
  csl: 50,
};

// 48小时毫秒数
const RETENTION_WINDOW_MS = 48 * 60 * 60 * 1000;

// 权威来源白名单
const AUTHORITY_SOURCES = [
  '新华社', '人民日报', '央视新闻', '新华网', '人民网', '央视网',
  '中国新闻网', '环球网', '光明网', '经济日报', '中国青年报',
  '解放军报', '央广网', '国际在线', '中国日报', '参考消息',
  '中国政府网', '外交部', '国防部发布',
];

// 低质量关键词（标题包含则降权）
const LOW_QUALITY_KEYWORDS = [
  '震惊', '出人意料', '难以置信', '紧急通知', '速看', '删前速看',
  '千万别', '一定要看', '深度好文', '价值千万', '赚翻了',
];

// 池 section → mock 数组映射
const SECTION_MAP = {
  domestic:  { main: 'mockHotNewsDomestic',      extra: 'mockHotNewsDomesticExtra',      mainN: 30, extraN: 170 },
  international: { main: 'mockHotNewsInternational',  extra: 'mockHotNewsInternationalExtra',  mainN: 30, extraN: 170 },
  ai:          { main: 'mockHotNewsAI',            extra: 'mockHotNewsAIExtra',            mainN: 30, extraN: 170 },
  entertainment: { main: 'mockEntertainment',         extra: 'mockEntertainmentExtra',         mainN: 30, extraN: 170 },
  stock:       { main: 'mockStockNews',            extra: 'mockStockNewsExtra',            mainN: 30, extraN: 170 },
  henan:       { main: 'mockHenanNews',            extra: null,                            mainN: 50, extraN: 0 },
  csl:         { main: 'mockCslOtherTeams',        extra: null,                            mainN: 50, extraN: 0 },
};

// extract_news.js 的 mock 数组 → 池 section 反向映射
const MOCK_TO_SECTION = {
  mockHotNewsDomestic: 'domestic',
  mockHotNewsDomesticExtra: 'domestic',
  mockHotNewsInternational: 'international',
  mockHotNewsInternationalExtra: 'international',
  mockHotNewsAI: 'ai',
  mockHotNewsAIExtra: 'ai',
  mockEntertainment: 'entertainment',
  mockEntertainmentExtra: 'entertainment',
  mockStockNews: 'stock',
  mockStockNewsExtra: 'stock',
  mockHenanNews: 'henan',
  mockCslOtherTeams: 'csl',
};

// ============================================================
// 工具函数
// ============================================================

function now() { return new Date().toISOString(); }

function cnNow() {
  var d = new Date();
  return d.getFullYear() + '-' +
    String(d.getMonth()+1).padStart(2,'0') + '-' +
    String(d.getDate()).padStart(2,'0') + ' ' +
    String(d.getHours()).padStart(2,'0') + ':' +
    String(d.getMinutes()).padStart(2,'0');
}

// 获取新闻的时间戳（优先 publishedAt，其次 collected_at，其次 time，其次标题含日期）
function getNewsTime(item) {
  if (item.publishedAt) return new Date(item.publishedAt).getTime();
  if (item.collectedAt) return new Date(item.collectedAt).getTime();
  if (item.time) {
    // time 格式: "7月3日 12:37" — 尝试解析
    var m = item.time.match(/(\d+)月(\d+)日\s+(\d+):(\d+)/);
    if (m) {
      var year = new Date().getFullYear();
      return new Date(year, parseInt(m[1])-1, parseInt(m[2]), parseInt(m[3]), parseInt(m[4])).getTime();
    }
    // 尝试 ISO 格式: "2026-07-03 12:37"
    m = item.time.match(/(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})/);
    if (m) return new Date(m[1]).getTime();
  }
  return Date.now();
}

// 标准化标题用于去重
function normalizeTitle(title) {
  return (title || '').replace(/\s+/g, '').replace(/[「」『』【】《》，。！？、：；""''（）\[\]——\-—\uD800-\uDFFF]/g, '').substring(0, 30);
}

// 标题相似度（基于公共子串比例）
function titleSimilarity(t1, t2) {
  var a = (t1 || '').replace(/\s+/g, '');
  var b = (t2 || '').replace(/\s+/g, '');
  if (!a || !b) return 0;
  // 短字符串取编辑距离
  var len = Math.max(a.length, b.length);
  if (len < 10) return a === b ? 1 : 0;
  // 长字符串取前缀匹配 + 公共字符比例
  var prefixLen = 0;
  for (var i = 0; i < Math.min(a.length, b.length, 20); i++) {
    if (a[i] === b[i]) prefixLen++;
    else break;
  }
  // 公共字符集合
  var setA = {}, setB = {};
  for (var c of a) setA[c] = (setA[c] || 0) + 1;
  for (var c of b) setB[c] = (setB[c] || 0) + 1;
  var common = 0, total = 0;
  var allKeys = new Set(Object.keys(setA).concat(Object.keys(setB)));
  for (var c of allKeys) {
    common += Math.min(setA[c] || 0, setB[c] || 0);
    total += Math.max(setA[c] || 0, setB[c] || 0);
  }
  var charRatio = total > 0 ? common / total : 0;
  return Math.max(prefixLen / 20, charRatio);
}

// 来源权威分 (0-20)
function getSourceScore(source) {
  if (!source) return 0;
  for (var i = 0; i < AUTHORITY_SOURCES.length; i++) {
    if (source.indexOf(AUTHORITY_SOURCES[i]) >= 0) return 20;
  }
  return 5;
}

// 低质量检测
function isLowQuality(title) {
  if (!title) return true;
  for (var i = 0; i < LOW_QUALITY_KEYWORDS.length; i++) {
    if (title.indexOf(LOW_QUALITY_KEYWORDS[i]) >= 0) return true;
  }
  return false;
}

// 新闻综合评分 (0-100)
function scoreItem(item) {
  var score = 40; // 基础分

  // 新鲜度 (0-30)
  var age = Date.now() - getNewsTime(item);
  var hoursOld = age / (1000 * 60 * 60);
  if (hoursOld < 6) score += 30;
  else if (hoursOld < 12) score += 25;
  else if (hoursOld < 24) score += 20;
  else if (hoursOld < 48) score += 10;
  else if (hoursOld < 72) score += 5;
  // >72h 不加分

  // 摘要完整性 (0-15)
  var sl = (item.summary || '').length;
  if (sl >= 80) score += 15;
  else if (sl >= 50) score += 10;
  else if (sl >= 20) score += 5;

  // 来源权威 (0-20)
  score += getSourceScore(item.source);

  // heat (0-15)
  score += Math.min(15, (item.heat || 5) * 1.5);

  // 低质量惩罚 (-100)
  if (isLowQuality(item.title)) score -= 100;

  return Math.max(0, score);
}

// ============================================================
// 去重：从合并数组中移除重复项
// ============================================================
function deduplicate(items) {
  var seenUrl = {};
  var seenTitle = {};
  var result = [];

  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    var url = (item.url || '').trim();
    var normTitle = normalizeTitle(item.title);

    // 精确 URL 去重
    if (url) {
      if (seenUrl[url]) {
        // 保留分数更高的
        var existing = seenUrl[url];
        if (scoreItem(item) > scoreItem(existing)) {
          // 替换
          var idx = result.indexOf(existing);
          if (idx >= 0) result[idx] = item;
          seenUrl[url] = item;
        }
        continue;
      }
      seenUrl[url] = item;
    }

    // 标题去重（前30字符）
    if (normTitle) {
      var similar = false;
      for (var existingTitle in seenTitle) {
        if (titleSimilarity(normTitle, existingTitle) > 0.65) {
          similar = true;
          var existing = seenTitle[existingTitle];
          if (scoreItem(item) > scoreItem(existing)) {
            var idx = result.indexOf(existing);
            if (idx >= 0) result[idx] = item;
            seenTitle[existingTitle] = item;
          }
          break;
        }
      }
      if (similar) continue;
      seenTitle[normTitle] = item;
    }

    result.push(item);
  }

  return result;
}

// ============================================================
// 将 fresh item 转为 pool item 格式
// ============================================================
function toPoolItem(fresh, section) {
  return {
    section: section,
    title: fresh.title || '',
    source: fresh.source || '',
    summary: fresh.summary || '',
    url: fresh.url || '',
    heat: fresh.heat || 5,
    publishedAt: fresh.time || '',
    time: fresh.time || '',
    collectedAt: now(),
  };
}

// ============================================================
// 将 pool item 转为 mock 数组格式（用于 apply_news.js）
// ============================================================
function toMockItem(poolItem) {
  return {
    rank: 0, // apply_news.js 会自动设置 rank
    title: poolItem.title || '',
    source: poolItem.source || '',
    summary: poolItem.summary || '',
    url: poolItem.url || '',
    heat: poolItem.heat || 5,
    time: poolItem.time || poolItem.publishedAt || '',
  };
}

// ============================================================
// 主流程
// ============================================================
function main() {
  console.log('=== merge_news_pool.js 启动 ===\n');

  // 1. 读取现有池
  var pool = {};
  try {
    pool = JSON.parse(fs.readFileSync(POOL_FILE, 'utf-8'));
    console.log('读取现有新闻池:');
    for (var k in pool) console.log('  ' + k + ': ' + pool[k].length + ' 条');
  } catch(e) {
    console.log('news_pool.json 不存在或无效，创建新池');
    for (var k in CAPACITY) pool[k] = [];
  }

  // 2. 读取新提取数据
  if (!fs.existsSync(NEWS_JSON)) {
    console.error('ERROR: news_data.json 不存在，请先运行 extract_news.js');
    process.exit(1);
  }
  var freshData = JSON.parse(fs.readFileSync(NEWS_JSON, 'utf-8'));
  var freshSections = freshData.sections || {};
  console.log('\n本次提取:');
  var freshTotal = 0;
  for (var k in freshSections) {
    console.log('  ' + k + ': ' + freshSections[k].length + ' 条');
    freshTotal += freshSections[k].length;
  }
  console.log('  总计: ' + freshTotal + ' 条');

  // 3. 逐版块合并
  var stats = {
    extracted_at: freshData.extracted_at || now(),
    updated_at: cnNow(),
    pulled: freshTotal,
    added: 0,
    deduped: 0,
    trimmed: 0,
    final: {},
    pushed_to_github: false,
    status: 'success',
    target: 'index.html',
  };

  var mergedSections = {};
  var totalFinal = 0;

  for (var sectionKey in SECTION_MAP) {
    var mockMain = SECTION_MAP[sectionKey].main;
    var freshItems = freshSections[mockMain] || [];
    var freshExtraItems = SECTION_MAP[sectionKey].extra ? (freshSections[SECTION_MAP[sectionKey].extra] || []) : [];

    // 合并 fresh 主 + extra
    var allFresh = freshItems.concat(freshExtraItems);

    // 已有池数据
    var existingPool = pool[sectionKey] || [];

    var beforeCount = existingPool.length;
    var freshCount = allFresh.length;

    // 将 fresh 转为 pool 格式
    var newPoolItems = allFresh.map(function(item) { return toPoolItem(item, sectionKey); });

    // 合并
    var combined = existingPool.concat(newPoolItems);
    var afterMerge = combined.length;

    // 去重
    var deduped = deduplicate(combined);
    var dedupCount = afterMerge - deduped.length;

    // 评分排序
    deduped.sort(function(a, b) { return scoreItem(b) - scoreItem(a); });

    // 容量控制
    var capacity = CAPACITY[sectionKey] || 200;
    var trimmed = deduped.slice(0, capacity);
    var trimCount = deduped.length - trimmed.length;

    // 写回池
    pool[sectionKey] = trimmed;

    // 统计
    var addedCount = freshCount; // 近似值（实际会扣除去重）
    stats.added += Math.max(0, trimmed.length - beforeCount);
    stats.deduped += dedupCount;
    stats.trimmed += trimCount;
    stats.final[sectionKey] = trimmed.length;
    totalFinal += trimmed.length;

    console.log('\n--- ' + sectionKey + ' ---');
    console.log('  池中原有: ' + beforeCount + ' 条');
    console.log('  本次新增: ' + freshCount + ' 条');
    console.log('  合并后: ' + afterMerge + ' 条');
    console.log('  去重: ' + dedupCount + ' 条');
    console.log('  淘汰: ' + trimCount + ' 条');
    console.log('  最终: ' + trimmed.length + ' 条');

    // 转换为 mock 格式
    var map = SECTION_MAP[sectionKey];
    var mainCount = map.mainN;
    var poolItems = trimmed;

    var mainArr = poolItems.slice(0, mainCount).map(function(item, idx) {
      var mock = toMockItem(item);
      mock.rank = idx + 1;
      return mock;
    });

    var extraArr = [];
    if (map.extra) {
      extraArr = poolItems.slice(mainCount).map(function(item, idx) {
        var mock = toMockItem(item);
        mock.rank = mainCount + idx + 1;
        return mock;
      });
    }

    mergedSections[map.main] = mainArr;
    if (map.extra) mergedSections[map.extra] = extraArr;
  }

  // 4. 写回 news_pool.json
  fs.writeFileSync(POOL_FILE, JSON.stringify(pool, null, 2), 'utf-8');
  console.log('\n✅ news_pool.json 已更新');

  // 5. 写 news_data.json（供 apply_news.js 使用）
  var output = {
    extracted_at: now(),
    source_file: freshData.source_file || '',
    total_items: totalFinal,
    sections: mergedSections,
  };
  fs.writeFileSync(NEWS_JSON, JSON.stringify(output, null, 2), 'utf-8');
  console.log('✅ news_data.json 已更新（含合并后数据）');

  // 6. 写状态文件
  var statusContent = {
    updated_at: cnNow(),
    status: 'success',
    pulled: stats.pulled,
    added_net: stats.added,
    deduped: stats.deduped,
    trimmed: stats.trimmed,
    sections: stats.final,
    total_final: totalFinal,
    pushed_to_github: false,
    target: 'index.html',
    notes: '滚动合并到本地新闻池，等待 Codex 审核排序',
  };
  fs.writeFileSync(STATUS_FILE, JSON.stringify(statusContent, null, 2), 'utf-8');

  // 7. 追加历史记录
  var historyLine = JSON.stringify(Object.assign({
    run_id: now().replace(/[:.]/g, '-'),
    status: 'success',
  }, statusContent));
  try {
    var existingHistory = fs.readFileSync(HISTORY_FILE, 'utf-8').trim();
    fs.writeFileSync(HISTORY_FILE, existingHistory + '\n' + historyLine + '\n', 'utf-8');
  } catch(e) {
    fs.writeFileSync(HISTORY_FILE, historyLine + '\n', 'utf-8');
  }

  console.log('✅ workbuddy_news_update_status.json 已更新');
  console.log('\n=== 合并完成 ===');
  console.log('共 ' + totalFinal + ' 条新闻保留在池中');
  console.log('等待 Codex 审核排序后推送远程');
}

main();
