from flask import Flask, request, render_template, jsonify
import requests
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timezone, timedelta
import logging

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)
API_KEY = os.getenv("XAI_API_KEY")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
API_URL = "https://api.x.ai/v1/chat/completions"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"
CACHE_PATH = os.path.join(os.path.dirname(__file__), 'nba_schedule_cache.json')

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

TEAM_NAME_MAP = { # Unchanged - looks good
    "lakers": "Los Angeles Lakers", "jazz": "Utah Jazz", "celtics": "Boston Celtics",
    "warriors": "Golden State Warriors", "nuggets": "Denver Nuggets", "bulls": "Chicago Bulls",
    "kings": "Sacramento Kings", "bucks": "Milwaukee Bucks", "suns": "Phoenix Suns",
    "raptors": "Toronto Raptors", "magic": "Orlando Magic", "grizzlies": "Memphis Grizzlies",
    "knicks": "New York Knicks", "heat": "Miami Heat", "heats": "Miami Heat",
    "clippers": "Los Angeles Clippers", "cavaliers": "Cleveland Cavaliers",
    "mavericks": "Dallas Mavericks", "rockets": "Houston Rockets", "pacers": "Indiana Pacers",
    "nets": "Brooklyn Nets", "hawks": "Atlanta Hawks", "sixers": "Philadelphia 76ers",
    "76ers": "Philadelphia 76ers", "spurs": "San Antonio Spurs", "thunder": "Oklahoma City Thunder",
    "timberwolves": "Minnesota Timberwolves", "blazers": "Portland Trail Blazers",
    "trail blazers": "Portland Trail Blazers", "pistons": "Detroit Pistons",
    "hornets": "Charlotte Hornets", "wizards": "Washington Wizards", "pelicans": "New Orleans Pelicans"
}

USED_GAMES = set()

def update_schedule_cache():
    params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h", "daysFrom": 7}
    try:
        response = requests.get(ODDS_API_URL, params=params, timeout=5)
        response.raise_for_status()
        games = response.json()
        cache = {}
        for game in games:
            date = game["commence_time"][:10]
            if date not in cache:
                cache[date] = []
            cache[date].append({"home": game["home_team"], "away": game["away_team"]})
        with open(CACHE_PATH, 'w') as f:
            json.dump(cache, f)
        logging.debug("Schedule cache updated successfully")
    except Exception as e:
        logging.error(f"Cache update failed: {str(e)}")

def load_schedule_cache():
    try:
        with open(CACHE_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        update_schedule_cache()
        return load_schedule_cache()
    except Exception as e:
        logging.error(f"Cache load error: {str(e)}")
        return {}

def get_last_game(team):
    today = (datetime.now(timezone.utc) - timedelta(hours=7)).strftime('%Y-%m-%d')
    try:
        with open('nba_schedule.json', 'r') as f:
            past_schedule = json.load(f)
        for date in sorted(past_schedule.keys(), reverse=True):
            if date < today:
                for game in past_schedule[date]:
                    if team.lower() in [game["home"].lower(), game["away"].lower()]:
                        return date, game["home"], game["away"], game.get("score")
    except FileNotFoundError:
        logging.error("nba_schedule.json not found for past games")
    return None, None, None, None

def get_next_game(team):
    today = (datetime.now(timezone.utc) - timedelta(hours=7)).strftime('%Y-%m-%d')
    schedule = load_schedule_cache()
    logging.debug(f"Cache for {team}: {schedule}")
    for date in sorted(schedule.keys()):
        if date >= today:
            for game in schedule[date]:
                if team.lower() in [game["home"].lower(), game["away"].lower()]:
                    return date, game["home"], game["away"]
    logging.debug(f"No next game for {team} in cache")
    return None, None, None  # Fixed typo!

def query_grok(prompt):
    current_date = (datetime.now(timezone.utc) - timedelta(hours=7)).strftime('%Y-%m-%d')
    schedule = load_schedule_cache()
    schedule_str = json.dumps({k: v for k, v in schedule.items() if k >= current_date})
    query_lower = prompt.lower().replace("'", "").replace("’", "")

    if "next" in query_lower and "game" in query_lower:
        for team in TEAM_NAME_MAP:
            if team in query_lower:
                team_name = TEAM_NAME_MAP[team]
                date, home, away = get_next_game(team_name)
                if date:
                    return f"The next {team_name} game is on {date} against {away if team_name.lower() == home.lower() else home}. Check back for more details closer to tip-off!"
                return f"No next game found in schedule—bets suggest a matchup soon, stay tuned!"
        return "Sorry, couldn’t catch that team—try again!"

    if "last" in query_lower and "game" in query_lower:
        for team in TEAM_NAME_MAP:
            if team in query_lower:
                team_name = TEAM_NAME_MAP[team]
                date, home, away, score = get_last_game(team_name)
                if date:
                    return f"The last {team_name} game was on {date} against {away if team_name.lower() == home.lower() else home}. Score: {score or 'no score yet'}—wild, right?"
                return f"No recent game found for {team_name}—they’re keeping it low-key!"
        return "Sorry, couldn’t catch that team—try again!"

def get_betting_odds(query=None):
    params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h", "oddsFormat": "decimal", "daysFrom": 7}
    try:
        response = requests.get(ODDS_API_URL, params=params, timeout=5)
        response.raise_for_status()
        odds_data = response.json()
        bets = []
        for game in odds_data[:3]:  # Top 3 games
            home = game["home_team"]
            away = game["away_team"]
            for bookmaker in game["bookmakers"]:
                if bookmaker["key"] == "draftkings":  # Pick a bookmaker
                    for market in bookmaker["markets"]:
                        if market["key"] == "h2h":
                            outcomes = market["outcomes"]
                            bet = f"Next game: Bet on {home} vs {away}: {outcomes[0]['name']} to win @ {outcomes[0]['price']} [disclaimer]"
                            bets.append(bet)
                            break
                    break
        return "\n".join(bets) if bets else "No betting odds available yet—check back soon!"
    except Exception as e:
        logging.error(f"Betting odds error: {str(e)}")
        return "No upcoming NBA odds available right now."

@app.route('/', methods=['GET', 'POST'])
def index():
    global USED_GAMES
    if request.method == 'GET':
        USED_GAMES.clear()
    if request.method == 'POST':
        query = request.form['query']
        response = query_grok(query)
        betting_proposal = get_betting_odds(query)
        return jsonify({'response': response, 'betting': betting_proposal})
    popular_bets = get_betting_odds()
    return render_template('index.html', popular_bets=popular_bets)

if __name__ == '__main__':
    update_schedule_cache()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)

# chat URL https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44