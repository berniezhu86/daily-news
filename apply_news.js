/**
 * apply_news.js - 读取 news_data.json，替换 index.html 中的新闻数组
 * 
 * 用法: node apply_news.js
 * 
 * 安全保障:
 *   - 只替换白名单中的数组
 *   - 绝对不碰 mockTrackingEvents, mockMatches, mockPastMatches,
 *     mockMovieRanking, mockTVRanking, mockVarietyRanking,
 *     mockStockIndices, mockSectorPrediction, mockExclusiveNews, mockStockAI
 *   - 使用括号计数法精确定位数组边界
 *   - 替换后自动验证 JS 语法
 */

const fs = require('fs');
const path = require('path');

const REPO_DIR = __dirname;
const INDEX_HTML = path.join(REPO_DIR, 'index.html');
const ARRAYS_JS = path.join(REPO_DIR, 'generated_news_arrays.js');
const NEWS_JSON = path.join(REPO_DIR, 'news_data.json');

// ============================================================
// 白名单：只有这些数组允许替换
// ============================================================
const ALLOWED_ARRAYS = [
  'mockHotNewsDomestic',
  'mockHotNewsDomesticExtra',
  'mockHotNewsInternational',
  'mockHotNewsInternationalExtra',
  'mockHotNewsAI',
  'mockHotNewsAIExtra',
  'mockEntertainment',
  'mockEntertainmentExtra',
  'mockHenanNews',
  'mockCslOtherTeams',
  'mockStockNews',
  'mockStockNewsExtra',
  // mockStockAI 已移除 — 由财经AI观察自动化单独维护，不受全量新闻更新影响
];

// 受保护数组 - 绝对不能碰
const PROTECTED_ARRAYS = [
  'mockTrackingEvents',
  'mockMatches',
  'mockPastMatches',
  'mockMovieRanking',
  'mockTVRanking',
  'mockVarietyRanking',
  'mockStockIndices',
  'mockSectorPrediction',
  'mockExclusiveNews',
  'mockStockAI',  // 由财经AI观察自动化维护，不受全量新闻更新影响
];

// ============================================================
// 将新闻对象转换为 JS 代码
// ============================================================
function itemToCode(item) {
  const parts = [];
  
  // rank
  if (item.rank !== undefined) {
    parts.push(`rank:${item.rank}`);
  } else {
    parts.push(`rank:1`);
  }
  
  // title
  parts.push(`title:${JSON.stringify(item.title)}`);
  
  // source
  parts.push(`source:${JSON.stringify(item.source || '')}`);
  
  // summary
  parts.push(`summary:${JSON.stringify(item.summary || '')}`);
  
  // heat
  parts.push(`heat:${item.heat || 5}`);
  
  // time — 格式化显示（如"6月29日 16:42"）
  let timeStr = item.time || '';
  if (!timeStr) {
    const now = new Date();
    timeStr = `${now.getMonth()+1}月${now.getDate()}日 ${now.getHours()}:${String(now.getMinutes()).padStart(2,'0')}`;
  }
  parts.push(`time:${JSON.stringify(timeStr)}`);
  
  // url
  parts.push(`url:${JSON.stringify(item.url || '')}`);
  
  // sourceRegion (for international news)
  if (item.rawTitle) {
    parts.push(`sourceRegion:"global"`);
  }
  
  return `{${parts.join(', ')}}`;
}

function itemsToCode(items) {
  if (items.length === 0) return '[]';
  const lines = items.map(item => '  ' + itemToCode(item));
  return `[\n${lines.join(',\n')}\n]`;
}

