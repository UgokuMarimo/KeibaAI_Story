# C:\KeibaAI\code\utils\scraper.py

"""
スクレイピングユーティリティ (scraper.py)

■ 役割
netkeiba.com からレース情報や馬の過去戦績データを取得するための関数群を提供するモジュール。
主に `m04_predict.py` や `app.py` から呼び出されて使用される。

■ 主な機能
1. `scrape_shutuba_table(race_id)`:
   - 指定されたレースIDの出馬表（馬番、馬名、騎手、オッズなど）をスクレイピングする。
   - リアルタイムなオッズや馬体重の取得に使用。

2. `load_past_race_data(horse_ids)`:
   - ローカルに保存されたCSVファイル（`data/YYYY.csv`）から、指定された馬の過去走データを読み込む。
   - 高速化のために使用される（スクレイピング不要）。

3. `load_past_race_data_with_overseas(...)`:
   - 指定された馬の過去走データを取得する。
   - オプションにより、各馬の個別ページをスクレイピングして、最新のデータや地方・海外レースのデータも含めることができる。
   - 取得した地方・海外データはキャッシュ（`data/kaigai/`, `data/tihou/`）に保存される。

"""
import requests
from bs4 import BeautifulSoup
import time, re, os, sys
import pandas as pd
import numpy as np
from typing import Optional, List
from tqdm import tqdm

_current_dir = os.path.dirname(os.path.abspath(__file__)); PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..')); sys.path.append(PROJECT_ROOT); sys.path.append(os.path.join(PROJECT_ROOT, 'src'))
import config

REQUEST_WAIT_TIME = 0.3
def safe_get_text(element, strip=True): return element.get_text(strip=True) if element else ""
def to_numeric_or_nan(value):
    if value is None or str(value).strip() in ['', '**', '--', '---.-']: return np.nan
    try:
        cleaned_value = re.sub(r'[^\d.-]', '', str(value))
        if cleaned_value in ['.', '-', '']: return np.nan
        return float(cleaned_value)
    except (ValueError, TypeError): return np.nan

def get_db_connection():
    from dotenv import load_dotenv
    try:
        import pymysql
    except ImportError:
        print("[WARN] pymysql is not installed. Database connection disabled (falling back to scraping).")
        return None
    load_dotenv(os.path.join(PROJECT_ROOT, '.env'))
    host = os.getenv("DB_HOST", "").strip()
    port_str = os.getenv("DB_PORT", "").strip()
    user = os.getenv("DB_USER", "").strip()
    password = os.getenv("DB_PASSWORD", "").strip()
    db_name = os.getenv("DB_NAME", "").strip()
    port = int(port_str) if port_str else 3306
    if not host or not user or not db_name:
        return None
    try:
        return pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db_name,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"[DB ERROR] Failed to connect to DB: {e}")
        return None

