import os
import asyncio
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database import (
    init_db, authenticate_user, get_products_paginated, search_products_paginated,
    add_to_cart, remove_from_cart, get_cart, get_cart_total, clear_cart
)
import data_manager
from locales import get_text

PRODUCTS_PER_PAGE = 8

# Инициализация телеграм-бота
bot = Bot(token=config.bot_token)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

class AuthStates(StatesGroup):
    waiting_for_pin = State()

class AdminStates(StatesGroup):
    waiting_for_users_excel = State()
    waiting_for_catalog_excel = State()

async def get_lang(message_or_call, state: FSMContext) -> str:
    data = await state.get_data()
    if 'lang' in data:
        return data['lang']
    code = message_or_call.from_user.language_code
    if code and code.startswith('en'):
        return 'en'
    return 'ru'

# --- АДМИН ПАНЕЛЬ (Загрузка Excel) ---

@router.message(Command("update_users"))
async def cmd_update_users(message: Message, state: FSMContext):
    lang = await get_lang(message, state)
    if message.from_user.id not in config.get_admin_ids:
        await message.answer(get_text(lang, 'admin_denied'))
        return
    await state.set_state(AdminStates.waiting_for_users_excel)
    await message.answer(get_text(lang, 'update_users_prompt'))

@router.message(AdminStates.waiting_for_users_excel, F.document)
async def handle_users_excel(message: Message, state: FSMContext):
    lang = await get_lang(message, state)
    file_id = message.document.file_id
    file_info = await bot.get_file(file_id)
    file_path = f"users_{message.from_user.id}.xlsx"
    await bot.download_file(file_info.file_path, file_path)
    
    try:
        count = data_manager.parse_users_excel(file_path)
        await message.answer(get_text(lang, 'users_updated', count=count))
    except Exception as e:
        await message.answer(get_text(lang, 'file_error', e=e))
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        await state.set_state(None)

@router.message(Command("update_catalog"))
async def cmd_update_catalog(message: Message, state: FSMContext):
    lang = await get_lang(message, state)
    if message.from_user.id not in config.get_admin_ids:
        await message.answer(get_text(lang, 'admin_denied'))
        return
    await state.set_state(AdminStates.waiting_for_catalog_excel)
    await message.answer(get_text(lang, 'update_catalog_prompt'))

@router.message(AdminStates.waiting_for_catalog_excel, F.document)
async def handle_catalog_excel(message: Message, state: FSMContext):
    lang = await get_lang(message, state)
    file_id = message.document.file_id
    file_info = await bot.get_file(file_id)
    file_path = f"catalog_{message.from_user.id}.xlsx"
    await bot.download_file(file_info.file_path, file_path)
    
    try:
        count = data_manager.parse_catalog_excel(file_path)
        await message.answer(get_text(lang, 'catalog_updated', count=count))
    except Exception as e:
        await message.answer(get_text(lang, 'file_error', e=e))
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        await state.set_state(None)


# --- АВТОРИЗАЦИЯ 2.0 И ЯЗЫК ---
@router.message(Command("set_language"))
async def cmd_set_language(message: Message, state: FSMContext):
    lang = await get_lang(message, state)
    new_lang = 'en' if lang == 'ru' else 'ru'
    await state.update_data(lang=new_lang)
    await message.answer(get_text(new_lang, 'lang_changed'))

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    lang = await get_lang(message, state)
    user_data = await state.get_data()
    if user_data.get("authenticated", False):
        await message.answer(get_text(lang, 'welcome_back', name=user_data.get('name')))
        return
    await state.set_state(AuthStates.waiting_for_pin)
    await message.answer(get_text(lang, 'welcome_init'))

@router.message(AuthStates.waiting_for_pin)
async def request_pin(message: Message, state: FSMContext):
    lang = await get_lang(message, state)
    pin = message.text.strip()
    
    user = authenticate_user(pin)
    if user:
        await state.clear()
        # Сохраняем все данные юзера
        await state.update_data(
            authenticated=True, 
            user_id=user['id'], 
            name=user['name'], 
            phone=user['phone'],
            region=user['region'],
            lang=lang # Сохраняем язык
        )
        await message.answer(get_text(lang, 'auth_success', name=user['name'], phone=user['phone'], region=user['region']))
    else:
        await message.answer(get_text(lang, 'auth_fail'))

