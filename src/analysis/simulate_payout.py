import sqlite3
import pandas as pd
import numpy as np
import sys
import os

# プロジェクトパス設定
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from src.a4_prediction.probability_calculator import ProbabilityCalculator

def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    conn = sqlite3.connect('predictions.db')
    
    # 実際の結果（result_rank）が1〜3着まで確定している予測レコードを取得
    query = """
    SELECT race_id, umaban, pred_win, result_rank 
    FROM predictions 
    WHERE result_rank IS NOT NULL AND result_rank > 0
    """
    df = pd.read_sql_query(query, conn)
    
    # payouts（払い戻し情報）テーブルもロード
    payout_df = pd.read_sql_query("SELECT * FROM payouts", conn)
    payout_dict = payout_df.set_index('race_id').to_dict('index')
    
    race_ids = df['race_id'].unique()
    
    # 各式別の成績集計用 (1点買いシミュレーション: 各レース予測確率が最大の1点のみ購入)
    stats = {
        'tansho': {'name': '単勝 (AI1番人気)', 'hits': 0, 'pay': 0},
        'umaren': {'name': '馬連 (AI予測確率最大)', 'hits': 0, 'pay': 0},
        'umatan': {'name': '馬単 (AI予測確率最大)', 'hits': 0, 'pay': 0},
        'sanrenpuku': {'name': '3連複 (AI予測確率最大)', 'hits': 0, 'pay': 0},
        'sanrentan': {'name': '3連単 (AI予測確率最大)', 'hits': 0, 'pay': 0},
    }
    
    total_races = 0
    
    # 確率キャリブレーション分析用（AIが算出した予測確率と、実際の的中率の整合性）
    buckets = [0.0, 0.02, 0.05, 0.10, 0.20, 0.35, 1.0]
    bucket_stats = {
        'umaren': {b: {'trials': 0, 'hits': 0} for b in buckets[:-1]},
        'umatan': {b: {'trials': 0, 'hits': 0} for b in buckets[:-1]},
        'sanrenpuku': {b: {'trials': 0, 'hits': 0} for b in buckets[:-1]},
        'sanrentan': {b: {'trials': 0, 'hits': 0} for b in buckets[:-1]},
    }
    
    def get_bucket(prob):
        for i in range(len(buckets)-1):
            if buckets[i] <= prob < buckets[i+1]:
                return buckets[i]
        return buckets[-2]

    for race_id in race_ids:
        race_data = df[df['race_id'] == race_id]
        
        # 1着と2着のレコードが揃っていることを確認
        ranks = race_data['result_rank'].values
        if not (1 in ranks and 2 in ranks):
            continue
            
        has_third = 3 in ranks
        
        # 1, 2, 3着の馬番を特定
        first_umaban = int(race_data[race_data['result_rank'] == 1]['umaban'].iloc[0])
        second_umaban = int(race_data[race_data['result_rank'] == 2]['umaban'].iloc[0])
        third_umaban = int(race_data[race_data['result_rank'] == 3]['umaban'].iloc[0]) if has_third else None
        
        # AI予測値の辞書作成 {umaban: pred_win}
        win_probs = {int(row['umaban']): float(row['pred_win']) for _, row in race_data.iterrows()}
        
        # 確率計算機のロード (Harvilleの公式)
        try:
            calc = ProbabilityCalculator(win_probs)
        except Exception:
            continue
            
        total_races += 1
        payouts = payout_dict.get(race_id, {})
        
        # --- 1. 単勝の検証 ---
        sorted_win = sorted(win_probs.items(), key=lambda x: x[1], reverse=True)
        ai_first_horse = sorted_win[0][0]
        is_win_hit = (ai_first_horse == first_umaban)
        stats['tansho']['hits'] += is_win_hit
        if is_win_hit:
            stats['tansho']['pay'] += payouts.get('tansho_payout', 0)
            
        # --- 2. 馬連の検証 ---
        umaren_probs = calc.get_all_quinella_probs()
        if not umaren_probs.empty:
            best_umaren = umaren_probs.iloc[0]
            ai_u1, ai_u2 = int(best_umaren['1頭目']), int(best_umaren['2頭目'])
            u_prob = best_umaren['probability']
            
            real_u1, real_u2 = sorted([first_umaban, second_umaban])
            is_umaren_hit = (sorted([ai_u1, ai_u2]) == [real_u1, real_u2])
            
            stats['umaren']['hits'] += is_umaren_hit
            if is_umaren_hit:
                stats['umaren']['pay'] += payouts.get('umaren_payout', 0)
                
            b = get_bucket(u_prob)
            bucket_stats['umaren'][b]['trials'] += 1
            bucket_stats['umaren'][b]['hits'] += is_umaren_hit
            
        # --- 3. 馬単の検証 ---
        umatan_probs = calc.get_all_exacta_probs()
        if not umatan_probs.empty:
            best_umatan = umatan_probs.iloc[0]
            ai_ut1, ai_ut2 = int(best_umatan['1着']), int(best_umatan['2着'])
            ut_prob = best_umatan['probability']
            
            is_umatan_hit = (ai_ut1 == first_umaban and ai_ut2 == second_umaban)
            stats['umatan']['hits'] += is_umatan_hit
            if is_umatan_hit:
                stats['umatan']['pay'] += payouts.get('umatan_payout', 0)
                
            b = get_bucket(ut_prob)
            bucket_stats['umatan'][b]['trials'] += 1
            bucket_stats['umatan'][b]['hits'] += is_umatan_hit
            
        # --- 4. 3連複の検証 ---
        if has_third:
            trio_probs = calc.get_all_trio_probs()
            if not trio_probs.empty:
                best_trio = trio_probs.iloc[0]
                ai_t1, ai_t2, ai_t3 = int(best_trio['1頭目']), int(best_trio['2頭目']), int(best_trio['3頭目'])
                t_prob = best_trio['probability']
                
                real_t1, real_t2, real_t3 = sorted([first_umaban, second_umaban, third_umaban])
                is_trio_hit = (sorted([ai_t1, ai_t2, ai_t3]) == [real_t1, real_t2, real_t3])
                
                stats['sanrenpuku']['hits'] += is_trio_hit
                if is_trio_hit:
                    stats['sanrenpuku']['pay'] += payouts.get('sanrenpuku_payout', 0)
                    
                b = get_bucket(t_prob)
                bucket_stats['sanrenpuku'][b]['trials'] += 1
                bucket_stats['sanrenpuku'][b]['hits'] += is_trio_hit
                
        # --- 5. 3連単の検証 ---
        if has_third:
            trifecta_probs = calc.get_all_trifecta_probs()
            if not trifecta_probs.empty:
                best_trifecta = trifecta_probs.iloc[0]
                ai_tf1, ai_tf2, ai_tf3 = int(best_trifecta['1着']), int(best_trifecta['2着']), int(best_trifecta['3着'])
                tf_prob = best_trifecta['probability']
                
                is_trifecta_hit = (ai_tf1 == first_umaban and ai_tf2 == second_umaban and ai_tf3 == third_umaban)
                stats['sanrentan']['hits'] += is_trifecta_hit
                if is_trifecta_hit:
                    stats['sanrentan']['pay'] += payouts.get('sanrentan_payout', 0)
                    
                b = get_bucket(tf_prob)
                bucket_stats['sanrentan'][b]['trials'] += 1
                bucket_stats['sanrentan'][b]['hits'] += is_trifecta_hit
                
    conn.close()
    
    print("\n" + "="*60)
    print(f"📊 競馬AI マルチ系馬券 シミュレーション結果 (検証レース数: {total_races} レース)")
    print("="*60)
    
    for key, val in stats.items():
        hit_rate = val['hits'] / total_races if total_races > 0 else 0
        total_investment = total_races * 100
        recovery_rate = val['pay'] / total_investment if total_investment > 0 else 0
        print(f"■ {val['name']}:")
        print(f"  - 的中率: {hit_rate:.2%} ({val['hits']}/{total_races} 的中)")
        print(f"  - 回収率: {recovery_rate:.2%} (総投資: {total_investment:,}円 / 総払戻: {val['pay']:,}円)")
        print("-" * 40)
        
    print("\n" + "="*60)
    print("📈 AI予測確率（Harville計算確率）と、実際の的中率の関係検証 (精度分析)")
    print("="*60)
    for bet_type in ['umaren', 'umatan', 'sanrenpuku', 'sanrentan']:
        type_name = "馬連" if bet_type == 'umaren' else "馬単" if bet_type == 'umatan' else "3連複" if bet_type == 'sanrenpuku' else "3連単"
        print(f"\n📌 [{type_name} 予測確率帯ごとの実際の的中割合]")
        for b in buckets[:-1]:
            b_data = bucket_stats[bet_type][b]
            trials = b_data['trials']
            hits = b_data['hits']
            actual_rate = hits / trials if trials > 0 else 0.0
            print(f"  - 計算確率 {b:.0%} 〜 {buckets[buckets.index(b)+1]:.0%}: 実際の的中率 {actual_rate:.2%} (分母: {trials} レース中 {hits} 的中)")
            
if __name__ == '__main__':
    main()