def scrape_shutuba_table(race_id: str) -> Optional[pd.DataFrame]:
    print(f"[SCRAPER] Fetching shutuba table for race_id: {race_id}")
    
    # 1. データベース (everydb2) からの取得を試みる
    conn = get_db_connection()
    if conn:
        try:
            # race_id (例: 202610020412) を JRA-VAN キーに分解
            # 2026(Year) 10(JyoCD) 02(Kaiji) 04(Nichiji) 12(RaceNum)
            year = race_id[0:4]
            jyo_cd = race_id[4:6]
            kaiji = race_id[6:8]
            nichiji = race_id[8:10]
            race_num = race_id[10:12]
            
            with conn:
                with conn.cursor() as cursor:
                    # まず速報系 (s_uma_race, s_race) から引く
                    sql = """
                    SELECT 
                        CONCAT(su.Year, su.JyoCD, LPAD(su.Kaiji, 2, '0'), LPAD(su.Nichiji, 2, '0'), LPAD(su.RaceNum, 2, '0')) AS race_id,
                        CAST(su.Umaban AS UNSIGNED) AS `馬番`,
                        su.Bamei AS `馬`,
                        su.KettoNum AS horse_id,
                        CASE 
                            WHEN su.SexCD = '1' THEN '牡'
                            WHEN su.SexCD = '2' THEN '牝'
                            WHEN su.SexCD = '3' THEN 'セ'
                            ELSE ''
                        END AS `性`,
                        CAST(su.Barei AS UNSIGNED) AS `齢`,
                        CAST(su.Futan AS UNSIGNED) / 10.0 AS `斤量`,
                        su.KisyuRyakusyo AS `騎手`,
                        su.KisyuCode AS jockey_id,
                        su.ChokyosiRyakusyo AS `調教師`,
                        su.ChokyosiCode AS trainer_id,
                        su.BanusiName AS `馬主`,
                        su.BanusiCode AS owner_id,
                        CASE 
                            WHEN su.BaTaijyu = '   ' OR su.BaTaijyu = '' THEN NULL
                            ELSE CAST(su.BaTaijyu AS UNSIGNED)
                        END AS `体重`,
                        CASE 
                            WHEN su.ZogenSa = '   ' OR su.ZogenSa = '' THEN 0
                            ELSE CAST(su.ZogenSa AS SIGNED) * (CASE WHEN su.ZogenFugo = '-' THEN -1 ELSE 1 END)
                        END AS `体重変化`,
                        CASE 
                            WHEN su.Odds = '    ' OR su.Odds = '' THEN NULL
                            ELSE CAST(su.Odds AS UNSIGNED) / 10.0
                        END AS `オッズ`,
                        CASE 
                            WHEN su.Ninki = '  ' OR su.Ninki = '' THEN NULL
                            ELSE CAST(su.Ninki AS UNSIGNED)
                        END AS `人気`,
                        sr.Hondai AS `レース名`,
                        CONCAT(sr.Year, '年', CAST(SUBSTRING(sr.MonthDay, 1, 2) AS UNSIGNED), '月', CAST(SUBSTRING(sr.MonthDay, 3, 2) AS UNSIGNED), '日') AS `日付`,
                        CASE 
                            WHEN CAST(sr.TrackCD AS UNSIGNED) BETWEEN 10 AND 22 THEN '芝'
                            WHEN CAST(sr.TrackCD AS UNSIGNED) BETWEEN 23 AND 29 THEN 'ダ'
                            ELSE '障'
                        END AS `芝・ダート`,
                        CAST(sr.Kyori AS UNSIGNED) AS `距離`,
                        CASE sr.JyoCD
                            WHEN '01' THEN '札幌' WHEN '02' THEN '函館' WHEN '03' THEN '福島' WHEN '04' THEN '新潟'
                            WHEN '05' THEN '東京' WHEN '06' THEN '中山' WHEN '07' THEN '中京' WHEN '08' THEN '京都'
                            WHEN '09' THEN '阪神' WHEN '10' THEN '小倉'
                            ELSE '不明'
                        END AS `場名`,
                        sr.JyoCD AS `場id`,
                        sr.JyokenName AS `クラス`,
                        CASE 
                            WHEN CAST(sr.TrackCD AS UNSIGNED) IN (13, 14, 18, 20, 24, 28) THEN '左'
                            WHEN CAST(sr.TrackCD AS UNSIGNED) IN (11, 12, 15, 16, 17, 19, 23, 27) THEN '右'
                            WHEN CAST(sr.TrackCD AS UNSIGNED) IN (22, 29, 39) THEN '直'
                            ELSE '右'
                        END AS `回り`,
                        CASE sr.TenkoCD
                            WHEN '1' THEN '晴' WHEN '2' THEN '曇' WHEN '3' THEN '小雨' WHEN '4' THEN '雨' WHEN '5' THEN '小雪' WHEN '6' THEN '雪'
                            ELSE ''
                        END AS `天気`,
                        CASE 
                            WHEN CAST(sr.TrackCD AS UNSIGNED) BETWEEN 10 AND 22 THEN
                                CASE sr.SibaBabaCD WHEN '1' THEN '良' WHEN '2' THEN '稍重' WHEN '3' THEN '重' WHEN '4' THEN '不良' ELSE '' END
                            ELSE
                                CASE sr.DirtBabaCD WHEN '1' THEN '良' WHEN '2' THEN '稍重' WHEN '3' THEN '重' WHEN '4' THEN '不良' ELSE '' END
                        END AS `馬場`
                    FROM s_uma_race su
                    LEFT JOIN s_race sr ON 
                        su.Year = sr.Year AND 
                        su.JyoCD = sr.JyoCD AND 
                        su.Kaiji = sr.Kaiji AND 
                        su.Nichiji = sr.Nichiji AND 
                        su.RaceNum = sr.RaceNum
                    WHERE su.Year = %s AND su.JyoCD = %s AND su.Kaiji = %s AND su.Nichiji = %s AND su.RaceNum = %s
                    """
                    cursor.execute(sql, (year, jyo_cd, kaiji, nichiji, race_num))
                    records = cursor.fetchall()
                    
                    # 速報系になければ蓄積系 (n_uma_race, n_race) から引く (直近過去走の取得などで使うため)
                    if not records:
                        sql = sql.replace('s_uma_race', 'n_uma_race').replace('s_race', 'n_race')
                        cursor.execute(sql, (year, jyo_cd, kaiji, nichiji, race_num))
                        records = cursor.fetchall()
                        
                    if records:
                        df = pd.DataFrame(records)
                        # カラムの型調整と前ゼロ付きID化
                        df['jockey_id'] = df['jockey_id'].astype(str).str.zfill(5)
                        df['trainer_id'] = df['trainer_id'].astype(str).str.zfill(5)
                        if 'owner_id' in df.columns:
                            df['owner_id'] = df['owner_id'].astype(str).str.zfill(6)
                        print(f"-> Successfully loaded {len(df)} entries from JRA-VAN Database.")
                        return df
        except Exception as e:
            print(f"[DB WARN] Failed to fetch shutuba from DB: {e}. Falling back to netkeiba scraping.")

    # 2. データベース取得失敗、または0件の場合、従来のnetkeibaスクレイピングにフォールバック
    print("-> Falling back to netkeiba web scraping...")
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15); r.raise_for_status(); time.sleep(REQUEST_WAIT_TIME)
    except requests.exceptions.RequestException as e: print(f"\n[SCRAPER ERROR]...: {e}"); return None
    soup = BeautifulSoup(r.content, "html.parser", from_encoding=r.apparent_encoding)
    race_info_header = soup.find("div", class_="RaceList_Item02");
    if not race_info_header: print(f"[SCRAPER WARN] Race info header not found for race_id: {race_id}"); return None
    race_name_h1 = race_info_header.find("h1", class_="RaceName"); race_name = safe_get_text(race_name_h1)
    grade_span = race_info_header.find("span", class_=re.compile(r'Icon_GradeType'))
    if grade_span:
        class_str = ' '.join(grade_span.get('class', [])); grade_match = re.search(r'Icon_GradeType(\d+)', class_str)
        if grade_match:
            grade_num = grade_match.group(1); grade_map = {'1': 'GI', '2': 'GII', '3': 'GIII'}
            if grade_num in grade_map: race_name += f" ({grade_map[grade_num]})"
    details01_text = safe_get_text(race_info_header.find("div", class_="RaceData01")); details02_text = safe_get_text(race_info_header.find("div", class_="RaceData02"))
    details02_spans = race_info_header.find("div", class_="RaceData02").find_all("span")
    date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', soup.title.string); date_str = f"{date_match.group(1)}年{int(date_match.group(2))}月{int(date_match.group(3))}日" if date_match else ""
    track_type_match = re.search(r'(芝|ダ|障)', details01_text); track_type_char = track_type_match.group(1) if track_type_match else ''
    dist_match = re.search(r'(\d+)m', details01_text); distance = dist_match.group(1) if dist_match else ''
    turn_match = re.search(r'\((左|右|直)', details01_text); turn = turn_match.group(1) if turn_match else ''
    weather_match = re.search(r'天候:(\S+)', details01_text); weather = weather_match.group(1).split('/')[0].strip() if weather_match else ''
    track_cond_match = re.search(r'馬場:(\S+)', details01_text); track_condition = track_cond_match.group(1).strip() if track_cond_match else ''
    place_match = re.search(r'(東京|中山|阪神|京都|中京|新潟|福島|小倉|札幌|函館)', details02_text); place_name = place_match.group(1) if place_match else "不明"
    kaisai_match = re.search(r'(\d+回.+?\d+日目)', details02_text); kaisai = kaisai_match.group(1) if kaisai_match else ""
    race_class = f"{details02_spans[3].text.strip()} {details02_spans[4].text.strip()}" if len(details02_spans) > 4 else ""
    place_id = race_id[4:6] if len(race_id) >= 6 else ""
    table = soup.find("table", class_="ShutubaTable")
    if not table: return None
    records = []
    for row in table.find_all("tr", class_="HorseList"):
        cols = row.find_all("td");
        if not cols or len(cols) < 11: continue
        try:
            horse_link = cols[3].find("a"); horse_id = re.search(r'/horse/(\d+)', horse_link['href']).group(1) if horse_link and 'href' in horse_link.attrs else ""
            if not horse_id: continue
            jockey_link = cols[6].find("a"); j_match = re.search(r'/jockey/.*?/(\d+)', jockey_link['href']) if jockey_link and jockey_link.has_attr('href') else None; jockey_id = j_match.group(1) if j_match else ""
            weight_text = safe_get_text(cols[8]); w_match = re.match(r'(\d+)\((.+)\)', weight_text); weight, weight_dif = (w_match.groups()) if w_match else (weight_text, '0')
            sex_age_text = safe_get_text(cols[4])

            trainer_link = cols[7].find("a")
            t_match = re.search(r'/trainer/.*?/(\d+)', trainer_link['href']) if trainer_link and trainer_link.has_attr('href') else None
            if not t_match and trainer_link and trainer_link.has_attr('href'):
                t_match = re.search(r'/trainer/(\d+)', trainer_link['href'])
            trainer_id = t_match.group(1) if t_match else ""
            trainer_name = safe_get_text(trainer_link) if trainer_link else ""

            records.append({
                'race_id': race_id, '馬番': to_numeric_or_nan(safe_get_text(cols[1])), '馬': safe_get_text(cols[3]), 'horse_id': horse_id,
                '性': sex_age_text[0] if sex_age_text else '', '齢': to_numeric_or_nan(sex_age_text[1:]),
                '斤量': to_numeric_or_nan(safe_get_text(cols[5])), '騎手': safe_get_text(cols[6]), 'jockey_id': jockey_id,
                '調教師': trainer_name, 'trainer_id': trainer_id, '馬主': np.nan, 'owner_id': np.nan,
                '体重': to_numeric_or_nan(weight), '体重変化': to_numeric_or_nan(weight_dif),
                'オッズ': to_numeric_or_nan(safe_get_text(cols[9].find('span'))), '人気': to_numeric_or_nan(safe_get_text(cols[10].find('span'))),
                'レース名': race_name, '日付': date_str, '芝・ダート': track_type_char, '距離': to_numeric_or_nan(distance),
                '場名': place_name, '場id': place_id, 'クラス': race_class,
                '回り': turn, '天気': weather, '馬場': track_condition,
            })
        except Exception as e: print(f"\n[SCRAPER ERROR]...: {e}"); continue
    return pd.DataFrame(records) if records else None

