from flask import Flask, request, render_template, jsonify
import requests
import os
from dotenv import load_dotenv
from datetime import datetime

env_path = os.path.join(os.path.dirname(__file__), '.env')
print("Looking for .env at:", env_path)
load_dotenv(env_path)
API_KEY = os.getenv("XAI_API_KEY")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
print("Loaded ODDS_API_KEY:", ODDS_API_KEY)
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
        "markets": "h2h",
        "oddsFormat": "decimal"
    }
    try:
        response = requests.get(ODDS_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        print("Odds API response length:", len(data))
        if data and len(data) > 0:
            bets = []
            if query:
                query_lower = query.lower()
                print("Querying for:", query_lower)
                team_found = False
                for game in data:
                    home_team = game["home_team"].lower()
                    away_team = game["away_team"].lower()
                    if any(team in query_lower for team in [home_team, away_team]):
                        team_found = True
                        if game.get("bookmakers") and game["bookmakers"][0].get("markets"):
                            bookmakers = game["bookmakers"][0]["markets"][0]["outcomes"]
                            bet = f"Next game: Bet on {game['home_team']} vs {game['away_team']}: {bookmakers[0]['name']} to win @ {bookmakers[0]['price']}"
                            bets.append(bet)
                            print("Found match:", bet)
                if bets:
                    return "\n".join(bets)
                if team_found:
                    return f"No odds available yet for the next {query_lower.split('last ')[-1]} game."
                return f"No upcoming games found matching '{query}' in the current odds data."
            # Default: Top 3 upcoming games
            for game in data[:3]:
                if game.get("bookmakers") and game["bookmakers"][0].get("markets"):
                    home_team = game["home_team"]
                    away_team = game["away_team"]
                    bookmakers = game["bookmakers"][0]["markets"][0]["outcomes"]
                    bet = f"Bet on {home_team} vs {away_team}: {bookmakers[0]['name']} to win @ {bookmakers[0]['price']}"
                    bets.append(bet)
                else:
                    print(f"No odds for {game['home_team']} vs {game['away_team']}")
            return "\n".join(bets) if bets else "No upcoming NBA odds available with current bookmakers."
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
    popular_bets = get_betting_odds()
    return render_template('index.html', popular_bets=popular_bets)

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

# Chat log: https://grok.com/share/bGVnYWN5_e33c04e7-8eff-46b5-8cfd-226633279d2f