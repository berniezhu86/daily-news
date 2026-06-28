/**
 * extract_news.js - 从两个源 HTML 文件提取所有新闻，输出到 news_data.json
 * 
 * v2: 修复以下问题:
 *   - 修复 source_domestic.html 中嵌套div导致标题串联的bug
 *   - 过滤"动态更新"等占位符垃圾数据
 *   - 分离河南足球和其他中超球队新闻
 *   - 限制Extra数组最大40条
 *   - 更严格的去重（标题前30字符比对）
 */

const fs = require('fs');
const path = require('path');
const cheerio = require('/Users/bainian/.workbuddy/binaries/node/workspace/node_modules/cheerio');

const REPO_DIR = __dirname;

// ============================================================
// 垃圾标题过滤：包含这些关键词的标题直接丢弃
// ============================================================
const GARBAGE_PATTERNS = [
  '动态更新',
  ' placeholder',
  'TODO',
  'test',
];

function isGarbage(title) {
  if (!title || title.length < 8) return true;
  for (const pattern of GARBAGE_PATTERNS) {
    if (title.includes(pattern)) return true;
  }
  return false;
}

// ============================================================
// 解析 source_domestic.html (div-based 结构)
// v2: 使用 a > strong 作为主选择器，避免嵌套div问题
// ============================================================
function parseDomesticFile(html) {
  const $ = cheerio.load(html);
  const sections = {};

  // 获取所有 section-block div
  $('div.section-block').each((i, elem) => {
    const $section = $(elem);
    const sectionId = $section.attr('id');
    if (!sectionId) return;

    const newsItems = [];
    
    // 用 a > strong 作为主选择器，每个 a 标签就是一条新闻
    $section.find('a').each((j, aElem) => {
      const $a = $(aElem);
      const $strong = $a.find('strong').first();
      
      // 只处理包含 strong 标签的 a 标签（即新闻标题链接）
      if ($strong.length === 0) return;
      
      const title = $strong.text().trim();
      if (!title || isGarbage(title)) return;
      
      const url = $a.attr('href') || '';
      
      // 来源：a 标签后面的 span
      const $parent = $a.parent();
      const sourceText = $parent.find('span[style*="color:#888"]').text();
      const sourceMatch = sourceText.match(/\[(.+?)\]/);
      const source = sourceMatch ? sourceMatch[1] : '';
      
      // 摘要：同一层级的 color:#6e6e73 div
      // 向上找到最近的容器，然后查找摘要
      let summary = '';
      let $container = $a.closest('div[style*="background:#fff"]');
      if ($container.length === 0) {
        // 如果找不到 background:#fff 容器，用 parent 的 parent
        $container = $a.parent().parent();
      }
      summary = $container.find('div[style*="color:#6e6e73"]').first().text().trim();
      
      // 如果摘要太长（可能串联了多条），只取第一条
      if (summary.length > 200) {
        // 可能串联了多条新闻的摘要，截取合理的长度
        summary = summary.substring(0, 150) + '...';
      }
      
      newsItems.push({
        title: title,
        summary: summary,
        source: source,
        url: url,
        time: '',
        heat: 5
      });
    });
    
    if (newsItems.length > 0) {
      sections[sectionId] = newsItems;
    }
  });
  
  return sections;
}

// ============================================================
// 解析 source_international.html (article-based 结构)
// ============================================================
function parseInternationalFile(html) {
  const $ = cheerio.load(html);
  const sections = {};

  $('section.section-block').each((i, elem) => {
    const $section = $(elem);
    const sectionId = $section.attr('id');
    if (!sectionId) return;

    const newsItems = [];
    
    $section.find('article.news-item').each((j, item) => {
      const $item = $(item);
      
      const $link = $item.find('h3 a').first();
      const title = $link.text().trim();
      const url = $link.attr('href') || '';
      
      if (!title || isGarbage(title)) return;
      
      const rawTitle = $item.find('.raw-title').text().trim();
      const summary = $item.find('p').text().trim();
      
      const metaTexts = [];
      $item.find('.meta span').each((k, span) => {
        metaTexts.push($(span).text().trim());
      });
      
      const source = metaTexts[0] || '';
      
      let time = '';
      for (const t of metaTexts) {
        const m = t.match(/发布：(.+)/);
        if (m) { time = m[1]; break; }
      }
      
      let heat = 5;
      for (const t of metaTexts) {
        const m = t.match(/热度：(\d+)/);
        if (m) { heat = parseInt(m[1]); break; }
      }
      
      newsItems.push({
        title: title,
        summary: summary,
        source: source,
        url: url,
        time: time,
        heat: heat,
        rawTitle: rawTitle
      });
    });
    
    if (newsItems.length > 0) {
      sections[sectionId] = newsItems;
    }
  });
  
  return sections;
}

// ============================================================
// 去重：基于标题前30字符比对
// ============================================================
function deduplicate(items) {
  const seen = new Set();
  const result = [];
  for (const item of items) {
    const normalizedTitle = item.title.replace(/\s+/g, '').substring(0, 30);
    const key = item.url && item.url.length > 10 ? item.url : normalizedTitle;
    if (!seen.has(key)) {
      seen.add(key);
      result.push(item);
    }
  }
  return result;
}

