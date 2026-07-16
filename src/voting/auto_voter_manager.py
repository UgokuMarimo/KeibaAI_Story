# C:\KeibaAI\src\voting\auto_voter_manager.py
import os
import sys
import json
import pandas as pd
from datetime import date
from typing import List, Dict, Any, Optional

# プロジェクトパス設定
# _current_dir = src/voting/  →  PROJECT_ROOT = C:\KeibaAI（2階層上）
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import config
from utils.db_utils import send_discord_webhook, save_vote_to_db
from voting.voter_interface import BaseVoter
from voting.mock_voter import MockVoter

# 1日あたりの購入点数を追跡するファイルパス
_DAILY_BET_COUNTER_PATH = os.path.join(PROJECT_ROOT, 'data', 'daily_bet_counter.json')

def _load_daily_bet_info() -> Dict[str, Any]:
    """今日の投票情報（日付、件数、金額、上限予算）をファイルから読み込む"""
    today = date.today().isoformat()
    default_info = {'date': today, 'count': 0, 'amount': 0, 'limit_amount': None}
    try:
        if os.path.exists(_DAILY_BET_COUNTER_PATH):
            with open(_DAILY_BET_COUNTER_PATH, 'r') as f:
                data = json.load(f)
            if data.get('date') == today:
                # 必要なキーのデフォルト補完
                for k, v in default_info.items():
                    if k not in data:
                        data[k] = v
                return data
    except Exception:
        pass
    return default_info

def _save_daily_bet_info(info: Dict[str, Any]):
    """今日の投票情報をファイルに保存する"""
    try:
        os.makedirs(os.path.dirname(_DAILY_BET_COUNTER_PATH), exist_ok=True)
        with open(_DAILY_BET_COUNTER_PATH, 'w') as f:
            json.dump(info, f)
    except Exception as e:
        print(f"[AUTO-VOTER WARN] Failed to save daily bet info: {e}")