@router.message(Command("logout"))
async def cmd_logout(message: Message, state: FSMContext):
    lang = await get_lang(message, state)
    await state.clear()
    await state.update_data(lang=lang) # Сохраняем языковые настройки даже после выхода
    await message.answer(get_text(lang, 'logout_msg'))


# --- КАТАЛОГ, ПОИСК И ПАГИНАЦИЯ ---

def build_catalog_keyboard(offset: int, query: str = None, lang: str = 'ru') -> tuple[InlineKeyboardMarkup, int, int]:
    if query:
        products, total = search_products_paginated(query, PRODUCTS_PER_PAGE, offset)
    else:
        products, total = get_products_paginated(PRODUCTS_PER_PAGE, offset)
        
    builder = []
    
    for p in products:
        btn_text = get_text(lang, 'btn_add', name=p['name'], price=p['price'])
        builder.append([
            InlineKeyboardButton(text=btn_text, callback_data=f"add_{p['id']}")
        ])
        
    nav_buttons = []
    if offset > 0:
        prev_offset = max(0, offset - PRODUCTS_PER_PAGE)
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"page_{prev_offset}"))
    
    page_num = (offset // PRODUCTS_PER_PAGE) + 1
    total_pages = (total + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE
    if total_pages == 0: total_pages = 1
    
    nav_buttons.append(InlineKeyboardButton(text=f"— {page_num}/{total_pages} —", callback_data="ignore"))
    
    if offset + PRODUCTS_PER_PAGE < total:
        next_offset = offset + PRODUCTS_PER_PAGE
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"page_{next_offset}"))
        
    if nav_buttons:
        builder.append(nav_buttons)

    builder.append([InlineKeyboardButton(text=get_text(lang, 'btn_cart'), callback_data="view_cart")])
    return InlineKeyboardMarkup(inline_keyboard=builder), total, total_pages

@router.message(Command("catalog"))
async def cmd_catalog(message: Message, state: FSMContext):
    lang = await get_lang(message, state)
    data = await state.get_data()
    if not data.get("authenticated"):
        return await message.answer(get_text(lang, 'req_auth'))
        
    await state.update_data(search_query=None)
    kb, total, total_pages = build_catalog_keyboard(offset=0, query=None, lang=lang)
    await message.answer(get_text(lang, 'catalog_title', total=total), reply_markup=kb)

@router.message(F.text & ~F.state(AdminStates.waiting_for_users_excel) & ~F.state(AdminStates.waiting_for_catalog_excel))
async def handle_search_text(message: Message, state: FSMContext):
    lang = await get_lang(message, state)
    data = await state.get_data()
    if not data.get("authenticated"):
        return
        
    if message.text.startswith("/"):
        return 
        
    query = message.text.strip().lower()
    await state.update_data(search_query=query)
    
    kb, total, total_pages = build_catalog_keyboard(offset=0, query=query, lang=lang)
    
    if total == 0:
        await message.answer(get_text(lang, 'search_not_found', query=query))
    else:
        await message.answer(get_text(lang, 'search_found', query=query, total=total), reply_markup=kb)

@router.callback_query(F.data.startswith("page_"))
async def callback_paginate(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback, state)
    offset = int(callback.data.split("_")[1])
    data = await state.get_data()
    query = data.get("search_query")
    
    kb, total, total_pages = build_catalog_keyboard(offset=offset, query=query, lang=lang)
    
    title = get_text(lang, 'title_search', query=query, total=total) if query else get_text(lang, 'title_catalog', total=total)
    try:
        await callback.message.edit_text(text=title, reply_markup=kb)
    except Exception:
        pass 
    await callback.answer()

@router.callback_query(F.data == "ignore")
async def callback_ignore(callback: CallbackQuery):
    await callback.answer()

# --- КОРЗИНА И ЗАКАЗ ---

@router.callback_query(F.data.startswith("add_"))
async def callback_add_item(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback, state)
    user_id = callback.from_user.id
    product_id = int(callback.data.split("_")[1])
    add_to_cart(user_id, product_id, 1)
    
    total = get_cart_total(user_id)
    await callback.answer(get_text(lang, 'added_to_cart', total=total), show_alert=False)

