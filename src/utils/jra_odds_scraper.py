"""
JRA リアルタイム単勝オッズ スクレイパー

【概要】
JRA公式サイトから指定した開催場・レース番号の単勝オッズをリアルタイムに取得し、
CSVファイルとして保存するスクリプトです。Seleniumを使用して動的なページ遷移を行います。

【使い方: コマンドラインから実行する場合】
python code/utils/jra_odds_scraper.py --venue [開催場] --race [レース番号] [--date [日付(YYYY-MM-DD)]] [--headless]

例:
# 本日の東京11Rのオッズを取得（バックグラウンドで実行）
python code/utils/jra_odds_scraper.py --venue 東京 --race 11 --headless

# 日付を指定して京都11Rのオッズを取得（ブラウザ画面を表示しながら実行）
python code/utils/jra_odds_scraper.py --venue 京都 --race 11 --date 2026-02-21

【使い方: 他のPythonスクリプトから呼び出す場合】
from utils.jra_odds_scraper import JRAOddsScraper

scraper = JRAOddsScraper(headless=True)
try:
    # 開催場とレース番号を指定。dateを指定しない場合は実行日当日が対象となります。
    df_odds = scraper.get_odds(venue_name="東京", race_number=11)
    print(df_odds)
finally:
    scraper.close()
"""
import os
import sys
import time
import pandas as pd
import argparse
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup

# Add project root to path
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)

