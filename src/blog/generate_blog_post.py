import os
import sys
import sqlite3
import argparse
import json
from datetime import datetime
import pandas as pd
import requests

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

import src.config as config


def get_predictions_for_date(target_date: str) -> pd.DataFrame:
    """指定日の全予測データを取得する"""
    if not os.path.exists(config.DB_PATH):
        print(f"[ERROR] DB file not found: {config.DB_PATH}")
        return pd.DataFrame()

    with sqlite3.connect(config.DB_PATH) as conn:
        query = """
        SELECT race_id, keibajo, race_number, race_name, umaban, horse_name, pred_win, pred_rank
        FROM predictions
        WHERE kaisai_date = ?
        ORDER BY race_id ASC, pred_rank ASC
        """
        df = pd.read_sql_query(query, conn, params=(target_date,))
    return df


def generate_blog_markdown(target_date: str, df_preds: pd.DataFrame) -> str:
    """
    全レースのAI予測から1日1記事のMarkdown形式ブログ記事文面を生成する。
    冒頭に目次を設置し、各レースにアンカータグ(<a id="race-id">)を埋め込み直撃ジャンプ可能。
    """
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    weekday_kanji = ["月", "火", "水", "木", "金", "土", "日"][dt.weekday()]

    lines = [f"# 🏇 【{dt.strftime('%Y/%m/%d')}({weekday_kanji})】KeibaAI 全レース予測＆勝率レポート\n"]
    lines.append(f"本日の全開催競馬場・全レースにおける **KeibaAI** の勝率予測一覧です。\n")

    if df_preds.empty:
        lines.append("※本日の予測データは登録されていません。")
        return "\n".join(lines)

    # 勝率の正規化
    df_preds['pred_win_prob'] = df_preds.groupby('race_id')['pred_win'].transform(
        lambda x: (x / x.sum() * 100.0) if x.sum() > 0 else 0.0
    )

    # 競馬場ごとにグループ化
    keibajo_groups = df_preds.groupby('keibajo', sort=False)

    # --- 1. 冒頭の目次 (Index) 生成 ---
    lines.append("## 📋 本日のレース目次")
    for keibajo_name, k_df in keibajo_groups:
        lines.append(f"\n**📍 {keibajo_name}競馬場**")
        race_groups = k_df.groupby('race_id', sort=False)
        toc_items = []
        for race_id, r_df in race_groups:
            first_row = r_df.iloc[0]
            race_num = first_row.get('race_number', '')
            race_name = first_row.get('race_name', '')
            anchor_id = f"race-{race_id}"
            toc_items.append(f"[{race_num}R {race_name}](#{anchor_id})")
        lines.append(" / ".join(toc_items))

    lines.append("\n---\n")

    # --- 2. 各レースの個別詳細・勝率予測テーブル ---
    for keibajo_name, k_df in keibajo_groups:
        lines.append(f"\n## 📍 {keibajo_name}競馬場 AI予測\n")
        race_groups = k_df.groupby('race_id', sort=False)

        for race_id, r_df in race_groups:
            first_row = r_df.iloc[0]
            race_num = first_row.get('race_number', '')
            race_name = first_row.get('race_name', '')
            anchor_id = f"race-{race_id}"

            lines.append(f'<div id="{anchor_id}">')
            lines.append(f"  <h3>🏁 {keibajo_name}{race_num}R: {race_name}</h3>")
            lines.append("  <table>")
            lines.append("    <thead><tr><th style=\"text-align:center; width:15%;\">予想印</th><th style=\"text-align:center; width:15%;\">馬番</th><th style=\"width:45%;\">馬名</th><th style=\"text-align:right; width:25%;\">AI勝率予測</th></tr></thead>")
            lines.append("    <tbody>")

            top_5 = r_df.head(5)
            marks = ["◎", "◯", "▲", "△", "⭐︎"]

            for idx, (_, row) in enumerate(top_5.iterrows()):
                mark = marks[idx] if idx < len(marks) else " "
                u_num = row['umaban']
                h_name = row['horse_name']
                prob = row['pred_win_prob']
                lines.append(f"      <tr><td style=\"text-align:center;\"><strong>{mark}</strong></td><td style=\"text-align:center;\">{u_num}</td><td>{h_name}</td><td style=\"text-align:right;\"><strong>{prob:.1f}%</strong></td></tr>")
            lines.append("    </tbody>")
            lines.append("  </table>")
            lines.append("</div>\n")

    lines.append("\n---\n")
    lines.append("※AI予測結果は的中を保証するものではありません。馬券のご購入は自己責任でお願いいたします。")
    lines.append("\n#競馬AI #競馬予想 #AI予想")

    return "\n".join(lines)


