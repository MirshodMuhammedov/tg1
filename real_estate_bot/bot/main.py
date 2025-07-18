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
    search_type = State()        # Choose search type (keyword or location)
    keyword_query = State()      # For keyword search
    location_region = State()    # For location search - region selection
    location_district = State()  # For location search - district selection

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


def format_listing_for_channel(listing) -> str:
    """Format listing for channel posting with user's actual content"""
    # Show exactly what user wrote + contact info
    user_description = listing[3]  # User's actual content
    contact_info = listing[14]
    
    # Keep it simple for channel - just user content + contact
    channel_text = f"""{user_description}

📞 Aloqa: {contact_info}
\n🗺 Manzil: {listing[8]}"""
    
    # Add hashtags based on property type and status
    property_type = listing[4]  # property_type
    status = listing[12]  # status
    
    channel_text += f"\n\n#{property_type} #{status}"
    
    return channel_text

def format_listing_raw_display(listing, user_lang):
    """Display listing with user's actual content, not template format"""
    # Show the user's actual description content
    user_description = listing[3]  # This is the actual content user wrote
    
    # Just add basic info at the end
    location_display = listing[8] if listing[8] else listing[7]  # full_address or address
    contact_info = listing[14]
    
    # Format: User content + minimal additional info
    listing_text = f"""{user_description}

📞 Aloqa: {contact_info}"""
    
    # Only add location if it's different from what's already in description
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
    """Create keyboard for search type selection"""
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
    """Create keyboard with all 14 regions of Uzbekistan"""
    builder = InlineKeyboardBuilder()
    

    # Get regions for the specified language, fallback to 'uz' if language not found
    regions = regions_config.get(user_lang, regions_config['uz'])
    
    # Add buttons for each region
    for region_key, region_name in regions:
        builder.add(InlineKeyboardButton(
            text=region_name,
            callback_data=f"region_{region_key}"
        ))
    
    # Arrange buttons in a grid: 2 columns for better layout
    builder.adjust(2)
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
    
    # Extract region key properly (everything after 'region_')
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
    district_key = callback_query.data[9:]
    
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
        # Use raw display instead of template
        listing_text = format_listing_raw_display(listing, user_lang)
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

