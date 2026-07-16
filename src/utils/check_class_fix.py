
import pandas as pd
import sys
import os

# プロジェクトルートをパスに追加
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.utils.feature_pipeline import class_mapping

def test_class_mapping():
    test_cases = [
        {"レース名": "JBCクラシック(Jpn1)", "クラス": "オープン", "芝・ダート": "ダ", "expected": 8},
        {"レース名": "帝王賞(JpnI)", "クラス": "オープン", "芝・ダート": "ダ", "expected": 8},
        {"レース名": "東京大賞典(G1)", "クラス": "オープン", "芝・ダート": "ダ", "expected": 8},
        {"レース名": "かしわ記念(Jpn1)", "クラス": "オープン", "芝・ダート": "ダ", "expected": 8},
        {"レース名": "日本テレビ盃(Jpn2)", "クラス": "オープン", "芝・ダート": "ダ", "expected": 7},
        {"レース名": "兵庫チャンピオンシップ(JpnII)", "クラス": "オープン", "芝・ダート": "ダ", "expected": 7},
        {"レース名": "サウジカップ(G1)", "クラス": "オープン", "芝・ダート": "ダ", "expected": 8},        
        {"レース名": "ドバイワールドカップ(G1)", "クラス": "オープン", "芝・ダート": "ダ", "expected": 8},
        # 既存のテストケース
        {"レース名": "日本ダービー(GI)", "クラス": "オープン", "芝・ダート": "芝", "expected": 8},
        {"レース名": "毎日王冠(GII)", "クラス": "オープン", "芝・ダート": "芝", "expected": 7},
        {"レース名": "平場戦", "クラス": "3勝クラス", "芝・ダート": "ダ", "expected": 4},
        {"レース名": "平場戦", "クラス": "新馬", "芝・ダート": "芝", "expected": 0},
    ]

    print("--- Testing class_mapping ---")
    all_passed = True
    for case in test_cases:
        row = pd.Series(case)
        result = class_mapping(row)
        is_pass = result == case["expected"]
        status = "✅ PASS" if is_pass else f"❌ FAIL (Expected {case['expected']}, Got {result})"
        print(f"Race: {case['レース名']:<25} | Result: {result} | {status}")
        if not is_pass:
            all_passed = False

    if all_passed:
        print("\n🎉 All tests passed!")
    else:
        print("\n⚠️ Some tests failed.")

if __name__ == "__main__":
    test_class_mapping()
