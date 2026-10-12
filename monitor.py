"""Amazon displayed-offer monitor, using only the Python standard library."""
import argparse
import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path

PRODUCT = "HG 1/144 ガンダムヴァサーゴ"
MAX_PRICE = 3190
URL = "https://www.amazon.co.jp/dp/B0H32PBNFR"


class Node:
    def __init__(self, tag="", attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    def walk(self):
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.walk()

    def text(self):
        if self.tag in {"script", "style"}:
            return ""
        return " ".join(c.text() if isinstance(c, Node) else c for c in self.children)

    def by_id(self, value):
        return next((n for n in self.walk() if n.attrs.get("id") == value), None)

    def visible(self):
        n = self
        while n:
            style = re.sub(r"\s", "", n.attrs.get("style", "")).lower()
            if ("hidden" in n.attrs or n.attrs.get("aria-hidden") == "true"
                    or "aok-hidden" in n.attrs.get("class", "").split()
                    or "display:none" in style or "visibility:hidden" in style):
                return False
            n = n.parent
        return True


class Document(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node()
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.current)
        self.current.children.append(n)
        if tag not in self.VOID:
            self.current = n

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        n = self.current
        while n.parent:
            if n.tag == tag:
                self.current = n.parent
                break
            n = n.parent

    def handle_data(self, data):
        self.current.children.append(data)


def clean(node):
    return re.sub(r"\s+", " ", node.text()).strip() if node else ""


def yen(text):
    m = re.fullmatch(r"[￥¥]?\s*([0-9][0-9,]*)\s*円?", text.strip())
    return int(m[1].replace(",", "")) if m else None


def parse_amazon(html):
    root = Document(html).root
    result = dict(status="判定不能", detail="", price=None, shipping=None,
                  total=None, seller=None, eligible=False, availability="")
    def stop(status, detail):
        result.update(status=status, detail=detail)
        return result
    if root.by_id("captchacharacters") or "ご迷惑をおかけしています" in clean(root):
        return stop("判定不能", "Amazonのアクセス確認画面です")
    if "ガンダムヴァサーゴ" not in clean(root.by_id("productTitle") or root.by_id("title")):
        return stop("判定不能", "対象の商品タイトルを確認できません")
    box = root.by_id("buybox") or root.by_id("desktop_buybox")
    if box is None:
        return stop("判定不能", "購入欄を確認できません")
    availability = clean(box.by_id("availability"))
    result["availability"] = availability
    if any(s in availability for s in ("現在在庫切れ", "一時的に在庫切れ", "現在お取り扱いできません")):
        return stop("在庫なし", availability)
    buttons = [n for n in box.walk() if n.tag in {"input", "button"}
               and (n.attrs.get("id") in {"add-to-cart-button", "buy-now-button"}
                    or n.attrs.get("name") in {"submit.add-to-cart", "submit.preorder"})
               and "disabled" not in n.attrs and n.attrs.get("aria-disabled") != "true" and n.visible()]
    if not buttons:
        return stop("判定不能", "有効な購入・予約ボタンを確認できません")
    price_node = box.by_id("corePrice_feature_div") or box.by_id("corePriceDisplay_desktop_feature_div")
    prices = {yen(clean(n)) for n in price_node.walk()
              if "a-offscreen" in n.attrs.get("class", "").split()} if price_node else set()
    prices.discard(None)
    if len(prices) != 1:
        return stop("判定不能", "購入欄の価格を一意に確認できません")
    result["price"] = prices.pop()
    sellers = [clean(n) for n in box.walk() if
               n.attrs.get("data-csa-c-slot-id") == "odf-feature-text-desktop-merchant-info"]
    seller = clean(box.by_id("sellerProfileTriggerId")) or (sellers[0] if sellers else "")
    if not seller:
        m = re.search(r"この商品は、(.+?)が販売", clean(box.by_id("merchant-info")))
        seller = m[1].strip() if m else ""
    result["seller"] = seller or None
    if not seller:
        return stop("判定不能", "販売元を確認できません")
    delivery = box.by_id("deliveryBlockMessage") or box.by_id("deliveryBlock_feature_div")
    shipping = set()
    if delivery:
        for n in delivery.walk():
            if "data-csa-c-delivery-price" not in n.attrs:
                continue
            if n.attrs.get("data-csa-c-delivery-type") not in {None, "配送"}:
                continue
            if n.attrs.get("data-csa-c-delivery-condition"):
                continue
            value = n.attrs["data-csa-c-delivery-price"]
            amount = 0 if value == "無料" else yen(value)
            if amount is not None:
                shipping.add(amount)
    if len(shipping) != 1:
        return stop("判定不能", "無条件の配送料を一意に確認できません")
    result["shipping"] = shipping.pop()
    result["total"] = result["price"] + result["shipping"]
    if result["total"] > MAX_PRICE:
        return stop("価格超過", f"送料込み{result['total']:,}円（上限{MAX_PRICE:,}円）")
    result["eligible"] = True
    return stop("条件に合う入荷", "購入・予約可能、販売元確認済み、送料込み上限以内")


def check_amazon(url=URL):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ja-JP,ja;q=0.9"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            html = raw.decode(charset, "replace")
            result = parse_amazon(html)
            root = Document(html).root
            result["diagnostic"] = {
                "http_status": response.status,
                "bytes": len(raw),
                "charset": charset,
                "page_title": clean(next((n for n in root.walk() if n.tag == "title"), None))[:160],
                "product_title_found": root.by_id("productTitle") is not None,
                "buybox_found": root.by_id("buybox") is not None,
                "page_message": clean(root)[:400],
            }
            print("ページ診断:", json.dumps(result["diagnostic"], ensure_ascii=False))
            return result
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return dict(status="確認失敗", detail=f"接続エラー: {type(error).__name__}", eligible=False)


def notification_due(result, previous):
    if result["status"] in {"判定不能", "確認失敗"}:
        return False, previous
    eligible = result["eligible"]
    return eligible and not previous.get("eligible", False), {"eligible": eligible}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, help="オフライン検証用HTML")
    parser.add_argument("--state", type=Path, default=Path(".monitor-state/state.json"))
    args = parser.parse_args()
    result = parse_amazon(args.html.read_text(encoding="utf-8")) if args.html else check_amazon()
    result.update(product=PRODUCT, url=URL, checked_at=datetime.now(timezone(timedelta(hours=9))).isoformat())
    try:
        previous = json.loads(args.state.read_text(encoding="utf-8"))
        if not isinstance(previous, dict):
            previous = {}
    except (OSError, ValueError):
        previous = {}
    due, state = notification_due(result, previous)
    if not args.html:
        args.state.parent.mkdir(parents=True, exist_ok=True)
        args.state.write_text(json.dumps(state), encoding="utf-8")
    result["notification_due"] = due and not bool(args.html)
    Path("status.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    def safe(value):
        return str(value).replace("|", "／").replace("\n", " ").replace("<", "&lt;")
    lines = [f"## {PRODUCT}", "", "項目 | 結果", "--- | ---"]
    for label, key in [("判定", "status"), ("詳細", "detail"), ("商品価格（円）", "price"),
                       ("送料（円）", "shipping"), ("合計（円）", "total"), ("販売元", "seller"),
                       ("購入・予約状況", "availability"), ("確認日時（日本時間）", "checked_at")]:
        lines.append(f"{label} | {safe(result.get(key) if result.get(key) is not None else '未確認')}")
    lines += ["", f"[Amazonで確認]({URL})", "", "条件：販売元を問わず、送料込み3,190円以下。予約も対象。",
              "対象は商品ページの主購入欄のオファーです。他の出品一覧は監視対象外です。",
              "通知：新たに条件に合った場合、Actionsを意図的に失敗させて既存のメール通知を使用します。"]
    summary = "\n".join(lines) + "\n"
    Path("status.md").write_text(summary, encoding="utf-8")
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as file:
            file.write(summary)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as file:
            file.write(f"notify={'true' if result['notification_due'] else 'false'}\n")


if __name__ == "__main__":
    main()
