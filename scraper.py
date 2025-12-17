"""
سكرابر متقدم لمنصة زد مع استخراج ذكي للأسعار
"""
import requests
from bs4 import BeautifulSoup
import time
import re
import logging
from typing import List, Dict, Optional
from urllib.parse import urljoin

from config import (
    BASE_URL, USER_AGENTS, REQUEST_TIMEOUT,
    RETRY_ATTEMPTS, RETRY_DELAY, PAGE_DELAY, MAX_PAGES
)

logger = logging.getLogger(__name__)


class ZidScraperException(Exception):
    """استثناء مخصص للسكرابر"""
    pass


class ZidScraper:
    """سكرابر محسّن لمنصة زد مع معالجة أخطاء متقدمة"""

    def __init__(self):
        self.session = requests.Session()
        self.products_found = 0
        self.pages_processed = 0
        self.errors_count = 0

    def _get_headers(self) -> Dict[str, str]:
        """الحصول على Headers محسّنة"""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8',
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
        """
        استخراج معرف المنتج من الرابط مع تنظيف الـ query parameters
        مثال: /products/8972?variant=123 -> 8972
        """
        path = url.split('/')[-1]
        # إزالة أي query parameters
        product_id = path.split('?')[0]
        return product_id

    def _extract_price(self, item: BeautifulSoup) -> str:
        """
        استخراج السعر بذكاء مع معالجة الفواصل والأرقام الكبيرة
        🔥 محسّن لدعم الأسعار مثل: 1,200.00 و 460.00
        """
        price_text = ""

        # البحث عن عنصر السعر بطرق متعددة
        price_selectors = [
            '.price .text-dark-1.fs-18px',
            '.text-dark-1.fs-18px',
            '.price',
            '[class*="price"]'
        ]

        for selector in price_selectors:
            price_elm = item.select_one(selector)
            if price_elm:
                price_text = price_elm.text.strip()
                break

        if not price_text:
            return "0.00"

        # 🔥 تنظيف السعر: إزالة الفواصل والرموز
        # مثال: "1,200.50 ر.س" -> "1200.50"
        price_text = price_text.replace(',', '')  # إزالة الفواصل
        price_text = price_text.replace('ر.س', '').replace('SAR', '').strip()

        # استخراج الرقم العشري باستخدام Regex
        match = re.search(r'(\d+\.?\d*)', price_text)

        if match:
            try:
                price_float = float(match.group(1))
                return f"{price_float:.2f}"
            except ValueError:
                logger.warning(f"⚠️ فشل تحويل السعر: {price_text}")
                return "0.00"

        return "0.00"

    def _parse_product(self, item: BeautifulSoup) -> Optional[Dict]:
        """
        تحليل عنصر منتج واحد
        🔥 اللوجيك الأساسي بدون تعديل - فقط تحسينات في الكود
        """
        try:
            # 1. استخراج الرابط والعنوان
            title_tag = item.select_one('.title a')
            if not title_tag:
                title_tag = item.select_one('a.product-card')

            if not title_tag:
                logger.debug("⚠️ لم يتم العثور على رابط المنتج")
                return None

            # استخراج الاسم (من النص أو من attribute الـ title)
            name = title_tag.text.strip()
            if not name:
                name = title_tag.get('title', '').strip()

            # استخراج الرابط
            url = self._normalize_url(title_tag.get('href', ''))

            # استخراج الـ ID
            product_id = self._extract_product_id(url)

            if not name or not product_id:
                logger.debug("⚠️ معلومات المنتج ناقصة")
                return None

            # 2. استخراج السعر (بالدالة المُحسّنة)
            price = self._extract_price(item)

            # 3. تحديد الحالة (متوفر / نافد)
            status = "Available"

            # البحث عن مؤشرات نفاد الكمية
            img_container = item.select_one('.img.position-relative')

            # المؤشر الأول: الصورة الرمادية (img-grayscale)
            has_grayscale = (
                img_container and
                'img-grayscale' in img_container.get('class', [])
            )

            # المؤشر الثاني: زر "غير متوفر"
            has_out_button = item.select_one('.btn-out-of-stock') is not None

            # المؤشر الثالث: نص "غير متوفر" في المحتوى
            has_out_text = "غير متوفر" in item.text.lower()

            if has_grayscale or has_out_button or has_out_text:
                status = "Out of Stock"

            # بناء كائن المنتج
            product = {
                'id': product_id,
                'name': name,
                'url': url,
                'price': price,
                'status': status
            }

            logger.debug(f"✅ تم تحليل: {name[:50]}... - {status} - {price}")
            return product

        except Exception as e:
            logger.error(f"❌ خطأ في تحليل المنتج: {e}")
            return None

    def get_products(self, category_url: str) -> List[Dict]:
        """
        سحب جميع المنتجات من القسم
        🔥 اللوجيك الأساسي محفوظ بالكامل
        """
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
            product_items = soup.select('div.product')
            if not product_items:
                product_items = soup.select('.product-card')

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

            # إذا كانت المنتجات أقل من 5، غالباً هذه آخر صفحة
            if len(product_items) < 5:
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
