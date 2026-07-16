import sqlite3
import pandas as pd
import numpy as np
import os
import sys

def main():
    # Windowsのエンコーディング対策
    try:
        import sys
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

    # パス設定
    db_path = 'C:/KeibaAI/predictions.db'
    raw_2026_path = 'C:/KeibaAI/data/raw/2026.csv'
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return
    if not os.path.exists(raw_2026_path):
        print(f"Error: Raw results CSV not found at {raw_2026_path}")
        return
        
    print("Loading predictions from SQLite...")
    # 1. 予測値データのロード
    with sqlite3.connect(db_path) as conn:
        df_preds = pd.read_sql_query("SELECT race_id, umaban, horse_name, pred_win, kaisai_date FROM predictions", conn)
    
    print(f"Loaded {len(df_preds)} prediction records.")
    
    # 2. 同じレース内での予測勝率を正規化 (合計が1になるようにする)
    # レースごとの合計値を計算
    df_preds['sum_pred_win'] = df_preds.groupby('race_id')['pred_win'].transform('sum')
    # 正規化した勝率
    df_preds['normalized_pred_win'] = df_preds['pred_win'] / df_preds['sum_pred_win']
    
    print("Loading race results from 2026.csv...")
    # 3. 2026年実績データのロード
    # 列名の対応
    # 0: race_id, 5: 馬番, 9: 着順
    df_results = pd.read_csv(raw_2026_path, encoding='cp932', usecols=['race_id', '馬番', '着順'])
    df_results.rename(columns={'馬番': 'umaban', '着順': 'result_rank'}, inplace=True)
    
    # 型を揃える
    df_preds['race_id'] = df_preds['race_id'].astype(str)
    df_preds['umaban'] = pd.to_numeric(df_preds['umaban'], errors='coerce')
    df_results['race_id'] = df_results['race_id'].astype(str)
    df_results['umaban'] = pd.to_numeric(df_results['umaban'], errors='coerce')
    
    # 着順を数値型に変換 (除外や中止などはNaNになる)
    df_results['result_rank_num'] = pd.to_numeric(df_results['result_rank'], errors='coerce')
    # 1着判定
    df_results['actual_win'] = (df_results['result_rank_num'] == 1).astype(int)
    
    print(f"Loaded {len(df_results)} result records.")
    
    # 4. データのマージ
    df_merged = pd.merge(df_preds, df_results[['race_id', 'umaban', 'actual_win', 'result_rank_num']], on=['race_id', 'umaban'], how='inner')
    print(f"Successfully matched {len(df_merged)} horses ({len(df_merged['race_id'].unique())} races) with actual results.")
    
    if len(df_merged) == 0:
        print("Warning: No matching records found between predictions and results.")
        return
        
    # 5. キャリブレーション分析 (5% 刻み)
    # ビン分割用の閾値
    bins = np.arange(0, 1.05, 0.05)
    labels = [f"{int(bins[i]*100):>2d}-{int(bins[i+1]*100):>2d}%" for i in range(len(bins)-1)]
    
    # 5-1. 生の予測勝率での集計
    df_merged['bin_raw'] = pd.cut(df_merged['pred_win'], bins=bins, labels=labels, include_lowest=True)
    
    # 5-2. 正規化した予測勝率での集計
    df_merged['bin_norm'] = pd.cut(df_merged['normalized_pred_win'], bins=bins, labels=labels, include_lowest=True)
    
    # 分析結果作成関数
    def analyze_calibration(df, bin_col, prob_col):
        grouped = df.groupby(bin_col, observed=False)
        summary = grouped.agg(
            sample_count=('actual_win', 'count'),
            win_count=('actual_win', 'sum'),
            mean_pred_prob=(prob_col, 'mean')
        ).reset_index()
        
        summary['actual_win_rate'] = summary['win_count'] / summary['sample_count']
        summary['diff'] = summary['actual_win_rate'] - summary['mean_pred_prob']
        return summary
        
    print("\n=== Calibration Analysis (Raw Prediction Win Probability) ===")
    summary_raw = analyze_calibration(df_merged, 'bin_raw', 'pred_win')
    print_markdown_table(summary_raw)
    
    print("\n=== Calibration Analysis (Normalized Prediction Win Probability) ===")
    summary_norm = analyze_calibration(df_merged, 'bin_norm', 'normalized_pred_win')
    print_markdown_table(summary_norm)

def print_markdown_table(df):
    print("| 予測勝率範囲 | サンプル数 (頭) | 勝利数 (頭) | 実際の勝率 | 平均予測勝率 | 乖離 (実績 - 予測) | 簡易グラフ |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: | :--- |")
    for _, row in df.iterrows():
        if row['sample_count'] == 0:
            print(f"| {row.iloc[0]} | 0 | 0 | - | - | - | |")
            continue
            
        diff_val = row['diff']
        diff_str = f"{diff_val:+.1%}" if pd.notna(diff_val) else "-"
        
        # グラフ作成
        actual = row['actual_win_rate']
        pred = row['mean_pred_prob']
        # 20文字のバーで表現
        bar_len = 20
        actual_bars = int(actual * bar_len)
        pred_bars = int(pred * bar_len)
        
        graph = ""
        for i in range(bar_len):
            if i < min(actual_bars, pred_bars):
                graph += "o" # 両方重なっている部分
            elif i < actual_bars:
                graph += "+" # 実績の方が高い部分
            elif i < pred_bars:
                graph += "-" # 予測の方が高い部分
            else:
                graph += "."
                
        print(f"| {row.iloc[0]} | {row['sample_count']:,} | {row['win_count']:,} | {row['actual_win_rate']:.1%} | {row['mean_pred_prob']:.1%} | {diff_str} | `{graph}` |")

if __name__ == '__main__':
    main()
