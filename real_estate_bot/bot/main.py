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
from collections import defaultdict
from asyncio import create_task, sleep

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
CHANNEL_ID = os.getenv('CHANNEL_ID', '@your_channel')
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')

# Admin configuration
ADMIN_IDS = os.getenv('ADMIN_IDS', '').split(',')
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS if admin_id.strip()]

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

# Database migration function
def migrate_database():
    """Add missing columns to existing database"""
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    
    try:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(listings)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'region' not in columns:
            cursor.execute('ALTER TABLE listings ADD COLUMN region TEXT')
            logger.info("Added region column")
            
        if 'district' not in columns:
            cursor.execute('ALTER TABLE listings ADD COLUMN district TEXT')
            logger.info("Added district column")
            
        if 'approval_status' not in columns:
            cursor.execute('ALTER TABLE listings ADD COLUMN approval_status TEXT DEFAULT "pending"')
            logger.info("Added approval_status column")
            
        if 'admin_feedback' not in columns:
            cursor.execute('ALTER TABLE listings ADD COLUMN admin_feedback TEXT')
            logger.info("Added admin_feedback column")
            
        if 'reviewed_by' not in columns:
            cursor.execute('ALTER TABLE listings ADD COLUMN reviewed_by INTEGER')
            logger.info("Added reviewed_by column")
            
        if 'channel_message_id' not in columns:
            cursor.execute('ALTER TABLE listings ADD COLUMN channel_message_id INTEGER')
            logger.info("Added channel_message_id column")
            
        conn.commit()
    except Exception as e:
        logger.error(f"Migration error: {e}")
    finally:
        conn.close()

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
    
    # Updated listings table with admin approval
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
            approval_status TEXT DEFAULT 'pending',
            admin_feedback TEXT,
            reviewed_by INTEGER,
            channel_message_id INTEGER,
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

