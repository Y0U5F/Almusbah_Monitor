"""
نظام الإشعارات عبر التيليجرام مع دعم الرسائل المتعددة
"""
import requests
import time
import logging
from datetime import datetime
from typing import Dict, List
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, MessageTemplates

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """مدير إرسال الإشعارات عبر التيليجرام"""

    def __init__(self):
        self.token = TELEGRAM_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.messages_sent = 0
        self.failed_messages = 0
        self.templates = MessageTemplates()

    def _get_timestamp(self) -> str:
        """الحصول على الوقت الحالي بتنسيق جميل"""
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S")

    def _send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """إرسال رسالة واحدة"""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }

            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()

            self.messages_sent += 1
            logger.debug(f"✅ تم إرسال رسالة بنجاح (الإجمالي: {self.messages_sent})")
            return True

        except requests.exceptions.RequestException as e:
            self.failed_messages += 1
            logger.error(f"❌ فشل إرسال الرسالة: {e}")
            return False

    def _send_with_retry(self, text: str, max_retries: int = 3) -> bool:
        """إرسال مع إعادة المحاولة"""
        for attempt in range(1, max_retries + 1):
            if self._send_message(text):
                return True

            if attempt < max_retries:
                wait_time = 2 * attempt
                logger.info(f"⏳ إعادة المحاولة بعد {wait_time} ثانية...")
                time.sleep(wait_time)

        return False

    def notify_new_product(self, product: Dict) -> bool:
        """إشعار بمنتج جديد"""
        message = self.templates.NEW_PRODUCT.format(
            name=product['name'],
            price=product['price'],
            url=product['url'],
            timestamp=self._get_timestamp()
        )
        return self._send_with_retry(message)

    def notify_out_of_stock(self, product: Dict) -> bool:
        """إشعار بنفاد كمية"""
        message = self.templates.OUT_OF_STOCK.format(
            name=product['name'],
            price=product['price'],
            url=product['url'],
            timestamp=self._get_timestamp()
        )
        return self._send_with_retry(message)

    def notify_back_in_stock(self, product: Dict) -> bool:
        """إشعار بعودة توفر المنتج"""
        message = self.templates.BACK_IN_STOCK.format(
            name=product['name'],
            price=product['price'],
            url=product['url'],
            timestamp=self._get_timestamp()
        )
        return self._send_with_retry(message)

    def notify_deleted(self, product: Dict) -> bool:
        """إشعار بحذف منتج"""
        message = self.templates.DELETED.format(
            name=product['name'],
            price=product['price'],
            url=product['url'],
            timestamp=self._get_timestamp()
        )
        return self._send_with_retry(message)

    def notify_price_change(self, product: Dict, old_price: str, new_price: str) -> bool:
        """إشعار بتغيير السعر"""
        try:
            old_p = float(old_price)
            new_p = float(new_price)
            diff = new_p - old_p

            if diff > 0:
                price_emoji = "📈"
                price_diff = f"+{diff:.2f} ريال (زيادة)"
            else:
                price_emoji = "📉"
                price_diff = f"{diff:.2f} ريال (انخفاض)"
        except:
            price_emoji = "💰"
            price_diff = "تغيير في السعر"

        message = self.templates.PRICE_CHANGE.format(
            name=product['name'],
            old_price=old_price,
            new_price=new_price,
            price_emoji=price_emoji,
            price_diff=price_diff,
            url=product['url'],
            timestamp=self._get_timestamp()
        )
        return self._send_with_retry(message)

    def send_summary_report(self, stats: Dict) -> bool:
        """إرسال تقرير ملخص"""
        # تحديد رسالة الحالة
        total_changes = (
            stats.get('new', 0) +
            stats.get('went_out', 0) +
            stats.get('back_in', 0) +
            stats.get('deleted', 0) +
            stats.get('price_changes', 0)
        )

        if total_changes == 0:
            status_message = "✅ لا توجد تغييرات جديدة"
        else:
            status_message = f"🔔 تم اكتشاف {total_changes} تغيير"

        message = self.templates.SUMMARY_REPORT.format(
            timestamp=self._get_timestamp(),
            total=stats.get('total', 0),
            available=stats.get('available', 0),
            out_of_stock=stats.get('out_of_stock', 0),
            new=stats.get('new', 0),
            went_out=stats.get('went_out', 0),
            back_in=stats.get('back_in', 0),
            deleted=stats.get('deleted', 0),
            price_changes=stats.get('price_changes', 0),
            status_message=status_message
        )
        return self._send_with_retry(message)

    def send_batch_notifications(self, notifications: List[tuple]) -> Dict[str, int]:
        """إرسال مجموعة من الإشعارات"""
        results = {
            'sent': 0,
            'failed': 0,
            'total': len(notifications)
        }

        for notification_type, product_data in notifications:
            success = False

            if notification_type == 'new':
                success = self.notify_new_product(product_data)
            elif notification_type == 'out_of_stock':
                success = self.notify_out_of_stock(product_data)
            elif notification_type == 'back_in_stock':
                success = self.notify_back_in_stock(product_data)
            elif notification_type == 'deleted':
                success = self.notify_deleted(product_data)
            elif notification_type == 'price_change':
                success = self.notify_price_change(
                    product_data['product'],
                    product_data['old_price'],
                    product_data['new_price']
                )

            if success:
                results['sent'] += 1
            else:
                results['failed'] += 1

            # راحة قصيرة بين الرسائل لتجنب الحظر
            time.sleep(0.5)

        return results

    def test_connection(self) -> bool:
        """اختبار الاتصال بالتيليجرام"""
        try:
            url = f"{self.base_url}/getMe"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            if data.get('ok'):
                bot_name = data.get('result', {}).get('first_name', 'Bot')
                logger.info(f"✅ الاتصال بالتيليجرام ناجح - البوت: {bot_name}")
                return True
            else:
                logger.error("❌ فشل التحقق من التيليجرام")
                return False

        except Exception as e:
            logger.error(f"❌ خطأ في الاتصال بالتيليجرام: {e}")
            return False

    def get_statistics(self) -> Dict[str, int]:
        """الحصول على إحصائيات الإرسال"""
        return {
            'messages_sent': self.messages_sent,
            'failed_messages': self.failed_messages,
            'success_rate': (
                (self.messages_sent / (self.messages_sent + self.failed_messages) * 100)
                if (self.messages_sent + self.failed_messages) > 0
                else 0
            )
        }
