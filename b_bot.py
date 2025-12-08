import asyncio
import json
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F, Router  # <-- F импортируется из aiogram
from aiogram.filters import Command  # <-- Command импортируется из aiogram.filters
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.enums import ParseMode
from aiohttp import web
import aiohttp_cors
import logging

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = '7621395336:AAEWMZ2qify1tMHCwYp1e4XpiKHSFdM7opo'
ADMIN_IDS = [7630810979, 7513998193]  # Два администратора
WEB_SERVER_PORT = 3000
# Разрешённые IP только для админ-панели сайта
ALLOWED_ADMIN_IPS = ['178.172.246.19', '127.0.0.1']
# ===============================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('reviews.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            text TEXT NOT NULL,
            rating INTEGER NOT NULL,
            date TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            country TEXT,
            telegram_message_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deleted_reviews (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            text TEXT NOT NULL,
            rating INTEGER NOT NULL,
            date TEXT NOT NULL,
            deleted_by TEXT,
            deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Сохраняем настройки IP
    cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', 
                   ('allowed_admin_ips', ','.join(ALLOWED_ADMIN_IPS)))
    
    conn.commit()
    conn.close()

# Функции работы с БД
def add_review_to_db(name, text, rating, ip_address=None, user_agent=None, country=None):
    try:
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        
        date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO reviews (name, text, rating, date, ip_address, user_agent, country)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, text, rating, date, ip_address, user_agent, country))
        
        review_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Отзыв добавлен в БД с ID: {review_id}")
        return review_id
    except Exception as e:
        logger.error(f"Ошибка при добавлении отзыва в БД: {e}")
        return None

def get_reviews(limit=100, offset=0):
    try:
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, name, text, rating, date, created_at 
            FROM reviews 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        reviews = cursor.fetchall()
        conn.close()
        return reviews
    except Exception as e:
        logger.error(f"Ошибка при получении отзывов: {e}")
        return []

