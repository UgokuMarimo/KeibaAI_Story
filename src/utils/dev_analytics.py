import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
import lightgbm as lgb
import config
from .analytics_common import load_prediction_data_common

def load_prediction_data(db_path):
    """
    Load prediction data using shared logic.
    """
    return load_prediction_data_common(db_path)

def calculate_race_metrics(df):
    """
    Calculate race-level metrics: Avg Win Prob, Top Prob Gap, Top Prob.
    Uses 'win_prob' and 'tansho_odds' already present from load_prediction_data_common.
    """
    race_metrics = []

    for race_id, group in df.groupby('race_id'):
        # Sort by predicted rank
        group = group.sort_values('pred_rank')
        
        # 1. Average Win Probability
        avg_prob = group['win_prob'].mean()
        
        # 2. Top Probability (Rank 1)
        if len(group) >= 1:
            top_prob = group.iloc[0]['win_prob']
            top_odds = group.iloc[0]['tansho_odds']
            # fillna(0) for odds just in case
            safe_odds = top_odds if pd.notna(top_odds) else 0.0
            top_ev = top_prob * safe_odds
        else:
            top_prob = 0
            top_odds = 0
            top_ev = 0
            
        # 3. Top Probability Gap (Rank 1 - Rank 2)
        if len(group) >= 2:
            gap = group.iloc[0]['win_prob'] - group.iloc[1]['win_prob']
        else:
            gap = 0 # Only one horse?
            
        # Outcome for Rank 1
        rank1_row = group[group['pred_rank'] == 1]
        is_hit = False
        return_amount = 0
        if not rank1_row.empty:
            is_hit = (rank1_row.iloc[0]['result_rank'] == 1)
            # 'return' is already calculated per row in load_prediction_data_common if won
            return_amount = rank1_row.iloc[0]['return']
            
        race_metrics.append({
            'race_id': race_id,
            'avg_win_prob': avg_prob,
            'top_win_prob': top_prob,
            'top_odds': top_odds, 
            'top_ev': top_ev,     
            'top_prob_gap': gap,
            'is_hit': int(is_hit),
            'return': return_amount
        })
        
    return pd.DataFrame(race_metrics)

