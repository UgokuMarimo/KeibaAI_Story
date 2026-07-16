import os
import time
import requests
from typing import Optional

class HTMLDownloader:
    """netkeibaのレース結果HTMLをダウンロードし、ローカルにキャッシュ（保存）するクラス。
    
    Javaの「単一責任の原則（Single Responsibility Principle）」に基づき、
    このクラスは「通信」と「ファイルの保存・読み込み」のみに専念します。
    HTMLの解析（パース）やデータ加工は一切行いません。
    """
    
    def __init__(self, save_dir: str = "data/raw_html", wait_time: float = 1.0, retry_wait_time: float = 5.0):
        """コンストラクタ（メンバ変数の初期化）
        
        Javaでいうフィールドの宣言とコンストラクタでの初期化に相当します。
        
        Args:
            save_dir (str): HTMLファイルを保存するベースディレクトリ
            wait_time (float): リクエスト間の待機時間（秒）
            retry_wait_time (float): 通信エラー時の再試行までの待機時間（秒）
        """
        self.save_dir = save_dir
        self.wait_time = wait_time
        self.retry_wait_time = retry_wait_time
        self.headers = {'User-Agent': 'Mozilla/5.0'}
    
    def _get_file_path(self, race_id: str) -> str:
        """レースIDからローカルのHTML保存先パスを生成する（カプセル化された内部メソッド）
        
        メソッド名の先頭にアンダースコア `_` をつけることで、
        Javaの「private」メソッドのように、クラスの内部からのみ呼び出すべきであることを示します。
        
        例: race_id='202605160101' -> 'data/raw_html/2026/202605160101.html'
        地方競馬の場合: 'data/local/raw_html/2026/202654053001.html'
        """
        year = race_id[:4]
        place_id = race_id[4:6]
        
        import config
        is_jra = place_id in config.PLACE_MAP
        
        if is_jra:
            return os.path.join(self.save_dir, year, f"{race_id}.html")
        else:
            local_save_dir = os.path.join(config.DATA_DIR, "local", "raw_html")
            return os.path.join(local_save_dir, year, f"{race_id}.html")

    def _fetch_from_web(self, url: str, race_id: str) -> Optional[str]:
        """ネットから実際にHTMLをダウンロードする内部メソッド（再試行処理付き）"""
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            r.raise_for_status()
            time.sleep(self.wait_time)  # サーバーへの負荷軽減（ウェイト）
            
            # netkeibaはEUC-JPでエンコードされているためデコードする
            return r.content.decode("euc-jp", "ignore")
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"[INFO] Race {race_id} not found (404).")
                return None
            
            # 404以外のエラー（サーバー一時ダウンなど）は1回リトライする
            print(f"[WARN] HTTP Error {e.response.status_code} for {race_id}. Retrying after {self.retry_wait_time}s...")
            time.sleep(self.retry_wait_time)
            try:
                r = requests.get(url, headers=self.headers, timeout=10)
                r.raise_for_status()
                return r.content.decode("euc-jp", "ignore")
            except Exception as e2:
                print(f"[ERROR] Retry failed for {race_id}: {e2}")
                return None
                
        except Exception as e:
            print(f"[WARN] Request failed for {race_id}: {e}. Retrying after {self.retry_wait_time}s...")
            time.sleep(self.retry_wait_time)
            try:
                r = requests.get(url, headers=self.headers, timeout=10)
                r.raise_for_status()
                return r.content.decode("euc-jp", "ignore")
            except Exception as e2:
                print(f"[ERROR] Retry failed for {race_id}: {e2}")
                return None

    def get_html(self, race_id: str, force_fetch: bool = False) -> Optional[str]:
        """指定されたレースIDのHTMLデータを取得する（外部公開用のpublicメソッド）
        
        ローカルキャッシュ（ファイル）があればそれを読み込み、
        なければネットからダウンロードして保存し、その内容を返します。
        
        Args:
            race_id (str): レースID
            force_fetch (bool): Trueの場合、キャッシュがあっても無視してネットから再取得します。
        """
        file_path = self._get_file_path(race_id)
        
        # 1. ローカルキャッシュがある場合：ファイルから読み込む (force_fetchがFalseの場合のみ)
        if not force_fetch and os.path.exists(file_path):
            print(f"[CACHE] Loaded race {race_id} from local HTML file.")
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
                
        # 2. ローカルキャッシュがない、またはforce_fetch=Trueの場合：ネットから取得
        url = f"https://db.netkeiba.com/race/{race_id}"
        print(f"[NET] Fetching race {race_id} from netkeiba...")
        html_content = self._fetch_from_web(url, race_id)
        
        # 3. 取得に成功したらローカルに保存（キャッシュ）する（上書き保存）
        if html_content:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # ネットから取得したデータはEUC-JPですが、utf-8で保存し直します。
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"[CACHE] Saved race {race_id} to local HTML file.")
            
        return html_content
