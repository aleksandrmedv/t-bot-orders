import sqlite3
from typing import List, Dict, Optional, Tuple

DB_PATH = "bot_database.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Обновляем таблицы: сносим старые для миграции схемы
        cursor.execute("DROP TABLE IF EXISTS users")
        cursor.execute("DROP TABLE IF EXISTS products")
        
        # Таблица пользователей (с телефоном)
        cursor.execute('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            pin TEXT NOT NULL,
            phone TEXT NOT NULL,
            region TEXT NOT NULL
        )
        ''')
        
        # Таблица товаров (БЕЗ региона)
        cursor.execute('''
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            name_lower TEXT NOT NULL,
            price REAL NOT NULL
        )
        ''')
        
        # Корзина остается прежней
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart (
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            PRIMARY KEY (user_id, product_id)
        )
        ''')
        conn.commit()

def authenticate_user(pin: str) -> Optional[Dict]:
    """Проверка только по пин-коду (без регистра)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # В SQLITE LOWER() может не работать со всеми юникод-символами, но для 6-значных англ-цифровых PIN отлично работает.
        cursor.execute("SELECT id, name, phone, region FROM users WHERE LOWER(pin) = ?", (pin.lower(),))
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "name": row[1], "phone": row[2], "region": row[3]}
    return None

def get_products_paginated(limit: int, offset: int) -> Tuple[List[Dict], int]:
    """Возвращает список товаров для страницы и общее кол-во всех товаров."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Считаем всего
        cursor.execute("SELECT COUNT(id) FROM products")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT id, name, price FROM products LIMIT ? OFFSET ?", (limit, offset))
        rows = cursor.fetchall()
        return [{"id": r[0], "name": r[1], "price": r[2]} for r in rows], total

def search_products_paginated(query: str, limit: int, offset: int) -> Tuple[List[Dict], int]:
    """Ищет товары по имени (без регистра) и пагинирует их."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Считаем всего найденных
        search_pattern = f"%{query}%"
        # Для кириллицы SQLite штатный LIKE не работает без регистра, поэтому ищем по колонке name_lower
        cursor.execute("SELECT COUNT(id) FROM products WHERE name_lower LIKE ?", (search_pattern,))
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT id, name, price FROM products WHERE name_lower LIKE ? LIMIT ? OFFSET ?", (search_pattern, limit, offset))
        rows = cursor.fetchall()
        return [{"id": r[0], "name": r[1], "price": r[2]} for r in rows], total

def get_product(product_id: int) -> Optional[Dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, price FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "name": row[1], "price": row[2]}
    return None

def add_to_cart(user_id: int, product_id: int, quantity: int = 1):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT quantity FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE cart SET quantity = quantity + ? WHERE user_id = ? AND product_id = ?", (quantity, user_id, product_id))
        else:
            cursor.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, ?)", (user_id, product_id, quantity))
        conn.commit()

def remove_from_cart(user_id: int, product_id: int, quantity: int = 1):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT quantity FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        row = cursor.fetchone()
        if row:
            if row[0] > quantity:
                cursor.execute("UPDATE cart SET quantity = quantity - ? WHERE user_id = ? AND product_id = ?", (quantity, user_id, product_id))
            else:
                cursor.execute("DELETE FROM cart WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        conn.commit()

def clear_cart(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
        conn.commit()

def get_cart(user_id: int) -> List[Dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.id, p.name, p.price, c.quantity 
            FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.user_id = ?
        ''', (user_id,))
        rows = cursor.fetchall()
        return [{"product_id": r[0], "name": r[1], "price": r[2], "quantity": r[3]} for r in rows]

def get_cart_total(user_id: int) -> float:
    cart_items = get_cart(user_id)
    return round(sum(item['price'] * item['quantity'] for item in cart_items), 2)

def import_users(users_data: List[Dict]):
    """Очищает и загружает новых пользователей: name, pin, phone, region."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users")
        for u in users_data:
            cursor.execute("INSERT INTO users (name, pin, phone, region) VALUES (?, ?, ?, ?)", 
                           (u['name'], str(u['pin']), str(u.get('phone', '')), u['region']))
        conn.commit()

def import_products(products_data: List[Dict]):
    """Очищает и загружает новые товары: name, price."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products")
        for p in products_data:
            cursor.execute("INSERT INTO products (name, name_lower, price) VALUES (?, ?, ?)", 
                           (p['name'], str(p['name']).lower(), p['price']))
        conn.commit()