# ★★★ ここを修正 ★★★
def load_past_race_data(horse_ids: List[str], data_dir: str = config.DATA_DIR) -> Optional[pd.DataFrame]:
    """過去走データをローカルのCSVファイル群から読み込む (有効化バージョン)"""
    print(f"\n--- [Phase 2/5] Loading Past Race Data for {len(horse_ids)} horses from local CSVs ---")
    all_past_races = []
    # 検索範囲をconfigファイルから取得
    years = range(config.BUILD_END_YEAR, config.BUILD_START_YEAR - 1, -1)
    horse_id_set = set(map(str, horse_ids))
    
    for year in tqdm(years, desc="Loading past data by year"):
        file_path = os.path.join(data_dir, f"{year}.csv")
        if not os.path.exists(file_path): continue
        try:
            # low_memory=False を指定してDtypeWarningを抑制
            df = pd.read_csv(file_path, encoding="SHIFT-JIS", header=0, low_memory=False)
            if 'horse_id' not in df.columns: continue
            
            df['horse_id'] = df['horse_id'].astype(str)
            target_rows = df[df['horse_id'].isin(horse_id_set)]
            
            if not target_rows.empty:
                all_past_races.append(target_rows)
        except Exception as e:
            print(f"[DATA LOADER ERROR]...: {e}"); continue
            
    if not all_past_races:
        print("[DATA LOADER WARN] No past race data found for any of the specified horses in local files.")
        return None
        
    combined_df = pd.concat(all_past_races, ignore_index=True)
    combined_df.drop_duplicates(inplace=True)
    print(f"-> Found {len(combined_df)} past race entries from local files.")
    return combined_df

