/**
 * extract_news.js v4 - 从新统一源文件提取新闻，输出到 news_data.json
 *
 * v4 重构 (2026-06-29):
 *   - **源文件切换**：单一源文件 /Users/bainian/WorkBuddy/2026-06-28-16-31-12/outputs/news-daily-mrjb.html
 *     替代了旧的 source_domestic.html + source_international.html
 *   - **新 HTML 结构**：<section class="news-section" id="section-XXX">
 *     → <div class="news-card"> → h3.card-title a[title] + p.card-summary + span.source-chip + span.card-time
 *   - **时间过滤**：利用 card-time 的精确时间戳（"2026-06-29 16:42:09"）做 48 小时过滤
 *   - **摘要清理**：去除截断标记、元数据前缀
 *   - **足球和 AI 牛股**：通过关键词从各版块提取
 */

const fs = require('fs');
const path = require('path');
const cheerio = require('/Users/bainian/.workbuddy/binaries/node/workspace/node_modules/cheerio');

const REPO_DIR = __dirname;

// ============================================================
// 新源文件路径
// ============================================================
const SOURCE_FILE = '/Users/bainian/WorkBuddy/2026-06-28-16-31-12/outputs/news-daily-mrjb.html';

// ============================================================
// 已知旧事件黑名单（保持 v3 的列表）
// ============================================================
const KNOWN_OLD_EVENTS = [
  { pattern: '加快建设全国统一大市场.*审议通过', desc: '2022年4月旧闻' },
  { pattern: '全面深化改革委员会.*全国统一大市场', desc: '2022年4月旧闻' },
  { pattern: '民营经济促进法.*审议|审议.*民营经济促进法', desc: '民营经济促进法已于2025年4月通过，不再审议' },
  { pattern: '全国人大常委会第十次会议.*民营经济', desc: '人大常委会第十次会议在2024年，民营经济法已通过' },
  { pattern: '人大常委会.*6月29日.*民营经济', desc: '人大常委会第23次会议已于6月26日闭幕' },
  { pattern: '长安十二时辰2.*杨幂|杨幂.*长安十二时辰2', desc: '假新闻：长安十二时辰2真实主演为杨紫/张晚意，非杨幂/雷佳音' },
  { pattern: '长安十二时辰.*收视率破3', desc: '假新闻：长安十二时辰2实际定档4月10日，非近期开播' },
  { pattern: '卡多索.*加盟.*签约', desc: '卡多索2025年2月租借加盟（冬窗），非夏窗转会' },
  { pattern: '萨尔科.*河南.*主帅', desc: '萨尔科2024年已离开河南队，2025年6月起执教苏州东吴' },
  { pattern: '萨尔科.*河内.*状态', desc: '萨尔科已非河南队主帅' },
  { pattern: 'GPT-4\\.0|GPT-4o', desc: 'GPT-4o已发布多时' },
];

