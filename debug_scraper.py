"""
سكربت اختبار السكرابر فقط (بدون داتابيز أو تيليجرام)
"""
from scraper import ZidScraper
from config import CATEGORY_URL
import json

def test_extraction():
    print("🕷️ جاري تشغيل السكرابر في وضع الاختبار...")
    print(f"🔗 الرابط: {CATEGORY_URL}")

    scraper = ZidScraper()

    # سنجلب صفحة واحدة فقط للتجربة
    # تم تعديل الدالة في scraper.py لتقبل max_pages كباراميتر (اختياري)
    # أو ستقوم بقطع اللوب يدوياً هنا

    products = scraper.get_products(CATEGORY_URL)

    print(f"\n📦 تم العثور على {len(products)} منتج.")
    print("-" * 50)

    # طباعة أول 5 منتجات فقط للتأكد
    for i, p in enumerate(products[:5], 1):
        print(f"#{i}")
        print(f"📌 الاسم: {p['name']}")
        print(f"💰 السعر: {p['price']}")  # ركز هنا
        print(f"🔗 الرابط: {p['url']}")
        print(f"🚦 الحالة: {p['status']}")
        print("-" * 20)

if __name__ == "__main__":
    test_extraction()
