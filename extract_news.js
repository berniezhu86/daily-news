/**
 * extract_news.js - 从两个源 HTML 文件提取所有新闻，输出到 news_data.json
 * 
 * 用法: node extract_news.js
 * 
 * 源文件:
 *   source_domestic.html   (div-based 结构)
 *   source_international.html (article-based 结构)
 * 
 * 输出:
 *   news_data.json  (包含所有板块的新闻数据)
 * 
 * 板块映射:
 *   domestic → mockHotNewsDomestic / mockHotNewsDomesticExtra
 *   international (两个文件合并) → mockHotNewsInternational / mockHotNewsInternationalExtra
 *   ai + ai_tech (两个文件合并) → mockHotNewsAI / mockHotNewsAIExtra
 *   entertainment → mockEntertainment / mockEntertainmentExtra
 *   henan_football → mockHenanNews
 *   csl_other → mockCslOtherTeams
 *   stock (articles) → mockStockNews / mockStockNewsExtra
 *   ai_stock → mockStockAI
 */

const fs = require('fs');
const path = require('path');
const cheerio = require('/Users/bainian/.workbuddy/binaries/node/workspace/node_modules/cheerio');

const REPO_DIR = __dirname;

// ============================================================
// 解析 source_domestic.html (div-based 结构)
// ============================================================
function parseDomesticFile(html) {
  const $ = cheerio.load(html);
  const sections = {};

  // 获取所有 section-block div
  $('div.section-block, div[id].section-block').each((i, elem) => {
    const $section = $(elem);
    const sectionId = $section.attr('id');
    if (!sectionId) return;

    const newsItems = [];
    
    // 查找新闻条目 (div with background:#fff)
    $section.find('div[style*="background:#fff"]').each((j, item) => {
      const $item = $(item);
      
      // 提取标题和URL
      const $link = $item.find('a').first();
      const title = $link.find('strong').text().trim() || $link.text().trim();
      const url = $link.attr('href') || '';
      
      if (!title) return;
      
      // 提取来源 [来源名]
      const sourceMatch = $item.find('span[style*="color:#888"]').text().match(/\[(.+?)\]/);
      const source = sourceMatch ? sourceMatch[1] : '';
      
      // 提取摘要
      const summary = $item.find('div[style*="color:#6e6e73"]').text().trim();
      
      newsItems.push({
        title: title,
        summary: summary,
        source: source,
        url: url,
        time: '',  // domestic file doesn't have explicit timestamps
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
      
      // 提取标题和URL
      const $link = $item.find('h3 a').first();
      const title = $link.text().trim();
      const url = $link.attr('href') || '';
      
      if (!title) return;
      
      // 提取原始英文标题
      const rawTitle = $item.find('.raw-title').text().trim();
      
      // 提取摘要
      const summary = $item.find('p').text().trim();
      
      // 提取 meta 信息
      const metaTexts = [];
      $item.find('.meta span').each((k, span) => {
        metaTexts.push($(span).text().trim());
      });
      
      const source = metaTexts[0] || '';
      const domain = metaTexts[1] || '';
      
      // 解析发布时间 "发布：2026-06-28 18:16"
      let time = '';
      for (const t of metaTexts) {
        const m = t.match(/发布：(.+)/);
        if (m) { time = m[1]; break; }
      }
      
      // 解析热度 "热度：9"
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
// 合并去重
// ============================================================
function deduplicateByUrl(items) {
  const seen = new Set();
  const result = [];
  for (const item of items) {
    const key = item.url || item.title;
    if (key && !seen.has(key)) {
      seen.add(key);
      result.push(item);
    }
  }
  return result;
}

function deduplicateByTitle(items) {
  const seen = new Set();
  const result = [];
  for (const item of items) {
    const normalizedTitle = item.title.replace(/\s+/g, '').substring(0, 20);
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
function splitMainAndExtra(items, mainCount = 20) {
  const main = items.slice(0, mainCount);
  const extra = items.slice(mainCount);
  return { main, extra };
}

// ============================================================
// 主函数
// ============================================================
function main() {
  console.log('=== 新闻提取脚本启动 ===');
  
  // 读取源文件
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
  
  // 合并各板块
  const result = {};
  
  // 1. 国内新闻 (仅 domestic 文件)
  const domesticNews = domesticSections['domestic'] || [];
  const domesticSplit = splitMainAndExtra(deduplicateByTitle(domesticNews));
  result.mockHotNewsDomestic = domesticSplit.main;
  result.mockHotNewsDomesticExtra = domesticSplit.extra;
  
  // 2. 国际新闻 (两个文件合并)
  const intlNews = [
    ...(domesticSections['international'] || []),
    ...(internationalSections['international'] || [])
  ];
  const intlSplit = splitMainAndExtra(deduplicateByUrl(intlNews));
  result.mockHotNewsInternational = intlSplit.main;
  result.mockHotNewsInternationalExtra = intlSplit.extra;
  
  // 3. AI科技 (两个文件合并: ai_tech + ai)
  const aiNews = [
    ...(domesticSections['ai_tech'] || []),
    ...(internationalSections['ai'] || [])
  ];
  const aiSplit = splitMainAndExtra(deduplicateByUrl(aiNews));
  result.mockHotNewsAI = aiSplit.main;
  result.mockHotNewsAIExtra = aiSplit.extra;
  
  // 4. 娱乐新闻 (仅 domestic 文件)
  const entNews = domesticSections['entertainment'] || [];
  const entSplit = splitMainAndExtra(deduplicateByTitle(entNews));
  result.mockEntertainment = entSplit.main;
  result.mockEntertainmentExtra = entSplit.extra;
  
  // 5. 河南足球 (仅 domestic 文件)
  result.mockHenanNews = deduplicateByTitle(domesticSections['henan_football'] || []);
  
  // 6. 中超其他球队 (仅 domestic 文件)
  result.mockCslOtherTeams = deduplicateByTitle(domesticSections['csl_other'] || []);
  
  // 7. 财经新闻 (仅 international 文件的 stock section)
  const stockNews = internationalSections['stock'] || [];
  const stockSplit = splitMainAndExtra(deduplicateByUrl(stockNews));
  result.mockStockNews = stockSplit.main;
  result.mockStockNewsExtra = stockSplit.extra;
  
  // 8. AI牛股推荐 (仅 domestic 文件的 ai_stock section)
  result.mockStockAI = deduplicateByTitle(domesticSections['ai_stock'] || []);
  
  // 输出统计
  console.log('\n=== 提取结果 ===');
  let total = 0;
  for (const [key, items] of Object.entries(result)) {
    console.log(`  ${key}: ${items.length} 条`);
    total += items.length;
  }
  console.log(`  总计: ${total} 条`);
  
  // 添加元数据
  const output = {
    extracted_at: new Date().toISOString(),
    total_items: total,
    sections: result
  };
  
  // 写入 news_data.json
  const outputPath = path.join(REPO_DIR, 'news_data.json');
  fs.writeFileSync(outputPath, JSON.stringify(output, null, 2), 'utf-8');
  console.log(`\n已输出到: ${outputPath}`);
  
  return output;
}

main();
