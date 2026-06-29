const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// 读取 index.html
const indexFile = path.join(__dirname, 'index.html');
const statusFile = path.join(__dirname, 'workbuddy_news_update_status.json');

console.log('读取 index.html...');
const content = fs.readFileSync(indexFile, 'utf8');

// 更可靠的统计方法：使用括号计数来识别数组中的每个对象
function countArrayItems(content, arrayName) {
  // 找到数组开始的位置
  const startPattern = `const ${arrayName} = [`;
  const startIndex = content.indexOf(startPattern);
  
  if (startIndex === -1) {
    console.log(`  未找到数组 ${arrayName}`);
    return 0;
  }
  
  // 找到匹配的结束括号
  let bracketCount = 0;
  let inString = false;
  let stringChar = '';
  let i = startIndex + startPattern.length - 1; // -1 因为 [ 已经算一个括号
  
  let depth = 0;
  let itemCount = 0;
  
  while (i < content.length) {
    const char = content[i];
    const nextChar = i + 1 < content.length ? content[i + 1] : '';
    
    // 处理字符串
    if (inString) {
      if (char === '\\') {
        i += 2; // 跳过转义字符
        continue;
      }
      if (char === stringChar) {
        inString = false;
      }
      i++;
      continue;
    }
    
    // 检测字符串开始
    if (char === '"' || char === "'" || char === '`') {
      inString = true;
      stringChar = char;
      i++;
      continue;
    }
    
    // 计数括号
    if (char === '[') {
      bracketCount++;
    } else if (char === ']') {
      bracketCount--;
      if (bracketCount === 0) {
        // 找到数组结束
        break;
      }
    } else if (char === '{') {
      if (bracketCount === 1) {
        // 这是数组中的一个对象的开始
        itemCount++;
      }
    }
    
    i++;
  }
  
  return itemCount;
}

// 读取现有的状态文件（如果存在）
let status = {
  "updated_at": new Date().toISOString().replace('Z', '+08:00'),
  "run_id": `manual-${Date.now()}`,
  "status": "success",
  "summary": "News data updated",
  "sections": {
    "domestic": {
      "fetched": 0,
      "accepted": 0,
      "rejected": 0
    },
    "international": {
      "fetched": 0,
      "accepted": 0,
      "rejected": 0
    },
    "ai_tech": {
      "fetched": 0,
      "accepted": 0,
      "rejected": 0
    },
    "finance": {
      "fetched": 0,
      "accepted": 0,
      "rejected": 0
    },
    "football": {
      "fetched": 0,
      "accepted": 0,
      "rejected": 0
    },
    "entertainment": {
      "fetched": 0,
      "accepted": 0,
      "rejected": 0
    },
    "stock_ai": {
      "fetched": 0,
      "accepted": 0,
      "rejected": 0
    },
    "csl_other": {
      "fetched": 0,
      "accepted": 0,
      "rejected": 0
    }
  },
  "output_files": [
    "index.html"
  ],
  "failed_sources": [],
  "pushed_to_github": false,
  "notes": "Status file auto-generated after news update"
};

console.log('\n统计新闻数量...\n');

// 统计国内新闻 (主数组 + Extra)
const domesticMain = countArrayItems(content, 'mockHotNewsDomestic');
const domesticExtra = countArrayItems(content, 'mockHotNewsDomesticExtra');
const domesticTotal = domesticMain + domesticExtra;
status.sections.domestic.fetched = domesticTotal;
status.sections.domestic.accepted = domesticTotal;
console.log(`国内新闻: ${domesticMain} + ${domesticExtra} = ${domesticTotal} 条`);

// 统计国际新闻
const internationalMain = countArrayItems(content, 'mockHotNewsInternational');
const internationalExtra = countArrayItems(content, 'mockHotNewsInternationalExtra');
const internationalTotal = internationalMain + internationalExtra;
status.sections.international.fetched = internationalTotal;
status.sections.international.accepted = internationalTotal;
console.log(`国际新闻: ${internationalMain} + ${internationalExtra} = ${internationalTotal} 条`);

