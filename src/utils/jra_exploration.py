
import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

def setup_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    # Try using the same user-agent as the existing scraper
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    try:
        service = Service(ChromeDriverManager().install())
    except Exception:
        service = Service()

    driver = webdriver.Chrome(service=service, options=options)
    return driver

def explore():
    driver = setup_driver()
    try:
        # 1. Go to JRA Top
        print("Accessing JRA Top Page...")
        driver.get("https://www.jra.go.jp/")
        time.sleep(3)
        print(f"Title: {driver.title}")

        # Dump source
        with open("jra_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        
        # Dump links
        links = driver.find_elements(By.TAG_NAME, "a")
        with open("jra_links.txt", "w", encoding="utf-8") as f:
            for link in links:
                try:
                    txt = link.text.strip()
                    href = link.get_attribute("href")
                    onclick = link.get_attribute("onclick")
                    f.write(f"Text: {txt}, Href: {href}, Onclick: {onclick}\n")
                except:
                    continue
        
        print("Dumped source and links.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    explore()
