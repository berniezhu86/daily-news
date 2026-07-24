/**
 * validate_index_html.js — index.html 内嵌 JS 语法校验
 *
 * 从 index.html 中抽取所有 <script>...</script> 内容，
 * 用 node --check 逐个校验语法，存在 SyntaxError 则非零退出。
 *
 * 用法: node validate_index_html.js
 *   返回值: 0 = 全部通过，非 0 = 存在语法错误
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const REPO_DIR = __dirname;
const INDEX_HTML = path.join(REPO_DIR, 'index.html');
const TMP_PREFIX = path.join(REPO_DIR, '.tmp_script_check_');

function main() {
  const html = fs.readFileSync(INDEX_HTML, 'utf-8');

  // 抽取所有 <script> 块（含内嵌 JS，不含 src= 外部引用）
  const scriptPattern = /<script\b[^>]*>([\s\S]*?)<\/script\s*>/gi;
  let match;
  let blockIndex = 0;
  let hasError = false;
  const tempFiles = [];

  while ((match = scriptPattern.exec(html)) !== null) {
    const rawContent = match[1];
    const attrs = match[0].match(/<script\b([^>]*)>/i);
    const hasSrc = attrs && /src\s*=/.test(attrs[1]);

    // 跳过外部引用 <script src="...">
    if (hasSrc) continue;

    // 跳过空块
    const trimmed = rawContent.trim();
    if (!trimmed) continue;

    const tmpFile = TMP_PREFIX + blockIndex + '.js';
    tempFiles.push(tmpFile);

    // 写入临时文件
    fs.writeFileSync(tmpFile, rawContent, 'utf-8');

    // 用 node --check 校验语法
    try {
      execSync(`/Users/bainian/.workbuddy/binaries/node/versions/22.22.2/bin/node --check "${tmpFile}"`, {
        stdio: ['pipe', 'pipe', 'pipe'],
        timeout: 10000,
      });
    } catch (e) {
      hasError = true;
      const stderr = (e.stderr || '').toString().trim();
      // 提取行号
      const lineMatch = stderr.match(/\.tmp_script_check_\d+\.js:(\d+)/);
      const lineNum = lineMatch ? lineMatch[1] : '?';
      // 尝试定位在 index.html 中的实际行号
      const fileLines = rawContent.split('\n');
      const errorLine = lineMatch ? parseInt(lineMatch[1]) : 0;
      const snippet = errorLine > 0 && errorLine <= fileLines.length
        ? fileLines[errorLine - 1].trim().substring(0, 120)
        : '';

      console.error(`\n❌ 语法错误 — 第 ${blockIndex + 1} 个 <script> 块 (行 ~${lineNum}):`);
      console.error(`   错误: ${stderr.split('\n').pop() || stderr}`);
      if (snippet) console.error(`   代码: ${snippet}`);
    }

    blockIndex++;
  }

  // 清理临时文件
  for (const f of tempFiles) {
    try { fs.unlinkSync(f); } catch(e) {}
  }

  if (hasError) {
    console.error(`\n⚠️  共 ${blockIndex} 个 <script> 块，存在语法错误，已阻止提交。`);
    process.exit(1);
  }

  console.log(`✅ 语法校验通过: ${blockIndex} 个 <script> 块均无错误`);
  process.exit(0);
}

main();