# Enhanced translations with all languages complete
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
        'no_location_results': "😔 Bu hududda e'lonlar topilmadi.",
        # New template and admin translations
        'listing_template_shown': "Yuqoridagi namuna asosida e'loningizni yozing:",
        'is_description_complete': "E'lon tavsifi tayyor?",
        'yes_complete': "✅ Ha, tayyor",
        'add_more_info': "➕ Qo'shimcha ma'lumot qo'shish",
        'phone_number_request': "📞 Telefon raqamingizni kiriting:\n(Masalan: +998901234567)",
        'additional_info': "📝 Qo'shimcha ma'lumot kiriting:",
        'add_photos_mediagroup': "📸 Rasmlarni yuklang:\n\n💡 Bir nechta rasmni birga yuborish uchun, ularni media guruh sifatida yuboring (bir vaqtda bir nechta rasmni tanlang)\n\nYoki bitta-bitta yuborishingiz ham mumkin.",
        'photo_added_count': "📸 Rasm qo'shildi! Jami: {count} ta",
        'media_group_received': "📸 {count} ta rasm qabul qilindi!",
        'listing_submitted_for_review': "📝 E'loningiz yuborildi!\n\n⏳ Adminlar tomonidan ko'rib chiqilmoqda...\nTasdiqlangandan so'ng kanalga joylanadi.",
        'listing_approved': "✅ E'loningiz tasdiqlandi!\n\n🎉 E'loningiz kanalga joylandi va boshqa foydalanuvchilar ko'rishi mumkin.",
        'listing_declined': "❌ E'loningiz rad etildi\n\n📝 Sabab: {feedback}\n\nIltimos, kamchiklarni bartaraf etib, qaytadan yuboring.",
    },
    'ru': {
        'start': "🏠 Добро пожаловать!\n\nДобро пожаловать в бот объявлений недвижимости!\nЗдесь вы можете:\n• Размещать объявления\n• Удобно искать\n• Использовать премиум услуги",
        'choose_language': "Выберите язык:",
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
        'listing_title': "📝 Введите название объявления:",
        'listing_description': "📄 Введите описание объявления:",
        'property_type': "🏘 Выберите тип недвижимости:",
        'select_region': "🗺 Выберите область:",
        'select_district': "🏘 Выберите район:",
        'region_selected': "✅ Область выбрана",
        'district_selected': "✅ Район выбран",
        'apartment': "🏢 Квартира",
        'house': "🏠 Дом",
        'commercial': "🏪 Коммерческая",
        'land': "🌱 Земля",
        'address': "📍 Введите точный адрес:",
        'price': "💰 Введите цену (сум):",
        'area': "📐 Введите площадь (м²):",
        'rooms': "🚪 Введите количество комнат:",
        'condition': "🏗 Выберите состояние:",
        'new': "✨ Новое",
        'good': "👍 Хорошее",
        'repair_needed': "🔨 Требует ремонта",
        'status': "🎯 Выберите цель:",
        'sale': "💵 Продажа",
        'rent': "📅 Аренда",
        'contact_info': "📞 Введите контактную информацию:",
        'add_photos': "📸 Добавьте фотографии (необязательно):",
        'photos_done': "✅ Готово",
        'listing_created': "🎉 Объявление успешно создано!",
        'no_listings': "😔 Объявлений пока нет",
        'added_to_favorites': "❤️ Добавлено в избранное!",
        'removed_from_favorites': "💔 Удалено из избранного!",
        'no_favorites': "😔 Список избранного пуст",
        'contact_seller': "💬 Связаться с продавцом",
        'add_favorite': "❤️ Избранное",
        'remove_favorite': "💔 Удалить",
        'next': "Следующий ▶️",
        'previous': "◀️ Предыдущий",
        'skip': "⏭ Пропустить",
        'search_prompt': "🔍 Введите ключевое слово для поиска:",
        'about': "ℹ️ О боте:\n\nЭтот бот создан для объявлений недвижимости.\n\n👨‍💻 Разработчик: @your_username",
        'location_search_results': "🗺 Результаты по {region}:",
        'no_location_results': "😔 В этом регионе объявлений не найдено.",
        # New template and admin translations
        'listing_template_shown': "Напишите свое объявление по образцу выше:",
        'is_description_complete': "Описание объявления готово?",
        'yes_complete': "✅ Да, готово",
        'add_more_info': "➕ Добавить дополнительную информацию",
        'phone_number_request': "📞 Введите свой номер телефона:\n(Например: +998901234567)",
        'additional_info': "📝 Введите дополнительную информацию:",
        'add_photos_mediagroup': "📸 Загрузите фотографии:\n\n💡 Чтобы отправить несколько фото сразу, отправьте их как медиа-группу (выберите несколько фото одновременно)\n\nИли можете отправлять по одной.",
        'photo_added_count': "📸 Фото добавлено! Всего: {count}",
        'media_group_received': "📸 Получено {count} фотографий!",
        'listing_submitted_for_review': "📝 Ваше объявление отправлено!\n\n⏳ Рассматривается администраторами...\nПосле одобрения будет размещено в канале.",
        'listing_approved': "✅ Ваше объявление одобрено!\n\n🎉 Объявление размещено в канале и доступно другим пользователям.",
        'listing_declined': "❌ Ваше объявление отклонено\n\n📝 Причина: {feedback}\n\nПожалуйста, устраните недочеты и отправьте повторно.",
    },
    'en': {
        'start': "🏠 Welcome!\n\nWelcome to the real estate listings bot!\nHere you can:\n• Post listings\n• Search conveniently\n• Use premium services",
        'choose_language': "Choose language:",
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
        'listing_title': "📝 Enter listing title:",
        'listing_description': "📄 Enter listing description:",
        'property_type': "🏘 Select property type:",
        'select_region': "🗺 Select region:",
        'select_district': "🏘 Select district:",
        'region_selected': "✅ Region selected",
        'district_selected': "✅ District selected",
        'apartment': "🏢 Apartment",
        'house': "🏠 House",
        'commercial': "🏪 Commercial",
        'land': "🌱 Land",
        'address': "📍 Enter exact address:",
        'price': "💰 Enter price (UZS):",
        'area': "📐 Enter area (m²):",
        'rooms': "🚪 Enter number of rooms:",
        'condition': "🏗 Select condition:",
        'new': "✨ New",
        'good': "👍 Good",
        'repair_needed': "🔨 Needs repair",
        'status': "🎯 Select purpose:",
        'sale': "💵 Sale",
        'rent': "📅 Rent",
        'contact_info': "📞 Enter contact information:",
        'add_photos': "📸 Add photos (optional):",
        'photos_done': "✅ Done",
        'listing_created': "🎉 Listing created successfully!",
        'no_listings': "😔 No listings yet",
        'added_to_favorites': "❤️ Added to favorites!",
        'removed_from_favorites': "💔 Removed from favorites!",
        'no_favorites': "😔 Favorites list is empty",
        'contact_seller': "💬 Contact seller",
        'add_favorite': "❤️ Favorites",
        'remove_favorite': "💔 Remove",
        'next': "Next ▶️",
        'previous': "◀️ Previous",
        'skip': "⏭ Skip",
        'search_prompt': "🔍 Enter keyword to search:",
        'about': "ℹ️ About bot:\n\nThis bot is created for real estate listings.\n\n👨‍💻 Developer: @your_username",
        'location_search_results': "🗺 Results for {region}:",
        'no_location_results': "😔 No listings found in this region.",
        # New template and admin translations
        'listing_template_shown': "Write your listing based on the template above:",
        'is_description_complete': "Is the listing description complete?",
        'yes_complete': "✅ Yes, complete",
        'add_more_info': "➕ Add additional information",
        'phone_number_request': "📞 Enter your phone number:\n(Example: +998901234567)",
        'additional_info': "📝 Enter additional information:",
        'add_photos_mediagroup': "📸 Upload photos:\n\n💡 To send multiple photos at once, send them as a media group (select multiple photos at the same time)\n\nOr you can send them one by one.",
        'photo_added_count': "📸 Photo added! Total: {count}",
        'media_group_received': "📸 Received {count} photos!",
        'listing_submitted_for_review': "📝 Your listing has been submitted!\n\n⏳ Being reviewed by administrators...\nWill be posted to channel after approval.",
        'listing_approved': "✅ Your listing has been approved!\n\n🎉 Your listing is now posted to the channel and visible to other users.",
        'listing_declined': "❌ Your listing has been declined\n\n📝 Reason: {feedback}\n\nPlease fix the issues and resubmit.",
    }
}

