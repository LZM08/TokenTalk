from flask import Flask, request, jsonify, render_template, redirect, session, url_for, make_response
from openai import OpenAI
import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, auth
import re

# 환경 변수 로드
dotenv_path = os.path.join(os.path.dirname(__file__), 'apikey', '.env')
load_dotenv(dotenv_path)
API_KEY = os.environ['OPENAI_API_KEY']
client = OpenAI(api_key=API_KEY)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # 세션 관리를 위한 시크릿 키

# Firebase 초기화
if not firebase_admin._apps:
    cred = credentials.Certificate("apikey/tokentalk-7662f-firebase-adminsdk-hokx1-8d7a9325b2.json")
    firebase_admin.initialize_app(cred)

firebase_config = {
    "apiKey": os.getenv('FIREBASE_API_KEY'),
    "authDomain": os.getenv('FIREBASE_AUTH_DOMAIN'),
    "projectId": os.getenv('FIREBASE_PROJECT_ID'),
    "storageBucket": os.getenv('FIREBASE_STORAGE_BUCKET'),
    "messagingSenderId": os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
    "appId": os.getenv('FIREBASE_APP_ID'),
    "measurementId": os.getenv('FIREBASE_MEASUREMENT_ID')
}

# 대화 기록을 저장할 딕셔너리 (사용자별로 구분)
conversation_histories = {}

# 이미지 관련 키워드 패턴
IMAGE_KEYWORDS = [
    r'그림', r'이미지', r'사진', r'picture', r'image', r'photo', r'draw',
    r'생성해', r'만들어', r'그려', r'보여줘', r'визуализировать', 
    r'illustrate', r'visualize', r'display', r'create', r'generate'
]

def contains_image_keywords(text):
    """메시지에 이미지 관련 키워드가 포함되어 있는지 확인"""
    pattern = '|'.join(IMAGE_KEYWORDS)
    return bool(re.search(pattern, text.lower()))

def generate_image(prompt):
    """DALL-E를 사용하여 이미지 생성"""
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        return response.data[0].url
    except Exception as e:
        print(f"Image generation error: {str(e)}")
        return None

@app.route('/login', methods=['POST'])
def login_post():
    if request.is_json:
        data = request.get_json()
        token = data.get('token')
        try:
            decoded_token = auth.verify_id_token(token)
            uid = decoded_token['uid']
            session['user_id'] = uid
            return jsonify({'success': True, 'uid': uid, 'redirect': '/chat'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400
    return jsonify({'success': False, 'message': 'Invalid request'}), 400

@app.route('/login')
def login_get():
    return render_template('login.html', firebase_config=firebase_config)

@app.route('/')
def home():
    return redirect('/login')

@app.route('/chat')
def chat_page():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('chat.html', firebase_config=firebase_config)

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()  # 세션 지우기

    # 세션 쿠키 삭제
    resp = make_response(redirect(url_for('login_get')))
    resp.set_cookie('user_id', '', expires=0)

    # 캐시 방지 설정
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'

    return resp

def get_openai_response(user_input, user_id):
    """사용자 요청에 따라 OpenAI API를 사용하여 텍스트 또는 이미지 응답 생성"""
    if user_id not in conversation_histories:
        conversation_histories[user_id] = []
    
    # 이미지 키워드가 있는지 확인
    should_generate_image = contains_image_keywords(user_input)
    
    # 이미지 생성 로직
    if should_generate_image:
        image_prompt = f"Generate an image for: '{user_input}'"
        image_url = generate_image(image_prompt)
        return None, image_url  # 텍스트 응답 없이 이미지 URL만 반환

    # 텍스트 응답 생성 로직
    conversation_histories[user_id].append({"role": "user", "content": user_input})
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=conversation_histories[user_id]
        )
        bot_reply = response.choices[0].message.content
        conversation_histories[user_id].append({"role": "assistant", "content": bot_reply})
        return bot_reply, None  # 텍스트 응답만 반환, 이미지 없음
    except Exception as e:
        return f"Error: {str(e)}", None

@app.route('/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_message = request.form['message']
    bot_reply, image_url = get_openai_response(user_message, session['user_id'])
    
    response_data = {}
    if bot_reply:
        response_data['reply'] = bot_reply
    if image_url:
        response_data['image_url'] = image_url
    
    return jsonify(response_data)

@app.route('/generate_image', methods=['POST'])
def generate_image_route():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        # 이미지 생성 요청을 OpenAI API에 보내기
        image_url = generate_image(request.form['message'])
        if image_url:
            return jsonify({'image_url': image_url})  # 'reply' 없이 image_url만 반환
        else:
            return jsonify({'error': 'Failed to generate image'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
