import streamlit as st
import os
import sys
import sqlite3
import pandas as pd
import numpy as np
import json
import itertools
import re
import subprocess
import plotly.graph_objects as go

# config のインポート（app.py から呼ばれる場合と単独実行の両方に対応）
try:
    import config
except ModuleNotFoundError:
    import sys, os
    _dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.abspath(os.path.join(_dir, '..', '..')))  # PROJECT_ROOT
    sys.path.insert(0, os.path.abspath(os.path.join(_dir, '..')))        # src/
    import config


def render_recovery_analysis(db_path, project_root):
    st.header("回収率分析")

    # --- 結果更新ボタン ---
    if st.button("レース結果を更新する (未確定レースの取得)"):
        with st.spinner("レース結果を取得・更新中... (数分かかる場合があります)"):
            script_path = os.path.join(project_root, 'src', 'prediction', 'update_results.py')
            result = subprocess.run(
                [sys.executable, script_path], 
                capture_output=True, 
                text=True, 
                encoding='utf-8'
            )
            if result.returncode == 0:
                st.success("レース結果の更新が完了しました！")
                with st.expander("更新ログ詳細"):
                    st.text(result.stdout)
            else:
                st.error("更新中にエラーが発生しました。")
                st.text(result.stderr)

    if not os.path.exists(db_path):
        st.error("データベースファイルが見つかりません。")
        return

    # --- データベース接続 ---
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        
        # 必要なデータを結合して取得
        query = """
        SELECT
            p.race_id,
            p.race_number,
            p.umaban,
            p.pred_rank,
            p.result_rank,
            p.kaisai_date,
            p.race_class,
            pay.tansho_payout, pay.tansho_numbers,
            pay.fukusho_payouts,
            pay.umaren_payout, pay.umaren_numbers,
            pay.wide_payouts,
            pay.umatan_payout, pay.umatan_numbers,
            pay.sanrenpuku_payout, pay.sanrenpuku_numbers,
            pay.sanrentan_payout, pay.sanrentan_numbers
        FROM
            predictions p
        LEFT JOIN payouts pay ON p.race_id = pay.race_id
        WHERE
            p.result_rank IS NOT NULL
        ORDER BY
            p.race_id, p.pred_rank;
        """
        try:
            df = pd.read_sql_query(query, conn)
        except Exception as e:
            st.error(f"データ取得エラー: {e}")
            return

    if df.empty:
        st.info("分析対象のデータがありません。予測を実行し、結果を更新してください。")
        return

    # --- サイドバー設定 (分析条件) ---
    st.sidebar.subheader("📊 分析条件設定")

    # 1. レースフィルター
    st.sidebar.markdown("### 1. レースフィルター")
    race_num_range = st.sidebar.slider("レース番号範囲", 1, 12, (1, 12))
    
    unique_classes = df['race_class'].dropna().unique().tolist()
    unique_classes = [c for c in unique_classes if c] # Remove empty strings
    
    selected_classes = st.sidebar.multiselect("レースクラス", ["全て"] + unique_classes, default=["全て"])

    # 2. 賭け式設定
    st.sidebar.markdown("### 2. シミュレーション設定")
    bet_type = st.sidebar.selectbox("券種", ["単勝", "複勝", "馬連", "ワイド", "馬単", "3連複", "3連単"])
    strategy = st.sidebar.selectbox("買い方", ["ボックス", "流し(1頭軸)", "フォーメーション - 未実装"], index=0)

    # パラメータ設定 (買い方に応じて変化)
    top_n = 5 # default
    axis_rank = 1
    opponent_count = 5

    if strategy == "ボックス":
        top_n = st.sidebar.number_input("予測上位何頭を買うか (Box)", min_value=1, max_value=18, value=5)
    elif strategy == "流し(1頭軸)":
        axis_rank = st.sidebar.number_input("軸馬にする予測順位 (1頭)", min_value=1, max_value=18, value=1)
        opponent_count = st.sidebar.number_input("相手にする頭数 (予測上位から)", min_value=1, max_value=18, value=5)
    else:
        st.sidebar.warning("現在ボックスと流し(1頭軸)のみサポートしています。")

    bet_amount = st.sidebar.number_input("1点あたりの投資額 (円)", min_value=100, step=100, value=100)

    # --- 分析ロジック ---

    # 1. フィルター適用
    mask = (df['race_number'] >= race_num_range[0]) & (df['race_number'] <= race_num_range[1])
    if "全て" not in selected_classes and selected_classes:
        mask &= df['race_class'].isin(selected_classes)
        
    filtered_df = df[mask].copy()

    if filtered_df.empty:
        st.warning("条件に一致するレースがありません。")
        return

    # レースごとに処理
    race_ids = filtered_df['race_id'].unique()

    total_investment = 0
    total_return = 0
    hit_count = 0
    race_results_list = []

    for race_id in race_ids:
        race_data = filtered_df[filtered_df['race_id'] == race_id]

        # --- 買い目生成ロジック ---
        combinations = []
        
        if strategy == "ボックス":
            top_horses = race_data.nsmallest(top_n, 'pred_rank')
            selected_umabans = top_horses['umaban'].tolist()
            
            if bet_type == "単勝":
                combinations = [(u,) for u in selected_umabans]
            elif bet_type == "複勝":
                combinations = [(u,) for u in selected_umabans]
            elif bet_type == "馬連":
                combinations = list(itertools.combinations(selected_umabans, 2))
            elif bet_type == "ワイド":
                combinations = list(itertools.combinations(selected_umabans, 2))
            elif bet_type == "馬単":
                combinations = list(itertools.permutations(selected_umabans, 2))
            elif bet_type == "3連複":
                combinations = list(itertools.combinations(selected_umabans, 3))
            elif bet_type == "3連単":
                combinations = list(itertools.permutations(selected_umabans, 3))
                
        elif strategy == "流し(1頭軸)":
            axis_horse = race_data[race_data['pred_rank'] == axis_rank]
            if axis_horse.empty:
                continue
            axis_umaban = axis_horse['umaban'].iloc[0]
            
            race_data_sorted = race_data.sort_values('pred_rank')
            opponents = race_data_sorted[race_data_sorted['umaban'] != axis_umaban].head(opponent_count)
            opponent_umabans = opponents['umaban'].tolist()
            
            if not opponent_umabans:
                continue

            if bet_type in ["単勝", "複勝"]:
                 combinations = [(axis_umaban,)]
            elif bet_type == "馬連":
                combinations = [(min(axis_umaban, opp), max(axis_umaban, opp)) for opp in opponent_umabans]
            elif bet_type == "ワイド":
                combinations = [(min(axis_umaban, opp), max(axis_umaban, opp)) for opp in opponent_umabans]
            elif bet_type == "馬単":
                combinations = [(axis_umaban, opp) for opp in opponent_umabans]
            elif bet_type == "3連複":
                opp_combos = list(itertools.combinations(opponent_umabans, 2))
                for c in opp_combos:
                    combo = tuple(sorted([axis_umaban, c[0], c[1]]))
                    combinations.append(combo)
            elif bet_type == "3連単":
                opp_perms = list(itertools.permutations(opponent_umabans, 2))
                for p in opp_perms:
                    combinations.append((axis_umaban, p[0], p[1]))

        # 投資額加算
        investment = len(combinations) * bet_amount
        total_investment += investment

        # 払い戻し判定
        payout = 0
        hit_flag = False

        row = race_data.iloc[0]

        if pd.isna(row['tansho_numbers']):
            continue

        # 的中判定ロジック
        def check_hit(bet_combo, result_numbers_str, payout_val):
            if not result_numbers_str: return 0
            bet_set = set(map(str, bet_combo))
            res_nums = re.findall(r'\d+', str(result_numbers_str))
            res_set = set(res_nums)

            if bet_type in ["馬単", "3連単"]:
                if tuple(map(str, bet_combo)) == tuple(res_nums):
                    return payout_val
            else:
                if bet_set == res_set:
                    return payout_val
            return 0

        # 券種ごとの判定
        race_payout = 0

        if bet_type == "単勝":
            if str(row['tansho_numbers']) in [str(c[0]) for c in combinations]:
                race_payout += row['tansho_payout']

        elif bet_type == "複勝":
            try:
                fuku_dict = json.loads(row['fukusho_payouts'])
                for bet in combinations:
                    u = str(bet[0])
                    if u in fuku_dict:
                        race_payout += fuku_dict[u]
            except: pass

        elif bet_type == "馬連":
            for bet in combinations:
                race_payout += check_hit(bet, row['umaren_numbers'], row['umaren_payout'])

        elif bet_type == "ワイド":
            try:
                wide_dict = json.loads(row['wide_payouts'])
                for bet in combinations:
                    bet_set = set(map(str, bet))
                    for key, pay in wide_dict.items():
                        key_set = set(re.findall(r'\d+', key))
                        if bet_set == key_set:
                            race_payout += pay
            except: pass

        elif bet_type == "馬単":
            for bet in combinations:
                race_payout += check_hit(bet, row['umatan_numbers'], row['umatan_payout'])

        elif bet_type == "3連複":
            for bet in combinations:
                race_payout += check_hit(bet, row['sanrenpuku_numbers'], row['sanrenpuku_payout'])

        elif bet_type == "3連単":
            for bet in combinations:
                race_payout += check_hit(bet, row['sanrentan_numbers'], row['sanrentan_payout'])

        if race_payout > 0:
            hit_count += 1
            hit_flag = True

        total_return += race_payout

        race_results_list.append({
            "race_id": race_id,
            "race_num": row['race_number'],
            "race_class": row['race_class'],
            "date": row['kaisai_date'],
            "investment": investment,
            "return": race_payout,
            "hit": "🎯" if hit_flag else "-"
        })

    # --- 結果表示 ---
    total_races = len(race_ids)
    hit_rate = (hit_count / total_races) * 100 if total_races > 0 else 0
    recovery_rate = (total_return / total_investment) * 100 if total_investment > 0 else 0

    st.markdown("---")
    st.subheader(f"分析結果 ({bet_type} / {strategy} / Top {top_n}頭)")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("対象レース数", f"{total_races} レース")
    col2.metric("的中率", f"{hit_rate:.1f}%")
    col3.metric("回収率", f"{recovery_rate:.1f}%", delta=f"{recovery_rate - 100:.1f}%")
    col4.metric("払戻", f"{total_return - total_investment:,} 円")
    st.write(f"総投資: {total_investment:,} 円 / 総払戻: {total_return:,} 円")

    # 詳細テーブル
    with st.expander("レース別詳細を見る"):
        st.dataframe(pd.DataFrame(race_results_list))

    # --- クラス別推移分析 ---
    st.markdown("---")
    st.subheader("📊 クラス別成績")
    
    if race_results_list:
        res_df = pd.DataFrame(race_results_list)
        res_df['race_class'] = res_df['race_class'].replace('', '不明/過去データ').fillna('不明/過去データ')
        
        class_stats = res_df.groupby('race_class').agg({
            'investment': 'sum',
            'return': 'sum',
            'race_id': 'count',
            'hit': lambda x: (x == "🎯").sum()
        }).reset_index()
        
        class_stats['recovery_rate'] = (class_stats['return'] / class_stats['investment'] * 100).fillna(0)
        class_stats['hit_rate'] = (class_stats['hit'] / class_stats['race_id'] * 100).fillna(0)
        class_stats.sort_values('race_id', ascending=False, inplace=True)
        
        # グラフ作成
        fig_class = go.Figure()
        fig_class.add_trace(go.Bar(
            x=class_stats['race_class'],
            y=class_stats['recovery_rate'],
            name='回収率',
            marker_color='mediumseagreen'
        ))
        fig_class.add_hline(y=100, line_dash="dash", line_color="red")
        fig_class.update_layout(
            title='クラス別 回収率',
            xaxis_title='クラス',
            yaxis_title='回収率 (%)'
        )
        st.plotly_chart(fig_class, use_container_width=True)
        st.dataframe(class_stats)

    # --- 日別推移分析 ---
    st.markdown("---")
    st.subheader("📅 日別推移")

    if race_results_list:
        res_df = pd.DataFrame(race_results_list)
        
        daily_stats = res_df.groupby('date').agg({
            'investment': 'sum',
            'return': 'sum',
            'race_id': 'count',
            'hit': lambda x: (x == "🎯").sum()
        }).reset_index()

        daily_stats['recovery_rate'] = (daily_stats['return'] / daily_stats['investment'] * 100).fillna(0)
        daily_stats['hit_rate'] = (daily_stats['hit'] / daily_stats['race_id'] * 100).fillna(0)
        daily_stats.rename(columns={'race_id': 'race_count', 'hit': 'hit_count'}, inplace=True)
        daily_stats.sort_values('date', inplace=True)

        fig = go.Figure()

        # 回収率
        fig.add_trace(go.Bar(
            x=daily_stats['date'],
            y=daily_stats['recovery_rate'],
            name='回収率',
            yaxis='y1',
            marker_color='lightblue',
            opacity=0.7
        ))

        # 的中率
        fig.add_trace(go.Scatter(
            x=daily_stats['date'],
            y=daily_stats['hit_rate'],
            name='的中率',
            yaxis='y2',
            mode='lines+markers',
            line=dict(color='orange', width=2)
        ))

        fig.update_layout(
            title='日別 回収率・的中率推移',
            xaxis=dict(title='日付'),
            yaxis=dict(
                title='回収率 (%)',
                side='left',
                showgrid=True,
            ),
            yaxis2=dict(
                title='的中率 (%)',
                side='right',
                overlaying='y',
                showgrid=False,
                range=[0, 100]
            ),
            legend=dict(x=0.01, y=0.99),
            hovermode='x unified'
        )
        
        fig.add_hline(y=100, line_dash="dash", line_color="red", annotation_text="100%")
        st.plotly_chart(fig, use_container_width=True)

        st.write("##### 日別詳細データ")
        display_daily = daily_stats.copy()
        display_daily['recovery_rate'] = display_daily['recovery_rate'].map('{:.1f}%'.format)
        display_daily['hit_rate'] = display_daily['hit_rate'].map('{:.1f}%'.format)
        display_daily['investment'] = display_daily['investment'].map('{:,} 円'.format)
        display_daily['return'] = display_daily['return'].map('{:,} 円'.format)
        
        st.dataframe(
            display_daily[['date', 'race_count', 'hit_count', 'hit_rate', 'investment', 'return', 'recovery_rate']],
            column_config={
                "date": "日付",
                "race_count": "レース数",
                "hit_count": "的中数",
                "hit_rate": "的中率",
                "investment": "投資額",
                "return": "払戻額",
                "recovery_rate": "回収率"
            },
            hide_index=True
        )