# NEW SEARCH HANDLERS WITH INTEGRATED OPTIONS
@dp.message(F.text.in_(['🔍 Qidiruv', '🔍 Поиск', '🔍 Search']))
async def search_handler(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    await state.set_state(SearchStates.search_type)
    await message.answer(
        get_text(user_lang, 'choose_search_type'),
        reply_markup=get_search_type_keyboard(user_lang)
    )

@dp.callback_query(F.data == 'search_keyword')
async def search_keyword_selected(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    await state.set_state(SearchStates.keyword_query)
    await callback_query.message.edit_text(get_text(user_lang, 'search_prompt'))
    await callback_query.answer()

@dp.callback_query(F.data == 'search_location')
async def search_location_selected(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    await state.set_state(SearchStates.location_region)
    await callback_query.message.edit_text(
        get_text(user_lang, 'select_region_for_search'),
        reply_markup=get_regions_keyboard(user_lang)
    )
    await callback_query.answer()

@dp.message(SearchStates.keyword_query)
async def process_keyword_search(message: Message, state: FSMContext):
    user_lang = get_user_language(message.from_user.id)
    query = message.text
    await state.clear()
    
    listings = search_listings(query)
    
    if not listings:
        await message.answer(get_text(user_lang, 'no_listings'))
        return
    
    await message.answer(f"🔍 Qidiruv natijalari: {len(listings)} ta e'lon topildi")
    
    for listing in listings[:3]:
        # Use raw display instead of template
        listing_text = format_listing_raw_display(listing, user_lang)
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
                    await message.answer("👆 E'lon", reply_markup=keyboard)
            except:
                await message.answer(listing_text, reply_markup=keyboard)
        else:
            await message.answer(listing_text, reply_markup=keyboard)

# Handle region selection for location search
@dp.callback_query(F.data.startswith('region_'), SearchStates.location_region)
async def process_search_region_selection(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    
    # Extract region key properly (everything after 'region_')
    region_key = callback_query.data[7:]  # Remove 'region_' prefix
    
    # Check if region exists
    if region_key not in REGIONS_DATA.get(user_lang, {}):
        await callback_query.answer("Region not found!")
        return
    
    await state.update_data(search_region=region_key)
    
    # Create keyboard with districts + "All region" option
    builder = InlineKeyboardBuilder()
    
    # Add "All region" option first
    builder.add(InlineKeyboardButton(
        text=get_text(user_lang, 'all_region'),
        callback_data=f"search_all_region_{region_key}"
    ))
    
    # Add districts
    try:
        districts = REGIONS_DATA[user_lang][region_key]['districts']
        for district_key, district_name in districts.items():
            builder.add(InlineKeyboardButton(
                text=district_name,
                callback_data=f"search_district_{district_key}"
            ))
    except KeyError:
        pass
    
    # Add back button
    builder.add(InlineKeyboardButton(
        text=get_text(user_lang, 'back'),
        callback_data="search_back_to_regions"
    ))
    
    builder.adjust(1, 2, 2, 2, 2, 2, 1)
    
    await state.set_state(SearchStates.location_district)
    await callback_query.message.edit_text(
        get_text(user_lang, 'select_district_or_all'),
        reply_markup=builder.as_markup()
    )
    await callback_query.answer(get_text(user_lang, 'region_selected'))

@dp.callback_query(F.data.startswith('search_all_region_'))
async def process_search_all_region(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    region_key = callback_query.data[18:]  # Remove 'search_all_region_' prefix
    
    data = await state.get_data()
    await state.clear()
    
    # Search only by region
    listings = search_listings_by_location(region_key=region_key)
    
    if not listings:
        await callback_query.message.edit_text(get_text(user_lang, 'no_location_results'))
        return
    
    region_name = REGIONS_DATA[user_lang][region_key]['name']
    await callback_query.message.edit_text(
        get_text(user_lang, 'location_search_results', region=region_name)
    )
    
    for listing in listings[:3]:
        listing_text = format_listing_raw_display(listing, user_lang)
        keyboard = get_listing_keyboard(listing[0], user_lang)
        
        photo_file_ids = json.loads(listing[15]) if listing[15] else []
        
        if photo_file_ids:
            try:
                if len(photo_file_ids) == 1:
                    await callback_query.message.answer_photo(
                        photo=photo_file_ids[0],
                        caption=listing_text,
                        reply_markup=keyboard
                    )
                else:
                    media_group = MediaGroupBuilder(caption=listing_text)
                    for photo_id in photo_file_ids[:5]:
                        media_group.add_photo(media=photo_id)
                    
                    await callback_query.message.answer_media_group(media=media_group.build())
                    await callback_query.message.answer("👆 E'lon", reply_markup=keyboard)
            except:
                await callback_query.message.answer(listing_text, reply_markup=keyboard)
        else:
            await callback_query.message.answer(listing_text, reply_markup=keyboard)
    
    await callback_query.answer()

@dp.callback_query(F.data.startswith('search_district_'))
async def process_search_district_selection(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    district_key = callback_query.data[16:]  # Remove 'search_district_' prefix
    
    data = await state.get_data()
    region_key = data.get('search_region')
    await state.clear()
    
    # Search by both region and district
    listings = search_listings_by_location(region_key=region_key, district_key=district_key)
    
    if not listings:
        await callback_query.message.edit_text(get_text(user_lang, 'no_location_results'))
        return
    
    try:
        region_name = REGIONS_DATA[user_lang][region_key]['name']
        district_name = REGIONS_DATA[user_lang][region_key]['districts'][district_key]
        location_name = f"{district_name}, {region_name}"
    except KeyError:
        location_name = "Selected location"
    
    await callback_query.message.edit_text(
        get_text(user_lang, 'location_search_results', region=location_name)
    )
    
    for listing in listings[:3]:
        listing_text = format_listing_raw_display(listing, user_lang)
        keyboard = get_listing_keyboard(listing[0], user_lang)
        
        photo_file_ids = json.loads(listing[15]) if listing[15] else []
        
        if photo_file_ids:
            try:
                if len(photo_file_ids) == 1:
                    await callback_query.message.answer_photo(
                        photo=photo_file_ids[0],
                        caption=listing_text,
                        reply_markup=keyboard
                    )
                else:
                    media_group = MediaGroupBuilder(caption=listing_text)
                    for photo_id in photo_file_ids[:5]:
                        media_group.add_photo(media=photo_id)
                    
                    await callback_query.message.answer_media_group(media=media_group.build())
                    await callback_query.message.answer("👆 E'lon", reply_markup=keyboard)
            except:
                await callback_query.message.answer(listing_text, reply_markup=keyboard)
        else:
            await callback_query.message.answer(listing_text, reply_markup=keyboard)
    
    await callback_query.answer()

@dp.callback_query(F.data == 'search_back_to_regions')
async def search_back_to_regions(callback_query, state: FSMContext):
    user_lang = get_user_language(callback_query.from_user.id)
    
    await state.set_state(SearchStates.location_region)
    await callback_query.message.edit_text(
        get_text(user_lang, 'select_region_for_search'),
        reply_markup=get_regions_keyboard(user_lang)
    )
    await callback_query.answer()

@dp.callback_query(F.data.startswith('fav_add_'))
async def add_favorite_callback(callback_query):
    listing_id = int(callback_query.data.split('_')[2])
    user_lang = get_user_language(callback_query.from_user.id)
    
    # Check if listing is still active
    listing = get_listing_by_id(listing_id)
    if not listing or not listing[17]:  # not active
        await callback_query.answer(get_text(user_lang, 'posting_no_longer_available'), show_alert=True)
        return
    
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
        # Use raw display instead of template
        listing_text = format_listing_raw_display(favorite, user_lang)
        
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

def get_user_postings(user_id: int):
    """Get all postings by user"""
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l.*, 
               (SELECT COUNT(*) FROM favorites f WHERE f.listing_id = l.id) as favorite_count
        FROM listings l 
        WHERE l.user_id = ?
        ORDER BY l.created_at DESC
    ''', (user_id,))
    postings = cursor.fetchall()
    conn.close()
    return postings

def update_listing_status(listing_id: int, is_active: bool):
    """Update listing active status"""
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE listings 
        SET is_approved = ?
        WHERE id = ?
    ''', (is_active, listing_id))
    conn.commit()
    conn.close()

def delete_listing(listing_id: int):
    """Delete listing and remove from favorites"""
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    
    # First, get users who favorited this listing
    cursor.execute('SELECT user_id FROM favorites WHERE listing_id = ?', (listing_id,))
    favorite_users = cursor.fetchall()
    
    # Delete from favorites
    cursor.execute('DELETE FROM favorites WHERE listing_id = ?', (listing_id,))
    
    # Delete the listing
    cursor.execute('DELETE FROM listings WHERE id = ?', (listing_id,))
    
    conn.commit()
    conn.close()
    
    return [user[0] for user in favorite_users]  # Return list of user IDs who had it favorited

def get_listing_favorites_users(listing_id: int):
    """Get users who favorited this listing"""
    conn = sqlite3.connect('real_estate.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM favorites WHERE listing_id = ?', (listing_id,))
    users = cursor.fetchall()
    conn.close()
    return [user[0] for user in users]

def get_posting_status_text(listing, user_lang):
    """Get status text for posting"""
    if listing[18] == 'pending':  # approval_status
        return get_text(user_lang, 'posting_status_pending')
    elif listing[18] == 'declined':
        return get_text(user_lang, 'posting_status_declined')
    elif listing[17]:  # is_approved (active)
        return get_text(user_lang, 'posting_status_active')
    else:
        return get_text(user_lang, 'posting_status_inactive')

def format_my_posting_display(listing, user_lang):
    """Format posting for owner view"""
    location_display = listing[8] if listing[8] else listing[7]
    status_text = get_posting_status_text(listing, user_lang)
    favorite_count = listing[22] if len(listing) > 22 else 0  # favorite_count from query
    
    listing_text = f"""
🆔 <b>E'lon #{listing[0]}</b>
📊 <b>Status:</b> {status_text}

🏠 <b>{listing[2]}</b>
🗺 <b>Manzil:</b> {location_display}
💰 <b>Narx:</b> {listing[9]:,} so'm
📐 <b>Maydon:</b> {listing[10]} m²
🚪 <b>Xonalar:</b> {listing[11]}

{get_text(user_lang, 'posting_stats', favorites=favorite_count)}

📝 <b>Tavsif:</b> {listing[3][:100]}{'...' if len(listing[3]) > 100 else ''}
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

# Handlers for My Postings
@dp.message(F.text.in_(['📝 Mening e\'lonlarim', '📝 Мои объявления', '📝 My Postings']))
async def my_postings_handler(message: Message):
    user_lang = get_user_language(message.from_user.id)
    postings = get_user_postings(message.from_user.id)
    
    if not postings:
        await message.answer(get_text(user_lang, 'no_my_postings'))
        return
    
    await message.answer(f"📝 Sizning e'lonlaringiz: {len(postings)} ta")
    
    for posting in postings[:5]:  # Show first 5
        posting_text = format_my_posting_display(posting, user_lang)
        is_active = posting[17]  # is_approved
        keyboard = get_posting_management_keyboard(
            posting[0], is_active, user_lang, is_admin(message.from_user.id)
        )
        
        # Show with photos if available
        photo_file_ids = json.loads(posting[15]) if posting[15] else []
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
    user_lang = get_user_language(callback_query.from_user.id)
    
    # Check ownership or admin rights
    listing = get_listing_by_id(listing_id)
    if not listing or (listing[1] != callback_query.from_user.id and not is_admin(callback_query.from_user.id)):
        await callback_query.answer("⛔ Ruxsat yo'q!")
        return
    
    # Activate the posting
    update_listing_status(listing_id, True)
    
    await callback_query.message.edit_reply_markup(
        reply_markup=get_posting_management_keyboard(
            listing_id, True, user_lang, is_admin(callback_query.from_user.id)
        )
    )
    await callback_query.answer(get_text(user_lang, 'posting_activated'))

@dp.callback_query(F.data.startswith('deactivate_post_'))
async def deactivate_posting(callback_query):
    listing_id = int(callback_query.data.split('_')[2])
    user_lang = get_user_language(callback_query.from_user.id)
    
    # Check ownership or admin rights
    listing = get_listing_by_id(listing_id)
    if not listing or (listing[1] != callback_query.from_user.id and not is_admin(callback_query.from_user.id)):
        await callback_query.answer("⛔ Ruxsat yo'q!")
        return
    
    # Deactivate the posting
    update_listing_status(listing_id, False)
    
    # Notify users who favorited it
    await notify_favorite_users_posting_unavailable(listing_id, listing[2])
    
    await callback_query.message.edit_reply_markup(
        reply_markup=get_posting_management_keyboard(
            listing_id, False, user_lang, is_admin(callback_query.from_user.id)
        )
    )
    await callback_query.answer(get_text(user_lang, 'posting_deactivated'))

@dp.callback_query(F.data.startswith('delete_post_'))
async def confirm_delete_posting(callback_query):
    listing_id = int(callback_query.data.split('_')[2])
    user_lang = get_user_language(callback_query.from_user.id)
    
    # Check ownership or admin rights
    listing = get_listing_by_id(listing_id)
    if not listing or (listing[1] != callback_query.from_user.id and not is_admin(callback_query.from_user.id)):
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
    user_lang = get_user_language(callback_query.from_user.id)
    
    # Check ownership or admin rights
    listing = get_listing_by_id(listing_id)
    if not listing or (listing[1] != callback_query.from_user.id and not is_admin(callback_query.from_user.id)):
        await callback_query.answer("⛔ Ruxsat yo'q!")
        return
    
    # Delete the posting and get users who favorited it
    favorite_users = delete_listing(listing_id)
    
    # Notify users who favorited it
    await notify_favorite_users_posting_deleted(favorite_users, listing[2], user_lang)
    
    await callback_query.message.edit_text(get_text(user_lang, 'posting_deleted'))
    await callback_query.answer()

@dp.callback_query(F.data.startswith('cancel_delete_'))
async def cancel_delete_posting(callback_query):
    listing_id = int(callback_query.data.split('_')[2])
    user_lang = get_user_language(callback_query.from_user.id)
    
    # Get posting and show management interface again
    listing = get_listing_by_id(listing_id)
    if listing:
        posting_text = format_my_posting_display(listing, user_lang)
        keyboard = get_posting_management_keyboard(
            listing_id, listing[17], user_lang, is_admin(callback_query.from_user.id)
        )
        
        await callback_query.message.edit_text(posting_text, reply_markup=keyboard)
    
    await callback_query.answer()

# Notification functions
async def notify_favorite_users_posting_unavailable(listing_id: int, listing_title: str):
    """Notify users when a favorited posting becomes unavailable"""
    favorite_users = get_listing_favorites_users(listing_id)
    
    for user_id in favorite_users:
        try:
            user_lang = get_user_language(user_id)
            message = get_text(user_lang, 'favorites_removed_notification', title=listing_title)
            await bot.send_message(chat_id=user_id, text=message)
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")

async def notify_favorite_users_posting_deleted(favorite_users: list, listing_title: str, user_lang: str):
    """Notify users when a favorited posting is deleted"""
    for user_id in favorite_users:
        try:
            message = get_text(user_lang, 'favorites_removed_notification', title=listing_title)
            await bot.send_message(chat_id=user_id, text=message)
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")


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