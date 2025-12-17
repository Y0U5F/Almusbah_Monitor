"""
إدارة قاعدة البيانات مع دعم النسخ الاحتياطي والإحصائيات
"""
import sqlite3
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from contextlib import contextmanager
import logging

from config import DB_FILE, DB_BACKUP_DIR

logger = logging.getLogger(__name__)


class DatabaseManager:
    """مدير قاعدة البيانات مع دعم المعاملات والنسخ الاحتياطي"""

    def __init__(self, db_file: str = DB_FILE):
        self.db_file = db_file
        self._ensure_backup_dir()
        self.init_db()

    def _ensure_backup_dir(self):
        """إنشاء مجلد النسخ الاحتياطية إذا لم يكن موجوداً"""
        Path(DB_BACKUP_DIR).mkdir(exist_ok=True)

    @contextmanager
    def get_connection(self):
        """Context manager للاتصال بقاعدة البيانات"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row  # للحصول على النتائج كقاموس
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"خطأ في قاعدة البيانات: {e}")
            raise
        finally:
            conn.close()

    def init_db(self):
        """إنشاء جداول قاعدة البيانات"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # جدول المنتجات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    price TEXT NOT NULL,
                    status TEXT NOT NULL,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    times_checked INTEGER DEFAULT 1
                )
            ''')

            # جدول التغييرات (للأرشفة)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS change_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id TEXT NOT NULL,
                    change_type TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (product_id) REFERENCES products(id)
                )
            ''')

            # جدول الإحصائيات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_products INTEGER,
                    available_products INTEGER,
                    out_of_stock_products INTEGER,
                    new_products INTEGER,
                    deleted_products INTEGER,
                    status_changes INTEGER,
                    price_changes INTEGER
                )
            ''')

            logger.info("✅ تم تجهيز قاعدة البيانات بنجاح")

    def create_backup(self) -> str:
        """إنشاء نسخة احتياطية من قاعدة البيانات"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{DB_BACKUP_DIR}/products_backup_{timestamp}.db"

        try:
            shutil.copy2(self.db_file, backup_file)
            logger.info(f"✅ تم إنشاء نسخة احتياطية: {backup_file}")
            return backup_file
        except Exception as e:
            logger.error(f"❌ فشل إنشاء النسخة الاحتياطية: {e}")
            raise

    def get_all_products(self) -> Dict[str, Dict]:
        """الحصول على جميع المنتجات كقاموس"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM products")
            rows = cursor.fetchall()

            return {
                row['id']: {
                    'id': row['id'],
                    'name': row['name'],
                    'url': row['url'],
                    'price': row['price'],
                    'status': row['status'],
                    'first_seen': row['first_seen'],
                    'last_updated': row['last_updated'],
                    'times_checked': row['times_checked']
                }
                for row in rows
            }

    def get_product(self, product_id: str) -> Optional[Dict]:
        """الحصول على منتج واحد"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None

    def upsert_product(self, product: Dict):
        """إضافة أو تحديث منتج"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # التحقق من وجود المنتج
            existing = self.get_product(product['id'])

            if existing:
                # تحديث المنتج الموجود
                cursor.execute('''
                    UPDATE products
                    SET name = ?, url = ?, price = ?, status = ?,
                        last_updated = CURRENT_TIMESTAMP,
                        times_checked = times_checked + 1
                    WHERE id = ?
                ''', (
                    product['name'], product['url'],
                    product['price'], product['status'],
                    product['id']
                ))

                # تسجيل التغييرات
                self._log_changes(cursor, product, existing)
            else:
                # إضافة منتج جديد
                cursor.execute('''
                    INSERT INTO products (id, name, url, price, status)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    product['id'], product['name'],
                    product['url'], product['price'],
                    product['status']
                ))

    def _log_changes(self, cursor, new_product: Dict, old_product: Dict):
        """تسجيل التغييرات في جدول التاريخ"""
        product_id = new_product['id']

        # تغيير في الحالة
        if new_product['status'] != old_product['status']:
            cursor.execute('''
                INSERT INTO change_history (product_id, change_type, old_value, new_value)
                VALUES (?, ?, ?, ?)
            ''', (product_id, 'status_change', old_product['status'], new_product['status']))

        # تغيير في السعر
        if new_product['price'] != old_product['price']:
            cursor.execute('''
                INSERT INTO change_history (product_id, change_type, old_value, new_value)
                VALUES (?, ?, ?, ?)
            ''', (product_id, 'price_change', old_product['price'], new_product['price']))

    def delete_product(self, product_id: str):
        """حذف منتج من قاعدة البيانات"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # تسجيل الحذف في التاريخ
            cursor.execute('''
                INSERT INTO change_history (product_id, change_type, old_value)
                VALUES (?, ?, ?)
            ''', (product_id, 'deleted', 'exists'))

            # حذف المنتج
            cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
            logger.info(f"🗑️ تم حذف المنتج {product_id}")

    def get_statistics(self) -> Dict:
        """الحصول على الإحصائيات الحالية"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # إحصائيات عامة
            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'Available' THEN 1 ELSE 0 END) as available,
                    SUM(CASE WHEN status = 'Out of Stock' THEN 1 ELSE 0 END) as out_of_stock
                FROM products
            ''')
            stats = dict(cursor.fetchone())

            # إحصائيات التغييرات (آخر 24 ساعة)
            cursor.execute('''
                SELECT
                    COUNT(CASE WHEN change_type = 'status_change' THEN 1 END) as status_changes,
                    COUNT(CASE WHEN change_type = 'price_change' THEN 1 END) as price_changes,
                    COUNT(CASE WHEN change_type = 'deleted' THEN 1 END) as deletions
                FROM change_history
                WHERE timestamp > datetime('now', '-24 hours')
            ''')
            changes = dict(cursor.fetchone())

            return {**stats, **changes}

    def save_statistics(self, stats: Dict):
        """حفظ إحصائيات الفحص"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO statistics (
                    total_products, available_products, out_of_stock_products,
                    new_products, deleted_products, status_changes, price_changes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                stats.get('total', 0),
                stats.get('available', 0),
                stats.get('out_of_stock', 0),
                stats.get('new', 0),
                stats.get('deleted', 0),
                stats.get('status_changes', 0),
                stats.get('price_changes', 0)
            ))

    def get_recent_changes(self, limit: int = 10) -> List[Dict]:
        """الحصول على آخر التغييرات"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT ch.*, p.name as product_name
                FROM change_history ch
                LEFT JOIN products p ON ch.product_id = p.id
                ORDER BY ch.timestamp DESC
                LIMIT ?
            ''', (limit,))

            return [dict(row) for row in cursor.fetchall()]

    def cleanup_old_history(self, days: int = 30):
        """حذف سجلات التغييرات القديمة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM change_history
                WHERE timestamp < datetime('now', '-' || ? || ' days')
            ''', (days,))

            deleted = cursor.rowcount
            logger.info(f"🧹 تم حذف {deleted} سجل قديم")
            return deleted
