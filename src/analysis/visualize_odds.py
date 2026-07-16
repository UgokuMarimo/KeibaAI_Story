# C:\KeibaAI\scratch\visualize_odds.py
import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# プロジェクトパス設定
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..'))
sys.path.append(PROJECT_ROOT)

# 日本語フォントの設定（Windows標準のMS Gothicなどを指定）
plt.rcParams['font.family'] = 'MS Gothic'
plt.rcParams['axes.unicode_minus'] = False

def visualize_race_odds(race_id: str, race_name: str):
    csv_path = f"C:/KeibaAI/data/odds_history/odds_{race_id}.csv"
    if not os.path.exists(csv_path):
        print(f"File not found: {csv_path}")
        return
        
    # 1. データの読み込み
    df = pd.read_csv(csv_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # 単勝オッズを数値に変換（'---'などの欠損値はNaNへ）
    df['単勝'] = pd.to_numeric(df['単勝'], errors='coerce')
    
    # 2. 上位人気馬（最終タイムスタンプでオッズが低い上位5頭）の抽出
    latest_time = df['timestamp'].max()
    latest_df = df[df['timestamp'] == latest_time]
    top_horses = latest_df.nsmallest(5, '単勝')['馬番'].tolist()
    
    # 3. グラフ描画
    plt.figure(figsize=(10, 6))
    
    # 分析用テキストデータの作成
    analysis_lines = []
    
    for umaban in top_horses:
        horse_data = df[df['馬番'] == umaban].sort_values('timestamp')
        horse_name = horse_data['馬名'].iloc[0]
        
        # オッズの最初と最後
        first_odds = horse_data['単勝'].iloc[0]
        last_odds = horse_data['単勝'].iloc[-1]
        diff = last_odds - first_odds
        pct_change = (diff / first_odds) * 100
        
        label = f"{umaban}番 {horse_name} (最終 {last_odds:.1f}倍)"
        plt.plot(horse_data['timestamp'], horse_data['単勝'], marker='o', label=label, linewidth=2)
        
        analysis_lines.append({
            'umaban': umaban,
            'name': horse_name,
            'first': first_odds,
            'last': last_odds,
            'diff': diff,
            'pct': pct_change
        })
        
    plt.title(f"{race_name} (ID: {race_id}) 上位人気馬のオッズ推移 (発走15分前～直前)", fontsize=14)
    plt.xlabel("取得時刻", fontsize=12)
    plt.ylabel("単勝オッズ (倍)", fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.legend(loc='upper right', fontsize=10)
    
    # 横軸のフォーマットをHH:MMに設定
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    plt.gca().xaxis.set_major_locator(mdates.MinuteLocator(interval=2))
    plt.gcf().autofmt_xdate() # ラベルの重なりを防ぐ斜め表示
    
    save_path = f"C:/KeibaAI/data/odds_history/odds_trend_{race_id}.png"
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"\n--- {race_name} 分析データ ---")
    for a in analysis_lines:
        trend_str = "下落 (売れた)" if a['diff'] < 0 else "上昇 (不人気化)"
        if abs(a['diff']) < 0.01:
            trend_str = "横ばい"
        print(f"  * {a['umaban']}番 {a['name']}: {a['first']:.1f}倍 -> {a['last']:.1f}倍 "
              f"(差: {a['diff']:+.1f}倍, 変化率: {a['pct']:.1f}%) [{trend_str}]")

if __name__ == "__main__":
    # matplotlibが入っているか確認
    try:
        import matplotlib
    except ImportError:
        print("installing matplotlib...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "matplotlib"])
        
    # 2つの12Rを可視化
    visualize_race_odds("202609030112", "阪神12R")
    visualize_race_odds("202605030112", "東京12R")
