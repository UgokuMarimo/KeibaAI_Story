
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

def load_prediction_data_common(db_path):
    """
    Load prediction data from the database with common columns needed for analysis.
    Computes normalized win probability and return amount.
    """
    with sqlite3.connect(db_path) as conn:
        query = """
        SELECT 
            p.race_id, p.race_number, p.umaban, p.horse_name,
            p.kaisai_date, p.keibajo, p.track_type, 
            p.pred_win, p.pred_rank, 
            p.result_rank, p.tansho_odds,
            pay.tansho_payout
        FROM predictions p
        LEFT JOIN payouts pay ON p.race_id = pay.race_id
        WHERE p.result_rank IS NOT NULL
        """
        df = pd.read_sql_query(query, conn)
    
    if df.empty:
        return df

    # Type definition
    df['race_id'] = df['race_id'].astype(str)
    
    # Date Handling
    if 'kaisai_date' in df.columns:
        df['kaisai_date'] = pd.to_datetime(df['kaisai_date'])
        df['month'] = df['kaisai_date'].dt.strftime('%Y-%m')

    # --- Common Calculation ---
    # 1. Normalize prediction score to probability
    df['race_total_score'] = df.groupby('race_id')['pred_win'].transform('sum')
    df['win_prob'] = df.apply(
        lambda x: x['pred_win'] / x['race_total_score'] if x['race_total_score'] > 0 else 0, 
        axis=1
    )
    
    # 2. EV Calculation
    # Ensure numeric
    df['tansho_odds'] = pd.to_numeric(df['tansho_odds'], errors='coerce').fillna(0)
    df['expected_value'] = df['win_prob'] * df['tansho_odds']
    
    # 3. Hit Flag
    df['is_hit'] = (df['result_rank'] == 1)
    
    # 4. Return Calculation (Flat 100 yen bet simulation)
    # Note: Logic assumes we bet on this specific row. 
    # Whether we bet or not depends on strategy (e.g. Rank 1 only), 
    # but 'return' column usually implies "If I bet on this horse, what do I get?"
    def calculate_return(row):
        if row['result_rank'] == 1:
            return row['tansho_payout'] if pd.notna(row['tansho_payout']) else 0
        return 0

    df['return'] = df.apply(calculate_return, axis=1)
    
    return df

def plot_monthly_stats_common(df, rank_filter=1):
    """
    Common Monthly Stats Plot.
    Usage: pass df filtered by rank if needed, or function filters by rank_filter.
    """
    # Usually we analyze Rank 1 performance
    target_df = df[df['pred_rank'] == rank_filter].copy()
    
    if 'month' not in target_df.columns:
         if 'kaisai_date' in target_df.columns:
             target_df['month'] = target_df['kaisai_date'].dt.strftime('%Y-%m')
         else:
             return go.Figure()

    if target_df.empty:
         return go.Figure()

    monthly_stats = target_df.groupby('month').apply(
        lambda x: pd.Series({
            'hit_rate': (x['is_hit'].sum() / len(x)) * 100,
            'recovery_rate': (x['return'].sum() / (len(x) * 100)) * 100,
            'count': len(x)
        })
    ).reset_index()
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=monthly_stats['month'], y=monthly_stats['hit_rate'],
        name='的中率 (%)', yaxis='y1', marker_color='rgba(55, 83, 109, 0.7)'
    ))
    fig.add_trace(go.Scatter(
        x=monthly_stats['month'], y=monthly_stats['recovery_rate'],
        name='回収率 (%)', yaxis='y2', mode='lines+markers',
        line=dict(color='rgb(219, 64, 82)', width=3)
    ))
    fig.update_layout(
        title='月別 的中率・回収率推移',
        xaxis=dict(title='年月'),
        yaxis=dict(title='的中率 (%)', side='left', range=[0, 100]),
        yaxis2=dict(title='回収率 (%)', side='right', overlaying='y', showgrid=False),
        legend=dict(x=0.01, y=0.99), hovermode='x unified'
    )
    return fig

def plot_venue_stats_common(df, rank_filter=1):
    """Common Venue Stats Plot."""
    target_df = df[df['pred_rank'] == rank_filter].copy()
    if target_df.empty: return go.Figure()

    venue_stats = target_df.groupby('keibajo').apply(
        lambda x: pd.Series({
            'hit_rate': (x['is_hit'].sum() / len(x)) * 100,
            'recovery_rate': (x['return'].sum() / (len(x) * 100)) * 100
        })
    ).reset_index().sort_values('recovery_rate', ascending=False)
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=venue_stats['keibajo'], y=venue_stats['hit_rate'],
        name='的中率 (%)', marker_color='rgba(55, 83, 109, 0.7)'
    ))
    fig.add_trace(go.Bar(
        x=venue_stats['keibajo'], y=venue_stats['recovery_rate'],
        name='回収率 (%)', marker_color='rgba(26, 118, 255, 0.7)'
    ))
    fig.add_shape(type="line", x0=-0.5, y0=100, x1=len(venue_stats)-0.5, y1=100, line=dict(color="red", width=2, dash="dash"))
    fig.update_layout(title='競馬場別 成績 (回収率順)', xaxis=dict(title='競馬場'), yaxis=dict(title='パーセント (%)'), barmode='group')
    return fig

def plot_ev_analysis_common(df, rank_filter=1):
    """Common EV Analysis Plot."""
    target_df = df[df['pred_rank'] == rank_filter].copy()
    if target_df.empty: return go.Figure()
    
    bins = [0, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 5.0, 100]
    labels = ['<0.5', '0.5-0.8', '0.8-1.0', '1.0-1.2', '1.2-1.5', '1.5-2.0', '2.0-5.0', '>5.0']
    
    target_df['ev_bin'] = pd.cut(target_df['expected_value'], bins=bins, labels=labels)
    
    ev_stats = target_df.groupby('ev_bin', observed=True).apply(
        lambda x: pd.Series({
            'hit_rate': (x['is_hit'].sum() / len(x)) * 100 if len(x) > 0 else 0,
            'recovery_rate': (x['return'].sum() / (len(x) * 100)) * 100 if len(x) > 0 else 0
        })
    ).reset_index()
    
    fig = go.Figure()
    fig.add_trace(go.Bar(x=ev_stats['ev_bin'], y=ev_stats['hit_rate'], name='的中率 (%)', marker_color='rgba(55, 83, 109, 0.7)'))
    fig.add_trace(go.Bar(x=ev_stats['ev_bin'], y=ev_stats['recovery_rate'], name='回収率 (%)', marker_color='rgba(26, 118, 255, 0.7)'))
    fig.add_shape(type="line", x0=-0.5, y0=100, x1=len(ev_stats)-0.5, y1=100, line=dict(color="red", width=2, dash="dash"))
    fig.update_layout(title='期待値(EV)別 成績 (AI予測1位)', xaxis=dict(title='期待値'), yaxis=dict(title='パーセント (%)'), barmode='group')
    return fig
