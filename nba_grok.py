from flask import Flask, request, render_template, jsonify
import requests
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timezone, timedelta

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)
API_KEY = os.getenv("XAI_API_KEY")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
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
    "pelicans": "New Orleans Pelicans"  # Added Pelicans
}

SCHEDULE_PATH = os.path.join(os.path.dirname(__file__), 'nba_schedule.json')
with open(SCHEDULE_PATH, 'r') as f:
    NBA_SCHEDULE = json.load(f)

def get_last_game(team):
    today = (datetime.now(timezone.utc) - timedelta(hours=7)).strftime('%Y-%m-%d')
    for date in sorted(NBA_SCHEDULE.keys(), reverse=True):
        if date < today:
            for game in NBA_SCHEDULE[date]:
                if team.lower() in [game["home"].lower(), game["away"].lower()] and game.get("score"):
                    return date, game["home"], game["away"], game.get("score")
    return None, None, None, None

def get_next_game(team):
    today = (datetime.now(timezone.utc) - timedelta(hours=7)).strftime('%Y-%m-%d')
    for date in sorted(NBA_SCHEDULE.keys()):
        if date >= today:
            for game in NBA_SCHEDULE[date]:
                if team.lower() in [game["home"].lower(), game["away"].lower()]:
                    return date, game["home"], game["away"]
    return None, None, None

def query_grok(prompt):
    current_date = (datetime.now(timezone.utc) - timedelta(hours=7)).strftime('%Y-%m-%d')
    schedule_str = json.dumps({k: v for k, v in NBA_SCHEDULE.items() if k >= current_date and k <= '2025-03-31'})
    query_lower = prompt.lower().replace("'", "").replace("’", "")

    # Check for general basketball questions first
    if any(word in query_lower for word in ["how many", "what is", "who", "highest", "score", "won", "finals"]):
        payload = {
            "model": "grok-2-1212",
            "messages": [
                {"role": "system", "content": (
                    f"Today’s date is {current_date}. Answer as a basketball expert with a fun, conversational tone. "
                    f"Use the 7-day schedule only if relevant: {schedule_str}. Otherwise, tap into your full NBA knowledge!"
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
            return response.json()['choices'][0]['message']['content']
        except Exception as e:
            return f"Oops! Hit a snag: {str(e)}. Let’s try that again!"

    # Last-game logic for team-specific queries
    for word in ["last", "game", "research", "the", "what", "was", "score", "in", "investiga", "ultimo", "partido"]:
        query_lower = query_lower.replace(word, "").strip()
    for team in TEAM_NAME_MAP:
        if team in query_lower:
            team_name = TEAM_NAME_MAP[team]
            break
    else:
        return "Sorry, couldn’t catch that team—give me a clearer shot!"

    date, home, away, score = get_last_game(team_name)
    if not date:
        return f"No recent game found for {team_name} in the schedule—maybe they’re dodging the spotlight!"

    validated_prompt = f"On {date}, {home} played {away} with a score of {score or 'upcoming'}. Provide top scorer and highest assists for {team_name}."
    
    payload = {
        "model": "grok-2-1212",
        "messages": [
            {"role": "system", "content": (
                f"Today’s date is {current_date}. Use the provided game data and this 7-day schedule to provide the top scorer "
                f"and highest assists for the requested team in a fun, chatty tone. Schedule: {schedule_str}"
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
        return f"Oops! Something went wonky with the API: {str(e)}"

# [get_betting_odds function remains unchanged for now—focus is on chat]

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
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)

# chat URL https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44