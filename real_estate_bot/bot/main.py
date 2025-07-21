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
import asyncpg
from collections import defaultdict
from asyncio import create_task, sleep
from utils.translations import REGIONS_DATA, TRANSLATIONS, regions_config
from utils.templates import get_listing_template

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
CHANNEL_ID = os.getenv('CHANNEL_ID', '@your_channel')
API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password'),
    'database': os.getenv('DB_NAME', 'real_estate_db')
}

# Admin configuration
ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '')
ADMIN_IDS = []

if ADMIN_IDS_STR:
    try:
        # Split by comma and convert to integers, handle any whitespace
        raw_ids = [admin_id.strip() for admin_id in ADMIN_IDS_STR.split(',') if admin_id.strip()]
        ADMIN_IDS = [int(admin_id) for admin_id in raw_ids]
        logger.info(f"✅ Successfully parsed ADMIN_IDS: {ADMIN_IDS}")
        
        # Validate each ID
        for admin_id in ADMIN_IDS:
            if admin_id <= 0:
                logger.warning(f"⚠️ Invalid admin ID: {admin_id}")
            else:
                logger.info(f"   Admin ID: {admin_id}")
                
    except ValueError as e:
        logger.error(f"❌ Error parsing ADMIN_IDS: {e}")
        logger.error(f"❌ ADMIN_IDS string was: '{ADMIN_IDS_STR}'")
        logger.error("❌ Please check your .env file format: ADMIN_IDS=1234567890,0987654321")
        ADMIN_IDS = []
else:
    logger.warning("⚠️ ADMIN_IDS not set in environment variables")
    logger.warning("⚠️ No admin access will be available!")

if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
    logger.error("❌ Please set BOT_TOKEN in .env file!")
    exit(1)

if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
    logger.error("❌ Please set BOT_TOKEN in .env file!")
    exit(1)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Database connection pool
db_pool = None

async def init_db_pool():
    """Initialize database connection pool"""
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            database=DB_CONFIG['database'],
            min_size=10,
            max_size=20,
            command_timeout=60
        )
        logger.info("✅ Database pool initialized")
        return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False

async def close_db_pool():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database pool closed")

