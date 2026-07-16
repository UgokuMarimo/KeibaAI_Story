
"""
レースの展開・ペース・質を分析するためのロジックモジュール。
主な機能：
1. ラップタイム文字列("12.3 - 11.4 ...")からのペース判定
2. ラップ構成の分類（瞬発力戦 vs 消耗戦）
3. コーナー通過順の解析（位置取りの変遷）
"""

import math
import re

# --- Constants for Pace Analysis ---
LAP_BASELINE = 12.0
LAP_FAST_THRESHOLD = 11.4
LAP_SLOW_THRESHOLD = 12.5

class RacePaceCategory:
    HIGH_STAMINA = "High (Stamina)"         # 消耗戦 (前半が速い)
    AVERAGE = "Average"                     # 平均ペース
    SLOW_INSTANT = "Slow (Instant)"         # 瞬発力戦 (前半が遅い)
    UNKNOWN = "Unknown"

def _clean_lap_string(lap_str: str) -> list[float]:
    """ラップタイム文字列を数値リストに変換"""
    if not lap_str or not isinstance(lap_str, str):
        return []
    # 全角スペース、ハイフンなどをカンマに正規化
    cleaned = lap_str.replace(' ', '').replace('-', ',')
    try:
        return [float(x) for x in cleaned.split(',') if x]
    except ValueError:
        return []

def analyze_race_pace(lap_times_str: str) -> dict:
    """
    ラップタイム文字列を受け取り、レースの質の分析結果を返す。
    
    Returns:
        dict: {
            "category": RacePaceCategory,
            "flow": list[str], # ['Slow', 'Fast', ...]
            "stats": {
                "first_3f": float,
                "last_3f": float,
                "diff": float  # First3F - Last3F (Plus = Slow Start/Rear-loaded)
            }
        }
    """
    laps = _clean_lap_string(lap_times_str)
    if not laps:
        return {
            "category": RacePaceCategory.UNKNOWN, 
            "flow": [], 
            "stats": {"first_3f": 0, "last_3f": 0, "diff": 0}
        }

    # 1. ラップごとの質の分類 (Visual Flow)
    # 1F 12.0秒基準
    # <= 11.4: Fast (無酸素)
    # 11.5 - 12.4: Avg
    # >= 12.5: Slow (有酸素)
    flow = []
    for l in laps:
        if l <= LAP_FAST_THRESHOLD:
            flow.append("Fast")
        elif l >= LAP_SLOW_THRESHOLD:
            flow.append("Slow")
        else:
            flow.append("Avg")

    # 2. ペース判定 (前半3F vs 後半3F)
    # 距離が短い場合(3F未満)は判定不能だが、通常はありえない
    if len(laps) >= 3:
        first_3f = sum(laps[:3])
        last_3f = sum(laps[-3:])
        diff = first_3f - last_3f
    else:
        first_3f = sum(laps)
        last_3f = sum(laps)
        diff = 0

    # 判定ロジック
    # diff > 0: 前半の方が時間がかかっている = スローペース (瞬発力戦になりやすい)
    # diff < 0: 前半の方が速い = ハイペース (消耗戦になりやすい)
    # 閾値は ±1.5秒 (0.5秒/F x 3) とする
    
    if diff >= 1.5:
        category = RacePaceCategory.SLOW_INSTANT # "後傾ラップ"
    elif diff <= -1.5:
        category = RacePaceCategory.HIGH_STAMINA # "前傾ラップ"
    else:
        category = RacePaceCategory.AVERAGE

    # 補正: 全体の平均タイムが極端に速い/遅い場合の調整などが必要ならここに追加
    
    return {
        "category": category,
        "flow": flow,
        "stats": {
            "first_3f": round(first_3f, 1),
            "last_3f": round(last_3f, 1),
            "diff": round(diff, 1)
        }
    }

def format_corner_passage(passage_text: str) -> str:
    """
    コーナー通過順テキストを、LLMが理解しやすい要約形式に変換する。
    例: "3コーナー:(*5,2)(3,4)..." -> "3角先頭(5,2), 4角先頭(5,2)"
    """
    if not passage_text or not isinstance(passage_text, str):
        return ""
        
    summary_parts = []
    corners = passage_text.split('|')
    
    for c in corners:
        parts = c.split(':')
        if len(parts) != 2: continue
        corner_name = parts[0].strip().replace("コーナー", "角")
        order_str = parts[1].strip()
        
        # 先頭集団だけ抽出 (最初のカッコ、または最初の数字群)
        # (*5,2) -> 5,2
        first_group = re.search(r'[\(\[\（]([\d,]+)[\)\]\）]', order_str)
        leading_horses = ""
        
        if first_group:
            leading_horses = first_group.group(1)
        else:
            # カッコがない場合は最初の数字だけ
            match = re.search(r'^\s*(\d+)', order_str)
            if match:
                leading_horses = match.group(1)
        
        if leading_horses:
            summary_parts.append(f"{corner_name}先頭[{leading_horses}]")
            
    return ", ".join(summary_parts)