def delete_review(review_id, deleted_by='telegram_bot'):
    try:
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        
        # Сохраняем в архив удалённых отзывов
        cursor.execute('SELECT * FROM reviews WHERE id = ?', (review_id,))
        review = cursor.fetchone()
        
        if review:
            cursor.execute('''
                INSERT INTO deleted_reviews (id, name, text, rating, date, deleted_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (review[0], review[1], review[2], review[3], review[4], deleted_by))
        
        # Удаляем из основной таблицы
        cursor.execute('DELETE FROM reviews WHERE id = ?', (review_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при удалении отзыва: {e}")
        return False

def get_stats():
    try:
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM reviews')
        total_reviews = cursor.fetchone()[0]
        
        cursor.execute('SELECT AVG(rating) FROM reviews')
        avg_rating = cursor.fetchone()[0] or 0
        
        # Отзывы за сегодня
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('SELECT COUNT(*) FROM reviews WHERE DATE(created_at) = ?', (today,))
        today_reviews = cursor.fetchone()[0]
        
        conn.close()
        return {
            'total_reviews': total_reviews,
            'avg_rating': round(avg_rating, 1),
            'today_reviews': today_reviews
        }
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        return None

# Веб-сервер для API
async def handle_get_reviews(request):
    """Получить все отзывы - доступно всем пользователям из любой страны"""
    try:
        limit = int(request.query.get('limit', 100))
        offset = int(request.query.get('offset', 0))
        
        reviews = get_reviews(limit, offset)
        reviews_list = []
        
        for review in reviews:
            id, name, text, rating, date, created_at = review
            reviews_list.append({
                'id': id,
                'name': name,
                'text': text,
                'rating': rating,
                'date': date,
                'created_at': created_at
            })
        
        return web.json_response({
            'reviews': reviews_list, 
            'total': len(reviews_list),
            'message': 'Добро пожаловать! Отзывы доступны пользователям со всего мира 🌍'
        })
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def handle_add_review(request):
    """Добавить отзыв с сайта - доступно всем пользователям из любой страны"""
    try:
        data = await request.json()
        ip_address = request.remote
        user_agent = request.headers.get('User-Agent', '')
        
        name = data.get('name', 'Аноним')
        text = data.get('text', '')
        rating = data.get('rating', 5)
        
        # Простая защита от спама
        if not text or len(text.strip()) < 5:
            return web.json_response({'error': 'Текст отзыва должен содержать минимум 5 символов'}, status=400)
        
        if len(text) > 2000:
            return web.json_response({'error': 'Текст отзыва слишком длинный (максимум 2000 символов)'}, status=400)
        
        if rating < 1 or rating > 5:
            rating = 5
        
        # Принимаем отзывы от пользователей из ВСЕХ СТРАН без ограничений
        country = "International 🌍"
        
        review_id = add_review_to_db(name, text, rating, ip_address, user_agent, country)
        
        if review_id:
            # Уведомляем всех админов в Telegram
            stars = '⭐' * rating
            admin_message = (
                f"🌐 <b>НОВЫЙ ОТЗЫВ С САЙТА</b>\n\n"
                f"👤 <b>Имя:</b> {name}\n"
                f"⭐ <b>Оценка:</b> {rating}/5 {stars}\n"
                f"💬 <b>Текст:</b> {text[:200]}...\n"
                f"🌍 <b>Страна:</b> {country}\n"
                f"🌐 <b>IP:</b> {ip_address}\n"
                f"🕒 <b>Время:</b> {datetime.now().strftime('%H:%M %d.%m.%Y')}\n"
                f"📌 <b>ID отзыва:</b> #{review_id}"
            )
            
            # Отправляем уведомление всем админам
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, admin_message, parse_mode=ParseMode.HTML)
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")
            
            return web.json_response({
                'success': True,
                'message': '✅ Отзыв успешно добавлен! Спасибо за ваш отзыв из любой точки мира! 🌍',
                'review_id': review_id
            })
        else:
            return web.json_response({'error': 'Ошибка сохранения отзыва'}, status=500)
            
    except Exception as e:
        logger.error(f"Ошибка в API добавления отзыва: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def handle_admin_stats(request):
    """Статистика для админ-панели (только для разрешённых IP)"""
    try:
        client_ip = request.remote
        
        # Проверяем IP только для админ-панели
        if client_ip not in ALLOWED_ADMIN_IPS and client_ip != '127.0.0.1':
            if not client_ip.startswith('192.168.'):
                return web.json_response({
                    'error': 'Доступ к админ-панели запрещён. Отзывы могут оставлять пользователи из всех стран.',
                    'access_type': 'public'
                }, status=403)
        
        stats = get_stats()
        
        # Получаем последние отзывы
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, name, text, rating, date, ip_address, country, created_at 
            FROM reviews 
            ORDER BY created_at DESC 
            LIMIT 50
        ''')
        reviews = cursor.fetchall()
        conn.close()
        
        reviews_list = []
        for review in reviews:
            id, name, text, rating, date, ip_address, country, created_at = review
            reviews_list.append({
                'id': id,
                'name': name,
                'text': text,
                'rating': rating,
                'date': date,
                'ip_address': ip_address,
                'country': country,
                'created_at': created_at
            })
        
        return web.json_response({
            'stats': stats,
            'reviews': reviews_list,
            'allowed_admin_ips': ALLOWED_ADMIN_IPS,
            'your_ip': client_ip,
            'message': 'Админ панель доступна только с разрешённых IP. Отзывы могут оставлять все пользователи 🌍'
        })
        
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)

