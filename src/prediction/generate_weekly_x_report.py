import os
import sys
import argparse
import urllib.parse
import json
import requests
from datetime import datetime, timedelta

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

import src.config as config
from analysis.weekly_report_calculator import generate_weekly_report_data



KEIBAJO_MAP = {
    '01': '札幌', '02': '函館', '03': '福島', '04': '新潟',
    '05': '東京', '06': '中山', '07': '中京', '08': '京都',
    '09': '阪神', '10': '小倉'
}


def parse_race_info_from_id(race_id: str) -> str:
    try:
        race_id_str = str(race_id)
        if len(race_id_str) >= 12:
            place_code = race_id_str[4:6]
            race_num = int(race_id_str[10:12])
            place_name = KEIBAJO_MAP.get(place_code, '')
            if place_name:
                return f"{place_name}{race_num}R"
    except Exception:
        pass
    return "対象レース"


def format_weekly_report_text(report_data: dict, blog_url: str = None) -> str:
    """
    集計データからX(旧Twitter)用成績レポート文面を整形する。
    """
    date_str = report_data.get('target_date', '')
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    weekday_kanji = ["月", "火", "水", "木", "金", "土", "日"][dt.weekday()]

    daily = report_data.get('daily', {})
    weekly = report_data.get('weekly', {})
    yearly = report_data.get('yearly', {})

    lines = [f"🏇【KeibaAI 週末成績レポート】"]
    lines.append(f"📅 {dt.strftime('%Y/%m/%d')}({weekday_kanji}) 開催分\n")

    is_sunday = report_data.get('is_sunday', False)

    # 日曜日は「今週(土日)の総合成績」のみ、土曜日は「本日(土)の成績」のみ表示して文字数削減
    if is_sunday:
        w_total = weekly.get('total_amount', 0)
        w_payout = weekly.get('payout_amount', 0)
        w_rate = weekly.get('recovery_rate', 0.0)
        w_stamp = "🔥" if w_rate >= 100 else "📈"

        lines.append(f"【今週(土日)の総合成績】")
        lines.append(f"・購入金額: {w_total:,}円")
        lines.append(f"・回収金額: {w_payout:,}円")
        lines.append(f"・今週回収率: {w_rate:.1f}% {w_stamp}\n")
    else:
        d_total = daily.get('total_amount', 0)
        d_payout = daily.get('payout_amount', 0)
        d_rate = daily.get('recovery_rate', 0.0)
        d_bets = daily.get('total_bets', 0)
        d_hits = daily.get('hit_bets', 0)

        lines.append(f"【本日({weekday_kanji})の成績】")
        lines.append(f"・購入金額: {d_total:,}円 ({d_bets}点)")
        lines.append(f"・回収金額: {d_payout:,}円 (的中 {d_hits}/{d_bets})")
        d_stamp = "🎯" if d_rate >= 100 else "📊"
        lines.append(f"・本日回収率: {d_rate:.1f}% {d_stamp}\n")

    # 的中ハイライト
    target_hits = weekly.get('hit_details', []) if is_sunday else daily.get('hit_details', [])
    if target_hits:
        sorted_hits = sorted(target_hits, key=lambda x: x.get('pay_val', 0), reverse=True)[:2]
        lines.append("【今週の主な的中🎯】" if is_sunday else "【本日の主な的中🎯】")
        for hit in sorted_hits:
            race_title = parse_race_info_from_id(hit['race_id'])
            vtype = hit.get('vote_type', '単勝')
            pay_val = hit.get('pay_val', 0)
            lines.append(f"・{race_title} {vtype} {pay_val:,.0f}円")
        lines.append("")

    # 年間累計成績
    y_total = yearly.get('total_amount', 0)
    y_payout = yearly.get('payout_amount', 0)
    y_rate = yearly.get('recovery_rate', 0.0)
    lines.append(f"【{dt.year}年 通算累計】")
    lines.append(f"・回収率: {y_rate:.1f}% (購入 {y_total:,}円 / 回収 {y_payout:,}円)\n")

    if blog_url:
        lines.append(f"👇詳しいレポート・全予測はブログをチェック！\n{blog_url}\n")

    lines.append("#競馬AI #成績報告 #競馬予想 #回収率")

    return "\n".join(lines)


def send_weekly_x_report_to_discord(date_str: str = None, webhook_url: str = None) -> bool:
    """
    指定日の成績を集計し、新チャンネルに1タップ投稿リンク付きで送信する。
    """
    if not webhook_url:
        webhook_url = getattr(config, 'DISCORD_X_WEBHOOK_URL', None)
    if not webhook_url:
        print("[WARN] DISCORD_X_WEBHOOK_URL is not set.")
        return False

    report_data = generate_weekly_report_data(date_str)
    report_text = format_weekly_report_text(report_data)

    dt = datetime.strptime(report_data['target_date'], '%Y-%m-%d')
    weekday_kanji = ["月", "火", "水", "木", "金", "土", "日"][dt.weekday()]

    # 二重エンコードが発生しない Embed 用の Intent URL 生成
    encoded_text = urllib.parse.quote(report_text)
    intent_url = f"https://twitter.com/intent/tweet?text={encoded_text}"

    content = f"📊 **【KeibaAI 週末成績レポート X投稿アシスト】** (`{date_str} {weekday_kanji}曜`)\n\n"
    content += "↓ 1タップ投稿は下の**青いカードタイトル**をタップ、手動の場合は枠内を全選択コピーしてください:\n"
    content += "```\n" + report_text + "\n```"

    payload = {
        "username": "KeibaAI 収支レポートアシスト",
        "content": content,
        "embeds": [
            {
                "title": f"🚀 1タップで成績レポートをX(Twitter)に投稿する ({date_str})",
                "url": intent_url,
                "description": f"👉 上の青いタイトル「🚀 1タップで成績レポートをX...」をタップすると、入力済みのツイート画面が開きます！",
                "color": 3447003
            }
        ]
    }

    try:
        r = requests.post(webhook_url, json=payload)
        r.raise_for_status()
        print(f"-> Sent weekly performance report to Discord X channel successfully.")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send weekly report to Discord: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate and send weekly performance report for X.")
    parser.add_argument('--date', help='Target date (YYYY-MM-DD)')
    args = parser.parse_args()

    target_date = args.date or datetime.now().strftime('%Y-%m-%d')
    print(f"--- Generating Weekly X Performance Report for {target_date} ---")
    send_weekly_x_report_to_discord(target_date)