# FSM States for new listing flow with admin approval
class ListingStates(StatesGroup):
    property_type = State()      # First: Property type
    status = State()             # Second: Purpose (sale/rent)
    region = State()             # Third: Region
    district = State()           # Fourth: District
    description = State()        # Fifth: Description based on template
    confirmation = State()       # Sixth: "Is that all?" confirmation
    contact_info = State()       # Seventh: Phone number
    photos = State()             # Eighth: Photos

class SearchStates(StatesGroup):
    query = State()
    location_search = State()

class AdminStates(StatesGroup):
    reviewing_listing = State()
    writing_feedback = State()

# Media group collector for handling multiple photos
class MediaGroupCollector:
    def __init__(self):
        self.groups = defaultdict(list)
        self.timers = {}
    
    async def add_message(self, message: Message, state: FSMContext):
        if not message.media_group_id:
            # Single photo
            return await self.process_single_photo(message, state)
        
        # Add to group
        self.groups[message.media_group_id].append(message)
        
        # Cancel existing timer
        if message.media_group_id in self.timers:
            self.timers[message.media_group_id].cancel()
        
        # Set new timer to process group after 1 second of no new messages
        self.timers[message.media_group_id] = create_task(
            self.process_group_after_delay(message.media_group_id, state)
        )
    
    async def process_group_after_delay(self, group_id: str, state: FSMContext):
        await sleep(1.0)  # Wait 1 second for all photos in group
        
        if group_id in self.groups:
            messages = self.groups[group_id]
            await self.process_media_group(messages, state)
            
            # Clean up
            del self.groups[group_id]
            if group_id in self.timers:
                del self.timers[group_id]
    
    async def process_single_photo(self, message: Message, state: FSMContext):
        user_lang = get_user_language(message.from_user.id)
        
        data = await state.get_data()
        photo_file_ids = data.get('photo_file_ids', [])
        photo_file_ids.append(message.photo[-1].file_id)
        await state.update_data(photo_file_ids=photo_file_ids)
        
        await message.answer(
            get_text(user_lang, 'photo_added_count', count=len(photo_file_ids))
        )
    
    async def process_media_group(self, messages: list, state: FSMContext):
        user_lang = get_user_language(messages[0].from_user.id)
        
        data = await state.get_data()
        photo_file_ids = data.get('photo_file_ids', [])
        
        # Add all photos from the media group
        for msg in messages:
            if msg.photo:
                photo_file_ids.append(msg.photo[-1].file_id)
        
        await state.update_data(photo_file_ids=photo_file_ids)
        
        await messages[0].answer(
            get_text(user_lang, 'media_group_received', count=len(messages))
        )

# Initialize media collector
media_collector = MediaGroupCollector()

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

# Admin helper functions
def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in ADMIN_IDS

