import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..'))
sys.path.append(PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'db', 'predictions.db')
TARGET_MDX_DIR = r"C:\side_job\src\content\predictions"


def decode_bytes(val):
    if isinstance(val, bytes):
        try:
            return val.decode('utf-8')
        except Exception:
            try:
                return val.decode('cp932')
            except Exception:
                return val.decode('utf-8', errors='replace')
    return str(val) if val is not None else ""


def export_real_prediction_mdx(target_date: str = '2026-07-26'):
    print(f"--- Exporting ENHANCED prediction data with EV logic for {target_date} from {DB_PATH} ---")
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] DB not found at: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.text_factory = bytes
    cursor = conn.cursor()

    query = """
    SELECT race_id, keibajo, race_number, race_name, umaban, horse_name, 
           pred_win, pred_rank, tansho_odds, tansho_ninki, result_rank
    FROM predictions
    WHERE kaisai_date = ?
    ORDER BY race_id ASC, pred_rank ASC
    """
    cursor.execute(query, (target_date,))
    rows = cursor.fetchall()

    if not rows:
        print(f"[ERROR] No records found for date {target_date}")
        conn.close()
        return

    records = []
    for r in rows:
        records.append({
            'race_id': decode_bytes(r[0]),
            'keibajo': decode_bytes(r[1]),
            'race_number': int(r[2]) if r[2] else 0,
            'race_name': decode_bytes(r[3]),
            'umaban': int(r[4]) if r[4] else 0,
            'horse_name': decode_bytes(r[5]),
            'pred_win': float(r[6]) if r[6] else 0.0,
            'pred_rank': int(r[7]) if r[7] else 0,
            'tansho_odds': float(r[8]) if r[8] and float(r[8]) > 0 else 0.0,
            'tansho_ninki': int(r[9]) if r[9] else 0,
            'result_rank': int(r[10]) if r[10] else None
        })

    df = pd.DataFrame(records)
    conn.close()

    # 勝率のグループ毎正規化 (各レース内での確率化 %)
    df['pred_win_prob'] = df.groupby('race_id')['pred_win'].transform(
        lambda x: (x / x.sum() * 100.0) if x.sum() > 0 else 0.0
    )

    # 期待値 (EV = 勝率 * 単勝オッズ) 算出
    df['ev'] = df.apply(lambda r: (r['pred_win_prob'] / 100.0) * r['tansho_odds'] if r['tansho_odds'] > 0 else 0.0, axis=1)

    dt = datetime.strptime(target_date, '%Y-%m-%d')
    weekday_kanji = ["月", "火", "水", "木", "金", "土", "日"][dt.weekday()]
    keibajo_list = df['keibajo'].unique().tolist()
    keibajo_str = "・".join(keibajo_list)
    total_races = df['race_id'].nunique()

    # --- 1. 改良版「勝負レース Top 3」選定ロジック ---
    # オッズがある場合: 期待値(EV)が高い馬が含まれるレースを優先
    # オッズがない場合: 1位勝率と2位勝率の差（絶対的本命度・ダントツ感）が大きいレースを優先
    race_scores = []
    for race_id, r_df in df.groupby('race_id', sort=False):
        top1 = r_df[r_df['pred_rank'] == 1].iloc[0]
        top2_prob = r_df[r_df['pred_rank'] == 2].iloc[0]['pred_win_prob'] if len(r_df) > 1 else 0.0
        gap = top1['pred_win_prob'] - top2_prob
        max_ev = r_df['ev'].max()

        # 総合勝負度スコア (EV重視、または勝率差重視)
        score = max_ev * 1.5 + gap * 0.5 if max_ev > 0 else gap + (top1['pred_win_prob'] * 0.2)

        race_scores.append({
            'race_id': race_id,
            'keibajo': top1['keibajo'],
            'race_number': top1['race_number'],
            'race_name': top1['race_name'],
            'top1_umaban': top1['umaban'],
            'top1_horse_name': top1['horse_name'],
            'top1_prob': top1['pred_win_prob'],
            'max_ev': max_ev,
            'score': score
        })

    race_score_df = pd.DataFrame(race_scores).sort_values(by='score', ascending=False)
    勝負races = race_score_df.head(3)

    # --- 2. 的中実績の自動抽出 ---
    hit_races = df[(df['pred_rank'] == 1) & (df['result_rank'] == 1)]

    # --- Frontmatter ---
    lines = [
        "---",
        f'title: "【{dt.strftime("%Y/%m/%d")}({weekday_kanji})】KeibaAI 全レースAI勝率予測＆予想一覧"',
        f'subtitle: "{keibajo_str} 全{total_races}レースのAI勝率スコア・激アツ穴馬・推奨買い目一覧"',
        f'publishedAt: "{target_date}"',
        'category: "AI競馬予想"',
        f'description: "【実データ】{dt.strftime("%Y年%m月%d日")}({weekday_kanji})開催の全レースにおけるKeibaAIの予測スコア、AI厳選穴馬、推奨買い目一覧です。"',
        f'tags: ["競馬AI", "AI予想", "回収率", "{keibajo_list[0] if keibajo_list else "競馬予想"}"]',
        "---\n",
        f"2026年{dt.month}月{dt.day}日({weekday_kanji})に開催される全競馬場・全{total_races}レースにおける **KeibaAI** の予測データ一覧です。\n",
        "---\n"
    ]

    # --- 的中実績ハイライト (結果確定データがある場合) ---
    if not hit_races.empty:
        lines.append("## 🎯 本日のAI的中ハイライト\n")
        lines.append("<div className=\"p-4 mb-6 rounded-xl bg-[#e8f5e9] border border-[#2d6a4f]/30\">")
        lines.append("  <h4 className=\"font-bold text-[#1b4332] text-sm mb-2\">本日の単勝本命(◎) 的中ピックアップ</h4>")
        lines.append("  <ul className=\"text-xs text-[#1b4332] space-y-1\">")
        for _, hr in hit_races.iterrows():
            odds_str = f" (単勝 {hr['tansho_odds']:.1f}倍)" if hr['tansho_odds'] > 0 else ""
            lines.append(f"    <li>🎯 <strong>{hr['keibajo']}{hr['race_number']}R {hr['race_name']}</strong>: ◎ {hr['umaban']}番 {hr['horse_name']} 1着!{odds_str}</li>")
        lines.append("  </ul>")
        lines.append("</div>\n")

    # --- 期待値＆信頼度重視の「本日のAI勝負レース Top 3」 ---
    if not 勝負races.empty:
        lines.append("## 🎯 本日のAI厳選・勝負レース Top 3\n")
        lines.append("期待値（EV）および本命馬のAI評価信頼度に基づき厳選された注目レースです。\n")
        lines.append("<div className=\"grid grid-cols-1 md:grid-cols-3 gap-3 mb-8\">")
        for idx, (_, sr) in enumerate(勝負races.iterrows(), 1):
            r_anchor = f"#race-{sr['race_id']}"
            ev_label = f" / 期待値: <strong>{sr['max_ev']:.2f}</strong>" if sr['max_ev'] > 0 else ""
            lines.append("  <div className=\"p-3 rounded-lg bg-white border border-[#2d6a4f]/30 shadow-xs\">")
            lines.append(f"    <div className=\"text-[11px] font-bold text-[#2d6a4f]\">勝負レース #{idx}</div>")
            lines.append(f"    <div className=\"font-bold text-sm text-slate-900\"><a href=\"{r_anchor}\">{sr['keibajo']}{sr['race_number']}R {sr['race_name']}</a></div>")
            lines.append(f"    <div className=\"text-xs text-slate-600 mt-1\">◎ <strong>{sr['top1_umaban']}番 {sr['top1_horse_name']}</strong> (勝率: <strong>{sr['top1_prob']:.1f}%</strong>{ev_label})</div>")
            lines.append("  </div>")
        lines.append("</div>\n")

    # --- 目次作成 ---
    lines.append("## 📋 本日のレース目次\n")
    lines.append("タップすると該当レースのAI勝率予測・推奨買い目テーブルへ直接ジャンプします。\n")

    keibajo_groups = df.groupby('keibajo', sort=False)

    for keibajo_name, k_df in keibajo_groups:
        lines.append(f"### 📍 {keibajo_name}競馬場")
        race_groups = k_df.groupby('race_id', sort=False)
        toc_items = []
        for race_id, r_df in race_groups:
            first_row = r_df.iloc[0]
            r_num = first_row['race_number']
            r_name = first_row['race_name']
            toc_items.append(f"[{r_num}R {r_name}](#race-{race_id})")
        lines.append(" / ".join(toc_items) + "\n")

    lines.append("---\n")

    # --- 本文（レースごとの詳細予測テーブル ＋ 穴馬 ＋ 推奨買い目） ---
    for keibajo_name, k_df in keibajo_groups:
        lines.append(f"## 📍 {keibajo_name}競馬場 AI勝率予測\n")
        race_groups = k_df.groupby('race_id', sort=False)

        for race_id, r_df in race_groups:
            first_row = r_df.iloc[0]
            r_num = first_row['race_number']
            r_name = first_row['race_name']

            lines.append(f'<a id="race-{race_id}"></a>')
            lines.append(f"### 🏁 {keibajo_name}{r_num}R: {r_name}\n")

            # 🔥 激アツ穴馬判定 (4位・5位の評価馬をピックアップ)
            ana_horses = r_df[(r_df['pred_rank'] >= 4) & (r_df['pred_rank'] <= 5)]
            if not ana_horses.empty:
                ana_row = ana_horses.iloc[0]
                ninki_info = f" (予想{ana_row['tansho_ninki']}人気)" if ana_row['tansho_ninki'] > 0 else ""
                ev_info = f" / EV: {ana_row['ev']:.2f}" if ana_row['ev'] > 0 else ""
                lines.append(f"> 🔥 **AI注目穴馬**: **{ana_row['umaban']}番 {ana_row['horse_name']}** (AI勝率 {ana_row['pred_win_prob']:.1f}%{ninki_info}{ev_info})\n")

            # テーブル表記
            lines.append("| 予想印 | 馬番 | 馬名 | AI勝率 | オッズ (人気) |")
            lines.append("| :---: | :---: | :--- | :---: | :---: |")

            top_5 = r_df.head(5)
            marks = ["◎", "◯", "▲", "△", "⭐︎"]

            honmei_num = top_5.iloc[0]['umaban']
            aite_nums = [str(r['umaban']) for _, r in top_5.iloc[1:4].iterrows()]
            aite_str = ", ".join(aite_nums)

            for idx, (_, row) in enumerate(top_5.iterrows()):
                mark = marks[idx] if idx < len(marks) else " "
                u_num = row['umaban']
                h_name = row['horse_name']
                prob = row['pred_win_prob']
                odds_val = row['tansho_odds']
                ninki_val = row['tansho_ninki']
                odds_disp = f"{odds_val:.1f}倍 ({ninki_val}人気)" if odds_val > 0 else "---"

                lines.append(f"| **{mark}** | {u_num} | {h_name} | **{prob:.1f}%** | {odds_disp} |")

            lines.append("")
            # 推奨買い目
            lines.append(f"💡 **推奨買い目**: 単勝: **{honmei_num}** / 馬連・ワイド: **{honmei_num} － {aite_str}**\n")

    lines.append("---\n")
    lines.append("※ KeibaAIの予測結果は的中を保証するものではありません。馬券のご購入は自己責任でお願いいたします。")

    mdx_content = "\n".join(lines)

    os.makedirs(TARGET_MDX_DIR, exist_ok=True)
    out_file = os.path.join(TARGET_MDX_DIR, f"{target_date}-keiba-ai-predictions.mdx")
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(mdx_content)

    print(f"[SUCCESS] Exported ENHANCED real predictions MDX with EV logic to: {out_file}")


if __name__ == "__main__":
    export_real_prediction_mdx('2026-07-26')
