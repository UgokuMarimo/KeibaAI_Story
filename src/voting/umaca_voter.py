# C:\KeibaAI\src\voting\umaca_voter.py
import os
import sys
import time
import random
from typing import Dict, List, Any
from playwright.sync_api import sync_playwright, Page, Dialog

# プロジェクトパス設定
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..'))
sys.path.append(PROJECT_ROOT)

import config
from voting.voter_interface import BaseVoter

class UmacaVoter(BaseVoter):
    """
    JRA UMACAスマート（スマートフォン専用投票サイト）をPlaywrightで自動操作する本番用投票エンジン。
    日曜朝にダンプされたHTMLモックファイルを使用した、平日模擬テスト環境（--test-mock）も内包する。
    """
    
    def __init__(self, use_mock: bool = None):
        # use_mockが明示されない場合は、configの設定を参照
        self.use_mock = use_mock if use_mock is not None else (getattr(config, 'AUTO_VOTING_MODE', 'mock') == 'mock')
        
        self.logged_in = False
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.balance = 0.0
        
        # モックファイルの保存先ディレクトリの確認
        self.mock_dir = 'C:/KeibaAI/data/voting_mocks'
        
        # JRA UMACAスマートの本番URL
        self.umaca_url = 'https://www.ipat.jra.go.jp/sp/umaca/'

    def _init_browser(self):
        """Playwrightブラウザとタッチエミュレーション（iPhone 12 Pro）の初期化"""
        if self.page:
            return
            
        print(f"[UMACA-VOTER] Launching Playwright browser (Mock Mode: {self.use_mock})...")
        self.playwright = sync_playwright().start()
        
        # UI操作の可視化のため headless=False (本番稼働時にバックグラウンド化したい場合は config で制御可能)
        self.browser = self.playwright.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled", # 自動操作検知の回避
                "--disable-gpu",                                 # GPU関連のエラー・警告の抑制
                "--log-level=3"                                  # 不要なログ（DevTools等）の抑制
            ]
        )
        
        # JRA UMACAスマートはスマートフォン専用のため、iPhone 12 Pro のタッチエミュレーションを強制適用
        iphone_12 = self.playwright.devices['iPhone 12 Pro']
        self.context = self.browser.new_context(
            **iphone_12,
            locale="ja-JP",
            timezone_id="Asia/Tokyo"
        )
        
        self.page = self.context.new_page()
        self.page.set_default_timeout(30000) # ページ操作全体のデフォルトタイムアウトを30秒に制限
        
        # ※ グローバルダイアログハンドラーは使用しない。
        # 投票確定ステップで page.expect_event("dialog") を使い、明示的にダイアログを待って承認する。
        # （グローバルハンドラーだと networkidle より遅れてダイアログが現れた場合に取りこぼす）
        
        # モックモード時は外部接続を遮断し、高速かつ安定したローカルHTMLテストを実現
        if self.use_mock:
            self.page.route("**/*", self._handle_mock_route)

    def _handle_mock_route(self, route):
        """モックテスト時にJRA本番サーバーへの不要なリクエスト（JS/CSS/画像等）を遮断するインターセプター"""
        url = route.request.url
        if url.startswith("file://"):
            route.continue_()
        else:
            # 外部ネットワークリクエストは即時アボートしてタイムアウトを防ぐ
            route.abort()

    def _handle_dialog(self, dialog: Dialog):
        """ブラウザの確認ダイアログ（confirm）を自動承認するイベントハンドラ"""
        print(f"[UMACA-VOTER DIALOG] Dialog appeared: '{dialog.message}' -> Auto Accepting.")
        dialog.accept()

    def _wait_for(self, selector: str, timeout: int = 30000):
        """モックモード時は attached (DOM存在確認)、本番時は visible (表示確認) で要素を待機する"""
        state = "attached" if self.use_mock else "visible"
        self.page.wait_for_selector(selector, state=state, timeout=timeout)

    def _random_delay(self, min_ms: int = 800, max_ms: int = 2000):
        """人間らしい操作に見せかけるためのランダムウェイト（高速化チューニング）"""
        delay = random.uniform(min_ms, max_ms) / 1000.0
        time.sleep(delay)

    def _human_type(self, selector: str, text: str):
        """1文字ごとに数ミリ秒のランダム遅延を挟み、キーボードタイピングを模倣する（人間らしい速度）"""
        self._wait_for(selector)
        if self.use_mock:
            self.page.locator(selector).fill(text, force=True)
        else:
            self.page.locator(selector).click()
            self._random_delay(200, 500)
            self.page.locator(selector).fill("")
            self._random_delay(150, 300)
            for char in text:
                self.page.locator(selector).type(char)
                self._random_delay(80, 200)

    def _human_click(self, selector: str):
        """タップ前に十分なディレイを挟み、確実にボタンをタップする（超安定スマホエミュレート）"""
        self._random_delay(400, 800)
        self._wait_for(selector)
        
        # 表示直後はイベントリスナーが未バインドの可能性があるため、十分な安定ウェイト（1秒前後）を挟む
        self._random_delay(500, 1000)
        
        if self.use_mock:
            self.page.locator(selector).first.click(force=True)
        else:
            try:
                # SPAは複数のdata-role="page"を同時保持するため、.first で現在アクティブな画面のボタンを確実に指定
                self.page.locator(selector).first.tap(timeout=5000)
            except Exception as tap_err:
                # タップがサポートされていない、または失敗した場合は通常のクリックにフォールバック
                print(f"[UMACA-VOTER WARN] Tap failed, falling back to click: {tap_err}")
                self.page.locator(selector).first.click()

    def _navigate_step(self, step_num: int, fallback_selector: str = None, action: str = "click"):
        """
        ハイブリッドナビゲーション：
        模擬テストモードの場合は次のHTMLモックファイルを直接開き、
        本番モードの場合はUI上のセレクターをクリック、またはアクションを実行して画面遷移させる。
        """
        if self.use_mock:
            # 模擬テストモード: 対応するローカルHTMLファイルを直接開く
            # 呼び出し側のステップ数と実際のHTMLファイルのズレを補正
            mapped_step = step_num
            if step_num == 7:
                mapped_step = 8   # 馬番選択の段階で、金額入力フォームが表示されている08を読み込む
            elif step_num == 8:
                mapped_step = 9   # セット完了後の投票一覧画面09を読み込む
            elif step_num == 9:
                mapped_step = 10  # 合計金額入力画面10を読み込む

            file_name = f"{mapped_step:02d}_screen_step.html" if mapped_step > 1 else "01_login_page.html"
            mock_file_path = os.path.join(self.mock_dir, file_name)
            
            # HTMLダンプが存在しない場合はエラー
            if not os.path.exists(mock_file_path):
                raise FileNotFoundError(f"[UMACA-VOTER ERROR] Mock file not found: {mock_file_path}")
                
            print(f"[UMACA-VOTER MOCK-NAV] Navigating directly to local mockup: {file_name}")
            self.page.goto(f"file:///{mock_file_path}")
            self._random_delay(300, 600)
        else:
            # 本番モード: 実際のUIセレクターをクリック・操作する
            if fallback_selector:
                print(f"[UMACA-VOTER PRODUCTION] Performing action '{action}' on selector '{fallback_selector}'")
                if action == "click":
                    self._human_click(fallback_selector)
                elif action == "press_enter":
                    self.page.locator(fallback_selector).press("Enter")
                # 画面遷移後の通信待ちを 1.5秒〜3秒 に調整して安定化
                self._random_delay(1500, 3000) # 通信とSPA遷移の完了を待つ

    def login(self) -> bool:
        """投票システムへのログインを実行する。"""
        if self.logged_in:
            return True
            
        try:
            self._init_browser()
            
            # 1. ログインページへ移動
            if self.use_mock:
                self._navigate_step(1)
            else:
                print(f"[UMACA-VOTER] Connecting to production UMACA Smart: {self.umaca_url}")
                self.page.goto(self.umaca_url)
                self._random_delay(1500, 3000)
            
            # 2. 認証情報の取得（.env経由）
            card_no = os.getenv("UMACA_CARD_NUMBER", "")
            birthday = os.getenv("UMACA_BIRTHDAY", "")
            security_code = os.getenv("UMACA_SECURITY_CODE", "")
            
            if self.use_mock:
                # モックモード時は .env の設定が空でもダミー値でテストできるようにする
                if not card_no: card_no = "1234567890"
                if not birthday: birthday = "19900101"
                if not security_code: security_code = "1234"
            else:
                if not card_no or not birthday or not security_code:
                    print("[UMACA-VOTER ERROR] Missing credentials in .env! Card, Birthday, and Security Code are all required.")
                    return False
                
            print("[UMACA-VOTER] Inputting login credentials (autofill for Card/Birthday)...")
            
            # カード番号の入力 (オートフィル模倣のため即時入力)
            self._wait_for("input#umacaCard")
            self.page.locator("input#umacaCard").fill(card_no)
            
            # 生年月日の入力 (オートフィル模倣のため即時入力)
            self._wait_for("input#birth")
            self.page.locator("input#birth").fill(birthday)
            
            # 暗証番号の入力 (人間らしいタイピング遅延)
            self._human_type("input#pass", security_code)
            
            # 3. ログイン実行 ➡ メニュー画面へ遷移
            print("[UMACA-VOTER] Clicking Login button...")
            self._navigate_step(2, fallback_selector=".btnColor a") # 本番時はログインボタンをクリック、モック時は02を開く
            
            # ログイン検証 (SPAのため、id="voteMenu" がページ内に現れるか確認)
            self._wait_for("#voteMenu", timeout=15000)
            print("[UMACA-VOTER] Login Successful!")
            self.logged_in = True
            return True
            
        except Exception as e:
            print(f"[UMACA-VOTER ERROR] Login process failed: {e}")
            return False

    def get_balance(self) -> float:
        """現在の投票口座/UMACA残高を取得する。"""
        if not self.logged_in:
            print("[UMACA-VOTER ERROR] Must login before getting balance.")
            return 0.0
            
        # 投票完了フラグが立っている場合は、パースをスキップしてキャッシュ残高を直接返す（モック・本番共通）
        if getattr(self, '_voted_flag', False):
            print(f"[UMACA-VOTER] Returning estimated post-vote balance: {self.balance:,} 円")
            return self.balance
            
        try:
            # ログイン後メニュー画面から投票限度額のテキストを抽出
            # 残高表示エリアのセレクター: #umacaPrice 内の .PricePurchase
            balance_selector = "#umacaPrice .PricePurchase"
            self._wait_for(balance_selector, timeout=15000)
            
            balance_text = self.page.locator(balance_selector).text_content()
            
            # カンマなどを除去して数値（float）にパース
            cleaned_balance = balance_text.replace(",", "").replace("円", "").strip()
            self.balance = float(cleaned_balance)
            
            print(f"[UMACA-VOTER] Current balance fetched: {self.balance:,} 円")
            return self.balance
            
        except Exception as e:
            print(f"[UMACA-VOTER ERROR] Failed to fetch balance: {e}")
            return 0.0

    def vote(self, race_id: str, bets: List[Dict[str, Any]]) -> bool:
        """指定されたレースに対して投票（購入）を実行する。"""
        if not self.logged_in:
            print("[UMACA-VOTER ERROR] Must login before voting.")
            return False
            
        if not bets:
            print("[UMACA-VOTER] No bets specified. Skipping.")
            return True
            
        # 1レースあたりの最大投資上限額リミッター
        total_cost = sum(bet['amount'] for bet in bets)
        max_limit = getattr(config, 'AUTO_VOTING_MAX_AMOUNT_PER_RACE', 5000)
        if total_cost > max_limit:
            print(f"[UMACA-VOTER ERROR] Vote aborted! Total cost ({total_cost:,} 円) exceeds maximum limit per race ({max_limit:,} 円).")
            return False

        # 現在の残高を確認
        current_balance = self.get_balance()
        if current_balance < total_cost:
            print(f"[UMACA-VOTER ERROR] Insufficient balance! Required: {total_cost:,} 円, Available: {current_balance:,} 円")
            return False

        bet_type = bets[0].get('bet_type', 'win')
        if not self.navigate_to_race_and_bet_type(race_id, bet_type):
            return False
            
        return self.vote_on_current_page(bets)

    def navigate_to_race_and_bet_type(self, race_id: str, bet_type: str = "win") -> bool:
        """投票のために競馬場・レース・式別を選択し、馬番選択画面へ遷移する（一本化フロー用）。"""
        if not self.logged_in:
            print("[UMACA-VOTER ERROR] Must login before navigation.")
            return False
        try:
            # ------------------------------------------------------------
            # Step 1: 通常投票ページへの遷移
            # ------------------------------------------------------------
            print("[UMACA-VOTER] Transitioning to regular vote menu...")
            self._navigate_step(3, fallback_selector=".voteMainNav a.ico_regular") # 通常投票をクリック

            # ------------------------------------------------------------
            # Step 2: 競馬場（開催場）の選択
            # ------------------------------------------------------------
            course_id = race_id[4:6]
            venue_name = config.PLACE_MAP_IDS.get(course_id)
            if not venue_name:
                raise ValueError(f"Unknown course ID '{course_id}' in race_id: {race_id}")
                
            print(f"[UMACA-VOTER] Selecting Venue: {venue_name}...")
            venue_selector = f'#jyo a:has-text("{venue_name}"):not([data-value2])'
            self._navigate_step(4, fallback_selector=venue_selector)

            # ------------------------------------------------------------
            # Step 3: レース番号（1R〜12R）の選択
            # ------------------------------------------------------------
            race_num_str = str(int(race_id[10:])) # "11R" の "11" 部分
            print(f"[UMACA-VOTER] Selecting Race: {race_num_str}R...")
            race_selector = f'a.raceList:has(.raceNum:has-text("{race_num_str}R"))'
            self._navigate_step(5, fallback_selector=race_selector)

            # ------------------------------------------------------------
            # Step 4: 式別（単勝・複勝など）の選択
            # ------------------------------------------------------------
            bet_type_name = "単勝" if bet_type == "win" else "複勝"
            print(f"[UMACA-VOTER] Selecting Bet Type: {bet_type_name}...")
            siki_selector = f'#siki ul.selectList a:has-text("{bet_type_name}")'
            self._navigate_step(6, fallback_selector=siki_selector)
            
            # 馬番選択画面への遷移確認（モック時は07_screen_step.htmlをロード）
            if self.use_mock:
                self._navigate_step(7)
            else:
                self._wait_for("ul.selectHorse", timeout=15000)
            
            return True
        except Exception as e:
            print(f"[UMACA-VOTER ERROR] Navigation failed: {e}")
            return False

    def get_odds_from_page(self) -> dict:
        """現在開いている馬番選択画面からリアルタイムオッズを一括取得する（一本化フロー用）。"""
        print("[UMACA-VOTER] Fetching odds directly from UMACA vote page...")
        try:
            self._wait_for("ul.selectHorse a")
            
            # すべての馬のリンク要素を取得
            horse_locators = self.page.locator("ul.selectHorse a")
            count = horse_locators.count()
            
            odds_dict = {}
            for i in range(count):
                loc = horse_locators.nth(i)
                # 馬番を取得
                umaban_str = loc.get_attribute("data-value")
                # オッズテキストを取得
                ods_span = loc.locator("span.ods")
                if ods_span.count() > 0:
                    ods_text = ods_span.inner_text().strip()
                    try:
                        odds_dict[int(umaban_str)] = float(ods_text)
                    except ValueError:
                        # 取消馬など
                        pass
            print(f"[UMACA-VOTER] Successfully scraped {len(odds_dict)} odds from the page.")
            return odds_dict
        except Exception as e:
            print(f"[UMACA-VOTER ERROR] Failed to fetch odds from page: {e}")
            return {}

    def vote_on_current_page(self, bets: list) -> bool:
        """現在開いている馬番選択画面から、選択した馬・金額で投票を完了させる（一本化フロー用）。"""
        if not self.logged_in:
            print("[UMACA-VOTER ERROR] Must login before voting.")
            return False
        if not bets:
            print("[UMACA-VOTER] No bets specified. Skipping.")
            return True
            
        try:
            total_cost = sum(bet['amount'] for bet in bets)
            print(f"[UMACA-VOTER] Processing {len(bets)} bet(s) (Total Cost: {total_cost:,} 円)...")

            # ------------------------------------------------------------
            # 馬番の選択と金額入力（多点買い対応ループ）
            # ------------------------------------------------------------
            for idx, bet in enumerate(bets):
                umaban = bet['umaban']
                amount = bet['amount']
                unit_amount = amount // 100
                if unit_amount <= 0:
                    raise ValueError(f"Invalid bet amount: {amount} (Must be at least 100 yen)")

                print(f"  -> Bet [{idx+1}]: Horse No. {umaban} (Amount: {amount} yen)")

                # 投票一覧画面から馬番選択画面へ戻る（2頭目以降の場合）
                if idx > 0:
                    print(f"  -> Back to horse selection for Bet [{idx+1}]...")
                    continue_selector = 'ul li.btnSoftColor a:has-text("馬")'
                    self._human_click(continue_selector)
                    self._random_delay(2000, 3500)

                # 馬番 aタグのクリック
                uma_selector = f'ul.selectHorse a[data-value="{umaban}"]'
                self._navigate_step(7, fallback_selector=uma_selector)

                # 金額入力 (div#kin 内の input)
                input_selector = "div#kin input[type='tel']"
                self._human_type(input_selector, str(unit_amount))

                # 「セット」ボタンのクリック ➡ 投票一覧へ
                print("  -> Setting bet amount...")
                set_selector = "div#kin .btnColor a:not([title])"
                self._navigate_step(8, fallback_selector=set_selector)

            # ------------------------------------------------------------
            # 投票リストの確認と購入完了
            # ------------------------------------------------------------
            print("[UMACA-VOTER] Confirming bet list...")
            self._wait_for("ul#noCircle", timeout=30000)
            
            print("[UMACA-VOTER] Finalizing inputs...")
            finish_selector = "div#toui .btnColor a"
            self._navigate_step(9, fallback_selector=finish_selector)

            # 最終確認画面（合計金額入力）
            print(f"[UMACA-VOTER] Typing total sum amount: {total_cost} yen...")
            sum_selector = "input#sum"
            self._human_type(sum_selector, str(total_cost))

            # 「投票」ボタンをクリックして送信
            print("[UMACA-VOTER] ===== COMMITTING ACTUAL VOTE =====")
            vote_btn_selector = "div#LIST .btnColor a"
            
            if self.use_mock:
                self._human_click(vote_btn_selector)
                print("[UMACA-VOTER MOCK] Vote committed successfully in mock simulation!")
                self.balance -= total_cost
                self._voted_flag = True
            else:
                print("[UMACA-VOTER] Clicking vote button and waiting for confirm dialog (up to 30s)...")
                try:
                    with self.page.expect_event("dialog", timeout=30000) as dialog_info:
                        self._human_click(vote_btn_selector)
                    dialog = dialog_info.value
                    print(f"[UMACA-VOTER DIALOG] Dialog appeared: '{dialog.message}' -> Accepting.")
                    dialog.accept()
                    print("[UMACA-VOTER] Dialog accepted. Waiting for page transition (up to 30s)...")
                    self.page.wait_for_load_state("networkidle", timeout=30000)
                except Exception as dialog_err:
                    print(f"[UMACA-VOTER WARN] No dialog detected ({dialog_err}). Waiting anyway...")
                    self.page.wait_for_load_state("networkidle", timeout=30000)
                
                print("[UMACA-VOTER PRODUCTION] Vote committed successfully to JRA server!")
                self.balance -= total_cost
                self._voted_flag = True

            print("[UMACA-VOTER] ===================================")
            return True
        except Exception as e:
            print(f"[UMACA-VOTER ERROR] Unified vote processing failed: {e}")
            return False

    def close(self):
        """ブラウザやセッションをクローズし、クリーンアップする。"""
        print("[UMACA-VOTER] Closing browser session...")
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass
        try:
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
        self.logged_in = False
        print("[UMACA-VOTER] Session closed safely.")