// ============================================================
// 拆分主数组和 Extra 数组
// Extra 最大40条
// ============================================================
function splitMainAndExtra(items, mainCount = 20, extraMax = 40) {
  const main = items.slice(0, mainCount);
  const extra = items.slice(mainCount, mainCount + extraMax);
  return { main, extra };
}

// ============================================================
// 河南足球新闻过滤：只保留标题含"河南"的
// ============================================================
function filterHenanNews(items) {
  return items.filter(item => {
    const t = item.title;
    return t.includes('河南') || t.includes('拉莫斯') || t.includes('航海体育场') || t.includes('彩陶坊');
  });
}

// 中超其他球队新闻：排除河南相关
function filterCslOtherNews(items) {
  return items.filter(item => {
    const t = item.title;
    return !t.includes('河南') && !t.includes('拉莫斯') && !t.includes('航海体育场') && !t.includes('彩陶坊');
  });
}

// ============================================================
// 主函数
// ============================================================
function main() {
  console.log('=== 新闻提取脚本 v2 启动 ===');
  
  const domesticPath = path.join(REPO_DIR, 'source_domestic.html');
  const internationalPath = path.join(REPO_DIR, 'source_international.html');
  
  if (!fs.existsSync(domesticPath)) {
    console.error('ERROR: source_domestic.html 不存在!');
    process.exit(1);
  }
  if (!fs.existsSync(internationalPath)) {
    console.error('ERROR: source_international.html 不存在!');
    process.exit(1);
  }
  
  const domesticHtml = fs.readFileSync(domesticPath, 'utf-8');
  const internationalHtml = fs.readFileSync(internationalPath, 'utf-8');
  
  console.log('解析 source_domestic.html ...');
  const domesticSections = parseDomesticFile(domesticHtml);
  Object.keys(domesticSections).forEach(k => {
    console.log(`  [domestic] ${k}: ${domesticSections[k].length} 条`);
  });
  
  console.log('解析 source_international.html ...');
  const internationalSections = parseInternationalFile(internationalHtml);
  Object.keys(internationalSections).forEach(k => {
    console.log(`  [international] ${k}: ${internationalSections[k].length} 条`);
  });
  
  const result = {};
  
  // 1. 国内新闻 (仅 domestic 文件)
  const domesticNews = deduplicate(domesticSections['domestic'] || []);
  const domesticSplit = splitMainAndExtra(domesticNews);
  result.mockHotNewsDomestic = domesticSplit.main;
  result.mockHotNewsDomesticExtra = domesticSplit.extra;
  
  // 2. 国际新闻 (两个文件合并)
  const intlNews = deduplicate([
    ...(domesticSections['international'] || []),
    ...(internationalSections['international'] || [])
  ]);
  const intlSplit = splitMainAndExtra(intlNews);
  result.mockHotNewsInternational = intlSplit.main;
  result.mockHotNewsInternationalExtra = intlSplit.extra;
  
  // 3. AI科技 (两个文件合并: ai_tech + ai)
  const aiNews = deduplicate([
    ...(domesticSections['ai_tech'] || []),
    ...(internationalSections['ai'] || [])
  ]);
  const aiSplit = splitMainAndExtra(aiNews);
  result.mockHotNewsAI = aiSplit.main;
  result.mockHotNewsAIExtra = aiSplit.extra;
  
  // 4. 娱乐新闻 (仅 domestic 文件)
  const entNews = deduplicate(domesticSections['entertainment'] || []);
  const entSplit = splitMainAndExtra(entNews);
  result.mockEntertainment = entSplit.main;
  result.mockEntertainmentExtra = entSplit.extra;
  
  // 5. 河南足球 — 从 henan_football 和 csl_other 合并后筛选
  const allFootball = deduplicate([
    ...(domesticSections['henan_football'] || []),
    ...(domesticSections['csl_other'] || [])
  ]);
  result.mockHenanNews = filterHenanNews(allFootball).slice(0, 15);
  
  // 6. 中超其他球队 — 从合并后的足球新闻中排除河南
  result.mockCslOtherTeams = filterCslOtherNews(allFootball).slice(0, 20);
  
  // 7. 财经新闻 (仅 international 文件的 stock section)
  const stockNews = deduplicate(internationalSections['stock'] || []);
  const stockSplit = splitMainAndExtra(stockNews);
  result.mockStockNews = stockSplit.main;
  result.mockStockNewsExtra = stockSplit.extra;
  
  // 8. AI牛股推荐 (仅 domestic 文件的 ai_stock section)
  result.mockStockAI = deduplicate(domesticSections['ai_stock'] || []).slice(0, 10);
  
  // 输出统计
  console.log('\n=== 提取结果 ===');
  let total = 0;
  for (const [key, items] of Object.entries(result)) {
    console.log(`  ${key}: ${items.length} 条`);
    total += items.length;
  }
  console.log(`  总计: ${total} 条`);
  
  const output = {
    extracted_at: new Date().toISOString(),
    total_items: total,
    sections: result
  };
  
  const outputPath = path.join(REPO_DIR, 'news_data.json');
  fs.writeFileSync(outputPath, JSON.stringify(output, null, 2), 'utf-8');
  console.log(`\n已输出到: ${outputPath}`);
  
  return output;
}

main();