def get_listing_by_id(listing_id: int):
    """Get listing details by ID"""
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l.*, u.first_name, u.username 
        FROM listings l 
        JOIN users u ON l.user_id = u.telegram_id 
        WHERE l.id = ?
    ''', (listing_id,))
    listing = cursor.fetchone()
    conn.close()
    return listing

def update_listing_approval(listing_id: int, status: str, admin_id: int, feedback: str = None):
    """Update listing approval status"""
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE listings 
        SET approval_status = ?, reviewed_by = ?, admin_feedback = ?
        WHERE id = ?
    ''', (status, admin_id, feedback, listing_id))
    conn.commit()
    conn.close()

def get_pending_listings():
    """Get all pending listings for admin review"""
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l.*, u.first_name, u.username 
        FROM listings l 
        JOIN users u ON l.user_id = u.telegram_id 
        WHERE l.approval_status = "pending"
        ORDER BY l.created_at ASC
    ''', )
    listings = cursor.fetchall()
    conn.close()
    return listings

def format_listing_for_admin(listing) -> str:
    """Format listing for admin review"""
    location = listing[8] if listing[8] else "Manzil ko'rsatilmagan"
    
    return f"""
🆔 <b>E'lon #{listing[0]}</b>
👤 <b>Foydalanuvchi:</b> {listing[18]} (@{listing[19] or 'username_yoq'})
🏘 <b>Tur:</b> {listing[4]}
🎯 <b>Maqsad:</b> {listing[12]}
🗺 <b>Manzil:</b> {location}
📞 <b>Aloqa:</b> {listing[14]}

<b>📝 Tavsif:</b>
{listing[3]}

⏰ <b>Vaqt:</b> {listing[21]}
"""

def get_admin_review_keyboard(listing_id: int) -> InlineKeyboardMarkup:
    """Create admin review keyboard"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_{listing_id}"))
    builder.add(InlineKeyboardButton(text="❌ Rad etish", callback_data=f"decline_{listing_id}"))
    builder.add(InlineKeyboardButton(text="📋 Barcha kutilayotganlar", callback_data="pending_all"))
    builder.adjust(2, 1)
    return builder.as_markup()

def get_listing_template(user_lang: str, status: str, property_type: str) -> str:
    """Generate template based on property type and status"""
    
    if user_lang == 'uz':
        if status == 'rent':
            return """
E'lon mazmunini yozing.
Shu namuna asosida e'loningizni yozing!

🏠 KVARTIRA IJARAGA BERILADI
📍 Shahar, Tuman 5-kvartal
💰 Narxi: 300$–400$
🛏 Xonalar: 2 xonali
♨️ Kommunal: gaz, suv, svet bor
🪚 Holati: yevro remont yoki o'rtacha
🛋 Jihoz: jihozli yoki jihozsiz
🕒 Muddat: qisqa yoki uzoq muddatga
👥 Kimga: Shariy nikohga / oilaga / studentlarga

🔴 Eslatma
Ma'lumotlar qatorida tel raqamingizni bot so'ramaguncha yozmang, aks holda sizni telingiz jiringlashdan to'xtamaydi va biz siz yuborgan xabarni botdan o'chirib tashlash imkonsiz
"""
        else:  # sale
            return """
E'lon mazmunini yozing.
Shu namuna asosida e'loningizni yozing!

🏠 UY-JOY SOTILADI 
📍 Shahar, Tuman
💰 Narxi: 50,000$–80,000$
🛏 Xonalar: 3 xonali
📐 Maydon: 65 m²
♨️ Kommunal: gaz, suv, svet bor
🪚 Holati: yevro remont yoki o'rtacha
🛋 Jihoz: jihozli yoki jihozsiz
🏢 Qavat: 3/9

🔴 Eslatma
Ma'lumotlar qatorida tel raqamingizni bot so'ramaguncha yozmang, aks holda sizni telingiz jiringlashdan to'xtamaydi va biz siz yuborgan xabarni botdan o'chirib tashlash imkonsiz
"""
    elif user_lang == 'ru':
        if status == 'rent':
            return """
Напишите содержание объявления.
Пишите свое объявление по этому образцу!

🏠 КВАРТИРА СДАЕТСЯ В АРЕНДУ
📍 Город, Район 5-квартал
💰 Цена: 300$–400$
🛏 Комнаты: 2-комнатная
♨️ Коммунальные: газ, вода, свет есть
🪚 Состояние: евроремонт или среднее
🛋 Мебель: с мебелью или без мебели
🕒 Срок: краткосрочно или долгосрочно
👥 Для кого: для гражданского брака / для семьи / для студентов

🔴 Примечание
Не пишите свой номер телефона в тексте, пока бот не попросит, иначе ваш телефон не перестанет звонить и мы не сможем удалить ваше сообщение из бота
"""
        else:  # sale
            return """
Напишите содержание объявления.
Пишите свое объявление по этому образцу!

🏠 ПРОДАЕТСЯ НЕДВИЖИМОСТЬ
📍 Город, Район
💰 Цена: 50,000$–80,000$
🛏 Комнаты: 3-комнатная
📐 Площадь: 65 м²
♨️ Коммунальные: газ, вода, свет есть
🪚 Состояние: евроремонт или среднее
🛋 Мебель: с мебелью или без мебели
🏢 Этаж: 3/9

🔴 Примечание
Не пишите свой номер телефона в тексте, пока бот не попросит, иначе ваш телефон не перестанет звонить и мы не сможем удалить ваше сообщение из бота
"""
    else:  # English
        if status == 'rent':
            return """
Write the content of the listing.
Write your listing based on this template!

🏠 APARTMENT FOR RENT
📍 City, District 5th Quarter
💰 Price: $300–$400
🛏 Rooms: 2-room
♨️ Utilities: gas, water, electricity available
🪚 Condition: euro renovation or average
🛋 Furniture: furnished or unfurnished
🕒 Period: short-term or long-term
👥 For whom: for civil marriage / for family / for students

🔴 Note
Do not write your phone number in the text until the bot asks for it, otherwise your phone will not stop ringing and we cannot delete your message from the bot
"""
        else:  # sale
            return """
Write the content of the listing.
Write your listing based on this template!

🏠 PROPERTY FOR SALE
📍 City, District
💰 Price: $50,000–$80,000
🛏 Rooms: 3-room
📐 Area: 65 m²
♨️ Utilities: gas, water, electricity available
🪚 Condition: euro renovation or average
🛋 Furniture: furnished or unfurnished
🏢 Floor: 3/9

🔴 Note
Do not write your phone number in the text until the bot asks for it, otherwise your phone will not stop ringing and we cannot delete your message from the bot
"""

def format_listing_for_channel(listing) -> str:
    """Format listing for channel posting"""
    location = listing[8] if listing[8] else "Manzil ko'rsatilmagan"
    
    return f"""
{listing[3]}

📞 Aloqa: {listing[14]}
🗺 Manzil: {location}

#{listing[4]} #{listing[12]}
"""

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
    
    if user_lang == 'uz':
        builder.add(InlineKeyboardButton(text="🏙 Toshkent shahri", callback_data="region_tashkent_city"))
        builder.add(InlineKeyboardButton(text="🌄 Toshkent viloyati", callback_data="region_tashkent_region"))
        builder.add(InlineKeyboardButton(text="🏛 Samarqand viloyati", callback_data="region_samarkand"))
    elif user_lang == 'ru':
        builder.add(InlineKeyboardButton(text="🏙 Город Ташкент", callback_data="region_tashkent_city"))
        builder.add(InlineKeyboardButton(text="🌄 Ташкентская область", callback_data="region_tashkent_region"))
        builder.add(InlineKeyboardButton(text="🏛 Самаркандская область", callback_data="region_samarkand"))
    else:  # English
        builder.add(InlineKeyboardButton(text="🏙 Tashkent City", callback_data="region_tashkent_city"))
        builder.add(InlineKeyboardButton(text="🌄 Tashkent Region", callback_data="region_tashkent_region"))
        builder.add(InlineKeyboardButton(text="🏛 Samarkand Region", callback_data="region_samarkand"))
    
    builder.adjust(1)
    return builder.as_markup()

def get_districts_keyboard(region_key: str, user_lang: str) -> InlineKeyboardMarkup:
    """Create keyboard with districts for selected region"""
    builder = InlineKeyboardBuilder()
    
    try:
        districts = REGIONS_DATA[user_lang][region_key]['districts']
        
        for district_key, district_name in districts.items():
            builder.add(InlineKeyboardButton(
                text=district_name,
                callback_data=f"district_{district_key}"
            ))
        
        builder.add(InlineKeyboardButton(
            text=get_text(user_lang, 'back'),
            callback_data="back_to_regions"
        ))
        
        builder.adjust(2, 2, 2, 2, 2, 1)
        return builder.as_markup()
        
    except KeyError:
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
            contact_info, photo_file_ids, approval_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, data.get('title', ''), data['description'], data['property_type'],
        data.get('region'), data.get('district'), data.get('address', ''), 
        data.get('full_address', ''), data.get('price', 0), data.get('area', 0), 
        data.get('rooms', 0), data.get('condition', ''), data['status'], 
        data['contact_info'], photo_file_ids, 'pending'
    ))
    
    listing_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return listing_id

def get_listings(limit=10, offset=0):
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l.*, u.first_name, u.username 
        FROM listings l 
        JOIN users u ON l.user_id = u.telegram_id 
        WHERE l.approval_status = "approved"
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
        AND l.approval_status = "approved"
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
        WHERE l.approval_status = "approved"
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
        WHERE f.user_id = ? AND l.approval_status = "approved"
        ORDER BY f.created_at DESC
    ''', (user_id,))
    favorites = cursor.fetchall()
    conn.close()
    return favorites