def jravan_time_to_seconds(time_str):
    if not time_str or pd.isna(time_str):
        return np.nan
    time_str = str(time_str).strip()
    if not time_str.isdigit():
        return np.nan
    try:
        if len(time_str) >= 4:
            m = int(time_str[0:-3])
            s = int(time_str[-3:-1])
            t = int(time_str[-1])
            return float(m * 60 + s + t * 0.1)
        elif len(time_str) >= 1:
            s = int(time_str[0:-1])
            t = int(time_str[-1])
            return float(s + t * 0.1)
    except Exception:
        return np.nan

def format_lap_times(row):
    laps = []
    for i in range(1, 26):
        val = row.get(f'LapTime{i}')
        if val is None or pd.isna(val):
            continue
        val = str(val).strip()
        if not val or val == '0' or val == '00' or val == '000':
            continue
        try:
            laps.append(f"{int(val) * 0.1:.1f}")
        except Exception:
            continue
    return "-".join(laps) if laps else np.nan

def format_corner_passage(row):
    corners = []
    for c in ['Jyuni1c', 'Jyuni2c', 'Jyuni3c', 'Jyuni4c']:
        val = row.get(c)
        if val is None or pd.isna(val):
            continue
        val = str(val).strip()
        if not val or val == '0' or val == '00' or val == '  ':
            continue
        try:
            corners.append(str(int(val)))
        except Exception:
            continue
    return "-".join(corners) if corners else np.nan

