# C:\keibaAI\code\a1_data_collection\m00_get_race_schedule.py

"""
netkeiba.comから指定された日付のレーススケジュール（全レースのrace_idと発走時刻）
を取得するスクリプト。
実績のあるSeleniumベースのコードを元に、プロジェクト仕様に合わせて関数化。

■ 主な処理
1. Selenium WebDriverを起動し、指定された日付のレース一覧ページにアクセスする。
2. JavaScriptの実行が完了し、レース情報が表示されるまで待機する。
3. 完全にレンダリングされた後のHTMLソースから、各レースのrace_idと発走時刻を抽出。
4. 抽出した情報をpandas DataFrameにまとめて返す。

■ 使い方
- 初回実行前にライブラリのインストールが必要:
  pip install selenium webdriver-manager
- 他のスクリプトから:
  from src.a1_data_collection.m00_get_race_schedule import get_race_schedule_for_date
- 単体でデバッグ実行:
  python src/a1_data_collection/m00_get_race_schedule.py [YYYY-MM-DD]
"""

import sys
import os
import pandas as pd
import re
import json
from datetime import datetime, date
import time
import logging

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
# ---

CACHE_DIR = os.path.join(PROJECT_ROOT, 'cache')

# --- Selenium関連のインポート --
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Seleniumのドライバマネージャのログを抑制
logging.getLogger('WDM').setLevel(logging.WARNING)

TARGET_URL_TEMPLATE = "https://race.netkeiba.com/top/race_list.html?kaisai_date={}"

def setup_driver() -> webdriver.Chrome:
    """Selenium WebDriverをセットアップする（先輩のコードを参考）"""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu') # GPU無効化
    options.add_argument('--window-size=1920,1080') # ウィンドウサイズ固定
    options.add_argument('--disable-extensions')
    options.page_load_strategy = 'eager' # 画像などの読み込みを待たない
    options.add_argument('--log-level=3')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    # User-Agentを設定してBot判定を回避
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # webdriver-manager を利用してchromedriverを自動管理
    # webdriver-manager を利用してchromedriverを自動管理
    try:
        service = Service(ChromeDriverManager().install())
    except Exception as e:
        print(f"Warning: Failed to install/update chromedriver ({e}). Trying to use default 'chromedriver' in system PATH.")
        service = Service() # Try default (expects chromedriver in PATH)

    driver = webdriver.Chrome(service=service, options=options)
    
    # タイムアウト設定 (読み込み最大30秒)
    driver.set_page_load_timeout(30)
    return driver

