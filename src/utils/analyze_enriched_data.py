
"""
enrichment_YYYY.csv のデータを読み込み、
1. ラップタイムの分析（ペース判定: S/M/H, 瞬発力 vs 持久力）
2. コーナー通過順の解析（逃げ/先行/差し/追込 の傾向把握など）
を行い、結果を表示するスクリプト。

主な機能:
- parse_lap_times: "12.3 - 11.4 - ..." 文字列をリストに変換
- classify_pace: 前半3Fと後半3Fの比較などでペースを分類
- parse_corner_passage: "3コーナー:(*5,2)..." を解析可能な構造にする（通過ごとの各馬の位置）
"""

import pandas as pd
import re
import argparse
import os
import sys

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
import config

def parse_lap_times(lap_str):
    if pd.isna(lap_str): return []
    # 全角スペースやハイフンを正規化
    cleaned = lap_str.replace(' ', '').replace('-', ',')
    # 数値を抽出
    try:
        laps = [float(x) for x in cleaned.split(',') if x]
        return laps
    except ValueError:
        return []

def analyze_pace(laps):
    """
    ラップタイムリストからペース特徴を抽出
    基準: 1F 12.0s
    """
    if not laps: return "Unknown", {}, []
    
    # 距離 (ラップ数 * 200m) ※実際は残り距離などで最後の区間が短い場合もあるが概算
    est_distance = len(laps) * 200 
    
    # 前半3F (最初から3つ) vs 後半3F (最後から3つ)
    # n個のラップがあるとき、start=0..2, end=n-3..n-1
    if len(laps) >= 3:
        first_3f = sum(laps[:3])
        last_3f = sum(laps[-3:])
        pace_diff = first_3f - last_3f # プラスなら「前半遅い＝Sペース（後傾）」、マイナスなら「前半速い＝Hペース（前傾）」
    else:
        first_3f, last_3f, pace_diff = 0, 0, 0

    # 個別ラップの評価
    lap_classifications = []
    for l in laps:
        if l <= 11.4: lap_classifications.append('Fast') # 無酸素・消耗
        elif l >= 12.5: lap_classifications.append('Slow') # 有酸素・回復
        else: lap_classifications.append('Avg')          # 平均

    # 総合判定
    pace_category = "Middle"
    if pace_diff >= 1.5: pace_category = "Slow (Instant)" # 瞬発力勝負
    elif pace_diff <= -1.5: pace_category = "High (Stamina)" # 消耗戦
    
    stats = {
        "first_3f": first_3f,
        "last_3f": last_3f,
        "diff": pace_diff,
        "dist_est": est_distance
    }
    
    return pace_category, stats, lap_classifications

def parse_corner_passage(passage_text):
    """
    "3コーナー:(*5,2)... | 4コーナー:..." 形式を解釈する
    非常に複雑な表記（例: 2(3,4)(5,6) など）があるため、
    「先頭集団(逃げ)」「中団」「後方」に大別できるか簡易チェックする
    """
    if pd.isna(passage_text): return None
    
    # コーナーごとに分割
    corners = passage_text.split('|')
    parsed_corners = {}
    
    for c in corners:
        parts = c.split(':')
        if len(parts) != 2: continue
        corner_name = parts[0].strip() # 3コーナー, 4コーナー etc
        order_str = parts[1].strip()
        
        # 簡易的に、先頭にいる馬番を抽出してみる
        # カッコや記号を除去して、最初の数字を取得
        # (*5,2) -> 5, 2
        # 正規表現ですべての数字を抽出
        all_horses_in_order = re.findall(r'\d+', order_str)
        
        parsed_corners[corner_name] = {
            "raw": order_str,
            "leading_group": all_horses_in_order[:3] if all_horses_in_order else []
        }
        
    return parsed_corners

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('file_path', help='Path to enrichment CSV file')
    parser.add_argument('--limit', type=int, default=10, help='Number of rows to inspect')
    args = parser.parse_args()

    if not os.path.exists(args.file_path):
        print(f"File not found: {args.file_path}")
        return

    # cp932で読み込み
    df = pd.read_csv(args.file_path, encoding='cp932')
    print(f"Loaded {len(df)} rows from {args.file_path}")
    
    # サンプル抽出
    sample = df.head(args.limit)
    
    print("\n=== Analysis Results (Sample) ===\n")
    
    for idx, row in sample.iterrows():
        print(f"Race ID: {row['race_id']}")
        
        # 1. Lap Time Analysis
        laps = parse_lap_times(row['lap_times'])
        pace_cat, stats, lap_classes = analyze_pace(laps)
        
        print(f"  [Lap Analysis] Category: {pace_cat}")
        print(f"    - First 3F: {stats['first_3f']:.1f}s / Last 3F: {stats['last_3f']:.1f}s (Diff: {stats['diff']:+.1f}s)")
        print(f"    - Flow: {' -> '.join(lap_classes)}")
        
        # 2. Corner Passage Analysis
        corners = parse_corner_passage(row['corner_passage_text'])
        print(f"  [Corner Analysis]")
        if corners:
            for c_name, data in corners.items():
                print(f"    - {c_name}: Leading {data['leading_group']} (Raw: {data['raw']})")
        else:
            print("    - No corner data")
            
        print("-" * 50)

if __name__ == "__main__":
    main()
