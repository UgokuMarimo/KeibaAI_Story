# C:\KeibaAI\scratch\get_quinella_odds.py
import requests
from bs4 import BeautifulSoup
import time

# 2024年日本ダービーのレースID (実在する確実なレースID)
# 2024年5月26日 東京11R 日本ダービー
race_id = "202405021211"
url = f"https://db.netkeiba.com/race/{race_id}"
headers = {'User-Agent': 'Mozilla/5.0'}

r = requests.get(url, headers=headers)
html = r.content.decode('euc-jp', 'ignore')
soup = BeautifulSoup(html, 'html.parser')

print("--- [2024 Derby 202405021211] confirmed Quinella result ---")
pay_table = soup.find("table", class_="pay_table_01")
if pay_table:
    for tr in pay_table.find_all("tr"):
        th = tr.find("th")
        if th and "馬連" in th.text:
            tds = tr.find_all("td")
            if len(tds) >= 2:
                print(f"馬連的中番: {tds[0].get_text(strip=True)}")
                print(f"馬連払戻金: {tds[1].get_text(strip=True)}")
else:
    print("Result not found")

# 馬連オッズの取得 (netkeibaのオッズAPI)
# netkeibaの馬連オッズAPIの検証
api_url = f"https://race.netkeiba.com/api/api_get_odds.html?race_id={race_id}&type=b4"
r_api = requests.get(api_url, headers=headers)
print(f"\nAPI URL: {api_url}")
print(f"API HTTP Status: {r_api.status_code}")

if r_api.status_code == 200:
    content = r_api.text
    print("\nAPI Response Preview:")
    soup_api = BeautifulSoup(content, 'html.parser')
    # 馬連オッズの最初の数件をパースして表示
    odds_elements = soup_api.find_all(class_='odds')
    if odds_elements:
        print(f"Successfully retrieved {len(odds_elements)} odds combinations.")
    else:
        # テキストを改行コードなどを消して綺麗に少し表示
        print(content[:500].replace('\n', ' '))