async def handle_delete_review(request):
    """Удалить отзыв (только для админа по IP)"""
    try:
        client_ip = request.remote
        
        # Проверяем IP только для админ-панели
        if client_ip not in ALLOWED_ADMIN_IPS and client_ip != '127.0.0.1':
            if not client_ip.startswith('192.168.'):
                return web.json_response({
                    'error': 'Доступ к админ-панели запрещён',
                    'access_type': 'public'
                }, status=403)
        
        data = await request.json()
        review_id = data.get('review_id')
        
        if not review_id:
            return web.json_response({'error': 'Не указан ID отзыва'}, status=400)
        
        success = delete_review(review_id, deleted_by=f'site_admin_{client_ip}')
        
        if success:
            # Уведомляем всех админов в Telegram
            admin_message = (
                f"🗑 <b>ОТЗЫВ УДАЛЁН ЧЕРЕЗ САЙТ</b>\n\n"
                f"📌 <b>ID отзыва:</b> #{review_id}\n"
                f"🌐 <b>Админ IP:</b> {client_ip}\n"
                f"🕒 <b>Время:</b> {datetime.now().strftime('%H:%M %d.%m.%Y')}"
            )
            
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, admin_message, parse_mode=ParseMode.HTML)
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")
            
            return web.json_response({
                'success': True, 
                'message': 'Отзыв удалён'
            })
        else:
            return web.json_response({'error': 'Ошибка удаления отзыва'}, status=500)
            
    except Exception as e:
        logger.error(f"Ошибка при удалении отзыва: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def start_web_server():
    """Запуск веб-сервера для API"""
    app = web.Application()
    
    # Настройка CORS - разрешаем доступ со всех доменов
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    })
    
    # Маршруты API
    # Публичные маршруты (доступны всем пользователям из любых стран)
    app.router.add_get('/api/reviews', handle_get_reviews)
    app.router.add_post('/api/reviews', handle_add_review)
    
    # Защищённые маршруты (только для админов с разрешённых IP)
    app.router.add_get('/api/admin/stats', handle_admin_stats)
    app.router.add_post('/api/admin/delete', handle_delete_review)
    
    # Проверка здоровья сервера
    app.router.add_get('/health', lambda r: web.Response(
        text='✅ Сервер работает. Отзывы доступны пользователям со всего мира 🌍'
    ))
    
    # Применяем CORS ко всем маршрутам
    for route in list(app.router.routes()):
        cors.add(route)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', WEB_SERVER_PORT)
    await site.start()
    logger.info(f"🌐 Веб-сервер запущен на порту {WEB_SERVER_PORT}")
    logger.info(f"🌍 Доступен пользователям из всех стран")

# ========== КОМАНДЫ БОТА ==========
@router.message(Command("start"))
async def start_command(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='📝 Оставить отзыв', callback_data='leave_review'),
            InlineKeyboardButton(text='⭐ Посмотреть отзывы', callback_data='view_reviews')
        ]
    ])
    
    # Проверяем, является ли пользователь администратором
    is_admin = message.from_user.id in ADMIN_IDS
    
    if is_admin:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text='👑 Админ панель', callback_data='admin_panel')
        ])
    
    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n"
        f"Я бот для управления отзывами сайта Coin2Game.\n\n"
        f"📌 Что я умею:\n"
        f"• 📝 Принимать отзывы\n"
        f"• ⭐ Показывать отзывы других пользователей\n"
        f"• 📊 Показывать статистику\n"
        f"• 🔄 Синхронизировать отзывы с сайтом\n\n"
        f"🌍 <b>Доступно пользователям из всех стран!</b>"
    )
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

@router.message(Command("admin"))
async def admin_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас нет прав администратора")
        return
    
    stats = get_stats()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📊 Статистика', callback_data='stats')],
        [InlineKeyboardButton(text='🗑 Управление отзывами', callback_data='manage_reviews')],
        [InlineKeyboardButton(text='🌐 Настройки сайта', callback_data='site_settings')]
    ])
    
    await message.answer(
        f"👑 <b>АДМИН ПАНЕЛЬ</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего отзывов: {stats['total_reviews']}\n"
        f"• Средний рейтинг: {stats['avg_rating']}/5\n"
        f"• Сегодня: {stats['today_reviews']} отзывов\n\n"
        f"🌐 <b>API сервер:</b> http://localhost:{WEB_SERVER_PORT}\n"
        f"🔑 <b>Админ IP:</b> {len(ALLOWED_ADMIN_IPS)} адресов\n"
        f"👥 <b>Администраторы:</b> {len(ADMIN_IDS)} пользователя\n"
        f"🌍 <b>Доступ:</b> ОТКРЫТ ДЛЯ ВСЕХ СТРАН МИРА! 🌎",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data == 'leave_review')
async def leave_review_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    await bot.send_message(
        callback_query.from_user.id,
        "✍️ <b>Оставьте отзыв</b>\n\n"
        "Пожалуйста, напишите ваш отзыв в формате:\n\n"
        "👤 <b>Имя:</b> [ваше имя]\n"
        "⭐ <b>Оценка:</b> [от 1 до 5]\n"
        "💬 <b>Текст:</b> [ваш отзыв]\n\n"
        "<b>Пример:</b>\n"
        "<code>Имя: Алексей\n"
        "Оценка: 5\n"
        "Текст: Отличный сервис, всё быстро!</code>\n\n"
        "🌍 <b>Бот доступен пользователям из всех стран мира!</b>",
        parse_mode=ParseMode.HTML
    )

