# C:\KeibaAI\src\analysis\loss_streak_detailed.py
import sys

def calc_streak_prob(p, M, N):
    """
    的中率 p のとき、M回の試行の中で、
    「少なくとも1回は N連敗以上」が発生する確率を動的計画法で計算する。
    """
    q = 1.0 - p
    dp = [0.0] * N
    dp[0] = 1.0 # 初期状態 (0連敗)
    reached = 0.0

    for _ in range(M):
        next_dp = [0.0] * N
        next_reached = reached
        
        for j in range(N):
            prob = dp[j]
            if prob == 0.0:
                continue
            
            # 的中した場合 (確率 p) -> 0連敗に戻る
            next_dp[0] += prob * p
            
            # 外れた場合 (確率 q) -> 連敗数が +1 になる
            if j + 1 < N:
                next_dp[j + 1] += prob * q
            else:
                next_reached += prob * q
                
        dp = next_dp
        reached = next_reached
        
    return reached

def main():
    # 的中率のリスト (8.5% から 6.0% まで 0.5% 刻み)
    hit_rates = [0.085, 0.080, 0.075, 0.070, 0.065, 0.060]
    
    # 期間 (1ヶ月: 150レース, 3ヶ月: 450レース, 6ヶ月: 900レース)
    periods = [
        ("1ヶ月 (150レース)", 150),
        ("3ヶ月 (450レース)", 450),
        ("6ヶ月 (900レース)", 900)
    ]
    
    # 検証する連敗数
    streaks = [30, 40, 50, 60, 70, 80, 90, 100]

    for p in hit_rates:
        print(f"\n==============================================")
        print(f" 的中率: {p*100:.1f}% のシミュレーション")
        print(f"==============================================")
        print(f"【期間内で少なくとも1回は N連敗以上 を経験する確率】")
        print("-" * 75)
        print("{:<8} | {:<18} | {:<18} | {:<18}".format("連敗数(N)", "1ヶ月(150R)", "3ヶ月(450R)", "6ヶ月(900R)"))
        print("-" * 75)
        
        for N in streaks:
            p1 = calc_streak_prob(p, 150, N) * 100
            p2 = calc_streak_prob(p, 450, N) * 100
            p3 = calc_streak_prob(p, 900, N) * 100
            print("{:<8} | {:<18.2f}% | {:<18.2f}% | {:<18.2f}%".format(
                f"{N}連敗", p1, p2, p3
            ))

if __name__ == '__main__':
    main()
