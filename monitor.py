import re
import urllib.request
import urllib.error
from html import unescape
from datetime import datetime, timezone

PRODUCT = "HG 1/144 ガンダムヴァサーゴ"
MAX_PRICE = 3190

STORES = {
    "Amazon": "https://www.amazon.co.jp/dp/B0H32PBNFR",
}

def fetch_page(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja-JP,ja;q=0.9",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", "replace")
            return response.status, html
    except urllib.error.HTTPError as error:
        return error.code, None
    except Exception:
        return None, None

def check_amazon(url):
    status, html = fetch_page(url)

    if status != 200 or not html:
        return "確認失敗", f"HTTP: {status}"

    text = unescape(re.sub(r"<[^>]*>", " ", html))
    text = re.sub(r"\s+", " ", text)

    if "ガンダムヴァサーゴ" not in text:
        return "判定不能", "商品名を確認できません"

    if "カートに入れる" not in text:
        return "未確認", "購入ボタンが見つかりません"

    return (
        "要確認",
        "購入ボタンあり。販売元・価格・送料は未確定"
    )

def main():
    print("監視商品:", PRODUCT)
    print("価格上限:", MAX_PRICE, "円")
    print("確認日時:", datetime.now(timezone.utc).isoformat())

    for store, url in STORES.items():
        status, detail = check_amazon(url)
        print(f"{store}: {status}")
        print("詳細:", detail)
        print("URL:", url)

    print("自動入荷通知: 無効")
    print("未確認の情報では通知しません")

if __name__ == "__main__":
    main()
