#!/usr/bin/env python3
"""
Marvis Interest Listener - 接收网页端兴趣词提交，自动搜索推送
监听 localhost:9876，收到请求后：更新 exclusive_interests.json → 运行 extract_news.py → git push
"""
import json
import os
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
INTERESTS_FILE = os.path.join(PROJECT_DIR, 'exclusive_interests.json')
EXTRACT_SCRIPT = os.path.join(PROJECT_DIR, 'extract_news.py')

class InterestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        
        # CORS headers
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        if parsed.path == '/ping':
            self.wfile.write(json.dumps({'status': 'ok'}).encode())
            return
        
        if parsed.path == '/interest':
            params = parse_qs(parsed.query)
            user = params.get('user', [''])[0]
            keyword = params.get('keyword', [''])[0]
            action = params.get('action', ['add'])[0]
            
            if not user or not keyword:
                self.wfile.write(json.dumps({'error': 'Missing user or keyword'}).encode())
                return
            
            try:
                # 读取当前兴趣词
                interests = {}
                if os.path.exists(INTERESTS_FILE):
                    with open(INTERESTS_FILE, 'r', encoding='utf-8') as f:
                        interests = json.load(f)
                
                if user not in interests:
                    interests[user] = []
                
                if action == 'remove':
                    if keyword in interests[user]:
                        interests[user].remove(keyword)
                        self.log_message(f"Removed '{keyword}' from user '{user}'")
                else:
                    if keyword not in interests[user]:
                        interests[user].append(keyword)
                        self.log_message(f"Added '{keyword}' for user '{user}'")
                
                # 写入文件
                with open(INTERESTS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(interests, f, ensure_ascii=False, indent=2)
                
                # 运行 extract_news.py
                self.log_message("Running extract_news.py...")
                result = subprocess.run(
                    [sys.executable, EXTRACT_SCRIPT],
                    cwd=PROJECT_DIR,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    # git add + commit + push
                    subprocess.run(['git', 'add', 'exclusive_interests.json', 'exclusive_news_arrays.js'], cwd=PROJECT_DIR)
                    subprocess.run(['git', 'commit', '-m', f'自动更新专属新闻: {user} -> {keyword}'], cwd=PROJECT_DIR)
                    subprocess.run(['git', 'push'], cwd=PROJECT_DIR)
                    
                    self.wfile.write(json.dumps({'success': True, 'message': f'已为{user}搜索「{keyword}」相关新闻并推送'}).encode())
                else:
                    self.wfile.write(json.dumps({'success': False, 'error': result.stderr[:200]}).encode())
                    
            except Exception as e:
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            return
        
        # 默认响应
        self.wfile.write(json.dumps({'message': 'Marvis Interest Listener running'}).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[Listener] {format % args}", flush=True)


if __name__ == '__main__':
    port = 9876
    server = HTTPServer(('127.0.0.1', port), InterestHandler)
    print(f"[Listener] Started on http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Listener] Shutting down...")
        server.shutdown()
