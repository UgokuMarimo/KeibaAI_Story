import os
import csv
from typing import List, Dict, Any

class RaceDataWriter:
    """パースされた競馬の成績データをCSVファイルに安全に保存・追記するクラス。
    
    Javaの「単一責任の原則（Single Responsibility Principle）」に基づき、
    このクラスは「CSVファイルへの書き込み・データ永続化」のみを担当します。
    通信や解析のロジックは一切含みません。
    """
    
    def __init__(self, save_dir: str = "data/raw"):
        """コンストラクタ（保存先フォルダの初期化）
        
        Args:
            save_dir (str): CSVファイルを保存するベースディレクトリ（デフォルト: data/raw）
        """
        self.save_dir = save_dir
        
        # ==========================================================
        # CSVの列名（日本語ヘッダー）の定義
        # 出力されるCSVの列順を既存の学習データと完全に固定・一致させます。
        # ==========================================================
        self.csv_header = [
            'race_id', '馬', 'horse_id', '騎手', 'jockey_id', '馬番', '走破時間', 'オッズ', 
            '通過順', '着順', '体重', '体重変化', '性', '齢', '斤量', '上がり', 
            '人気', 'レース名', '日付', '開催', 'クラス', '芝・ダート', '距離', '回り', 
            '馬場', '天気', '場id', '場名', '調教師', 'trainer_id', '馬主', 'owner_id', 
            '賞金', 'corner_passage_text', 'lap_times', 'race_pace'
        ]

        # 英語キーから日本語キーへのマッピング定義
        self.key_mapping = {
            'race_id': 'race_id', 'horse_name': '馬', 'horse_id': 'horse_id', 
            'jockey_name': '騎手', 'jockey_id': 'jockey_id', 'umaban': '馬番', 
            'runtime': '走破時間', 'odds': 'オッズ', 'pas': '通過順', 'rank': '着順', 
            'weight': '体重', 'weight_dif': '体重変化', 'sex': '性', 'age': '齢', 
            'kinryo': '斤量', 'last': '上がり', 'pop': '人気', 'title': 'レース名', 
            'date': '日付', 'detail': '開催', 'class': 'クラス', 'surface': '芝・ダート', 
            'distance': '距離', 'direction': '回り', 'condition': '馬場', 'weather': '天気', 
            'place_id': '場id', 'place_name': '場名', 'trainer_name': '調教師', 
            'trainer_id': 'trainer_id', 'owner_name': '馬主', 'owner_id': 'owner_id', 
            'prize_money': '賞金', 'corner_passage_text': 'corner_passage_text', 
            'lap_times': 'lap_times', 'race_pace': 'race_pace'
        }

    def _get_csv_path(self, year: str) -> str:
        """年ごとのCSVファイルパスを生成する内部プライベートメソッド"""
        return os.path.join(self.save_dir, f"{year}.csv")

    def write_rows(self, year: str, rows: List[Dict[str, Any]]) -> bool:
        """パースされた馬ごとの成績データ（辞書のリスト）をCSVに書き込む公開メソッド。
        
        ファイルが存在しない場合は新規作成してヘッダーを書き込み、
        既に存在する場合はヘッダーは書かずにデータの追記のみ行います。
        
        Args:
            year (str): レースが開催された年（ファイル名になります 例: '2023'）
            rows (List[Dict[str, Any]]): パース済みの辞書のリスト
            
        Returns:
            bool: 保存に成功した場合は True、失敗した場合は False
        """
        if not rows:
            print("[INFO] 書き込むデータがありませんでした。")
            return False
            
        csv_path = self._get_csv_path(year)
        file_exists = os.path.exists(csv_path)
        
        # 保存先のディレクトリ（data/raw など）がなければ自動作成する
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        
        try:
            import config
            # SHIFT-JIS (CP932) でファイルを開きます（errors='replace' で書き込みエラーを防止）
            # モードは 'a' (Append: 追記モード) を使用します
            with open(csv_path, 'a' if file_exists else 'w', newline='', encoding="SHIFT-JIS", errors='replace') as f:
                # Python標準の csv.DictWriter を使用
                writer = csv.DictWriter(f, fieldnames=self.csv_header)
                
                # 新規作成時のみ、列名（ヘッダー）を一行目に書き込む
                if not file_exists:
                    writer.writeheader()
                    print(f"[FILE] 新規のCSVファイルを作成しました: {csv_path}")
                
                # 各成績データを書き込む
                for row in rows:
                    # 英語キーの辞書である場合、日本語キーにマッピング
                    mapped_row = {}
                    for eng_key, jpn_key in self.key_mapping.items():
                        # 元データが英語キーまたは日本語キーのどちらでも取得できるようにする
                        val = row.get(eng_key, row.get(jpn_key, ''))
                        mapped_row[jpn_key] = val
                    
                    # '場名' が空で '場id' がある場合、configから補完
                    if not mapped_row.get('場名') and mapped_row.get('場id'):
                        try:
                            mapped_row['場名'] = config.PLACE_MAP.get(f"{int(mapped_row['場id']):02d}", '')
                        except Exception:
                            pass
                    
                    # 【防御プログラミング】
                    # self.csv_header に定義された列名と1対1で揃うようにデータをフィルタリング・補完します。
                    clean_row = {key: mapped_row.get(key, '') for key in self.csv_header}
                    writer.writerow(clean_row)
                    
            print(f"[FILE] {len(rows)} 件のレコードをCSVに正常に保存（追記）しました。")
            return True
            
        except Exception as e:
            print(f"[ERROR] CSVへの書き込み中にエラーが発生しました: {e}")
            return False
