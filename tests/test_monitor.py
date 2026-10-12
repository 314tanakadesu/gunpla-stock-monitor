import unittest
from monitor import parse_amazon, notification_due


def page(price=3000, shipping="無料", extra="", button='<input id="add-to-cart-button">', seller="お店"):
    return f'''<span id="productTitle">HG ガンダムヴァサーゴ</span>
    <div id="buybox"><div id="availability">在庫あり</div>
    <div id="corePrice_feature_div"><span class="a-offscreen">￥{price:,}</span></div>
    <div data-csa-c-slot-id="odf-feature-text-desktop-merchant-info">{seller}</div>
    <div id="deliveryBlockMessage"><span data-csa-c-delivery-price="{shipping}" {extra}></span></div>
    {button}</div>'''


class MonitorTests(unittest.TestCase):
    def test_boundary_including_shipping(self):
        self.assertTrue(parse_amazon(page(3000, "190円"))["eligible"])
        self.assertEqual(parse_amazon(page(3000, "191円"))["status"], "価格超過")

    def test_third_party_allowed(self):
        self.assertEqual(parse_amazon(page())["seller"], "お店")
        self.assertTrue(parse_amazon(page())["eligible"])

    def test_unknown_shipping_and_conditional_shipping(self):
        for html in [page(shipping="レジで計算"), page(extra='data-csa-c-delivery-condition="Prime"')]:
            self.assertFalse(parse_amazon(html)["eligible"])

    def test_disabled_hidden_and_text_are_not_buttons(self):
        for button in ['カートに入れる', '<input id="add-to-cart-button" disabled>',
                       '<div class="aok-hidden"><input id="add-to-cart-button"></div>']:
            self.assertFalse(parse_amazon(page(button=button))["eligible"])

    def test_unrelated_price_and_button_ignored(self):
        html = page(5000, button="") + '<span class="a-offscreen">￥2,000</span><input id="add-to-cart-button">'
        self.assertFalse(parse_amazon(html)["eligible"])

    def test_wrong_title_captcha_missing_seller(self):
        for html in [page().replace("ガンダムヴァサーゴ", "別商品"),
                     page() + '<input id="captchacharacters">', page(seller="")]:
            self.assertFalse(parse_amazon(html)["eligible"])

    def test_preorder(self):
        self.assertTrue(parse_amazon(page(button='<input name="submit.preorder">'))["eligible"])

    def test_continue_shopping_challenge(self):
        result = parse_amazon('<title>Amazon.co.jp</title><p>下のボタンをクリックしてショッピングを続けてください</p>')
        self.assertFalse(result['eligible'])
        self.assertIn('アクセス確認画面', result['detail'])

    def test_stockout(self):
        self.assertEqual(parse_amazon(page().replace("在庫あり", "現在在庫切れ"))["status"], "在庫なし")

    def test_notification_transition_and_unknown(self):
        yes = parse_amazon(page())
        due, state = notification_due(yes, {})
        self.assertTrue(due)
        self.assertFalse(notification_due(yes, state)[0])
        self.assertEqual(notification_due(dict(status="判定不能"), state), (False, state))
        _, state = notification_due(parse_amazon(page(4000)), state)
        self.assertTrue(notification_due(yes, state)[0])


if __name__ == "__main__":
    unittest.main()
