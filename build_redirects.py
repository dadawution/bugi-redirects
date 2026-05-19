#!/usr/bin/env python3
"""
bugi.tw 短連結建置腳本
---------------------------------------
功能：從 Google Sheet 對照表讀取資料，
     為每個短代號生成轉跳 HTML 檔案

執行：python build_redirects.py
"""

import csv
import os
import re
import shutil
import datetime
import urllib.request
import urllib.parse

# ========================================
# 設定區（如果未來換 Google Sheet 才需要改）
# ========================================
SHEET_ID = '1A5s6RfoLKR8OmA45zL5dpq35fPRfT7fE'
SHEET_NAME = '對照表'

CSV_URL = (
    f'https://docs.google.com/spreadsheets/d/{SHEET_ID}'
    f'/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(SHEET_NAME)}'
)

# 不刪除的檔案/資料夾（生成 HTML 前會清掉舊的，但這些保留）
KEEP_FILES = {
    'CNAME', 'README.md', 'build_redirects.py',
    '.git', '.github', '.gitignore', '.nojekyll',
}

# 轉跳 HTML 模板（雙重保險：meta refresh + JavaScript）
REDIRECT_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<title>跳轉中...</title>
<meta name="robots" content="noindex,nofollow">
<meta http-equiv="refresh" content="0;url={target_html}">
<link rel="canonical" href="{target_html}">
<script>window.location.replace("{target_js}");</script>
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:40px;text-align:center;color:#555;">
<p>正在跳轉到目的地...</p>
<p style="font-size:13px;">如果沒有自動跳轉，請<a href="{target_html}">點此繼續</a>。</p>
</body>
</html>
"""

# 首頁模板（給管理員看的列表，noindex 不會被 Google 收錄）
INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<title>bugi.tw 短連結系統</title>
<meta name="robots" content="noindex,nofollow">
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:900px;margin:40px auto;padding:20px;color:#333;}}
h1{{color:#2E5C8A;}}
table{{border-collapse:collapse;width:100%;margin-top:20px;}}
td,th{{border:1px solid #ddd;padding:10px;text-align:left;}}
th{{background:#2E5C8A;color:#fff;}}
tr:nth-child(even){{background:#f9f9f9;}}
code{{background:#eef;padding:2px 6px;border-radius:3px;}}
.meta{{color:#888;font-size:13px;}}
</style>
</head>
<body>
<h1>bugi.tw 短連結系統</h1>
<p class="meta">目前共 <strong>{count}</strong> 個短連結 ｜ 最後更新：{date}</p>
<table>
<tr><th>短代號</th><th>用途</th></tr>
{rows}
</table>
</body>
</html>
"""


def html_escape(s: str) -> str:
    return (s.replace('&', '&amp;')
             .replace('"', '&quot;')
             .replace('<', '&lt;')
             .replace('>', '&gt;'))


def js_escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"')


def clean_old_files():
    """清掉舊的 redirect 資料夾與 HTML，保留設定檔。"""
    for entry in os.listdir('.'):
        if entry in KEEP_FILES:
            continue
        if entry.startswith('.'):
            continue  # 不動隱藏檔
        if os.path.isdir(entry):
            shutil.rmtree(entry)
            print(f'  Removed dir: {entry}')
        elif entry.endswith('.html'):
            os.remove(entry)
            print(f'  Removed: {entry}')


def fetch_csv() -> str:
    """從 Google Sheet 下載 CSV。"""
    print(f'Fetching from Google Sheet...')
    req = urllib.request.Request(CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode('utf-8')


def parse_entries(csv_text: str) -> list[dict]:
    """解析 CSV，回傳合法的 entry 列表。"""
    reader = csv.reader(csv_text.splitlines())
    rows = list(reader)

    # 找標題列（第一個 A 欄等於「短代號」的列）
    header_idx = None
    for i, row in enumerate(rows):
        if row and row[0].strip() == '短代號':
            header_idx = i
            break
    if header_idx is None:
        raise RuntimeError('在 CSV 中找不到「短代號」標題列，請確認 Google Sheet A 欄第一格是「短代號」')

    entries = []
    seen = set()
    skipped = 0

    for row in rows[header_idx + 1:]:
        if len(row) < 2:
            continue
        code = row[0].strip()
        target = row[1].strip()
        purpose = row[2].strip() if len(row) > 2 else ''

        # 跳過空列
        if not code or not target:
            continue

        # 跳過示範資料（含 XXXX、YYYY、ZZZZ 或 ...?）
        if any(pattern in target for pattern in ('XXXX', 'YYYY', 'ZZZZ', '...?', '/...')):
            print(f'  Skip example: {code}')
            skipped += 1
            continue

        # 目的地必須是 http(s)
        if not (target.startswith('http://') or target.startswith('https://')):
            print(f'  Skip invalid URL: {code} -> {target}')
            skipped += 1
            continue

        # 短代號只允許英數、底線、連字號
        if not re.match(r'^[a-zA-Z0-9_\-]+$', code):
            print(f'  Skip invalid code: "{code}"')
            skipped += 1
            continue

        # 重複代號取第一筆
        if code in seen:
            print(f'  WARNING: duplicate code "{code}", using first')
            continue
        seen.add(code)

        entries.append({'code': code, 'target': target, 'purpose': purpose})

    print(f'Parsed {len(entries)} entries, skipped {skipped}')
    return entries


def build_redirects(entries: list[dict]):
    """為每個 entry 生成轉跳 HTML。"""
    for e in entries:
        code = e['code']
        target = e['target']
        os.makedirs(code, exist_ok=True)
        with open(f'{code}/index.html', 'w', encoding='utf-8') as f:
            f.write(REDIRECT_TEMPLATE.format(
                target_html=html_escape(target),
                target_js=js_escape(target),
            ))
        print(f'  Built: /{code}')


def build_index(entries: list[dict]):
    """生成首頁（管理員視角的清單）。"""
    rows_html = '\n'.join(
        f'<tr><td><code>{html_escape(e["code"])}</code></td><td>{html_escape(e["purpose"])}</td></tr>'
        for e in entries
    )
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(INDEX_TEMPLATE.format(
            count=len(entries),
            date=datetime.datetime.now().strftime('%Y-%m-%d %H:%M UTC'),
            rows=rows_html,
        ))
    print('  Built: index.html')


def ensure_nojekyll():
    """建立 .nojekyll 避免 GitHub Pages 把資料夾當 Jekyll 站處理。"""
    if not os.path.exists('.nojekyll'):
        with open('.nojekyll', 'w') as f:
            pass
        print('  Built: .nojekyll')


def main():
    print('=== bugi.tw 短連結建置開始 ===\n')

    print('Step 1: 清掉舊檔')
    clean_old_files()

    print('\nStep 2: 從 Google Sheet 抓資料')
    csv_text = fetch_csv()

    print('\nStep 3: 解析資料')
    entries = parse_entries(csv_text)

    if not entries:
        print('\n⚠️  沒有任何有效的短連結，腳本停止。')
        print('   請檢查 Google Sheet 是否有實際資料（不是範例）。')
        return

    print('\nStep 4: 生成轉跳 HTML')
    build_redirects(entries)

    print('\nStep 5: 生成首頁與設定')
    build_index(entries)
    ensure_nojekyll()

    print(f'\n=== 完成。總共建立 {len(entries)} 個短連結 ===')


if __name__ == '__main__':
    main()
