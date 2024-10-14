from flask import Flask, request, jsonify, render_template
from openai import OpenAI
import os

app = Flask(__name__)

#GPT-4o 복잡하고 여러s 단계로 구성된 작업을 위한 고지능 플래그십 모델

#o1-preview and o1-mini 복잡한 추론을 수행하기 위해 강화 학습으로 훈련된 언어 모델입니다.

# OpenAI API 키 설정
client = OpenAI(
    api_key="???",
)
conversation_history = []

def get_openai_response(user_input):
    global conversation_history
    conversation_history.append({"role": "user", "content": user_input})
    
    try:
        response =  client.chat.completions.create(  # ChatCompletion API 호출
            model="gpt-4",
            messages=conversation_history
        )
        bot_reply = response.choices[0].message.content  # 수정된 부분
        conversation_history.append({"role": "assistant", "content": bot_reply})
        return bot_reply
    except Exception as e:
        return f"Error: {str(e)}"


def generate_image(prompt):
    try:
        response = OpenAI.Image.create(
            prompt=prompt,
            n=1,
            size="512x512"
        )
        image_url = response['data'][0]['url']
        return image_url
    except Exception as e:
        return f"Image generation error: {str(e)}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.form['message']
    bot_reply = get_openai_response(user_message)
    return jsonify({'reply': bot_reply})


@app.route('/generate_image', methods=['POST'])
def generate_image_route():
    response = client.images.generate(
        model="dall-e-3",
        prompt= request.form['message'],
        size="1024x1024",
        quality="standard",
        n=1,
    )
    image_url = response.data[0].url
    return jsonify({'reply': "이미지를 생성했습니다.", 'image_url': image_url})
    
if __name__ == '__main__':
    app.run(debug=True)
