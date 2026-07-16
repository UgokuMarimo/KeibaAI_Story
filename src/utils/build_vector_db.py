# C:\KeibaAI\code\utils\build_vector_db.py

#

import pandas as pd
import os
import sys
import chromadb
import google.generativeai as genai
from tqdm import tqdm
from dotenv import load_dotenv

# .envファイルの読み込み
load_dotenv()

# --- プロジェクトパス設定 ---
_current_dir = os.path.dirname(os.path.abspath(__file__)); PROJECT_ROOT = os.path.abspath(os.path.join(_current_dir, '..', '..')); sys.path.append(PROJECT_ROOT); sys.path.append(os.path.join(PROJECT_ROOT, 'src'))
import config

# APIキーを設定
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    raise ValueError("環境変数 'GOOGLE_API_KEY' が設定されていません。")
genai.configure(api_key=GOOGLE_API_KEY)

# --- 設定 ---
VECTOR_DB_PATH = os.path.join(PROJECT_ROOT, "vector_db") # DBの保存場所
COLLECTION_NAME = "race_results" # DB内のテーブル名
EMBEDDING_MODEL = "models/text-embedding-004" # Googleのベクトル化モデル

def main():
    print("--- [START] Building Vector Database ---")
    
    # 1. 全ての過去レースデータを読み込む
    all_dfs = []
    print(f"Loading past race data from {config.VECTOR_DB_START_YEAR} to {config.BUILD_END_YEAR}...")
    for year in range(config.VECTOR_DB_START_YEAR, config.BUILD_END_YEAR + 1):
        file_path = os.path.join(config.DATA_DIR, f"{year}.csv")
        if os.path.exists(file_path):
            all_dfs.append(pd.read_csv(file_path, encoding="SHIFT-JIS", low_memory=False))
    
    if not all_dfs:
        print("[ERROR] No data found in /data folder.")
        return
        
    df = pd.concat(all_dfs, ignore_index=True)
    df.dropna(subset=['horse_id', '着順', 'レース名'], inplace=True)
    
    # --- データ削減 & クリーニング ---
    # 着順を数値に変換（数字以外は除外）
    df['着順'] = pd.to_numeric(df['着順'], errors='coerce')
    df = df.dropna(subset=['着順'])
    
    # 上位5頭のみ保留 (傾向分析には勝馬・好走馬の情報が最重要であり、全体を埋め込むとノイズになるため)
    org_len = len(df)
    df = df[df['着順'] <= 5]
    print(f"Filtered to Top 5 performers: {len(df)} entries (Original: {org_len})")
    
    # 日付処理
    df['date_dt'] = pd.to_datetime(df['日付'], format='%Y年%m月%d日', errors='coerce')
    df['year'] = df['date_dt'].dt.year.fillna(0).astype(int)

    print(f"Loaded {len(df)} race entries for indexing.")

    # 2. データベースのセットアップ
    client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
    # 既に存在する場合は削除して作り直す
    if COLLECTION_NAME in [c.name for c in client.list_collections()]:
        print(f"Collection '{COLLECTION_NAME}' already exists. Deleting and rebuilding.")
        client.delete_collection(name=COLLECTION_NAME)
    
    collection = client.create_collection(name=COLLECTION_NAME)

    # 3. データをベクトル化してDBに保存
    # 処理が重いので、馬ごとにまとめて処理する
    print("Generating embeddings for each race entry...")
    documents = []
    metadatas = []
    ids = []
    
    # tqdmを使って進捗を表示
    for _, row in tqdm(df.iterrows(), total=len(df)):
        # 日付差 (ローテーション) の計算
        interval_text = ""
        if 'interval' in row and pd.notna(row['interval']):
             interval_text = f"間隔{int(row['interval'])}日"
        
        # ペース情報の追加
        pace_text = ""
        if 'race_pace' in row and pd.notna(row['race_pace']):
            pace_text = f"ペース:{row['race_pace']}"

        # 脚質/展開情報の追加
        corner_text = ""
        if 'corner_passage_text' in row and pd.notna(row['corner_passage_text']):
            corner_text = f"通過:{row['corner_passage_text']}"
            
        # 上がり3F
        agari_text = ""
        if '上がり' in row and pd.notna(row['上がり']):
            agari_text = f"上がり3F:{row['上がり']}"

        # LLMが検索しやすいように、各行を自然言語の「ドキュメント」に変換
        # ユーザーの質問「ジャパンカップの傾向」「前走上がり最速」に対応できるように情報を記述
        doc_text = (
            f"【{row['year']}年 {row['レース名']}】"
            f"開催:{row['日付']} コース:{row['場名']}{row['芝・ダート']}{row['距離']}m 馬場:{row['馬場']} "
            f"順位:{int(row['着順'])}着 馬名:{row['馬']} (騎手:{row['騎手']}) "
            f"{pace_text} {corner_text} {agari_text} {interval_text}"
        )
        documents.append(doc_text)
        
        # 後で参照できるように、元のデータをメタデータとして保存
        metadatas.append({
            "horse_id": str(row['horse_id']),
            "race_id": str(row['race_id']),
            "rank": str(row['着順']),
            "race_name": str(row['レース名']),
            "year": str(row['year']),
            "course": f"{row['場名']}{row['芝・ダート']}{row['距離']}m"
        })
        
        # 各ドキュメントの一意なID
        ids.append(f"{row['race_id']}_{row['horse_id']}")
    
    # GoogleのAPIを使って、全ドキュメントをバッチ処理でベクトルに変換
    print(f"Embedding {len(documents)} documents... (This may take a while)")
    
    batch_size = 100 # API limit safety
    for i in tqdm(range(0, len(documents), batch_size), desc="Embedding Batches"):
        batch_docs = documents[i : i + batch_size]
        batch_metadatas = metadatas[i : i + batch_size]
        batch_ids = ids[i : i + batch_size]
        
        try:
            result = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=batch_docs,
                task_type="RETRIEVAL_DOCUMENT"
            )
            batch_embeddings = result['embedding']
            
            # ベクトル化したデータをDBに保存
            collection.add(
                embeddings=batch_embeddings,
                documents=batch_docs,
                metadatas=batch_metadatas,
                ids=batch_ids
            )
        except Exception as e:
            print(f"[WARN] Batch {i // batch_size} failed: {e}")
            continue

    print("\n--- [SUCCESS] Vector Database has been built. ---")
    print(f"Total documents indexed: {collection.count()}")
    print(f"Database saved at: {VECTOR_DB_PATH}")

if __name__ == "__main__":
    main()