// ============================================================
// 时效过滤
// ============================================================
function isOldNews(title, summary, cardTime) {
  const text = title + ' ' + (summary || '');

  // === 第1层：已知旧事件黑名单 ===
  for (const event of KNOWN_OLD_EVENTS) {
    if (new RegExp(event.pattern).test(text)) {
      return true;
    }
  }

  // === 第2层：card-time 精确过滤（>72小时） ===
  if (cardTime) {
    const match = cardTime.match(/(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
    if (match) {
      const cardDate = new Date(
        parseInt(match[1]), parseInt(match[2]) - 1, parseInt(match[3]),
        parseInt(match[4]), parseInt(match[5])
      );
      const now = new Date();
      const hoursDiff = (now - cardDate) / (1000 * 60 * 60);
      if (hoursDiff > 72) return true;
      // 如果 card-time 验证通过（≤72h），信任时间戳，跳过文本日期检测
      return false;
    }
  }

  // === 第3层：如果无 card-time，回退到文本日期检测（>72小时） ===
  const dateMatches = text.match(/(\d+)月(\d+)日/g);
  if (dateMatches) {
    const now = new Date();
    const today = now.getDate();
    const thisMonth = now.getMonth() + 1;
    
    for (const dm of dateMatches) {
      const parts = dm.match(/(\d+)月(\d+)日/);
      const m = parseInt(parts[1]);
      const d = parseInt(parts[2]);
      
      // 计算日期差（简化：假设同月）
      if (m === thisMonth) {
        const dayDiff = today - d;
        if (dayDiff > 3) return true;  // 超过3天
      } else if (m < thisMonth) {
        return true;  // 上个月及之前
      }
    }
  }

  // 旧年份
  if (/\b202[0-5]年\b/.test(text)) return true;

  // 模糊旧时间词
  if (/去年|前年|数年前|几个月前/.test(text)) return true;

  return false;
}

// ============================================================
// 时间格式转换：2026-06-29 16:42:09 → 6月29日 16:42
// ============================================================
function formatTime(cardTime) {
  if (!cardTime) return '';
  const match = cardTime.match(/(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
  if (!match) return cardTime;
  const month = parseInt(match[2]);
  const day = parseInt(match[3]);
  const hour = parseInt(match[4]);
  const minute = parseInt(match[5]);
  return `${month}月${day}日 ${hour}:${String(minute).padStart(2,'0')}`;
}

// ============================================================
// 摘要清理
// ============================================================
function cleanSummary(summary) {
  if (!summary) return '';

  // 去除 "本条新闻核心要点：" 等元数据前缀
  summary = summary.replace(/^本条新闻核心要点[：:]\s*/g, '');
  summary = summary.replace(/^核心要点[：:]\s*/g, '');

  // 去除末尾的 "..."
  summary = summary.replace(/\.{2,}$/g, '');

  // 去除末尾不完整的半句话（以 "..." 后跟无意义文本）
  summary = summary.replace(/[。！？\.!\?]\s*\.{2,}$/g, '。');

  // 过长截断
  if (summary.length > 200) {
    summary = summary.substring(0, 180) + '...';
  }

  return summary.trim();
}

// ============================================================
// 垃圾标题过滤
// ============================================================
const GARBAGE_PATTERNS = ['动态更新', ' placeholder', 'TODO', 'test'];

function isGarbage(title) {
  if (!title || title.length < 8) return true;
  for (const pattern of GARBAGE_PATTERNS) {
    if (title.includes(pattern)) return true;
  }
  return false;
}

// ============================================================
// 解析新源文件 (section-based 结构，cheerio 友好)
// ============================================================
function parseNewsDailyFile(html) {
  const $ = cheerio.load(html);
  const sections = {};

  $('section.news-section').each((i, elem) => {
    const $section = $(elem);
    const sectionId = $section.attr('id') || '';
    if (!sectionId.startsWith('section-')) return;

    const newsItems = [];

    $section.find('.news-card').each((j, card) => {
      const $card = $(card);

      // 标题：h3.card-title > a[title]
      const $link = $card.find('h3.card-title a').first();
      const title = ($link.attr('title') || $link.text() || '').trim();
      if (!title || isGarbage(title)) return;

      const url = $link.attr('href') || '';

      // 摘要：p.card-summary
      let summary = cleanSummary($card.find('p.card-summary').first().text().trim());

      // 来源：span.source-chip
      const source = $card.find('span.source-chip').first().text().trim();

      // 时间：span.card-time
      const cardTime = $card.find('span.card-time').first().text().trim();

      // 时效检查
      if (isOldNews(title, summary, cardTime)) return;

      // 摘要检查：无摘要的新闻直接跳过
      if (!summary || summary.length < 5) return;

      // 热度：基于时间新鲜度
      let heat = 5;
      if (cardTime) {
        const match = cardTime.match(/(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
        if (match) {
          const cardDate = new Date(
            parseInt(match[1]), parseInt(match[2]) - 1, parseInt(match[3]),
            parseInt(match[4]), parseInt(match[5])
          );
          const hoursAgo = (new Date() - cardDate) / (1000 * 60 * 60);
          if (hoursAgo < 3) heat = 9;
          else if (hoursAgo < 6) heat = 8;
          else if (hoursAgo < 12) heat = 7;
          else if (hoursAgo < 24) heat = 6;
          else heat = 5;
        }
      }

      newsItems.push({
        title: title,
        summary: summary,
        source: source,
        url: url,
        time: formatTime(cardTime),
        heat: heat
      });
    });

    if (newsItems.length > 0) {
      sections[sectionId] = newsItems;
    }
  });

  return sections;
}

// ============================================================
// 获取所有新闻（跨版块合并）
// ============================================================
function getAllNews(sections) {
  const all = [];
  for (const [key, items] of Object.entries(sections)) {
    for (const item of items) {
      all.push({ ...item, _section: key });
    }
  }
  return all;
}

// ============================================================
// 去重：基于标题前30字符比对
// ============================================================
function deduplicate(items) {
  const seen = new Set();
  const result = [];
  for (const item of items) {
    const normalizedTitle = item.title.replace(/\s+/g, '').substring(0, 30);
    if (!seen.has(normalizedTitle)) {
      seen.add(normalizedTitle);
      result.push(item);
    }
  }
  return result;
}

// ============================================================
// 拆分主数组和 Extra 数组
// ============================================================
function splitMainAndExtra(items, mainCount = 20, extraMax = 40) {
  const main = items.slice(0, mainCount);
  const extra = items.slice(mainCount, mainCount + extraMax);
  return { main, extra };
}

// ============================================================
// 足球新闻关键词过滤
// ============================================================
// 河南足球关键词 — 必须严格匹配，避免误匹配（如"布拉莫斯"匹配"拉莫斯"）
const HENAN_KEYWORDS = ['河南队', '河南足球', '航海体育场', '彩陶坊', '河南建业'];
const HENAN_BROAD_KEYWORDS = ['河南']; // 仅在摘要中有足球上下文时使用

// 足球通用关键词 — 仅保留明确指足球的术语，避免歧义误匹配
// "世预赛" 在篮球中也使用，"球场"可指网球场，"中超"可能出现在非足球文本中
const FOOTBALL_KEYWORDS = [
  '中超联赛', '中甲联赛',
  '国足', '亚洲杯', '亚冠联赛',
  '英超联赛', '西甲联赛', '意甲联赛', '德甲联赛', '法甲联赛', '欧冠联赛', '欧联杯',
  '足球', '世界杯', '欧洲杯', '美洲杯',
  '球衣', '球票',
  '转会费', '租借加盟',
];

// 宽泛关键词 — 需要足球上下文验证
const FOOTBALL_BROAD_KEYWORDS = [
  '中超', '中甲', '亚冠', '世预赛',
  '英超', '西甲', '意甲', '德甲', '法甲', '欧冠', '欧联',
  '球场',
];

const FOOTBALL_CONTEXT_SIGNALS = ['足球', '球员', '球队', '俱乐部', '教练', '射手', '门将', '后卫', '前锋', '中场', '裁判', '罚球', '点球', '角球', '帽子戏法', '梅开二度', '乌龙球', '替补', '首发', '拉莫斯', '梅西', 'C罗', '姆巴佩', '哈兰德', '内马尔'];

function isHenanNews(title, summary) {
  const text = title + ' ' + (summary || '');
  // 精确匹配
  if (HENAN_KEYWORDS.some(kw => text.includes(kw))) return true;
  // 宽泛匹配"河南"需有足球上下文
  if (text.includes('河南')) {
    if (FOOTBALL_CONTEXT_SIGNALS.some(s => text.includes(s))) return true;
  }
  return false;
}

function isFootballNews(title, summary) {
  const text = title + ' ' + (summary || '');
  // 精确足球关键词（完整联赛名称）
  if (FOOTBALL_KEYWORDS.some(kw => text.includes(kw))) return true;
  // 宽泛关键词需有足球上下文
  const broadMatch = FOOTBALL_BROAD_KEYWORDS.find(kw => text.includes(kw));
  if (broadMatch) {
    if (FOOTBALL_CONTEXT_SIGNALS.some(s => text.includes(s))) return true;
  }
  return false;
}

// AI牛股关键词
const AI_STOCK_KEYWORDS = [
  '牛股', '涨停', '选股', '金股', '荐股', '风口', '龙头',
  '暴涨', '翻倍', '抄底', '主升浪', '涨停板',
];

function isAIStockNews(title) {
  const t = title;
  return AI_STOCK_KEYWORDS.some(kw => t.includes(kw));
}

// ============================================================
// 版块映射
// ============================================================
const SECTION_MAP = {
  'section-国内新闻': 'domestic',
  'section-国际新闻': 'international',
  'section-财经新闻': 'finance',
  'section-娱乐新闻': 'entertainment',
  'section-AI科技新闻': 'ai_tech',
};

// ============================================================
// 主函数
// ============================================================
function main() {
  console.log('=== 新闻提取脚本 v4 启动 ===');
  console.log(`源文件: ${SOURCE_FILE}`);

  if (!fs.existsSync(SOURCE_FILE)) {
    console.error(`ERROR: 源文件不存在! ${SOURCE_FILE}`);
    console.log('提示：AI日报自动化会在每日 5:00 和 17:00 生成此文件');
    process.exit(1);
  }

  const html = fs.readFileSync(SOURCE_FILE, 'utf-8');
  console.log(`源文件大小: ${(html.length / 1024).toFixed(1)} KB`);

  console.log('解析新闻日报文件...');
  const sections = parseNewsDailyFile(html);
  const allNews = getAllNews(sections);

  // 统计各版块
  for (const [key, items] of Object.entries(sections)) {
    console.log(`  [${key}] ${items.length} 条`);
  }
  console.log(`  总计: ${allNews.length} 条`);

  // ============================================================
  // 映射到输出数组
  // ============================================================

  const getSection = (secId) => deduplicate(sections[secId] || []);

  // 1. 国内新闻 — 全部抓取（不再限制数量）
  const domesticNews = getSection('section-国内新闻');
  const domSplit = splitMainAndExtra(domesticNews, 500, 500);
  const mockHotNewsDomestic = domSplit.main;
  const mockHotNewsDomesticExtra = domSplit.extra;

  // 2. 国际新闻 — 全部抓取
  const intlNews = getSection('section-国际新闻');
  const intlSplit = splitMainAndExtra(intlNews, 500, 500);
  const mockHotNewsInternational = intlSplit.main;
  const mockHotNewsInternationalExtra = intlSplit.extra;

  // 3. AI科技 — 全部抓取
  const aiNews = getSection('section-AI科技新闻');
  const aiSplit = splitMainAndExtra(aiNews, 500, 500);
  const mockHotNewsAI = aiSplit.main;
  const mockHotNewsAIExtra = aiSplit.extra;

  // 4. 娱乐 — 全部抓取
  const entNews = getSection('section-娱乐新闻');
  const entSplit = splitMainAndExtra(entNews, 500, 500);
  const mockEntertainment = entSplit.main;
  const mockEntertainmentExtra = entSplit.extra;

  // 5. 财经 — 全部抓取
  const finNews = getSection('section-财经新闻');
  const finSplit = splitMainAndExtra(finNews, 500, 500);
  const mockStockNews = finSplit.main;
  const mockStockNewsExtra = finSplit.extra;

  // 6. 河南足球 — 直接从 section-河南足球俱乐部 提取（新源文件已有专版）
  const henanNews = getSection('section-河南足球俱乐部');
  const henanSplit = splitMainAndExtra(henanNews, 30, 100);
  const mockHenanNews = henanSplit.main;

  // 7. 中超其他球队 — 直接从 section-中超联赛动态 提取（新源文件已有专版）
  const cslNews = getSection('section-中超联赛动态');
  const cslSplit = splitMainAndExtra(cslNews, 30, 100);
  const mockCslOtherTeams = cslSplit.main;

  // 8. AI牛股推荐 — 从财经和AI版块提取（关键词筛选）
  const aiStockPool = deduplicate(
    allNews.filter(item =>
      (item._section === 'section-财经新闻' || item._section === 'section-AI科技新闻') &&
      isAIStockNews(item.title)
    )
  );
  const mockStockAI = aiStockPool.slice(0, 30);

  // 汇总
  const result = {
    mockHotNewsDomestic,
    mockHotNewsDomesticExtra,
    mockHotNewsInternational,
    mockHotNewsInternationalExtra,
    mockHotNewsAI,
    mockHotNewsAIExtra,
    mockEntertainment,
    mockEntertainmentExtra,
    mockHenanNews,
    mockCslOtherTeams,
    mockStockNews,
    mockStockNewsExtra,
    mockStockAI,
  };

  // 输出统计
  console.log('\n=== 提取结果 ===');
  let total = 0;
  for (const [key, items] of Object.entries(result)) {
    console.log(`  ${key}: ${items.length} 条`);
    total += items.length;
  }
  console.log(`  总计: ${total} 条`);

  // 特别提示
  if (mockHenanNews.length < 5) {
    console.warn('\n⚠️  河南足球新闻不足5条！新源文件不含足球专版，可能需单独补充。');
  }
  if (mockStockAI.length < 5) {
    console.warn('⚠️  AI牛股推荐不足5条！新源文件不含荐股版块。');
  }

  const output = {
    extracted_at: new Date().toISOString(),
    source_file: SOURCE_FILE,
    total_items: total,
    sections: result
  };

  const outputPath = path.join(REPO_DIR, 'news_data.json');
  fs.writeFileSync(outputPath, JSON.stringify(output, null, 2), 'utf-8');
  console.log(`\n已输出到: ${outputPath}`);

  return output;
}

main();
