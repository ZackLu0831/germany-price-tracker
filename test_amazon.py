import unittest
from tracker import extract_amazon_buybox

class AmazonBuyBoxTests(unittest.TestCase):
    def test_amazon_sold(self):
        html='<div id="desktop_buybox"><span id="merchantInfo">Verkauf durch Amazon.de</span><span class="a-price"><span class="a-offscreen">249,00 €</span></span></div>'
        self.assertEqual(extract_amazon_buybox(html)[0], 249.0)
    def test_third_party_fba_rejected(self):
        html='<div id="desktop_buybox"><span id="merchantInfo">Versand durch Amazon, Verkauf durch Example GmbH</span><span class="a-price"><span class="a-offscreen">199,00 €</span></span></div>'
        with self.assertRaises(ValueError): extract_amazon_buybox(html)
    def test_missing_seller_rejected(self):
        with self.assertRaises(ValueError): extract_amazon_buybox('<div id="desktop_buybox"><span class="a-price"><span class="a-offscreen">99 €</span></span></div>')

if __name__ == '__main__': unittest.main()