def get_race_schedule_for_date(target_date_str: str = None, force_reload: bool = False) -> pd.DataFrame | None:
    """
    指定された日付（YYYY-MM-DD形式）のレーススケジュールを取得する。
    force_reload: Trueの場合、既存のキャッシュファイルがあっても無視して再取得(上書き)する。
    """
    # 入力の型チェックと変換
    if target_date_str is None:
        target_date = date.today()
    elif isinstance(target_date_str, (datetime, date)):
        target_date = target_date_str
    elif isinstance(target_date_str, str):
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError:
            try:
                print(f"[ERROR] Invalid date format: {target_date_str}. Please use YYYY-MM-DD.")
            except Exception:
                pass
            return None
    else:
        try:
            print(f"[ERROR] Invalid argument type: {type(target_date_str)}")
        except Exception:
            pass
        return None

    target_date_formatted = target_date.strftime('%Y%m%d')
    # Use 'races' subdirectory
    cache_subdir = os.path.join(CACHE_DIR, 'races')
    if not os.path.exists(cache_subdir):
        os.makedirs(cache_subdir)
    cache_path = os.path.join(cache_subdir, f"races_{target_date_formatted}.csv")
    
    # キャッシュチェック (force_reload=Trueならスキップ)
    if not force_reload and os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path, encoding='utf-8')
            # race_idなどは文字列として扱うべき
            df['race_id'] = df['race_id'].astype(str)
            df['race_number'] = df['race_number'].astype(str)
            print(f"[INFO] Loaded race schedule from cache: {cache_path}")
            return df
        except Exception as e:
            print(f"[WARN] Failed to load cache: {e}")

    target_url = TARGET_URL_TEMPLATE.format(target_date_formatted)
    
    # Retry mechanism for robustness
    max_retries = 3
    for attempt in range(max_retries):
        driver = None
        all_races = []
        try:
            # 2回目以降は少し待機
            if attempt > 0:
                print(f"--- Retrying... (Attempt {attempt+1}/{max_retries}) ---")
                time.sleep(5)

            try:
                print(f"--- [START] Fetching race schedule for {target_date.strftime('%Y-%m-%d')} using Selenium (Attempt {attempt+1}) ---")
            except Exception:
                pass
            
            driver = setup_driver()
            try:
                print(f"-> Accessing target URL: {target_url}")
            except Exception:
                pass
            driver.get(target_url)

            # ページ読み込み待機 (Explicit Wait)
            # .RaceList_DataList が表示されるまで最大10秒待つ
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.RaceList_DataList'))
                )
            except:
                # タイムアウトしても一旦処理を続行（要素がない＝開催なしの可能性があるため）
                pass
            
            # 開催場ごとの情報を取得 (先輩のコードのセレクタを参考)
            race_list_sections = driver.find_elements(By.CSS_SELECTOR, '.RaceList_DataList')

            if not race_list_sections:
                try:
                    print(f"[INFO] No race venues found for {target_date_formatted}.")
                except Exception:
                    pass
                # 開催なしと判断できた場合は、リトライせずに空のDFを返して終了
                # ただし、ページ読み込み失敗の可能性もゼロではないが、構成上判別困難なため空として扱う
                if driver: driver.quit()
                return pd.DataFrame(columns=['race_id', 'start_time', 'venue_name', 'race_number'])

            try:
                print(f"-> Found {len(race_list_sections)} venues.")
            except Exception:
                pass

            for section in race_list_sections:
                # 競馬場名を取得
                title = section.find_element(By.CSS_SELECTOR, '.RaceList_DataTitle').text
                venue_name = title.split()[1]
                
                # 各レースの情報を取得
                race_items = section.find_elements(By.CSS_SELECTOR, '.RaceList_DataItem')
                for item in race_items:
                    # 発走時刻を取得
                    start_time = item.find_element(By.CSS_SELECTOR, '.RaceList_Itemtime').text
                    # レース番号を取得
                    race_number = item.find_element(By.CSS_SELECTOR, '.Race_Num').text.replace('R', '')
                    
                    # レース名を取得
                    try:
                        race_name_element = item.find_element(By.CSS_SELECTOR, '.RaceList_ItemTitle')
                        race_name = race_name_element.text
                    except:
                        race_name = "レース名なし"
                    
                    # グレードを取得 (Icon_GradeTypeクラスを持つ要素を探す)
                    grade = None
                    try:
                        grade_element = item.find_element(By.CSS_SELECTOR, '[class*="Icon_GradeType"]')
                        grade_class = grade_element.get_attribute("class")
                        
                        # Regexで数値を抽出してから厳密に判定
                        match = re.search(r'Icon_GradeType(\d+)', grade_class)
                        if match:
                            grade_id = int(match.group(1))
                            
                            if grade_id == 1: grade = "G1"
                            elif grade_id == 2: grade = "G2"
                            elif grade_id == 3: grade = "G3"
                            elif grade_id == 10: grade = "Jpn1"
                            elif grade_id == 11: grade = "Jpn2"
                            elif grade_id == 12: grade = "Jpn3"
                            elif grade_id == 15: grade = "L"
                            elif grade_id == 16: grade = "OP"
                            elif grade_id == 17: grade = "OP"
                            # 18などは除外 (条件戦など)
                    except:
                        grade = None

                    # race_id を取得 (aタグのhrefから抽出)
                    link_element = item.find_element(By.TAG_NAME, 'a')
                    race_href = link_element.get_attribute('href')
                    
                    race_id_match = re.search(r'race_id=([^&]+)', race_href)
                    if race_id_match:
                        race_id = race_id_match.group(1)
                        
                        all_races.append({
                            'race_id': race_id,
                            'start_time': start_time,
                            'venue_name': venue_name,
                            'race_number': race_number,
                            'race_name': race_name,
                            'grade': grade
                        })
            
            # If successful, break the retry loop
            break

        except Exception as e:
            try:
                print(f"[WARN] An error occurred during scraping (Attempt {attempt+1}/{max_retries}): {e}")
            except Exception:
                pass
            # Clean up driver before retrying
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            driver = None
            if attempt == max_retries - 1:
                print("[FATAL] Max retries reached. Exiting.")
                raise RuntimeError(f"Failed to scrape schedule for {target_date_formatted} after {max_retries} attempts. Check network or chrome driver.")
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

    if not all_races:

        try:
            print(f"[INFO] No valid race schedules could be extracted for {target_date_str}.")
        except Exception:
            pass
        return pd.DataFrame(columns=['race_id', 'start_time', 'venue_name', 'race_number'])

    schedule_df = pd.DataFrame(all_races)
    schedule_df = schedule_df.sort_values('start_time').reset_index(drop=True)
    
    # --- Cache Saving ---
    try:
        cache_subdir = os.path.join(CACHE_DIR, 'races')
        # if not os.path.exists(cache_subdir): os.makedirs(cache_subdir) # Already ensured above
        schedule_df.to_csv(cache_path, index=False, encoding='utf-8')
        print(f"[INFO] Saved race schedule to cache: {cache_path}")
    except Exception as e:
        print(f"[WARN] Failed to save cache: {e}")
    
    try:
        print(f"--- [SUCCESS] Found {len(schedule_df)} races in total. ---")
    except Exception:
        pass
    return schedule_df

