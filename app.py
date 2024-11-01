from flask import Flask, request, jsonify, render_template, redirect, session, url_for, make_response
from openai import OpenAI
import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, auth, firestore
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
dotenv_path = os.path.join(os.path.dirname(__file__), 'apikey', '.env')
load_dotenv(dotenv_path)
API_KEY = os.environ['OPENAI_API_KEY']
client = OpenAI(api_key=API_KEY)
app.secret_key = os.urandom(24)  # 세션 관리를 위한 시크릿 키

# Firebase 초기화
if not firebase_admin._apps:
    cred = credentials.Certificate("apikey/tokentalk-7662f-firebase-adminsdk-hokx1-8d7a9325b2.json")
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://tokentalk-7662f-default-rtdb.firebaseio.com/'
    })

db = firestore.client()

# Firebase 설정
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

# 이미지 키워드 
IMAGE_KEYWORDS = [
    r'그림', r'이미지', r'사진', r'picture', r'image', r'photo', r'draw',
    r'생성해', r'만들어', r'그려', r'보여줘', r'визуализировать', 
    r'illustrate', r'visualize', r'display', r'create', r'generate'
]

def contains_image_keywords(text):
    """이미지 키워드 있는지"""
    pattern = '|'.join(IMAGE_KEYWORDS)
    return bool(re.search(pattern, text.lower()))

def generate_image(prompt):
    """DALL-E 이미지 생성"""
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

            # Firebase에서 채팅 기록 로드
            conversation_histories[uid] = load_chat_history(uid)
            print(f"Loaded chat history for user {uid}: {conversation_histories[uid]}")

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
    
    user_id = session['user_id']
    chat_history = conversation_histories.get(user_id, [])
    return render_template('chat.html', firebase_config=firebase_config, chat_history=chat_history)

@app.route('/logout', methods=['POST'])
def logout():
    # 세션 지우기
    session.clear()  
    
    # 세션 쿠키 삭제
    resp = make_response(redirect(url_for('login_get')))
    resp.set_cookie('user_id', '', expires=0)
    
    # 캐시 방지 설정
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

def save_conversation_history(user_id):
    """대화 기록을 Firestore에 저장"""
    db.collection('conversations').document(user_id).set({
        'history': conversation_histories[user_id]
    })

def load_chat_history(user_id):
    """Firebase에서 사용자 채팅 기록을 불러오기"""
    doc_ref = db.collection('chat_histories').document(user_id)
    history = doc_ref.get()
    if history.exists:
        return history.to_dict().get('history', [])
    else:
        return []

@app.route('/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_message = request.form['message']
    user_id = session['user_id']
    
    # 이미지 키워드
    if contains_image_keywords(user_message):
        try:
            image_url = generate_image(user_message)
            if image_url:
                # 이미지 URL, 간단한 응답 메시지 반환
                response_data = {
                    'reply': "이미지를 생성했습니다:",
                    'image_url': image_url
                }
                # 대화 기록에 저장
                if user_id not in conversation_histories:
                    conversation_histories[user_id] = []

                conversation_histories[user_id].append({"role": "user", "content": user_message})
                conversation_histories[user_id].append({"role": "assistant", "content": "이미지를 생성했습니다."})
                save_conversation_history(user_id)
                return jsonify(response_data)
            else:
                return jsonify({
                    'reply': "이미지 생성에 실패했습니다. 다시 시도해주세요."
                })
        except Exception as e:
            return jsonify({
                'reply': f"이미지 생성 중 오류가 발생했습니다: {str(e)}"
            })
    
    #텍스트 응답
    try:
        if user_id not in conversation_histories:
            conversation_histories[user_id] = []
    
        conversation_histories[user_id].append({"role": "user", "content": user_message})
        response = client.chat.completions.create(
            model="gpt-4o",  
            messages=conversation_histories[user_id]
        )
        bot_reply = response.choices[0].message.content
        conversation_histories[user_id].append({"role": "assistant", "content": bot_reply})
        save_conversation_history(user_id)
        return jsonify({'reply': bot_reply})
        
    except Exception as e:
        return jsonify({'reply': f"Error: {str(e)}"})

if __name__ == '__main__':
    app.run(debug=True)