from flask import Flask, request, jsonify, render_template, redirect, session, url_for, make_response
from openai import OpenAI
import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, auth

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
    # Firebase 설정을 템플릿에 전달
    return render_template('login.html', firebase_config=firebase_config)


@app.route('/')
def home():
    return redirect('/login')


@app.route('/chat')
def chat_page():
    if 'user_id' not in session:
        return redirect('/login')  # 'firebase_config'는 이제 필요 없음
    return render_template('chat.html', firebase_config=firebase_config)



@app.route('/logout', methods=['POST'])  # POST 메서드로 설정
def logout():
    session.clear()  # 세션 지우기

    # 세션 쿠키 삭제
    resp = make_response(redirect(url_for('login_get')))  # 로그인 페이지로 리디렉션
    resp.set_cookie('user_id', '', expires=0)  # 쿠키를 만료시켜 삭제

    # 캐시 방지 설정
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'

    return resp  # 수정된 응답 반환


def get_openai_response(user_input, user_id):
    if user_id not in conversation_histories:
        conversation_histories[user_id] = []
    
    conversation_histories[user_id].append({"role": "user", "content": user_input})
    
    try:
        response = client.chat.completions.create(
            model="gpt-4",  # gpt-4o 대신 gpt-4 사용
            messages=conversation_histories[user_id]
        )
        bot_reply = response.choices[0].message.content
        conversation_histories[user_id].append({"role": "assistant", "content": bot_reply})
        return bot_reply
    except Exception as e:
        return f"Error: {str(e)}"


@app.route('/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_message = request.form['message']
    bot_reply = get_openai_response(user_message, session['user_id'])
    return jsonify({'reply': bot_reply})


@app.route('/generate_image', methods=['POST'])
def generate_image_route():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        # 이미지 생성 요청을 OpenAI API에 보내기
        response = client.images.generate(
            model="dall-e-3",
            prompt=request.form['message'],
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        return jsonify({'reply': "이미지를 생성했습니다.", 'image_url': image_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