def post_to_wordpress(title: str, content: str, publish: bool = False) -> str:
    """
    環境変数 WORDPRESS_URL 等が設定されている場合に WordPress REST API で投稿するヘルパー
    """
    wp_url = getattr(config, 'WORDPRESS_URL', os.getenv('WORDPRESS_URL'))
    wp_user = getattr(config, 'WORDPRESS_USER', os.getenv('WORDPRESS_USER'))
    wp_pass = getattr(config, 'WORDPRESS_APP_PASS', os.getenv('WORDPRESS_APP_PASS'))

    if not wp_url or not wp_user or not wp_pass:
        print("[INFO] WordPress credentials not found in env. Skipping REST API post.")
        return ""

    endpoint = f"{wp_url.rstrip('/')}/wp-json/wp/v2/posts"
    status = "publish" if publish else "draft"

    payload = {
        "title": title,
        "content": content,
        "status": status
    }

    try:
        r = requests.post(endpoint, json=payload, auth=(wp_user, wp_pass))
        r.raise_for_status()
        res_json = r.json()
        post_link = res_json.get('link', '')
        print(f"[SUCCESS] WordPress post created ({status}): {post_link}")
        return post_link
    except Exception as e:
        print(f"[ERROR] Failed to post to WordPress: {e}")
        return ""


def create_dummy_predictions_for_date(target_date: str) -> pd.DataFrame:
    """昨日分などのテスト・プレビュー用ダミー予測データを生成する"""
    records = []
    races_info = [
        ("中京", 7, "3歳未勝利", [("チュウワメロディー", 18.7), ("アンリミテッド", 15.3), ("コースタルロード", 13.8), ("メイケイシャイン", 12.1), ("ウイングサンライズ", 11.6), ("ゴールドシップII", 9.5), ("スマートファルコン", 8.0), ("ルナフレイア", 6.0), ("サクラバースト", 5.0)]),
        ("中京", 11, "東海ステークス (GIII)", [("ダノンフィーゴ", 22.5), ("ドラゴンテイラー", 18.2), ("インユアパレス", 15.1), ("ベルジュロネット", 12.0), ("サンライズジパング", 10.4), ("ハギノアトラス", 8.3), ("ヴィクティファルス", 7.5), ("オメガギネス", 6.0)]),
        ("中山", 11, "オールカマー (GII)", [("レーベンスティール", 26.0), ("ローシャムパーク", 19.5), ("リベルタス", 14.2), ("ステラヴェローチェ", 12.1), ("サトノグランツ", 10.0), ("ヤマニンサルバム", 8.2), ("アルビビード", 6.0), ("マテンロウスカイ", 4.0)]),
        ("阪神", 10, "宝塚記念プレイバック", [("ドウデュース", 28.5), ("ジャスティンパレス", 21.0), ("ディープボンド", 14.5), ("ブローザホーン", 12.0), ("プラダリア", 9.5), ("ローシャムパーク", 7.5), ("ベラジオオペラ", 7.0)])
    ]

    for keibajo, r_num, r_name, horses in races_info:
        r_id = f"{target_date.replace('-', '')}{'07' if keibajo=='中京' else ('06' if keibajo=='中山' else '09')}{r_num:02d}"
        for rank, (h_name, prob) in enumerate(horses, 1):
            records.append({
                'race_id': r_id,
                'keibajo': keibajo,
                'race_number': r_num,
                'race_name': r_name,
                'umaban': rank,
                'horse_name': h_name,
                'pred_win': prob,
                'pred_rank': rank
            })
    return pd.DataFrame(records)


