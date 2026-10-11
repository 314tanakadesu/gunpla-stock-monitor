import re
import urllib.request
from html import unescape

PRODUCT_URL = "https://www.amazon.co.jp/dp/B0H32PBNFR"
MAX_PRICE = 3190

def check_stock():
    request = urllib.request.Request(
        PRODUCT_URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja-JP,ja;q=0.9",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", "replace")
    except Exception as error:
        print(f"確認失敗: {type(error).__name__}")
        return

    text = unescape(re.sub(r"<[^>]*>", " ", html))
    text = re.sub(r"\s+", " ", text)

    if "ガンダムヴァサーゴ" not in text:
        print("商品情報を確認できません")
        return

    if "カートに入れる" not in text:
        print("購入可能な在庫は確認できません")
        return

    print("購入ボタンを検出しました。販売元と価格の確認が必要です。")
    print(PRODUCT_URL)

if __name__ == "__main__":
    check_stock()