def format_listing_display(listing, user_lang):
    """Format listing for display with region/district info"""
    location_display = listing[8] if listing[8] else listing[7]
    
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

async def post_to_channel(listing):
    """Post approved listing to channel"""
    try:
        channel_text = format_listing_for_channel(listing)
        photo_file_ids = json.loads(listing[15]) if listing[15] else []
        
        if photo_file_ids:
            if len(photo_file_ids) == 1:
                message = await bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=photo_file_ids[0],
                    caption=channel_text
                )
            else:
                media_group = MediaGroupBuilder(caption=channel_text)
                for photo_id in photo_file_ids[:10]:
                    media_group.add_photo(media=photo_id)
                
                messages = await bot.send_media_group(chat_id=CHANNEL_ID, media=media_group.build())
                message = messages[0]
        else:
            message = await bot.send_message(
                chat_id=CHANNEL_ID,
                text=channel_text
            )
        
        # Save channel message ID
        conn = sqlite3.connect('real_estate.db')
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE listings SET channel_message_id = ? WHERE id = ?',
            (message.message_id, listing[0])
        )
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error posting to channel: {e}")

async def send_to_admins_for_review(listing_id: int):
    """Send listing to all admins for review"""
    listing = get_listing_by_id(listing_id)
    if not listing:
        return
    
    admin_text = format_listing_for_admin(listing)
    keyboard = get_admin_review_keyboard(listing_id)
    
    for admin_id in ADMIN_IDS:
        try:
            photo_file_ids = json.loads(listing[15]) if listing[15] else []
            
            if photo_file_ids:
                if len(photo_file_ids) == 1:
                    await bot.send_photo(
                        chat_id=admin_id,
                        photo=photo_file_ids[0],
                        caption=admin_text,
                        reply_markup=keyboard
                    )
                else:
                    media_group = MediaGroupBuilder(caption=admin_text)
                    for photo_id in photo_file_ids[:10]:
                        media_group.add_photo(media=photo_id)
                    
                    await bot.send_media_group(chat_id=admin_id, media=media_group.build())
                    await bot.send_message(
                        chat_id=admin_id,
                        text="👆 Yuqoridagi e'lonni ko'rib chiqing:",
                        reply_markup=keyboard
                    )
            else:
                await bot.send_message(
                    chat_id=admin_id,
                    text=admin_text,
                    reply_markup=keyboard
                )
        except Exception as e:
            logger.error(f"Error sending to admin {admin_id}: {e}")

