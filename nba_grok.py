import sqlite3
from datetime import datetime, timedelta, timezone
import requests
import json
import logging
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
ODDS_API_KEY = "547a8403fcaa9d12eaeb986848600e4d"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/basketball/nba/odds"
DB_PATH = "roster.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS roster (
        date TEXT, home TEXT, away TEXT, odds TEXT, status TEXT, score TEXT,
        PRIMARY KEY (date, home, away)
    )''')
    conn.commit()
    conn.close()

def update_main_roster():
    now = datetime.now(timezone.utc) - timedelta(hours=7)  # PDT
    today = now.strftime('%Y%m%d')
    yesterday = (now - timedelta(days=1)).strftime('%Y%m%d')
    tomorrow = (now + timedelta(days=1)).strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={yesterday}-{tomorrow}"
    try:
        logging.debug("Updating main roster from ESPN...")
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for event in data.get('events', []):
            date = event['date'][:10]  # YYYY-MM-DD
            home = event['competitions'][0]['competitors'][0]['team']['displayName']
            away = event['competitions'][0]['competitors'][1]['team']['displayName']
            c.execute("INSERT OR REPLACE INTO roster (date, home, away, odds, status, score) VALUES (?, ?, ?, ?, ?, ?)",
                      (date, home, away, "", "pending", ""))
        conn.commit()
        conn.close()
        logging.debug("Main roster updated")
    except Exception as e:
        logging.error(f"Main roster update failed: {str(e)}")

def update_odds():
    params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h", "oddsFormat": "decimal", "daysFrom": 7}
    try:
        logging.debug("Updating odds from Odds API...")
        response = requests.get(ODDS_API_URL, params=params, timeout=5)
        response.raise_for_status()
        odds_data = response.json()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for game in odds_data:
            date = game["commence_time"][:10]
            home = game["home_team"]
            away = game["away_team"]
            odds = ""
            for bookmaker in game["bookmakers"]:
                if bookmaker["key"] == "draftkings":
                    for market in bookmaker["markets"]:
                        if market["key"] == "h2h":
                            odds = f"{market['outcomes'][0]['name']} to win @ {market['outcomes'][0]['price']}"
                            break
                    break
            if odds:
                c.execute("UPDATE roster SET odds = ? WHERE date = ? AND home = ? AND away = ?",
                          (odds, date, home, away))
        conn.commit()
        conn.close()
        logging.debug("Odds updated")
    except Exception as e:
        logging.error(f"Odds update failed: {str(e)}")

def update_scores():
    now = datetime.now(timezone.utc) - timedelta(hours=7)
    today = now.strftime('%Y%m%d')
    yesterday = (now - timedelta(days=1)).strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={yesterday}-{today}"
    try:
        logging.debug("Updating scores from ESPN...")
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for event in data.get('events', []):
            date = event['date'][:10]
            home = event['competitions'][0]['competitors'][0]['team']['displayName']
            away = event['competitions'][0]['competitors'][1]['team']['displayName']
            status = event['status']['type']['state']  # pre, in, post
            score = f"{event['competitions'][0]['competitors'][0]['score']} - {event['competitions'][0]['competitors'][1]['score']}" if status == "post" else ""
            c.execute("UPDATE roster SET status = ?, score = ? WHERE date = ? AND home = ? AND away = ?",
                      ("over" if status == "post" else "in-play" if status == "in" else "pending", score, date, home, away))
        conn.commit()
        conn.close()
        logging.debug("Scores updated")
    except Exception as e:
        logging.error(f"Scores update failed: {str(e)}")

def get_game_info(query):
    now = datetime.now(timezone.utc) - timedelta(hours=7)  # PDT
    today = now.strftime('%Y-%m-%d')
    last_24h = now - timedelta(hours=24)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM roster")
    roster = {}
    for row in c.fetchall():
        date, home, away, odds, status, score = row
        if date not in roster:
            roster[date] = []
        roster[date].append({"home": home, "away": away, "odds": odds, "status": status, "score": score})
    conn.close()
    grok_data = {
        '2025-03-31': [
            {"home": "Memphis Grizzlies", "away": "Boston Celtics"},
            {"home": "Orlando Magic", "away": "Los Angeles Clippers"}
        ]
    }
    query_lower = query.lower().replace("research", "").replace("tell me about", "").strip()
    all_games = {**roster, **grok_data}
    if "next" in query_lower:
        for date in sorted(all_games.keys()):
            for game in all_games[date]:
                home_lower = game["home"].lower()
                away_lower = game["away"].lower()
                game_time = datetime.strptime(f"{date}T00:00:00-07:00", '%Y-%m-%dT%H:%M:%S%z')
                if "celtics" in query_lower and ("celtics" in home_lower or "celtics" in away_lower):
                    team = "Boston Celtics"
                    opponent = game['away'] if team == game['home'] else game['home']
                    if date >= today:  # Today or future
                        return f"The next {team} game is on {date} against {opponent}—check back for more details!"
                elif "lakers" in query_lower and ("lakers" in home_lower or "lakers" in away_lower):
                    team = "Los Angeles Lakers"
                    opponent = game['away'] if team == game['home'] else game['home']
                    if date >= today:
                        return f"The next {team} game is on {date} against {opponent}—check back for more details!"
                elif "suns" in query_lower and ("suns" in home_lower or "suns" in away_lower):
                    team = "Phoenix Suns"
                    opponent = game['away'] if team == game['home'] else game['home']
                    if date >= today:
                        return f"The next {team} game is on {date} against {opponent}—check back for more details!"
                elif "knicks" in query_lower and ("knicks" in home_lower or "knicks" in away_lower):
                    team = "New York Knicks"
                    opponent = game['away'] if team == game['home'] else game['home']
                    if date >= today:
                        return f"The next {team} game is on {date} against {opponent}—check back for more details!"
        return "No next game found in schedule—bets suggest a matchup soon, stay tuned!"
    elif "last" in query_lower:
        for date in sorted(all_games.keys(), reverse=True):
            for game in all_games[date]:
                home_lower = game["home"].lower()
                away_lower = game["away"].lower()
                game_time = datetime.strptime(f"{date}T00:00:00-07:00", '%Y-%m-%dT%H:%M:%S%z')
                if "celtics" in query_lower and ("celtics" in home_lower or "celtics" in away_lower):
                    team = "Boston Celtics"
                    opponent = game['away'] if team == game['home'] else game['home']
                    if game_time < now and game_time >= last_24h:
                        return f"The last {team} game was on {date} against {opponent}—score: {game.get('score', 'not available yet')}"
                    elif game_time < last_24h:
                        return f"Grok says: The last {team} game was on {date} against {opponent}—score not available yet, wild right?"
                elif "lakers" in query_lower and ("lakers" in home_lower or "lakers" in away_lower):
                    team = "Los Angeles Lakers"
                    opponent = game['away'] if team == game['home'] else game['home']
                    if game_time < now and game_time >= last_24h:
                        return f"The last {team} game was on {date} against {opponent}—score: {game.get('score', 'not available yet')}"
                    elif game_time < last_24h:
                        return f"Grok says: The last {team} game was on {date} against {opponent}—score not available yet, wild right?"
                elif "suns" in query_lower and ("suns" in home_lower or "suns" in away_lower):
                    team = "Phoenix Suns"
                    opponent = game['away'] if team == game['home'] else game['home']
                    if game_time < now and game_time >= last_24h:
                        return f"The last {team} game was on {date} against {opponent}—score: {game.get('score', 'not available yet')}"
                    elif game_time < last_24h:
                        return f"Grok says: The last {team} game was on {date} against {opponent}—score not available yet, wild right?"
                elif "knicks" in query_lower and ("knicks" in home_lower or "knicks" in away_lower):
                    team = "New York Knicks"
                    opponent = game['away'] if team == game['home'] else game['home']
                    if game_time < now and game_time >= last_24h:
                        return f"The last {team} game was on {date} against {opponent}—score: {game.get('score', 'not available yet')}"
                    elif game_time < last_24h:
                        return f"Grok says: The last {team} game was on {date} against {opponent}—score not available yet, wild right?"
        return "No last game found—try again later!"
    return "Query unclear—try 'next Lakers game' or 'last Spurs game'!"

def get_betting_odds(query=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT date, home, away, odds FROM roster WHERE odds != '' AND date >= ?",
                  (datetime.now(timezone.utc).strftime('%Y-%m-%d'),))
        bets = [f"Next game: Bet on {row[1]} vs {row[2]}: {row[3]}" for row in c.fetchall()[:5]]
        conn.close()
        return "<br><br>".join(bets) if bets else "No betting odds available yet—check back soon!"
    except Exception as e:
        logging.error(f"Betting odds fetch failed: {str(e)}")
        return "No upcoming NBA odds available right now."

@app.route('/', methods=['GET', 'POST'])
def index():
    try:
        init_db()
        update_main_roster()
        popular_bets = get_betting_odds()
        if request.method == 'POST':
            query = request.form.get('query', '')
            logging.debug(f"Received POST query: {query}")
            response = get_game_info(query)
            betting = get_betting_odds(query)
            logging.debug(f"POST response: {response}, betting: {betting}")
            return jsonify({'response': response, 'betting': betting})
        return render_template('index.html', popular_bets=popular_bets)
    except Exception as e:
        logging.error(f"Index error: {str(e)}")
        return jsonify({'response': 'Oops, something broke!', 'betting': ''}), 500

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(message)s')
    logging.debug("Script starting...")
    init_db()
    update_main_roster()
    app.run(host='0.0.0.0', port=10000)

# multi cron pivot https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44