def load_past_race_data_with_overseas(
    horse_ids: List[str],
    race_date: str,
    num_past_races: int = 5,
    use_horse_page: bool = True,
    save_to_cache: bool = True,
    data_dir: str = config.DATA_DIR
) -> Optional[pd.DataFrame]:
    """
    JRA-VAN データベースおよび補完用ネット競馬スクレイピングから過去走データを取得
    """
    print(f"\n--- [Phase 2/5] Loading Past Race Data (with JRA-VAN DB / Scraping) for {len(horse_ids)} horses ---")
    
    if not use_horse_page:
        return load_past_race_data(horse_ids, data_dir)
        
    db_past_df = None
    
    # 1. JRA-VAN データベースから一括クエリを試みる
    conn = get_db_connection()
    if conn:
        try:
            with conn:
                with conn.cursor() as cursor:
                    format_strings = ','.join(['%s'] * len(horse_ids))
                    sql = f"""
                    SELECT 
                        CONCAT(ur.Year, ur.JyoCD, LPAD(ur.Kaiji, 2, '0'), LPAD(ur.Nichiji, 2, '0'), LPAD(ur.RaceNum, 2, '0')) AS race_id,
                        ur.KettoNum AS horse_id,
                        CONCAT(ur.Year, '年', CAST(SUBSTRING(r.MonthDay, 1, 2) AS UNSIGNED), '月', CAST(SUBSTRING(r.MonthDay, 3, 2) AS UNSIGNED), '日') AS `日付`,
                        r.Hondai AS `レース名`,
                        CASE 
                            WHEN CAST(r.TrackCD AS UNSIGNED) BETWEEN 10 AND 22 THEN '芝'
                            WHEN CAST(r.TrackCD AS UNSIGNED) BETWEEN 23 AND 29 THEN 'ダ'
                            ELSE '障'
                        END AS `芝・ダート`,
                        CAST(r.Kyori AS UNSIGNED) AS `距離`,
                        CASE r.JyoCD
                            WHEN '01' THEN '札幌' WHEN '02' THEN '函館' WHEN '03' THEN '福島' WHEN '04' THEN '新潟'
                            WHEN '05' THEN '東京' WHEN '06' THEN '中山' WHEN '07' THEN '中京' WHEN '08' THEN '京都'
                            WHEN '09' THEN '阪神' WHEN '10' THEN '小倉'
                            ELSE '不明'
                        END AS `場名`,
                        r.JyoCD AS `場id`,
                        CASE 
                            WHEN CAST(r.TrackCD AS UNSIGNED) BETWEEN 10 AND 22 THEN
                                CASE r.SibaBabaCD WHEN '1' THEN '良' WHEN '2' THEN '稍重' WHEN '3' THEN '重' WHEN '4' THEN '不良' ELSE '' END
                            ELSE
                                CASE r.DirtBabaCD WHEN '1' THEN '良' WHEN '2' THEN '稍重' WHEN '3' THEN '重' WHEN '4' THEN '不良' ELSE '' END
                        END AS `馬場`,
                        CAST(ur.Ninki AS UNSIGNED) AS `人気`,
                        CASE 
                            WHEN ur.Odds = '    ' OR ur.Odds = '' THEN NULL
                            ELSE CAST(ur.Odds AS UNSIGNED) / 10.0
                        END AS `単勝オッズ`,
                        CAST(ur.KakuteiJyuni AS UNSIGNED) AS `着順`,
                        CASE 
                            WHEN ur.TimeDiff = '   ' OR ur.TimeDiff = '' THEN NULL
                            ELSE CAST(ur.TimeDiff AS SIGNED) / 10.0
                        END AS `着差`,
                        ur.Time AS `タイム_raw`,
                        CAST(ur.Futan AS UNSIGNED) / 10.0 AS `斤量`,
                        ur.KisyuRyakusyo AS `騎手`,
                        ur.KisyuCode AS jockey_id,
                        ur.ChokyosiRyakusyo AS `調教師`,
                        ur.ChokyosiCode AS trainer_id,
                        ur.Jyuni1c, ur.Jyuni2c, ur.Jyuni3c, ur.Jyuni4c,
                        r.LapTime1, r.LapTime2, r.LapTime3, r.LapTime4, r.LapTime5, r.LapTime6, r.LapTime7, r.LapTime8, r.LapTime9, r.LapTime10,
                        r.LapTime11, r.LapTime12, r.LapTime13, r.LapTime14, r.LapTime15, r.LapTime16, r.LapTime17, r.LapTime18, r.LapTime19, r.LapTime20,
                        r.LapTime21, r.LapTime22, r.LapTime23, r.LapTime24, r.LapTime25
                    FROM n_uma_race ur
                    LEFT JOIN n_race r ON 
                        ur.Year = r.Year AND 
                        ur.JyoCD = r.JyoCD AND 
                        ur.Kaiji = r.Kaiji AND 
                        ur.Nichiji = r.Nichiji AND 
                        ur.RaceNum = r.RaceNum
                    WHERE ur.KettoNum IN ({format_strings})
                    """
                    cursor.execute(sql, tuple(horse_ids))
                    db_records = cursor.fetchall()
                    
                    if db_records:
                        temp_df = pd.DataFrame(db_records)
                        # カラム型調整と前ゼロ付きID化
                        temp_df['jockey_id'] = temp_df['jockey_id'].astype(str).str.zfill(5)
                        temp_df['trainer_id'] = temp_df['trainer_id'].astype(str).str.zfill(5)
                        # タイムの秒数変換
                        temp_df['タイム'] = temp_df['タイム_raw'].apply(jravan_time_to_seconds)
                        # ラップタイムの結合
                        temp_df['lap_times'] = temp_df.apply(format_lap_times, axis=1)
                        # コーナー通過順の結合
                        temp_df['corner_passage_text'] = temp_df.apply(format_corner_passage, axis=1)
                        
                        # 不要カラムのドロップ
                        cols_to_drop = ['タイム_raw', 'Jyuni1c', 'Jyuni2c', 'Jyuni3c', 'Jyuni4c'] + [f'LapTime{i}' for i in range(1, 26)]
                        temp_df.drop(columns=cols_to_drop, errors='ignore', inplace=True)
                        db_past_df = temp_df
                        print(f"-> Successfully pre-fetched {len(db_past_df)} past race entries from JRA-VAN Database.")
        except Exception as e:
            print(f"[DB WARN] Failed to query past races from DB: {e}. Falling back fully to netkeiba scraping.")

    # 2. 各馬の履歴の処理と補完
    try:
        from data_collection.scrape_horse_past_races import scrape_all_past_races_from_horse_page
    except ImportError:
        from src.data_collection.scrape_horse_past_races import scrape_all_past_races_from_horse_page
    
    all_past_races = []
    kaigai_races_to_save = []
    tihou_races_to_save = []
    LOCAL_TRACKS = {'大井', '船橋', '川崎', '浦和', '門別', '盛岡', '水沢', '金沢', '笠松', '名古屋', '園田', '姫路', '高知', '佐賀'}
    target_date = pd.to_datetime(race_date, format='%Y年%m月%d日', errors='coerce')
    
    for horse_id in tqdm(horse_ids, desc="Processing horse history"):
        horse_past = None
        
        # JRA-VAN DB からの切り出し
        if db_past_df is not None and not db_past_df.empty:
            df_horse = db_past_df[db_past_df['horse_id'] == horse_id].copy()
            if not df_horse.empty:
                df_horse['日付_temp'] = pd.to_datetime(df_horse['日付'], format='%Y年%m月%d日', errors='coerce')
                if pd.notna(target_date):
                    df_horse = df_horse[df_horse['日付_temp'] < target_date]
                df_horse.sort_values('日付_temp', ascending=False, inplace=True)
                df_horse.drop(columns=['日付_temp'], errors='ignore', inplace=True)
                
                # 十分な件数がある場合はスクレイピングをスキップ
                if len(df_horse) >= num_past_races:
                    horse_past = df_horse.head(num_past_races)
                else:
                    horse_past = df_horse

        # DBだけではデータが不足している場合（地方/海外実績を含む場合など）、ネット競馬から補完スクレイピング
        if horse_past is None or len(horse_past) < num_past_races:
            db_count = len(horse_past) if horse_past is not None else 0
            # 効率化のため、新馬などの「そもそも走ったことがない馬」に対して無駄なスクレイピングを繰り返すのを防ぎたいが、
            # 地方や海外で走っている可能性があるため、DB数が必要数に満たない場合のみスクレイピングを実行する
            horse_url = f"https://db.netkeiba.com/horse/result/{horse_id}/"
            try:
                scraped_df = scrape_all_past_races_from_horse_page(
                    horse_id, 
                    horse_url, 
                    max_races=num_past_races * 2
                )
                if scraped_df is not None and not scraped_df.empty:
                    scraped_df['日付_temp'] = pd.to_datetime(scraped_df['日付'], format='%Y年%m月%d日', errors='coerce')
                    if pd.notna(target_date):
                        scraped_df = scraped_df[scraped_df['日付_temp'] < target_date]
                    scraped_df.sort_values('日付_temp', ascending=False, inplace=True)
                    scraped_df.drop(columns=['日付_temp'], errors='ignore', inplace=True)
                    
                    # スクレイピングデータを優先して設定
                    horse_past = scraped_df.head(num_past_races)
                    
                    # キャッシュ分類用
                    if save_to_cache and 'is_jra_race' in scraped_df.columns:
                        non_jra_races = scraped_df[scraped_df['is_jra_race'] == False].copy()
                        for _, race in non_jra_races.iterrows():
                            place_name = race.get('場名', '')
                            if place_name in LOCAL_TRACKS:
                                tihou_races_to_save.append(race)
                            else:
                                kaigai_races_to_save.append(race)
            except Exception as e:
                # スクレイピングに失敗した場合でも、DBデータがあればそれを使う
                pass

        if horse_past is not None and not horse_past.empty:
            all_past_races.append(horse_past.head(num_past_races))
            
    # 海外・地方データの保存
    if save_to_cache:
        if kaigai_races_to_save:
            _save_overseas_data(pd.DataFrame(kaigai_races_to_save), 'kaigai', data_dir)
        if tihou_races_to_save:
            _save_overseas_data(pd.DataFrame(tihou_races_to_save), 'tihou', data_dir)
            
    if not all_past_races:
        print("[DATA LOADER WARN] No past race data found.")
        return None
        
    combined_df = pd.concat(all_past_races, ignore_index=True)
    combined_df.drop_duplicates(subset=['horse_id', '日付', 'レース名'], inplace=True)
    
    # ---------------------------------------------------------
    # JRA-VAN DBからの過去走について、ラップタイムや通過順が欠損している場合にローカルCSVで補う処理
    # (JRA-VAN DBから直接ラップ等を取得できているため、基本的にはスキップされるか、スクレイピングで得た一部のデータのみマージされる)
    # ---------------------------------------------------------
    if 'race_id' in combined_df.columns:
        # lap_times または corner_passage_text が NaN のレコードがある場合のみ、ローカルCSVから補完する
        nan_mask = combined_df['lap_times'].isna() | combined_df['corner_passage_text'].isna()
        if nan_mask.any():
            unique_rids = combined_df.loc[nan_mask, 'race_id'].dropna().astype(str).unique().tolist()
            if unique_rids:
                local_details = get_local_race_data(unique_rids)
                if not local_details.empty:
                    combined_df = pd.merge(combined_df, local_details, on='race_id', how='left', suffixes=('', '_local'))
                    if 'lap_times' in combined_df.columns and 'lap_times_local' in combined_df.columns:
                        combined_df['lap_times'] = combined_df['lap_times'].fillna(combined_df['lap_times_local'])
                        combined_df.drop(columns=['lap_times_local'], inplace=True)
                    if 'corner_passage_text' in combined_df.columns and 'corner_passage_text_local' in combined_df.columns:
                        combined_df['corner_passage_text'] = combined_df['corner_passage_text'].fillna(combined_df['corner_passage_text_local'])
                        combined_df.drop(columns=['corner_passage_text_local'], inplace=True)
                        
    print(f"-> Found {len(combined_df)} past race entries (including JRA-VAN & scraped local/overseas).")
    return combined_df