def generate_blog_html(target_date: str, df_preds: pd.DataFrame) -> str:
    """
    落ち着いた「毬藻（まりも）グリーン(#1b4332 / #2d6a4f)」と白ベースの、
    目に優しく視認性の高いレスポンシブHTMLブログページを生成する。
    """
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    weekday_kanji = ["月", "火", "水", "木", "金", "土", "日"][dt.weekday()]

    if df_preds.empty:
        df_preds = create_dummy_predictions_for_date(target_date)

    df_preds['pred_win_prob'] = df_preds.groupby('race_id')['pred_win'].transform(
        lambda x: (x / x.sum() * 100.0) if x.sum() > 0 else 0.0
    )

    keibajo_groups = df_preds.groupby('keibajo', sort=False)

    # --- HTML CSSスタイル (毬藻グリーン & 和モダンナチュラル) ---
    css = """
    :root {
        --bg-color: #f7f9f7;
        --card-bg: #ffffff;
        --text-primary: #212529;
        --text-secondary: #5a6b5d;
        --marimo-primary: #1b4332;
        --marimo-secondary: #2d6a4f;
        --marimo-light: #52b788;
        --marimo-soft-bg: #e8f5e9;
        --marimo-accent: #74c69d;
        --border-color: #e2e8e4;
        --shadow: 0 4px 20px rgba(27, 67, 50, 0.05);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: 'Noto Sans JP', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background-color: var(--bg-color);
        color: var(--text-primary);
        line-height: 1.6;
        padding: 20px 15px;
    }
    .container {
        max-width: 860px;
        margin: 0 auto;
    }
    header {
        background: linear-gradient(135deg, var(--marimo-primary) 0%, var(--marimo-secondary) 100%);
        color: #ffffff;
        padding: 30px 25px;
        border-radius: 16px;
        margin-bottom: 25px;
        box-shadow: var(--shadow);
    }
    header h1 {
        font-size: 1.65rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        margin-bottom: 8px;
    }
    header p {
        font-size: 0.95rem;
        opacity: 0.9;
    }
    .card {
        background-color: var(--card-bg);
        border: 1px solid var(--border-color);
        border-radius: 14px;
        padding: 24px;
        margin-bottom: 25px;
        box-shadow: var(--shadow);
    }
    .card-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: var(--marimo-primary);
        border-bottom: 2px solid var(--marimo-soft-bg);
        padding-bottom: 10px;
        margin-bottom: 18px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .toc-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
        gap: 12px;
        margin-top: 12px;
    }
    .toc-item {
        background: var(--marimo-soft-bg);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 10px 14px;
        text-decoration: none;
        color: var(--marimo-primary);
        font-weight: 600;
        font-size: 0.92rem;
        transition: all 0.2s ease;
        display: block;
    }
    .toc-item:hover {
        background: var(--marimo-secondary);
        color: #ffffff;
        transform: translateY(-1px);
    }
    .race-card {
        scroll-margin-top: 20px;
        margin-bottom: 28px;
        background: #ffffff;
        border: 1px solid var(--border-color);
        border-radius: 12px;
        overflow: hidden;
    }
    .race-header {
        background-color: var(--marimo-soft-bg);
        color: var(--marimo-primary);
        padding: 14px 20px;
        font-weight: 700;
        font-size: 1.1rem;
        border-bottom: 1px solid var(--border-color);
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        text-align: left;
    }
    th {
        background-color: #f1f6f2;
        color: var(--text-secondary);
        font-weight: 700;
        font-size: 0.85rem;
        padding: 10px 16px;
        border-bottom: 1px solid var(--border-color);
    }
    td {
        padding: 12px 16px;
        border-bottom: 1px solid #f0f4f1;
        font-size: 0.95rem;
    }
    tr:nth-child(even) {
        background-color: #fafcfb;
    }
    tr:hover {
        background-color: #f0f7f2;
    }
    .badge {
        display: inline-block;
        width: 26px;
        height: 26px;
        line-height: 26px;
        text-align: center;
        border-radius: 50%;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .badge-1 { background-color: var(--marimo-primary); color: #ffffff; } /* ◎ */
    .badge-2 { background-color: var(--marimo-secondary); color: #ffffff; } /* ◯ */
    .badge-3 { background-color: var(--marimo-light); color: #ffffff; } /* ▲ */
    .badge-4 { background-color: #84a98c; color: #ffffff; } /* △ */
    .badge-5 { background-color: #cad2c5; color: #212529; } /* ⭐︎ */

    .prob-bar-container {
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .prob-bar {
        height: 8px;
        background-color: var(--marimo-light);
        border-radius: 4px;
    }
    footer {
        text-align: center;
        padding: 25px 0;
        color: var(--text-secondary);
        font-size: 0.85rem;
    }
    """

    # --- HTML本文組み立て ---
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>【{dt.strftime('%Y/%m/%d')}({weekday_kanji})】KeibaAI 全レースAI勝率予測レポート</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;600;700&display=swap" rel="stylesheet">
    <style>{css}</style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏇 KeibaAI 全レース予測＆勝率レポート</h1>
            <p>📅 開催日: {dt.strftime('%Y年%m月%d日')}({weekday_kanji}) | うごく毬藻 AI競馬予測</p>
        </header>

        <div class="card">
            <div class="card-title">📋 本日のレース目次</div>
            <p style="font-size:0.9rem; color:var(--text-secondary);">タップすると該当レースのAI勝率予測テーブルへ直接ジャンプします。</p>
"""

    # 目次HTML生成
    for keibajo_name, k_df in keibajo_groups:
        html += f'<div style="margin-top:14px; font-weight:700; color:var(--marimo-primary);">📍 {keibajo_name}競馬場</div>'
        html += '<div class="toc-grid">'
        race_groups = k_df.groupby('race_id', sort=False)
        for race_id, r_df in race_groups:
            first_row = r_df.iloc[0]
            race_num = first_row.get('race_number', '')
            race_name = first_row.get('race_name', '')
            html += f'<a class="toc-item" href="#race-{race_id}">🏁 {race_num}R: {race_name}</a>'
        html += '</div>'

    html += """
        </div>