@router.message()
async def handle_message(message: types.Message):
    text = message.text
    
    # Пропускаем команды
    if text.startswith('/'):
        return
    
    # Проверяем, является ли сообщение отзывом
    if ('Имя:' in text or 'имя:' in text or 'Name:' in text.lower() or 
        'Nombre:' in text.lower() or 'Nom:' in text.lower() or '名字:' in text):
        
        try:
            # Парсим отзыв (поддерживаем разные языки)
            lines = text.split('\n')
            data = {}
            
            for line in lines:
                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        key = parts[0].strip().lower()
                        value = parts[1].strip()
                        
                        # Поддержка разных языков для имени
                        if key in ['имя', 'name', 'nombre', 'nom', '名字', 'nome']:
                            data['name'] = value
                        # Поддержка разных языков для оценки
                        elif key in ['оценка', 'rating', 'score', 'puntuación', 'note', '评分']:
                            data['rating'] = value
                        # Поддержка разных языков для текста
                        elif key in ['текст', 'text', 'review', 'reseña', 'avis', '评论']:
                            data['text'] = value
            
            name = data.get('name', message.from_user.first_name or 'Аноним')
            rating_str = data.get('rating', '5')
            review_text = data.get('text', '')
            
            # Если нет текста в данных, проверяем остаток сообщения
            if not review_text:
                for line in lines:
                    if not (':' in line and any(keyword in line.lower() for keyword in 
                            ['имя:', 'name:', 'оценка:', 'rating:', 'score:', 'текст:', 'text:', 'review:'])):
                        if line.strip():
                            review_text += line.strip() + ' '
            
            if not review_text.strip():
                await message.answer("❌ Пожалуйста, добавьте текст отзыва.")
                return
            
            try:
                rating = int(''.join(filter(str.isdigit, rating_str)))
                if rating < 1 or rating > 5:
                    rating = 5
            except:
                rating = 5
            
            # Сохраняем отзыв
            review_id = add_review_to_db(name, review_text, rating, country="Telegram")
            
            if review_id:
                await message.answer(
                    f"✅ <b>Спасибо за ваш отзыв, {name}!</b>\n\n"
                    f"⭐ <b>Оценка:</b> {rating}/5\n"
                    f"💬 <b>Текст:</b> {review_text[:100]}...\n\n"
                    f"Отзыв сохранён и будет показан на сайте.\n"
                    f"🌍 <b>Доступно пользователям из всех стран!</b>",
                    parse_mode=ParseMode.HTML
                )
                
                # Уведомляем всех админов
                stars = '⭐' * rating
                admin_message = (
                    f"📝 <b>НОВЫЙ ОТЗЫВ В БОТЕ</b>\n\n"
                    f"👤 <b>Имя:</b> {name}\n"
                    f"⭐ <b>Оценка:</b> {rating}/5 {stars}\n"
                    f"💬 <b>Текст:</b> {review_text[:200]}...\n"
                    f"👤 <b>От:</b> @{message.from_user.username or message.from_user.full_name}\n"
                    f"🌍 <b>Страна:</b> Telegram (International)\n"
                    f"🕒 <b>Время:</b> {datetime.now().strftime('%H:%M %d.%m.%Y')}\n"
                    f"📌 <b>ID отзыва:</b> #{review_id}"
                )
                
                for admin_id in ADMIN_IDS:
                    try:
                        await bot.send_message(admin_id, admin_message, parse_mode=ParseMode.HTML)
                    except Exception as e:
                        logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")
                
            else:
                await message.answer("❌ Ошибка сохранения отзыва. Попробуйте ещё раз.")
                
        except Exception as e:
            logger.error(f"Ошибка обработки отзыва: {e}")
            await message.answer("❌ Ошибка обработки отзыва. Пожалуйста, используйте правильный формат.")
    
    # Если это просто сообщение (не отзыв)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='📝 Оставить отзыв', callback_data='leave_review')]
        ])
        
        await message.answer(
            "Хотите оставить отзыв о нашем сервисе?\n\n"
            "Вы можете использовать:\n"
            "• Русский: Имя: ... Оценка: ... Текст: ...\n"
            "• English: Name: ... Rating: ... Text: ...\n"
            "• Español: Nombre: ... Puntuación: ... Texto: ...\n"
            "• Français: Nom: ... Note: ... Avis: ...\n"
            "• 中文: 名字: ... 评分: ... 评论: ...\n\n"
            "🌍 <b>Бот поддерживает все языки!</b>",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

@router.callback_query(F.data == 'view_reviews')
async def view_reviews_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    reviews = get_reviews(5)
    
    if reviews:
        response = "⭐ <b>Последние отзывы:</b>\n\n"
        for review in reviews:
            id, name, text, rating, date, created_at = review
            stars = '⭐' * rating + '☆' * (5 - rating)
            response += f"👤 <b>{name}</b> ({date})\n"
            response += f"{stars}\n"
            response += f"{text[:100]}...\n\n"
            response += f"🆔 #{id}\n"
            response += "─" * 30 + "\n\n"
    else:
        response = "📭 Пока нет отзывов. Будьте первым!\n🌍 Доступно для пользователей из всех стран!"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='📝 Оставить отзыв', callback_data='leave_review'),
            InlineKeyboardButton(text='🔄 Обновить', callback_data='view_reviews')
        ]
    ])
    
    await bot.send_message(callback_query.from_user.id, response, 
                         reply_markup=keyboard, parse_mode=ParseMode.HTML)