# ==============================================================================
# 🧪 平日模擬テスト用のエントリーポイント
# ==============================================================================
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test UMACA Voter.")
    parser.add_argument('--test-mock', action='store_true', help="Run in weekday mock simulation mode using dumped HTML files.")
    args = parser.parse_args()
    
    if args.test_mock or len(sys.argv) > 1:
        print("\n=== [MOCK TESTING] Starting UMACA Smart Voter Weekday Simulation ===")
        # モックモードを強制的にTrueにしてテスト
        voter = UmacaVoter(use_mock=True)
        
        # モック用のテストアカウント情報を環境変数に一時セット（すでに設定されていればそれを優先）
        if not os.getenv("UMACA_CARD_NUMBER"):
            os.environ["UMACA_CARD_NUMBER"] = "110002378622"
            os.environ["UMACA_BIRTHDAY"] = "20030214"
            os.environ["UMACA_SECURITY_CODE"] = "4041"
            
        success = False
        try:
            # 1. ログイン
            if voter.login():
                # 2. 残高取得
                balance = voter.get_balance()
                
                # 3. 模擬投票 (東京11R・単勝16番・100円)
                test_bets = [{
                    'umaban': 16,
                    'bet_type': 'win',
                    'amount': 100
                }]
                
                # 東京の開催コードは "05" (race_id の 4-6 桁目が "05" に対応)
                test_race_id = "202605310511" # 2026年5月31日 東京11R
                
                success = voter.vote(test_race_id, test_bets)
                
                # 4. 投票後の残高取得
                new_balance = voter.get_balance()
                print(f"[MOCK RESULT] Initial: {balance:,} 円 -> New: {new_balance:,} 円 (Cost: 100円)")
        finally:
            voter.close()
            
        if success:
            print("\n=== [MOCK SUCCESS] UMACA Smart Voter Simulation Completed Flawlessly! ===")
            sys.exit(0)
        else:
            print("\n=== [MOCK FAILED] UMACA Smart Voter Simulation Failed. ===")
            sys.exit(1)
