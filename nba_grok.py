from flask import Flask, request, render_template, jsonify
import requests
import os
from dotenv import load_dotenv
from datetime import datetime

env_path = os.path.join(os.path.dirname(__file__), '.env')
print("Looking for .env at:", env_path)  # Debug path
load_dotenv(env_path)
API_KEY = os.getenv("XAI_API_KEY")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
print("Loaded ODDS_API_KEY:", ODDS_API_KEY)  # Debug value
API_URL = "https://api.x.ai/v1/chat/completions"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"

app = Flask(__name__)

def query_grok(prompt):
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
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Oops! Something went wrong with the API: {str(e)}"

def get_betting_odds(query=None):
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "decimal"
    }
    try:
        response = requests.get(ODDS_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            # If query provided, filter for matching team
            if query:
                query_lower = query.lower()
                for game in data:
                    home_team = game["home_team"].lower()
                    away_team = game["away_team"].lower()
                    if any(team in query_lower for team in [home_team, away_team]):
                        bookmakers = game["bookmakers"][0]["markets"][0]["outcomes"]
                        return f"Bet on {game['home_team']} vs {game['away_team']}: {bookmakers[0]['name']} @ {bookmakers[0]['price']}"
            # Default: Show top 3 upcoming games
            bets = []
            for game in data[:3]:  # Limit to 3 popular bets
                home_team = game["home_team"]
                away_team = game["away_team"]
                bookmakers = game["bookmakers"][0]["markets"][0]["outcomes"]
                bet = f"Bet on {home_team} vs {away_team}: {bookmakers[0]['name']} @ {bookmakers[0]['price']}"
                bets.append(bet)
            return "\n".join(bets) if bets else "No upcoming NBA odds available."
        return "No upcoming NBA odds available right now."
    except Exception as e:
        return f"Betting odds error: {str(e)}"

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        query = request.form['query']
        response = query_grok(query)
        betting_proposal = get_betting_odds(query)
        return jsonify({'response': response, 'betting': betting_proposal})
    # Default: Show popular bets on page load
    popular_bets = get_betting_odds()
    return render_template('index.html', popular_bets=popular_bets)

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

# Chat log: https://grok.com/share/bGVnYWN5_e33c04e7-8eff-46b5-8cfd-226633279d2f
# https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44