def _save_overseas_data(df: pd.DataFrame, data_type: str, data_dir: str):
    """
    海外・地方レースデータを年別CSVに保存
    
    Args:
        df: 保存するデータフレーム
        data_type: 'kaigai' または 'tihou'
        data_dir: データディレクトリ
    """
    if df.empty:
        return
    
    # 保存先ディレクトリを作成
    save_dir = os.path.join(data_dir, data_type)
    os.makedirs(save_dir, exist_ok=True)
    
    # 年別に分割して保存
    df['日付_temp'] = pd.to_datetime(df['日付'], format='%Y年%m月%d日', errors='coerce')
    df['year'] = df['日付_temp'].dt.year
    df = df.drop('日付_temp', axis=1)
    
    for year, year_df in df.groupby('year'):
        if pd.isna(year):
            continue
        
        year = int(year)
        file_path = os.path.join(save_dir, f"{year}.csv")
        
        # 既存ファイルがあれば読み込んで結合
        if os.path.exists(file_path):
            try:
                existing_df = pd.read_csv(file_path, encoding='SHIFT-JIS', low_memory=False)
                year_df = pd.concat([existing_df, year_df], ignore_index=True)
                year_df.drop_duplicates(subset=['horse_id', '日付', 'レース名'], inplace=True)
            except Exception as e:
                print(f"[SAVE ERROR] Failed to load existing {data_type} data for {year}: {e}")
        
        # 保存
        try:
            year_df.to_csv(file_path, index=False, encoding='SHIFT-JIS')
            print(f"[SAVE] Saved {len(year_df)} {data_type} races to {file_path}")
        except Exception as e:
            print(f"[SAVE ERROR] Failed to save {data_type} data for {year}: {e}")

