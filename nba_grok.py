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

TEAM_NAME_MAP = {  # unchanged ... }

SCHEDULE_PATH = os.path.join(os.path.dirname(__file__), 'nba_schedule.json')
with open(SCHEDULE_PATH, 'r') as f:
    NBA_SCHEDULE = json.load(f)

USED_GAMES = set()

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

    # Handle "next game" queries
    if "next" in query_lower and "game" in query_lower:
        for team in TEAM_NAME_MAP:
            if team in query_lower:
                team_name = TEAM_NAME_MAP[team]
                date, home, away = get_next_game(team_name)
                if date:
                    return f"The next {team_name} game is on {date} against {away if team_name.lower() == home.lower() else home}. Check back for more details closer to tip-off!"
                return f"No next game found for {team_name} in the schedule—stay tuned!"
        return "Sorry, couldn’t catch that team—try again!"

    # Handle general queries
    if any(word in query_lower for word in ["how many", "what is", "who", "highest", "score", "won", "finals"]):
        payload = {
            "model": "grok-2-1212",
            "messages": [
                {"role": "system", "content": (
                    f"Today’s date is {current_date}. Answer as a basketball expert with a fun, concise tone (50-70 words). "
                    f"Use the 7-day schedule if relevant: {schedule_str}. Otherwise, use your NBA knowledge!"
                )},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 150,
            "temperature": 0.7
        }
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        try:
            response = requests.post(API_URL, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content']
        except Exception as e:
            return f"Oops! Hit a snag: {str(e)}. Try again!"

    # Handle "last game" queries
    for word in ["last", "game", "research", "the", "what", "was", "score", "in", "investiga", "ultimo", "partido"]:
        query_lower = query_lower.replace(word, "").strip()
    for team in TEAM_NAME_MAP:
        if team in query_lower:
            team_name = TEAM_NAME_MAP[team]
            break
    else:
        return "Sorry, couldn’t catch that team—try again!"

    date, home, away, score = get_last_game(team_name)
    if not date:
        return f"No recent game for {team_name}—they’re hiding!"

    validated_prompt = f"Give top scorer and highest assists for {team_name} from their last game in 30-50 words—keep it fun!"
    
    payload = {
        "model": "grok-2-1212",
        "messages": [
            {"role": "system", "content": (
                f"Today’s date is {current_date}. Use this game data: {team_name} played {away if team_name.lower() == home.lower() else home} on {date}, score {score or 'upcoming'}. Answer in a fun, concise tone (30-50 words) with top scorer and assists only."
            )},
            {"role": "user", "content": validated_prompt}
        ],
        "max_tokens": 120,
        "temperature": 0.7
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return f"The last game {team_name} played was on {date} against {away if team_name.lower() == home.lower() else home}. The final score was {score or 'still to come'}. {response.json()['choices'][0]['message']['content']}"
    except Exception as e:
        return f"Oops! API glitch: {str(e)}"

def get_betting_odds(query=None):  # unchanged from last update ...

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