#!/usr/bin/env node
/**
 * 更新 index.html 中的 AUTHORITATIVE_NEWS_FALLBACK
 * 读取 authoritative_news.json，将数据注入 index.html
 */
const fs = require('fs');
const path = require('path');

const INDEX_FILE = path.resolve(__dirname, 'index.html');
const AUTH_FILE = path.resolve(__dirname, 'authoritative_news.json');

// 读取 authoritative_news.json
const authData = JSON.parse(fs.readFileSync(AUTH_FILE, 'utf-8'));
const jsonStr = JSON.stringify(authData).replace(/<\//g, '<\\/'); // 防 XSS

// 构建 fallback script 块
const scriptBlock = `\n<script>
var AUTHORITATIVE_NEWS_FALLBACK = ${jsonStr};
</script>\n`;

// 读取 index.html
let html = fs.readFileSync(INDEX_FILE, 'utf-8');

// 检查是否已有 AUTHORITATIVE_NEWS_FALLBACK
const existingMatch = html.match(/var AUTHORITATIVE_NEWS_FALLBACK = .*?;(\s*<\/script>)?/s);
if (existingMatch) {
  // 替换现有 fallback（保留 </script> 闭合标签）
  html = html.replace(
    /var AUTHORITATIVE_NEWS_FALLBACK = .*?;(\s*<\/script>)?/s,
    `var AUTHORITATIVE_NEWS_FALLBACK = ${jsonStr};$1`
  );
  console.log('已替换现有的 AUTHORITATIVE_NEWS_FALLBACK');
} else {
  // 在 </body> 前注入
  const injectPattern = /(<script[\s\S]*?)?\s*<\/body>/i;
  if (injectPattern.test(html)) {
    html = html.replace(injectPattern, (match, scriptTag) => {
      // 如果已经有一个 script 块在 </body> 前，用现有的
      return `${scriptBlock}</body>`;
    });
  } else {
    html = html.replace('</body>', scriptBlock + '</body>');
  }
  console.log('已注入 AUTHORITATIVE_NEWS_FALLBACK');
}

fs.writeFileSync(INDEX_FILE, html, 'utf-8');
console.log('✅ index.html fallback 更新完成');
console.log(`   共 ${authData.count} 条权威要闻`);
