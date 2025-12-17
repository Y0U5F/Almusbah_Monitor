"""
سكرابر متقدم لمنصة زد مع معالجة أخطاء شاملة
"""
import requests
from bs4 import BeautifulSoup
import time
import random
import logging
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

from config import (
    BASE_URL, USER_AGENTS, REQUEST_TIMEOUT,
    RETRY_ATTEMPTS, RETRY_DELAY, PAGE_DELAY, MAX_PAGES
)

logger = logging.getLogger(__name__)


class ZidScraperException(Exception):
    """استثناء مخصص للسكرابر"""
    pass


class ZidScraper:
    """سكرابر محسّن لمنصة زد"""

    def __init__(self):
        self.session = requests.Session()
        self.products_found = 0
        self.pages_processed = 0
        self.errors_count = 0

    def _get_headers(self) -> Dict[str, str]:
        """الحصول على هيدرز عشوائية"""
        return {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ar,en-US;q=0.7,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    def _make_request(self, url: str, attempt: int = 1) -> Optional[requests.Response]:
        """طلب HTTP مع إعادة المحاولة"""
        try:
            logger.info(f"📡 طلب الصفحة: {url} (محاولة {attempt}/{RETRY_ATTEMPTS})")

            response = self.session.get(
                url,
                headers=self._get_headers(),
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True
            )

            response.raise_for_status()
            return response

        except requests.exceptions.Timeout:
            logger.warning(f"⏱️ انتهت مهلة الطلب للرابط: {url}")
        except requests.exceptions.ConnectionError:
            logger.warning(f"🔌 خطأ في الاتصال بالرابط: {url}")
        except requests.exceptions.HTTPError as e:
            logger.warning(f"❌ خطأ HTTP {e.response.status_code}: {url}")
        except Exception as e:
            logger.error(f"❌ خطأ غير متوقع: {e}")

        # إعادة المحاولة
        if attempt < RETRY_ATTEMPTS:
            wait_time = RETRY_DELAY * attempt
            logger.info(f"⏳ إعادة المحاولة بعد {wait_time} ثانية...")
            time.sleep(wait_time)
            return self._make_request(url, attempt + 1)

        self.errors_count += 1
        return None

    def _normalize_url(self, url: str) -> str:
        """تطبيع الرابط (إضافة النطاق إذا كان نسبياً)"""
        if url.startswith('http'):
            return url
        return urljoin(BASE_URL, url)

    def _extract_product_id(self, url: str) -> str:
        """استخراج معرف المنتج من الرابط"""
        # مثال: /products/8972 -> 8972
        # مثال: /products/slug-name -> slug-name
        path = urlparse(url).path
        parts = path.strip('/').split('/')
        return parts[-1] if parts else url

    def _clean_text(self, text: str) -> str:
        """تنظيف النص من المسافات الزائدة"""
        if not text:
            return ""
        return ' '.join(text.split()).strip()

    def _extract_price(self, price_text: str) -> str:
        """استخراج السعر وتنظيفه"""
        if not price_text:
            return "0.00"

        # إزالة رمز الريال والمسافات
        price = price_text.replace('ر.س', '').replace('SAR', '').strip()
        # استخراج الأرقام فقط
        price = ''.join(c for c in price if c.isdigit() or c == '.')

        try:
            return f"{float(price):.2f}"
        except ValueError:
            return "0.00"

    def _parse_product(self, item: BeautifulSoup) -> Optional[Dict]:
        """تحليل عنصر منتج واحد"""
        try:
            # 1. استخراج الرابط والعنوان
            link_tag = None

            # محاولة 1: البحث في div.title
            title_div = item.find('div', class_='title')
            if title_div:
                link_tag = title_div.find('a')

            # محاولة 2: البحث المباشر عن رابط المنتج
            if not link_tag:
                link_tag = item.find('a', href=lambda x: x and '/products/' in x)

            if not link_tag:
                logger.debug("⚠️ لم يتم العثور على رابط المنتج")
                return None

            # استخراج البيانات الأساسية
            name = self._clean_text(link_tag.get('title') or link_tag.text)
            url = self._normalize_url(link_tag.get('href', ''))
            product_id = self._extract_product_id(url)

            if not name or not product_id:
                logger.debug("⚠️ معلومات المنتج ناقصة")
                return None

            # 2. استخراج السعر
            price = "0.00"
            price_div = item.find('div', class_='text-dark-1 fs-18px')
            if price_div:
                price = self._extract_price(price_div.text)

            # 3. تحديد الحالة (متوفر / نافد)
            status = "Available"

            # البحث عن أزرار "غير متوفر" أو "Out of Stock"
            out_of_stock_indicators = [
                item.find('a', class_='btn-out-of-stock'),
                item.find('button', class_='btn-out-of-stock'),
                item.find(text=lambda x: x and 'غير متوفر' in x.lower()),
                item.find(text=lambda x: x and 'out of stock' in x.lower()),
                item.find('div', class_='img-grayscale'),  # الصورة الرمادية تدل على نفاد
            ]

            if any(out_of_stock_indicators):
                status = "Out of Stock"

            product = {
                'id': product_id,
                'name': name,
                'url': url,
                'price': price,
                'status': status
            }

            logger.debug(f"✅ تم تحليل: {name[:50]}... - {status}")
            return product

        except Exception as e:
            logger.error(f"❌ خطأ في تحليل المنتج: {e}")
            return None

    def get_products(self, category_url: str) -> List[Dict]:
        """سحب جميع المنتجات من القسم"""
        all_products = []
        self.products_found = 0
        self.pages_processed = 0
        self.errors_count = 0

        logger.info(f"🚀 بدء فحص القسم: {category_url}")

        for page in range(1, MAX_PAGES + 1):
            # بناء رابط الصفحة
            url = f"{category_url}?page={page}"

            # طلب الصفحة
            response = self._make_request(url)
            if not response:
                logger.error(f"❌ فشل تحميل الصفحة {page}")
                break

            # تحليل HTML
            soup = BeautifulSoup(response.text, 'html.parser')

            # البحث عن المنتجات
            # في منصة زد، المنتجات عادة داخل div.product
            product_items = soup.find_all('div', class_='product')

            if not product_items:
                logger.info(f"🏁 لا توجد منتجات في الصفحة {page} - الانتهاء")
                break

            logger.info(f"📦 وجدت {len(product_items)} منتج في الصفحة {page}")

            # تحليل كل منتج
            page_products = 0
            for item in product_items:
                product = self._parse_product(item)
                if product:
                    all_products.append(product)
                    page_products += 1

            self.products_found += page_products
            self.pages_processed += 1

            # إذا كانت المنتجات أقل من 10، غالباً هذه آخر صفحة
            if len(product_items) < 10:
                logger.info("🏁 تم الوصول لآخر صفحة")
                break

            # راحة بين الصفحات
            if page < MAX_PAGES:
                time.sleep(PAGE_DELAY)

        # تقرير نهائي
        logger.info(f"""
╔════════════════════════════════════════╗
║        تقرير السكرابر النهائي          ║
╠════════════════════════════════════════╣
║ 📄 الصفحات المعالجة: {self.pages_processed:>16} ║
║ 📦 المنتجات المكتشفة: {self.products_found:>15} ║
║ ❌ الأخطاء: {self.errors_count:>25} ║
╚════════════════════════════════════════╝
        """)

        return all_products

    def test_connection(self, url: str) -> bool:
        """اختبار الاتصال بالموقع"""
        try:
            response = self._make_request(url)
            if response and response.status_code == 200:
                logger.info("✅ الاتصال بالموقع ناجح")
                return True
            else:
                logger.error("❌ فشل الاتصال بالموقع")
                return False
        except Exception as e:
            logger.error(f"❌ خطأ في اختبار الاتصال: {e}")
            return False
