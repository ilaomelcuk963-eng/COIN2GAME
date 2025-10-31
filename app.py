from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'rofle-secret-key-1488'
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Настройки email
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'port': 587,
    'sender_email': 'ilaomelcuk963@gmail.com',  # Замените на email для отправки
    'password': 'ilaomel2011',  # Пароль приложения Gmail
    'receiver_email': 'ilaomelcuk963@gmail.com'  # Email для уведомлений
}

SPECIAL_LINKS = {
    '1488': 'https://www.bluestacks.com/ru/blog/redeem-codes/grand-mobile-redeem-codes-ru.html'  # Замените на вашу спец ссылку
}

def send_email_notification(user_ip, password_used, user_agent):
    try:
        message = MIMEMultipart()
        message['From'] = EMAIL_CONFIG['sender_email']
        message['To'] = EMAIL_CONFIG['receiver_email']
        message['Subject'] = '🚨 НОВЫЙ ДОСТУП К ROFL CHEATS!'
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background: #f0f0f0; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1);">
                <h2 style="color: #ff3366; text-align: center;">⚠️ КТО-ТО ВВЕЛ ПАРОЛЬ НА ROFL CHEATS!</h2>
                
                <div style="background: #fff5f5; padding: 15px; border-radius: 8px; border-left: 4px solid #ff3366; margin: 20px 0;">
                    <h3 style="color: #333; margin-top: 0;">📋 Детали доступа:</h3>
                    <p><strong>🕐 Время:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>🌐 IP адрес:</strong> {user_ip}</p>
                    <p><strong>🔑 Введенный пароль:</strong> <span style="color: #ff3366; font-weight: bold;">{password_used}</span></p>
                    <p><strong>💻 Браузер:</strong> {user_agent}</p>
                </div>
                
                <div style="background: #e6f7ff; padding: 15px; border-radius: 8px; border-left: 4px solid #1890ff; margin: 20px 0;">
                    <h4 style="color: #333; margin-top: 0;">📍 Действие:</h4>
                    <p>Пользователь получил доступ к защищенному контенту и был перенаправлен по специальной ссылке.</p>
                </div>
                
                <hr style="border: none; border-top: 2px dashed #ddd;">
                <p style="text-align: center; color: #666; font-size: 12px;">
                    <em>Автоматическое уведомление от системы безопасности ROFL Cheats</em>
                </p>
            </div>
        </body>
        </html>
        """
        
        message.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['port'])
        server.starttls()
        server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['password'])
        server.send_message(message)
        server.quit()
        
        print(f"✅ Email отправлен на {EMAIL_CONFIG['receiver_email']}")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки email: {e}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/check_password', methods=['POST'])
def check_password():
    password = request.form.get('password')
    if password == '1488':
        session['authenticated'] = True
        
        # Отправка уведомления на email
        user_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        user_agent = request.headers.get('User-Agent', 'Неизвестно')
        
        send_email_notification(user_ip, password, user_agent)
        
        # Перенаправление по специальной ссылке
        return redirect(SPECIAL_LINKS.get('1488', '/'))
    else:
        # Возврат с ошибкой
        return redirect('/?error=1')

@app.route('/special/<password>')
def special_redirect(password):
    if password in SPECIAL_LINKS:
        session['authenticated'] = True
        return redirect(SPECIAL_LINKS[password])
    else:
        return redirect('/')

if __name__ == '__main__':
    # Создаем папку templates если её нет
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    app.run(debug=True, host='0.0.0.0', port=5000)