# Database operations with PostgreSQL
# Database operations with PostgreSQL
async def save_user(user_id: int, username: str, first_name: str, last_name: str, language: str = 'uz'):
    """Save or update user in database"""
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO real_estate_telegramuser (
                telegram_id, username, first_name, last_name, language, 
                is_blocked, balance, created_at, updated_at, is_premium
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW(), $8)
            ON CONFLICT (telegram_id) 
            DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                updated_at = NOW()
        ''', user_id, username or '', first_name or '', last_name or '', language, False, 0.00, False)

async def get_user_language(user_id: int) -> str:
    """Get user language preference"""
    async with db_pool.acquire() as conn:
        result = await conn.fetchval(
            'SELECT language FROM real_estate_telegramuser WHERE telegram_id = $1', 
            user_id
        )
        return result if result else 'uz'

async def update_user_language(user_id: int, language: str):
    """Update user language"""
    async with db_pool.acquire() as conn:
        await conn.execute(
            'UPDATE real_estate_telegramuser SET language = $1, updated_at = NOW() WHERE telegram_id = $2',
            language, user_id
        )

async def save_listing(user_id: int, data: dict) -> int:
    """Save listing to database with proper handling of all required fields"""
    async with db_pool.acquire() as conn:
        # Get user database ID
        user_db_id = await conn.fetchval(
            'SELECT id FROM real_estate_telegramuser WHERE telegram_id = $1',
            user_id
        )
        
        if not user_db_id:
            raise Exception("User not found in database")
        
        # Prepare all required fields with proper defaults
        photo_file_ids = json.dumps(data.get('photo_file_ids', []))
        
        # Ensure title is not None - create from description if needed
        title = data.get('title')
        if not title:
            description = data.get('description', 'No description')
            # Take first line or first 50 characters as title
            title = description.split('\n')[0][:50] + ('...' if len(description) > 50 else '')
        
        # Ensure all required fields have proper values
        description = data.get('description', 'No description')
        property_type = data.get('property_type', 'apartment')
        region = data.get('region', '')
        district = data.get('district', '')
        address = data.get('address', '')
        full_address = data.get('full_address', '')
        price = data.get('price', 0)
        area = data.get('area', 0)
        rooms = data.get('rooms', 0)
        condition = data.get('condition', '')
        status = data.get('status', 'sale')
        contact_info = data.get('contact_info', '')
        
        try:
            # Insert with all required fields properly set
            listing_id = await conn.fetchval('''
                INSERT INTO real_estate_property (
                    user_id, title, description, property_type, region, district,
                    address, full_address, price, area, rooms, condition, status, 
                    contact_info, photo_file_ids, is_premium, is_approved, is_active,
                    views_count, admin_notes, approval_status, favorites_count,
                    posted_to_channel, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                    $16, $17, $18, $19, $20, $21, $22, $23, NOW(), NOW()
                )
                RETURNING id
            ''', 
                user_db_id,                           # user_id
                title,                                # title (now guaranteed not null)
                description,                          # description
                property_type,                        # property_type
                region,                               # region
                district,                             # district
                address,                              # address
                full_address,                         # full_address
                price,                                # price
                area,                                 # area
                rooms,                                # rooms
                condition,                            # condition
                status,                               # status
                contact_info,                         # contact_info
                photo_file_ids,                       # photo_file_ids
                False,                                # is_premium
                False,                                # is_approved
                True,                                 # is_active
                0,                                    # views_count
                '',                                   # admin_notes
                'pending',                            # approval_status
                0,                                    # favorites_count
                False                                 # posted_to_channel (set to False initially)
            )
            
            logger.info(f"Successfully saved listing {listing_id} for user {user_id}")
            return listing_id
            
        except Exception as e:
            logger.error(f"Failed to save listing: {e}")
            logger.error(f"Data being saved: {data}")
            
            # Let's also check what the actual table schema expects
            try:
                # Get column info to better understand requirements
                columns = await conn.fetch("""
                    SELECT 
                        column_name, 
                        data_type, 
                        is_nullable, 
                        column_default
                    FROM information_schema.columns 
                    WHERE table_name = 'real_estate_property' 
                    AND table_schema = 'public'
                    AND is_nullable = 'NO'
                    AND column_default IS NULL
                    ORDER BY ordinal_position
                """)
                
                required_fields = [col['column_name'] for col in columns]
                logger.error(f"Required fields without defaults: {required_fields}")
                
            except Exception as schema_error:
                logger.error(f"Could not fetch schema info: {schema_error}")
            
            raise Exception(f"Could not save listing. Database error: {str(e)}")



# Also add this to your error handler to get better debugging info
async def save_listing_with_debug(user_id: int, data: dict) -> int:
    """Save listing with detailed error information"""
    async with db_pool.acquire() as conn:
        user_db_id = await conn.fetchval(
            'SELECT id FROM real_estate_telegramuser WHERE telegram_id = $1',
            user_id
        )
        
        if not user_db_id:
            raise Exception("User not found in database")
        
        # Let's see what fields exist and what's required
        try:
            # First check what the table looks like
            await debug_table_schema()
            
            # Try the save
            return await save_listing(user_id, data)
            
        except Exception as e:
            logger.error(f"Save listing error: {e}")
            logger.error(f"Data being saved: {data}")
            raise
async def get_listings(limit=10, offset=0):
    """Get approved listings"""
    async with db_pool.acquire() as conn:
        return await conn.fetch('''
            SELECT p.*, u.first_name, u.username 
            FROM real_estate_property p 
            JOIN real_estate_telegramuser u ON p.user_id = u.id 
            WHERE p.is_approved = true AND p.is_active = true
            ORDER BY p.is_premium DESC, p.created_at DESC 
            LIMIT $1 OFFSET $2
        ''', limit, offset)

async def search_listings(query: str):
    """Search listings by keyword"""
    async with db_pool.acquire() as conn:
        return await conn.fetch('''
            SELECT p.*, u.first_name, u.username 
            FROM real_estate_property p 
            JOIN real_estate_telegramuser u ON p.user_id = u.id 
            WHERE (p.title ILIKE $1 OR p.description ILIKE $1 OR p.full_address ILIKE $1) 
            AND p.is_approved = true AND p.is_active = true
            ORDER BY p.is_premium DESC, p.created_at DESC 
            LIMIT 10
        ''', f'%{query}%')

async def search_listings_by_location(region_key=None, district_key=None):
    """Search listings by region and/or district"""
    async with db_pool.acquire() as conn:
        query = '''
            SELECT p.*, u.first_name, u.username 
            FROM real_estate_property p 
            JOIN real_estate_telegramuser u ON p.user_id = u.id 
            WHERE p.is_approved = true AND p.is_active = true
        '''
        params = []
        param_count = 0
        
        if region_key:
            param_count += 1
            query += f' AND p.region = ${param_count}'
            params.append(region_key)
        
        if district_key:
            param_count += 1
            query += f' AND p.district = ${param_count}'
            params.append(district_key)
        
        query += ' ORDER BY p.is_premium DESC, p.created_at DESC LIMIT 10'
        
        return await conn.fetch(query, *params)

async def get_listing_by_id(listing_id: int):
    """Get listing by ID with user info"""
    async with db_pool.acquire() as conn:
        return await conn.fetchrow('''
            SELECT p.*, u.first_name, u.username 
            FROM real_estate_property p 
            JOIN real_estate_telegramuser u ON p.user_id = u.id 
            WHERE p.id = $1
        ''', listing_id)

async def add_to_favorites(user_id: int, listing_id: int):
    """Add listing to user's favorites"""
    async with db_pool.acquire() as conn:
        # Get user database ID
        user_db_id = await conn.fetchval(
            'SELECT id FROM real_estate_telegramuser WHERE telegram_id = $1',
            user_id
        )
        
        if user_db_id:
            await conn.execute('''
                INSERT INTO real_estate_favorite (user_id, property_id, created_at) 
                VALUES ($1, $2, NOW())
                ON CONFLICT (user_id, property_id) DO NOTHING
            ''', user_db_id, listing_id)

async def get_user_favorites(user_id: int):
    """Get user's favorite listings"""
    async with db_pool.acquire() as conn:
        # Get user database ID
        user_db_id = await conn.fetchval(
            'SELECT id FROM real_estate_telegramuser WHERE telegram_id = $1',
            user_id
        )
        
        if not user_db_id:
            return []
        
        return await conn.fetch('''
            SELECT p.*, u.first_name, u.username 
            FROM real_estate_favorite f
            JOIN real_estate_property p ON f.property_id = p.id
            JOIN real_estate_telegramuser u ON p.user_id = u.id
            WHERE f.user_id = $1 AND p.is_approved = true AND p.is_active = true
            ORDER BY f.created_at DESC
        ''', user_db_id)

async def get_user_postings(user_id: int):
    """Get all postings by user"""
    async with db_pool.acquire() as conn:
        # Get user database ID
        user_db_id = await conn.fetchval(
            'SELECT id FROM real_estate_telegramuser WHERE telegram_id = $1',
            user_id
        )
        
        if not user_db_id:
            return []
        
        return await conn.fetch('''
            SELECT p.*, 
                   (SELECT COUNT(*) FROM real_estate_favorite f WHERE f.property_id = p.id) as favorite_count
            FROM real_estate_property p 
            WHERE p.user_id = $1
            ORDER BY p.created_at DESC
        ''', user_db_id)

async def update_listing_status(listing_id: int, is_active: bool):
    """Update listing active status"""
    async with db_pool.acquire() as conn:
        await conn.execute(
            'UPDATE real_estate_property SET is_approved = $1, updated_at = NOW() WHERE id = $2',
            is_active, listing_id
        )

async def delete_listing(listing_id: int):
    """Delete listing and return users who had it favorited"""
    async with db_pool.acquire() as conn:
        # Get users who favorited this listing
        favorite_users = await conn.fetch('''
            SELECT tu.telegram_id 
            FROM real_estate_favorite f
            JOIN real_estate_telegramuser tu ON f.user_id = tu.id
            WHERE f.property_id = $1
        ''', listing_id)
        
        # Delete from favorites first
        await conn.execute('DELETE FROM real_estate_favorite WHERE property_id = $1', listing_id)
        
        # Delete the listing
        await conn.execute('DELETE FROM real_estate_property WHERE id = $1', listing_id)
        
        return [user['telegram_id'] for user in favorite_users]

# Admin functions
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def get_pending_listings():
    """Get listings pending approval"""
    async with db_pool.acquire() as conn:
        return await conn.fetch('''
            SELECT p.*, u.first_name, u.username 
            FROM real_estate_property p 
            JOIN real_estate_telegramuser u ON p.user_id = u.id 
            WHERE p.is_approved = false
            ORDER BY p.created_at ASC
        ''')

async def update_listing_approval(listing_id: int, is_approved: bool, admin_id: int):
    """Update listing approval status"""
    async with db_pool.acquire() as conn:
        await conn.execute('''
            UPDATE real_estate_property 
            SET is_approved = $1, updated_at = NOW()
            WHERE id = $2
        ''', is_approved, listing_id)

# FSM States for new listing flow
class ListingStates(StatesGroup):
    property_type = State()      
    status = State()             
    region = State()             
    district = State()
    price = State()              
    area = State()                           
    description = State()        
    confirmation = State()       
    contact_info = State()       
    photos = State()             

class SearchStates(StatesGroup):
    search_type = State()        
    keyword_query = State()      
    location_region = State()    
    location_district = State()  

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
            return await self.process_single_photo(message, state)
        
        self.groups[message.media_group_id].append(message)
        
        if message.media_group_id in self.timers:
            self.timers[message.media_group_id].cancel()
        
        self.timers[message.media_group_id] = create_task(
            self.process_group_after_delay(message.media_group_id, state)
        )
    
    async def process_group_after_delay(self, group_id: str, state: FSMContext):
        await sleep(1.0)
        
        if group_id in self.groups:
            messages = self.groups[group_id]
            await self.process_media_group(messages, state)
            
            del self.groups[group_id]
            if group_id in self.timers:
                del self.timers[group_id]
    
    async def process_single_photo(self, message: Message, state: FSMContext):
        user_lang = await get_user_language(message.from_user.id)
        
        data = await state.get_data()
        photo_file_ids = data.get('photo_file_ids', [])
        photo_file_ids.append(message.photo[-1].file_id)
        await state.update_data(photo_file_ids=photo_file_ids)
        
        await message.answer(
            get_text(user_lang, 'photo_added_count', count=len(photo_file_ids))
        )
    
    async def process_media_group(self, messages: list, state: FSMContext):
        user_lang = await get_user_language(messages[0].from_user.id)
        
        data = await state.get_data()
        photo_file_ids = data.get('photo_file_ids', [])
        
        for msg in messages:
            if msg.photo:
                photo_file_ids.append(msg.photo[-1].file_id)
        
        await state.update_data(photo_file_ids=photo_file_ids)
        
        await messages[0].answer(
            get_text(user_lang, 'media_group_received', count=len(messages))
        )

# Initialize media collector
media_collector = MediaGroupCollector()

# Add search translations
SEARCH_TRANSLATIONS = {
    'uz': {
        'choose_search_type': "🔍 Qidiruv turini tanlang:",
        'search_by_keyword': "📝 Kalit so'z bo'yicha qidiruv",
        'search_by_location': "🏘 Hudud bo'yicha qidiruv", 
        'search_prompt': "🔍 Qidirish uchun kalit so'z kiriting:",
        'select_region_for_search': "🗺 Qidiruv uchun viloyatni tanlang:",
        'select_district_or_all': "🏘 Tumanni tanlang yoki butun viloyat bo'yicha qidiring:",
        'all_region': "🌍 Butun viloyat",
        'search_results_count': "🔍 Qidiruv natijalari: {count} ta e'lon topildi",
        'no_search_results': "😔 Hech narsa topilmadi.\n\nBoshqa kalit so'z bilan yoki boshqa hudud bo'yicha qaytadan qidirib ko'ring.",
        'ask_price': "💰 E'lon narxini kiriting:\n\nMasalan: 50000, 50000$, 500 ming, 1.2 mln",
        'ask_area': "📐 Maydonni kiriting (m²):\n\nMasalan: 65, 65.5, 100",
        'invalid_price': "❌ Narx noto'g'ri kiritildi. Iltimos, faqat raqam kiriting.\n\nMasalan: 50000, 75000",
        'invalid_area': "❌ Maydon noto'g'ri kiritildi. Iltimos, faqat raqam kiriting.\n\nMasalan: 65, 100.5",
        'personalized_template_shown': "✨ Sizning ma'lumotlaringiz bilan tayyor namuna!\n\nQuyidagi namuna asosida e'loningizni yozing:",
    },
    'ru': {
        'choose_search_type': "🔍 Выберите тип поиска:",
        'search_by_keyword': "📝 Поиск по ключевому слову",
        'search_by_location': "🏘 Поиск по местоположению",
        'search_prompt': "🔍 Введите ключевое слово для поиска:",
        'select_region_for_search': "🗺 Выберите область для поиска:",
        'select_district_or_all': "🏘 Выберите район или искать по всей области:",
        'all_region': "🌍 Вся область",
        'search_results_count': "🔍 Результаты поиска: найдено {count} объявлений",
        'no_search_results': "😔 Ничего не найдено.\n\nПопробуйте другое ключевое слово или другой регион.",
        'ask_price': "💰 Введите цену объявления:\n\nНапример: 50000, 50000$, 500 тыс, 1.2 млн",
        'ask_area': "📐 Введите площадь (м²):\n\nНапример: 65, 65.5, 100",
        'invalid_price': "❌ Цена введена неправильно. Пожалуйста, введите только числа.\n\nНапример: 50000, 75000",
        'invalid_area': "❌ Площадь введена неправильно. Пожалуйста, введите только числа.\n\nНапример: 65, 100.5",
        'personalized_template_shown': "✨ Готовый шаблон с вашими данными!\n\nНапишите объявление по образцу ниже:",
    },
    'en': {
        'choose_search_type': "🔍 Choose search type:",
        'search_by_keyword': "📝 Search by keyword", 
        'search_by_location': "🏘 Search by location",
        'search_prompt': "🔍 Enter keyword to search:",
        'select_region_for_search': "🗺 Select region for search:",
        'select_district_or_all': "🏘 Select district or search entire region:",
        'all_region': "🌍 Entire region",
        'search_results_count': "🔍 Search results: found {count} listings",
        'no_search_results': "😔 Nothing found.\n\nTry a different keyword or location.",
        'ask_price': "💰 Enter listing price:\n\nExample: 50000, 50000$, 500k, 1.2M",
        'ask_area': "📐 Enter area (m²):\n\nExample: 65, 65.5, 100",
        'invalid_price': "❌ Price entered incorrectly. Please enter numbers only.\n\nExample: 50000, 75000",
        'invalid_area': "❌ Area entered incorrectly. Please enter numbers only.\n\nExample: 65, 100.5",
        'personalized_template_shown': "✨ Ready template with your data!\n\nWrite your listing based on the template below:",
    }
}

# Helper functions
def get_text(user_lang: str, key: str, **kwargs) -> str:
    # Try to get from main TRANSLATIONS first
    text = TRANSLATIONS.get(user_lang, TRANSLATIONS.get('uz', {})).get(key)
    
    # If not found, try from SEARCH_TRANSLATIONS
    if not text:
        text = SEARCH_TRANSLATIONS.get(user_lang, SEARCH_TRANSLATIONS.get('uz', {})).get(key)
    
    # If still not found, return a default message
    if not text:
        if key == 'no_search_results':
            text = "😔 Hech narsa topilmadi."
        elif key == 'search_results_count':
            text = "🔍 Qidiruv natijalari: {count} ta"
        else:
            text = key
    
    if kwargs and text:
        try:
            return text.format(**kwargs)
        except:
            return text
    return text

def get_personalized_listing_template(user_lang: str, status: str, property_type: str, price: str, area: str, location: str) -> str:
    """Generate personalized template with user's actual data"""
    
    # Special templates for Land and Commercial (regardless of sale/rent)
    if property_type == 'land':
        if user_lang == 'uz':
            return f"""
✨ Sizning ma'lumotlaringiz bilan tayyor namuna:

🧱 Bo'sh yer sotiladi
📍 Hudud: {location}
📐 Maydoni: {area} sotix
💰 Narxi: {price}
📄 Hujjatlari: tayyor/tayyorlanmoqda
🚗 Yo'l: asfalt yo'lga yaqin/uzoq
💧 Kommunikatsiya: suv, svet yaqin/uzoq
(Qo'shimcha ma'lumot kiritish mumkin)

🔴 Eslatma
Ma'lumotlar qatorida tel raqamingizni bot so'ramaguncha yozmang, aks holda sizni telingiz jiringlashdan to'xtamaydi va biz siz yuborgan xabarni botdan o'chirib tashlash imkonsiz
"""
        elif user_lang == 'ru':
            return f"""
✨ Готовый шаблон с вашими данными:

🧱 Продается пустой участок
📍 Район: {location}
📐 Площадь: {area} соток
💰 Цена: {price}
📄 Документы: готовы/готовятся
🚗 Дорога: близко/далеко к асфальту
💧 Коммуникации: вода, свет рядом/далеко
(Можно добавить дополнительную информацию)

🔴 Примечание
Не пишите свой номер телефона в тексте, пока бот не попросит, иначе ваш телефон не перестанет звонить и мы не сможем удалить ваше сообщение из бота
"""
        else:  # English
            return f"""
✨ Ready template with your data:

🧱 Empty land for sale
📍 Area: {location}
📐 Area: {area} acres
💰 Price: {price}
📄 Documents: ready/being prepared
🚗 Road: close/far to paved road
💧 Communications: water, electricity nearby/far
(Additional information can be added)

🔴 Note
Do not write your phone number in the text until the bot asks for it, otherwise your phone will not stop ringing and we cannot delete your message from the bot
"""
    
    elif property_type == 'commercial':
        if user_lang == 'uz':
            return f"""
✨ Sizning ma'lumotlaringiz bilan tayyor namuna:

🏢 Tijorat ob'ekti sotiladi
📍 Tuman: {location}
📐 Maydoni: {area} m²
💰 Narxi: {price}
📄 Hujjat: noturar bino/tijorat ob'ekti sifatida
📌 Hozirda faoliyat yuritmoqda/bo'sh
(Qo'shimcha ma'lumot kiritish mumkin)

🔴 Eslatma
Ma'lumotlar qatorida tel raqamingizni bot so'ramaguncha yozmang, aks holda sizni telingiz jiringlashdan to'xtamaydi va biz siz yuborgan xabarni botdan o'chirib tashlash imkonsiz
"""
        elif user_lang == 'ru':
            return f"""
✨ Готовый шаблон с вашими данными:

🏢 Продается коммерческий объект
📍 Район: {location}
📐 Площадь: {area} м²
💰 Цена: {price}
📄 Документ: нежилое здание/коммерческий объект
📌 В настоящее время работает/пустует
(Можно добавить дополнительную информацию)

🔴 Примечание
Не пишите свой номер телефона в тексте, пока бот не попросит, иначе ваш телефон не перестанет звонить и мы не сможем удалить ваше сообщение из бота
"""
        else:  # English
            return f"""
✨ Ready template with your data:

🏢 Commercial property for sale
📍 District: {location}
📐 Area: {area} m²
💰 Price: {price}
📄 Document: non-residential building/commercial property
📌 Currently operating/vacant
(Additional information can be added)

🔴 Note
Do not write your phone number in the text until the bot asks for it, otherwise your phone will not stop ringing and we cannot delete your message from the bot
"""
    
    # Regular templates for apartment/house based on sale/rent
    else:
        if user_lang == 'uz':
            if status == 'rent':
                return f"""
✨ Sizning ma'lumotlaringiz bilan tayyor namuna:

🏠 KVARTIRA IJARAGA BERILADI
📍 {location}
💰 Narxi: {price}
📐 Maydon: {area} m²
🛏 Xonalar: __ xonali
♨️ Kommunal: gaz, suv, svet bor
🪚 Holati: yevro remont yoki o'rtacha
🛋 Jihoz: jihozli yoki jihozsiz
🕒 Muddat: qisqa yoki uzoq muddatga
👥 Kimga: Shariy nikohga / oilaga / studentlarga

🔴 Eslatma
Ma'lumotlar qatorida tel raqamingizni bot so'ramaguncha yozmang, aks holda sizni telingiz jiringlashdan to'xtamaydi va biz siz yuborgan xabarni botdan o'chirib tashlash imkonsiz
"""
            else:  # sale
                return f"""
✨ Sizning ma'lumotlaringiz bilan tayyor namuna:

🏠 UY-JOY SOTILADI 
📍 {location}
💰 Narxi: {price}
📐 Maydon: {area} m²
🛏 Xonalar: __ xonali
♨️ Kommunal: gaz, suv, svet bor
🪚 Holati: yevro remont yoki o'rtacha
🛋 Jihoz: jihozli yoki jihozsiz
🏢 Qavat: __/__

🔴 Eslatma
Ma'lumotlar qatorida tel raqamingizni bot so'ramaguncha yozmang, aks holda sizni telingiz jiringlashdan to'xtamaydi va biz siz yuborgan xabarni botdan o'chirib tashlash imkonsiz
"""
        elif user_lang == 'ru':
            if status == 'rent':
                return f"""
✨ Готовый шаблон с вашими данными:

🏠 КВАРТИРА СДАЕТСЯ В АРЕНДУ
📍 {location}
💰 Цена: {price}
📐 Площадь: {area} м²
🛏 Комнаты: __-комнатная
♨️ Коммунальные: газ, вода, свет есть
🪚 Состояние: евроремонт или среднее
🛋 Мебель: с мебелью или без мебели
🕒 Срок: краткосрочно или долгосрочно
👥 Для кого: для гражданского брака / для семьи / для студентов

🔴 Примечание
Не пишите свой номер телефона в тексте, пока бот не попросит, иначе ваш телефон не перестанет звонить и мы не сможем удалить ваше сообщение из бота
"""
            else:  # sale
                return f"""
✨ Готовый шаблон с вашими данными:

🏠 ПРОДАЕТСЯ НЕДВИЖИМОСТЬ
📍 {location}
💰 Цена: {price}
📐 Площадь: {area} м²
🛏 Комнаты: __-комнатная
♨️ Коммунальные: газ, вода, свет есть
🪚 Состояние: евроремонт или среднее
🛋 Мебель: с мебелью или без мебели
🏢 Этаж: __/__

🔴 Примечание
Не пишите свой номер телефона в тексте, пока бот не попросит, иначе ваш телефон не перестанет звонить и мы не сможем удалить ваше сообщение из бота
"""
        else:  # English
            if status == 'rent':
                return f"""
✨ Ready template with your data:

🏠 APARTMENT FOR RENT
📍 {location}
💰 Price: {price}
📐 Area: {area} m²
🛏 Rooms: __-room
♨️ Utilities: gas, water, electricity available
🪚 Condition: euro renovation or average
🛋 Furniture: furnished or unfurnished
🕒 Period: short-term or long-term
👥 For whom: for civil marriage / for family / for students

🔴 Note
Do not write your phone number in the text until the bot asks for it, otherwise your phone will not stop ringing and we cannot delete your message from the bot
"""
            else:  # sale
                return f"""
✨ Ready template with your data:

🏠 PROPERTY FOR SALE
📍 {location}
💰 Price: {price}
📐 Area: {area} m²
🛏 Rooms: __-room
♨️ Utilities: gas, water, electricity available
🪚 Condition: euro renovation or average
🛋 Furniture: furnished or unfurnished
🏢 Floor: __/__

🔴 Note
Do not write your phone number in the text until the bot asks for it, otherwise your phone will not stop ringing and we cannot delete your message from the bot
"""

def format_listing_for_admin(listing) -> str:
    location = listing['full_address'] if listing['full_address'] else "Manzil ko'rsatilmagan"
    
    return f"""
🆔 <b>E'lon #{listing['id']}</b>
👤 <b>Foydalanuvchi:</b> {listing['first_name']} (@{listing['username'] or 'username_yoq'})
🏘 <b>Tur:</b> {listing['property_type']}
🎯 <b>Maqsad:</b> {listing['status']}
🗺 <b>Manzil:</b> {location}
📞 <b>Aloqa:</b> {listing['contact_info']}

<b>📝 Tavsif:</b>
{listing['description']}

⏰ <b>Vaqt:</b> {listing['created_at']}
"""

def get_admin_review_keyboard(listing_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_{listing_id}"))
    builder.add(InlineKeyboardButton(text="❌ Rad etish", callback_data=f"decline_{listing_id}"))
    builder.add(InlineKeyboardButton(text="📋 Barcha kutilayotganlar", callback_data="pending_all"))
    builder.adjust(2, 1)
    return builder.as_markup()

def format_listing_for_channel(listing) -> str:
    user_description = listing['description']
    contact_info = listing['contact_info']
    
    channel_text = f"""{user_description}

📞 Aloqa: {contact_info}
\n🗺 Manzil: {listing['full_address']}"""
    
    property_type = listing['property_type']
    status = listing['status']
    
    channel_text += f"\n\n#{property_type} #{status}"
    
    return channel_text

def format_listing_raw_display(listing, user_lang):
    user_description = listing['description']
    location_display = listing['full_address'] if listing['full_address'] else listing['address']
    contact_info = listing['contact_info']
    
    listing_text = f"""{user_description}

📞 Aloqa: {contact_info}"""
    
    if location_display and location_display.strip():
        listing_text += f"\n🗺 Manzil: {location_display}"
    
    return listing_text

def get_main_menu_keyboard(user_lang: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=get_text(user_lang, 'post_listing')))
    builder.add(KeyboardButton(text=get_text(user_lang, 'view_listings')))
    builder.add(KeyboardButton(text=get_text(user_lang, 'my_postings')))
    builder.add(KeyboardButton(text=get_text(user_lang, 'search')))
    builder.add(KeyboardButton(text=get_text(user_lang, 'favorites')))
    builder.add(KeyboardButton(text=get_text(user_lang, 'info')))
    builder.add(KeyboardButton(text=get_text(user_lang, 'language')))
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def get_search_type_keyboard(user_lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text=get_text(user_lang, 'search_by_keyword'), 
        callback_data="search_keyword"
    ))
    builder.add(InlineKeyboardButton(
        text=get_text(user_lang, 'search_by_location'), 
        callback_data="search_location"
    ))
    builder.adjust(1)
    return builder.as_markup()

def get_language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"))
    builder.add(InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"))
    builder.add(InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en"))
    builder.adjust(1)
    return builder.as_markup()

def get_regions_keyboard(user_lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    regions = regions_config.get(user_lang, regions_config['uz'])
    
    for region_key, region_name in regions:
        builder.add(InlineKeyboardButton(
            text=region_name,
            callback_data=f"region_{region_key}"
        ))
    
    builder.adjust(2)
    return builder.as_markup()

def get_search_regions_keyboard(user_lang: str) -> InlineKeyboardMarkup:
    """SEPARATE keyboard for search regions to avoid conflicts"""
    builder = InlineKeyboardBuilder()
    regions = regions_config.get(user_lang, regions_config['uz'])
    
    for region_key, region_name in regions:
        builder.add(InlineKeyboardButton(
            text=region_name,
            callback_data=f"search_region_{region_key}"  # DIFFERENT PREFIX
        ))
    
    builder.adjust(2)
    return builder.as_markup()

def get_districts_keyboard(region_key: str, user_lang: str) -> InlineKeyboardMarkup:
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

def get_search_districts_keyboard(region_key: str, user_lang: str) -> InlineKeyboardMarkup:
    """SEPARATE keyboard for search districts to avoid conflicts"""
    builder = InlineKeyboardBuilder()
    
    # Add "All region" option first
    builder.add(InlineKeyboardButton(
        text=get_text(user_lang, 'all_region'),
        callback_data=f"search_all_region_{region_key}"
    ))
    
    try:
        districts = REGIONS_DATA[user_lang][region_key]['districts']
        
        for district_key, district_name in districts.items():
            builder.add(InlineKeyboardButton(
                text=district_name,
                callback_data=f"search_district_{district_key}"  # DIFFERENT PREFIX
            ))
    except KeyError:
        pass
    
    # Add back button
    builder.add(InlineKeyboardButton(
        text=get_text(user_lang, 'back'),
        callback_data="search_back_to_regions"
    ))
    
    builder.adjust(1, 2, 2, 2, 2, 2, 1)
    return builder.as_markup()

def get_property_type_keyboard(user_lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'apartment'), callback_data="type_apartment"))
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'house'), callback_data="type_house"))
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'commercial'), callback_data="type_commercial"))
    builder.add(InlineKeyboardButton(text=get_text(user_lang, 'land'), callback_data="type_land"))
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

def format_my_posting_display(listing, user_lang):
    """Format posting for owner view"""
    location_display = listing['full_address'] if listing['full_address'] else listing['address']
    
    # Status determination based on is_approved
    if listing['is_approved']:
        status_text = get_text(user_lang, 'posting_status_active')
    else:
        status_text = get_text(user_lang, 'posting_status_pending')
    
    favorite_count = listing.get('favorite_count', 0)
    
    listing_text = f"""
🆔 <b>E'lon #{listing['id']}</b>
📊 <b>Status:</b> {status_text}

🏠 <b>{listing['title'] or listing['description'][:50]}...</b>
🗺 <b>Manzil:</b> {location_display}
💰 <b>Narx:</b> {listing['price']:,} so'm
📐 <b>Maydon:</b> {listing['area']} m²

📝 <b>Tavsif:</b> {listing['description'][:100]}{'...' if len(listing['description']) > 100 else ''}
"""
    return listing_text

def get_posting_management_keyboard(listing_id: int, is_active: bool, user_lang: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    """Create posting management keyboard"""
    builder = InlineKeyboardBuilder()
    
    # Status toggle button
    if is_active:
        builder.add(InlineKeyboardButton(
            text=get_text(user_lang, 'deactivate_posting'), 
            callback_data=f"deactivate_post_{listing_id}"
        ))
    else:
        builder.add(InlineKeyboardButton(
            text=get_text(user_lang, 'activate_posting'), 
            callback_data=f"activate_post_{listing_id}"
        ))
    
    # Management buttons
    builder.add(InlineKeyboardButton(
        text=get_text(user_lang, 'delete_posting'), 
        callback_data=f"delete_post_{listing_id}"
    ))
    
    # Admin-only buttons
    if is_admin:
        builder.add(InlineKeyboardButton(
            text="🔧 Admin Actions", 
            callback_data=f"admin_post_{listing_id}"
        ))
    
    builder.adjust(2)
    return builder.as_markup()

async def post_to_channel(listing):
    """Post approved listing to channel"""
    try:
        channel_text = format_listing_for_channel(listing)
        photo_file_ids = json.loads(listing['photo_file_ids']) if listing['photo_file_ids'] else []
        
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
        
        # Save channel message ID (optional - would need to add this field to DB)
        # await update_listing_channel_message_id(listing['id'], message.message_id)
        
    except Exception as e:
        logger.error(f"Error posting to channel: {e}")

# Add this to your environment variables section
ADMIN_CHANNEL_ID = os.getenv('ADMIN_CHANNEL_ID', '@two_day_or_today')

async def send_to_admin_channel_for_review(listing_id: int):
    """Send listing to admin channel for review"""
    listing = await get_listing_by_id(listing_id)
    if not listing:
        logger.error(f"Listing {listing_id} not found for admin review")
        return
    
    if not ADMIN_CHANNEL_ID:
        logger.error("No ADMIN_CHANNEL_ID configured! Please set ADMIN_CHANNEL_ID in .env file")
        return
    
    admin_text = format_listing_for_admin_channel(listing)
    keyboard = get_admin_channel_review_keyboard(listing_id)
    
    try:
        photo_file_ids = json.loads(listing['photo_file_ids']) if listing['photo_file_ids'] else []
        
        if photo_file_ids:
            if len(photo_file_ids) == 1:
                message = await bot.send_photo(
                    chat_id=ADMIN_CHANNEL_ID,
                    photo=photo_file_ids[0],
                    caption=admin_text,
                    reply_markup=keyboard
                )
            else:
                media_group = MediaGroupBuilder(caption=admin_text)
                for photo_id in photo_file_ids[:10]:
                    media_group.add_photo(media=photo_id)
                
                messages = await bot.send_media_group(chat_id=ADMIN_CHANNEL_ID, media=media_group.build())
                message = await bot.send_message(
                    chat_id=ADMIN_CHANNEL_ID,
                    text="👆 Yuqoridagi e'lonni ko'rib chiqing:",
                    reply_markup=keyboard
                )
        else:
            message = await bot.send_message(
                chat_id=ADMIN_CHANNEL_ID,
                text=admin_text,
                reply_markup=keyboard
            )
        
        logger.info(f"Successfully sent listing {listing_id} to admin channel {ADMIN_CHANNEL_ID}")
        return message
        
    except Exception as e:
        logger.error(f"Error sending to admin channel {ADMIN_CHANNEL_ID}: {e}")
        
        # Specific error handling
        error_msg = str(e).lower()
        if "chat not found" in error_msg:
            logger.error("Admin channel not found! Make sure the bot is added to the channel.")
        elif "forbidden" in error_msg or "not enough rights" in error_msg:
            logger.error("Bot doesn't have permission to post in admin channel! Make bot an admin.")
        else:
            logger.error(f"Unknown error: {e}")
        
        raise

def format_listing_for_admin_channel(listing) -> str:
    """Format listing for admin channel review"""
    location = listing['full_address'] if listing['full_address'] else "Manzil ko'rsatilmagan"
    
    # Get user info
    user_info = f"{listing['first_name']}"
    if listing['username']:
        user_info += f" (@{listing['username']})"
    
    # Get property type and status in Uzbek
    property_types = {
        'apartment': 'Kvartira',
        'house': 'Uy',
        'commercial': 'Tijorat',
        'land': 'Yer'
    }
    
    statuses = {
        'sale': 'Sotuv',
        'rent': 'Ijara'
    }
    
    prop_type = property_types.get(listing['property_type'], listing['property_type'])
    status = statuses.get(listing['status'], listing['status'])
    
    return f"""
🆕 <b>YANGI E'LON KO'RIB CHIQISH UCHUN</b>

🆔 <b>E'lon ID:</b> #{listing['id']}
👤 <b>Foydalanuvchi:</b> {user_info}
🏘 <b>Tur:</b> {prop_type}
🎯 <b>Maqsad:</b> {status}
🗺 <b>Manzil:</b> {location}
💰 <b>Narx:</b> {listing['price']:,} so'm
📐 <b>Maydon:</b> {listing['area']} m²
📞 <b>Aloqa:</b> {listing['contact_info']}

<b>📝 Tavsif:</b>
{listing['description']}

⏰ <b>Yuborilgan vaqt:</b> {listing['created_at'].strftime('%d.%m.%Y %H:%M')}

👥 <b>Adminlar, bu e'lonni ko'rib chiqing!</b>
"""

def get_admin_channel_review_keyboard(listing_id: int) -> InlineKeyboardMarkup:
    """Create keyboard for admin channel review"""
    builder = InlineKeyboardBuilder()
    
    # Approval buttons
    builder.add(InlineKeyboardButton(
        text="✅ Tasdiqlash", 
        callback_data=f"admin_approve_{listing_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="❌ Rad etish", 
        callback_data=f"admin_decline_{listing_id}"
    ))
    
    # Additional action buttons
    builder.add(InlineKeyboardButton(
        text="👀 Batafsil ko'rish", 
        callback_data=f"admin_details_{listing_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="📊 Statistika", 
        callback_data=f"admin_stats"
    ))
    
    builder.adjust(2, 2)
    return builder.as_markup()

# Update the callback handlers for admin channel

# Add these debug commands to your existing code (before the other handlers)

@dp.message(Command("check_admin"))
async def check_admin_status(message: Message):
    """Debug command to check admin status and configuration"""
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    first_name = message.from_user.first_name or "No name"
    
    debug_info = f"""
🔍 <b>ADMIN DEBUG INFO</b>

👤 <b>Your Info:</b>
• ID: <code>{user_id}</code>
• Name: {first_name}
• Username: @{username}

🔧 <b>Configuration:</b>
• Environment ADMIN_IDS: "{os.getenv('ADMIN_IDS', 'NOT SET')}"
• Parsed Admin IDs: {ADMIN_IDS}
• Total Admins: {len(ADMIN_IDS)}
• Your ID in admin list: {'✅ YES' if is_admin(user_id) else '❌ NO'}

📋 <b>Channels:</b>
• Admin Channel: {ADMIN_CHANNEL_ID}
• Main Channel: {CHANNEL_ID}

🎯 <b>Final Result:</b> {'✅ YOU ARE ADMIN' if is_admin(user_id) else '❌ NOT ADMIN'}
"""
    
    await message.answer(debug_info)
    
    # If not admin, show what needs to be fixed
    if not is_admin(user_id):
        fix_message = f"""
❌ <b>PROBLEM DETECTED:</b>
Your ID <code>{user_id}</code> is not in the admin list.

📝 <b>TO FIX:</b>
1. Update your .env file:
   <code>ADMIN_IDS={user_id}</code>

2. Restart the bot

3. Send /check_admin again to verify

💡 <b>Current admin list:</b> {ADMIN_IDS}
"""
        await message.answer(fix_message)

@dp.message(Command("debug_config"))
async def debug_config(message: Message):
    """Show all configuration details"""
    env_admin_ids = os.getenv('ADMIN_IDS', 'NOT SET')
    
    config_info = f"""
🔧 <b>COMPLETE CONFIGURATION DEBUG</b>

📝 <b>Environment Variables:</b>
• ADMIN_IDS (raw): "{env_admin_ids}"
• BOT_TOKEN: {'✅ SET' if BOT_TOKEN != 'YOUR_BOT_TOKEN_HERE' else '❌ NOT SET'}
• CHANNEL_ID: {CHANNEL_ID}
• ADMIN_CHANNEL_ID: {ADMIN_CHANNEL_ID}

🔄 <b>Parsing Process:</b>
• Raw string: "{env_admin_ids}"
• After split: {env_admin_ids.split(',') if env_admin_ids != 'NOT SET' else 'N/A'}
• Final ADMIN_IDS: {ADMIN_IDS}
• Type: {type(ADMIN_IDS)}

👤 <b>Your Details:</b>
• Your ID: {message.from_user.id}
• Type: {type(message.from_user.id)}
• Check result: {message.from_user.id in ADMIN_IDS}

🧮 <b>Comparison Test:</b>
"""
    
    # Test each admin ID individually
    if ADMIN_IDS:
        for i, admin_id in enumerate(ADMIN_IDS):
            comparison = message.from_user.id == admin_id
            config_info += f"• {message.from_user.id} == {admin_id}: {comparison}\n"
    else:
        config_info += "• No admin IDs to compare\n"
    
    await message.answer(config_info)

@dp.message(Command("fix_admin_now"))
async def fix_admin_now(message: Message):
    """Temporary fix for admin access"""
    user_id = message.from_user.id
    
    # Add user to admin list temporarily (for this session only)
    if user_id not in ADMIN_IDS:
        ADMIN_IDS.append(user_id)
        await message.answer(f"🔧 Temporarily added {user_id} to admin list for this session.\n\n✅ Try the approval buttons now!\n\n⚠️ This is temporary - update your .env file permanently.")
    else:
        await message.answer(f"✅ You're already in the admin list: {ADMIN_IDS}")

@dp.message(Command("test_callback"))
async def test_callback_handling(message: Message):
    """Test if callback handling works for admin"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer(f"❌ You're not an admin!\n\nYour ID: {user_id}\nConfigured admins: {ADMIN_IDS}\n\nUse /fix_admin_now for temporary fix")
        return
    
    # Create test callback buttons
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Test Approve", callback_data="test_approve_123"))
    builder.add(InlineKeyboardButton(text="❌ Test Decline", callback_data="test_decline_123"))
    builder.add(InlineKeyboardButton(text="📊 Test Details", callback_data="test_details_123"))
    
    await message.answer(
        "🧪 <b>CALLBACK TEST</b>\n\nIf you're an admin, these buttons should work:",
        reply_markup=builder.as_markup()
    )

# Test callback handlers
@dp.callback_query(F.data.startswith('test_approve_'))
async def test_approve_callback(callback_query):
    """Test approve callback"""
    user_id = callback_query.from_user.id
    
    if not is_admin(user_id):
        await callback_query.answer("❌ You're not an admin!", show_alert=True)
        return
    
    await callback_query.answer("✅ Approve callback works!")
    await callback_query.message.edit_text(
        f"✅ <b>SUCCESS!</b>\n\n"
        f"Approve callback handled successfully by admin {user_id}\n"
        f"Real approval system should work now!"
    )

@dp.callback_query(F.data.startswith('test_decline_'))
async def test_decline_callback(callback_query):
    """Test decline callback"""
    user_id = callback_query.from_user.id
    
    if not is_admin(user_id):
        await callback_query.answer("❌ You're not an admin!", show_alert=True)
        return
    
    await callback_query.answer("❌ Decline callback works!")
    await callback_query.message.edit_text(
        f"❌ <b>SUCCESS!</b>\n\n"
        f"Decline callback handled successfully by admin {user_id}\n"
        f"Real decline system should work now!"
    )

@dp.callback_query(F.data.startswith('test_details_'))
async def test_details_callback(callback_query):
    """Test details callback"""
    user_id = callback_query.from_user.id
    
    if not is_admin(user_id):
        await callback_query.answer("❌ You're not an admin!", show_alert=True)
        return
    
    details_text = f"""
📊 <b>TEST DETAILS</b>

✅ Callback system working
✅ Admin check passing
✅ User ID: {user_id}
✅ Admin permissions: Confirmed

All systems ready for real listings!
"""
    
    await callback_query.answer(details_text, show_alert=True)

@dp.callback_query(F.data.startswith('admin_approve_'))
async def admin_channel_approve_listing(callback_query):
    """Handle approval from admin channel"""
    # Check if user is admin
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⛔ Sizda admin huquqlari yo'q!")
        return
    
    listing_id = int(callback_query.data.split('_')[2])
    admin_name = callback_query.from_user.first_name
    admin_username = f"@{callback_query.from_user.username}" if callback_query.from_user.username else ""
    
    # Approve the listing in database
    await update_listing_approval(listing_id, True, callback_query.from_user.id)
    
    # Get the listing
    listing = await get_listing_by_id(listing_id)
    if not listing:
        await callback_query.answer("E'lon topilmadi!")
        return
    
    # Post to main channel
    try:
        await post_to_channel(listing)
        channel_status = "va asosiy kanalga yuborildi ✅"
    except Exception as e:
        logger.error(f"Error posting to main channel: {e}")
        channel_status = "lekin asosiy kanalga yuborishda xatolik yuz berdi ❌"
    
    # Notify the user who created the listing
    await notify_user_approval(listing['user_id'], True)
    
    # Update the admin channel message
    approval_text = f"""
✅ <b>E'LON TASDIQLANDI!</b>

🆔 <b>E'lon ID:</b> #{listing_id}
👨‍💼 <b>Tasdiqlagan admin:</b> {admin_name} {admin_username}
📅 <b>Tasdiqlangan vaqt:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}

{channel_status}
"""
    
    try:
        await callback_query.message.edit_text(approval_text)
    except:
        # If can't edit (too old message), send new one
        await callback_query.message.reply(approval_text)
    
    await callback_query.answer(f"✅ E'lon #{listing_id} tasdiqlandi!")

@dp.callback_query(F.data.startswith('admin_decline_'))
async def admin_channel_decline_listing(callback_query, state: FSMContext):
    """Handle decline from admin channel"""
    # Check if user is admin
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⛔ Sizda admin huquqlari yo'q!")
        return
    
    listing_id = int(callback_query.data.split('_')[2])
    
    # Set state for feedback
    await state.set_state(AdminStates.writing_feedback)
    await state.update_data(
        listing_id=listing_id, 
        admin_message_id=callback_query.message.message_id,
        admin_chat_id=callback_query.message.chat.id
    )
    
    # Ask admin to write feedback in private
    try:
        await bot.send_message(
            chat_id=callback_query.from_user.id,
            text=f"❌ E'lon #{listing_id} uchun rad etish sababini yozing:\n\n"
                 f"💭 Foydalanuvchiga yuborilacak xabar:"
        )
        await callback_query.answer("📝 Sizga shaxsiy xabar yuborildi. Rad etish sababini yozing.")
    except Exception as e:
        # If can't send private message, ask in channel
        await callback_query.message.reply(
            f"❌ @{callback_query.from_user.username or callback_query.from_user.first_name}, "
            f"e'lon #{listing_id} uchun rad etish sababini yozing:"
        )
        await callback_query.answer("📝 Rad etish sababini yozing.")

# Replace the admin_channel_show_details function with this shorter version:

@dp.callback_query(F.data.startswith('admin_details_'))
async def admin_channel_show_details(callback_query):
    """Show detailed info about listing"""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⛔ Sizda admin huquqlari yo'q!")
        return
    
    listing_id = int(callback_query.data.split('_')[2])
    listing = await get_listing_by_id(listing_id)
    
    if not listing:
        await callback_query.answer("E'lon topilmadi!")
        return
    
    # Get additional stats
    async with db_pool.acquire() as conn:
        user_listing_count = await conn.fetchval(
            'SELECT COUNT(*) FROM real_estate_property WHERE user_id = $1',
            listing['user_id']
        )
        
        user_approved_count = await conn.fetchval(
            'SELECT COUNT(*) FROM real_estate_property WHERE user_id = $1 AND is_approved = true',
            listing['user_id']
        )
    
    # SHORT version for callback answer (under 200 chars)
    short_details = f"""
📊 E'lon #{listing['id']}
👤 {listing['first_name']} 
📈 Jami: {user_listing_count} | Tasdiqlangan: {user_approved_count}
💰 {listing['price']:,} so'm | 📐 {listing['area']} m²
"""
    
    # Send SHORT message as callback answer
    await callback_query.answer(short_details.strip(), show_alert=True)
    
    # Optionally send FULL details as a separate message
    full_details_text = f"""
📊 <b>BATAFSIL MA'LUMOT</b>

🆔 <b>E'lon ID:</b> #{listing['id']}
👤 <b>Foydalanuvchi:</b> {listing['first_name']} (@{listing['username'] or 'username_yoq'})

📈 <b>Foydalanuvchi statistikasi:</b>
• Jami e'lonlar: {user_listing_count}
• Tasdiqlangan: {user_approved_count}

🏠 <b>E'lon ma'lumotlari:</b>
• Tur: {listing['property_type']}
• Maqsad: {listing['status']}
• Hudud: {listing['region']} - {listing['district']}
• Narx: {listing['price']:,} so'm
• Maydon: {listing['area']} m²
• Xonalar: {listing['rooms']}

📞 <b>Aloqa:</b> {listing['contact_info']}
📅 <b>Yaratilgan:</b> {listing['created_at'].strftime('%d.%m.%Y %H:%M')}
"""
    
    # Send full details as a regular message
    try:
        await callback_query.message.reply(full_details_text)
    except Exception as e:
        logger.error(f"Could not send full details: {e}")

# Also fix the admin stats function:
@dp.callback_query(F.data == 'admin_stats')
async def admin_channel_show_stats(callback_query):
    """Show general admin statistics"""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⛔ Sizda admin huquqlari yo'q!")
        return
    
    async with db_pool.acquire() as conn:
        total_listings = await conn.fetchval('SELECT COUNT(*) FROM real_estate_property')
        pending_listings = await conn.fetchval('SELECT COUNT(*) FROM real_estate_property WHERE is_approved = false')
        approved_listings = await conn.fetchval('SELECT COUNT(*) FROM real_estate_property WHERE is_approved = true')
        total_users = await conn.fetchval('SELECT COUNT(*) FROM real_estate_telegramuser')
        
        # Today's stats
        today_listings = await conn.fetchval(
            "SELECT COUNT(*) FROM real_estate_property WHERE DATE(created_at) = CURRENT_DATE"
        )
        
        today_approved = await conn.fetchval(
            "SELECT COUNT(*) FROM real_estate_property WHERE DATE(updated_at) = CURRENT_DATE AND is_approved = true"
        )
    
    # SHORT version for callback (under 200 chars)
    short_stats = f"""
📊 Jami: {total_listings} | Kutish: {pending_listings}
✅ Tasdiqlangan: {approved_listings}
👥 Foydalanuvchilar: {total_users}
🆕 Bugun: {today_listings}
"""
    
    await callback_query.answer(short_stats.strip(), show_alert=True)
    
    # Send full stats as a separate message
    full_stats_text = f"""
📊 <b>ADMIN STATISTIKA</b>

📈 <b>Umumiy:</b>
• Jami e'lonlar: {total_listings}
• Kutilayotgan: {pending_listings}
• Tasdiqlangan: {approved_listings}
• Foydalanuvchilar: {total_users}

📅 <b>Bugun:</b>
• Yangi e'lonlar: {today_listings}
• Tasdiqlangan: {today_approved}

⏱ <b>Vaqt:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
    
    try:
        await callback_query.message.reply(full_stats_text)
    except Exception as e:
        logger.error(f"Could not send full stats: {e}")

# Also fix any debug commands that might be too long:
@dp.callback_query(F.data.startswith('test_details_'))
async def test_details_callback(callback_query):
    """Test details callback - FIXED VERSION"""
    user_id = callback_query.from_user.id
    
    if not is_admin(user_id):
        await callback_query.answer("❌ You're not an admin!", show_alert=True)
        return
    
    # SHORT message (under 200 chars)
    short_details = f"""
📊 TEST SUCCESS
✅ Callback: OK
✅ Admin: {user_id}
✅ Permissions: Confirmed
"""
    
    await callback_query.answer(short_details.strip(), show_alert=True)
async def notify_user_approval(user_id: int, approved: bool, feedback: str = None):
    """Notify user about listing approval/decline"""
    user_lang = await get_user_language(user_id)
    
    try:
        if approved:
            message = get_text(user_lang, 'listing_approved')
        else:
            message = get_text(user_lang, 'listing_declined', feedback=feedback or "Sabab ko'rsatilmagan")
        
        await bot.send_message(chat_id=user_id, text=message)
    except Exception as e:
        logger.error(f"Error notifying user {user_id}: {e}")

async def display_search_results(message_or_callback, listings, user_lang, search_term=""):
    """Display search results to user"""
    
    # Determine if this is a Message or CallbackQuery
    is_callback = hasattr(message_or_callback, 'message')
    
    if not listings:
        text = get_text(user_lang, 'no_search_results')
        if is_callback:
            await message_or_callback.message.answer(text)
        else:
            await message_or_callback.answer(text)
        return
    
    # Show search results count
    results_text = get_text(user_lang, 'search_results_count', count=len(listings))
    if is_callback:
        await message_or_callback.message.answer(results_text)
    else:
        await message_or_callback.answer(results_text)
    
    # Display each listing
    for listing in listings[:5]:
        listing_text = format_listing_raw_display(listing, user_lang)
        keyboard = get_listing_keyboard(listing['id'], user_lang)
        
        photo_file_ids = json.loads(listing['photo_file_ids']) if listing['photo_file_ids'] else []
        
        try:
            if photo_file_ids:
                if len(photo_file_ids) == 1:
                    # Send single photo
                    if is_callback:
                        await message_or_callback.message.answer_photo(
                            photo=photo_file_ids[0],
                            caption=listing_text,
                            reply_markup=keyboard
                        )
                    else:
                        await message_or_callback.answer_photo(
                            photo=photo_file_ids[0],
                            caption=listing_text,
                            reply_markup=keyboard
                        )
                else:
                    # Send media group
                    media_group = MediaGroupBuilder(caption=listing_text)
                    for photo_id in photo_file_ids[:5]:
                        media_group.add_photo(media=photo_id)
                    
                    if is_callback:
                        await message_or_callback.message.answer_media_group(media=media_group.build())
                        await message_or_callback.message.answer("👆 E'lon", reply_markup=keyboard)
                    else:
                        await message_or_callback.answer_media_group(media=media_group.build())
                        await message_or_callback.answer("👆 E'lon", reply_markup=keyboard)
            else:
                # No photos, send text only
                if is_callback:
                    await message_or_callback.message.answer(listing_text, reply_markup=keyboard)
                else:
                    await message_or_callback.answer(listing_text, reply_markup=keyboard)
        except Exception as e2:
            logger.error(f"Error in fallback display: {e2}")

# Handlers
@dp.message(CommandStart())
async def start_handler(message: Message):
    user = message.from_user
    await save_user(user.id, user.username, user.first_name, user.last_name)
    user_lang = await get_user_language(user.id)
    
    await message.answer(
        get_text(user_lang, 'start'),
        reply_markup=get_main_menu_keyboard(user_lang)
    )

@dp.message(F.text.in_(['🌐 Til', '🌐 Язык', '🌐 Language']))
async def language_handler(message: Message):
    user_lang = await get_user_language(message.from_user.id)
    await message.answer(
        get_text(user_lang, 'choose_language'),
        reply_markup=get_language_keyboard()
    )

@dp.callback_query(F.data.startswith('lang_'))
async def language_callback(callback_query):
    lang = callback_query.data.split('_')[1]
    await update_user_language(callback_query.from_user.id, lang)
    
    await callback_query.answer(f"Language changed!")
    
    await callback_query.message.answer(
        get_text(lang, 'main_menu'),
        reply_markup=get_main_menu_keyboard(lang)
    )

# =============================================
# SEARCH HANDLERS - COMPLETELY SEPARATE
# =============================================

@dp.message(F.text.in_(['🔍 Qidiruv', '🔍 Поиск', '🔍 Search']))
async def search_handler(message: Message, state: FSMContext):
    """ONLY FOR SEARCHING EXISTING LISTINGS"""
    user_lang = await get_user_language(message.from_user.id)
    await state.set_state(SearchStates.search_type)
    await message.answer(
        get_text(user_lang, 'choose_search_type'),
        reply_markup=get_search_type_keyboard(user_lang)
    )

@dp.callback_query(F.data == 'search_keyword')
async def search_keyword_selected(callback_query, state: FSMContext):
    user_lang = await get_user_language(callback_query.from_user.id)
    await state.set_state(SearchStates.keyword_query)
    await callback_query.message.edit_text(get_text(user_lang, 'search_prompt'))
    await callback_query.answer()

@dp.callback_query(F.data == 'search_location')
async def search_location_selected(callback_query, state: FSMContext):
    user_lang = await get_user_language(callback_query.from_user.id)
    await state.set_state(SearchStates.location_region)
    await callback_query.message.edit_text(
        get_text(user_lang, 'select_region_for_search'),
        reply_markup=get_search_regions_keyboard(user_lang)  # SEPARATE KEYBOARD
    )
    await callback_query.answer()

@dp.message(SearchStates.keyword_query)
async def process_keyword_search(message: Message, state: FSMContext):
    user_lang = await get_user_language(message.from_user.id)
    query = message.text.strip()
    await state.clear()
    
    # Search existing listings
    listings = await search_listings(query)
    
    # Display results
    await display_search_results(message, listings, user_lang, query)

# SEARCH REGION HANDLERS - DIFFERENT PREFIX
@dp.callback_query(F.data.startswith('search_region_'))
async def process_search_region_selection(callback_query, state: FSMContext):
    user_lang = await get_user_language(callback_query.from_user.id)
    
    region_key = callback_query.data[14:]  # Remove 'search_region_' prefix
    
    if region_key not in REGIONS_DATA.get(user_lang, {}):
        await callback_query.answer("Region not found!")
        return
    
    await state.update_data(search_region=region_key)
    await state.set_state(SearchStates.location_district)
    await callback_query.message.edit_text(
        get_text(user_lang, 'select_district_or_all'),
        reply_markup=get_search_districts_keyboard(region_key, user_lang)  # SEPARATE KEYBOARD
    )
    await callback_query.answer()

@dp.callback_query(F.data.startswith('search_all_region_'))
async def process_search_all_region(callback_query, state: FSMContext):
    user_lang = await get_user_language(callback_query.from_user.id)
    region_key = callback_query.data[18:]  # Remove 'search_all_region_' prefix
    
    await state.clear()
    
    # Search by region only
    listings = await search_listings_by_location(region_key=region_key)
    
    # Get region name for display
    try:
        region_name = REGIONS_DATA[user_lang][region_key]['name']
    except KeyError:
        region_name = "Selected region"
    
    # Display results
    await display_search_results(callback_query, listings, user_lang, region_name)

@dp.callback_query(F.data.startswith('search_district_'))
async def process_search_district_selection(callback_query, state: FSMContext):
    user_lang = await get_user_language(callback_query.from_user.id)
    district_key = callback_query.data[16:]  # Remove 'search_district_' prefix
    
    data = await state.get_data()
    region_key = data.get('search_region')
    await state.clear()
    
    # Search by both region and district
    listings = await search_listings_by_location(region_key=region_key, district_key=district_key)
    
    # Get location name for display
    try:
        region_name = REGIONS_DATA[user_lang][region_key]['name']
        district_name = REGIONS_DATA[user_lang][region_key]['districts'][district_key]
        location_name = f"{district_name}, {region_name}"
    except KeyError:
        location_name = "Selected location"
    
    # Display results
    await display_search_results(callback_query, listings, user_lang, location_name)

@dp.callback_query(F.data == 'search_back_to_regions')
async def search_back_to_regions(callback_query, state: FSMContext):
    user_lang = await get_user_language(callback_query.from_user.id)
    
    await state.set_state(SearchStates.location_region)
    await callback_query.message.edit_text(
        get_text(user_lang, 'select_region_for_search'),
        reply_markup=get_search_regions_keyboard(user_lang)  # SEPARATE KEYBOARD
    )
    await callback_query.answer()

# =============================================
# LISTING CREATION HANDLERS - COMPLETELY SEPARATE
# =============================================

@dp.message(F.text.in_(['📝 E\'lon joylash', '📝 Разместить объявление', '📝 Post listing']))
async def post_listing_handler(message: Message, state: FSMContext):
    """ONLY FOR CREATING NEW LISTINGS"""
    user_lang = await get_user_language(message.from_user.id)
    
    await state.set_state(ListingStates.property_type)
    await message.answer(
        get_text(user_lang, 'property_type'),
        reply_markup=get_property_type_keyboard(user_lang)
    )

@dp.callback_query(F.data.startswith('type_'))
async def process_property_type(callback_query, state: FSMContext):
    user_lang = await get_user_language(callback_query.from_user.id)
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
    user_lang = await get_user_language(callback_query.from_user.id)
    status = callback_query.data.split('_')[1]
    await state.update_data(status=status)
    
    await state.set_state(ListingStates.region)
    await callback_query.message.edit_text(
        get_text(user_lang, 'select_region'),
        reply_markup=get_regions_keyboard(user_lang)  # NORMAL KEYBOARD FOR LISTING
    )
    await callback_query.answer()

# LISTING REGION HANDLERS - NORMAL PREFIX (only works when in ListingStates)
@dp.callback_query(F.data.startswith('region_'), ListingStates.region)
async def process_region_selection(callback_query, state: FSMContext):
    user_lang = await get_user_language(callback_query.from_user.id)
    
    region_key = callback_query.data[7:]  # Remove 'region_' prefix
    
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
    user_lang = await get_user_language(callback_query.from_user.id)
    district_key = callback_query.data[9:]
    
    await state.update_data(district=district_key)
    
    # Ask for price first
    await state.set_state(ListingStates.price)
    await callback_query.message.edit_text(get_text(user_lang, 'ask_price'))
    await callback_query.answer(get_text(user_lang, 'district_selected'))

@dp.message(ListingStates.price)
async def process_price(message: Message, state: FSMContext):
    user_lang = await get_user_language(message.from_user.id)
    
    # Validate price input
    try:
        price_text = message.text.strip()
        # Remove common separators and extract numbers
        price_clean = ''.join(filter(str.isdigit, price_text))
        
        if not price_clean:
            await message.answer(get_text(user_lang, 'invalid_price'))
            return
        
        price = int(price_clean)
        await state.update_data(price=price, price_text=price_text)
        
        # Ask for area
        await state.set_state(ListingStates.area)
        await message.answer(get_text(user_lang, 'ask_area'))
        
    except ValueError:
        await message.answer(get_text(user_lang, 'invalid_price'))

@dp.message(ListingStates.area)
async def process_area(message: Message, state: FSMContext):
    user_lang = await get_user_language(message.from_user.id)
    
    # Validate area input
    try:
        area_text = message.text.strip()
        # Extract numbers (can be decimal)
        area_clean = ''.join(c for c in area_text if c.isdigit() or c == '.')
        
        if not area_clean:
            await message.answer(get_text(user_lang, 'invalid_area'))
            return
        
        area = float(area_clean)
        await state.update_data(area=area, area_text=area_text)
        
        # Now show personalized template
        data = await state.get_data()
        property_type = data.get('property_type')
        status = data.get('status')
        price_text = data.get('price_text', '')
        area_text = data.get('area_text', '')
        region_key = data.get('region')
        district_key = data.get('district')
        
        # Get location names
        region_name = REGIONS_DATA[user_lang][region_key]['name']
        district_name = REGIONS_DATA[user_lang][region_key]['districts'][district_key]
        location = f"{district_name}, {region_name}"
        
        # Get personalized template
        template = get_personalized_listing_template(
            user_lang, status, property_type, price_text, area_text, location
        )
        
        await state.set_state(ListingStates.description)
        await message.answer(template)
        await message.answer(get_text(user_lang, 'personalized_template_shown'))
        
    except ValueError:
        await message.answer(get_text(user_lang, 'invalid_area'))

@dp.callback_query(F.data == 'back_to_regions')
async def back_to_regions(callback_query, state: FSMContext):
    user_lang = await get_user_language(callback_query.from_user.id)
    
    await state.set_state(ListingStates.region)
    await callback_query.message.edit_text(
        get_text(user_lang, 'select_region'),
        reply_markup=get_regions_keyboard(user_lang)
    )
    await callback_query.answer()

@dp.message(ListingStates.description)
async def process_description(message: Message, state: FSMContext):
    user_lang = await get_user_language(message.from_user.id)
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
    user_lang = await get_user_language(callback_query.from_user.id)
    
    await state.set_state(ListingStates.contact_info)
    await callback_query.message.edit_text(get_text(user_lang, 'phone_number_request'))
    await callback_query.answer()

@dp.callback_query(F.data == 'desc_add_more')
async def description_add_more(callback_query, state: FSMContext):
    user_lang = await get_user_language(callback_query.from_user.id)
    
    await state.set_state(ListingStates.description)
    await callback_query.message.edit_text(get_text(user_lang, 'additional_info'))
    await callback_query.answer()

@dp.message(ListingStates.contact_info)
async def process_contact_info(message: Message, state: FSMContext):
    user_lang = await get_user_language(message.from_user.id)
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
    user_lang = await get_user_language(callback_query.from_user.id)
    data = await state.get_data()
    
    # Build full address
    region_key = data.get('region')
    district_key = data.get('district')
    
    if region_key and district_key:
        try:
            region_name = REGIONS_DATA[user_lang][region_key]['name']
            district_name = REGIONS_DATA[user_lang][region_key]['districts'][district_key]
            full_address = f"{district_name}, {region_name}"
            data['full_address'] = full_address
            data['address'] = full_address
        except KeyError:
            # Fallback if region/district data is missing
            data['full_address'] = f"{district_key}, {region_key}"
            data['address'] = f"{district_key}, {region_key}"
    
    # Ensure title is properly set from description
    description = data.get('description', 'No description provided')
    if not data.get('title'):
        # Create title from first line or first 50 chars of description
        title = description.split('\n')[0][:50]
        if len(description) > 50:
            title += '...'
        data['title'] = title
    
    # Ensure all required numeric fields have proper defaults
    if 'price' not in data or data['price'] is None:
        data['price'] = 0
    if 'area' not in data or data['area'] is None:
        data['area'] = 0
    if 'rooms' not in data:
        data['rooms'] = 0
    
    # Ensure string fields are not None
    if not data.get('condition'):
        data['condition'] = ''
    if not data.get('contact_info'):
        data['contact_info'] = 'Not provided'
    
    # Debug: Log what we're about to save
    logger.info(f"Saving listing with data: {data}")
    
    try:
        # Save listing to database (will be pending approval)
        listing_id = await save_listing(callback_query.from_user.id, data)
        
        # REMOVED: Auto-approval and immediate channel posting
        # OLD CODE:
        # await update_listing_approval(listing_id, True, 0)
        # listing = await get_listing_by_id(listing_id)
        # if listing:
        #     await post_to_channel(listing)
        
        # NEW: Send to admin channel for review instead of auto-posting
        await send_to_admin_channel_for_review(listing_id)
        
        # Notify user that listing is created and sent for review
        await callback_query.message.edit_text(
            get_text(user_lang, 'listing_submitted_for_review')
        )
        
        await state.clear()
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Error in finish_listing: {e}")
        
        # Notify user of the error
        error_message = "❌ Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring."
        
        await callback_query.message.edit_text(error_message)
        await callback_query.answer("❌ Xatolik yuz berdi", show_alert=True)
        
        # Clear state so user can start over
        await state.clear()

# =============================================
# OTHER HANDLERS
# =============================================

@dp.message(F.text.in_(['👀 E\'lonlar', '👀 Объявления', '👀 Listings']))
async def view_listings_handler(message: Message):
    user_lang = await get_user_language(message.from_user.id)
    listings = await get_listings(limit=5)
    
    if not listings:
        await message.answer(get_text(user_lang, 'no_listings'))
        return
    
    for listing in listings:
        # Use raw display instead of template
        listing_text = format_listing_raw_display(listing, user_lang)
        keyboard = get_listing_keyboard(listing['id'], user_lang)
        
        photo_file_ids = json.loads(listing['photo_file_ids']) if listing['photo_file_ids'] else []
        
        if photo_file_ids:
            try:
                if len(photo_file_ids) == 1:
                    await message.answer_photo(
                        photo=photo_file_ids[0],
                        caption=listing_text,
                        reply_markup=keyboard
                    )
                else:
                    # For multiple photos, show user content as caption on first photo
                    media_group = MediaGroupBuilder(caption=listing_text)
                    for i, photo_id in enumerate(photo_file_ids[:10]):
                        if i == 0:
                            media_group.add_photo(media=photo_id)
                        else:
                            media_group.add_photo(media=photo_id)
                    
                    await message.answer_media_group(media=media_group.build())
                    # Send keyboard separately for media groups
                    await message.answer("👆 E'lon", reply_markup=keyboard)
                    
            except Exception as e:
                # Fallback to text if photo fails
                await message.answer(listing_text, reply_markup=keyboard)
        else:
            await message.answer(listing_text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith('fav_add_'))
async def add_favorite_callback(callback_query):
    listing_id = int(callback_query.data.split('_')[2])
    user_lang = await get_user_language(callback_query.from_user.id)
    
    # Check if listing is still active
    listing = await get_listing_by_id(listing_id)
    if not listing or not listing['is_approved']:  # not active
        await callback_query.answer(get_text(user_lang, 'posting_no_longer_available'), show_alert=True)
        return
    
    await add_to_favorites(callback_query.from_user.id, listing_id)
    await callback_query.answer(get_text(user_lang, 'added_to_favorites'))

@dp.callback_query(F.data.startswith('contact_'))
async def contact_callback(callback_query):
    listing_id = int(callback_query.data.split('_')[1])
    user_lang = await get_user_language(callback_query.from_user.id)
    
    listing = await get_listing_by_id(listing_id)
    
    if listing:
        await callback_query.answer(f"📞 Aloqa: {listing['contact_info']}", show_alert=True)
    else:
        await callback_query.answer("E'lon topilmadi")

@dp.message(F.text.in_(['❤️ Sevimlilar', '❤️ Избранное', '❤️ Favorites']))
async def favorites_handler(message: Message):
    user_lang = await get_user_language(message.from_user.id)
    favorites = await get_user_favorites(message.from_user.id)
    
    if not favorites:
        await message.answer(get_text(user_lang, 'no_favorites'))
        return
    
    await message.answer(f"❤️ Sevimli e'lonlar: {len(favorites)} ta")
    
    for favorite in favorites[:5]:
        # Use raw display instead of template
        listing_text = format_listing_raw_display(favorite, user_lang)
        
        photo_file_ids = json.loads(favorite['photo_file_ids']) if favorite['photo_file_ids'] else []
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
    user_lang = await get_user_language(message.from_user.id)
    await message.answer(get_text(user_lang, 'about'))

# Handlers for My Postings
@dp.message(F.text.in_(['📝 Mening e\'lonlarim', '📝 Мои объявления', '📝 My Postings']))
async def my_postings_handler(message: Message):
    user_lang = await get_user_language(message.from_user.id)
    postings = await get_user_postings(message.from_user.id)
    
    if not postings:
        await message.answer(get_text(user_lang, 'no_my_postings'))
        return
    
    await message.answer(f"📝 Sizning e'lonlaringiz: {len(postings)} ta")
    
    for posting in postings:  # Show all postings
        posting_text = format_my_posting_display(posting, user_lang)
        is_active = posting['is_approved']  # is_approved
        keyboard = get_posting_management_keyboard(
            posting['id'], is_active, user_lang, is_admin(message.from_user.id)
        )
        
        # Show with photos if available
        photo_file_ids = json.loads(posting['photo_file_ids']) if posting['photo_file_ids'] else []
        if photo_file_ids:
            try:
                await message.answer_photo(
                    photo=photo_file_ids[0],
                    caption=posting_text,
                    reply_markup=keyboard
                )
            except:
                await message.answer(posting_text, reply_markup=keyboard)
        else:
            await message.answer(posting_text, reply_markup=keyboard)

# Status management callbacks
@dp.callback_query(F.data.startswith('activate_post_'))
async def activate_posting(callback_query):
    listing_id = int(callback_query.data.split('_')[2])
    user_lang = await get_user_language(callback_query.from_user.id)
    
    # Check ownership or admin rights
    listing = await get_listing_by_id(listing_id)
    if not listing:
        await callback_query.answer("⛔ E'lon topilmadi!")
        return
    
    # Get user database ID for ownership check
    async with db_pool.acquire() as conn:
        user_db_id = await conn.fetchval(
            'SELECT id FROM real_estate_telegramuser WHERE telegram_id = $1',
            callback_query.from_user.id
        )
    
    if listing['user_id'] != user_db_id and not is_admin(callback_query.from_user.id):
        await callback_query.answer("⛔ Ruxsat yo'q!")
        return
    
    # Activate the posting
    await update_listing_status(listing_id, True)
    
    await callback_query.message.edit_reply_markup(
        reply_markup=get_posting_management_keyboard(
            listing_id, True, user_lang, is_admin(callback_query.from_user.id)
        )
    )
    await callback_query.answer(get_text(user_lang, 'posting_activated'))

@dp.callback_query(F.data.startswith('deactivate_post_'))
async def deactivate_posting(callback_query):
    listing_id = int(callback_query.data.split('_')[2])
    user_lang = await get_user_language(callback_query.from_user.id)
    
    # Check ownership or admin rights
    listing = await get_listing_by_id(listing_id)
    if not listing:
        await callback_query.answer("⛔ E'lon topilmadi!")
        return
    
    # Get user database ID for ownership check
    async with db_pool.acquire() as conn:
        user_db_id = await conn.fetchval(
            'SELECT id FROM real_estate_telegramuser WHERE telegram_id = $1',
            callback_query.from_user.id
        )
    
    if listing['user_id'] != user_db_id and not is_admin(callback_query.from_user.id):
        await callback_query.answer("⛔ Ruxsat yo'q!")
        return
    
    # Deactivate the posting
    await update_listing_status(listing_id, False)
    
    await callback_query.message.edit_reply_markup(
        reply_markup=get_posting_management_keyboard(
            listing_id, False, user_lang, is_admin(callback_query.from_user.id)
        )
    )
    await callback_query.answer(get_text(user_lang, 'posting_deactivated'))

@dp.callback_query(F.data.startswith('delete_post_'))
async def confirm_delete_posting(callback_query):
    listing_id = int(callback_query.data.split('_')[2])
    user_lang = await get_user_language(callback_query.from_user.id)
    
    # Check ownership or admin rights
    listing = await get_listing_by_id(listing_id)
    if not listing:
        await callback_query.answer("⛔ E'lon topilmadi!")
        return
    
    # Get user database ID for ownership check
    async with db_pool.acquire() as conn:
        user_db_id = await conn.fetchval(
            'SELECT id FROM real_estate_telegramuser WHERE telegram_id = $1',
            callback_query.from_user.id
        )
    
    if listing['user_id'] != user_db_id and not is_admin(callback_query.from_user.id):
        await callback_query.answer("⛔ Ruxsat yo'q!")
        return
    
    # Show confirmation dialog
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text=get_text(user_lang, 'yes_delete'), 
        callback_data=f"confirm_delete_{listing_id}"
    ))
    builder.add(InlineKeyboardButton(
        text=get_text(user_lang, 'cancel_action'), 
        callback_data=f"cancel_delete_{listing_id}"
    ))
    builder.adjust(2)
    
    await callback_query.message.edit_text(
        get_text(user_lang, 'confirm_delete'),
        reply_markup=builder.as_markup()
    )
    await callback_query.answer()

@dp.callback_query(F.data.startswith('confirm_delete_'))
async def delete_posting_confirmed(callback_query):
    listing_id = int(callback_query.data.split('_')[2])
    user_lang = await get_user_language(callback_query.from_user.id)
    
    # Check ownership or admin rights
    listing = await get_listing_by_id(listing_id)
    if not listing:
        await callback_query.answer("⛔ E'lon topilmadi!")
        return
    
    # Get user database ID for ownership check
    async with db_pool.acquire() as conn:
        user_db_id = await conn.fetchval(
            'SELECT id FROM real_estate_telegramuser WHERE telegram_id = $1',
            callback_query.from_user.id
        )
    
    if listing['user_id'] != user_db_id and not is_admin(callback_query.from_user.id):
        await callback_query.answer("⛔ Ruxsat yo'q!")
        return
    
    # Delete the posting and get users who favorited it
    favorite_users = await delete_listing(listing_id)
    
    # Notify users who favorited it
    for user_id in favorite_users:
        try:
            message = get_text(user_lang, 'favorites_removed_notification', title=listing['title'] or listing['description'][:50])
            await bot.send_message(chat_id=user_id, text=message)
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")
    
    await callback_query.message.edit_text(get_text(user_lang, 'posting_deleted'))
    await callback_query.answer()

@dp.callback_query(F.data.startswith('cancel_delete_'))
async def cancel_delete_posting(callback_query):
    listing_id = int(callback_query.data.split('_')[2])
    user_lang = await get_user_language(callback_query.from_user.id)
    
    # Get posting and show management interface again
    listing = await get_listing_by_id(listing_id)
    if listing:
        posting_text = format_my_posting_display(listing, user_lang)
        keyboard = get_posting_management_keyboard(
            listing_id, listing['is_approved'], user_lang, is_admin(callback_query.from_user.id)
        )
        
        await callback_query.message.edit_text(posting_text, reply_markup=keyboard)
    
    await callback_query.answer()

# ADMIN HANDLERS
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Sizda admin huquqlari yo'q!")
        return
    
    pending_listings = await get_pending_listings()
    
    if not pending_listings:
        await message.answer("✅ Hamma e'lonlar ko'rib chiqilgan!")
        return
    
    await message.answer(f"📋 Kutilayotgan e'lonlar: {len(pending_listings)} ta")
    
    if pending_listings:
        listing = pending_listings[0]
        admin_text = format_listing_for_admin(listing)
        keyboard = get_admin_review_keyboard(listing['id'])
        
        photo_file_ids = json.loads(listing['photo_file_ids']) if listing['photo_file_ids'] else []
        
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
    
    # Approve the listing in database
    await update_listing_approval(listing_id, True, callback_query.from_user.id)
    
    # Get the listing
    listing = await get_listing_by_id(listing_id)
    if not listing:
        await callback_query.answer("E'lon topilmadi!")
        return
    
    # NOW post to channel (only after admin approval)
    try:
        await post_to_channel(listing)
        channel_status = "va kanalga yuborildi"
    except Exception as e:
        logger.error(f"Error posting to channel: {e}")
        channel_status = "lekin kanalga yuborishda xatolik yuz berdi"
    
    # Notify the user who created the listing
    await notify_user_approval(listing['user_id'], True)
    
    # Update admin interface
    await callback_query.message.edit_text(
        f"✅ E'lon #{listing_id} tasdiqlandi {channel_status}!"
    )
    await callback_query.answer("✅ E'lon tasdiqlandi!")

# Also add the missing translation
APPROVAL_TRANSLATIONS = {
    'uz': {
        'listing_submitted_for_review': "✅ E'loningiz muvaffaqiyatli yuborildi!\n\n👨‍💼 Admin ko'rib chiqishidan so'ng kanalda e'lon qilinadi.\n\n⏱ Odatda bu 24 soat ichida amalga oshiriladi.",
        'listing_approved': "🎉 Tabriklaymiz! E'loningiz tasdiqlandi va kanalda e'lon qilindi!",
        'listing_declined': "❌ Afsuski, e'loningiz rad etildi.\n\n📝 Sabab: {feedback}\n\nIltimos, talablarni hisobga olib qaytadan yuboring.",
    },
    'ru': {
        'listing_submitted_for_review': "✅ Ваше объявление успешно отправлено!\n\n👨‍💼 После проверки администратором оно будет опубликовано в канале.\n\n⏱ Обычно это происходит в течение 24 часов.",
        'listing_approved': "🎉 Поздравляем! Ваше объявление одобрено и опубликовано в канале!",
        'listing_declined': "❌ К сожалению, ваше объявление отклонено.\n\n📝 Причина: {feedback}\n\nПожалуйста, учтите требования и отправьте заново.",
    },
    'en': {
        'listing_submitted_for_review': "✅ Your listing has been successfully submitted!\n\n👨‍💼 It will be published in the channel after admin review.\n\n⏱ This usually happens within 24 hours.",
        'listing_approved': "🎉 Congratulations! Your listing has been approved and published in the channel!",
        'listing_declined': "❌ Unfortunately, your listing was declined.\n\n📝 Reason: {feedback}\n\nPlease consider the requirements and resubmit.",
    }
}
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
    
    # Delete the listing instead of just declining
    listing = await get_listing_by_id(listing_id)
    if listing:
        await delete_listing(listing_id)
        await notify_user_approval(listing['user_id'], False, feedback)
    
    await message.answer(f"❌ E'lon #{listing_id} rad etildi va foydalanuvchiga xabar yuborildi!")
    await state.clear()

# Debug commands for testing
@dp.message(Command("debug"))
async def debug_handler(message: Message):
    """Debug database and search"""
    try:
        async with db_pool.acquire() as conn:
            # Check total listings
            total_count = await conn.fetchval('SELECT COUNT(*) FROM real_estate_property')
            approved_count = await conn.fetchval('SELECT COUNT(*) FROM real_estate_property WHERE is_approved = true')
            pending_count = await conn.fetchval('SELECT COUNT(*) FROM real_estate_property WHERE is_approved = false')
            
            status_counts = await conn.fetch('SELECT is_approved, COUNT(*) FROM real_estate_property GROUP BY is_approved')
        
        debug_text = f"""📊 Database Debug:
        
Total listings: {total_count}
Approved: {approved_count}
Pending: {pending_count}

Status breakdown:
{chr(10).join([f"- {'Approved' if status[0] else 'Pending'}: {status[1]}" for status in status_counts])}

Search test:"""
        
        await message.answer(debug_text)
        
        # Test search
        if approved_count > 0:
            listings = await search_listings("a")  # Search for letter "a"
            await message.answer(f"Search test 'a': Found {len(listings)} results")
            
            if listings:
                listing = listings[0]
                sample_text = f"Sample listing #{listing['id']}:\n{listing['description'][:100]}..."
                await message.answer(sample_text)
        else:
            await message.answer("❌ No approved listings found! Please approve some listings first using /admin")
            
    except Exception as e:
        await message.answer(f"❌ Debug error: {str(e)}")

@dp.message(Command("test_search"))
async def test_search_handler(message: Message):
    """Test search functionality"""
    user_lang = await get_user_language(message.from_user.id)
    
    # Test database connection
    try:
        listings = await search_listings("uy")
        await message.answer(f"✅ Search test: Found {len(listings)} listings with 'uy'")
        
        if listings:
            listing = listings[0]
            text = format_listing_raw_display(listing, user_lang)
            await message.answer(f"Sample listing:\n{text}")
        else:
            await message.answer("❌ No listings found in database")
            
    except Exception as e:
        await message.answer(f"❌ Search error: {str(e)}")

# Error handler
@dp.error()
async def error_handler(event):
    """Handle errors in bot"""
    update = event.update
    exception = event.exception
    
    logger.error(f"Error occurred in update {update.update_id}: {exception}")
    
    # Log full traceback for debugging
    import traceback
    logger.error(f"Full traceback: {traceback.format_exc()}")
    
    # Try to notify user if possible
    try:
        if update.message:
            user_lang = await get_user_language(update.message.from_user.id) if db_pool else 'uz'
            await update.message.answer("❌ Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
        elif update.callback_query:
            await update.callback_query.answer("❌ Xatolik yuz berdi.", show_alert=True)
    except Exception as notify_error:
        logger.error(f"Could not notify user about error: {notify_error}")
    
    return True

async def main():
    """Main bot function with proper initialization"""
    global db_pool
    
    logger.info("🤖 Starting Real Estate Bot...")
    
    # Check environment variables
    required_vars = ['BOT_TOKEN', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"❌ Missing environment variables: {missing_vars}")
        logger.error("Please check your .env file")
        return
    
    # Initialize database pool
    logger.info("🔌 Connecting to database...")
    if not await init_db_pool():
        logger.error("❌ Failed to initialize database pool")
        logger.error("Please ensure PostgreSQL is running and Django migrations are applied")
        logger.error("Run: cd backend && python manage.py migrate")
        return
    
    # Test database connection
    try:
        async with db_pool.acquire() as conn:
            # Check if tables exist
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'real_estate_telegramuser'
                );
            """)
            
            if not table_exists:
                logger.error("❌ Database tables don't exist!")
                logger.error("Please run Django migrations first:")
                logger.error("   cd backend")
                logger.error("   python manage.py migrate")
                logger.error("   python manage.py populate_regions")
                await close_db_pool()
                return
            
            logger.info("✅ Database connection successful")
            
    except Exception as e:
        logger.error(f"❌ Database test failed: {e}")
        await close_db_pool()
        return
    
    logger.info("🚀 Starting bot polling...")
    
    try:
        # Start polling
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
    finally:
        logger.info("🔌 Closing connections...")
        await bot.session.close()
        await close_db_pool()
        logger.info("👋 Bot stopped")

if __name__ == "__main__":
    asyncio.run(main())