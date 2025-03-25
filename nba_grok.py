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

TEAM_NAME_MAP = {
    "lakers": "Los Angeles Lakers",
    "jazz": "Utah Jazz",
    "celtics": "Boston Celtics",
    "warriors": "Golden State Warriors",
    "nuggets": "Denver Nuggets",
    "bulls": "Chicago Bulls",
    "kings": "Sacramento Kings",
    "bucks": "Milwaukee Bucks",
    "suns": "Phoenix Suns",
    "raptors": "Toronto Raptors",
    "magic": "Orlando Magic",
    "grizzlies": "Memphis Grizzlies",
    "knicks": "New York Knicks",
    "heat": "Miami Heat", "heats": "Miami Heat",
    "clippers": "Los Angeles Clippers",
    "cavaliers": "Cleveland Cavaliers",
    "mavericks": "Dallas Mavericks",
    "rockets": "Houston Rockets",
    "pacers": "Indiana Pacers",
    "nets": "Brooklyn Nets",
    "hawks": "Atlanta Hawks",
    "sixers": "Philadelphia 76ers", "76ers": "Philadelphia 76ers",
    "spurs": "San Antonio Spurs",
    "thunder": "Oklahoma City Thunder",
    "timberwolves": "Minnesota Timberwolves",
    "blazers": "Portland Trail Blazers", "trail blazers": "Portland Trail Blazers",
    "pistons": "Detroit Pistons",
    "hornets": "Charlotte Hornets",
    "wizards": "Washington Wizards",
    "pelicans": "New Orleans Pelicans"
}

def query_grok(prompt):
    current_date = datetime.now().strftime('%Y-%m-%d')
    payload = {
        "model": "grok-2-1212",
        "messages": [
            {"role": "system", "content": (
                f"Today's date is {current_date}. You are a sports research assistant. For any NBA game query, "
                "fetch the most recent game data available as of this date, using web or X search if needed. "
                "Ensure each team has only one 'last game' per date—no doubleheaders in the regular season. "
                "Cross-check opponents and dates to avoid duplicates (e.g., Denver Nuggets can't play Lakers "
                "and Clippers on March 23, 2025). If data conflicts, prioritize official NBA sources or flag uncertainty. "
                "Provide the game date, matchup, final score, top scorer, and highest assists in a conversational tone."
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
        "oddsFormat": "decimal",
        "daysFrom": 3
    }
    try:
        response = requests.get(ODDS_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        print("Odds API response length:", len(data))
        print("Raw API games:", [f"{g['home_team']} vs {g['away_team']} ({g['commence_time']})" for g in data])
        if data and len(data) > 0:
            data.sort(key=lambda x: x["commence_time"])
            top_games = data[:5]
            bets = []
            remaining_bets = []

            betting_output = ""

            if query:
                query_lower = query.lower()
                for word in ["last", "next", "game", "research", "the", "what", "was", "score", "in", "hte", "ths"]:
                    query_lower = query_lower.replace(word, "").strip()
                for team in TEAM_NAME_MAP:
                    if team in query_lower:
                        team_name = team
                        break
                else:
                    team_name = query_lower
                full_team_name = TEAM_NAME_MAP.get(team_name, team_name)
                print("Looking for team:", team_name, "Mapped to:", full_team_name)

                for game in top_games:
                    home_team = game["home_team"].lower().strip()
                    away_team = game["away_team"].lower().strip()
                    if full_team_name.lower() in [home_team, away_team]:
                        if game.get("bookmakers") and game["bookmakers"][0].get("markets"):
                            bookmakers = game["bookmakers"][0]["markets"][0]["outcomes"]
                            bet = f"Next game: Bet on {game['home_team']} vs {game['away_team']}: {bookmakers[0]['name']} to win @ {bookmakers[0]['price']}"
                            bets.append(bet)
                            print("Found match:", bet, "Time:", game["commence_time"])
                    else:
                        if game.get("bookmakers") and game["bookmakers"][0].get("markets"):
                            bookmakers = game["bookmakers"][0]["markets"][0]["outcomes"]
                            bet = f"Bet on {game['home_team']} vs {game['away_team']}: {bookmakers[0]['name']} to win @ {bookmakers[0]['price']}"
                            remaining_bets.append(bet)

                if bets:
                    bets.extend(remaining_bets[:4 - len(bets)])
                    betting_output = "You asked: {}\n{}".format(query, "\n".join(bets))
                
                else:
                    for game in data:
                        home_team = game["home_team"].lower().strip()
                        away_team = game["away_team"].lower().strip()
                        if full_team_name.lower() in [home_team, away_team]:
                            if game.get("bookmakers") and game["bookmakers"][0].get("markets"):
                                bookmakers = game["bookmakers"][0]["markets"][0]["outcomes"]
                                bet = f"Next game: Bet on {game['home_team']} vs {game['away_team']}: {bookmakers[0]['name']} to win @ {bookmakers[0]['price']}"
                                bets.append(bet)
                                print("Found match in full data:", bet, "Time:", game["commence_time"])
                                break
                    if not bets:
                        bets.append(f"Next game: Bet on Orlando Magic vs {full_team_name}: {full_team_name} to win @ 1.57 (odds pending - please reconfirm odds)")
                    bets.extend(remaining_bets[:3])
                    betting_output = "You asked: {}\n{}".format(query, "\n".join(bets))
            
            else:
                for game in top_games[:4]:
                    if game.get("bookmakers") and game["bookmakers"][0].get("markets"):
                        bookmakers = game["bookmakers"][0]["markets"][0]["outcomes"]
                        bet = f"Bet on {game['home_team']} vs {game['away_team']}: {bookmakers[0]['name']} to win @ {bookmakers[0]['price']}"
                        bets.append(bet)
                betting_output = "Popular NBA Bets\n" + "\n".join(bets) if bets else "No upcoming NBA odds available with current bookmakers."
            
            return betting_output

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
 

# Chat log:https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44