#!/usr/bin/env python3
"""
bugi.tw 短連結建置腳本（v3）
從 Google Sheet 對照表讀取資料，為每個短代號生成轉跳 HTML 檔案
"""

import csv
import os
import re
import shutil
import datetime
import urllib.request
import urllib.parse

SHEET_ID   = '1A5s6RfoLKR8OmA45zL5dpq35fPRfT7fE'
SHEET_NAME = '對照表'
CSV_URL = (
    f'https://docs.google.com/spreadsheets/d/{SHEET_ID}'
    f'/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(SHEET_NAME)}'
)

KEEP_FILES    = {'CNAME','README.md','build_redirects.py','.git','.github','.gitignore','.nojekyll'}
SKIP_STATUSES = {'已停用','過期'}
EXAMPLE_PATS  = ['範例','XXXX','YYYY','ZZZZ','...?','/...']

REDIRECT_TPL = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<title>跳轉中...</title>
<meta name="robots" content="noindex,nofollow">
<meta http-equiv="refresh" content="0;url={th}">
<link rel="canonical" href="{th}">
<script>window.location.replace("{tj}");</script>
</head>
<body style="font-family:-apple-system,sans-serif;padding:40px;text-align:center;color:#555;">
<p>正在跳轉到目的地...</p>
<p style="font-size:13px;">如果沒有自動跳轉，請<a href="{th}">點此繼續</a>。</p>
</body>
</html>
"""

INDEX_TPL = """<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="utf-8"><title>bugi.tw 短連結系統</title>
<meta name="robots" content="noindex,nofollow">
<style>body{{font-family:-apple-system,sans-serif;max-width:1000px;margin:40px auto;padding:20px;color:#333;}}
h1{{color:#2E5C8A;}}table{{border-collapse:collapse;width:100%;}}
td,th{{border:1px solid #ddd;padding:10px;}}th{{background:#2E5C8A;color:#fff;}}
tr:nth-child(even){{background:#f9f9f9;}}code{{background:#eef;padding:2px 6px;}}</style>
</head><body>
<h1>bugi.tw 短連結系統</h1>
<p style="color:#888">{count} 個短連結 ｜ 最後更新：{date}</p>
<table><tr><th>短代號</th><th>平台</th><th>產品</th><th>狀態</th></tr>
{rows}</table></body></html>
"""

def he(s): return s.replace('&','&amp;').replace('"','&quot;').replace('<','&lt;').replace('>','&gt;')
def je(s): return s.replace('\\','\\\\').replace('"','\\"')

def clean():
    for e in os.listdir('.'):
        if e in KEEP_FILES or e.startswith('.'): continue
        if os.path.isdir(e): shutil.rmtree(e); print(f'  Removed dir: {e}')
        elif e.endswith('.html'): os.remove(e); print(f'  Removed: {e}')

def fetch_csv():
    print('Fetching CSV from Google Sheet...')
    req = urllib.request.Request(CSV_URL, headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8')

def find_col(header, *candidates):
    for i, name in enumerate(header):
        for c in candidates:
            if c in name.strip(): return i
    return -1

def parse(csv_text):
    rows = list(csv.reader(csv_text.splitlines()))
    header_idx = None
    for i, row in enumerate(rows):
        if not row: continue
        # 搜尋所有欄位（不限前 N 欄）
        joined = '|'.join(c.strip() for c in row)
        if '地區' in joined and '短代號' in joined:
            header_idx = i; break
        if row[0].strip() == '短代號':
            header_idx = i; break
    if header_idx is None:
        raise RuntimeError('找不到標題列（需含「地區」+「短代號」）')

    hdr = rows[header_idx]
    code_idx   = find_col(hdr, '短代號')
    target_idx = find_col(hdr, '目的地連結','目的地')
    plat_idx   = find_col(hdr, '聯盟平台')
    prod_idx   = find_col(hdr, '產品名稱')
    stat_idx   = find_col(hdr, '狀態')
    print(f'Columns → code:{code_idx} target:{target_idx} platform:{plat_idx} product:{prod_idx} status:{stat_idx}')

    if code_idx < 0 or target_idx < 0:
        raise RuntimeError(f'缺少必要欄位：短代號={code_idx} 目的地連結={target_idx}')

    entries, seen, skipped = [], set(), 0
    for row in rows[header_idx+1:]:
        def g(i): return row[i].strip() if i >= 0 and i < len(row) else ''
        code, target = g(code_idx), g(target_idx)
        if not code or not target: continue
        if any(p in target for p in EXAMPLE_PATS): print(f'  Skip example: {code}'); skipped+=1; continue
        if not (target.startswith('http://') or target.startswith('https://')): skipped+=1; continue
        if g(stat_idx) in SKIP_STATUSES: print(f'  Skip {g(stat_idx)}: {code}'); skipped+=1; continue
        if not re.match(r'^[a-zA-Z0-9_\-]+$', code): print(f'  Skip invalid: {code}'); skipped+=1; continue
        if code in seen: print(f'  Dup: {code}'); continue
        seen.add(code)
        entries.append({'code':code,'target':target,'platform':g(plat_idx),'product':g(prod_idx),'status':g(stat_idx)})
    print(f'Parsed {len(entries)} entries, skipped {skipped}')
    return entries

def build(entries):
    for e in entries:
        os.makedirs(e['code'], exist_ok=True)
        with open(f'{e["code"]}/index.html','w',encoding='utf-8') as f:
            f.write(REDIRECT_TPL.format(th=he(e['target']), tj=je(e['target'])))
        print(f'  Built: /{e["code"]}')

def index(entries):
    rows = '\n'.join(f'<tr><td><code>{he(e["code"])}</code></td><td>{he(e["platform"])}</td><td>{he(e["product"])}</td><td>{he(e["status"])}</td></tr>' for e in entries)
    with open('index.html','w',encoding='utf-8') as f:
        f.write(INDEX_TPL.format(count=len(entries), date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M UTC'), rows=rows))

def nojekyll():
    if not os.path.exists('.nojekyll'):
        open('.nojekyll','w').close()

def main():
    print('=== bugi.tw 短連結建置（v3）===\n')
    print('Step 1: 清掉舊檔'); clean()
    print('\nStep 2: 抓 CSV'); csv_text = fetch_csv()
    print('\nStep 3: 解析'); entries = parse(csv_text)
    if not entries: print('\n⚠️ 無有效短連結'); return
    print('\nStep 4: 生成 HTML'); build(entries)
    print('\nStep 5: 首頁 + .nojekyll'); index(entries); nojekyll()
    print(f'\n=== 完成，共建立 {len(entries)} 個短連結 ===')

if __name__ == '__main__':
    main()
