from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import os
import sqlite3
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Разрешить CORS для всех доменов

# Настройки
BOT_TOKEN = os.environ.get('BOT_TOKEN', '7621395336:AAEWMZ2qify1tMHCwYp1e4XpiKHSFdM7opo')
ADMIN_IDS = json.loads(os.environ.get('ADMIN_IDS', '[7630810979, 7513998193]'))

# Инициализация БД
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

@app.route('/api/reviews', methods=['GET'])
def get_reviews():
    """Получить все отзывы"""
    try:
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, text, rating, date, created_at FROM reviews ORDER BY created_at DESC LIMIT 100')
        reviews = cursor.fetchall()
        conn.close()
        
        reviews_list = []
        for review in reviews:
            reviews_list.append({
                'id': review[0],
                'name': review[1],
                'text': review[2],
                'rating': review[3],
                'date': review[4],
                'created_at': review[5]
            })
        
        return jsonify({
            'success': True,
            'reviews': reviews_list,
            'total': len(reviews_list)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reviews', methods=['POST'])
def add_review():
    """Добавить новый отзыв"""
    try:
        data = request.json
        name = data.get('name', 'Аноним')
        text = data.get('text', '')
        rating = data.get('rating', 5)
        
        if not text or len(text.strip()) < 5:
            return jsonify({'error': 'Текст отзыва должен содержать минимум 5 символов'}), 400
        
        if len(text) > 2000:
            return jsonify({'error': 'Текст отзыва слишком длинный (максимум 2000 символов)'}), 400
        
        if rating < 1 or rating > 5:
            rating = 5
        
        date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        conn = sqlite3.connect('reviews.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reviews (name, text, rating, date)
            VALUES (?, ?, ?, ?)
        ''', (name, text, rating, date))
        
        review_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Отправляем уведомление в Telegram
        send_telegram_notification(review_id, name, text, rating)
        
        return jsonify({
            'success': True,
            'message': '✅ Отзыв успешно добавлен!',
            'review_id': review_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def send_telegram_notification(review_id, name, text, rating):
    """Отправка уведомления в Telegram"""
    import requests
    
    stars = '⭐' * rating
    message = (
        f"📝 *Новый отзыв на Coin2Game*\n\n"
        f"👤 *Имя:* {name}\n"
        f"⭐ *Рейтинг:* {rating}/5 {stars}\n"
        f"💬 *Текст:* {text[:200]}{'...' if len(text) > 200 else ''}\n\n"
        f"📌 *ID отзыва:* #{review_id}"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': admin_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            requests.post(url, json=payload)
        except Exception as e:
            print(f"Ошибка отправки в Telegram: {e}")

@app.route('/health', methods=['GET'])
def health():
    """Проверка здоровья сервера"""
    return jsonify({
        'status': 'healthy',
        'service': 'Coin2Game API',
        'message': '✅ Сервер работает. Отзывы доступны пользователям со всего мира 🌍'
    })

@app.route('/', methods=['GET'])
def index():
    """Главная страница API"""
    return jsonify({
        'service': 'Coin2Game API',
        'version': '1.0',
        'endpoints': {
            'GET /api/reviews': 'Получить все отзывы',
            'POST /api/reviews': 'Добавить новый отзыв',
            'GET /health': 'Проверка здоровья сервера'
        }
    })

if __name__ == '__main__':
    # Инициализация БД при запуске
    init_db()
    print("✅ База данных инициализирована")
    print("🚀 API сервер запущен на порту 10000")
    
    # Запуск Flask приложения
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
