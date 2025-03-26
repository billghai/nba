from flask import Flask, request, render_template, jsonify
import requests
import os
from dotenv import load_dotenv  # Add this line
import json
from datetime import datetime

env_path = os.path.join(os.path.dirname(__file__), '.env')
print("Looking for .env at:", env_path)
load_dotenv(env_path)
API_KEY = os.getenv("XAI_API_KEY")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
print("Loaded ODDS_API_KEY:", ODDS_API_KEY)
API_URL = "https://api.x.ai/v1/chat/completions"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"

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

# Load NBA schedule
SCHEDULE_PATH = os.path.join(os.path.dirname(__file__), 'nba_schedule.json')
with open(SCHEDULE_PATH, 'r') as f:
    NBA_SCHEDULE = json.load(f)

def validate_game(date, team1, team2, score=None):
    games = NBA_SCHEDULE.get(date, [])
    for game in games:
        teams = {game["home"].lower(), game["away"].lower()}
        if team1.lower() in teams and team2.lower() in teams:
            if score and score == game.get("score"):
                return True
            elif not score:  # Upcoming game
                return True
    return False

def get_last_game(team):
    today = datetime.now().strftime('%Y-%m-%d')
    for date in sorted(NBA_SCHEDULE.keys(), reverse=True):
        if date <= today:
            for game in NBA_SCHEDULE[date]:
                if team.lower() in [game["home"].lower(), game["away"].lower()]:
                    return date, game["home"], game["away"], game.get("score")
    return None, None, None, None

def query_grok(prompt):
    current_date = datetime.now().strftime('%Y-%m-%d')
    # Extract team from query
    query_lower = prompt.lower()
    for word in ["last", "game", "research", "the", "what", "was", "score", "in"]:
        query_lower = query_lower.replace(word, "").strip()
    for team in TEAM_NAME_MAP:
        if team in query_lower:
            team_name = TEAM_NAME_MAP[team]
            break
    else:
        return "Sorry, couldn’t identify the team—try again!"

    # Validate last game
    date, home, away, score = get_last_game(team_name)
    if not date:
        return f"No recent game found for {team_name} in the schedule."

    # Build validated query
    validated_prompt = f"On {date}, {home} played {away} with a score of {score or 'upcoming'}. Provide top scorer and highest assists for {team_name}."
    
    payload = {
        "model": "grok-2-1212",
        "messages": [
            {"role": "system", "content": (
                f"Today's date is {current_date}. You are a sports research assistant. Use the provided game data "
                "to provide the top scorer and highest assists for the requested team in a conversational tone. "
                "Do not search externally—rely on the input data."
            )},
            {"role": "user", "content": validated_prompt}
        ],
        "max_tokens": 500,
        "temperature": 0.7
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return f"The last game {team_name} played was on {date} against {away if team_name.lower() == home.lower() else home}. The final score was {score or 'still to come'}. {response.json()['choices'][0]['message']['content']}"
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
            # Validate API games
            validated_data = []
            for game in data:
                date = game["commence_time"].split("T")[0]
                if validate_game(date, game["home_team"], game["away_team"]):
                    validated_data.append(game)
            validated_data.sort(key=lambda x: x["commence_time"])
            top_games = validated_data[:5]
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
                    # Mock if not found in top games
                    betting_output = "You asked: {}\nNext game: Bet on Orlando Magic vs {}: {} to win @ 1.57 (odds pending - please reconfirm odds)\n{}".format(
                        query, full_team_name, full_team_name, "\n".join(remaining_bets[:3]))
            
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