import re
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Any

class NetkeibaParser:
    """netkeibaのレース結果HTMLを解析し、構造化されたデータに変換するクラス。
    
    Javaの「単一責任の原則（Single Responsibility Principle）」に基づき、
    このクラスは「HTMLのパース・データ抽出」のみに専念します。
    """
    
    # ==========================================================
    # タイム指数（プレミアム列5つ）を除外した後の、
    # 綺麗で一定なテーブル列インデックス（フィールド定数）
    # ==========================================================
    COL_RANK = 0          # 着順
    COL_WAKUBAN = 1       # 枠番
    COL_UMABAN = 2        # 馬番
    COL_HORSE = 3         # 馬名/リンク
    COL_SEX_AGE = 4       # 性齢
    COL_KINRYO = 5        # 斤量
    COL_JOCKEY = 6        # 騎手/リンク
    COL_TIME = 7          # 走破タイム
    COL_MARGIN = 8        # 着差
    COL_PAS = 9           # 通過順 (cells[9])
    COL_LAST = 10         # 上り3F (cells[10])
    COL_ODDS = 11         # 単勝オッズ (cells[11])
    COL_POPULARITY = 12   # 人気 (cells[12])
    COL_WEIGHT = 13       # 馬体重 (cells[13])
    COL_TRAINER = 17      # 調教師 (cells[17])
    COL_OWNER = 18        # 馬主 (cells[18])
    COL_PRIZE = 19        # 賞金 (cells[19])

    def __init__(self, html_content: str):
        """コンストラクタ"""
        self._soup = BeautifulSoup(html_content, "html.parser")

    def _safe_get_text(self, element) -> str:
        """HTML要素から安全にテキストを取得し、空白を除去するプライベートメソッド"""
        if not element:
            return ""
        # 特殊スペース '\xa0' を通常の半角スペースに置き換え、前後の空白を除去します
        return element.get_text().replace('\xa0', ' ').strip()

    def get_race_info(self) -> Dict[str, Any]:
        """レースの基本情報（レース名、日付、馬場、天候など）を抽出するゲッター"""
        info = {
            "title": "", "date": "", "detail": "", "class": "",
            "surface": "", "direction": "", "distance": "", "weather": "", "condition": ""
        }
        
        data_intro = self._soup.find("div", class_="data_intro")
        if not data_intro:
            return info

        info["title"] = self._safe_get_text(data_intro.find("h1"))
        
        smalltxt = self._safe_get_text(data_intro.find("p", class_="smalltxt")).split()
        info["date"] = smalltxt[0] if smalltxt else ""
        info["detail"] = smalltxt[1] if len(smalltxt) > 1 else ""
        info["class"] = smalltxt[2].replace('\xa0', ' ') if len(smalltxt) > 2 else ""

        diary_snap_text = ""
        all_spans = data_intro.find_all("span")
        for span in all_spans:
            text = self._safe_get_text(span)
            if "m" in text and "天候" in text:
                diary_snap_text = text.replace('\xa0', ' ')
                break
        
        if diary_snap_text:
            parts = diary_snap_text.split('/')
            if len(parts) >= 3:
                info["surface"] = parts[0].strip()[0]                     # 芝・ダート
                info["direction"] = parts[0].strip()[1]                   # 回り
                info["distance"] = ''.join(filter(str.isdigit, parts[0])) # 距離
                info["weather"] = parts[1].split(':')[1].strip() if ':' in parts[1] else ''   # 天候
                info["condition"] = parts[2].split(':')[1].strip() if ':' in parts[2] else '' # 馬場

        return info

    def get_race_details(self) -> Dict[str, str]:
        """コーナー通過順、ラップタイム、レースペースなどの詳細情報を抽出するゲッター"""
        details = {
            "corner_passage_text": "",
            "lap_times": "",
            "race_pace": ""
        }
        
        try:
            tables = self._soup.find_all("table")
            for table in tables:
                table_str = str(table)
                if "コーナー通過順" in table_str:
                    corner_rows = table.find_all("tr")
                    passages = []
                    for row in corner_rows:
                        th = row.find("th")
                        td = row.find("td")
                        if th and td:
                            passages.append(f"{self._safe_get_text(th)}:{self._safe_get_text(td)}")
                    if passages:
                        details["corner_passage_text"] = " | ".join(passages)

                if "ラップ" in table_str and "ペース" in table_str:
                    rows = table.find_all("tr")
                    for row in rows:
                        th = row.find("th")
                        td = row.find("td")
                        if th and td:
                            header = self._safe_get_text(th)
                            value = self._safe_get_text(td)
                            if "ラップ" in header:
                                details["lap_times"] = value
                            elif "ペース" in header:
                                details["race_pace"] = value
        except Exception as e:
            print(f"[WARN] Failed to scrape details (corners/laps): {e}")
            
        return details

    def get_horse_results(self, race_id: str) -> List[Dict[str, Any]]:
        """馬ごとの成績データを抽出するゲッター"""
        race_table = self._soup.find("table", class_="race_table_01")
        if not race_table:
            return []

        race_info = self.get_race_info()
        race_details = self.get_race_details()
        place_id = race_id[4:6]
        
        horse_results = []
        horse_rows = race_table.find_all("tr")[1:]

        for row_idx, row in enumerate(horse_rows):
            # 1. まずは普通に行のセルをすべて取得する
            cells = row.find_all("td")
            
            # タイム指数などのプレミアム列が含まれるため、本来は最低でも15列以上あります
            if len(cells) < 15:
                continue

            # 2. 【究極の解決策】
            # インデックス 9番目〜13番目（cells[9:14]）のタイム指数など5つのプレミアム列を
            # Pythonのリスト操作で直接削除して前に詰めさせます。
            # これにより、HTML構造の破壊やクラス名(bml)の誤削除問題を完璧に回避します！
            del cells[9:14]

            try:
                # ==========================================================
                # カプセル化された定数を使ってパース。
                # インデックスの順序が変わっても、定数定義を変更するだけで
                # このロジック本体は1行も修正せずにそのまま動き続けます！
                # ==========================================================
                rank = self._safe_get_text(cells[self.COL_RANK])
                umaban = self._safe_get_text(cells[self.COL_UMABAN])
                
                horse_link = cells[self.COL_HORSE].find("a")
                horse_name = self._safe_get_text(horse_link)
                horse_id = horse_link['href'].split('/')[-2] if horse_link else ""
                
                sex_age = self._safe_get_text(cells[self.COL_SEX_AGE])
                sex, age = (sex_age[0], sex_age[1:]) if sex_age else ('', '')
                
                kinryo = self._safe_get_text(cells[self.COL_KINRYO])
                
                jockey_link = cells[self.COL_JOCKEY].find("a")
                jockey_name = self._safe_get_text(jockey_link)
                jockey_id_match = re.search(r'/jockey/result/recent/(\d+)/', jockey_link['href']) if jockey_link else None
                jockey_id = jockey_id_match.group(1) if jockey_id_match else ""
                
                runtime = self._safe_get_text(cells[self.COL_TIME])
                pas = self._safe_get_text(cells[self.COL_PAS])
                last = self._safe_get_text(cells[self.COL_LAST])
                odds = self._safe_get_text(cells[self.COL_ODDS])
                pop = self._safe_get_text(cells[self.COL_POPULARITY])
                
                weight_text = self._safe_get_text(cells[self.COL_WEIGHT])
                weight, weight_dif = weight_text.replace(')', '').split('(') if '(' in weight_text else (weight_text, '0')

                trainer_link = cells[self.COL_TRAINER].find("a")
                trainer_name = self._safe_get_text(trainer_link)
                trainer_id = trainer_link['href'].split('/')[-2] if trainer_link else ""

                owner_link = cells[self.COL_OWNER].find("a")
                owner_name = self._safe_get_text(owner_link)
                owner_id = owner_link['href'].split('/')[-2] if owner_link else ""

                prize_money = self._safe_get_text(cells[self.COL_PRIZE])

                result_row = {
                    "race_id": race_id,
                    "horse_name": horse_name,
                    "horse_id": horse_id,
                    "jockey_name": jockey_name,
                    "jockey_id": jockey_id,
                    "umaban": umaban,
                    "runtime": runtime,
                    "odds": odds,
                    "pas": pas,
                    "rank": rank,
                    "weight": weight,
                    "weight_dif": weight_dif,
                    "sex": sex,
                    "age": age,
                    "kinryo": kinryo,
                    "last": last,
                    "pop": pop,
                    "title": race_info["title"],
                    "date": race_info["date"],
                    "detail": race_info["detail"],
                    "class": race_info["class"],
                    "surface": race_info["surface"],
                    "distance": race_info["distance"],
                    "direction": race_info["direction"],
                    "condition": race_info["condition"],
                    "weather": race_info["weather"],
                    "place_id": place_id,
                    "trainer_name": trainer_name,
                    "trainer_id": trainer_id,
                    "owner_name": owner_name,
                    "owner_id": owner_id,
                    "prize_money": prize_money,
                    "corner_passage_text": race_details["corner_passage_text"],
                    "lap_times": race_details["lap_times"],
                    "race_pace": race_details["race_pace"]
                }
                
                horse_results.append(result_row)

            except Exception as e:
                print(f"[WARN] Failed to parse horse row {row_idx} in race {race_id}: {e}. Skipping this horse.")
                continue

        return horse_results

    def get_payouts(self) -> Dict[str, Any]:
        """払い戻し情報を解析し、DB保存用の辞書を作成する"""
        import json
        payout_data_for_db = {}
        pay_block = self._soup.find('dl', class_='pay_block')
        if not pay_block:
            return payout_data_for_db
        payout_map = {
            'tan': 'tansho', 'fuku': 'fukusho', 'waku': 'wakuren', 'uren': 'umaren',
            'wide': 'wide', 'utan': 'umatan', 'sanfuku': 'sanrenpuku', 'santan': 'sanrentan'
        }
        for row in pay_block.find_all('tr'):
            th = row.find('th')
            if not th or not th.has_attr('class') or not th.get('class')[0] in payout_map:
                continue
            key_prefix = payout_map[th.get('class')[0]]
            try:
                tds = row.find_all('td')
                if len(tds) < 2:
                    continue
                
                # get_text(separator)を使い、<br>タグを安全に処理する
                nums_text = [n.strip() for n in tds[0].get_text(separator='<br>').split('<br>') if n.strip()]
                payouts = [int(p.strip().replace(',', '')) for p in tds[1].get_text(separator='<br>').split('<br>') if p.strip().replace(',', '').isdigit()]

                if not payouts:
                    continue
                if key_prefix in ['fukusho', 'wide']:
                    payout_data_for_db[f'{key_prefix}_payouts'] = json.dumps({num: pay for num, pay in zip(nums_text, payouts)}, ensure_ascii=False)
                else:
                    payout_data_for_db[f'{key_prefix}_payout'] = payouts[0]
                    payout_data_for_db[f'{key_prefix}_numbers'] = nums_text[0]
            except Exception as e:
                print(f"  [PARSER WARN] '{key_prefix}'の解析中にエラー: {e}")
                continue
        return payout_data_for_db