def render_developer_page(db_path):
    st.header("🛠️ 開発者用予測分析 (Metrics Analysis)")
    
    df_raw = load_prediction_data(db_path)
    if df_raw.empty:
        st.warning("データベースに有効な予測結果（着順あり）がありません。")
        return

    st.info(f"分析対象: {df_raw['race_id'].nunique()} レース")

    # --- 1. Track Type Filter ---
    st.sidebar.markdown("## 📊 分析フィルター")
    
    # Filter out None/Empty if any
    av_tracks = df_raw['track_type'].dropna().unique().tolist()
    
    if av_tracks:
        selected_tracks = st.sidebar.multiselect(
            "トラック種別 (Track Type)", 
            options=av_tracks, 
            default=av_tracks
        )
        if not selected_tracks:
            st.error("少なくとも1つのトラックを選択してください。")
            return
        df_raw = df_raw[df_raw['track_type'].isin(selected_tracks)].copy()

    # Race-level aggregation
    df_races = calculate_race_metrics(df_raw)
    
    # --- UI for Analysis ---
    
    metrics = {
        "平均勝率 (Average Win Prob)": "avg_win_prob",
        "トップ勝率 (Top Win Prob)": "top_win_prob",
        "トップ勝率差 (Top Prob Gap)": "top_prob_gap"
    }

    st.subheader("指標別の回収率・的中率分析")
    
    with st.expander("📊 グラフの見方・指標の解説 (クリックして開く)", expanded=True):
        st.markdown("""
        **各指標の意味:**
        - **平均勝率 (Average Win Prob)**: レース全体の「堅さ」。値が高いほど、有力馬が明確で荒れにくいレース傾向。
        - **トップ勝率 (Top Win Prob)**: 予測1位の馬の「信頼度」。AIがその馬の勝利をどれだけ確信しているか。
        - **トップ勝率差 (Top Prob Gap)**: 予測1位と2位の「実力差」。差が大きいほど「1強」、小さいほど「大混戦」。
        
        **グラフの見方:**
        - **横軸 (Bin)**: 指標の値を「低い順」から「高い順」にグループ分けしたもの。
            - 左側: 指標が低いレース群（例: 混戦、自信なし）
            - 右側: 指標が高いレース群（例: 1強、自信あり）
        - **棒グラフ (水色)**: **的中率 (%)**。予測1位が実際に1着になった確率。（左軸）
        - **折れ線 (オレンジ)**: **回収率 (%)**。単勝を均等買いした場合の収益性。（右軸。100%超で黒字）
        """)
    
    for label, col in metrics.items():
        st.markdown(f"### {label}")
        
        # Binning (Quantile cut)
        n_bins = st.slider(f"{label}: 分割数 (Bins)", min_value=2, max_value=10, value=4, key=f"bins_{col}")
        
        try:
            df_races[f'{col}_bin'] = pd.qcut(df_races[col], q=n_bins, duplicates='drop')
        except ValueError:
            st.warning(f"{label} のデータ分布が偏りすぎているため、等分割できませんでした。標準の分割を使用します。")
            df_races[f'{col}_bin'] = pd.cut(df_races[col], bins=n_bins)

        # Aggregate metrics
        grouped = df_races.groupby(f'{col}_bin', observed=False).agg(
            count=('race_id', 'count'),
            hit_count=('is_hit', 'sum'),
            total_return=('return', 'sum')
        ).reset_index()

        grouped['hit_rate'] = (grouped['hit_count'] / grouped['count']) * 100
        # Assume 100 yen flat bet per race
        grouped['recovery_rate'] = (grouped['total_return'] / (grouped['count'] * 100)) * 100
        
        # Sort bins for display (convert interval to string for plotting)
        grouped['bin_label'] = grouped[f'{col}_bin'].astype(str)
        
        # Visualization
        fig = go.Figure()
        
        # Bar: Hit Rate
        fig.add_trace(go.Bar(
            x=grouped['bin_label'],
            y=grouped['hit_rate'],
            name='的中率 (%)',
            marker_color='skyblue',
            yaxis='y1'
        ))
        
        # Line: Recovery Rate
        fig.add_trace(go.Scatter(
            x=grouped['bin_label'],
            y=grouped['recovery_rate'],
            name='回収率 (%)',
            mode='lines+markers',
            line=dict(color='orange', width=3),
            yaxis='y2'
        ))
        
        fig.update_layout(
            title=f"{label} による特性",
            xaxis_title="指標グループ (Low -> High)",
            yaxis=dict(title="的中率 (%)", side="left", showgrid=False),
            yaxis2=dict(title="回収率 (%)", side="right", overlaying="y", showgrid=False),
            shapes=[
                dict(type="line", xref="paper", x0=0, x1=1, yref="y2", y0=100, y1=100,
                     line=dict(color="red", width=1, dash="dash"))
            ]
        )
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander(f"{label} 詳細データ"):
            st.dataframe(grouped.style.format({
                'hit_rate': "{:.1f}%",
                'recovery_rate': "{:.1f}%"
            }))

    # --- Strategy Simulation ---
    render_simulation_section(df_races)
    
    # --- Feature Importance ---
    render_feature_importance_section()