async def notify_user_approval(user_id: int, approved: bool, feedback: str = None):
    """Notify user about listing approval/decline"""
    user_lang = get_user_language(user_id)
    
    try:
        if approved:
            message = get_text(user_lang, 'listing_approved')
        else:
            message = get_text(user_lang, 'listing_declined', feedback=feedback or "Sabab ko'rsatilmagan")
        
        await bot.send_message(chat_id=user_id, text=message)
    except Exception as e:
        logger.error(f"Error notifying user {user_id}: {e}")

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
    
    await callback_query.answer(f"Language changed!")
    
    await callback_query.message.answer(
        get_text(lang, 'main_menu'),
        reply_markup=get_main_menu_keyboard(lang)
    )

# NEW LISTING FLOW HANDLERS
@dp.message(F.text.in_(['📝 E\'lon joylash', '📝 Разместить объявление', '📝 Post listing']))
async def post_listing_handler(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    
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
    
    await state.set_state(ListingStates.region)
    await callback_query.message.edit_text(
        get_text(user_lang, 'select_region'),
        reply_markup=get_regions_keyboard(user_lang)
    )
    await callback_query.answer()

@dp.callback_query(F.data.startswith('region_'))
async def process_region_selection(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    
    # FIX: Extract region key properly (everything after 'region_')
    region_key = callback_query.data[7:]  # Remove 'region_' prefix
    
    # Check if region exists
    if region_key not in REGIONS_DATA.get(user_lang, {}):
        await callback_query.answer("Region not found!")
        return
    
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
    
    await state.update_data(district=district_key)
    
    # Show template and ask for description
    data = await state.get_data()
    property_type = data.get('property_type')
    status = data.get('status')
    
    template = get_listing_template(user_lang, status, property_type)
    
    await state.set_state(ListingStates.description)
    await callback_query.message.edit_text(template)
    
    await callback_query.message.answer(get_text(user_lang, 'listing_template_shown'))
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

@dp.message(ListingStates.description)
async def process_description(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    await state.update_data(description=message.text)
    
    # Ask for confirmation with Yes/Add more options
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text=get_text(user_lang, 'yes_complete'), 
        callback_data="desc_complete"
    ))
    builder.add(InlineKeyboardButton(
        text=get_text(user_lang, 'add_more_info'), 
        callback_data="desc_add_more"
    ))
    builder.adjust(1)
    
    await state.set_state(ListingStates.confirmation)
    await message.answer(
        get_text(user_lang, 'is_description_complete'),
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == 'desc_complete')
async def description_complete(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    
    await state.set_state(ListingStates.contact_info)
    await callback_query.message.edit_text(get_text(user_lang, 'phone_number_request'))
    await callback_query.answer()

@dp.callback_query(F.data == 'desc_add_more')
async def description_add_more(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    
    await state.set_state(ListingStates.description)
    await callback_query.message.edit_text(get_text(user_lang, 'additional_info'))
    await callback_query.answer()

@dp.message(ListingStates.contact_info)
async def process_contact_info(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    await state.update_data(contact_info=message.text)
    
    await state.set_state(ListingStates.photos)
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'photos_done'), callback_data="photos_done"))
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'skip'), callback_data="photos_skip"))
    
    await message.answer(
        get_text(user_lang, 'add_photos_mediagroup'),
        reply_markup=builder.as_markup()
    )

