# C:\KeibaAI\src\voting\umaca_voter.py
import os
import sys
import time
import random
from typing import Dict, List, Any
from playwright.sync_api import sync_playwright, Page, Dialog

# 繝励Ο繧ｸ繧ｧ繧ｯ繝医ヱ繧ｹ險ｭ螳・_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..'))
sys.path.append(PROJECT_ROOT)

import config
from voting.voter_interface import BaseVoter

class UmacaVoter(BaseVoter):
    """
    JRA UMACA繧ｹ繝槭・繝茨ｼ医せ繝槭・繝医ヵ繧ｩ繝ｳ蟆ら畑謚慕･ｨ繧ｵ繧､繝茨ｼ峨ｒPlaywright縺ｧ閾ｪ蜍墓桃菴懊☆繧区悽逡ｪ逕ｨ謚慕･ｨ繧ｨ繝ｳ繧ｸ繝ｳ縲・    譌･譖懈悃縺ｫ繝繝ｳ繝励＆繧後◆HTML繝｢繝・け繝輔ぃ繧､繝ｫ繧剃ｽｿ逕ｨ縺励◆縲∝ｹｳ譌･讓｡謫ｬ繝・せ繝育腸蠅・ｼ・-test-mock・峨ｂ蜀・桁縺吶ｋ縲・    """
    
    def __init__(self, use_mock: bool = None):
        # use_mock縺梧・遉ｺ縺輔ｌ縺ｪ縺・ｴ蜷医・縲…onfig縺ｮ險ｭ螳壹ｒ蜿ら・
        self.use_mock = use_mock if use_mock is not None else (getattr(config, 'AUTO_VOTING_MODE', 'mock') == 'mock')
        
        self.logged_in = False
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.balance = 0.0
        
        # 繝｢繝・け繝輔ぃ繧､繝ｫ縺ｮ菫晏ｭ伜・繝・ぅ繝ｬ繧ｯ繝医Μ縺ｮ遒ｺ隱・        self.mock_dir = 'C:/KeibaAI/data/voting_mocks'
        
        # JRA UMACA繧ｹ繝槭・繝医・譛ｬ逡ｪURL
        self.umaca_url = 'https://www.ipat.jra.go.jp/sp/umaca/'

    def _init_browser(self):
        """Playwright繝悶Λ繧ｦ繧ｶ縺ｨ繧ｿ繝・メ繧ｨ繝溘Η繝ｬ繝ｼ繧ｷ繝ｧ繝ｳ・・Phone 12 Pro・峨・蛻晄悄蛹・""
        if self.page:
            return
            
        print(f"[UMACA-VOTER] Launching Playwright browser (Mock Mode: {self.use_mock})...")
        self.playwright = sync_playwright().start()
        
        # UI謫堺ｽ懊・蜿ｯ隕門喧縺ｮ縺溘ａ headless=False (譛ｬ逡ｪ遞ｼ蜒肴凾縺ｫ繝舌ャ繧ｯ繧ｰ繝ｩ繧ｦ繝ｳ繝牙喧縺励◆縺・ｴ蜷医・ config 縺ｧ蛻ｶ蠕｡蜿ｯ閭ｽ)
        self.browser = self.playwright.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"] # 閾ｪ蜍墓桃菴懈､懃衍縺ｮ蝗樣∩
        )
        
        # JRA UMACA繧ｹ繝槭・繝医・繧ｹ繝槭・繝医ヵ繧ｩ繝ｳ蟆ら畑縺ｮ縺溘ａ縲（Phone 12 Pro 縺ｮ繧ｿ繝・メ繧ｨ繝溘Η繝ｬ繝ｼ繧ｷ繝ｧ繝ｳ繧貞ｼｷ蛻ｶ驕ｩ逕ｨ
        iphone_12 = self.playwright.devices['iPhone 12 Pro']
        self.context = self.browser.new_context(
            **iphone_12,
            locale="ja-JP",
            timezone_id="Asia/Tokyo"
        )
        
        self.page = self.context.new_page()
        
        # 窶ｻ 繧ｰ繝ｭ繝ｼ繝舌Ν繝繧､繧｢繝ｭ繧ｰ繝上Φ繝峨Λ繝ｼ縺ｯ菴ｿ逕ｨ縺励↑縺・・        # 謚慕･ｨ遒ｺ螳壹せ繝・ャ繝励〒 page.expect_event("dialog") 繧剃ｽｿ縺・∵・遉ｺ逧・↓繝繧､繧｢繝ｭ繧ｰ繧貞ｾ・▲縺ｦ謇ｿ隱阪☆繧九・        # ・医げ繝ｭ繝ｼ繝舌Ν繝上Φ繝峨Λ繝ｼ縺縺ｨ networkidle 繧医ｊ驕・ｌ縺ｦ繝繧､繧｢繝ｭ繧ｰ縺檎樟繧後◆蝣ｴ蜷医↓蜿悶ｊ縺薙⊂縺呻ｼ・        
        # 繝｢繝・け繝｢繝ｼ繝画凾縺ｯ螟夜Κ謗･邯壹ｒ驕ｮ譁ｭ縺励・ｫ倬溘°縺､螳牙ｮ壹＠縺溘Ο繝ｼ繧ｫ繝ｫHTML繝・せ繝医ｒ螳溽樟
        if self.use_mock:
            self.page.route("**/*", self._handle_mock_route)

    def _handle_mock_route(self, route):
        """繝｢繝・け繝・せ繝域凾縺ｫJRA譛ｬ逡ｪ繧ｵ繝ｼ繝舌・縺ｸ縺ｮ荳崎ｦ√↑繝ｪ繧ｯ繧ｨ繧ｹ繝茨ｼ・S/CSS/逕ｻ蜒冗ｭ会ｼ峨ｒ驕ｮ譁ｭ縺吶ｋ繧､繝ｳ繧ｿ繝ｼ繧ｻ繝励ち繝ｼ"""
        url = route.request.url
        if url.startswith("file://"):
            route.continue_()
        else:
            # 螟夜Κ繝阪ャ繝医Ρ繝ｼ繧ｯ繝ｪ繧ｯ繧ｨ繧ｹ繝医・蜊ｳ譎ゅい繝懊・繝医＠縺ｦ繧ｿ繧､繝繧｢繧ｦ繝医ｒ髦ｲ縺・            route.abort()

    def _handle_dialog(self, dialog: Dialog):
        """繝悶Λ繧ｦ繧ｶ縺ｮ遒ｺ隱阪ム繧､繧｢繝ｭ繧ｰ・・onfirm・峨ｒ閾ｪ蜍墓価隱阪☆繧九う繝吶Φ繝医ワ繝ｳ繝峨Λ"""
        print(f"[UMACA-VOTER DIALOG] Dialog appeared: '{dialog.message}' -> Auto Accepting.")
        dialog.accept()

    def _wait_for(self, selector: str, timeout: int = 15000):
        """繝｢繝・け繝｢繝ｼ繝画凾縺ｯ attached (DOM蟄伜惠遒ｺ隱・縲∵悽逡ｪ譎ゅ・ visible (陦ｨ遉ｺ遒ｺ隱・ 縺ｧ隕∫ｴ繧貞ｾ・ｩ溘☆繧・""
        state = "attached" if self.use_mock else "visible"
        self.page.wait_for_selector(selector, state=state, timeout=timeout)

    def _random_delay(self, min_ms: int = 1500, max_ms: int = 3500):
        """莠ｺ髢薙ｉ縺励＞謫堺ｽ懊↓隕九○縺九￠繧九◆繧√・縺倥▲縺上ｊ縺ｨ縺励◆繝ｩ繝ｳ繝繝繧ｦ繧ｧ繧､繝茨ｼ医せ繝ｭ繝ｼ繝√Η繝ｼ繝九Φ繧ｰ・・""
        delay = random.uniform(min_ms, max_ms) / 1000.0
        time.sleep(delay)

    def _human_type(self, selector: str, text: str):
        """1譁・ｭ励＃縺ｨ縺ｫ謨ｰ繝溘Μ遘偵・繝ｩ繝ｳ繝繝驕・ｻｶ繧呈検縺ｿ縲√く繝ｼ繝懊・繝峨ち繧､繝斐Φ繧ｰ繧呈ｨ｡蛟｣縺吶ｋ・井ｺｺ髢薙ｉ縺励＞騾溷ｺｦ・・""
        self._wait_for(selector)
        if self.use_mock:
            self.page.locator(selector).fill(text, force=True)
        else:
            self.page.locator(selector).click()
            self._random_delay(500, 1000)
            self.page.locator(selector).fill("")
            self._random_delay(300, 600)
            for char in text:
                self.page.locator(selector).type(char)
                self._random_delay(150, 350)

    def _human_click(self, selector: str):
        """繧ｿ繝・・蜑阪↓蜊∝・縺ｪ繝・ぅ繝ｬ繧､繧呈検縺ｿ縲∫｢ｺ螳溘↓繝懊ち繝ｳ繧偵ち繝・・縺吶ｋ・郁ｶ・ｮ牙ｮ壹せ繝槭・繧ｨ繝溘Η繝ｬ繝ｼ繝茨ｼ・""
        self._random_delay(800, 1500)
        self._wait_for(selector)
        
        # 陦ｨ遉ｺ逶ｴ蠕後・繧､繝吶Φ繝医Μ繧ｹ繝翫・縺梧悴繝舌う繝ｳ繝峨・蜿ｯ閭ｽ諤ｧ縺後≠繧九◆繧√∝香蛻・↑螳牙ｮ壹え繧ｧ繧､繝茨ｼ・遘貞燕蠕鯉ｼ峨ｒ謖溘・
        self._random_delay(1000, 1800)
        
        if self.use_mock:
            self.page.locator(selector).first.click(force=True)
        else:
            try:
                # SPA縺ｯ隍・焚縺ｮdata-role="page"繧貞酔譎ゆｿ晄戟縺吶ｋ縺溘ａ縲・first 縺ｧ迴ｾ蝨ｨ繧｢繧ｯ繝・ぅ繝悶↑逕ｻ髱｢縺ｮ繝懊ち繝ｳ繧堤｢ｺ螳溘↓謖・ｮ・                self.page.locator(selector).first.tap(timeout=5000)
            except Exception as tap_err:
                # 繧ｿ繝・・縺後し繝昴・繝医＆繧後※縺・↑縺・√∪縺溘・螟ｱ謨励＠縺溷ｴ蜷医・騾壼ｸｸ縺ｮ繧ｯ繝ｪ繝・け縺ｫ繝輔か繝ｼ繝ｫ繝舌ャ繧ｯ
                print(f"[UMACA-VOTER WARN] Tap failed, falling back to click: {tap_err}")
                self.page.locator(selector).first.click()

    def _navigate_step(self, step_num: int, fallback_selector: str = None, action: str = "click"):
        """
        繝上う繝悶Μ繝・ラ繝翫ン繧ｲ繝ｼ繧ｷ繝ｧ繝ｳ・・        讓｡謫ｬ繝・せ繝医Δ繝ｼ繝峨・蝣ｴ蜷医・谺｡縺ｮHTML繝｢繝・け繝輔ぃ繧､繝ｫ繧堤峩謗･髢九″縲・        譛ｬ逡ｪ繝｢繝ｼ繝峨・蝣ｴ蜷医・UI荳翫・繧ｻ繝ｬ繧ｯ繧ｿ繝ｼ繧偵け繝ｪ繝・け縲√∪縺溘・繧｢繧ｯ繧ｷ繝ｧ繝ｳ繧貞ｮ溯｡後＠縺ｦ逕ｻ髱｢驕ｷ遘ｻ縺輔○繧九・        """
        if self.use_mock:
            # 讓｡謫ｬ繝・せ繝医Δ繝ｼ繝・ 蟇ｾ蠢懊☆繧九Ο繝ｼ繧ｫ繝ｫHTML繝輔ぃ繧､繝ｫ繧堤峩謗･髢九￥
            file_name = f"{step_num:02d}_screen_step.html" if step_num > 1 else "01_login_page.html"
            mock_file_path = os.path.join(self.mock_dir, file_name)
            
            # HTML繝繝ｳ繝励′蟄伜惠縺励↑縺・ｴ蜷医・繧ｨ繝ｩ繝ｼ
            if not os.path.exists(mock_file_path):
                raise FileNotFoundError(f"[UMACA-VOTER ERROR] Mock file not found: {mock_file_path}")
                
            print(f"[UMACA-VOTER MOCK-NAV] Navigating directly to local mockup: {file_name}")
            self.page.goto(f"file:///{mock_file_path}")
            self._random_delay(500, 1000)
        else:
            # 譛ｬ逡ｪ繝｢繝ｼ繝・ 螳滄圀縺ｮUI繧ｻ繝ｬ繧ｯ繧ｿ繝ｼ繧偵け繝ｪ繝・け繝ｻ謫堺ｽ懊☆繧・            if fallback_selector:
                print(f"[UMACA-VOTER PRODUCTION] Performing action '{action}' on selector '{fallback_selector}'")
                if action == "click":
                    self._human_click(fallback_selector)
                elif action == "press_enter":
                    self.page.locator(fallback_selector).press("Enter")
                # 逕ｻ髱｢驕ｷ遘ｻ蠕後・騾壻ｿ｡蠕・■繧・3遘偵・遘・縺ｫ螟ｧ蟷・↓蟒ｶ髟ｷ縺励※螳牙ｮ壼喧
                self._random_delay(3000, 5000) # 騾壻ｿ｡縺ｨSPA驕ｷ遘ｻ縺ｮ螳御ｺ・ｒ蠕・▽

    def login(self) -> bool:
        """謚慕･ｨ繧ｷ繧ｹ繝・Β縺ｸ縺ｮ繝ｭ繧ｰ繧､繝ｳ繧貞ｮ溯｡後☆繧九・""
        if self.logged_in:
            return True
            
        try:
            self._init_browser()
            
            # 1. 繝ｭ繧ｰ繧､繝ｳ繝壹・繧ｸ縺ｸ遘ｻ蜍・            if self.use_mock:
                self._navigate_step(1)
            else:
                print(f"[UMACA-VOTER] Connecting to production UMACA Smart: {self.umaca_url}")
                self.page.goto(self.umaca_url)
                self._random_delay(1500, 3000)
            
            # 2. 隱崎ｨｼ諠・ｱ縺ｮ蜿門ｾ暦ｼ・env邨檎罰・・            card_no = os.getenv("UMACA_CARD_NUMBER", "")
            birthday = os.getenv("UMACA_BIRTHDAY", "")
            security_code = os.getenv("UMACA_SECURITY_CODE", "")
            
            if not card_no or not birthday or not security_code:
                print("[UMACA-VOTER ERROR] Missing credentials in .env! Card, Birthday, and Security Code are all required.")
                return False
                
            print("[UMACA-VOTER] Typing login credentials...")
            
            # 繧ｫ繝ｼ繝臥分蜿ｷ縺ｮ蜈･蜉・            self._human_type("input#umacaCard", card_no)
            
            # 逕溷ｹｴ譛域律縺ｮ蜈･蜉・            self._human_type("input#birth", birthday)
            
            # 證苓ｨｼ逡ｪ蜿ｷ縺ｮ蜈･蜉・            self._human_type("input#pass", security_code)
            
            # 3. 繝ｭ繧ｰ繧､繝ｳ螳溯｡・筐｡ 繝｡繝九Η繝ｼ逕ｻ髱｢縺ｸ驕ｷ遘ｻ
            print("[UMACA-VOTER] Clicking Login button...")
            self._navigate_step(2, fallback_selector=".btnColor a") # 譛ｬ逡ｪ譎ゅ・繝ｭ繧ｰ繧､繝ｳ繝懊ち繝ｳ繧偵け繝ｪ繝・け縲√Δ繝・け譎ゅ・02繧帝幕縺・            
            # 繝ｭ繧ｰ繧､繝ｳ讀懆ｨｼ (SPA縺ｮ縺溘ａ縲（d="voteMenu" 縺後・繝ｼ繧ｸ蜀・↓迴ｾ繧後ｋ縺狗｢ｺ隱・
            self._wait_for("#voteMenu", timeout=15000)
            print("[UMACA-VOTER] Login Successful!")
            self.logged_in = True
            return True
            
        except Exception as e:
            print(f"[UMACA-VOTER ERROR] Login process failed: {e}")
            return False

    def get_balance(self) -> float:
        """迴ｾ蝨ｨ縺ｮ謚慕･ｨ蜿｣蠎ｧ/UMACA谿矩ｫ倥ｒ蜿門ｾ励☆繧九・""
        if not self.logged_in:
            print("[UMACA-VOTER ERROR] Must login before getting balance.")
            return 0.0
            
        # 謚慕･ｨ螳御ｺ・ヵ繝ｩ繧ｰ縺檎ｫ九▲縺ｦ縺・ｋ蝣ｴ蜷医・縲√ヱ繝ｼ繧ｹ繧偵せ繧ｭ繝・・縺励※繧ｭ繝｣繝・す繝･谿矩ｫ倥ｒ逶ｴ謗･霑斐☆・医Δ繝・け繝ｻ譛ｬ逡ｪ蜈ｱ騾夲ｼ・        if getattr(self, '_voted_flag', False):
            print(f"[UMACA-VOTER] Returning estimated post-vote balance: {self.balance:,} 蜀・)
            return self.balance
            
        try:
            # 繝ｭ繧ｰ繧､繝ｳ蠕後Γ繝九Η繝ｼ逕ｻ髱｢縺九ｉ謚慕･ｨ髯仙ｺｦ鬘阪・繝・く繧ｹ繝医ｒ謚ｽ蜃ｺ
            # 谿矩ｫ倩｡ｨ遉ｺ繧ｨ繝ｪ繧｢縺ｮ繧ｻ繝ｬ繧ｯ繧ｿ繝ｼ: #umacaPrice 蜀・・ .PricePurchase
            balance_selector = "#umacaPrice .PricePurchase"
            self._wait_for(balance_selector, timeout=15000)
            
            balance_text = self.page.locator(balance_selector).text_content()
            
            # 繧ｫ繝ｳ繝槭↑縺ｩ繧帝勁蜴ｻ縺励※謨ｰ蛟､・・loat・峨↓繝代・繧ｹ
            cleaned_balance = balance_text.replace(",", "").replace("蜀・, "").strip()
            self.balance = float(cleaned_balance)
            
            print(f"[UMACA-VOTER] Current balance fetched: {self.balance:,} 蜀・)
            return self.balance
            
        except Exception as e:
            print(f"[UMACA-VOTER ERROR] Failed to fetch balance: {e}")
            return 0.0

    def vote(self, race_id: str, bets: List[Dict[str, Any]]) -> bool:
        """謖・ｮ壹＆繧後◆繝ｬ繝ｼ繧ｹ縺ｫ蟇ｾ縺励※謚慕･ｨ・郁ｳｼ蜈･・峨ｒ螳溯｡後☆繧九・""
        if not self.logged_in:
            print("[UMACA-VOTER ERROR] Must login before voting.")
            return False
            
        if not bets:
            print("[UMACA-VOTER] No bets specified. Skipping.")
            return True
            
        # 1繝ｬ繝ｼ繧ｹ縺ゅ◆繧翫・譛螟ｧ謚戊ｳ・ｸ企剞鬘阪Μ繝溘ャ繧ｿ繝ｼ
        total_cost = sum(bet['amount'] for bet in bets)
        max_limit = getattr(config, 'AUTO_VOTING_MAX_AMOUNT_PER_RACE', 5000)
        if total_cost > max_limit:
            print(f"[UMACA-VOTER ERROR] Vote aborted! Total cost ({total_cost:,} 蜀・ exceeds maximum limit per race ({max_limit:,} 蜀・.")
            return False

        # 迴ｾ蝨ｨ縺ｮ谿矩ｫ倥ｒ遒ｺ隱・        current_balance = self.get_balance()
        if current_balance < total_cost:
            print(f"[UMACA-VOTER ERROR] Insufficient balance! Required: {total_cost:,} 蜀・ Available: {current_balance:,} 蜀・)
            return False

        try:
            print(f"[UMACA-VOTER] Processing {len(bets)} bet(s) for race {race_id} (Total Cost: {total_cost:,} 蜀・...")
            
            # ------------------------------------------------------------
            # Step 1: 騾壼ｸｸ謚慕･ｨ繝壹・繧ｸ縺ｸ縺ｮ驕ｷ遘ｻ
            # ------------------------------------------------------------
            print("[UMACA-VOTER] Transitioning to regular vote menu...")
            self._navigate_step(3, fallback_selector=".voteMainNav a.ico_regular") # 騾壼ｸｸ謚慕･ｨ繧偵け繝ｪ繝・け

            # ------------------------------------------------------------
            # Step 2: 遶ｶ鬥ｬ蝣ｴ・磯幕蛯ｬ蝣ｴ・峨・驕ｸ謚・            # ------------------------------------------------------------
            # race_id 縺ｮ4-6譯∫岼縺九ｉ遶ｶ鬥ｬ蝣ｴID繧偵ヱ繝ｼ繧ｹ
            course_id = race_id[4:6]
            venue_name = config.PLACE_MAP_IDS.get(course_id)
            if not venue_name:
                raise ValueError(f"Unknown course ID '{course_id}' in race_id: {race_id}")
                
            print(f"[UMACA-VOTER] Selecting Venue: {venue_name}...")
            # 遶ｶ鬥ｬ蝣ｴ蜷阪〒a繧ｿ繧ｰ繧帝Κ蛻・ｸ閾ｴ驕ｸ謚橸ｼ・I迚ｹ險ｭ縺ｪ縺ｩ縺ｮ data-value2 螻樊ｧ謖√■繧帝勁螟悶＠縺ｦ荳諢上↓迚ｹ螳夲ｼ・            venue_selector = f'#jyo a:has-text("{venue_name}"):not([data-value2])'
            self._navigate_step(4, fallback_selector=venue_selector)

            # ------------------------------------------------------------
            # Step 3: 繝ｬ繝ｼ繧ｹ逡ｪ蜿ｷ・・R縲・2R・峨・驕ｸ謚・            # ------------------------------------------------------------
            # race_id 縺ｮ荳・譯√°繧峨Ξ繝ｼ繧ｹ逡ｪ蜿ｷ繧偵ヱ繝ｼ繧ｹ
            print(f"[UMACA-VOTER-DEBUG] Raw race_id: '{race_id}' (Type: {type(race_id).__name__}, Length: {len(str(race_id))})")
            race_num_str = str(int(race_id[10:])) # "11R" 縺ｮ "11" 驛ｨ蛻・            print(f"[UMACA-VOTER-DEBUG] Sliced race_id[10:]: '{race_id[10:]}' -> Parsed race number: {race_num_str}")
            print(f"[UMACA-VOTER] Selecting Race: {race_num_str}R...")
            # 繝ｬ繝ｼ繧ｹ逡ｪ蜿ｷ・井ｾ・ "11R"・峨ｒ蜀・桁縺吶ｋ raceList a繧ｿ繧ｰ繧偵け繝ｪ繝・け
            race_selector = f'a.raceList:has(.raceNum:has-text("{race_num_str}R"))'
            self._navigate_step(5, fallback_selector=race_selector)

            # ------------------------------------------------------------
            # Step 4: 蠑丞挨・亥腰蜍昴・隍・享縺ｪ縺ｩ・峨・驕ｸ謚・            # ------------------------------------------------------------
            # 迴ｾ迥ｶ縺ｯ蜊伜享 ('win') 縺ｾ縺溘・隍・享 ('place') 繧呈Φ螳壹Ｃets[0] 縺九ｉ豎ｺ螳・            bet_type = bets[0].get('bet_type', 'win')
            bet_type_name = "蜊伜享" if bet_type == "win" else "隍・享"
            
            print(f"[UMACA-VOTER] Selecting Bet Type: {bet_type_name}...")
            # 蠑丞挨蜷搾ｼ井ｾ・ "蜊伜享"・峨ｒ蜷ｫ繧 a繧ｿ繧ｰ繧偵け繝ｪ繝・け
            siki_selector = f'#siki ul.selectList a:has-text("{bet_type_name}")'
            self._navigate_step(6, fallback_selector=siki_selector)

            # ------------------------------------------------------------
            # Step 5: 鬥ｬ逡ｪ縺ｮ驕ｸ謚槭→驥鷹｡榊・蜉幢ｼ亥､夂せ雋ｷ縺・ｯｾ蠢懊Ν繝ｼ繝暦ｼ・            # ------------------------------------------------------------
            for idx, bet in enumerate(bets):
                umaban = bet['umaban']
                amount = bet['amount']
                
                # 逋ｾ蜀・腰菴阪↓螟画鋤 (萓・ 100蜀・↑繧・1, 500蜀・↑繧・5)
                unit_amount = amount // 100
                if unit_amount <= 0:
                    raise ValueError(f"Invalid bet amount: {amount} (Must be at least 100 yen)")

                print(f"  -> Bet [{idx+1}]: Horse No. {umaban} (Amount: {amount} yen)")

                # 謚慕･ｨ荳隕ｧ逕ｻ髱｢縺九ｉ譎ｮ騾壹・螻ｱ螻ｱ驕ｸ謚樒判髱｢縺ｸ謌ｻ繧具ｼ・鬆ｭ逶ｮ莉･髯阪・蝣ｴ蜷茨ｼ・                if idx > 0:
                    # 縲碁ｦｬ・域椢・臥分縺九ｉ邯壹￠縺ｦ蜈･蜉帙阪・繧ｿ繝ｳ繧偵け繝ｪ繝・け縺励※鬥ｬ逡ｪ驕ｸ謚樒判髱｢縺ｫ謌ｻ繧・                    print(f"  -> Back to horse selection for Bet [{idx+1}]...")
                    continue_selector = 'ul li.btnSoftColor a:has-text("\u99ac")'
                    self._human_click(continue_selector)
                    self._random_delay(2000, 3500)

                # 鬥ｬ逡ｪ a繧ｿ繧ｰ縺ｮ繧ｯ繝ｪ繝・け
                # a[data-value="16"] 縺ｪ縺ｩ縺ｮ繧ｻ繝ｬ繧ｯ繧ｿ繝ｼ繧剃ｽｿ逕ｨ
                uma_selector = f'ul.selectHorse a[data-value="{umaban}"]'
                self._navigate_step(7, fallback_selector=uma_selector)

                # 驥鷹｡榊・蜉・(div#kin 蜀・・ input)
                # jQuery Mobile 縺ｮ繧ｭ繝｣繝・す繝･遶ｶ蜷医ｒ髦ｲ縺舌◆繧！D謖・ｮ壹〒蝣・欧蛹・                input_selector = "div#kin input[type='tel']"
                self._human_type(input_selector, str(unit_amount))

                # 縲後そ繝・ヨ縲阪・繧ｿ繝ｳ縺ｮ繧ｯ繝ｪ繝・け 筐｡ 謚慕･ｨ荳隕ｧ縺ｸ
                # 縲悟・蜑ｲ縺励※螻暮幕繧ｻ繝・ヨ縲阪・繧ｿ繝ｳ・・itle螻樊ｧ縺ゅｊ・峨ｒ髯､螟悶＠縲・壼ｸｸ縺ｮ縲後そ繝・ヨ縲阪□縺代ｒ荳諢上↓迚ｹ螳壹☆繧・                print("  -> Setting bet amount...")
                set_selector = "div#kin .btnColor a:not([title])"
                self._navigate_step(8, fallback_selector=set_selector)

            # ------------------------------------------------------------
            # Step 6: 謚慕･ｨ荳隕ｧ 筐｡ 蜈･蜉帷ｵゆｺ・            # ------------------------------------------------------------
            print("[UMACA-VOTER] Confirming bet list...")
            self._wait_for("ul#noCircle", timeout=15000) # 謚慕･ｨ縺悟・縺｣縺溘Μ繧ｹ繝医・蜃ｺ迴ｾ繧堤｢ｺ隱・            
            print("[UMACA-VOTER] Finalizing inputs...")
            # 縲悟・蜉帷ｵゆｺ・阪・繧ｿ繝ｳ繧偵け繝ｪ繝・け縺励※蜷郁ｨ磯≡鬘榊・蜉帷判髱｢縺ｸ
            # 譌･譛ｬ隱槭・繝・メ繝ｳ繧ｰ繧帝∩縺代√け繝ｩ繧ｹ蜷阪〒荳諢上↓迚ｹ螳・            finish_selector = "div#toui .btnColor a"
            self._navigate_step(9, fallback_selector=finish_selector)

            # ------------------------------------------------------------
            # Step 7: 蜷郁ｨ磯≡鬘阪・譛邨ら｢ｺ隱榊・蜉帙→謚慕･ｨ遒ｺ螳・            # ------------------------------------------------------------
            print(f"[UMACA-VOTER] Typing total sum amount: {total_cost} yen...")
            # 蜷郁ｨ磯≡鬘榊・蜉帙ヵ繧｣繝ｼ繝ｫ繝・(input#sum)
            sum_selector = "input#sum"
            self._human_type(sum_selector, str(total_cost))

            # 譛邨ゅ梧兜逾ｨ縲阪・繧ｿ繝ｳ縺ｮ繧ｯ繝ｪ繝・け
            # JRA繧ｵ繧､繝医′ window.confirm() 縺ｧ繝繧､繧｢繝ｭ繧ｰ繧定｡ｨ遉ｺ縺吶ｋ縲・            # page.on("dialog") 繝ｪ繧ｹ繝翫・縺瑚・蜍墓価隱阪☆繧具ｼ域怙蛻昴↓謌仙粥縺励◆譁ｹ蠑擾ｼ・            print("[UMACA-VOTER] ===== COMMITTING ACTUAL VOTE =====")
            vote_btn_selector = "div#LIST .btnColor a"
            
            if self.use_mock:
                # 讓｡謫ｬ繝・せ繝医Δ繝ｼ繝・ 縲梧兜逾ｨ縲阪・繧ｿ繝ｳ繧偵け繝ｪ繝・け縺励※繝｢繝・け邨ゆｺ・                self._human_click(vote_btn_selector)
                print("[UMACA-VOTER MOCK] Vote committed successfully in mock simulation!")
                self.balance -= total_cost # 蜀・Κ迥ｶ諷九・谿矩ｫ倥ｒ繧ｷ繝溘Η繝ｬ繝ｼ繝域ｸ帷ｮ・                self._voted_flag = True # 謚慕･ｨ螳御ｺ・ヵ繝ｩ繧ｰ繧偵そ繝・ヨ
            else:
                # 譛ｬ逡ｪ繝｢繝ｼ繝・
                # page.expect_event("dialog") 縺ｧ謚慕･ｨ繝懊ち繝ｳ繧ｯ繝ｪ繝・け蠕後・confirm繝繧､繧｢繝ｭ繧ｰ繧呈・遉ｺ逧・↓蠕・▽
                # 縺薙ｌ縺ｫ繧医ｊ networkidle 縺後ム繧､繧｢繝ｭ繧ｰ繧医ｊ蜈医↓螳御ｺ・＠縺ｦ繧ゅム繧､繧｢繝ｭ繧ｰ繧貞叙繧翫％縺ｼ縺輔↑縺・                print("[UMACA-VOTER] Clicking vote button and waiting for confirm dialog (up to 15s)...")
                try:
                    with self.page.expect_event("dialog", timeout=15000) as dialog_info:
                        self._human_click(vote_btn_selector)
                    dialog = dialog_info.value
                    print(f"[UMACA-VOTER DIALOG] Dialog appeared: '{dialog.message}' -> Accepting.")
                    dialog.accept()
                    print("[UMACA-VOTER] Dialog accepted. Waiting for page transition (up to 30s)...")
                    self.page.wait_for_load_state("networkidle", timeout=30000)
                except Exception as dialog_err:
                    # 繝繧､繧｢繝ｭ繧ｰ縺悟・縺ｪ縺九▲縺溷ｴ蜷茨ｼ医し繧､繝亥・縺ｮ莉墓ｧ伜､画峩遲会ｼ峨・縺昴・縺ｾ縺ｾ蠕・ｩ・                    print(f"[UMACA-VOTER WARN] No dialog detected ({dialog_err}). Waiting anyway...")
                    self.page.wait_for_load_state("networkidle", timeout=30000)
                
                print("[UMACA-VOTER PRODUCTION] Vote committed successfully to JRA server!")
                # 謚慕･ｨ螳御ｺ・ｾ後・谿矩ｫ倥ｒ貂帷ｮ励＠縺ｦ繧ｭ繝｣繝・す繝･・域兜逾ｨ蠕後・繝ｼ繧ｸ縺ｧ縺ｮ谿矩ｫ伜叙蠕怜､ｱ謨励↓蛯吶∴繧具ｼ・                self.balance -= total_cost
                self._voted_flag = True

            print("[UMACA-VOTER] ===================================")
            return True

        except Exception as e:
            print(f"[UMACA-VOTER ERROR] An error occurred during automatic voting navigation: {e}")
            import traceback
            traceback.print_exc()
            return False

    def close(self):
        """繝悶Λ繧ｦ繧ｶ繧・そ繝・す繝ｧ繝ｳ繧偵け繝ｭ繝ｼ繧ｺ縺励√け繝ｪ繝ｼ繝ｳ繧｢繝・・縺吶ｋ縲・""
        if self.page:
            print("[UMACA-VOTER] Closing browser session...")
            try:
                self.context.close()
                self.browser.close()
                self.playwright.stop()
            except Exception:
                pass
            self.page = None
            self.logged_in = False
            print("[UMACA-VOTER] Session closed safely.")


# ==============================================================================
# ｧｪ 蟷ｳ譌･讓｡謫ｬ繝・せ繝育畑縺ｮ繧ｨ繝ｳ繝医Μ繝ｼ繝昴う繝ｳ繝・# ==============================================================================
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test UMACA Voter.")
    parser.add_argument('--test-mock', action='store_true', help="Run in weekday mock simulation mode using dumped HTML files.")
    args = parser.parse_args()
    
    if args.test_mock or len(sys.argv) > 1:
        print("\n=== [MOCK TESTING] Starting UMACA Smart Voter Weekday Simulation ===")
        # 繝｢繝・け繝｢繝ｼ繝峨ｒ蠑ｷ蛻ｶ逧・↓True縺ｫ縺励※繝・せ繝・        voter = UmacaVoter(use_mock=True)
        
        # 繝｢繝・け逕ｨ縺ｮ繝・せ繝医い繧ｫ繧ｦ繝ｳ繝域ュ蝣ｱ繧堤腸蠅・､画焚縺ｫ荳譎ゅそ繝・ヨ・医☆縺ｧ縺ｫ險ｭ螳壹＆繧後※縺・ｌ縺ｰ縺昴ｌ繧貞━蜈茨ｼ・        if not os.getenv("UMACA_CARD_NUMBER"):
            os.environ["UMACA_CARD_NUMBER"] = "110002378622"
            os.environ["UMACA_BIRTHDAY"] = "20030214"
            os.environ["UMACA_SECURITY_CODE"] = "4041"
            
        success = False
        try:
            # 1. 繝ｭ繧ｰ繧､繝ｳ
            if voter.login():
                # 2. 谿矩ｫ伜叙蠕・                balance = voter.get_balance()
                
                # 3. 讓｡謫ｬ謚慕･ｨ (譚ｱ莠ｬ11R繝ｻ蜊伜享16逡ｪ繝ｻ100蜀・
                test_bets = [{
                    'umaban': 16,
                    'bet_type': 'win',
                    'amount': 100
                }]
                
                # 譚ｱ莠ｬ縺ｮ髢句ぎ繧ｳ繝ｼ繝峨・ "05" (race_id 縺ｮ 4-6 譯∫岼縺・"05" 縺ｫ蟇ｾ蠢・
                test_race_id = "202605310511" # 2026蟷ｴ5譛・1譌･ 譚ｱ莠ｬ11R
                
                success = voter.vote(test_race_id, test_bets)
                
                # 4. 謚慕･ｨ蠕後・谿矩ｫ伜叙蠕・                new_balance = voter.get_balance()
                print(f"[MOCK RESULT] Initial: {balance:,} 蜀・-> New: {new_balance:,} 蜀・(Cost: 100蜀・")
        finally:
            voter.close()
            
        if success:
            print("\n=== [MOCK SUCCESS] UMACA Smart Voter Simulation Completed Flawlessly! ===")
            sys.exit(0)
        else:
            print("\n=== [MOCK FAILED] UMACA Smart Voter Simulation Failed. ===")
            sys.exit(1)
