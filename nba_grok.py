from datetime import datetime, timedelta, timezone
import requests
import json
import logging
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
ODDS_API_KEY = "547a8403fcaa9d12eaeb986848600e4d"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"
CACHE_PATH = "nba_schedule_cache.json"

def update_schedule_cache():
    now = datetime.now(timezone.utc) - timedelta(hours=7)  # PDT
    today = now.strftime('%Y-%m-%d')
    params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h", "daysFrom": 7}
    try:
        logging.debug("Starting cache update...")
        response = requests.get(ODDS_API_URL, params=params, timeout=5)
        response.raise_for_status()
        games = response.json()
        cache = {
            '2025-03-31': [
                {"home": "Memphis Grizzlies", "away": "Boston Celtics"},
                {"home": "Orlando Magic", "away": "Los Angeles Clippers"}
            ],
            '2025-04-01': [
                {"home": "Los Angeles Lakers", "away": "Houston Rockets"}
            ]
        }
        for game in games:
            game_time = datetime.strptime(game["commence_time"], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
            game_date_pdt = (game_time - timedelta(hours=7)).strftime('%Y-%m-%d')
            if game_date_pdt >= today:
                if game_date_pdt not in cache:
                    cache[game_date_pdt] = []
                cache[game_date_pdt].append({"home": game["home_team"], "away": game["away_team"]})
        with open(CACHE_PATH, 'w') as f:
            json.dump(cache, f)
        logging.debug(f"Schedule cache updated: {cache}")
        return cache
    except Exception as e:
        logging.error(f"Cache update failed: {str(e)}")
        raise

def get_game_info(query):
    now = datetime.now(timezone.utc) - timedelta(hours=7)  # PDT
    try:
        with open(CACHE_PATH, 'r') as f:
            cache = json.load(f)
    except:
        cache = {}
    grok_data = {
        '2025-03-31': [
            {"home": "Memphis Grizzlies", "away": "Boston Celtics"},
            {"home": "Orlando Magic", "away": "Los Angeles Clippers"}
        ]
    }
    if "next" in query:
        all_games = {**grok_data, **cache}
        for date in sorted(all_games.keys()):
            for game in all_games[date]:
                if any(team in query for team in [game["home"], game["away"]]):
                    game_time = datetime.strptime(f"{date}T00:00:00-07:00", '%Y-%m-%dT%H:%M:%S%z')
                    team = next(t for t in [game["home"], game["away"]] if t in query)
                    if game_time < now - timedelta(hours=24):
                        return f"Grok says: The next {team} game was on {date} against {game['away' if team == game['home'] else 'home']}..."
                    return f"The next {team} game is on {date} against {game['away' if team == game['home'] else 'home']}..."
        return "No next game found in schedule—check back!"
    elif "last" in query:
        all_games = {**grok_data, **cache}
        for date in sorted(all_games.keys(), reverse=True):
            for game in all_games[date]:
                if any(team in query for team in [game["home"], game["away"]]):
                    game_time = datetime.strptime(f"{date}T00:00:00-07:00", '%Y-%m-%dT%H:%M:%S%z')
                    team = next(t for t in [game["home"], game["away"]] if t in query)
                    if game_time < now - timedelta(hours=24):
                        return f"Grok says: The last {team} game was on {date} against {game['away' if team == game['home'] else 'home']}..."
        return "No last game found—try again later!"
    return "Query unclear—try 'next Lakers game' or 'last Spurs game'!"

def get_betting_odds(query=None):
    params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h", "oddsFormat": "decimal", "daysFrom": 7}
    try:
        response = requests.get(ODDS_API_URL, params=params, timeout=5)
        response.raise_for_status()
        odds_data = response.json()
        bets = []
        for game in odds_data[:5]:
            home = game["home_team"]
            away = game["away_team"]
            for bookmaker in game["bookmakers"]:
                if bookmaker["key"] == "draftkings":
                    for market in bookmaker["markets"]:
                        if market["key"] == "h2h":
                            outcomes = market["outcomes"]
                            bet = f"Next game: Bet on {home} vs {away}: {outcomes[0]['name']} to win @ {outcomes[0]['price']}"
                            bets.append(bet)
                            break
                    break
        return "<br><br>".join(bets) if bets else "No betting odds available yet—check back soon!"
    except Exception as e:
        logging.error(f"Betting odds error: {str(e)}")
        return "No upcoming NBA odds available right now."

# Force Render refresh - April 1 10:35 PM PDT
@app.route('/', methods=['GET', 'POST'])
def index():
    cache = update_schedule_cache()
    popular_bets = get_betting_odds()
    if request.method == 'POST':
        query = request.form['query']
        response = get_game_info(query)
        betting = get_betting_odds(query)
        return jsonify({'response': response, 'betting': betting})
    return render_template('index.html', popular_bets=popular_bets)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(message)s')
    logging.debug("Script starting...")
    update_schedule_cache()
    app.run(host='0.0.0.0', port=10000)
# https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44
# 0401 9:35