def get_cart_text_and_keyboard(user_id: int, lang: str = 'ru'):
    items = get_cart(user_id)
    if not items:
        return get_text(lang, 'cart_empty'), None
    
    text = get_text(lang, 'cart_title')
    total = 0.0
    kb_builder = []
    for i, item in enumerate(items, 1):
        line_total = round(item['price'] * item['quantity'], 2)
        text += get_text(lang, 'cart_item', i=i, name=item['name'], qty=item['quantity'], price=item['price'], total=line_total)
        total = round(total + line_total, 2)
        kb_builder.append([InlineKeyboardButton(text=get_text(lang, 'btn_remove', name=item['name']), callback_data=f"rem_{item['product_id']}")])
    
    text += get_text(lang, 'cart_total', total=total)
    
    kb_builder.append([InlineKeyboardButton(text=get_text(lang, 'btn_checkout'), callback_data="checkout")])
    kb_builder.append([InlineKeyboardButton(text=get_text(lang, 'btn_clear'), callback_data="clear_cart")])
    return text, InlineKeyboardMarkup(inline_keyboard=kb_builder)

@router.message(Command("cart"))
async def cmd_cart(message: Message, state: FSMContext):
    lang = await get_lang(message, state)
    data = await state.get_data()
    if not data.get("authenticated"):
        return await message.answer(get_text(lang, 'req_auth'))
    text, kb = get_cart_text_and_keyboard(message.from_user.id, lang=lang)
    await message.answer(text, reply_markup=kb)

@router.callback_query(F.data == "view_cart")
async def callback_view_cart(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback, state)
    user_id = getattr(callback, 'fromuser', callback.from_user).id
    text, kb = get_cart_text_and_keyboard(user_id, lang=lang)
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("rem_"))
async def callback_remove_item(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback, state)
    product_id = int(callback.data.split("_")[1])
    remove_from_cart(callback.from_user.id, product_id, 1)
    
    text, kb = get_cart_text_and_keyboard(callback.from_user.id, lang=lang)
    if kb:
        await callback.message.edit_text(text, reply_markup=kb)
    else:
        await callback.message.edit_text(get_text(lang, 'cart_empty'))
    await callback.answer()

@router.callback_query(F.data == "clear_cart")
async def callback_clear_cart(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback, state)
    clear_cart(callback.from_user.id)
    await callback.message.edit_text(get_text(lang, 'cart_cleared'))
    await callback.answer()

@router.callback_query(F.data == "checkout")
async def callback_checkout(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback, state)
    total = get_cart_total(callback.from_user.id)
    if total == 0:
        return await callback.answer(get_text(lang, 'checkout_empty'), show_alert=True)
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, 'btn_yes'), callback_data="confirm_order")],
        [InlineKeyboardButton(text=get_text(lang, 'btn_no'), callback_data="view_cart")]
    ])
    await callback.message.edit_text(
        get_text(lang, 'checkout_confirm', total=total),
        reply_markup=kb
    )
    await callback.answer()

@router.callback_query(F.data == "confirm_order")
async def callback_confirm_order(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback, state)
    user_id = callback.from_user.id
    items = get_cart(user_id)
    total = get_cart_total(user_id)
    data = await state.get_data()
    
    user_name = data.get("name", "Unknown")
    phone = data.get("phone", "Unknown")
    region = data.get("region", "Unknown")
    
    await callback.message.edit_text(get_text(lang, 'order_processing'))
    
    try:
        file_path = data_manager.generate_order_excel(items, total, user_name, phone, region, lang=lang)
        
        if config.get_admin_ids:
            doc = FSInputFile(file_path)
            body = get_text(lang, 'admin_order_notification', name=user_name, phone=phone, region=region, total=total)
            for admin_id in config.get_admin_ids:
                try:
                    await bot.send_document(admin_id, doc, caption=body)
                except Exception as ex:
                    print(f"Failed to send order to admin {admin_id}: {ex}")
        else:
            print("Предупреждение: не настроены ADMIN_IDS, заказ не отправлен администраторам!")

        clear_cart(user_id)
        
        await callback.message.edit_text(get_text(lang, 'order_success', total=total))
    except Exception as e:
        await callback.message.edit_text(get_text(lang, 'order_error', e=e))
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def main():
    print("Инициализация базы данных V2.0...")
    init_db()
    
    print("🤖 Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