def get_local_race_data(race_ids: List[str]) -> pd.DataFrame:
    """
    指定されたrace_idリストに対応するラップタイムとコーナー通過順を、
    ローカルのdataディレクトリにある年度別CSVから取得する。
    """
    if not race_ids:
        return pd.DataFrame()

    # 年度ごとに必要なrace_idをグルーピング
    year_map = {}
    for rid in race_ids:
        rid_str = str(rid)
        if len(rid_str) >= 4:
            year = rid_str[:4]
            if year not in year_map: year_map[year] = []
            year_map[year].append(rid_str)
            
    accumulated_data = []
    
    for year, rids in year_map.items():
        csv_path = os.path.join(config.DATA_DIR, f"{year}.csv")
        if not os.path.exists(csv_path):
            # print(f"[WARN] Local data file not found: {csv_path}")
            continue
            
        try:
            # 必要なカラムだけ読む (メモリ節約)
            header = pd.read_csv(csv_path, nrows=0).columns.tolist()
            
            use_cols = ['race_id']
            if 'lap_times' in header: use_cols.append('lap_times')
            if 'corner_passage_text' in header: use_cols.append('corner_passage_text')
            
            if len(use_cols) == 1: # race_idしかない
                continue
                
            # 対象のrace_idが含まれる行だけ抽出
            df_year = pd.read_csv(csv_path, usecols=use_cols, dtype={'race_id': str})
            
            # フィルタ
            filtered = df_year[df_year['race_id'].isin(rids)]
            if not filtered.empty:
                accumulated_data.append(filtered)
                
        except Exception as e:
            print(f"[ERROR] Failed to read local data {csv_path}: {e}")
            
    if not accumulated_data:
        return pd.DataFrame()
        
    result_df = pd.concat(accumulated_data, ignore_index=True)
    return result_df