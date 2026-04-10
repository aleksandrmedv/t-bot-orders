import pandas as pd
import os

from config import config
from database import import_users, import_products
from locales import get_text

def parse_users_excel(file_path: str):
    """
    Парсинг эксельки пользователей 2.0.
    Колонки: name, pin, phone, region
    """
    df = pd.read_excel(file_path)
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    users_data = []
    for _, row in df.iterrows():
        name = str(row.get('name', '')).strip()
        pin = str(row.get('pin', '')).strip()
        if pin.endswith('.0'): 
            pin = pin[:-2]
        
        # Получаем телефон
        phone = str(row.get('phone', '')).strip()
        if phone.endswith('.0'): 
            phone = phone[:-2]
            
        region = str(row.get('region', '')).strip()
        
        if name and pin:
            users_data.append({'name': name, 'pin': pin, 'phone': phone, 'region': region})
            
    if users_data:
        import_users(users_data)
        return len(users_data)
    return 0

def parse_catalog_excel(file_path: str):
    """
    Парсинг эксельки каталога 2.0.
    Колонки: name, price
    """
    df = pd.read_excel(file_path)
    df.columns = [str(c).lower().strip() for c in df.columns]
    
    products_data = []
    for _, row in df.iterrows():
        name = str(row.get('name', '')).strip()
        try:
            price = float(row.get('price', 0))
        except ValueError:
            price = 0.0
            
        if name:
            products_data.append({'name': name, 'price': price})
            
    if products_data:
        import_products(products_data)
        return len(products_data)
    return 0

def generate_order_excel(cart_items: list, total: float, user_name: str, phone: str, region: str, lang: str = 'ru') -> str:
    """Генерирует Excel-файл заказа."""
    data = []
    
    col_item = get_text(lang, 'excel_item')
    col_price = get_text(lang, 'excel_price')
    col_qty = get_text(lang, 'excel_qty')
    col_sum = get_text(lang, 'excel_sum')
    
    for item in cart_items:
        data.append({
            col_item: item['name'],
            col_price: item['price'],
            col_qty: item['quantity'],
            col_sum: item['price'] * item['quantity']
        })
    df = pd.DataFrame(data)
    
    # Строка ИТОГО
    df.loc[len(df)] = [get_text(lang, 'excel_total'), '', '', total]
    
    # Добавляем инфу о покупателе вниз таблички:
    df.loc[len(df)] = ['', '', '', '']
    df.loc[len(df)] = [get_text(lang, 'excel_client'), user_name, '', '']
    df.loc[len(df)] = [get_text(lang, 'excel_phone'), phone, '', '']
    df.loc[len(df)] = [get_text(lang, 'excel_region'), region, '', '']
    
    file_name = f"Order_{user_name}_{region}.xlsx"
    df.to_excel(file_name, index=False)
    return file_name