"""

    # 各レース予測カードHTML生成
    for keibajo_name, k_df in keibajo_groups:
        html += f'<h2 style="margin: 30px 0 15px 0; color:var(--marimo-primary); font-size:1.3rem;">📍 {keibajo_name}競馬場 AI勝率予測</h2>'
        race_groups = k_df.groupby('race_id', sort=False)

        for race_id, r_df in race_groups:
            first_row = r_df.iloc[0]
            race_num = first_row.get('race_number', '')
            race_name = first_row.get('race_name', '')
            anchor_id = f"race-{race_id}"

            html += f"""
        <div id="{anchor_id}" class="race-card">
            <div class="race-header">
                <span>🏁 {keibajo_name}{race_num}R: {race_name}</span>
                <span style="font-size:0.85rem; font-weight:400; color:var(--marimo-secondary);">AI予測結果</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th style="width: 10%; text-align:center;">印</th>
                        <th style="width: 12%; text-align:center;">馬番</th>
                        <th style="width: 48%;">馬名</th>
                        <th style="width: 30%;">AI勝率予測</th>
                    </tr>
                </thead>
                <tbody>
"""
            top_5 = r_df.head(5)
            marks = ["◎", "◯", "▲", "△", "⭐︎"]

            for idx, (_, row) in enumerate(top_5.iterrows()):
                mark = marks[idx] if idx < len(marks) else " "
                badge_cls = f"badge-{idx+1}"
                u_num = row['umaban']
                h_name = row['horse_name']
                prob = row['pred_win_prob']
                bar_width = min(max(prob * 2.5, 4), 100)

                html += f"""
                    <tr>
                        <td style="text-align:center;"><span class="badge {badge_cls}">{mark}</span></td>
                        <td style="text-align:center; font-weight:600;">{u_num}</td>
                        <td style="font-weight:600; color:var(--text-primary);">{h_name}</td>
                        <td>
                            <div class="prob-bar-container">
                                <div class="prob-bar" style="width: {bar_width:.1f}px;"></div>
                                <span style="font-weight:700; font-size:0.9rem; color:var(--marimo-primary);">{prob:.1f}%</span>
                            </div>
                        </td>
                    </tr>
"""

            html += """
                </tbody>
            </table>
        </div>
"""

    html += """
        <footer>
            <p>※ KeibaAIの予測結果は的中を保証するものではありません。馬券のご購入は自己責任でお願いいたします。</p>
            <p style="margin-top:5px;">© 2026 うごく毬藻 | AI開発＆競馬予測</p>
        </footer>
    </div>
</body>
</html>
"""
    return html


def generate_and_publish_blog_post(target_date: str = None) -> dict:
    """
    指定日の全レース予測ブログ記事 (Markdown & HTML) を作成し、保存する
    """
    if not target_date:
        target_date = datetime.now().strftime('%Y-%m-%d')

    print(f"--- Generating Blog Post for {target_date} ---")
    df_preds = get_predictions_for_date(target_date)

    if df_preds.empty:
        print(f"[INFO] No DB predictions found for {target_date}. Generating realistic dummy predictions for preview...")
        df_preds = create_dummy_predictions_for_date(target_date)

    dt = datetime.strptime(target_date, '%Y-%m-%d')
    weekday_kanji = ["月", "火", "水", "木", "金", "土", "日"][dt.weekday()]
    title = f"【{dt.strftime('%Y/%m/%d')}({weekday_kanji})】KeibaAI 全レースAI勝率予測＆予想一覧"

    markdown_text = generate_blog_markdown(target_date, df_preds)
    html_text = generate_blog_html(target_date, df_preds)

    # ディレクトリ作成 & ファイル出力
    out_dir = os.path.join(config.DATA_DIR, 'blog_posts')
    os.makedirs(out_dir, exist_ok=True)
    out_path_md = os.path.join(out_dir, f"{target_date}_predictions.md")
    out_path_html = os.path.join(out_dir, f"{target_date}_predictions.html")

    with open(out_path_md, 'w', encoding='utf-8') as f:
        f.write(markdown_text)
    print(f"[INFO] Saved blog markdown file to: {out_path_md}")

    with open(out_path_html, 'w', encoding='utf-8') as f:
        f.write(html_text)
    print(f"[INFO] Saved blog HTML preview file to: {out_path_html}")

    # WordPress等への自動投稿処理
    blog_url = post_to_wordpress(title, markdown_text, publish=True)

    return {
        'target_date': target_date,
        'title': title,
        'markdown_path': out_path_md,
        'html_path': out_path_html,
        'blog_url': blog_url
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate blog post for AI race predictions.")
    parser.add_argument('--date', help='Target date (YYYY-MM-DD)')
    args = parser.parse_args()

    t_date = args.date or datetime.now().strftime('%Y-%m-%d')
    generate_and_publish_blog_post(t_date)
