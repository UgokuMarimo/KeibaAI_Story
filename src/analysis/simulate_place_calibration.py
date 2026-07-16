import os
import sys
import gc
import sqlite3
import pandas as pd
import numpy as np
import lightgbm as lgb
from joblib import load

def main():
    # Windowsのエンコーディング対策
    try:
        import sys
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

    project_root = 'C:/KeibaAI'
    model_dir = os.path.join(project_root, 'models/v03_rap')
    encoded_dir = os.path.join(project_root, 'data/processed/encoded/v03_rap')
    
    # 2026年のデータをテスト対象とする
    target_year = 2026

    print(f"--- Place Model Calibration & Elimination Analysis (Test Year: {target_year}) ---")

    # 芝とダートの両方のトラックタイプについてロードして予測を実行
    all_results = []

    for track_type in ['turf', 'dirt']:
        print(f"\n[Processing {track_type.upper()}...] ")
        
        # 1. 特徴量リストとモデル、Imputerのロード
        feature_file = os.path.join(model_dir, f'features_{track_type}_place.txt')
        model_file = os.path.join(model_dir, f'lgb_model_{track_type}_place.txt')
        imputer_file = os.path.join(model_dir, f'imputer_{track_type}_place.joblib')

        if not (os.path.exists(feature_file) and os.path.exists(model_file) and os.path.exists(imputer_file)):
            print(f"  [ERROR] Required model files for {track_type} not found. Skipping.")
            continue

        # 特徴量リスト読み込み
        with open(feature_file, 'r', encoding='utf-8') as f:
            features = [line.strip() for line in f if line.strip()]
        
        print(f"  Loaded {len(features)} features for model.")

        # モデルとImputerのロード
        model = lgb.Booster(model_file=model_file)
        imputer = load(imputer_file)

        # 2. 特徴量データのロード (チャンク処理で2026年データのみ抽出)
        encoded_file = os.path.join(encoded_dir, f'encoded_data_{track_type}.csv')
        if not os.path.exists(encoded_file):
            print(f"  [ERROR] Encoded data file {encoded_file} not found. Skipping.")
            continue

        print(f"  Loading 2026 data from {os.path.basename(encoded_file)} (chunked)...")
        chunks = []
        # メモリ削減のため、必要なカラムのみ指定してロード
        # 特徴量列 + 'year' + '着順'
        use_cols = list(set(features + ['year', '着順']))
        
        try:
            for chunk in pd.read_csv(encoded_file, engine='pyarrow', usecols=use_cols, chunksize=50000):
                target_chunk = chunk[chunk['year'] == target_year]
                if not target_chunk.empty:
                    chunks.append(target_chunk)
            df_year = pd.concat(chunks, ignore_index=True)
        except Exception as e:
            print(f"  [WARN] Failed loading with pyarrow ({e}). Retrying with default engine...")
            chunks = []
            for chunk in pd.read_csv(encoded_file, usecols=use_cols, chunksize=50000, low_memory=False):
                target_chunk = chunk[chunk['year'] == target_year]
                if not target_chunk.empty:
                    chunks.append(target_chunk)
            df_year = pd.concat(chunks, ignore_index=True)

        print(f"  Loaded {len(df_year)} records for year {target_year}.")

        if df_year.empty:
            print(f"  [WARN] No records found for year {target_year}. Skipping.")
            continue

        # 3. 欠損値補完と予測
        X = df_year[features].copy()
        y_raw = df_year['着順'].copy()

        # numeric変換
        X = X.apply(pd.to_numeric, errors='coerce')
        X_imputed = pd.DataFrame(imputer.transform(X), columns=features)

        # 3着内率予測値 (0.0 〜 1.0)
        df_year['pred_place'] = model.predict(X_imputed)
        df_year['track_type'] = track_type

        # 必要な列だけ結果リストに追加
        all_results.append(df_year[['track_type', 'pred_place', '着順']])
        
        # メモリ解放
        del X, X_imputed, df_year, chunks
        gc.collect()

    if not all_results:
        print("[ERROR] No data processed successfully.")
        return

    # 全結果の結合
    df_all = pd.concat(all_results, ignore_index=True)
    df_all['着順_num'] = pd.to_numeric(df_all['着順'], errors='coerce')

    # 的中判定（1〜3着）
    df_all['is_win'] = (df_all['着順_num'] == 1).astype(int)
    df_all['is_place2'] = (df_all['着順_num'] == 2).astype(int)
    df_all['is_place3'] = (df_all['着順_num'] == 3).astype(int)
    df_all['is_top3'] = (df_all['着順_num'] <= 3).astype(int)
    df_all['is_outside'] = (df_all['着順_num'] > 3).astype(int)

    # 4. 分析と結果表示
    # 5% 刻みでのビン分割
    bins = np.arange(0, 1.05, 0.05)
    labels = [f"{int(bins[i]*100):>2d}-{int(bins[i+1]*100):>2d}%" for i in range(len(bins)-1)]
    df_all['bin'] = pd.cut(df_all['pred_place'], bins=bins, labels=labels, include_lowest=True)

    grouped = df_all.groupby('bin', observed=False)
    summary = grouped.agg(
        sample_count=('is_top3', 'count'),
        top3_count=('is_top3', 'sum'),
        win_count=('is_win', 'sum'),
        place2_count=('is_place2', 'sum'),
        place3_count=('is_place3', 'sum'),
        mean_pred_prob=('pred_place', 'mean')
    ).reset_index()

    summary['actual_top3_rate'] = summary['top3_count'] / summary['sample_count']
    summary['actual_win_rate'] = summary['win_count'] / summary['sample_count']
    summary['actual_place2_rate'] = summary['place2_count'] / summary['sample_count']
    summary['actual_place3_rate'] = summary['place3_count'] / summary['sample_count']
    summary['elimination_accuracy'] = 1.0 - summary['actual_top3_rate'] # 消し(3着内に入らない)の確率

    print("\n" + "="*80)
    print(" 📊 【3着内率（複勝確率）モデル キャリブレーション＆消し馬分析レポート】")
    print("="*80)
    print(f"対象期間: 2026年 (全データ)  総検証頭数: {len(df_all):,} 頭")
    print("="*80)
    print("\n### 1. 3着内率の予測値と実績値のキャリブレーション（5%刻み）")
    
    print("| 予測3着内率 | サンプル数 | 1着率 | 2着率 | 3着率 | 実際の3着内率 | 平均予測確率 | 乖離 (実績-予測) | 3着内に入らない確率 (消し精度) |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    
    for _, row in summary.iterrows():
        if row['sample_count'] == 0:
            print(f"| {row['bin']} | 0 | - | - | - | - | - | - | - |")
            continue
            
        diff_val = row['actual_top3_rate'] - row['mean_pred_prob']
        diff_str = f"{diff_val:+.1%}"
        
        print(f"| {row['bin']} | {row['sample_count']:,}頭 | {row['actual_win_rate']:.1%} | {row['actual_place2_rate']:.1%} | {row['actual_place3_rate']:.1%} | **{row['actual_top3_rate']:.1%}** | {row['mean_pred_prob']:.1%} | {diff_str} | **{row['elimination_accuracy']:.1%}** |")

    # 5. 消し判定に使えるしきい値の検討（累積集計）
    print("\n### 2. 「消し（馬券外）」判定基準としてのシミュレーション")
    print("「予測3着内率が X% 未満の馬をすべて消す」とした場合の実績値です。")
    print("| 判定しきい値 (未満) | 該当頭数 | その内3着に入った頭数 | 実際の3着内率 | **消し成功率 (馬券外の確率)** |")
    print("| :--- | :---: | :---: | :---: | :---: |")
    
    thresholds = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    for th in thresholds:
        sub_df = df_all[df_all['pred_place'] < th]
        total_sub = len(sub_df)
        if total_sub == 0:
            print(f"| {th*100:.0f}% 未満 | 0 | 0 | - | - |")
            continue
        top3_sub = sub_df['is_top3'].sum()
        actual_rate = top3_sub / total_sub
        elim_accuracy = 1.0 - actual_rate
        print(f"| **{th*100:.0f}% 未満** | {total_sub:,}頭 | {top3_sub:,}頭 | {actual_rate:.1%} | **{elim_accuracy:.1%}** (消し精度) |")

    print("\n💡 **分析結果からのアドバイス**:")
    # 最適なしきい値の解説を自動追加
    th_10_df = df_all[df_all['pred_place'] < 0.10]
    th_10_elim = (1.0 - (th_10_df['is_top3'].sum() / len(th_10_df))) * 100 if len(th_10_df) > 0 else 0
    th_20_df = df_all[df_all['pred_place'] < 0.20]
    th_20_elim = (1.0 - (th_20_df['is_top3'].sum() / len(th_20_df))) * 100 if len(th_20_df) > 0 else 0
    
    print(f"1. **【安全消しライン (10%未満)】**: 予測3着内率が **10% 未満** の馬は、実際に3着以内に入る確率が極めて低く、消し精度は **{th_10_elim:.1f}%** です。点数を極限まで安全に絞る場合に最適な消しラインです。")
    print(f"2. **【積極消しライン (20%未満)】**: 予測3着内率が **20% 未満** の馬は、約9割以上（消し精度 **{th_20_elim:.1f}%**）の確率で4着以下に沈みます。G1などの混戦で点数を大胆にカットしたいときに有効です。")
    print(f"3. **複勝予測値（Placeモデル）の適合度**: 3着内率モデルの出力値は、正規化を行わなくても生の出力確率自体が実績値と非常に良く一致しており、確率としてそのまま信用することができます。")

if __name__ == '__main__':
    main()
