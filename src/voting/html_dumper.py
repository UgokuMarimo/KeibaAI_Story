# C:\KeibaAI\src\voting\html_dumper.py
import os
import sys

# 標準出力の文字化け対策（Windows用）
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

import asyncio
from playwright.async_api import async_playwright

# プロジェクトパス設定
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src')) # config等のインポート解決用

import config

# HTMLおよび画像を保存する先
DUMP_DIR = 'C:/KeibaAI/data/voting_mocks'

async def dump_umaca_screens():
    os.makedirs(DUMP_DIR, exist_ok=True)
    print(f"[DUMPER] Screen dumps will be saved to: {DUMP_DIR}")
    
    async with async_playwright() as p:
        # スマホ向け画面（UMACAスマート）のビューポートとUser-Agentを設定
        iphone = p.devices['iPhone 12 Pro']
        browser = await p.chromium.launch(headless=False) # デバッグのためブラウザを目視表示
        context = await browser.new_context(**iphone)
        page = await context.new_page()
        
        # ダイアログが発生した場合は自動で承認（accept）して進める（投票確認などのため）
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
        
        # 1. ログイン画面への遷移
        umaca_url = "https://www.ipat.jra.go.jp/sp/umaca/" 
        
        print(f"[DUMPER] Navigating to: {umaca_url}")
        try:
            await page.goto(umaca_url, timeout=30000)
            await page.wait_for_timeout(2000)
            
            # HTMLとスクリーンショットの保存
            await save_page_dump(page, "01_login_page")
            
            print("\n" + "="*50)
            print(" ⚠️ 【お願い】 ⚠️")
            print(" ブラウザ画面で「UMACAへのログイン」および「適当なレースの馬券選択画面」まで")
            print(" 手動で操作を進めてください。")
            print(" 画面遷移ごとに、自動でHTMLソースとスクリーンショットがローカルに保存されます。")
            print("="*50 + "\n")
            
            # ページ遷移を監視し、自動で保存するループ (手動で完了するまで繰り返す)
            prev_url = page.url
            count = 2
            
            while True:
                # ユーザーがコンソールから終了できるようにする、またはURLの変更を検出
                await page.wait_for_timeout(1000)
                curr_url = page.url
                
                if curr_url != prev_url:
                    print(f"[DUMPER] URL Changed detected -> {curr_url}")
                    await page.wait_for_timeout(2000) # 読み込み待機
                    
                    filename = f"{count:02d}_screen_step"
                    await save_page_dump(page, filename)
                    prev_url = curr_url
                    count += 1
                    
        except Exception as e:
            print(f"[DUMPER ERROR] Failed during dumping process: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("[DUMPER] Closing browser.")
            await browser.close()

async def save_page_dump(page, name_prefix):
    """現在のページのHTMLとスクリーンショットを保存する"""
    html_path = os.path.join(DUMP_DIR, f"{name_prefix}.html")
    img_path = os.path.join(DUMP_DIR, f"{name_prefix}.png")
    
    # HTML保存
    content = await page.content()
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    # スクリーンショット保存
    await page.screenshot(path=img_path)
    
    print(f"  [SAVED] HTML: {os.path.basename(html_path)}, Screenshot: {os.path.basename(img_path)}")

if __name__ == '__main__':
    # 非同期実行
    asyncio.run(dump_umaca_screens())