// 统计AI科技新闻
const aiMain = countArrayItems(content, 'mockHotNewsAI');
const aiExtra = countArrayItems(content, 'mockHotNewsAIExtra');
const aiTotal = aiMain + aiExtra;
status.sections.ai_tech.fetched = aiTotal;
status.sections.ai_tech.accepted = aiTotal;
console.log(`AI科技新闻: ${aiMain} + ${aiExtra} = ${aiTotal} 条`);

// 统计财经新闻
const financeMain = countArrayItems(content, 'mockStockNews');
const financeExtra = countArrayItems(content, 'mockStockNewsExtra');
const financeTotal = financeMain + financeExtra;
status.sections.finance.fetched = financeTotal;
status.sections.finance.accepted = financeTotal;
console.log(`财经新闻: ${financeMain} + ${financeExtra} = ${financeTotal} 条`);

// 统计足球新闻（河南队）
const footballCount = countArrayItems(content, 'mockHenanNews');
status.sections.football.fetched = footballCount;
status.sections.football.accepted = footballCount;
console.log(`足球新闻（河南队）: ${footballCount} 条`);

// 统计娱乐新闻
const entMain = countArrayItems(content, 'mockEntertainment');
const entExtra = countArrayItems(content, 'mockEntertainmentExtra');
const entTotal = entMain + entExtra;
status.sections.entertainment.fetched = entTotal;
status.sections.entertainment.accepted = entTotal;
console.log(`娱乐新闻: ${entMain} + ${entExtra} = ${entTotal} 条`);

// 统计 AI 概念股
const stockAICount = countArrayItems(content, 'mockStockAI');
status.sections.stock_ai.fetched = stockAICount;
status.sections.stock_ai.accepted = stockAICount;
console.log(`AI概念股: ${stockAICount} 条`);

// 统计中超其他球队新闻
const cslOtherCount = countArrayItems(content, 'mockCslOtherTeams');
status.sections.csl_other.fetched = cslOtherCount;
status.sections.csl_other.accepted = cslOtherCount;
console.log(`中超其他球队: ${cslOtherCount} 条`);

// 检查 Git 状态
console.log('\n检查 Git 状态...');
try {
  const gitStatus = execSync('git status --porcelain', { 
    cwd: __dirname,
    encoding: 'utf8'
  });
  
  if (gitStatus.trim()) {
    console.log('检测到未提交的更改，尝试提交...');
    
    // 尝试提交和推送
    try {
      execSync('git add index.html', { cwd: __dirname });
      execSync('git commit -m "自动更新新闻数据"', { cwd: __dirname });
      execSync('git push origin main', { cwd: __dirname });
      status.pushed_to_github = true;
      console.log('✓ 已提交并推送到 GitHub');
    } catch (e) {
      status.pushed_to_github = false;
      status.notes = 'Git 提交或推送失败: ' + e.message;
      console.log('✗ Git 操作失败:', e.message);
    }
  } else {
    console.log('所有更改已提交');
    status.pushed_to_github = true;
  }
} catch (e) {
  console.log('无法检查 Git 状态');
  status.pushed_to_github = false;
}

// 写入状态文件
console.log('\n写入状态文件...');
fs.writeFileSync(statusFile, JSON.stringify(status, null, 2), 'utf8');
console.log('✓ 状态文件已更新:', statusFile);

// 追加到历史文件（JSONL 一行）
const historyFile = path.join(__dirname, 'workbuddy_news_update_history.jsonl');
fs.appendFileSync(historyFile, JSON.stringify(status) + '\n', 'utf8');
console.log('✓ 历史记录已追加:', historyFile);
console.log('\n=== 状态摘要 ===');
console.log(`更新时间: ${status.updated_at}`);
console.log(`状态: ${status.status}`);
console.log(`已推送到 GitHub: ${status.pushed_to_github}`);
console.log(`总计抓取: ${domesticTotal + internationalTotal + aiTotal + financeTotal + footballCount + entTotal + stockAICount + cslOtherCount} 条新闻`);
