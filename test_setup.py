"""
سكربت اختبار شامل للتحقق من صحة الإعداد قبل التشغيل
"""
import sys
import os

def check_python_version():
    """التحقق من إصدار Python"""
    print("🐍 فحص إصدار Python...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 9:
        print(f"   ✅ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"   ❌ Python {version.major}.{version.minor} (يجب 3.9+)")
        return False

def check_dependencies():
    """التحقق من المكتبات المطلوبة"""
    print("\n📦 فحص المكتبات...")
    required = {
        'requests': 'requests',
        'bs4': 'beautifulsoup4',
        'sqlite3': 'مدمجة'
    }

    missing = []
    for module, package in required.items():
        try:
            __import__(module)
            print(f"   ✅ {package}")
        except ImportError:
            print(f"   ❌ {package} - غير مثبتة")
            missing.append(package)

    if missing:
        print(f"\n⚠️ لتثبيت المكتبات الناقصة:")
        print(f"   pip install {' '.join(m for m in missing if m != 'مدمجة')}")
        return False

    return True

def check_config():
    """التحقق من ملف الإعدادات"""
    print("\n⚙️ فحص ملف الإعدادات...")

    try:
        from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, CATEGORY_URL

        checks = {
            "TELEGRAM_TOKEN": bool(TELEGRAM_TOKEN),
            "TELEGRAM_CHAT_ID": bool(TELEGRAM_CHAT_ID),
            "CATEGORY_URL": bool(CATEGORY_URL)
        }

        all_ok = True
        for name, status in checks.items():
            if status:
                print(f"   ✅ {name}")
            else:
                print(f"   ❌ {name} - غير محدد")
                all_ok = False

        if not all_ok:
            print("\n⚠️ تأكد من تعيين متغيرات البيئة:")
            print("   export TELEGRAM_TOKEN='your_token'")
            print("   export TELEGRAM_CHAT_ID='your_chat_id'")

        return all_ok

    except ImportError as e:
        print(f"   ❌ خطأ في استيراد config.py: {e}")
        return False

def check_files():
    """التحقق من وجود الملفات المطلوبة"""
    print("\n📁 فحص الملفات...")

    required_files = [
        'config.py',
        'database.py',
        'scraper.py',
        'notifier.py',
        'main.py',
        'requirements.txt'
    ]

    all_exist = True
    for file in required_files:
        if os.path.exists(file):
            print(f"   ✅ {file}")
        else:
            print(f"   ❌ {file} - غير موجود")
            all_exist = False

    return all_exist

def test_database():
    """اختبار قاعدة البيانات"""
    print("\n💾 اختبار قاعدة البيانات...")

    try:
        from database import DatabaseManager

        db = DatabaseManager()
        print("   ✅ تم إنشاء قاعدة البيانات")

        # اختبار بسيط
        test_product = {
            'id': 'test-123',
            'name': 'منتج تجريبي',
            'url': 'https://example.com',
            'price': '100.00',
            'status': 'Available'
        }

        db.upsert_product(test_product)
        retrieved = db.get_product('test-123')

        if retrieved:
            print("   ✅ اختبار القراءة/الكتابة")
            db.delete_product('test-123')
            print("   ✅ اختبار الحذف")
            return True
        else:
            print("   ❌ فشل اختبار القراءة/الكتابة")
            return False

    except Exception as e:
        print(f"   ❌ خطأ: {e}")
        return False

def test_scraper():
    """اختبار السكرابر"""
    print("\n🕷️ اختبار السكرابر...")

    try:
        from scraper import ZidScraper
        from config import CATEGORY_URL

        scraper = ZidScraper()

        if scraper.test_connection(CATEGORY_URL):
            print("   ✅ الاتصال بالموقع ناجح")
            return True
        else:
            print("   ❌ فشل الاتصال بالموقع")
            return False

    except Exception as e:
        print(f"   ❌ خطأ: {e}")
        return False

def test_notifier():
    """اختبار نظام الإشعارات"""
    print("\n📱 اختبار التيليجرام...")

    try:
        from notifier import TelegramNotifier

        notifier = TelegramNotifier()

        if notifier.test_connection():
            print("   ✅ الاتصال بالتيليجرام ناجح")

            # إرسال رسالة اختبار
            response = input("\n   هل تريد إرسال رسالة اختبار؟ (y/n): ")
            if response.lower() == 'y':
                test_msg = "✅ اختبار نظام الإشعارات - المشروع جاهز للعمل!"
                if notifier._send_message(test_msg):
                    print("   ✅ تم إرسال رسالة الاختبار")
                else:
                    print("   ❌ فشل إرسال رسالة الاختبار")

            return True
        else:
            print("   ❌ فشل الاتصال بالتيليجرام")
            return False

    except Exception as e:
        print(f"   ❌ خطأ: {e}")
        return False

def main():
    """تشغيل جميع الاختبارات"""
    print("""
╔══════════════════════════════════════════════════╗
║        🧪 اختبار إعداد المشروع                   ║
╚══════════════════════════════════════════════════╝
    """)

    tests = [
        ("إصدار Python", check_python_version),
        ("المكتبات المطلوبة", check_dependencies),
        ("ملف الإعدادات", check_config),
        ("الملفات المطلوبة", check_files),
        ("قاعدة البيانات", test_database),
        ("السكرابر", test_scraper),
        ("التيليجرام", test_notifier),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ خطأ غير متوقع في {name}: {e}")
            results.append((name, False))

    # التقرير النهائي
    print("""
╔══════════════════════════════════════════════════╗
║              📊 نتائج الاختبارات                 ║
╚══════════════════════════════════════════════════╝
    """)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")

    print(f"""
{'='*50}
النتيجة: {passed}/{total} اختبار نجح
{'='*50}
    """)

    if passed == total:
        print("""
🎉 تهانينا! المشروع جاهز تماماً للتشغيل!

للتشغيل المحلي:
    python main.py

للنشر على GitHub:
    1. ارفع المشروع: git push
    2. أضف Secrets في GitHub Settings
    3. فعّل Actions
        """)
        return 0
    else:
        print("""
⚠️ يوجد مشاكل يجب حلها قبل التشغيل.
راجع الأخطاء أعلاه وقم بإصلاحها.
        """)
        return 1

if __name__ == "__main__":
    sys.exit(main())
