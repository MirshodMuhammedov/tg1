import asyncio
import logging
import aiohttp
import json
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, 
    CallbackQuery, InputFile, FSInputFile
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.media_group import MediaGroupBuilder
import os
from datetime import datetime
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import sqlite3

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
CHANNEL_ID = os.getenv('CHANNEL_ID', '@your_channel')
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')

if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
    logger.error("❌ Please set BOT_TOKEN in .env file!")
    exit(1)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# REGIONS AND DISTRICTS DATA
REGIONS_DATA = {
    'uz': {
        'tashkent_city': {
            'name': 'Toshkent shahri',
            'districts': {
                'bektemir': 'Bektemir',
                'chilonzor': 'Chilonzor', 
                'mirobod': 'Mirobod',
                'mirzo_ulugbek': 'Mirzo Ulug\'bek',
                'olmazor': 'Olmazor',
                'sergeli': 'Sergeli',
                'shayxontohur': 'Shayxontohur',
                'uchtepa': 'Uchtepa',
                'yakkasaroy': 'Yakkasaroy',
                'yunusobod': 'Yunusobod',
                'yashnobod': 'Yashnobod'
            }
        },
        'tashkent_region': {
            'name': 'Toshkent viloyati',
            'districts': {
                'angren': 'Angren',
                'bekobod': 'Bekobod',
                'bostonliq': 'Bo\'stonliq',
                'chinoz': 'Chinoz',
                'qibray': 'Qibray',
                'oqqorgon': 'Oqqo\'rg\'on',
                'olmaliq': 'Olmaliq',
                'ohangaron': 'Ohangaron',
                'parkent': 'Parkent',
                'piskent': 'Piskent',
                'yangiyol': 'Yangiyo\'l',
                'zangiota': 'Zangiota'
            }
        },
        'samarkand': {
            'name': 'Samarqand viloyati',
            'districts': {
                'samarkand': 'Samarqand',
                'bulungur': 'Bulung\'ur',
                'ishtixon': 'Ishtixon',
                'jomboy': 'Jomboy',
                'kattaqorgon': 'Kattaqo\'rg\'on',
                'narpay': 'Narpay',
                'nurobod': 'Nurobod',
                'oqdaryo': 'Oqdaryo',
                'urgut': 'Urgut'
            }
        }
    },
    'ru': {
        'tashkent_city': {
            'name': 'Город Ташкент',
            'districts': {
                'bektemir': 'Бектемир',
                'chilonzor': 'Чиланзар',
                'mirobod': 'Мирабад',
                'mirzo_ulugbek': 'Мирзо Улугбек',
                'olmazor': 'Алмазар',
                'sergeli': 'Сергели',
                'shayxontohur': 'Шайхантахур',
                'uchtepa': 'Учтепа',
                'yakkasaroy': 'Яккасарай',
                'yunusobod': 'Юнусабад',
                'yashnobod': 'Яшнабад'
            }
        },
        'tashkent_region': {
            'name': 'Ташкентская область',
            'districts': {
                'angren': 'Ангрен',
                'bekobod': 'Бекабад',
                'bostonliq': 'Бустанлык',
                'chinoz': 'Чиназ',
                'qibray': 'Кибрай',
                'oqqorgon': 'Аккурган',
                'olmaliq': 'Алмалык',
                'ohangaron': 'Ахангаран',
                'parkent': 'Паркент',
                'piskent': 'Пскент',
                'yangiyol': 'Янгиюль',
                'zangiota': 'Зангиота'
            }
        },
        'samarkand': {
            'name': 'Самаркандская область',
            'districts': {
                'samarkand': 'Самарканд',
                'bulungur': 'Булунгур',
                'ishtixon': 'Иштыхан',
                'jomboy': 'Джамбай',
                'kattaqorgon': 'Каттакурган',
                'narpay': 'Нарпай',
                'nurobod': 'Нурабад',
                'oqdaryo': 'Акдарья',
                'urgut': 'Ургут'
            }
        }
    },
    'en': {
        'tashkent_city': {
            'name': 'Tashkent City',
            'districts': {
                'bektemir': 'Bektemir',
                'chilonzor': 'Chilanzar',
                'mirobod': 'Mirobod',
                'mirzo_ulugbek': 'Mirzo Ulugbek',
                'olmazor': 'Olmazor',
                'sergeli': 'Sergeli',
                'shayxontohur': 'Shaykhantakhur',
                'uchtepa': 'Uchtepa',
                'yakkasaroy': 'Yakkasaray',
                'yunusobod': 'Yunusabad',
                'yashnobod': 'Yashnabad'
            }
        },
        'tashkent_region': {
            'name': 'Tashkent Region',
            'districts': {
                'angren': 'Angren',
                'bekobod': 'Bekabad',
                'bostonliq': 'Bostanlyk',
                'chinoz': 'Chinaz',
                'qibray': 'Kibray',
                'oqqorgon': 'Akkurgan',
                'olmaliq': 'Almalyk',
                'ohangaron': 'Akhangaran',
                'parkent': 'Parkent',
                'piskent': 'Piskent',
                'yangiyol': 'Yangiyul',
                'zangiota': 'Zangiata'
            }
        },
        'samarkand': {
            'name': 'Samarkand Region',
            'districts': {
                'samarkand': 'Samarkand',
                'bulungur': 'Bulungur',
                'ishtixon': 'Ishtykhan',
                'jomboy': 'Jambay',
                'kattaqorgon': 'Kattakurgan',
                'narpay': 'Narpay',
                'nurobod': 'Nurabad',
                'oqdaryo': 'Akdarya',
                'urgut': 'Urgut'
            }
        }
    }
}

