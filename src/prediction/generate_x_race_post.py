import os
import sys
import sqlite3
import urllib.parse
import argparse
import requests
from datetime import datetime
import pandas as pd

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

import src.config as config
from blog.generate_blog_post import get_predictions_for_date


def format_race_x_post(race_df: pd.DataFrame, blog_url: str = None) -> dict:
    """
    1レース分の予測データから親ツイートおよびリプライ（ツリー）用文面を生成する。
    """
    if race_df.empty:
        return {}

    # 全頭の勝率正規化
    total_score = race_df['pred_win'].sum()
    race_df['prob'] = race_df['pred_win'].apply(lambda x: (x / total_score * 100.0) if total_score > 0 else 0.0)
    race_df = race_df.sort_values(by='pred_rank', ascending=True)

    first_row = race_df.iloc[0]
    keibajo = first_row.get('keibajo', '')
    race_num = first_row.get('race_number', '')
    race_name = first_row.get('race_name', '')

    marks = ["◎", "◯", "▲", "△", "⭐︎"]
    top_5 = race_df.head(5)

    # --- 1. 親ツイート作成 ---
    parent_lines = [f"🏁【{keibajo}{race_num}R {race_name}】AI勝率予測 🏇\n"]

    for idx, (_, row) in enumerate(top_5.iterrows()):
        mark = marks[idx] if idx < len(marks) else ""
        u_num = row['umaban']
        h_name = row['horse_name']
        prob = row['prob']
        parent_lines.append(f"{mark} {u_num}番 {h_name} ({prob:.1f}%)")

    parent_lines.append(f"\n#{keibajo}競馬 #{race_name} #競馬AI #競馬予想")
    parent_text = "\n".join(parent_lines)

    # --- 2. リプライ（ツリー）用ツイート作成 ---
    race_id = first_row['race_id']
    anchor_hash = f"#race-{race_id}"

    reply_lines = [f"👇 {keibajo}{race_num}R の詳細＆全レース予測はこちら！\n"]
    base_url = blog_url if blog_url else os.getenv('BLOG_URL', 'https://your-blog-domain.com')

    if "#" in base_url:
        full_race_url = base_url
    else:
        full_race_url = f"{base_url.rstrip('/')}{anchor_hash}"

    reply_lines.append(full_race_url)
    reply_lines.append("\n#競馬AI #競馬予想")
    reply_text = "\n".join(reply_lines)

    return {
        'race_id': first_row['race_id'],
        'race_title': f"{keibajo}{race_num}R {race_name}",
        'parent_text': parent_text,
        'reply_text': reply_text
    }


def send_race_post_to_discord(race_id: str, blog_url: str = None, webhook_url: str = None) -> bool:
    """
    指定レースの親ツイート・リプライ投稿リンクを Discord に送信する。
    """
    if not webhook_url:
        webhook_url = getattr(config, 'DISCORD_X_WEBHOOK_URL', os.getenv('DISCORD_X_WEBHOOK_URL'))
    if not webhook_url:
        print("[WARN] DISCORD_X_WEBHOOK_URL is not set.")
        return False

    with sqlite3.connect(config.DB_PATH) as conn:
        query = """
        SELECT race_id, keibajo, race_number, race_name, umaban, horse_name, pred_win, pred_rank
        FROM predictions
        WHERE race_id = ?
        ORDER BY pred_rank ASC
        """
        race_df = pd.read_sql_query(query, conn, params=(race_id,))

    if race_df.empty:
        print(f"[WARN] No prediction found for race_id: {race_id}")
        return False

    post_data = format_race_x_post(race_df, blog_url)
    parent_text = post_data['parent_text']
    reply_text = post_data['reply_text']

    encoded_parent = urllib.parse.quote(parent_text)
    encoded_reply = urllib.parse.quote(reply_text)

    parent_intent = f"https://twitter.com/intent/tweet?text={encoded_parent}"
    reply_intent = f"https://twitter.com/intent/tweet?text={encoded_reply}"

    content = f"🏇 **【X投稿アシスト: {post_data['race_title']}】**\n\n"
    content += "📌 **[1] 親ツイート (予測ポスト)**\n"
    content += "```\n" + parent_text + "\n```\n"
    content += "💬 **[2] リプライ用 (ブログ案内)**\n"
    content += "```\n" + reply_text + "\n```"

    payload = {
        "username": "KeibaAI X投稿アシスト",
        "content": content,
        "embeds": [
            {
                "title": "🚀 1. 親ツイート(予測)を投稿する",
                "url": parent_intent,
                "color": 3447003
            },
            {
                "title": "💬 2. リプライ(ブログ案内)を投稿する",
                "url": reply_intent,
                "color": 15105570
            }
        ]
    }

    try:
        r = requests.post(webhook_url, json=payload)
        r.raise_for_status()
        print(f"[SUCCESS] Sent race X post assist to Discord for {post_data['race_title']}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send race post assist to Discord: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate and send X post assist for a race.")
    parser.add_argument('--race_id', help='Target race ID (e.g. 202607020411)')
    parser.add_argument('--blog_url', help='Optional blog URL')
    args = parser.parse_args()

    if args.race_id:
        send_race_post_to_discord(args.race_id, args.blog_url)
    else:
        print("Please specify --race_id")
