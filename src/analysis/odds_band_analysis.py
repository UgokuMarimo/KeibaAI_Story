# C:\KeibaAI\src\analysis\odds_band_analysis.py
"""
オッズ帯別 的中率・回収率分析スクリプト

predictions.db の predictions テーブルを使用して：
- AI予測上位馬（pred_rank=1）のオッズ帯別 的中率・回収率を集計
- 「仮に期待値しきい値で購入していたら」のシミュレーション結果を出力
"""

import sys
import os
import sqlite3
import pandas as pd
import numpy as np

_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SRC_DIR)

import config

# Windows端末のエンコード対策
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def load_data() -> pd.DataFrame:
    """predictionsテーブルを読み込み、前処理を行う"""
    conn = sqlite3.connect(config.DB_PATH)
    df = pd.read_sql("""
        SELECT 
            race_id, umaban, kaisai_date, keibajo,
            race_number, track_type, race_class,
            pred_win, pred_rank,
            tansho_odds, tansho_ninki, result_rank
        FROM predictions
        WHERE result_rank IS NOT NULL  -- 結果が確定しているレースのみ
          AND tansho_odds IS NOT NULL
          AND tansho_odds > 0
    """, conn)
    conn.close()
    return df

def analyze(df: pd.DataFrame, target_ev: float = 1.0, min_win_prob: float = 0.10,
            min_odds: float = 0.0, max_odds: float = 999.0):
    """
    オッズ帯別の的中率・回収率を分析する。
    
    分析対象: pred_rank=1（AI最上位予測馬）かつ pred_win が正規化勝率として使える場合
    """
    print(f"\n{'='*65}")
    print(f"  📊 オッズ帯別 的中率・回収率分析")
    print(f"  データ件数: {len(df):,} 頭 (結果確定済み)")
    print(f"  期間: {df['kaisai_date'].min()} 〜 {df['kaisai_date'].max()}")
    print(f"{'='*65}\n")

    # 正規化勝率を race_id ごとに計算
    df = df.copy()
    race_sums = df.groupby('race_id')['pred_win'].transform('sum')
    df['pred_win_prob'] = df['pred_win'] / race_sums.where(race_sums > 0, 1)

    # 的中フラグ（1着）
    df['is_win'] = (df['result_rank'] == 1).astype(int)

    # ========================================
    # [1] AI最上位予測馬（pred_rank=1）の分析
    # ========================================
    top1 = df[df['pred_rank'] == 1].copy()
    total_top1 = len(top1)
    wins_top1 = top1['is_win'].sum()
    print(f"【AI 1位予測馬 全体】")
    print(f"  対象レース数: {total_top1:,}")
    print(f"  的中数      : {wins_top1:,}")
    print(f"  的中率      : {wins_top1/total_top1:.1%}")
    payout_top1 = (top1[top1['is_win']==1]['tansho_odds'] * 100).sum()
    invest_top1 = total_top1 * 100
    print(f"  回収率      : {payout_top1/invest_top1:.1%} (全頭100円ずつ購入した場合)\n")

    # ========================================
    # [2] オッズ帯別の的中率・回収率（全予測馬対象 / EV基準フィルター）
    # ========================================
    # EV計算
    df['ev'] = df['pred_win_prob'] * df['tansho_odds']

    # EV基準でフィルタリング（期待値購入シミュレーション）
    ev_targets = df[
        (df['pred_win_prob'] >= min_win_prob) &
        (df['ev'] >= target_ev) &
        (df['tansho_odds'] >= min_odds) &
        (df['tansho_odds'] <= max_odds)
    ].copy()

    print(f"【期待値購入シミュレーション (EV>={target_ev}, 勝率>={min_win_prob:.0%})】")
    print(f"  対象馬数: {len(ev_targets):,} 頭")
    if len(ev_targets) > 0:
        wins_ev = ev_targets['is_win'].sum()
        invest_ev = len(ev_targets) * 100
        payout_ev = (ev_targets[ev_targets['is_win']==1]['tansho_odds'] * 100).sum()
        print(f"  的中数  : {wins_ev:,}")
        print(f"  的中率  : {wins_ev/len(ev_targets):.1%}")
        print(f"  投資額  : {invest_ev:,} 円")
        print(f"  回収額  : {payout_ev:,.0f} 円")
        print(f"  回収率  : {payout_ev/invest_ev:.1%}")
    print()

    # ========================================
    # [3] オッズ帯別の詳細集計（EV基準フィルター後）
    # ========================================
    bins   = [0, 2, 4, 6, 8, 10, 15, 20, 30, 50, 999]
    labels = ['~2', '2~4', '4~6', '6~8', '8~10', '10~15', '15~20', '20~30', '30~50', '50~']

    if len(ev_targets) == 0:
        print("EV基準を満たす馬が存在しません。")
        return

    ev_targets['odds_band'] = pd.cut(
        ev_targets['tansho_odds'], bins=bins, labels=labels, right=False
    )

    summary = ev_targets.groupby('odds_band', observed=True).agg(
        購入点数=('is_win', 'count'),
        的中数=('is_win', 'sum'),
        平均EV=('ev', 'mean'),
        平均オッズ=('tansho_odds', 'mean'),
    ).reset_index()

    summary['的中率'] = summary['的中数'] / summary['購入点数']
    summary['投資額'] = summary['購入点数'] * 100

    # 回収額の計算（的中したときのオッズ×100）
    def calc_payout(group):
        return (group[group['is_win'] == 1]['tansho_odds'] * 100).sum()

    payouts = ev_targets.groupby('odds_band', observed=True).apply(calc_payout).reset_index()
    payouts.columns = ['odds_band', '回収額']
    summary = summary.merge(payouts, on='odds_band')
    summary['回収率'] = summary['回収額'] / summary['投資額']

    # 表示
    print(f"【オッズ帯別 詳細（EV>={target_ev} / 勝率>={min_win_prob:.0%}）】")
    print(f"{'オッズ帯':>8} {'点数':>5} {'的中':>5} {'的中率':>7} {'平均EV':>7} {'回収率':>7} {'投資額':>8} {'回収額':>8}")
    print("-" * 65)
    for _, row in summary.iterrows():
        if row['購入点数'] == 0:
            continue
        mark = " ✅" if row['回収率'] >= 1.0 else ("  ⚠" if row['回収率'] >= 0.7 else "  ❌")
        print(f"{str(row['odds_band']):>8}倍  {row['購入点数']:>4}  {row['的中数']:>4}  "
              f"{row['的中率']:>6.1%}  {row['平均EV']:>6.2f}  {row['回収率']:>6.1%}  "
              f"{row['投資額']:>7,}  {row['回収額']:>7,.0f}{mark}")

    print("-" * 65)
    print(f"{'合計':>8}   {summary['購入点数'].sum():>4}  {summary['的中数'].sum():>4}  "
          f"{summary['的中数'].sum()/summary['購入点数'].sum():>6.1%}  "
          f"{ev_targets['ev'].mean():>6.2f}  "
          f"{summary['回収額'].sum()/summary['投資額'].sum():>6.1%}  "
          f"{summary['投資額'].sum():>7,}  {summary['回収額'].sum():>7,.0f}")

    # ========================================
    # [4] 推奨設定の提案
    # ========================================
    print(f"\n{'='*65}")
    print(f"  💡 推奨オッズ帯（回収率70%以上のオッズ帯）")
    print(f"{'='*65}")
    good_bands = summary[(summary['的中率'] > 0) & (summary['回収率'] >= 0.70)]
    if len(good_bands) > 0:
        for _, row in good_bands.iterrows():
            print(f"  {str(row['odds_band']):>8}倍  的中率={row['的中率']:.1%}  回収率={row['回収率']:.1%}")
    else:
        print("  現状データでは回収率70%以上のオッズ帯はありません。")
        print("  → EV閾値を上げるか、データ蓄積を待つことを推奨します。")

    print(f"\n{'='*65}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="オッズ帯別 的中率・回収率分析")
    parser.add_argument('--ev', type=float, default=1.0, help="期待値しきい値 (default: 1.0)")
    parser.add_argument('--min-prob', type=float, default=0.10, help="最低勝率 (default: 0.10)")
    parser.add_argument('--min-odds', type=float, default=0.0, help="オッズ下限 (default: 0.0)")
    parser.add_argument('--max-odds', type=float, default=999.0, help="オッズ上限 (default: 999)")
    args = parser.parse_args()

    df = load_data()
    analyze(df, target_ev=args.ev, min_win_prob=args.min_prob,
            min_odds=args.min_odds, max_odds=args.max_odds)
