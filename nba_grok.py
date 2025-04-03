import sqlite3
from datetime import datetime, timedelta, timezone
import requests
import logging
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
ODDS_API_KEY = "547a8403fcaa9d12eaeb986848600e4d"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"
DB_PATH = "nba_roster.db"

TEAM_ALIASES = {
    "lakers": "Los Angeles Lakers",
    "celtics": "Boston Celtics",
    "knicks": "New York Knicks",
    "jazz": "Utah Jazz",
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS games (
        date TEXT, home TEXT, away TEXT, odds TEXT, status TEXT, score TEXT,
        PRIMARY KEY (date, home, away)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY, value TEXT
    )''')
    conn.commit()
    conn.close()

def update_schedule():
    now = datetime.now(timezone.utc) - timedelta(hours=7)
    start_date = (now - timedelta(days=2)).strftime('%Y%m%d')
    end_date = (now + timedelta(days=7)).strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={start_date}-{end_date}"
    try:
        logging.debug("Fetching NBA schedule from ESPN...")
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for event in data.get('events', []):
            date = event['date'][:10]
            home = event['competitions'][0]['competitors'][0]['team']['displayName']
            away = event['competitions'][0]['competitors'][1]['team']['displayName']
            state = event['status']['type']['state']
            status = "pending" if state == "pre" else "in-play" if state == "in" else "over"
            score = f"{event['competitions'][0]['competitors'][0]['score']} - {event['competitions'][0]['competitors'][1]['score']}" if status == "over" else ""
            c.execute("INSERT OR REPLACE INTO games (date, home, away, odds, status, score) VALUES (?, ?, ?, ?, ?, ?)",
                      (date, home, away, "", status, score))
        c.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                  ("last_schedule_update", now.strftime("%Y-%m-%d %H:%M:%S PDT")))
        conn.commit()
        conn.close()
        logging.debug("Schedule updated in database.")
    except Exception as e:
        logging.error(f"Schedule update failed: {str(e)}")

def update_odds():
    params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h", "oddsFormat": "decimal", "daysFrom": 7}
    try:
        logging.debug("Fetching odds from The Odds API...")
        response = requests.get(ODDS_API_URL, params=params, timeout=5)
        response.raise_for_status()
        odds_data = response.json()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for game in odds_data[:5]:
            date = game["commence_time"][:10]
            home = game["home_team"]
            away = game["away_team"]
            odds = ""
            for bookmaker in game["bookmakers"]:
                if bookmaker["key"] == "draftkings":
                    for market in bookmaker["markets"]:
                        if market["key"] == "h2h":
                            odds = f"{home} @ {market['outcomes'][0]['price']} vs {away} @ {market['outcomes'][1]['price']}"
                            break
                    break
            if odds:
                c.execute("UPDATE games SET odds = ? WHERE date = ? AND home = ? AND away = ?",
                          (odds, date, home, away))
        now = datetime.now(timezone.utc) - timedelta(hours=7)
        c.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                  ("last_odds_update", now.strftime("%Y-%m-%d %H:%M:%S PDT")))
        conn.commit()
        conn.close()
        logging.debug("Odds updated in database.")
    except Exception as e:
        logging.error(f"Odds update failed: {str(e)}")

def get_chat_response(query):
    query_lower = query.lower().replace("research", "").replace("the", "").replace("game", "").replace("tell me about", "").strip()
    logging.debug(f"Parsed query: {query_lower}")
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT date, home, away, status, score FROM games")
        games = c.fetchall()
        logging.debug(f"Games in database: {[(g[0], g[1], g[2], g[3], g[4]) for g in games]}")
        conn.close()

        debug_dump = "Database dump:\n" + "\n".join([f"{g[0]}: {g[1]} vs {g[2]} ({g[3]}, {g[4]})" for g in games])
        now = datetime.now(timezone.utc) - timedelta(hours=7)
        for date, home, away, status, score in sorted(games, key=lambda x: x[0]):
            game_time = datetime.strptime(f"{date}T00:00:00-07:00", '%Y-%m-%dT%H:%M:%S%z')
            query_team = next((full_name for alias, full_name in TEAM_ALIASES.items() if alias in query_lower), query_lower)
            if "last" in query_lower and game_time < now:
                if query_team.lower() in home.lower() or query_team.lower() in away.lower():
                    return f"Hey! The last {home} vs {away} game on {date} ended {score if score else '—score’s still coming in!'}. What’d you think of that one?"
            elif "next" in query_lower and (game_time > now or (game_time.date() == now.date() and status == "pending")):
                if query_team.lower() in home.lower() or query_team.lower() in away.lower():
                    return f"Yo, the next {home} vs {away} game is on {date}. Should be a good one—any predictions?"
        return f"Hmm, not sure what game you’re asking about. Wanna talk Lakers, Celtics, or something else?\n\n{debug_dump}"
    except Exception as e:
        logging.error(f"Chat response error: {str(e)}")
        return "Oops, something went wrong—try again!"

def get_popular_odds():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT date, home, away, odds FROM games WHERE odds != '' AND date >= ? ORDER BY date LIMIT 5",
                  (datetime.now(timezone.utc).strftime('%Y-%m-%d'),))
        bets = [f"{row[1]} vs {row[2]} on {row[0]}: {row[3]}" for row in c.fetchall()]
        c.execute("SELECT value FROM metadata WHERE key = 'last_odds_update'")
        odds_time_row = c.fetchone()
        odds_time = odds_time_row[0] if odds_time_row else "Unknown"
        c.execute("SELECT value FROM metadata WHERE key = 'last_schedule_update'")
        schedule_time_row = c.fetchone()
        schedule_time = schedule_time_row[0] if schedule_time_row else "Unknown"
        conn.close()
        bets_str = "<br><br>".join(bets) if bets else "No odds yet—check back soon!"
        return bets_str, odds_time, schedule_time
    except Exception as e:
        logging.error(f"Get popular odds error: {str(e)}")
        return "No odds available—try again later!", "Unknown", "Unknown"

@app.route('/', methods=['GET', 'POST'])
def index():
    try:
        init_db()
        update_schedule()
        update_odds()
        bets, odds_time, schedule_time = get_popular_odds()
        popular_bets_title = f"Popular NBA Bets ({odds_time})"
        popular_bets = f"{bets}<br><br>Data updated - Schedule: {schedule_time}, Odds: {odds_time}"
        if request.method == 'POST':
            query = request.form.get('query', '')
            response = get_chat_response(query)
            bets, odds_time, schedule_time = get_popular_odds()
            return jsonify({'response': response, 'betting': f"{bets}<br><br>Data updated - Schedule: {schedule_time}, Odds: {odds_time}"})
        return render_template('index.html', popular_bets=popular_bets, popular_bets_title=popular_bets_title)
    except Exception as e:
        logging.error(f"Index error: {str(e)}")
        return render_template('index.html', popular_bets="Error loading data", popular_bets_title="Popular NBA Bets (Error)")

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    app.run(host='0.0.0.0', port=10000)

#new 10:35 AM grokchat 04/03 https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44