# Database setup with updated schema
def init_db():
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            language TEXT DEFAULT 'uz',
            is_blocked BOOLEAN DEFAULT FALSE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Updated listings table with region/district
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            description TEXT,
            property_type TEXT,
            region TEXT,
            district TEXT,
            address TEXT,
            full_address TEXT,
            price INTEGER,
            area INTEGER,
            rooms INTEGER,
            status TEXT,
            condition TEXT,
            contact_info TEXT,
            photo_file_ids TEXT,
            is_premium BOOLEAN DEFAULT FALSE,
            is_approved BOOLEAN DEFAULT TRUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (telegram_id)
        )
    ''')
    
    # Favorites table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            listing_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (telegram_id),
            FOREIGN KEY (listing_id) REFERENCES listings (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Enhanced translations with region/district
TRANSLATIONS = {
    'uz': {
        'start': "🏠 Assalomu alaykum!\n\nUy-joy e'lonlari botiga xush kelibsiz!\nSiz bu yerda:\n• E'lon joylashingiz\n• Qulay qidiruv qilishingiz\n• Premium xizmatlardan foydalanishingiz mumkin",
        'choose_language': "Tilni tanlang:",
        'main_menu': "🏠 Asosiy menyu",
        'post_listing': "📝 E'lon joylash",
        'view_listings': "👀 E'lonlar",
        'search': "🔍 Qidiruv",
        'search_location': "🏘 Hudud bo'yicha",
        'favorites': "❤️ Sevimlilar",
        'info': "ℹ️ Ma'lumot",
        'contact': "☎️ Aloqa",
        'language': "🌐 Til",
        'back': "◀️ Orqaga",
        'cancel': "❌ Bekor qilish",
        'listing_title': "📝 E'lon sarlavhasini kiriting:",
        'listing_description': "📄 E'lon tavsifini kiriting:",
        'property_type': "🏘 Uy-joy turini tanlang:",
        'select_region': "🗺 Viloyatni tanlang:",
        'select_district': "🏘 Tumanni tanlang:",
        'region_selected': "✅ Viloyat tanlandi",
        'district_selected': "✅ Tuman tanlandi",
        'apartment': "🏢 Kvartira",
        'house': "🏠 Uy",
        'commercial': "🏪 Tijorat",
        'land': "🌱 Yer",
        'address': "📍 Aniq manzilni kiriting:",
        'price': "💰 Narxni kiriting (so'm):",
        'area': "📐 Maydonni kiriting (m²):",
        'rooms': "🚪 Xonalar sonini kiriting:",
        'condition': "🏗 Holatini tanlang:",
        'new': "✨ Yangi",
        'good': "👍 Yaxshi",
        'repair_needed': "🔨 Ta'mir kerak",
        'status': "🎯 Maqsadni tanlang:",
        'sale': "💵 Sotiladi",
        'rent': "📅 Ijara",
        'contact_info': "📞 Aloqa ma'lumotlarini kiriting:",
        'add_photos': "📸 Rasmlar qo'shing (ixtiyoriy):",
        'photos_done': "✅ Tayyor",
        'listing_created': "🎉 E'lon muvaffaqiyatli yaratildi!",
        'no_listings': "😔 Hozircha e'lonlar yo'q",
        'added_to_favorites': "❤️ Sevimlilar ro'yxatiga qo'shildi!",
        'removed_from_favorites': "💔 Sevimlilardan o'chirildi!",
        'no_favorites': "😔 Sevimlilar ro'yxati bo'sh",
        'contact_seller': "💬 Sotuvchi bilan bog'lanish",
        'add_favorite': "❤️ Sevimlilar",
        'remove_favorite': "💔 O'chirish",
        'next': "Keyingi ▶️",
        'previous': "◀️ Oldingi",
        'skip': "⏭ O'tkazib yuborish",
        'search_prompt': "🔍 Qidirish uchun kalit so'z kiriting:",
        'about': "ℹ️ Bot haqida:\n\nBu bot uy-joy e'lonlari uchun yaratilgan.\n\n👨‍💻 Dasturchi: @your_username",
        'location_search_results': "🗺 {region} bo'yicha natijalar:",
        'no_location_results': "😔 Bu hududda e'lonlar topilmadi."
    },
    'ru': {
        'start': "🏠 Добро пожаловать!\n\nДобро пожаловать в бот объявлений недвижимости!",
        'main_menu': "🏠 Главное меню",
        'post_listing': "📝 Разместить объявление",
        'view_listings': "👀 Объявления",
        'search': "🔍 Поиск",
        'search_location': "🏘 По району",
        'favorites': "❤️ Избранное",
        'info': "ℹ️ Информация",
        'contact': "☎️ Контакты",
        'language': "🌐 Язык",
        'back': "◀️ Назад",
        'cancel': "❌ Отмена",
        'select_region': "🗺 Выберите область:",
        'select_district': "🏘 Выберите район:",
        'region_selected': "✅ Область выбрана",
        'district_selected': "✅ Район выбран",
        'apartment': "🏢 Квартира",
        'house': "🏠 Дом",
        'commercial': "🏪 Коммерческая",
        'land': "🌱 Земля",
        'new': "✨ Новое",
        'good': "👍 Хорошее",
        'repair_needed': "🔨 Требует ремонта",
        'sale': "💵 Продажа",
        'rent': "📅 Аренда",
        'listing_created': "🎉 Объявление успешно создано!",
        'no_listings': "😔 Объявлений пока нет",
        'about': "ℹ️ О боте:\n\nЭтот бот создан для объявлений недвижимости.\n\n👨‍💻 Разработчик: @your_username",
        'location_search_results': "🗺 Результаты по {region}:",
        'no_location_results': "😔 В этом регионе объявлений не найдено."
    },
    'en': {
        'start': "🏠 Welcome!\n\nWelcome to the real estate listings bot!",
        'main_menu': "🏠 Main menu",
        'post_listing': "📝 Post listing",
        'view_listings': "👀 Listings",
        'search': "🔍 Search",
        'search_location': "🏘 By location",
        'favorites': "❤️ Favorites",
        'info': "ℹ️ Info",
        'contact': "☎️ Contact",
        'language': "🌐 Language",
        'back': "◀️ Back",
        'cancel': "❌ Cancel",
        'select_region': "🗺 Select region:",
        'select_district': "🏘 Select district:",
        'region_selected': "✅ Region selected",
        'district_selected': "✅ District selected",
        'apartment': "🏢 Apartment",
        'house': "🏠 House",
        'commercial': "🏪 Commercial",
        'land': "🌱 Land",
        'new': "✨ New",
        'good': "👍 Good",
        'repair_needed': "🔨 Needs repair",
        'sale': "💵 Sale",
        'rent': "📅 Rent",
        'listing_created': "🎉 Listing created successfully!",
        'no_listings': "😔 No listings yet",
        'about': "ℹ️ About bot:\n\nThis bot is created for real estate listings.\n\n👨‍💻 Developer: @your_username",
        'location_search_results': "🗺 Results for {region}:",
        'no_location_results': "😔 No listings found in this region."
    }
}

# FSM States with region/district
class ListingStates(StatesGroup):
    title = State()
    description = State()
    property_type = State()
    region = State()
    district = State()
    address = State()
    price = State()
    area = State()
    rooms = State()
    condition = State()
    status = State()
    contact_info = State()
    photos = State()

class SearchStates(StatesGroup):
    query = State()
    location_search = State()

# Helper functions
def get_text(user_lang: str, key: str, **kwargs) -> str:
    text = TRANSLATIONS.get(user_lang, TRANSLATIONS['uz']).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except:
            return text
    return text

def get_user_language(user_id: int) -> str:
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('SELECT language FROM users WHERE telegram_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 'uz'

def save_user(user_id: int, username: str, first_name: str, last_name: str, language: str = 'uz'):
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (telegram_id, username, first_name, last_name, language)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name, language))
    conn.commit()
    conn.close()

def update_user_language(user_id: int, language: str):
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET language = ? WHERE telegram_id = ?', (language, user_id))
    conn.commit()
    conn.close()

def get_main_menu_keyboard(user_lang: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=get_text(user_lang, 'post_listing')))
    builder.add(KeyboardButton(text=get_text(user_lang, 'view_listings')))
    builder.add(KeyboardButton(text=get_text(user_lang, 'search')))
    builder.add(KeyboardButton(text=get_text(user_lang, 'search_location')))
    builder.add(KeyboardButton(text=get_text(user_lang, 'favorites')))
    builder.add(KeyboardButton(text=get_text(user_lang, 'info')))
    builder.add(KeyboardButton(text=get_text(user_lang, 'language')))
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def get_language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"))
    builder.add(InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"))
    builder.add(InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en"))
    builder.adjust(1)
    return builder.as_markup()

def get_regions_keyboard(user_lang: str) -> InlineKeyboardMarkup:
    """Create keyboard with all regions"""
    builder = InlineKeyboardBuilder()
    
    regions = REGIONS_DATA[user_lang]
    for region_key, region_data in regions.items():
        builder.add(InlineKeyboardButton(
            text=region_data['name'], 
            callback_data=f"region_{region_key}"
        ))
    
    builder.adjust(1)  # One button per row
    return builder.as_markup()

def get_districts_keyboard(region_key: str, user_lang: str) -> InlineKeyboardMarkup:
    """Create keyboard with districts for selected region"""
    builder = InlineKeyboardBuilder()
    
    try:
        districts = REGIONS_DATA[user_lang][region_key]['districts']
        
        # Add districts (2 per row for better layout)
        for district_key, district_name in districts.items():
            builder.add(InlineKeyboardButton(
                text=district_name,
                callback_data=f"district_{district_key}"
            ))
        
        # Add back button
        builder.add(InlineKeyboardButton(
            text=get_text(user_lang, 'back'),
            callback_data="back_to_regions"
        ))
        
        builder.adjust(2, 2, 2, 2, 2, 1)  # 2 per row, back button on separate row
        return builder.as_markup()
        
    except KeyError:
        # Fallback empty keyboard
        return InlineKeyboardMarkup(inline_keyboard=[])

def get_property_type_keyboard(user_lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'apartment'), callback_data="type_apartment"))
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'house'), callback_data="type_house"))
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'commercial'), callback_data="type_commercial"))
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'land'), callback_data="type_land"))
    builder.adjust(2)
    return builder.as_markup()

def get_condition_keyboard(user_lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'new'), callback_data="condition_new"))
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'good'), callback_data="condition_good"))
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'repair_needed'), callback_data="condition_repair"))
    builder.adjust(2)
    return builder.as_markup()

def get_status_keyboard(user_lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'sale'), callback_data="status_sale"))
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'rent'), callback_data="status_rent"))
    builder.adjust(2)
    return builder.as_markup()

def get_listing_keyboard(listing_id: int, user_lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'add_favorite'), callback_data=f"fav_add_{listing_id}"))
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'contact_seller'), callback_data=f"contact_{listing_id}"))
    builder.adjust(2)
    return builder.as_markup()

# Enhanced database operations
def save_listing(user_id: int, data: dict):
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    
    photo_file_ids = json.dumps(data.get('photo_file_ids', []))
    
    cursor.execute('''
        INSERT INTO listings (
            user_id, title, description, property_type, region, district,
            address, full_address, price, area, rooms, condition, status, 
            contact_info, photo_file_ids
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, data['title'], data['description'], data['property_type'],
        data.get('region'), data.get('district'), data['address'], 
        data.get('full_address'), data['price'], data['area'], data['rooms'],
        data['condition'], data['status'], data['contact_info'], photo_file_ids
    ))
    
    conn.commit()
    conn.close()