@dp.message(ListingStates.photos, F.photo)
async def process_photo_with_collector(message: Message, state: FSMContext):
    """Handle both single photos and media groups using collector"""
    await media_collector.add_message(message, state)

@dp.callback_query(F.data.in_(['photos_done', 'photos_skip']))
async def finish_listing(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    data = await state.get_data()
    
    # Build full address
    region_key = data.get('region')
    district_key = data.get('district')
    
    if region_key and district_key:
        region_name = REGIONS_DATA[user_lang][region_key]['name']
        district_name = REGIONS_DATA[user_lang][region_key]['districts'][district_key]
        full_address = f"{district_name}, {region_name}"
        data['full_address'] = full_address
        data['address'] = full_address
    
    # Create title from description (first line or first 50 chars)
    description = data.get('description', '')
    title = description.split('\n')[0][:50] + ('...' if len(description) > 50 else '')
    data['title'] = title
    
    # Save listing to database (status: pending)
    listing_id = save_listing(callback_query.from_user.id, data)
    
    # Notify user that listing is submitted for review
    await callback_query.message.edit_text(get_text(user_lang, 'listing_submitted_for_review'))
    
    # Send to admins for approval
    await send_to_admins_for_review(listing_id)
    
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
        
        photo_file_ids = json.loads(listing[15]) if listing[15] else []
        
        if photo_file_ids:
            try:
                if len(photo_file_ids) == 1:
                    await message.answer_photo(
                        photo=photo_file_ids[0],
                        caption=listing_text,
                        reply_markup=keyboard
                    )
                else:
                    media_group = MediaGroupBuilder(caption=listing_text)
                    for i, photo_id in enumerate(photo_file_ids[:10]):
                        if i == 0:
                            media_group.add_photo(media=photo_id)
                        else:
                            media_group.add_photo(media=photo_id)
                    
                    await message.answer_media_group(media=media_group.build())
                    await message.answer("👆 E'lon ma'lumotlari", reply_markup=keyboard)
                    
            except Exception as e:
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
    
    await state.set_state(SearchStates.location_search)
    await message.answer(
        get_text(user_lang, 'select_region'),
        reply_markup=get_regions_keyboard(user_lang)
    )

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
    
    for listing in listings[:3]:
        listing_text = format_listing_display(listing, user_lang)
        keyboard = get_listing_keyboard(listing[0], user_lang)
        
        photo_file_ids = json.loads(listing[15]) if listing[15] else []
        
        if photo_file_ids:
            try:
                if len(photo_file_ids) == 1:
                    await message.answer_photo(
                        photo=photo_file_ids[0],
                        caption=listing_text,
                        reply_markup=keyboard
                    )
                else:
                    media_group = MediaGroupBuilder(caption=listing_text)
                    for i, photo_id in enumerate(photo_file_ids[:5]):
                        media_group.add_photo(media=photo_id)
                    
                    await message.answer_media_group(media=media_group.build())
                    await message.answer("👆 E'lon ma'lumotlari", reply_markup=keyboard)
            except:
                await message.answer(listing_text, reply_markup=keyboard)
        else:
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
    
    for favorite in favorites[:5]:
        listing_text = format_listing_display(favorite, user_lang)
        
        photo_file_ids = json.loads(favorite[15]) if favorite[15] else []
        if photo_file_ids:
            try:
                if len(photo_file_ids) == 1:
                    await message.answer_photo(
                        photo=photo_file_ids[0],
                        caption=listing_text
                    )
                else:
                    media_group = MediaGroupBuilder(caption=listing_text)
                    for photo_id in photo_file_ids[:5]:
                        media_group.add_photo(media=photo_id)
                    
                    await message.answer_media_group(media=media_group.build())
            except:
                await message.answer(listing_text)
        else:
            await message.answer(listing_text)

@dp.message(F.text.in_(['ℹ️ Ma\'lumot', 'ℹ️ Информация', 'ℹ️ Info']))
async def info_handler(message: Message):
    user_lang = get_user_language(message.from_user.id)
    await message.answer(get_text(user_lang, 'about'))

# ADMIN HANDLERS
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Sizda admin huquqlari yo'q!")
        return
    
    pending_listings = get_pending_listings()
    
    if not pending_listings:
        await message.answer("✅ Hamma e'lonlar ko'rib chiqilgan!")
        return
    
    await message.answer(f"📋 Kutilayotgan e'lonlar: {len(pending_listings)} ta")
    
    if pending_listings:
        listing = pending_listings[0]
        admin_text = format_listing_for_admin(listing)
        keyboard = get_admin_review_keyboard(listing[0])
        
        photo_file_ids = json.loads(listing[15]) if listing[15] else []
        
        if photo_file_ids:
            if len(photo_file_ids) == 1:
                await message.answer_photo(
                    photo=photo_file_ids[0],
                    caption=admin_text,
                    reply_markup=keyboard
                )
            else:
                media_group = MediaGroupBuilder(caption=admin_text)
                for photo_id in photo_file_ids[:10]:
                    media_group.add_photo(media=photo_id)
                
                await message.answer_media_group(media=media_group.build())
                await message.answer(
                    text="👆 E'lonni ko'rib chiqing:",
                    reply_markup=keyboard
                )
        else:
            await message.answer(admin_text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith('approve_'))
async def approve_listing(callback_query, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⛔ Sizda admin huquqlari yo'q!")
        return
    
    listing_id = int(callback_query.data.split('_')[1])
    
    update_listing_approval(listing_id, 'approved', callback_query.from_user.id)
    
    listing = get_listing_by_id(listing_id)
    if not listing:
        await callback_query.answer("E'lon topilmadi!")
        return
    
    await post_to_channel(listing)
    await notify_user_approval(listing[1], True)
    
    await callback_query.message.edit_text(
        f"✅ E'lon #{listing_id} tasdiqlandi va kanalga yuborildi!"
    )
    await callback_query.answer("✅ E'lon tasdiqlandi!")

@dp.callback_query(F.data.startswith('decline_'))
async def decline_listing(callback_query, state: FSMContext):
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⛔ Sizda admin huquqlari yo'q!")
        return
    
    listing_id = int(callback_query.data.split('_')[1])
    
    await state.set_state(AdminStates.writing_feedback)
    await state.update_data(listing_id=listing_id)
    
    await callback_query.message.edit_text(
        f"❌ E'lon #{listing_id} rad etish sababi:\n\nFikr-mulohaza yozing:"
    )
    await callback_query.answer()

@dp.message(AdminStates.writing_feedback)
async def process_admin_feedback(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    listing_id = data.get('listing_id')
    feedback = message.text
    
    update_listing_approval(listing_id, 'declined', message.from_user.id, feedback)
    
    listing = get_listing_by_id(listing_id)
    if listing:
        await notify_user_approval(listing[1], False, feedback)
    
    await message.answer(f"❌ E'lon #{listing_id} rad etildi va foydalanuvchiga xabar yuborildi!")
    await state.clear()

# Error handler
@dp.error()
async def error_handler(update, exception):
    logger.error(f"Error occurred: {exception}")
    return True

async def main():
    # Run database migration first
    migrate_database()
    
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