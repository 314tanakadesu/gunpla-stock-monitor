import re
import json
import urllib.request
from html import unescape

URL = "https://www.amazon.co.jp/dp/B0H32PBNFR"
MAX_PRICE = 3190

def clean(value):
    return re.sub(r"\s+", " ", unescape(
        re.sub(r"<[^>]+>", " ", value)
    )).strip()

def main():
    request = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "ja-JP,ja;q=0.9",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", "replace")
            print("HTTP:", response.status)
    except Exception as error:
        print("確認失敗:", type(error).__name__)
        return

    text = clean(html)

    if "ガンダムヴァサーゴ" not in text:
        print("判定不能: 商品名が一致しません")
        return

    print("商品名: 確認済み")

    price_patterns = [
        r'id="corePriceDisplay_desktop_feature_div".*?'
        r'￥\s*([\d,]+)',
        r'class="a-price-whole"[^>]*>([\d,]+)',
    ]

    for pattern in price_patterns:
        match = re.search(pattern, html, re.S)
        if match:
            print("価格候補:", match.group(1), "円")
            break
    else:
        print("価格候補: 取得できません")

    for label in ["販売元", "出荷元", "Amazon.co.jp"]:
        print(label + ":", "表示あり" if label in text else "未検出")

    print("購入ボタン:",
          "表示あり" if "カートに入れる" in text else "未検出")

    print("送料: 個別の確認が必要")
    print("判定: 調査段階（在庫確定ではありません）")
    print("自動通知: なし")

if __name__ == "__main__":
    main()