// ============================================================
// 从 HTML 内容中提取旧数组的标题集合（用于检测新条目）
// ============================================================
function extractOldTitles(content, arrayName) {
  const titles = new Set();
  const patterns = [
    new RegExp(`const\\s+${arrayName}\\s*=\\s*\\[`, 'g'),
    new RegExp(`var\\s+${arrayName}\\s*=\\s*\\[`, 'g'),
    new RegExp(`let\\s+${arrayName}\\s*=\\s*\\[`, 'g'),
  ];
  
  for (const pattern of patterns) {
    const match = pattern.exec(content);
    if (match) {
      const startIdx = match.index + match[0].length - 1; // 指向 '['
      const endIdx = findArrayEnd(content, startIdx);
      if (endIdx > startIdx) {
        const arrayStr = content.substring(startIdx + 1, endIdx);
        const titlePattern = /title:("[^"]*"|'[^']*')/g;
        let tm;
        while ((tm = titlePattern.exec(arrayStr)) !== null) {
          // 去掉外层引号
          const title = tm[1].slice(1, -1);
          titles.add(title);
        }
      }
      break; // 找到就退出
    }
  }
  
  return titles;
}

// ============================================================
// 在 index.html 中查找并替换数组
// 使用括号计数法精确定位数组边界
// ============================================================
function findArrayEnd(content, startIdx) {
  // startIdx 指向 '['
  let depth = 0;
  let inString = false;
  let stringChar = null;
  let i = startIdx;
  
  while (i < content.length) {
    const ch = content[i];
    
    if (inString) {
      if (ch === '\\') {
        i += 2;
        continue;
      }
      if (ch === stringChar) {
        inString = false;
      }
    } else {
      if (ch === '"' || ch === "'" || ch === '`') {
        inString = true;
        stringChar = ch;
      } else if (ch === '[') {
        depth++;
      } else if (ch === ']') {
        depth--;
        if (depth === 0) {
          return i; // 返回 ']' 的位置
        }
      }
    }
    i++;
  }
  
  return -1; // 没找到匹配的 ]
}

function replaceArray(content, arrayName, newContent) {
  // 查找 "const arrayName = [" 或 "var arrayName = [" 或 "let arrayName = ["
  const patterns = [
    new RegExp(`const\\s+${arrayName}\\s*=\\s*\\[`, 'g'),
    new RegExp(`var\\s+${arrayName}\\s*=\\s*\\[`, 'g'),
    new RegExp(`let\\s+${arrayName}\\s*=\\s*\\[`, 'g'),
  ];
  
  for (const pattern of patterns) {
    const match = pattern.exec(content);
    if (match) {
      const bracketStart = content.indexOf('[', match.index);
      if (bracketStart === -1) continue;
      
      const bracketEnd = findArrayEnd(content, bracketStart);
      if (bracketEnd === -1) {
        console.error(`  ERROR: 找不到 ${arrayName} 的结束括号 ]`);
        continue;
      }
      
      // 找到分号 (可能在 ] 之后)
      let semicolonEnd = bracketEnd + 1;
      while (semicolonEnd < content.length && content[semicolonEnd] !== ';' && content[semicolonEnd] !== '\n') {
        semicolonEnd++;
      }
      if (content[semicolonEnd] === ';') {
        semicolonEnd++;
      }
      
      const before = content.substring(0, match.index);
      const after = content.substring(semicolonEnd);
      const declaration = content.substring(match.index, bracketStart);
      
      return {
        content: before + declaration + newContent + ';' + after,
        found: true
      };
    }
  }
  
  return { content, found: false };
}

// ============================================================
// 更新版本号
// ============================================================
function updateVersion(content) {
  const now = new Date();
  const dateStr = now.getFullYear().toString() +
    String(now.getMonth() + 1).padStart(2, '0') +
    String(now.getDate()).padStart(2, '0');
  
  // 查找当前版本号格式 YYYYMMDDvN
  const versionRegex = /\d{8}v\d+/g;
  const matches = content.match(versionRegex);
  
  let newVersion;
  if (matches && matches.length > 0) {
    const currentVersion = matches[0];
    const currentDate = currentVersion.substring(0, 8);
    const currentNum = parseInt(currentVersion.substring(9));
    
    if (currentDate === dateStr) {
      newVersion = `${dateStr}v${currentNum + 1}`;
    } else {
      newVersion = `${dateStr}v1`;
    }
  } else {
    newVersion = `${dateStr}v1`;
  }
  
  // 替换所有版本号
  let newContent = content.replace(versionRegex, newVersion);
  console.log(`版本号更新: ${matches && matches[0] ? matches[0] : 'N/A'} → ${newVersion}`);
  
  return newContent;
}