class AutoVoterManager:
    """
    AI予測スコアとオッズを元に、自動投票条件に合致する馬を抽出して
    投票エンジンへ発注する自動投票オーケストレーター。

    ■ 購入フィルター（多重安全チェーン）
    1. AI勝率  >= MIN_WIN_PROB (例: 10%)
    2. 期待値  >= TARGET_EV_VOTE (例: 1.2)
    3. オッズ  >= AUTO_VOTING_MIN_ODDS (例: 2.0倍)  ← 旨味のない本命を除外
    4. オッズ  <= AUTO_VOTING_MAX_ODDS (例: 15.0倍) ← 超高配当の不安定馬を除外
    5. EV降順ソート後 上位 MAX_HORSES_PER_RACE 頭のみ選出
    6. 当日購入点数が MAX_BETS_PER_DAY を超えていれば購入中止
    """

    def __init__(self, voter: BaseVoter = None, target_ev: float = None,
                 min_win_prob: float = None, default_amount: int = None):
        # 設定値の読み込み（引数指定がなければconfigから取得）
        self.target_ev    = target_ev    if target_ev    is not None else getattr(config, 'TARGET_EV_VOTE', 1.2)
        self.min_win_prob = min_win_prob if min_win_prob is not None else getattr(config, 'MIN_WIN_PROB', 0.10)
        self.default_amount = default_amount if default_amount is not None else getattr(config, 'AUTO_VOTING_BASE_AMOUNT', 100)
        self.max_horses      = getattr(config, 'AUTO_VOTING_MAX_HORSES_PER_RACE', 1)
        self.max_odds        = getattr(config, 'AUTO_VOTING_MAX_ODDS', 15.0)
        self.min_odds        = getattr(config, 'AUTO_VOTING_MIN_ODDS', 2.0)
        self.max_bets_per_day = getattr(config, 'AUTO_VOTING_MAX_BETS_PER_DAY', 5)
        self.max_amount_per_day = getattr(config, 'AUTO_VOTING_MAX_AMOUNT_PER_DAY', None)

        # 投票エンジンの決定
        if voter is not None:
            self.voter = voter
        else:
            mode = getattr(config, 'AUTO_VOTING_MODE', 'mock')
            if mode == 'umaca':
                try:
                    from voting.umaca_voter import UmacaVoter
                    self.voter = UmacaVoter()
                    print("[AUTO-VOTER] Instantiated UmacaVoter engine.")
                except ImportError as e:
                    print(f"[AUTO-VOTER ERROR] UmacaVoter module could not be imported: {e}")
                    # 本番投票モードでエラーが発生した場合、MockVoterへの自動フォールバックは危険なのでエラーを通知して中断する。
                    err_msg = f"🚨 **【AI自動投票 起動エラー】** 🚨\n本番投票モード(`umaca`)が指定されていますが、必要なモジュール(Playwright等)がインポートできませんでした。\nエラー内容: `{e}`\n本日の自動投票は実行されません。"
                    send_discord_webhook(err_msg, webhook_url=getattr(config, 'DISCORD_VOTE_WEBHOOK_URL', None))
                    raise e
            else:
                self.voter = MockVoter()
                print("[AUTO-VOTER] Instantiated MockVoter engine.")

    def process_race_prediction_unified(self, race_id: str, final_result_df: pd.DataFrame) -> bool:
        """
        【オッズ取得・投票判断の一本化フロー】
        1. ログインして対象レースの馬番選択画面に遷移する。
        2. 画面からリアルタイムオッズを直接取得する。
        3. 予測確率と最新オッズから期待値をその場で算出し、購入基準を満たした馬がいれば、
           そのまま同じブラウザセッション内で投票を確定させる。
        """
        print(f"\n--- [AUTO-VOTER UNIFIED] Evaluation for Race: {race_id} ---")
        
        # --- 1日あたりの投票枠（件数・金額）の確認 (ログイン前チェック) ---
        daily_info = _load_daily_bet_info()
        daily_count = daily_info['count']
        daily_amount = daily_info['amount']
        limit_amount = daily_info['limit_amount']

        if self.max_amount_per_day is not None and self.max_amount_per_day > 0:
            if limit_amount != self.max_amount_per_day:
                limit_amount = self.max_amount_per_day
                daily_info['limit_amount'] = limit_amount
                _save_daily_bet_info(daily_info)
        
        limit_str = f"{limit_amount:,}円" if limit_amount is not None else "自動取得"
        print(f"    Criteria: EV>={self.target_ev}, Prob>={self.min_win_prob:.0%}, "
              f"Odds {self.min_odds}~{self.max_odds}倍, MaxHorses={self.max_horses}/Race, "
              f"MaxBets={self.max_bets_per_day}/Day, DailyBudget={limit_str} (Used: {daily_amount:,}円)")

        # 点数上限チェック
        remaining_slots = self.max_bets_per_day - daily_count
        if remaining_slots <= 0:
            print(f"[AUTO-VOTER] Daily bet count limit reached ({daily_count}/{self.max_bets_per_day}). Skipping.")
            return True

        # 金額上限チェック
        if limit_amount is not None:
            remaining_budget = limit_amount - daily_amount
            if remaining_budget < 100:
                print(f"[AUTO-VOTER] Daily budget limit reached or insufficient. Skipping.")
                return True
        else:
            remaining_budget = 99999999

        # カラム名の解決
        prob_col = None
        for col in ['normalized_pred_win', 'pred_win_prob', 'win_prob', 'pred_win']:
            if col in final_result_df.columns:
                prob_col = col
                break
        if prob_col is None:
            print("[AUTO-VOTER ERROR] Prediction prob column not found.")
            return False

        umaban_col = 'umaban' if 'umaban' in final_result_df.columns else                      ('馬番' if '馬番' in final_result_df.columns else None)

        try:
            # 1. ログイン実行
            if not self.voter.login():
                print("[AUTO-VOTER ERROR] Login failed. Aborting.")
                return False

            # 自動予算枠の設定 (今日最初のログインで limit_amount がない場合)
            if limit_amount is None:
                limit_amount = self.voter.get_balance()
                daily_info['limit_amount'] = limit_amount
                _save_daily_bet_info(daily_info)
                remaining_budget = limit_amount - daily_amount
                print(f"[AUTO-VOTER] Initial budget set dynamically from balance: {limit_amount:,} 円")

            # 2. 対象レースの馬番選択画面へ移動
            bet_type = 'win'
            if not self.voter.navigate_to_race_and_bet_type(race_id, bet_type):
                print("[AUTO-VOTER ERROR] Navigation to race page failed.")
                self.voter.close()
                return False

            # 3. 画面上のリアルタイムオッズを取得
            odds_dict = self.voter.get_odds_from_page()
            if not odds_dict:
                print("[AUTO-VOTER ERROR] Could not retrieve odds from the page. Aborting.")
                self.voter.close()
                return False

            # 4. オッズをマージして期待値を動的に判定
            bets = []
            skipped_reasons = []
            for _, row in final_result_df.iterrows():
                try:
                    umaban = int(row[umaban_col]) if umaban_col else int(row.iloc[0])
                except (KeyError, ValueError):
                    umaban = int(row.iloc[0])

                horse_name = row.get('horse_name', row.get('馬名', '不明'))
                win_prob = float(row[prob_col])

                # 画面オッズを参照
                odds_raw = odds_dict.get(umaban)
                if odds_raw is None or odds_raw <= 0:
                    skipped_reasons.append(f"  {umaban}番 {horse_name}: オッズ取得不可 (または取消/除外)")
                    continue
                odds = float(odds_raw)
                ev = win_prob * odds

                # 判定フィルター
                if win_prob < self.min_win_prob:
                    skipped_reasons.append(f"  {umaban}番 {horse_name}: 勝率不足 ({win_prob:.1%} < {self.min_win_prob:.0%})")
                    continue
                if ev < self.target_ev:
                    skipped_reasons.append(f"  {umaban}番 {horse_name}: EV不足 ({ev:.2f} < {self.target_ev}, odds={odds:.1f})")
                    continue
                if odds < self.min_odds:
                    skipped_reasons.append(f"  {umaban}番 {horse_name}: オッズ低すぎ ({odds:.1f}倍 < {self.min_odds}倍)")
                    continue
                if odds > self.max_odds:
                    skipped_reasons.append(f"  {umaban}番 {horse_name}: オッズ高すぎ ({odds:.1f}倍 > {self.max_odds}倍)")
                    continue

                bets.append({
                    'umaban': umaban,
                    'horse_name': horse_name,
                    'win_prob': win_prob,
                    'odds': odds,
                    'ev': ev,
                    'bet_type': 'win',
                    'amount': self.default_amount
                })

            if skipped_reasons:
                print(f"[AUTO-VOTER] Filtered out {len(skipped_reasons)} horse(s) based on real-time page odds:")
                for r in skipped_reasons:
                    print(r)

            if not bets:
                print(f"[AUTO-VOTER] No horses passed all filters with real-time odds. Skipping vote.")
                self.voter.close()
                return True

            # EV降順ソート
            bets.sort(key=lambda x: x['ev'], reverse=True)
            
            # max_horses制限
            if len(bets) > self.max_horses:
                dropped = bets[self.max_horses:]
                bets = bets[:self.max_horses]
                print(f"[AUTO-VOTER] {len(dropped)} horse(s) dropped by MAX_HORSES limit:")
                for d in dropped:
                    print(f"  (dropped) {d['umaban']}番 {d['horse_name']} EV={d['ev']:.2f}")

            # 残り点数スロット制限
            if len(bets) > remaining_slots:
                print(f"[AUTO-VOTER] Daily limit slots restriction. Only {remaining_slots} slot(s) remain.")
                bets = bets[:remaining_slots]

            # 予算制限
            affordable_bets = []
            accumulated_cost = 0
            for bet in bets:
                cost = bet['amount']
                if accumulated_cost + cost <= remaining_budget:
                    affordable_bets.append(bet)
                    accumulated_cost += cost
                else:
                    print(f"  (dropped due to budget) {bet['umaban']}番 {bet['horse_name']} EV={bet['ev']:.2f}")
            bets = affordable_bets

            if not bets:
                print(f"[AUTO-VOTER] No affordable bets remain within daily budget.")
                self.voter.close()
                return True

            print(f"[AUTO-VOTER] {len(bets)} horse(s) confirmed for unified voting:")
            for idx, bet in enumerate(bets):
                print(f"  ({idx+1}) {bet['umaban']}番 {bet['horse_name']} "
                      f"(勝率: {bet['win_prob']:.1%}, オッズ: {bet['odds']:.1f}倍, EV: {bet['ev']:.2f})")

            # 5. そのまま同じ画面で投票処理へ進行
            clean_bets = [
                {'umaban': bet['umaban'], 'bet_type': bet['bet_type'], 'amount': bet['amount']}
                for bet in bets
            ]
            success = self.voter.vote_on_current_page(clean_bets)

            if success:
                new_count = daily_count + len(bets)
                new_amount = daily_amount + accumulated_cost
                daily_info['count'] = new_count
                daily_info['amount'] = new_amount
                _save_daily_bet_info(daily_info)

                # DBログ保存 (umaca の場合)
                mode = getattr(config, 'AUTO_VOTING_MODE', 'mock')
                if mode == 'umaca':
                    kaisai_date = date.today().isoformat()
                    from voting.auto_voter_manager import save_vote_to_db
                    for bet in bets:
                        try:
                            save_vote_to_db(
                                race_id=race_id,
                                umaban=bet['umaban'],
                                horse_name=bet['horse_name'],
                                kaisai_date=kaisai_date,
                                vote_type=bet['bet_type'],
                                vote_odds=bet['odds'],
                                pred_win_prob=bet['win_prob'],
                                amount=bet['amount'],
                                status='success',
                                mode=mode
                            )
                        except Exception as db_err:
                            print(f"[AUTO-VOTER ERROR] Failed to log vote to DB: {db_err}")

                # Discord完了通知の送信
                is_mock = isinstance(self.voter, MockVoter) or self.voter.use_mock
                title = "🤖 **【AI自動投票 完了通知 (シミュレーション/テスト)】** 🤖" if is_mock else "🤖 **【AI自動投票 完了通知】** 🤖"
                try:
                    course_id = race_id[4:6]
                    venue_name = config.PLACE_MAP_IDS.get(course_id, "不明")
                    kaisai = int(race_id[6:8])
                    nichi = int(race_id[8:10])
                    race_num = int(race_id[10:])
                    race_info_str = f"**{venue_name} {race_num}R** (第{kaisai}回 {nichi}日目)"
                except Exception:
                    race_info_str = f"不明なレース (ID: `{race_id}`)"

                discord_msg = f"{title}\n"
                discord_msg += f"レース: {race_info_str} | ID: `{race_id}`\n"
                discord_msg += "━" * 15 + "\n"
                for bet in bets:
                    discord_msg += (f"・ **{bet['umaban']}番 {bet['horse_name']}** "
                                    f"(オッズ: {bet['odds']:.1f}倍, EV: {bet['ev']:.2f}) "
                                    f"に **単勝 {bet['amount']:,}円** 💸\n")
                new_balance = self.voter.get_balance()
                discord_msg += "━" * 15 + "\n"
                discord_msg += f"🏦 **投票後残高**: {new_balance:,}円\n"
                limit_display_str = f"{limit_amount:,}円" if limit_amount is not None else "制限なし"
                discord_msg += f"📊 **本日購入累計**: {new_amount:,} / {limit_display_str} (点数: {new_count}/{self.max_bets_per_day}点)\n"

                from utils.db_utils import send_discord_webhook
                send_discord_webhook(discord_msg, webhook_url=getattr(config, 'DISCORD_VOTE_WEBHOOK_URL', None))
                print("[AUTO-VOTER] Automated voting completed and Discord notification sent!")
            else:
                print("[AUTO-VOTER ERROR] Vote transaction failed.")

            self.voter.close()
            return success

        except Exception as e:
            print(f"[AUTO-VOTER ERROR] Unified process failed: {e}")
            import traceback
            traceback.print_exc()
            self.voter.close()
            return False

    def process_race_prediction(self, race_id: str, final_result_df: pd.DataFrame) -> bool:
        """
        予測が完了したレースのデータフレームを受け取り、自動投票の判定と処理を行う。
        """
        print(f"\n--- [AUTO-VOTER] Evaluation for Race: {race_id} ---")
        
        # --- 1日あたりの投票枠（件数・金額）の確認 ---
        daily_info = _load_daily_bet_info()
        daily_count = daily_info['count']
        daily_amount = daily_info['amount']
        limit_amount = daily_info['limit_amount']

        # 予算上限の確定とロック（手動設定がある場合はそれを適用、無ければログインして投票専用残高Aから取得）
        if self.max_amount_per_day is not None and self.max_amount_per_day > 0:
            # 手動設定がある場合、更新されていればファイルに上書き
            if limit_amount != self.max_amount_per_day:
                limit_amount = self.max_amount_per_day
                daily_info['limit_amount'] = limit_amount
                _save_daily_bet_info(daily_info)
        else:
            # 手動設定がない（自動設定）場合
            if limit_amount is None:
                # 今日最初の投票時: ログインして投票専用残高を取得する
                print("[AUTO-VOTER] Auto budget limit is enabled. Connecting to JRA to fetch initial Bet Dedicated balance...")
                try:
                    if self.voter.login():
                        if hasattr(self.voter, 'get_bet_dedicated_balance'):
                            limit_amount = self.voter.get_bet_dedicated_balance()
                        else:
                            limit_amount = self.voter.get_balance()
                        
                        daily_info['limit_amount'] = limit_amount
                        _save_daily_bet_info(daily_info)
                        print(f"[AUTO-VOTER] Initial Bet Dedicated balance set as today's budget limit: {limit_amount:,} 円")
                    else:
                        print("[AUTO-VOTER ERROR] Failed to login to fetch initial balance. Budget check might be bypassed or fail.")
                except Exception as e:
                    print(f"[AUTO-VOTER ERROR] Failed to initialize daily budget limit: {e}")
                finally:
                    self.voter.close()

        limit_str = f"{limit_amount:,}円" if limit_amount is not None else "自動取得（ログイン後にロックされます）"
        print(f"    Criteria: EV>={self.target_ev}, Prob>={self.min_win_prob:.0%}, "
              f"Odds {self.min_odds}~{self.max_odds}倍, MaxHorses={self.max_horses}/Race, "
              f"MaxBets={self.max_bets_per_day}/Day, DailyBudget={limit_str} (Used: {daily_amount:,}円)")

        # --- 上限チェック（件数制限） ---
        remaining_slots = self.max_bets_per_day - daily_count
        if remaining_slots <= 0:
            print(f"[AUTO-VOTER] Daily bet count limit reached ({daily_count}/{self.max_bets_per_day}). Skipping race {race_id}.")
            return True

        # --- 上限チェック（金額予算制限） ---
        if limit_amount is not None:
            remaining_budget = limit_amount - daily_amount
            if remaining_budget < 100: # 最低賭け金100円未満
                print(f"[AUTO-VOTER] Daily budget limit reached or insufficient (Used: {daily_amount:,} / Limit: {limit_amount:,} 円, Remaining: {remaining_budget:,} 円). Skipping race {race_id} without login (Safety).")
                return True
        else:
            remaining_budget = 99999999 # 制限なし

        # --- カラム名の解決 ---
        prob_col = None
        for col in ['normalized_pred_win', 'pred_win_prob', 'win_prob', 'pred_win']:
            if col in final_result_df.columns:
                prob_col = col
                break
        if prob_col is None:
            print("[AUTO-VOTER ERROR] Prediction prob column not found.")
            return False

        odds_col = None
        for col in ['tansho_odds', '単勝オッズ', 'オッズ', 'win_odds']:
            if col in final_result_df.columns:
                odds_col = col
                break
        if odds_col is None:
            print("[AUTO-VOTER WARN] Odds column not found. Skipping.")
            return False

        # --- 馬番カラムの解決 ---
        umaban_col = 'umaban' if 'umaban' in final_result_df.columns else \
                     ('馬番' if '馬番' in final_result_df.columns else None)

        # --- 自動投票対象馬の選定（多重フィルター） ---
        bets = []
        skipped_reasons = []
        for _, row in final_result_df.iterrows():
            try:
                umaban = int(row[umaban_col]) if umaban_col else int(row.iloc[0])
            except (KeyError, ValueError):
                umaban = int(row.iloc[0])

            horse_name = row.get('horse_name', row.get('馬名', '不明'))
            win_prob = float(row[prob_col])
            odds_raw = row[odds_col]

            if pd.isna(odds_raw) or float(odds_raw) <= 0:
                continue
            odds = float(odds_raw)
            ev = win_prob * odds

            # フィルター①: 勝率
            if win_prob < self.min_win_prob:
                skipped_reasons.append(f"  {umaban}番 {horse_name}: 勝率不足 ({win_prob:.1%} < {self.min_win_prob:.0%})")
                continue

            # フィルター②: 期待値
            if ev < self.target_ev:
                skipped_reasons.append(f"  {umaban}番 {horse_name}: EV不足 ({ev:.2f} < {self.target_ev})")
                continue

            # フィルター③: オッズ下限（旨味のない本命馬を除外）
            if odds < self.min_odds:
                skipped_reasons.append(f"  {umaban}番 {horse_name}: オッズ低すぎ ({odds:.1f}倍 < {self.min_odds}倍)")
                continue

            # フィルター④: オッズ上限（超高配当の不安定馬を除外）
            if odds > self.max_odds:
                skipped_reasons.append(f"  {umaban}番 {horse_name}: オッズ高すぎ ({odds:.1f}倍 > {self.max_odds}倍)")
                continue

            bets.append({
                'umaban': umaban,
                'horse_name': horse_name,
                'win_prob': win_prob,
                'odds': odds,
                'ev': ev,
                'bet_type': 'win',
                'amount': self.default_amount
            })

        if skipped_reasons:
            print(f"[AUTO-VOTER] Filtered out {len(skipped_reasons)} horse(s):")
            for r in skipped_reasons:
                print(r)

        if not bets:
            print(f"[AUTO-VOTER] No horses passed all filters for Race {race_id}.")
            return True

        # フィルター⑤: EV降順ソート後、上位 max_horses 頭のみ
        bets.sort(key=lambda x: x['ev'], reverse=True)
        if len(bets) > self.max_horses:
            dropped = bets[self.max_horses:]
            bets = bets[:self.max_horses]
            print(f"[AUTO-VOTER] {len(dropped)} horse(s) dropped by MAX_HORSES limit ({self.max_horses}頭, EV高順に選択):")
            for d in dropped:
                print(f"  (dropped) {d['umaban']}番 {d['horse_name']} EV={d['ev']:.2f}")

        # フィルター⑥: 1日購入点数上限 (件数)による絞り込み
        if len(bets) > remaining_slots:
            print(f"[AUTO-VOTER] Daily limit: only {remaining_slots} slot(s) remain ({daily_count}/{self.max_bets_per_day} used today).")
            bets = bets[:remaining_slots]

        # フィルター⑦: 残り予算金額による絞り込み (予算上限を超えないようにEVが低い馬をドロップ)
        affordable_bets = []
        accumulated_cost = 0
        for bet in bets:
            cost = bet['amount']
            if accumulated_cost + cost <= remaining_budget:
                affordable_bets.append(bet)
                accumulated_cost += cost
            else:
                print(f"  (dropped due to budget) {bet['umaban']}番 {bet['horse_name']} EV={bet['ev']:.2f} (Required: {cost}円, Remaining budget: {remaining_budget - accumulated_cost}円)")
        bets = affordable_bets

        if not bets:
            print(f"[AUTO-VOTER] No horses could be purchased within the remaining budget ({remaining_budget:,} 円) for Race {race_id}.")
            return True

        print(f"[AUTO-VOTER] {len(bets)} horse(s) selected for voting:")
        for idx, bet in enumerate(bets):
            print(f"  ({idx+1}) {bet['umaban']}番 {bet['horse_name']} "
                  f"(勝率: {bet['win_prob']:.1%}, オッズ: {bet['odds']:.1f}倍, EV: {bet['ev']:.2f})")

        # --- 投票の実行 ---
        try:
            if not self.voter.login():
                print("[AUTO-VOTER ERROR] Login failed. Aborting vote.")
                return False

            balance = self.voter.get_balance()
            total_amount = sum(bet['amount'] for bet in bets)
            if balance < total_amount:
                print(f"[AUTO-VOTER ERROR] Insufficient balance (Required: {total_amount:,}円, Balance: {balance:,}円).")
                return False

            clean_bets = [
                {'umaban': bet['umaban'], 'bet_type': bet['bet_type'], 'amount': bet['amount']}
                for bet in bets
            ]

            success = self.voter.vote(race_id, clean_bets)

            if success:
                # 1日購入点数・金額の更新
                new_count = daily_count + len(bets)
                new_amount = daily_amount + total_amount
                daily_info['count'] = new_count
                daily_info['amount'] = new_amount
                _save_daily_bet_info(daily_info)
                
                print(f"[AUTO-VOTER] Daily bet info updated. Count: {new_count}/{self.max_bets_per_day}, Amount: {new_amount}/{limit_amount if limit_amount is not None else 'N/A'}円")

                # 投票履歴をデータベースに保存 (本番スマート投票 umaca の場合のみ)
                mode = getattr(config, 'AUTO_VOTING_MODE', 'mock')
                if mode == 'umaca':
                    kaisai_date = date.today().isoformat()

                    for bet in bets:
                        try:
                            save_vote_to_db(
                                race_id=race_id,
                                umaban=bet['umaban'],
                                horse_name=bet['horse_name'],
                                kaisai_date=kaisai_date,
                                vote_type=bet['bet_type'],
                                vote_odds=bet['odds'],
                                pred_win_prob=bet['win_prob'],
                                amount=bet['amount'],
                                status='success',
                                mode=mode
                            )
                        except Exception as db_err:
                            print(f"[AUTO-VOTER ERROR] Failed to write vote log to DB: {db_err}")
                else:
                    print(f"[AUTO-VOTER] Mode is '{mode}'. DB vote logging skipped to keep database clean.")

                # Discord通知
                is_mock = isinstance(self.voter, MockVoter)
                title = "🤖 **【AI自動投票 完了通知 (シミュレーション/テスト)】** 🤖" if is_mock else "🤖 **【AI自動投票 完了通知】** 🤖"
                
                # レース情報をパースして分かりやすくする
                try:
                    course_id = race_id[4:6]
                    venue_name = config.PLACE_MAP_IDS.get(course_id, "不明")
                    kaisai = int(race_id[6:8])
                    nichi = int(race_id[8:10])
                    race_num = int(race_id[10:])
                    race_info_str = f"**{venue_name} {race_num}R** (第{kaisai}回 {nichi}日目)"
                except Exception:
                    race_info_str = f"不明なレース (ID: `{race_id}`)"
                
                discord_msg = f"{title}\n"
                discord_msg += f"レース: {race_info_str} | ID: `{race_id}`\n"
                discord_msg += "━" * 15 + "\n"
                for bet in bets:
                    discord_msg += (f"・ **{bet['umaban']}番 {bet['horse_name']}** "
                                    f"(オッズ: {bet['odds']:.1f}倍, EV: {bet['ev']:.2f}) "
                                    f"に **単勝 {bet['amount']:,}円** 💸\n")
                new_balance = self.voter.get_balance()
                discord_msg += "━" * 15 + "\n"
                discord_msg += f"🏦 **投票後残高**: {new_balance:,}円\n"
                limit_display_str = f"{limit_amount:,}円" if limit_amount is not None else "制限なし"
                discord_msg += f"📊 **本日購入累計**: {new_amount:,} / {limit_display_str} (点数: {new_count}/{self.max_bets_per_day}点)\n"

                send_discord_webhook(discord_msg, webhook_url=getattr(config, 'DISCORD_VOTE_WEBHOOK_URL', None))
                print("[AUTO-VOTER] Automated voting completed and Discord notification sent!")
            else:
                print("[AUTO-VOTER ERROR] Vote transaction failed.")

            return success

        except Exception as e:
            print(f"[AUTO-VOTER ERROR] An unexpected error occurred: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            self.voter.close()
