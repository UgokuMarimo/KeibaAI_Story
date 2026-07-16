def calc_streak_prob(p, M, N):
    """
    的中率 p のとき、M回の購入（試行）の中で、
    「少なくとも1回は N連敗以上」が発生する確率を動的計画法で計算する。
    """
    q = 1.0 - p
    # dp[i][j] : i回目に、現在の末尾の連続連敗数が j (0 <= j < N) である確率
    # ただし最大連敗数がすでに N 以上に達した確率は別で管理 (reached)
    dp = [0.0] * N
    dp[0] = 1.0 # 初期状態 (0連敗)
    reached = 0.0

    for _ in range(M):
        next_dp = [0.0] * N
        next_reached = reached # すでに連敗達成した状態はそのまま引き継ぐ
        
        for j in range(N):
            prob = dp[j]
            if prob == 0.0:
                continue
            
            # 1. 的中した場合 (確率 p) -> 連敗数が 0 に戻る
            next_dp[0] += prob * p
            
            # 2. 外れた場合 (確率 q) -> 連敗数が j + 1 になる
            if j + 1 < N:
                next_dp[j + 1] += prob * q
            else:
                next_reached += prob * q
                
        dp = next_dp
        reached = next_reached
        
    return reached

# 的中率 8.5% (p = 0.085)
p = 0.085

# 購入回数 M のバリエーション
# 19回 (1日分), 152回 (1ヶ月分), 456回 (3ヶ月分)
runs = [
    ("1日 (19頭購入)", 19),
    ("1ヶ月 (152頭購入)", 152),
    ("3ヶ月 (456頭購入)", 456)
]

print("=== STREAK SIMULATION (Hit Rate = 8.5%) ===")
print("各期間において、「少なくとも1回は N連敗以上」を経験する確率")
print("-" * 75)
print("{:<8} | {:<18} | {:<18} | {:<18}".format("連敗数(N)", "1日分(19頭中)", "1ヶ月分(152頭中)", "3ヶ月分(456頭中)"))
print("-" * 75)

for N in [5, 10, 15, 20, 25, 30, 35, 40, 50]:
    p1 = calc_streak_prob(p, 19, N) * 100
    p2 = calc_streak_prob(p, 152, N) * 100
    p3 = calc_streak_prob(p, 456, N) * 100
    print("{:<8} | {:<18.2f}% | {:<18.2f}% | {:<18.2f}%".format(
        f"{N}連敗", p1, p2, p3
    ))
