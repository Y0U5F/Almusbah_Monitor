"""
البرنامج الرئيسي لمراقبة المنتجات
"""
import logging
import sys
from datetime import datetime
from typing import Dict, List, Tuple

from config import (
    CATEGORY_URL, LOG_FILE, LOG_FORMAT, LOG_LEVEL,
    is_config_valid, validate_config
)
from database import DatabaseManager
from scraper import ZidScraper
from notifier import TelegramNotifier

# إعداد نظام السجلات
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class ProductMonitor:
    """المراقب الرئيسي للمنتجات"""

    def __init__(self):
        self.db = DatabaseManager()
        self.scraper = ZidScraper()
        self.notifier = TelegramNotifier()
        self.changes = {
            'new': [],
            'out_of_stock': [],
            'back_in_stock': [],
            'deleted': [],
            'price_changes': []
        }

    def _validate_setup(self) -> bool:
        """التحقق من صحة الإعداد"""
        logger.info("🔍 التحقق من الإعدادات...")

        config_checks = validate_config()
        all_valid = True

        for check, status in config_checks.items():
            icon = "✅" if status else "❌"
            logger.info(f"{icon} {check}: {'صحيح' if status else 'خطأ'}")
            if not status:
                all_valid = False

        if not all_valid:
            logger.error("❌ فشل التحقق من الإعدادات!")
            return False

        # اختبار الاتصالات
        logger.info("🔍 اختبار الاتصالات...")

        if not self.scraper.test_connection(CATEGORY_URL):
            logger.error("❌ فشل الاتصال بالموقع!")
            return False

        if not self.notifier.test_connection():
            logger.error("❌ فشل الاتصال بالتيليجرام!")
            return False

        logger.info("✅ جميع الفحوصات نجحت!")
        return True

    def _detect_new_products(self, current: Dict, old: Dict) -> List[Dict]:
        """اكتشاف المنتجات الجديدة"""
        new_products = []
        for p_id, product in current.items():
            if p_id not in old:
                new_products.append(product)
                logger.info(f"🆕 منتج جديد: {product['name'][:50]}...")
        return new_products

    def _detect_deleted_products(self, current: Dict, old: Dict) -> List[Dict]:
        """اكتشاف المنتجات المحذوفة"""
        deleted_products = []
        for p_id, product in old.items():
            if p_id not in current:
                deleted_products.append(product)
                logger.info(f"🗑️ منتج محذوف: {product['name'][:50]}...")
        return deleted_products

    def _detect_status_changes(self, current: Dict, old: Dict) -> Tuple[List[Dict], List[Dict]]:
        """اكتشاف تغييرات الحالة"""
        went_out = []
        came_back = []

        for p_id, new_product in current.items():
            if p_id in old:
                old_product = old[p_id]

                # من متوفر إلى نافد
                if (old_product['status'] == 'Available' and
                    new_product['status'] == 'Out of Stock'):
                    went_out.append(new_product)
                    logger.info(f"⚠️ نفاد كمية: {new_product['name'][:50]}...")

                # من نافد إلى متوفر
                elif (old_product['status'] == 'Out of Stock' and
                      new_product['status'] == 'Available'):
                    came_back.append(new_product)
                    logger.info(f"✅ عودة توفر: {new_product['name'][:50]}...")

        return went_out, came_back

    def _detect_price_changes(self, current: Dict, old: Dict) -> List[Dict]:
        """اكتشاف تغييرات الأسعار"""
        price_changes = []

        for p_id, new_product in current.items():
            if p_id in old:
                old_product = old[p_id]

                if old_product['price'] != new_product['price']:
                    price_changes.append({
                        'product': new_product,
                        'old_price': old_product['price'],
                        'new_price': new_product['price']
                    })
                    logger.info(
                        f"💰 تغيير سعر: {new_product['name'][:50]}... "
                        f"({old_product['price']} → {new_product['price']})"
                    )

        return price_changes

    def _send_notifications(self):
        """إرسال جميع الإشعارات"""
        notifications = []

        # بناء قائمة الإشعارات
        for product in self.changes['new']:
            notifications.append(('new', product))

        for product in self.changes['out_of_stock']:
            notifications.append(('out_of_stock', product))

        for product in self.changes['back_in_stock']:
            notifications.append(('back_in_stock', product))

        for product in self.changes['deleted']:
            notifications.append(('deleted', product))

        for change in self.changes['price_changes']:
            notifications.append(('price_change', change))

        # إرسال الإشعارات
        if notifications:
            logger.info(f"📤 إرسال {len(notifications)} إشعار...")
            results = self.notifier.send_batch_notifications(notifications)
            logger.info(
                f"✅ تم إرسال {results['sent']}/{results['total']} إشعار "
                f"(فشل: {results['failed']})"
            )
        else:
            logger.info("📭 لا توجد إشعارات للإرسال")

    def run_check(self):
        """تشغيل فحص كامل"""
        start_time = datetime.now()
        logger.info(f"""
╔══════════════════════════════════════════════════╗
║     🚀 بدء فحص المنتجات - {start_time.strftime('%Y-%m-%d %H:%M:%S')}     ║
╚══════════════════════════════════════════════════╝
        """)

        try:
            # 1. التحقق من الإعداد
            if not self._validate_setup():
                logger.error("❌ فشل التحقق من الإعداد. إنهاء البرنامج.")
                sys.exit(1)

            # 2. إنشاء نسخة احتياطية
            logger.info("💾 إنشاء نسخة احتياطية...")
            try:
                self.db.create_backup()
            except Exception as e:
                logger.warning(f"⚠️ تحذير: فشل النسخ الاحتياطي - {e}")

            # 3. تحميل البيانات القديمة
            logger.info("📂 تحميل البيانات المحفوظة...")
            old_products = self.db.get_all_products()
            logger.info(f"✅ تم تحميل {len(old_products)} منتج من قاعدة البيانات")

            # 4. سحب البيانات الجديدة
            logger.info("🕷️ بدء سحب البيانات من الموقع...")
            current_products_list = self.scraper.get_products(CATEGORY_URL)
            current_products = {p['id']: p for p in current_products_list}
            logger.info(f"✅ تم سحب {len(current_products)} منتج من الموقع")

            # 5. اكتشاف التغييرات
            logger.info("🔍 تحليل التغييرات...")

            self.changes['new'] = self._detect_new_products(current_products, old_products)
            self.changes['deleted'] = self._detect_deleted_products(current_products, old_products)

            went_out, came_back = self._detect_status_changes(current_products, old_products)
            self.changes['out_of_stock'] = went_out
            self.changes['back_in_stock'] = came_back

            self.changes['price_changes'] = self._detect_price_changes(current_products, old_products)

            # 6. تحديث قاعدة البيانات
            logger.info("💾 تحديث قاعدة البيانات...")

            for product in current_products.values():
                self.db.upsert_product(product)

            for product in self.changes['deleted']:
                self.db.delete_product(product['id'])

            # 7. إرسال الإشعارات
            self._send_notifications()

            # 8. حساب الإحصائيات
            stats = {
                'total': len(current_products),
                'available': sum(1 for p in current_products.values() if p['status'] == 'Available'),
                'out_of_stock': sum(1 for p in current_products.values() if p['status'] == 'Out of Stock'),
                'new': len(self.changes['new']),
                'deleted': len(self.changes['deleted']),
                'went_out': len(self.changes['out_of_stock']),
                'back_in': len(self.changes['back_in_stock']),
                'price_changes': len(self.changes['price_changes'])
            }

            # 9. حفظ الإحصائيات
            self.db.save_statistics(stats)

            # 10. إرسال تقرير الملخص
            logger.info("📊 إرسال تقرير الملخص...")
            self.notifier.send_summary_report(stats)

            # 11. التقرير النهائي
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            logger.info(f"""
╔══════════════════════════════════════════════════╗
║              📊 تقرير الفحص النهائي               ║
╠══════════════════════════════════════════════════╣
║ ⏱️  المدة: {duration:.2f} ثانية                          ║
║ 📦 إجمالي المنتجات: {stats['total']:<26} ║
║ ✅ المتوفرة: {stats['available']:<33} ║
║ ❌ غير المتوفرة: {stats['out_of_stock']:<29} ║
║                                                  ║
║ 🔄 التغييرات المكتشفة:                           ║
║ • منتجات جديدة: {stats['new']:<29} ║
║ • نفاد كمية: {stats['went_out']:<32} ║
║ • عودة توفر: {stats['back_in']:<32} ║
║ • منتجات محذوفة: {stats['deleted']:<27} ║
║ • تغييرات أسعار: {stats['price_changes']:<27} ║
╠══════════════════════════════════════════════════╣
║           ✅ اكتمل الفحص بنجاح                    ║
╚══════════════════════════════════════════════════╝
            """)

        except Exception as e:
            logger.error(f"❌ خطأ فادح أثناء الفحص: {e}", exc_info=True)
            sys.exit(1)


def main():
    """نقطة الدخول الرئيسية"""
    try:
        monitor = ProductMonitor()
        monitor.run_check()
    except KeyboardInterrupt:
        logger.info("\n⚠️ تم إيقاف البرنامج بواسطة المستخدم")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