def get_listings(limit=10, offset=0):
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l.*, u.first_name, u.username 
        FROM listings l 
        JOIN users u ON l.user_id = u.telegram_id 
        WHERE l.is_approved = 1 
        ORDER BY l.created_at DESC 
        LIMIT ? OFFSET ?
    ''', (limit, offset))
    listings = cursor.fetchall()
    conn.close()
    return listings

def search_listings(query: str):
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l.*, u.first_name, u.username 
        FROM listings l 
        JOIN users u ON l.user_id = u.telegram_id 
        WHERE (l.title LIKE ? OR l.description LIKE ? OR l.full_address LIKE ?) 
        AND l.is_approved = 1 
        ORDER BY l.created_at DESC 
        LIMIT 10
    ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
    listings = cursor.fetchall()
    conn.close()
    return listings

def search_listings_by_location(region_key=None, district_key=None):
    """Search listings by region and/or district"""
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    
    query = '''
        SELECT l.*, u.first_name, u.username 
        FROM listings l 
        JOIN users u ON l.user_id = u.telegram_id 
        WHERE l.is_approved = 1
    '''
    params = []
    
    if region_key:
        query += ' AND l.region = ?'
        params.append(region_key)
    
    if district_key:
        query += ' AND l.district = ?'
        params.append(district_key)
    
    query += ' ORDER BY l.created_at DESC LIMIT 10'
    
    cursor.execute(query, params)
    listings = cursor.fetchall()
    conn.close()
    return listings

def add_to_favorites(user_id: int, listing_id: int):
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO favorites (user_id, listing_id) 
        VALUES (?, ?)
    ''', (user_id, listing_id))
    conn.commit()
    conn.close()