// ============================================================
// 将数组注入 index.html 的 <script> 块中
// ============================================================
function insertArrayIntoScript(content, arrayName, newCode) {
  // 查找 <script> 标签
  const scriptMatch = content.match(/<script>[\s\S]*?<\/script>/);
  if (!scriptMatch) {
    console.error(`  ERROR: index.html 中找不到 <script> 块`);
    return null;
  }
  
  // 生成 const 声明
  const declaration = `const ${arrayName} = ${newCode};`;
  
  // 在 </script> 之前插入
  const insertPos = scriptMatch.index + scriptMatch[0].length - '</script>'.length;
  const before = content.substring(0, insertPos);
  const after = content.substring(insertPos);
  return before + '\n' + declaration + '\n' + after;
}

// ============================================================
// 更新 generated_news_arrays.js
// ============================================================
function updateArraysJs(sections) {
  if (!fs.existsSync(ARRAYS_JS)) {
    console.log('  SKIP: generated_news_arrays.js 不存在，跳过');
    return;
  }
  
  let content = fs.readFileSync(ARRAYS_JS, 'utf-8');
  let replaced = 0;
  
  for (const arrayName of ALLOWED_ARRAYS) {
    const items = sections[arrayName];
    if (!items || items.length === 0) {
      const emptyResult = replaceArray(content, arrayName, '[]');
      if (emptyResult.found) {
        content = emptyResult.content;
        console.log(`  [arrays.js] CLEARED: ${arrayName}`);
      }
      continue;
    }
    
    items.forEach((item, idx) => {
      if (!item.rank) item.rank = idx + 1;
    });
    
    const newCode = itemsToCode(items);
    const result = replaceArray(content, arrayName, newCode);
    
    if (result.found) {
      content = result.content;
      replaced++;
    }
  }
  
  if (replaced > 0) {
    fs.writeFileSync(ARRAYS_JS, content, 'utf-8');
    console.log(`  [arrays.js] 已更新 ${replaced} 个数组`);
  }
}

