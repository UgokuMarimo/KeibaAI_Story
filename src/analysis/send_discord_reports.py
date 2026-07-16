# C:\KeibaAI\src\analysis\send_discord_reports.py
import json
import urllib.request
import time
import sys

# Windows環境でのコンソール文字コード対策
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

webhook_url = "https://discordapp.com/api/webhooks/1513097156091711538/0RoI66LGE-rw2M3D9dlmaG22Tl8TWO12WBCRUqufAwwkWCzuGh7XgxG9yYn9WKfGAqdh"

def send_discord_message(content):
    payload = {"content": content}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    }
    
    req = urllib.request.Request(
        webhook_url, 
        data=json.dumps(payload).encode('utf-8'), 
        headers=headers, 
        method='POST'
    )
    try:
        with urllib.request.urlopen(req) as response:
            if response.status in [200, 204]:
                print("Discordへの送信が成功しました。")
            else:
                print(f"ステータスコード: {response.status}")
    except Exception as e:
        print(f"送信エラー: {e}")

def main():
    # 1. 4月度レポート
    report_april = (
        "🏆 **2026年4月度 成績シミュレーション結果（EV >= 1.3）**\n"
        "```yaml\n"
        "開催日数: 5日間\n"
        "購入頭数: 80頭 (1日平均: 16.00頭)\n"
        "的中数  : 8頭 (的中率: 10.0%)\n"
        "総投資額: 8,000円\n"
        "総払戻額: 11,460円\n"
        "回収率  : 143.2%\n"
        "純損益  : +3,460円\n"
        "```"
    )

    # 2. 5月度レポート
    report_may = (
        "🏆 **2026年5月度 成績シミュレーション結果（EV >= 1.3）**\n"
        "```yaml\n"
        "開催日数: 8日間\n"
        "購入頭数: 165頭 (1日平均: 20.63頭)\n"
        "的中数  : 13頭 (的中率: 7.9%)\n"
        "総投資額: 16,500円\n"
        "総払戻額: 21,080円\n"
        "回収率  : 127.8%\n"
        "純損益  : +4,580円\n"
        "```"
    )

    # 3. 累計レポート (4月〜5月)
    report_total = (
        "📊 **累計（4月〜5月）成績シミュレーション結果（EV >= 1.3）**\n"
        "```yaml\n"
        "開催日数: 13日間\n"
        "購入頭数: 245頭 (1日平均: 18.85頭)\n"
        "的中数  : 21頭 (的中率: 8.6%)\n"
        "総投資額: 24,500円\n"
        "総払戻額: 32,540円\n"
        "回収率  : 132.8%\n"
        "純損益  : +8,040円\n"
        "```"
    )

    print("--- 4月度レポートの送信中 ---")
    send_discord_message(report_april)
    time.sleep(2)  # レートリミット回避

    print("--- 5月度レポートの送信中 ---")
    send_discord_message(report_may)
    time.sleep(2)

    print("--- 累計レポートの送信中 ---")
    send_discord_message(report_total)

if __name__ == '__main__':
    main()
