import sqlite3
from datetime import datetime, timedelta, timezone
import requests
import logging
import random
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
ODDS_API_KEY = "547a8403fcaa9d12eaeb986848600e4d"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"
DB_PATH = "nba_roster.db"

TEAM_ALIASES = {
    "hawks": "Atlanta Hawks",
    "celtics": "Boston Celtics",
    "nets": "Brooklyn Nets",
    "hornets": "Charlotte Hornets",
    "bulls": "Chicago Bulls",
    "cavs": "Cleveland Cavaliers",
    "cavaliers": "Cleveland Cavaliers",
    "mavs": "Dallas Mavericks",
    "mavericks": "Dallas Mavericks",
    "nuggets": "Denver Nuggets",
    "pistons": "Detroit Pistons",
    "warriors": "Golden State Warriors",
    "dubs": "Golden State Warriors",
    "rockets": "Houston Rockets",
    "pacers": "Indiana Pacers",
    "clippers": "Los Angeles Clippers",
    "lakers": "Los Angeles Lakers",
    "grizzlies": "Memphis Grizzlies",
    "grizz": "Memphis Grizzlies",
    "heat": "Miami Heat",
    "bucks": "Milwaukee Bucks",
    "timberwolves": "Minnesota Timberwolves",
    "wolves": "Minnesota Timberwolves",
    "pelicans": "New Orleans Pelicans",
    "pels": "New Orleans Pelicans",
    "knicks": "New York Knicks",
    "ny": "New York Knicks",
    "thunder": "Oklahoma City Thunder",
    "okc": "Oklahoma City Thunder",
    "magic": "Orlando Magic",
    "76ers": "Philadelphia 76ers",
    "sixers": "Philadelphia 76ers",
    "philly": "Philadelphia 76ers",
    "suns": "Phoenix Suns",
    "trail blazers": "Portland Trail Blazers",
    "blazers": "Portland Trail Blazers",
    "kings": "Sacramento Kings",
    "sactown": "Sacramento Kings",
    "spurs": "San Antonio Spurs",
    "raptors": "Toronto Raptors",
    "raps": "Toronto Raptors",
    "jazz": "Utah Jazz",
    "wizards": "Washington Wizards",
    "wiz": "Washington Wizards",
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
    query_lower = query.lower().replace("bset", "best").replace("research", "").replace("the", "").replace("game", "").replace("tell me about", "").strip()
    logging.debug(f"Parsed query: {query_lower}")
    
    if "last" not in query_lower and "next" not in query_lower:
        if "lebron" in query_lower or "james" in query_lower:
            return "LeBron’s been killing it—averaging around 25 points, 8 rebounds, and 7 assists lately. He’s the NBA’s all-time leading scorer with over 41,000 points as of early 2025. What do you think of his legacy?"
        elif "highest" in query_lower and ("scorer" in query_lower or "goal" in query_lower) or "best scorer" in query_lower:
            return "As of April 2025, Shai Gilgeous-Alexander’s leading the league with around 32.8 points per game this season—pretty clutch stuff! What’s your take on him?"
        elif "best shooter" in query_lower:
            if "jazz" in query_lower:
                return "Jordan Clarkson’s probably the best shooter for the Utah Jazz right now—averaging around 2.4 threes per game this season. Thoughts on his game?"
            return "I’d need a team to pinpoint the best shooter—give me one, and I’ll hook you up with the details!"
        elif "standings" in query_lower:
            return "I can’t pull exact standings right now, but as of early April 2025, the top teams are fighting for playoff spots. Want me to dig into a specific team?"
        return "I’m not seeing a last or next game query here. Ask me anything about the NBA—I’ve got plenty to chat about!"

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT date, home, away, status, score FROM games")
        games = c.fetchall()
        logging.debug(f"Games in database: {[(g[0], g[1], g[2], g[3], g[4]) for g in games]}")
        conn.close()

        now = datetime.now(timezone.utc) - timedelta(hours=7)
        next_variations = [
            "Yo, the next {home} vs {away} game’s on {date}. Gonna be a banger—what’s your take?",
            "Hey, {home} takes on {away} next on {date}. Any hot predictions?",
            "Next up, {home} vs {away} on {date}. Should be wild—thoughts?"
        ]
        last_variations = [
            "Hey! The last {home} vs {away} game on {date} ended {score}. How’d you rate that one?",
            "Yo, {home} vs {away} last time on {date} was {score}. What’s your vibe on it?",
            "Last game, {home} vs {away} on {date} finished {score}. Cool or nah?"
        ]

        for date, home, away, status, score in sorted(games, key=lambda x: x[0]):
            game_time = datetime.strptime(f"{date}T00:00:00-07:00", '%Y-%m-%dT%H:%M:%S%z')
            query_team = next((full_name for alias, full_name in TEAM_ALIASES.items() if alias in query_lower), query_lower)
            if "last" in query_lower and game_time < now:
                if query_team.lower() in home.lower() or query_team.lower() in away.lower():
                    template = random.choice(last_variations)
                    return template.format(home=home, away=away, date=date, score=score if score else "—score’s still coming in!")
            elif "next" in query_lower and game_time >= now:
                if query_team.lower() in home.lower() or query_team.lower() in away.lower():
                    template = random.choice(next_variations)
                    return template.format(home=home, away=away, date=date)
                break  # Stop at first future game
        return "Hmm, not sure what game you’re asking about. Wanna talk Lakers, Celtics, or something else?"
    except Exception as e:
        logging.error(f"Chat response error: {str(e)}")
        return "Oops, something went wrong—try again!"

def get_popular_odds():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT date, home, away, odds FROM games WHERE odds != '' AND date >= ? ORDER BY date LIMIT 5",
                  (datetime.now(timezone.utc).strftime('%Y-%m-%d'),))
        bets = [f"{row[1]} vs {row[2]} on {row[0]} | {row[3]} | click here to go" for row in c.fetchall()]
        c.execute("SELECT value FROM metadata WHERE key = 'last_odds_update'")
        odds_time_row = c.fetchone()
        odds_time = odds_time_row[0] if odds_time_row else "Unknown"
        conn.close()
        bets_str = "\n".join(bets) if bets else "No odds yet—check back soon!"
        return bets_str, odds_time
    except Exception as e:
        logging.error(f"Get popular odds error: {str(e)}")
        return "No odds available—try again later!", "Unknown"

@app.route('/', methods=['GET', 'POST'])
def index():
    try:
        init_db()
        update_schedule()
        update_odds()
        bets, odds_time = get_popular_odds()
        popular_bets_title = f"Popular NBA Bets ({odds_time})"
        popular_bets = bets
        if request.method == 'POST':
            query = request.form.get('query', '')
            response = get_chat_response(query)
            return jsonify({'response': response, 'query': query})
        return render_template('index.html', popular_bets=popular_bets, popular_bets_title=popular_bets_title)
    except Exception as e:
        logging.error(f"Index error: {str(e)}")
        return render_template('index.html', popular_bets="Error loading data", popular_bets_title="Popular NBA Bets (Error)")

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    app.run(host='0.0.0.0', port=10000)
  

# newdesign team aliases 2:00PM 0403 https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44