def get_monthly_schedule_metadata(year, month, force_reload=False):
    """
    指定された年月の開催スケジュール（日付と開催場のリスト）を取得する
    Returns: {date_obj: ['東京', '京都'], ...}
    force_reload: Trueの場合、キャッシュを無視して再取得する
    """
    cache_subdir = os.path.join(CACHE_DIR, 'schedule')
    if not os.path.exists(cache_subdir):
        os.makedirs(cache_subdir)
    cache_path = os.path.join(cache_subdir, f"schedule_{year}_{month:02d}.json")
    
    # 1. キャッシュ確認
    if not force_reload and os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 文字列キーをdateオブジェクトに変換
            calendar_data = {datetime.strptime(k, '%Y-%m-%d').date(): v for k, v in data.items()}
            print(f"[INFO] Loaded monthly schedule from cache: {cache_path}")
            return calendar_data
        except Exception as e:
            print(f"[WARN] Failed to load cache: {e}")

    # 既存のsetup_driverがあればそれを使用
    driver = setup_driver() 
    url = f"https://race.netkeiba.com/top/calendar.html?year={year}&month={month}"
    
    calendar_data = {}
    try:
        driver.get(url)
        time.sleep(2) # 待機
        
        # カレンダーのセルを取得
        cells = driver.find_elements(By.XPATH, "//table[contains(@class, 'Calendar_Table')]//td")
        
        for cell in cells:
            try:
                # 日付 (class="Day")
                day_elements = cell.find_elements(By.CLASS_NAME, "Day")
                if not day_elements: continue
                day_text = day_elements[0].text.strip()
                if not day_text.isdigit(): continue
                
                current_date = date(year, month, int(day_text))
                
                # 開催場 (class="JyoName")
                venue_elements = cell.find_elements(By.CLASS_NAME, "JyoName")
                venues = [v.text.strip() for v in venue_elements if v.text.strip()]
                
                if venues:
                    calendar_data[current_date] = venues
            except Exception:
                continue
    except Exception as e:
        try:
            print(f"[ERROR] Calendar scrape failed: {e}")
        except Exception:
            pass
    finally:
        driver.quit()
        
    # --- Cache Saving ---
    try:
        # cache_subdir created above
        # dateキーを文字列に変換して保存
        save_data = {k.strftime('%Y-%m-%d'): v for k, v in calendar_data.items()}
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Saved monthly schedule to cache: {cache_path}")
    except Exception as e:
        print(f"[WARN] Failed to save cache: {e}")

    return calendar_data

if __name__ == '__main__':
    target_date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    schedule = get_race_schedule_for_date(target_date_arg)
    if schedule is not None:
        if schedule.empty:
            try:
                print("\nNo races scheduled for the target date.")
            except Exception:
                pass
        else:
            try:
                print("\n>>> Race Schedule:")
                print(schedule)
            except Exception:
                pass