def render_simulation_section(df_races):
    st.markdown("---")
    st.header("📈 投資戦略シミュレーション (Strategy Simulation)")
    st.info("AIの予測指標に基づいて、レースを厳選した場合の収支をシミュレーションします。")

    col1, col2 = st.columns(2)
    
    with col1:
        min_conf = st.slider("自信度フィルター (Top Win Prob > X)", 
                             min_value=0.0, max_value=1.0, value=0.0, step=0.05,
                             help="予測1位の勝率がこの値以上のレースのみ購入します。")
        
    with col2:
        min_odds = st.slider("最低オッズフィルター (Odds >= X)",
                             min_value=1.0, max_value=5.0, value=1.0, step=0.1,
                             help="予測1位の単勝オッズがこの値以上のレースのみ購入します（低配当除外）。")
        
    # Filter Data
    # 1. Confidence Filter
    mask = (df_races['top_win_prob'] >= min_conf)
    # 2. Odds Filter
    # Ensure top_odds is numeric
    df_races['top_odds'] = pd.to_numeric(df_races['top_odds'], errors='coerce').fillna(0)
    mask &= (df_races['top_odds'] >= min_odds)
    
    sim_df = df_races[mask].copy()
    
    if sim_df.empty:
        st.warning("条件に一致するレースがありません。フィルターを緩めてください。")
        return

    # Simulation Calculation
    # Cost = 100 yen per race
    # Return = 'return' column
    sim_df['profit'] = sim_df['return'] - 100
    sim_df['cumulative_profit'] = sim_df['profit'].cumsum()
    
    # --- Summary Metrics ---
    total_races = len(sim_df)
    hit_count = sim_df['is_hit'].sum()
    total_return = sim_df['return'].sum()
    total_cost = total_races * 100
    net_profit = total_return - total_cost
    hit_rate = (hit_count / total_races) * 100 if total_races > 0 else 0
    recovery_rate = (total_return / total_cost) * 100 if total_cost > 0 else 0
    
    st.markdown("### シミュレーション結果")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("購入レース数", f"{total_races} レース")
    m2.metric("的中率", f"{hit_rate:.1f} %")
    m3.metric("回収率", f"{recovery_rate:.1f} %", delta=f"{recovery_rate - 100:.1f} %")
    m4.metric("純損益", f"{net_profit:+,} 円", delta_color="normal")

    # --- Visualization ---
    fig = go.Figure()
    
    # Cumulative Profit Line
    fig.add_trace(go.Scatter(
        x=np.arange(len(sim_df)),
        y=sim_df['cumulative_profit'],
        mode='lines',
        name='累積損益',
        fill='tozeroy',
        line=dict(color='green' if net_profit >= 0 else 'red')
    ))
    
    fig.update_layout(
        title="資産推移シミュレーション (単勝100円均等買い)",
        xaxis_title="レース経過数 (時系列)",
        yaxis_title="累積損益 (円)",
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Show Data
    with st.expander("詳細データを見る"):
        st.dataframe(sim_df[['race_id', 'top_win_prob', 'top_odds', 'is_hit', 'return', 'profit']])

def render_feature_importance_section():
    st.markdown("---")
    st.header("🧠 特徴量重要度分析 (Feature Importance)")
    st.info("LightGBMモデルが学習時にどの特徴量を重視したかを可視化します。これにより、予測に寄与している要素を確認できます。")

    # 1. Select Model File
    model_dir = os.path.join(config.MODEL_DIR_BASE, config.EXPERIMENT_VERSION)
    if not os.path.exists(model_dir):
        st.error(f"モデルディレクトリが見つかりません: {model_dir}")
        return

    # Filter for .txt model files
    model_files = [f for f in os.listdir(model_dir) if f.startswith("lgb_model") and f.endswith(".txt")]
    
    if not model_files:
        st.warning("モデルファイル(.txt)が見つかりません。学習を実行してください。")
        return

    selected_model_file = st.selectbox("分析するモデルを選択", model_files)
    model_path = os.path.join(model_dir, selected_model_file)

    # 2. Load Model & Extract Importance
    try:
        booster = lgb.Booster(model_file=model_path)
        
        # Gain Importance (Quality of splits)
        importance_gain = booster.feature_importance(importance_type='gain')
        feature_names = booster.feature_name()
        
        # Create DataFrame
        df_imp = pd.DataFrame({
            'feature': feature_names,
            'importance_gain': importance_gain
        })
        
        # Normalize Gain (Percentage)
        df_imp['importance_gain_percent'] = (df_imp['importance_gain'] / df_imp['importance_gain'].sum()) * 100
        
        # Sort
        df_imp = df_imp.sort_values('importance_gain', ascending=False).reset_index(drop=True)
        
        # 3. Visualization
        top_n = st.slider("表示する特徴量数 (Top N)", min_value=5, max_value=50, value=20)
        df_viz = df_imp.head(top_n).sort_values('importance_gain', ascending=True) # Ascending for horizontal bar
        
        fig = px.bar(
            df_viz, 
            x='importance_gain_percent', 
            y='feature', 
            orientation='h',
            title=f"Feature Importance (Gain) - Top {top_n}",
            labels={'importance_gain_percent': 'Importance (Gain %)', 'feature': 'Feature Only'}
        )
        fig.update_layout(yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig, use_container_width=True)

        # 4. Show Full Data
        with st.expander("全特徴量の重要度リストを見る"):
            st.dataframe(df_imp)
            
    except Exception as e:
        st.error(f"モデルの読み込みまたは重要度の取得に失敗しました: {e}")
