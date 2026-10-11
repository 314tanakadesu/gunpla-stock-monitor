import re
import urllib.request
import urllib.error
from html import unescape

PRODUCTS = {
    "Amazon": "https://www.amazon.co.jp/dp/B0H32PBNFR",
}

MAX_PRICE = 3190

def check_store(name, url):
    print(f"\n確認先: {name}")
    print(f"商品ページ: {url}")

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
            print(f"HTTPステータス: {response.status}")
            print(f"取得データ: {len(html)}文字")
    except urllib.error.HTTPError as error:
        print(f"確認失敗: HTTP {error.code}")
        return
    except Exception as error:
        print(f"確認失敗: {type(error).__name__}")
        return

    text = unescape(re.sub(r"<[^>]*>", " ", html))
    text = re.sub(r"\s+", " ", text)

    if "ガンダムヴァサーゴ" not in text:
        print("判定不能: 商品名を確認できません")
        return

    print("商品名を確認しました")

    if "カートに入れる" not in text:
        print("購入可能な在庫は確認できません")
        return

    print("購入ボタンを検出しました")
    print("販売元・税込価格・送料の確認が必要です")
    print("自動入荷通知はまだ行いません")

def main():
    for name, url in PRODUCTS.items():
        check_store(name, url)

if __name__ == "__main__":
    main()
