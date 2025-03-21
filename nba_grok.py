from flask import Flask, request, render_template
import requests
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()
API_KEY = os.getenv("XAI_API_KEY")
API_URL = "https://api.x.ai/v1/chat/completions"

app = Flask(__name__)

def query_grok(prompt):
    # Get current date
    current_date = datetime.now().strftime('%Y-%m-%d')
    payload = {
        "model": "grok-2-1212",
        "messages": [
            {"role": "system", "content": (
                f"Today's date is {current_date}. You are a sports research assistant. For any NBA game query, "
                "fetch the most recent data available as of this date, using web or X search if needed. Provide "
                "the game date, matchup, final score, top scorer, and highest assists in a conversational tone. "
                "If the query is about the 'last' game, ensure it’s the most recent game played by that team in "
                "the 2024-25 season."
            )},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 500,
        "temperature": 0.7
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Oops! Something went wrong with the API: {str(e)}"

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        query = request.form['query']
        response = query_grok(query)
        return render_template('index.html', response=response)
    return render_template('index.html', response=None)

if __name__ == '__main__':
    app.run(debug=False)
    