def get_user_favorites(user_id: int):
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l.*, u.first_name, u.username 
        FROM favorites f
        JOIN listings l ON f.listing_id = l.id
        JOIN users u ON l.user_id = u.telegram_id
        WHERE f.user_id = ?
        ORDER BY f.created_at DESC
    ''', (user_id,))
    favorites = cursor.fetchall()
    conn.close()
    return favorites

def format_listing_display(listing, user_lang):
    """Format listing for display with region/district info"""
    # listing columns: id, user_id, title, description, property_type, region, district, address, full_address, price, area, rooms, status, condition, contact_info, photo_file_ids...
    
    location_display = listing[8] if listing[8] else listing[7]  # full_address or address
    
    listing_text = f"""
🏠 <b>{listing[2]}</b>

🗺 <b>Joylashuv:</b> {location_display}
💰 <b>Narx:</b> {listing[9]:,} so'm
📐 <b>Maydon:</b> {listing[10]} m²
🚪 <b>Xonalar:</b> {listing[11]}
📞 <b>Aloqa:</b> {listing[14]}

{listing[3][:200]}...
"""
    return listing_text

# Handlers
@dp.message(CommandStart())
async def start_handler(message: Message):
    user = message.from_user
    save_user(user.id, user.username, user.first_name, user.last_name)
    user_lang = get_user_language(user.id)
    
    await message.answer(
        get_text(user_lang, 'start'),
        reply_markup=get_main_menu_keyboard(user_lang)
    )

@dp.message(F.text.in_(['🌐 Til', '🌐 Язык', '🌐 Language']))
async def language_handler(message: Message):
    user_lang = get_user_language(message.from_user.id)
    await message.answer(
        get_text(user_lang, 'choose_language'),
        reply_markup=get_language_keyboard()
    )

@dp.callback_query(F.data.startswith('lang_'))
async def language_callback(callback_query):
    lang = callback_query.data.split('_')[1]
    update_user_language(callback_query.from_user.id, lang)
    
    await callback_query.message.edit_text(
        get_text(lang, 'main_menu'),
        reply_markup=None
    )
    
    await callback_query.message.answer(
        get_text(lang, 'main_menu'),
        reply_markup=get_main_menu_keyboard(lang)
    )
    await callback_query.answer()

@dp.message(F.text.in_(['📝 E\'lon joylash', '📝 Разместить объявление', '📝 Post listing']))
async def post_listing_handler(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    await state.set_state(ListingStates.title)
    await message.answer(get_text(user_lang, 'listing_title'))

@dp.message(ListingStates.title)
async def process_title(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    await state.update_data(title=message.text)
    await state.set_state(ListingStates.description)
    await message.answer(get_text(user_lang, 'listing_description'))

@dp.message(ListingStates.description)
async def process_description(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    await state.update_data(description=message.text)
    await state.set_state(ListingStates.property_type)
    await message.answer(
        get_text(user_lang, 'property_type'),
        reply_markup=get_property_type_keyboard(user_lang)
    )

@dp.callback_query(F.data.startswith('type_'))
async def process_property_type(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    property_type = callback_query.data.split('_')[1]
    await state.update_data(property_type=property_type)
    
    # NEW: Go to region selection
    await state.set_state(ListingStates.region)
    await callback_query.message.edit_text(
        get_text(user_lang, 'select_region'),
        reply_markup=get_regions_keyboard(user_lang)
    )
    await callback_query.answer()

@dp.callback_query(F.data.startswith('region_'))
async def process_region_selection(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    region_key = callback_query.data.split('_')[1]
    
    # Check if this is search mode
    data = await state.get_data()
    
    if data.get('search_mode'):
        # Search mode: show search results for region
        listings = search_listings_by_location(region_key=region_key)
        region_name = REGIONS_DATA[user_lang][region_key]['name']
        
        if listings:
            await callback_query.message.edit_text(
                get_text(user_lang, 'location_search_results', region=region_name)
            )
            
            for listing in listings[:3]:  # Show first 3
                listing_text = format_listing_display(listing, user_lang)
                keyboard = get_listing_keyboard(listing[0], user_lang)
                
                # Try to send with photo
                photo_file_ids = json.loads(listing[15]) if listing[15] else []
                if photo_file_ids:
                    try:
                        await callback_query.message.answer_photo(
                            photo=photo_file_ids[0],
                            caption=listing_text,
                            reply_markup=keyboard
                        )
                    except:
                        await callback_query.message.answer(listing_text, reply_markup=keyboard)
                else:
                    await callback_query.message.answer(listing_text, reply_markup=keyboard)
        else:
            await callback_query.message.edit_text(
                get_text(user_lang, 'no_location_results')
            )
        
        await state.clear()
    else:
        # Listing creation mode: continue with district selection
        await state.update_data(region=region_key)
        await state.set_state(ListingStates.district)
        await callback_query.message.edit_text(
            get_text(user_lang, 'select_district'),
            reply_markup=get_districts_keyboard(region_key, user_lang)
        )
        await callback_query.answer(get_text(user_lang, 'region_selected'))

@dp.callback_query(F.data.startswith('district_'))
async def process_district_selection(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    district_key = callback_query.data.split('_')[1]
    
    # Save district
    await state.update_data(district=district_key)
    
    # Continue to address input
    await state.set_state(ListingStates.address)
    await callback_query.message.edit_text(get_text(user_lang, 'address'))
    await callback_query.answer(get_text(user_lang, 'district_selected'))

@dp.callback_query(F.data == 'back_to_regions')
async def back_to_regions(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    
    await state.set_state(ListingStates.region)
    await callback_query.message.edit_text(
        get_text(user_lang, 'select_region'),
        reply_markup=get_regions_keyboard(user_lang)
    )
    await callback_query.answer()

@dp.message(ListingStates.address)
async def process_address(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    
    # Get saved region and district
    data = await state.get_data()
    region_key = data.get('region')
    district_key = data.get('district')
    
    # Build full address with region/district
    if region_key and district_key:
        region_name = REGIONS_DATA[user_lang][region_key]['name']
        district_name = REGIONS_DATA[user_lang][region_key]['districts'][district_key]
        full_address = f"{message.text}, {district_name}, {region_name}"
    else:
        full_address = message.text
    
    await state.update_data(
        address=message.text,
        full_address=full_address
    )
    
    await state.set_state(ListingStates.price)
    await message.answer(get_text(user_lang, 'price'))

@dp.message(ListingStates.price)
async def process_price(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    try:
        price = int(message.text.replace(' ', '').replace(',', ''))
        await state.update_data(price=price)
        await state.set_state(ListingStates.area)
        await message.answer(get_text(user_lang, 'area'))
    except ValueError:
        await message.answer("Iltimos, to'g'ri narx kiriting!")

@dp.message(ListingStates.area)
async def process_area(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    try:
        area = int(message.text)
        await state.update_data(area=area)
        await state.set_state(ListingStates.rooms)
        await message.answer(get_text(user_lang, 'rooms'))
    except ValueError:
        await message.answer("Iltimos, to'g'ri maydon kiriting!")

@dp.message(ListingStates.rooms)
async def process_rooms(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    try:
        rooms = int(message.text)
        await state.update_data(rooms=rooms)
        await state.set_state(ListingStates.condition)
        await message.answer(
            get_text(user_lang, 'condition'),
            reply_markup=get_condition_keyboard(user_lang)
        )
    except ValueError:
        await message.answer("Iltimos, to'g'ri xonalar sonini kiriting!")

@dp.callback_query(F.data.startswith('condition_'))
async def process_condition(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    condition = callback_query.data.split('_')[1]
    await state.update_data(condition=condition)
    await state.set_state(ListingStates.status)
    await callback_query.message.edit_text(
        get_text(user_lang, 'status'),
        reply_markup=get_status_keyboard(user_lang)
    )
    await callback_query.answer()

@dp.callback_query(F.data.startswith('status_'))
async def process_status(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    status = callback_query.data.split('_')[1]
    await state.update_data(status=status)
    await state.set_state(ListingStates.contact_info)
    await callback_query.message.edit_text(get_text(user_lang, 'contact_info'))
    await callback_query.answer()

@dp.message(ListingStates.contact_info)
async def process_contact_info(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    await state.update_data(contact_info=message.text)
    await state.set_state(ListingStates.photos)
    
    # Create done button
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'photos_done'), callback_data="photos_done"))
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'skip'), callback_data="photos_skip"))
    
    await message.answer(
        get_text(user_lang, 'add_photos'),
        reply_markup=builder.as_markup()
    )

@dp.message(ListingStates.photos, F.photo)
async def process_photo(message: Message, state: FSMContext):
    # Store photo file_id
    data = await state.get_data()
    photo_file_ids = data.get('photo_file_ids', [])
    photo_file_ids.append(message.photo[-1].file_id)
    await state.update_data(photo_file_ids=photo_file_ids)
    
    await message.answer(f"📸 Rasm qo'shildi! Jami: {len(photo_file_ids)}")

@dp.callback_query(F.data.in_(['photos_done', 'photos_skip']))
async def finish_listing(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    data = await state.get_data()
    
    # Save listing to database
    save_listing(callback_query.from_user.id, data)
    
    await callback_query.message.edit_text(get_text(user_lang, 'listing_created'))
    await state.clear()
    await callback_query.answer()

@dp.message(F.text.in_(['👀 E\'lonlar', '👀 Объявления', '👀 Listings']))
async def view_listings_handler(message: Message):
    user_lang = get_user_language(message.from_user.id)
    listings = get_listings(limit=5)
    
    if not listings:
        await message.answer(get_text(user_lang, 'no_listings'))
        return
    
    for listing in listings:
        listing_text = format_listing_display(listing, user_lang)
        keyboard = get_listing_keyboard(listing[0], user_lang)
        
        # Try to send with photos if available
        photo_file_ids = json.loads(listing[15]) if listing[15] else []
        if photo_file_ids:
            try:
                await message.answer_photo(
                    photo=photo_file_ids[0],
                    caption=listing_text,
                    reply_markup=keyboard
                )
            except:
                await message.answer(listing_text, reply_markup=keyboard)
        else:
            await message.answer(listing_text, reply_markup=keyboard)

@dp.message(F.text.in_(['🔍 Qidiruv', '🔍 Поиск', '🔍 Search']))
async def search_handler(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    await state.set_state(SearchStates.query)
    await message.answer(get_text(user_lang, 'search_prompt'))

@dp.message(F.text.in_(['🏘 Hudud bo\'yicha', '🏘 По району', '🏘 By location']))
async def location_search_handler(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    
    await message.answer(
        get_text(user_lang, 'select_region'),
        reply_markup=get_regions_keyboard(user_lang)
    )
    
    # Set search mode flag
    await state.set_data({'search_mode': True})

@dp.message(SearchStates.query)
async def process_search(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    query = message.text
    await state.clear()
    
    listings = search_listings(query)
    
    if not listings:
        await message.answer(get_text(user_lang, 'no_listings'))
        return
    
    await message.answer(f"🔍 Qidiruv natijalari: {len(listings)} ta e'lon topildi")
    
    for listing in listings[:3]:  # Show first 3 results
        listing_text = format_listing_display(listing, user_lang)
        keyboard = get_listing_keyboard(listing[0], user_lang)
        await message.answer(listing_text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith('fav_add_'))
async def add_favorite_callback(callback_query):
    listing_id = int(callback_query.data.split('_')[2])
    user_lang = get_user_language(callback_query.from_user.id)
    
    add_to_favorites(callback_query.from_user.id, listing_id)
    await callback_query.answer(get_text(user_lang, 'added_to_favorites'))

@dp.callback_query(F.data.startswith('contact_'))
async def contact_callback(callback_query):
    listing_id = int(callback_query.data.split('_')[1])
    user_lang = get_user_language(callback_query.from_user.id)
    
    # Get listing details
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('SELECT contact_info FROM listings WHERE id = ?', (listing_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        await callback_query.answer(f"📞 Aloqa: {result[0]}", show_alert=True)
    else:
        await callback_query.answer("E'lon topilmadi")

@dp.message(F.text.in_(['❤️ Sevimlilar', '❤️ Избранное', '❤️ Favorites']))
async def favorites_handler(message: Message):
    user_lang = get_user_language(message.from_user.id)
    favorites = get_user_favorites(message.from_user.id)
    
    if not favorites:
        await message.answer(get_text(user_lang, 'no_favorites'))
        return
    
    await message.answer(f"❤️ Sevimli e'lonlar: {len(favorites)} ta")
    
    for favorite in favorites[:5]:  # Show first 5
        listing_text = format_listing_display(favorite, user_lang)
        await message.answer(listing_text)

@dp.message(F.text.in_(['ℹ️ Ma\'lumot', 'ℹ️ Информация', 'ℹ️ Info']))
async def info_handler(message: Message):
    user_lang = get_user_language(message.from_user.id)
    await message.answer(get_text(user_lang, 'about'))

# Error handler
@dp.error()
async def error_handler(event, exception):
    logger.error(f"Error occurred: {exception}")
    return True

async def main():
    # Initialize database
    init_db()
    logger.info("✅ Database initialized")
    
    logger.info("🤖 Starting bot...")
    
    try:
        # Start polling
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())