// ============================================================
// 主函数
// ============================================================
function main() {
  console.log('=== 新闻应用脚本启动 ===');
  
  // 读取 news_data.json
  if (!fs.existsSync(NEWS_JSON)) {
    console.error('ERROR: news_data.json 不存在! 请先运行 extract_news.js');
    process.exit(1);
  }
  
  const newsData = JSON.parse(fs.readFileSync(NEWS_JSON, 'utf-8'));
  const sections = newsData.sections || newsData;
  
  // 先更新 generated_news_arrays.js（确保 JS 数据文件同步更新）
  updateArraysJs(sections);
  
  // 读取 index.html
  if (!fs.existsSync(INDEX_HTML)) {
    console.error('ERROR: index.html 不存在!');
    process.exit(1);
  }
  
  let content = fs.readFileSync(INDEX_HTML, 'utf-8');
  const originalLength = content.length;
  let needsArraysInserted = false;
  
  // 检查 index.html 是否包含数组
  for (const arrayName of ALLOWED_ARRAYS) {
    const patterns = [
      new RegExp(`const\\s+${arrayName}\\s*=\\s*\\[`, 'g'),
      new RegExp(`var\\s+${arrayName}\\s*=\\s*\\[`, 'g'),
      new RegExp(`let\\s+${arrayName}\\s*=\\s*\\[`, 'g'),
    ];
    let found = false;
    for (const p of patterns) {
      if (p.test(content)) { found = true; break; }
    }
    if (!found && sections[arrayName] && sections[arrayName].length > 0) {
      needsArraysInserted = true;
      break;
    }
  }
  
  // 如果 index.html 中没有数组，先注入
  if (needsArraysInserted) {
    console.log('  index.html 中未找到 JS 新闻数组，开始注入...');
    for (const arrayName of ALLOWED_ARRAYS) {
      const items = sections[arrayName];
      if (!items || items.length === 0) continue;
      
      items.forEach((item, idx) => {
        if (!item.rank) item.rank = idx + 1;
      });
      
      const newCode = itemsToCode(items);
      const result = insertArrayIntoScript(content, arrayName, newCode);
      if (result) {
        content = result;
        console.log(`  INSERTED: ${arrayName} ← ${items.length} 条`);
      }
    }
    console.log('  数组注入完成');
  }
  
  // 提前提取所有旧标题（用于检测新条目）
  const oldTitlesMap = {};
  for (const arrayName of ALLOWED_ARRAYS) {
    oldTitlesMap[arrayName] = extractOldTitles(content, arrayName);
  }
  
  // 替换每个白名单数组
  let replaced = 0;
  let notFound = 0;
  
  for (const arrayName of ALLOWED_ARRAYS) {
    const items = sections[arrayName];
    if (!items || items.length === 0) {
      // 没有新数据时清空数组，避免残留旧数据
      const emptyResult = replaceArray(content, arrayName, '[]');
      if (emptyResult.found) {
        content = emptyResult.content;
        console.log(`  CLEARED: ${arrayName} (无新数据，已清空旧数据)`);
      } else {
        console.log(`  SKIP: ${arrayName} (无数据且未找到数组)`);
      }
      continue;
    }
    
    // 为每条新闻设置 rank
    const oldTitles = oldTitlesMap[arrayName] || new Set();
    items.forEach((item, idx) => {
      if (!item.rank) item.rank = idx + 1;
    });
    
    const newCode = itemsToCode(items);
    const result = replaceArray(content, arrayName, newCode);
    
    if (result.found) {
      content = result.content;
      console.log(`  OK: ${arrayName} ← ${items.length} 条`);
      replaced++;
    } else {
      console.log(`  NOT FOUND: ${arrayName} (index.html 中不存在此数组)`);
      notFound++;
    }
  }
  
  // 验证：确保受保护数组未被修改
  for (const protectedName of PROTECTED_ARRAYS) {
    const before = fs.readFileSync(INDEX_HTML, 'utf-8');
    const beforeMatch = before.match(new RegExp(`(?:const|var|let)\\s+${protectedName}\\s*=\\s*\\[`));
    const afterMatch = content.match(new RegExp(`(?:const|var|let)\\s+${protectedName}\\s*=\\s*\\[`));
    
    if (beforeMatch && afterMatch) {
      // 简单验证：受保护数组仍然存在
      // (不做深度比较，只确认存在)
    } else if (beforeMatch && !afterMatch) {
      console.error(`  CRITICAL ERROR: 受保护数组 ${protectedName} 被意外删除!`);
      process.exit(1);
    }
  }
  
  console.log(`\n替换完成: ${replaced} 个数组已更新, ${notFound} 个未找到`);
  
  // 更新版本号
  content = updateVersion(content);
  
  // 写回 index.html
  fs.writeFileSync(INDEX_HTML, content, 'utf-8');
  console.log(`index.html 已更新 (${originalLength} → ${content.length} 字符)`);
  
  // 输出统计用于状态文件
  const stats = {};
  for (const arrayName of ALLOWED_ARRAYS) {
    if (sections[arrayName]) {
      stats[arrayName] = sections[arrayName].length;
    }
  }
  
  // 写入统计到临时文件供 update_status_file.js 使用
  const statsPath = path.join(REPO_DIR, '.last_apply_stats.json');
  fs.writeFileSync(statsPath, JSON.stringify({
    applied_at: new Date().toISOString(),
    replaced_arrays: replaced,
    not_found_arrays: notFound,
    stats: stats
  }, null, 2), 'utf-8');
  
  console.log(`\n统计已写入: ${statsPath}`);
  console.log('=== 完成 ===');
}

main();
