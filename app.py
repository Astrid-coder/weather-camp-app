from flask import Flask, render_template, request
from rag_agent import answer_question_with_weather_info

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    user_message = None
    answer = None

    if request.method == 'POST':
        user_message = request.form.get('message')

        if user_message:
            answer = answer_question_with_weather_info(user_message)

    return render_template('index.html', user_message=user_message, answer=answer)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)