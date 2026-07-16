# C:\KeibaAI\src\voting\direct_vote_runner.py
import os
import sys

# 標準出力の文字化け対策（Windows用）
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

import argparse

# プロジェクトパス設定
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

# .env ファイルの明示的なロード
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, '.env'))
except ImportError:
    print("[DIRECT-RUNNER WARN] python-dotenv is not installed. Environment variables might not load correctly.")

import config

# 念のためインポートを動的に解決
try:
    from voting.umaca_voter import UmacaVoter
except ImportError:
    sys.path.append(os.path.join(PROJECT_ROOT, 'voting'))
    from umaca_voter import UmacaVoter

def parse_args():
    parser = argparse.ArgumentParser(description="JRA UMACA Direct Bet Runner (単勝直接投票ツール / 多点買い対応)")
    parser.add_argument(
        '--production',
        action='store_true',
        help="【警告】本番のJRAサーバーに対して実際に投票（購入）を行います。指定しない場合はローカルHTMLモックを使用した模擬テストになります。"
    )
    parser.add_argument(
        '--race-id',
        type=str,
        help="12桁のレースID。例: 202605030107 (2026年3回東京1日目 7R)"
    )
    parser.add_argument(
        '--umaban',
        type=str,  # カンマ区切り対応のため str
        help="購入する馬番。単数: 1 、多点買い: 4,7,12 のようにカンマ区切りで入力"
    )
    parser.add_argument(
        '--amount',
        type=int,
        default=100,
        help="1点あたりの購入金額（円単位）。100円単位で指定。デフォルトは 100"
    )
    return parser.parse_args()

def interactive_input():
    print("\n========================================================")
    print("      JRA UMACA スマート 単勝直接自動投票ランナー")
    print("========================================================\n")

    # 1. 動作モードの選択
    mode_input = input("動作モードを選んでください (1: 平日模擬モックテスト [安全], 2: 本番投票 [実際にお金が動きます]): ").strip()
    is_production = (mode_input == "2")

    # 2. レースIDの入力
    print("\n■ レースIDの入力（12桁: 年[4桁] + 競馬場ID[2桁] + 回[2桁] + 日[2桁] + レース[2桁]）")
    print("   主要場ID: 05=東京, 09=京都, 06=中山, 08=阪神, 01=札幌, 02=函館, 03=福島, 04=新潟, 07=中京, 10=小倉")
    print("   例: 202605021204 -> 2回東京12日目 4R")
    race_id = input("レースIDを入力してください: ").strip()
    while len(race_id) != 12 or not race_id.isdigit():
        race_id = input("【エラー】12桁の半角数字で正しく入力してください: ").strip()

    # 3. 馬番の入力（カンマ区切りで複数可）
    print("\n■ 馬番の入力（1頭のみ: 1  / 多点買い: 4,7,12 のようにカンマ区切り）")
    umaban_input = input("購入する馬番を入力してください (例: 1 または 4,7,12): ").strip()
    umaban_list = []
    while True:
        try:
            umaban_list = [int(x.strip()) for x in umaban_input.split(',') if x.strip()]
            if umaban_list and all(1 <= u <= 18 for u in umaban_list):
                break
        except ValueError:
            pass
        umaban_input = input("【エラー】馬番は1~18の半角数字、カンマ区切りで入力してください: ").strip()

    # 4. 金額の入力（1点あたり）
    amount_str = input("\n1点あたりの購入金額を入力してください（円単位、100の倍数、例: 100）: ").strip()
    while not amount_str.isdigit() or int(amount_str) % 100 != 0 or int(amount_str) <= 0:
        amount_str = input("【エラー】100円単位の正の整数で入力してください: ").strip()
    amount = int(amount_str)

    return is_production, race_id, umaban_list, amount