@router.callback_query(F.data == 'stats')
async def stats_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    stats = get_stats()
    if stats:
        response = (
            f"📊 <b>Статистика отзывов</b>\n\n"
            f"📈 <b>Всего отзывов:</b> {stats['total_reviews']}\n"
            f"⭐ <b>Средний рейтинг:</b> {stats['avg_rating']}/5\n"
            f"📅 <b>Сегодня:</b> {stats['today_reviews']} отзывов\n\n"
            f"🕒 <b>Обновлено:</b> {datetime.now().strftime('%H:%M %d.%m.%Y')}\n"
            f"🌍 <b>Доступ:</b> Открыт для всех стран"
        )
    else:
        response = "❌ Не удалось получить статистику"
    
    await bot.send_message(callback_query.from_user.id, response, parse_mode=ParseMode.HTML)

@router.message(Command("delete"))
async def delete_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("🚫 У вас нет прав администратора")
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Использование: /delete <ID_отзыва>")
            return
        
        review_id = int(args[1])
        success = delete_review(review_id, deleted_by=f'telegram_command_{message.from_user.id}')
        
        if success:
            admin_message = (
                f"🗑 <b>ОТЗЫВ УДАЛЁН КОМАНДОЙ</b>\n\n"
                f"📌 <b>ID отзыва:</b> #{review_id}\n"
                f"👤 <b>Удалил:</b> @{message.from_user.username or message.from_user.full_name}\n"
                f"🕒 <b>Время:</b> {datetime.now().strftime('%H:%M %d.%m.%Y')}"
            )
            
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, admin_message, parse_mode=ParseMode.HTML)
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")
            
            await message.answer(f"✅ Отзыв #{review_id} удалён")
        else:
            await message.answer(f"❌ Не удалось удалить отзыв #{review_id}")
            
    except ValueError:
        await message.answer("❌ Неверный ID отзыва")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

# Запуск бота
async def main():
    # Инициализация БД
    init_db()
    logger.info("🤖 Бот запускается...")
    logger.info("🌍 Бот доступен пользователям из всех стран мира!")
    
    # Запускаем веб-сервер
    await start_web_server()
    
    # Уведомляем всех админов о запуске
    stats = get_stats()
    startup_message = (
        f"🚀 <b>БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ!</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Отзывов в базе: {stats['total_reviews']}\n"
        f"• Средний рейтинг: {stats['avg_rating']}/5\n"
        f"• Сегодня: {stats['today_reviews']} отзывов\n\n"
        f"🌐 <b>API сервер:</b> http://localhost:{WEB_SERVER_PORT}\n"
        f"🔑 <b>Админ IP:</b> {len(ALLOWED_ADMIN_IPS)} адресов\n"
        f"👥 <b>Администраторы:</b> {len(ADMIN_IDS)} пользователя\n"
        f"🌍 <b>Доступ:</b> ОТКРЫТ ДЛЯ ВСЕХ СТРАН МИРА! 🌎"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, startup_message, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")
    
    logger.info("✅ Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