class JRAOddsScraper:
    def __init__(self, headless=True):
        self.driver = self._setup_driver(headless)
        self.wait = WebDriverWait(self.driver, 10)

    def _setup_driver(self, headless):
        options = Options()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-renderer-backgrounding')
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Suppress logging
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        options.add_argument('--log-level=3')
        
        try:
            service = Service(ChromeDriverManager().install())
        except Exception:
            service = Service() # Expecting chromedriver in PATH

        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)  # ページ読み込みタイムアウトを30秒に緩和して安定化
        return driver

    def close(self):
        if self.driver:
            self.driver.quit()

    def get_odds(self, venue_name, race_number, target_date=None):
        """
        Navigates to the odds page for the specified venue and race.
        target_date: YYYY-MM-DD string or datetime object. Used to match (土)/(日).
        Returns a DataFrame with odds data.
        """
        
        # Determine target date string (YYYYMMDD) and weekday if date is provided
        target_date_str = None
        target_weekday_str = None
        weekday_map = {0: "月", 1: "火", 2: "水", 3: "木", 4: "金", 5: "土", 6: "日"}
        
        # If target_date is not provided, default to today
        if not target_date:
            target_date = datetime.now()
            
        if target_date:
            if isinstance(target_date, str):
                dt = datetime.strptime(target_date, "%Y-%m-%d")
            else:
                dt = target_date
            target_date_str = dt.strftime("%Y%m%d")
            target_weekday_str = f"({weekday_map[dt.weekday()]})"
            print(f"Targeting: {target_date_str} {target_weekday_str}")

        try:
            # 1. Access Top Page
            print("Accessing JRA Top Page...")
            self.driver.get("https://www.jra.go.jp/")
            time.sleep(2)
            
            # Click Odds menu using JS
            print("Navigating to Odds menu...")
            self.driver.execute_script("doAction('/JRADB/accessO.html','pw15oli00/6D');")
            
            # 2. Wait for the venue list area
            self.wait.until(EC.presence_of_element_located((By.ID, "main")))
            
            # Match venue links based on venue name AND date/weekday (if provided)
            # Example text: "1回東京5日(土)", "1回東京6日(日)"
            # Example onclick: "return doSearch('05', '20260215');"
            venue_links = self.driver.find_elements(By.CSS_SELECTOR, "#main a")
            candidate_links = []
            print("--- Available Venue Links ---")
            for link in venue_links:
                link_text = link.text.strip()
                onclick = link.get_attribute("onclick") or ""
                print(f"Found: '{link_text}' | OnClick: {onclick[:40]}...")
                
                # Check venue name (e.g. "東京")
                if venue_name in link_text:
                    score = 0
                    # 1. Exact date match in onclick is strongest (e.g. "20260215")
                    if target_date_str and target_date_str in onclick:
                        score = 200
                        print(f"  -> Exact date match found ({target_date_str}) in onclick!")
                    # 2. Weekday match in text is secondary (e.g. "(日)")
                    elif target_weekday_str and target_weekday_str in link_text:
                        score = 100
                        print(f"  -> Weekday match found ({target_weekday_str}) in text.")
                    
                    # Store as (score, link)
                    candidate_links.append((score, link))
            
            if not candidate_links:
                raise ValueError(f"Venue '{venue_name}' not found in current active venues.")
            
            # Sort by score descending. 
            # If scores are tied (e.g. date not provided or no exact match), pick the earliest day
            # (as usually we want today's races, not tomorrow's if we run on Saturday and both are active)
            def get_day_num(l):
                import re
                m = re.search(r'(\d+)日', l.text)
                return int(m.group(1)) if m else 99

            candidate_links.sort(key=lambda x: (x[0], -get_day_num(x[1])), reverse=True)
            
            target_venue_link = candidate_links[0][1]
            print(f"Selected Venue: '{target_venue_link.text.strip()}' (Match Score: {candidate_links[0][0]})")
            
            target_venue_link.click()
            time.sleep(2)

            # 4. Select Race Number
            print(f"Selecting Race: {race_number}R...")
            # Usually buttons like "1R", "2R"...
            # Selector might be .raceNum or similar.
            
            # Identify the button for the specific race number
            # Common pattern: an image with alt="1R" or text "1R"
            
            # Try to find a link with text matching "{race_number}R"
            try:
                # Try finding by alt text (common for JRA images: "11レース")
                race_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, f"//img[contains(@alt, '{race_number}レース')]/..")))
                print(f"Found race button for {race_number}R via alt text.")
                race_btn.click()
            except:
                 print(f"Could not find race button by alt '{race_number}レース'. Trying generic text...")
                 try:
                    race_btn = self.driver.find_element(By.XPATH, f"//a[contains(text(), '{race_number}R')]")
                    race_btn.click()
                 except:
                    print("Could not find race button by text either. Trying JS fallback...")
                    # Fallback: finding by alt and executing JS
                    try:
                        img = self.driver.find_element(By.XPATH, f"//img[contains(@alt, '{race_number}レース')]")
                        link = img.find_element(By.XPATH, "./..")
                        onclick_js = link.get_attribute("onclick")
                        if onclick_js:
                            print(f"Executing race selection JS: {onclick_js}")
                            self.driver.execute_script(onclick_js)
                        else:
                            raise Exception("Race link found but no onclick.")
                    except Exception as e2:
                        print(f"Race selection failed: {e2}")
                        raise
                
            time.sleep(2)
            
            # 5. Select "Win/Place" (単勝・複勝) if not already selected
            # JRA default might be Win/Place, but good to ensure.
            # Usually a tab or button "単勝・複勝"
            
            # Check if we are on the right view. If we see a table with "単勝", we are good.
            if "単勝" not in self.driver.page_source:
                print("Switching to Win/Place view...")
                win_place_link = self.driver.find_element(By.XPATH, "//a[contains(text(), '単勝') or contains(@alt, '単勝')]")
                win_place_link.click()
                time.sleep(2)

            # 6. Extract Data
            print("Extracting Odds data...")
            return self._parse_odds_table()

        except Exception as e:
            print(f"Error during scraping: {e}")
            with open("debug_error.txt", "w", encoding="utf-8") as f:
                f.write(str(e))
            # Dump source for debugging
            with open(os.path.join(PROJECT_ROOT, "debug_jra_error.html"), "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            return None

    def _parse_odds_table(self):
        """
        Parses the odds table using BeautifulSoup.
        """
        try:
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Find the odds table
            # Based on debug html, it has class "tanpuku"
            table = soup.find('table', class_='tanpuku')
            if not table:
                print("Could not find table with class 'tanpuku'. Searching for any table with '馬番'...")
                # Fallback search
                for t in soup.find_all('table'):
                    if '馬番' in t.get_text() and '単勝' in t.get_text():
                        table = t
                        break
            
            if not table:
                print("No suitable odds table found.")
                return None

            data = []
            rows = table.find_all('tr')
            
            print(f"Found {len(rows)} rows in table.")
            
            for row in rows:
                # We expect cells with class "num" (馬番) and "odds_tan" (単勝)
                num_cell = row.find('td', class_='num')
                odds_cell = row.find('td', class_='odds_tan')
                name_cell = row.find('td', class_='horse')
                
                if num_cell and odds_cell:
                    horse_num = num_cell.get_text(strip=True)
                    win_odds = odds_cell.get_text(strip=True)
                    horse_name = name_cell.get_text(strip=True) if name_cell else ""
                    
                    # Handle cases where odds might be non-numeric or empty
                    if horse_num.isdigit():
                         data.append({
                             '馬番': int(horse_num),
                             '馬名': horse_name,
                             '単勝': win_odds
                         })
            
            if not data:
                print("No data extracted from table rows.")
                return None
                
            df = pd.DataFrame(data)
            
            # Clean data (convert odds to numeric if possible, but keep as string for now to match request? No, usually float)
            # But "3.4" is string in extraction.
            # Let's clean it.
            # Convert '単勝' to numeric, forcing errors to NaN (for cancelled/scratch)
            # But wait, JRA uses '---' or similar for cancelled.
            
            return df
            
        except Exception as e:
            print(f"Error parsing odds table: {e}")
            return None

    def refresh_odds(self):
        """
        Refreshes the current page and parses the odds table again.
        Used for high-frequency logs without restarting browser or navigating.
        """
        try:
            print("Refreshing JRA odds page...")
            self.driver.refresh()
            time.sleep(2)
            # Wait for table to be loaded
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "tanpuku")))
            return self._parse_odds_table()
        except Exception as e:
            print(f"Error refreshing page: {e}")
            return None

def main():
    parser = argparse.ArgumentParser(description="JRA Odds Scraper")
    parser.add_argument('--venue', type=str, required=True, help='Venue name (e.g., 東京)')
    parser.add_argument('--race', type=int, required=True, help='Race number (e.g., 11)')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD)')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    
    args = parser.parse_args()
    
    scraper = JRAOddsScraper(headless=args.headless)
    try:
        df = scraper.get_odds(args.venue, args.race, target_date=args.date)
        if df is not None:
            print("\n--- Scraped Odds ---")
            print(df)
            
            # Save
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"jra_odds_{timestamp}_{args.venue}_{args.race}R.csv"
            save_path = os.path.join(PROJECT_ROOT, "data", "odds", filename)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            df.to_csv(save_path, index=False, encoding='utf-8-sig')
            print(f"\nSaved to: {save_path}")
        else:
            print("Failed to retrieve odds.")
            
    finally:
        scraper.close()

if __name__ == "__main__":
    main()