def main():
    args = parse_args()

    # コマンドライン引数が一部でも指定されていない場合は対話モードを起動
    if not args.race_id or not args.umaban:
        is_production, race_id, umaban_list, amount = interactive_input()
    else:
        is_production = args.production
        race_id = args.race_id
        umaban_list = [int(x.strip()) for x in args.umaban.split(',') if x.strip()]
        amount = args.amount

    total_cost = amount * len(umaban_list)

    print("\n========================================================")
    print("  [FINAL CHECK] 投票実行パラメーターの最終確認:")
    print(f"    - 動作モード: {'[本番投票] JRA本番サーバー接続' if is_production else '[平日模擬テスト] ローカルモック接続'}")
    print(f"    - レースID  : {race_id}")
    print(f"    - 購入点数  : {len(umaban_list)}点 (馬番: {', '.join(str(u) for u in umaban_list)})")
    print(f"    - 1点金額  : {amount:,} 円 (単勝)")
    print(f"    - 合計金額  : {total_cost:,} 円")
    print("========================================================\n")

    confirm = input("上記のパラメータで投票操作を実行します。よろしいですか？(y/n): ").strip().lower()
    if confirm != 'y':
        print("実行をキャンセルしました。")
        return

    use_mock = not is_production

    print("\n[DIRECT-RUNNER] JRA UMACA Voter エンジンを起動します...")
    voter = UmacaVoter(use_mock=use_mock)

    card_no = os.getenv("UMACA_CARD_NUMBER", "")
    birthday = os.getenv("UMACA_BIRTHDAY", "")
    security_code = os.getenv("UMACA_SECURITY_CODE", "")

    if not card_no or not birthday or not security_code:
        if use_mock:
            os.environ["UMACA_CARD_NUMBER"] = "110002378622"
            os.environ["UMACA_BIRTHDAY"] = "20030214"
            os.environ["UMACA_SECURITY_CODE"] = "4041"
            print("[DIRECT-RUNNER MOCK] .env 認証情報が空のため、テスト用のダミーアカウントを一時セットしました。")
        else:
            print("[DIRECT-RUNNER ERROR] .env ファイルに UMACA ログイン情報が設定されていません。")
            print("UMACA_CARD_NUMBER, UMACA_BIRTHDAY, UMACA_SECURITY_CODE の設定が必要です。")
            return

    success = False
    try:
        # 1. ログイン
        print("[DIRECT-RUNNER] ログイン中...")
        if not voter.login():
            print("[DIRECT-RUNNER ERROR] ログインに失敗しました。")
            return

        # 2. 残高チェック
        print("[DIRECT-RUNNER] 口座残高を取得中...")
        balance = voter.get_balance()
        print(f"[DIRECT-RUNNER] 口座/UMACA残高: {balance:,} 円")

        if balance < total_cost:
            print(f"[DIRECT-RUNNER ERROR] 残高不足です。必要な金額: {total_cost:,} 円, 現在の残高: {balance:,} 円")
            return

        # 3. 投票リストの構築（各馬番に同じ金額）
        bets = [
            {'umaban': u, 'bet_type': 'win', 'amount': amount}
            for u in umaban_list
        ]

        print(f"\n[DIRECT-RUNNER] {len(bets)}点買いの投票ナビゲーションを開始します。ブラウザ画面をじっくり見守ってください。")
        success = voter.vote(race_id, bets)

        if success:
            print("\n[SUCCESS] 【大成功】 投票操作シーケンスが完璧に完了しました！")
            new_balance = voter.get_balance()
            print(f"[DIRECT-RUNNER] 投票後の残高: {new_balance:,} 円 (減算: {balance - new_balance:,} 円)")
        else:
            print("\n[FAILED] 【失敗】 投票操作シーケンスの途中でエラーが発生しました。")

    except Exception as e:
        print(f"[DIRECT-RUNNER ERROR] 予期せぬ致命的なエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\n[DIRECT-RUNNER] セッションを終了し、ブラウザをクローズします...")
        voter.close()
        print("[DIRECT-RUNNER] 終了。")

if __name__ == "__main__":
    main()
