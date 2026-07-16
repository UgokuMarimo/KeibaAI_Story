import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from .analytics_common import (
    load_prediction_data_common, 
    plot_monthly_stats_common, 
    plot_venue_stats_common, 
    plot_ev_analysis_common
)

def load_analysis_data(db_path):
    """
    Load prediction and payout data using shared common logic.
    """
    return load_prediction_data_common(db_path)

def calculate_metrics(df):
    """
    Calculate overall metrics based on Rank 1 predictions.
    """
    # Filter for only the top-ranked predictions (1 per race)
    rank1_df = df[df['pred_rank'] == 1].copy()
    
    total_races = len(rank1_df)
    if total_races == 0:
        return 0, 0, 0, 0
        
    hit_count = rank1_df['is_hit'].sum()
    hit_rate = (hit_count / total_races) * 100
    
    # Common module calculates 'return' per row (0 if lost, payout if won)
    total_return = rank1_df['return'].sum()
    
    # Assume 100 yen bet per race
    total_investment = total_races * 100
    recovery_rate = (total_return / total_investment) * 100 if total_investment > 0 else 0
    
    return total_races, hit_rate, recovery_rate, total_return

def plot_monthly_stats(df):
    return plot_monthly_stats_common(df, rank_filter=1)

def plot_venue_stats(df):
    return plot_venue_stats_common(df, rank_filter=1)

def plot_track_type_stats(df):
    """
    Plot stats by Track Type (Turf/Dirt).
    Specific to this page.
    """
    rank1_df = df[df['pred_rank'] == 1].copy()
    
    def normalize_track(t):
        if '芝' in str(t): return '芝'
        if 'ダ' in str(t): return 'ダート'
        return 'その他'
        
    rank1_df['simple_track'] = rank1_df['track_type'].apply(normalize_track)
    
    track_stats = rank1_df.groupby('simple_track').apply(
        lambda x: pd.Series({
            'hit_rate': (x['is_hit'].sum() / len(x)) * 100,
            'recovery_rate': (x['return'].sum() / (len(x) * 100)) * 100,
        })
    ).reset_index()
    
    fig = px.bar(
        track_stats, 
        x='simple_track', 
        y=['hit_rate', 'recovery_rate'],
        barmode='group',
        title='芝・ダート別 成績',
        labels={'value': 'パーセント (%)', 'simple_track': 'コース区分', 'variable': '指標'}
    )
    
    # Add 100% line
    fig.add_shape(
        type="line",
        x0=-0.5, y0=100, x1=len(track_stats)-0.5, y1=100,
        line=dict(color="red", width=2, dash="dash"),
    )
    
    return fig

def plot_ev_analysis(df):
    return plot_ev_analysis_common(df, rank_filter=1)

