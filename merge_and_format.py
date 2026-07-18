import os
import sys
import pandas as pd
import numpy as np

# Windows環境での文字化け対策（標準出力をUTF-8に変更）
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 競馬場IDと漢字場名のマッピング (config.py から移植)
PLACE_MAP = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"
}

def format_time(time_str):
    """JRA-VANの走破時間（例: 1098 ＝ 1分09秒8）を netkeiba 形式（"1:09.8"）に変換"""
    try:
        if not time_str or pd.isna(time_str):
            return ""
        t_val = int(time_str)
        if t_val == 0:
            return ""
        seconds_total = t_val / 10.0
        minutes = int(seconds_total // 60)
        seconds = seconds_total % 60
        if minutes > 0:
            return f"{minutes}:{seconds:04.1f}"
        else:
            return f"{seconds:.1f}"
    except Exception:
        return ""

def format_odds(odds_str):
    """JRA-VANのオッズ（例: 24 ＝ 2.4倍）を小数（2.4）に変換"""
    try:
        if not odds_str or pd.isna(odds_str) or odds_str == "**" or odds_str == "000":
            return ""
        return f"{int(odds_str) / 10.0:.1f}"
    except Exception:
        return ""

def format_passage(row):
    """Jyuni1c〜Jyuni4c をハイフンで結合して通過順（例: "3-3-2-1"）を生成"""
    passages = []
    for col in ['Jyuni1c', 'Jyuni2c', 'Jyuni3c', 'Jyuni4c']:
        val = row.get(col)
        if pd.notna(val) and val != "" and val != "0" and val != "00":
            try:
                passages.append(str(int(val)))
            except ValueError:
                passages.append(str(val))
    return "-".join(passages) if passages else ""

def format_weight_diff(row):
    """ZogenFugo と ZogenSa から体重変化（例: "+6"）を生成"""
    fugo = row.get('ZogenFugo', '')
    sa = row.get('ZogenSa', '')
    if pd.isna(sa) or sa == "" or sa == "   ":
        return ""
    try:
        sa_val = int(sa)
        if sa_val == 0:
            return "0"
        prefix = "-" if fugo == "-" else "+"
        return f"{prefix}{sa_val}"
    except Exception:
        return ""

def format_sex(sex_cd):
    """SexCD から 性 を生成"""
    mapping = {"1": "牡", "2": "牝", "3": "セ"}
    return mapping.get(str(sex_cd), "")

def format_futan_or_haron(val):
    """斤量や上がり3F（例: 550 ＝ 55.0, 354 ＝ 35.4）を10で割る"""
    try:
        if not val or pd.isna(val) or val == "000" or val == "00":
            return ""
        return f"{int(val) / 10.0:.1f}"
    except Exception:
        return ""

def format_date(row):
    """Year と MonthDay から日付（"2026年06月21日"）を生成"""
    year = row.get('Year')
    monthday = row.get('MonthDay')
    if pd.isna(year) or pd.isna(monthday) or len(str(monthday)) < 4:
        return ""
    m = str(monthday)[:2]
    d = str(monthday)[2:]
    return f"{year}年{m}月{d}日"

def format_kaisai(row):
    """Kaiji, Nichiji, JyoCD から開催（"1回函館4日"）を生成"""
    kaiji = row.get('Kaiji')
    nichiji = row.get('Nichiji')
    jyo_cd = row.get('JyoCD')
    if pd.isna(kaiji) or pd.isna(nichiji) or pd.isna(jyo_cd):
        return ""
    place_name = PLACE_MAP.get(f"{int(jyo_cd):02d}", "")
    return f"{int(kaiji)}回{place_name}{int(nichiji)}日"

def format_track(track_cd):
    """TrackCD から 芝・ダート を生成"""
    try:
        cd = int(track_cd)
        if 10 <= cd <= 22:
            return "芝"
        elif 23 <= cd <= 29:
            return "ダート"
        else:
            return "障害"
    except Exception:
        return ""

def format_direction(track_cd):
    """TrackCD から 回り（右, 左, 直）を生成"""
    try:
        cd = int(track_cd)
        left = [11, 12, 13, 14, 21, 23, 25, 26]
        right = [15, 16, 17, 18, 20, 22, 24, 27, 28]
        straight = [19, 29]
        if cd in left:
            return "左"
        elif cd in right:
            return "右"
        elif cd in straight:
            return "直"
        else:
            return ""
    except Exception:
        return ""

def format_baba(row):
    """芝・ダートに応じて SibaBabaCD または DirtBabaCD から馬場状態を生成"""
    track_type = format_track(row.get('TrackCD'))
    cd = row.get('SibaBabaCD') if track_type == "芝" else row.get('DirtBabaCD')
    mapping = {"1": "良", "2": "稍重", "3": "重", "4": "不良"}
    return mapping.get(str(cd), "")

def format_weather(weather_cd):
    """TenkoCD から 天気 を生成"""
    mapping = {"1": "晴", "2": "曇", "3": "小雨", "4": "雨", "5": "小雪", "6": "雪"}
    return mapping.get(str(weather_cd), "")

def format_prize(honsyokin):
    """本賞金を100で割って万円単位（例: 580.0）に変換"""
    try:
        if not honsyokin or pd.isna(honsyokin):
            return "0.0"
        return f"{int(honsyokin) / 100.0:.1f}"
    except Exception:
        return "0.0"

def format_corner_passage_text(row):
    """Jyuni1〜Jyuni4 からコーナー通過順テキストを生成"""
    texts = []
    for i in range(1, 5):
        val = row.get(f'Jyuni{i}')
        if pd.notna(val) and val != "" and val != "0":
            texts.append(f"{i}コーナー:{val}")
    return " | ".join(texts) if texts else ""

def format_lap_times(row):
    """LapTime1〜LapTime25 からラップタイム文字列を生成"""
    laps = []
    for i in range(1, 26):
        val = row.get(f'LapTime{i}')
        if pd.notna(val) and val != "" and val != "000" and val != "0":
            try:
                laps.append(f"{int(val) / 10.0:.1f}")
            except Exception:
                pass
    return " - ".join(laps) if laps else ""

def format_race_pace(row):
    """HaronTimeS3 と HaronTimeL3 からレースペースを生成"""
    s3 = format_futan_or_haron(row.get('HaronTimeS3'))
    l3 = format_futan_or_haron(row.get('HaronTimeL3'))
    if s3 and l3:
        return f"{s3} - {l3}"
    return ""

def format_class(row):
    """JyokenName が空の場合に JyokenCD や SyubetuCD, Hondai からクラス名を推測して補完する"""
    name = row.get('JyokenName')
    if pd.notna(name) and name != "" and name != "nan":
        return name
        
    # クラスコードの取得 (JyokenCD5 が要約コードとして最も信頼性が高い)
    cd = row.get('JyokenCD5', '')
    if cd == '000' or cd == '' or pd.isna(cd):
        # もし JyokenCD5 が空なら、他のCD列から000以外の値を探す
        for col in ['JyokenCD4', 'JyokenCD3', 'JyokenCD2', 'JyokenCD1']:
            val = row.get(col, '')
            if val != '000' and val != '' and pd.notna(val):
                cd = val
                break

    syubetu = row.get('SyubetuCD', '')
    hondai = row.get('Hondai', '')
    
    # レース名に条件が含まれる場合の判定
    if pd.notna(hondai) and hondai != "":
        if "新馬" in hondai:
            return "新馬"
        if "未勝利" in hondai:
            return "未勝利"
        if "1勝" in hondai or "500万" in hondai:
            return "1勝クラス"
        if "2勝" in hondai or "1000万" in hondai:
            return "2勝クラス"
        if "3勝" in hondai or "1600万" in hondai:
            return "3勝クラス"
        
    if cd == '701':
        if syubetu == '11':
            return "2歳新馬"
        return "新馬"
    elif cd == '703' or cd == '003':
        if syubetu == '11':
            return "2歳未勝利"
        elif syubetu == '12':
            return "3歳未勝利"
        return "未勝利"
    elif cd == '005':
        return "1勝クラス"
    elif cd == '010':
        return "2勝クラス"
    elif cd == '016':
        return "3勝クラス"
    elif cd == '999':
        if syubetu == '39':
            return "障害"
        return "オープン"
    elif cd == '000' or cd == '':
        # 特別競走などでコードが000だがレース名がある場合はオープン扱い
        if pd.notna(hondai) and hondai != "":
            if syubetu == '39':
                return "障害"
            return "オープン"
        
    return ""

def main():
    print("=== CSVマージ＆フォーマット処理開始 ===")

    # 引数のチェック（YYYYMMDD形式）
    target_date_str = None
    if len(sys.argv) > 1:
        arg_date = sys.argv[1].strip()
        if len(arg_date) == 8 and arg_date.isdigit():
            target_date_str = arg_date
            print(f"指定された日付でマージを行います: {target_date_str}")
        else:
            print("[警告] 引数は YYYYMMDD 形式（例: 20260531）で指定してください。自動検出にフォールバックします。")

    output_dir = os.path.join("data", "SQL_data")

    # 対象ファイルの決定
    if not target_date_str:
        import glob
        import re
        # races_*.csv ファイルを検索して最新日付を見つける
        files = glob.glob(os.path.join(output_dir, "races_*.csv"))
        dates = []
        for f in files:
            m = re.search(r'races_(\d{8})\.csv', os.path.basename(f))
            if m:
                dates.append(m.group(1))
        
        if not dates:
            # フォールバック処理 (古い固定名のファイル)
            races_file = os.path.join(output_dir, "races_test.csv")
            shusso_uma_file = os.path.join(output_dir, "shusso_uma_test.csv")
            output_file = os.path.join(output_dir, "merged_races_test.csv")
            print("日付付きファイルが見つかりません。デフォルトの races_test.csv / shusso_uma_test.csv を使用します。")
        else:
            dates.sort()
            target_date_str = dates[-1]
            print(f"自動検出された最新日付を使用します: {target_date_str}")
            
    if target_date_str:
        races_file = os.path.join(output_dir, f"races_{target_date_str}.csv")
        shusso_uma_file = os.path.join(output_dir, f"shusso_uma_{target_date_str}.csv")
        output_file = os.path.join(output_dir, f"merged_races_{target_date_str}.csv")

    if not os.path.exists(races_file) or not os.path.exists(shusso_uma_file):
        print(f"[エラー] 入力ファイルが見つかりません。")
        print(f"期待したファイル:")
        print(f"  - {races_file} (存在: {os.path.exists(races_file)})")
        print(f"  - {shusso_uma_file} (存在: {os.path.exists(shusso_uma_file)})")
        return

    # UTF-8 (BOM付き) から読み込み
    print("CSVデータを読み込み中...")
    df_race = pd.read_csv(races_file, dtype=str)
    df_uma = pd.read_csv(shusso_uma_file, dtype=str)

    # 結合キーの指定
    join_keys = ['Year', 'MonthDay', 'JyoCD', 'Kaiji', 'Nichiji', 'RaceNum']
    print(f"レースデータ件数: {len(df_race)} 件")
    print(f"出走馬データ件数: {len(df_uma)} 件")

    # マージの実行
    print("データをマージ中...")
    df_merged = pd.merge(df_uma, df_race, on=join_keys, how='inner', suffixes=('', '_race'))
    print(f"マージ後レコード数: {len(df_merged)} 件")

    if df_merged.empty:
        print("[エラー] 結合結果が空です。キーの値が一致しているか確認してください。")
        return

    # 各列のフォーマット変換
    print("フォーマット変換処理を実行中...")
    
    # 1. race_id の生成
    df_merged['race_id'] = df_merged.apply(
        lambda r: f"{r['Year']}{int(r['JyoCD']):02d}{int(r['Kaiji']):02d}{int(r['Nichiji']):02d}{int(r['RaceNum']):02d}", 
        axis=1
    )

    # 各種マッピングの適用
    df_merged['馬'] = df_merged['Bamei']
    df_merged['horse_id'] = df_merged['KettoNum']
    df_merged['騎手'] = df_merged['KisyuRyakusyo']
    df_merged['jockey_id'] = df_merged['KisyuCode']
    df_merged['馬番'] = df_merged['Umaban'].apply(lambda x: str(int(x)) if pd.notna(x) and x != "" else "")
    df_merged['走破時間'] = df_merged['Time'].apply(format_time)
    df_merged['オッズ'] = df_merged['Odds'].apply(format_odds)
    df_merged['通過順'] = df_merged.apply(format_passage, axis=1)
    df_merged['着順'] = df_merged['KakuteiJyuni'].apply(lambda x: str(int(x)) if pd.notna(x) and x != "" and x != "00" else "")
    df_merged['体重'] = df_merged['BaTaijyu'].apply(lambda x: str(int(x)) if pd.notna(x) and x != "" and x != "000" else "")
    df_merged['体重変化'] = df_merged.apply(format_weight_diff, axis=1)
    df_merged['性'] = df_merged['SexCD'].apply(format_sex)
    df_merged['齢'] = df_merged['Barei'].apply(lambda x: str(int(x)) if pd.notna(x) and x != "" else "")
    df_merged['斤量'] = df_merged['Futan'].apply(format_futan_or_haron)
    df_merged['上がり'] = df_merged['HaronTimeL3'].apply(format_futan_or_haron)
    df_merged['人気'] = df_merged['Ninki'].apply(lambda x: str(int(x)) if pd.notna(x) and x != "" and x != "00" else "")
    df_merged['レース名'] = df_merged['Hondai']
    df_merged['日付'] = df_merged.apply(format_date, axis=1)
    df_merged['開催'] = df_merged.apply(format_kaisai, axis=1)
    df_merged['クラス'] = df_merged.apply(format_class, axis=1)
    df_merged['芝・ダート'] = df_merged['TrackCD'].apply(format_track)
    df_merged['距離'] = df_merged['Kyori']
    df_merged['回り'] = df_merged['TrackCD'].apply(format_direction)
    df_merged['馬場'] = df_merged.apply(format_baba, axis=1)
    df_merged['天気'] = df_merged['TenkoCD'].apply(format_weather)
    df_merged['場id'] = df_merged['JyoCD'].apply(lambda x: str(int(x)) if pd.notna(x) and x != "" else "")
    df_merged['場名'] = df_merged['JyoCD'].apply(lambda x: PLACE_MAP.get(f"{int(x):02d}", ""))
    df_merged['調教師'] = df_merged['ChokyosiRyakusyo']
    df_merged['trainer_id'] = df_merged['ChokyosiCode']
    df_merged['馬主'] = df_merged['BanusiName']
    df_merged['owner_id'] = df_merged['BanusiCode']
    df_merged['賞金'] = df_merged['Honsyokin'].apply(format_prize)
    df_merged['corner_passage_text'] = df_merged.apply(format_corner_passage_text, axis=1)
    df_merged['lap_times'] = df_merged.apply(format_lap_times, axis=1)
    df_merged['race_pace'] = df_merged.apply(format_race_pace, axis=1)

    # 出力列の順序を定義 (netkeiba形式のcsv_headerに完全一致させる)
    csv_header = [
        'race_id', '馬', 'horse_id', '騎手', 'jockey_id', '馬番', '走破時間', 'オッズ', 
        '通過順', '着順', '体重', '体重変化', '性', '齢', '斤量', '上がり', 
        '人気', 'レース名', '日付', '開催', 'クラス', '芝・ダート', '距離', '回り', 
        '馬場', '天気', '場id', '場名', '調教師', 'trainer_id', '馬主', 'owner_id', 
        '賞金', 'corner_passage_text', 'lap_times', 'race_pace'
    ]

    # 指定された列のみを抽出し、列順を固定
    df_output = df_merged[csv_header]

    # Shift-JIS (CP932) で保存 (errors='replace' が効かないので、念のためエラー時対策として cp932 でエンコードできない文字を置換)
    print("CSVファイルへの書き出し中...")
    
    # NaNを空文字列に置換
    df_output = df_output.fillna("")

    # SHIFT-JISで出力 (既存の netkeiba_parser / 過去データと完全に一致させるため)
    try:
        df_output.to_csv(output_file, index=False, encoding="SHIFT-JIS")
        print(f"[成功] CSV出力を完了しました: {output_file}")
    except UnicodeEncodeError as e:
        print(f"[警告] SHIFT-JISエンコードエラーが発生しました。代替文字への置換を行います。")
        # cp932 エンコードできない文字列を置換して保存するフォールバック処理
        for col in df_output.columns:
            df_output[col] = df_output[col].apply(
                lambda x: str(x).encode('cp932', errors='replace').decode('cp932') if isinstance(x, str) else x
            )
        df_output.to_csv(output_file, index=False, encoding="SHIFT-JIS")
        print(f"[成功] CSV出力を完了しました(代替文字置換あり): {output_file}")

    # プレビュー表示
    print("\n=== 変換後データのプレビュー ===")
    print(df_output[['race_id', '馬', '馬番', '走破時間', '着順', '人気', 'レース名', '日付', '芝・ダート']].head(5))

    print("\n=== CSVマージ＆フォーマット処理終了 ===")

if __name__ == "__main__":
    main()