def render_ev_dashboard(db_path):
    
    df = load_analysis_data(db_path)
    
    if df.empty:
        st.info("分析対象のデータがまだありません。")
        return

    # --- Overall Metrics ---
    total_races, hit_rate, recovery_rate, total_return = calculate_metrics(df)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("総予測レース数", f"{total_races} レース")
    col2.metric("単勝的中率 (1位)", f"{hit_rate:.1f}%")
    col3.metric("単勝回収率 (1位)", f"{recovery_rate:.1f}%", delta=f"{recovery_rate - 100:.1f}%")
    col4.metric("総払戻金", f"{int(total_return):,} 円")
    
    st.markdown("---")
    
    # --- Tabs for different analyses ---
    tab1, tab2, tab3, tab4 = st.tabs(["📈 時系列・全体", "🏟️ 会場・コース別", "💰 期待値分析", "📋 的中レース一覧"])
    
    with tab1:
        st.subheader("月別推移")
        st.plotly_chart(plot_monthly_stats(df), use_container_width=True)
        
        # Cumulative Recovery Rate
        rank1_df = df[df['pred_rank'] == 1].sort_values('kaisai_date').copy()
        rank1_df['cumulative_return'] = rank1_df['return'].cumsum()
        rank1_df['cumulative_invest'] = (rank1_df.index.to_series().reset_index(drop=True).index + 1) * 100
        rank1_df['cumulative_recovery'] = (rank1_df['cumulative_return'] / rank1_df['cumulative_invest']) * 100
        
        fig_cum = px.line(rank1_df, x='kaisai_date', y='cumulative_recovery', title='累積回収率の推移')
        fig_cum.add_hline(y=100, line_dash="dash", line_color="red")
        st.plotly_chart(fig_cum, use_container_width=True)

    with tab2:
        col_venue, col_track = st.columns(2)
        with col_venue:
            st.plotly_chart(plot_venue_stats(df), use_container_width=True)
        with col_track:
            st.plotly_chart(plot_track_type_stats(df), use_container_width=True)

    with tab3:
        st.subheader("期待値 (Expected Value) 分析")
        st.markdown("""
        **期待値 (EV)** = AI予測勝率 × 単勝オッズ
        
        - **EV > 1.0**: 理論上、長期的にプラスになる賭け
        - このグラフは、AIが1位と予測した馬の期待値ごとの成績を示しています。
        """)
        st.plotly_chart(plot_ev_analysis(df), use_container_width=True)
        
        # Simulation
        st.markdown("### 🛠️ 期待値シミュレーター")
        
        sim_mode = st.radio("シミュレーションモード", ["モードA: レース内「最大期待値」の馬を1頭買う", "モードB: 規定以上の期待値の馬を買う (多点買い可)"])
        
        if sim_mode == "モードA: レース内「最大期待値」の馬を1頭買う":
            st.info("各レースで最も期待値（EV）が高い馬を、単勝で1点買いした場合のシミュレーションです。")
            
            # 各レースで期待値最大の馬を抽出
            # 期待値が同じ場合は予測ランクが高い方を優先（sort_valuesで調整）
            # まずソート: race_id, expected_value(desc), pred_rank(asc)
            df_sorted = df.sort_values(['race_id', 'expected_value', 'pred_rank'], ascending=[True, False, True])
            max_ev_df = df_sorted.drop_duplicates(subset=['race_id'], keep='first')
            
            if not max_ev_df.empty:
                sim_races = len(max_ev_df)
                sim_hits = max_ev_df['is_hit'].sum()
                sim_return = max_ev_df['return'].sum()
                sim_invest = sim_races * 100
                
                s_col1, s_col2, s_col3 = st.columns(3)
                s_col1.metric("購入レース数", f"{sim_races}")
                s_col2.metric("的中率", f"{(sim_hits/sim_races)*100:.1f}%")
                rec_rate = (sim_return/sim_invest)*100
                s_col3.metric("回収率", f"{rec_rate:.1f}%", delta=f"{rec_rate-100:.1f}%")
                
                st.write(f"総投資: {sim_invest:,} 円 / 総払戻: {int(sim_return):,} 円")
            else:
                st.warning("データがありません。")

        elif sim_mode == "モードB: 規定以上の期待値の馬を買う (多点買い可)":
            st.info("期待値が閾値を超えている馬を購入します。1レースあたりの購入頭数制限も設定可能です。")
            
            col_th, col_limit, col_prob = st.columns(3)
            ev_threshold = col_th.slider("期待値の閾値 (これ以上なら購入)", 0.5, 5.0, 1.0, 0.1)
            limit_num = col_limit.number_input("1Rの最大購入頭数 (0=無制限)", 0, 18, 0)
            min_prob = col_prob.number_input("最低勝率フィルター (%)", 0.0, 50.0, 3.0, 0.5)
            
            # 1. 閾値 ＆ 最低勝率 フィルタ
            # win_prob は 0.0~1.0 なので、%表記の min_prob と比較するために 100倍するか、min_probを1/100する
            candidates = df[
                (df['expected_value'] >= ev_threshold) & 
                (df['win_prob'] * 100 >= min_prob)
            ].copy()
            
            if not candidates.empty:
                final_selection = candidates
                
                # 2. 頭数制限フィルタ
                if limit_num > 0:
                    # 期待値順にソートして、上位N頭に絞る
                    candidates = candidates.sort_values(['race_id', 'expected_value'], ascending=[True, False])
                    final_selection = candidates.groupby('race_id').head(limit_num)
                
                sim_tickets = len(final_selection)
                # レース数はユニークカウント
                sim_races = final_selection['race_id'].nunique()
                
                sim_hits = final_selection['is_hit'].sum()
                sim_return = final_selection['return'].sum()
                sim_invest = sim_tickets * 100
                
                s_col1, s_col2, s_col3 = st.columns(3)
                s_col1.metric("購入点数 (レース数)", f"{sim_tickets} ({sim_races}R)")
                
                # 的中率は「購入した馬券の中での当たり率」とするか「レース的中率」とするかだが、
                # ここではシンプルに「購入点数ベースの的中率」を表示
                # (多点買いならレース的中率はもっと上がるが、回収率が重要)
                hit_rate_ticket = (sim_hits/sim_tickets)*100 if sim_tickets > 0 else 0
                s_col2.metric("的中率 (点数ベース)", f"{hit_rate_ticket:.1f}%")
                
                rec_rate = (sim_return/sim_invest)*100 if sim_invest > 0 else 0
                s_col3.metric("回収率", f"{rec_rate:.1f}%", delta=f"{rec_rate-100:.1f}%")
                
                st.write(f"総投資: {sim_invest:,} 円 / 総払戻: {int(sim_return):,} 円")
                
                # 月別推移なども出せるとベストだが、まずは数値のみ
            else:
                st.warning(f"期待値 {ev_threshold} 以上の馬はいませんでした。")

    with tab4:
        st.subheader("的中レース一覧")
        hit_df = df[(df['pred_rank'] == 1) & (df['result_rank'] == 1)].copy()
        if not hit_df.empty:
            display_cols = ['kaisai_date', 'keibajo', 'race_number', 'horse_name', 'pred_win', 'tansho_odds', 'tansho_payout', 'expected_value']
            st.dataframe(
                hit_df[display_cols].sort_values('kaisai_date', ascending=False).style.format({
                    'pred_win': '{:.1%}',
                    'tansho_odds': '{:.1f}',
                    'expected_value': '{:.2f}'
                })
            )
        else:
            st.info("まだ的中したレースがありません。")
