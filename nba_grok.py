import sqlite3
from datetime import datetime, timedelta, timezone
import requests
import logging
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
ODDS_API_KEY = "b67a5835dd3254ae3960eacf0452d700"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"
DB_PATH = "nba_roster.db"

TEAM_ALIASES = {
    "hawks": "Atlanta Hawks", "celtics": "Boston Celtics", "nets": "Brooklyn Nets",
    "hornets": "Charlotte Hornets", "bulls": "Chicago Bulls", "cavs": "Cleveland Cavaliers",
    "cavaliers": "Cleveland Cavaliers", "mavs": "Dallas Mavericks", "mavericks": "Dallas Mavericks",
    "nuggets": "Denver Nuggets", "pistons": "Detroit Pistons", "warriors": "Golden State Warriors",
    "dubs": "Golden State Warriors", "rockets": "Houston Rockets", "pacers": "Indiana Pacers",
    "clippers": "Los Angeles Clippers", "lakers": "Los Angeles Lakers", "grizzlies": "Memphis Grizzlies",
    "grizz": "Memphis Grizzlies", "heat": "Miami Heat", "bucks": "Milwaukee Bucks",
    "timberwolves": "Minnesota Timberwolves", "wolves": "Minnesota Timberwolves",
    "pelicans": "New Orleans Pelicans", "pels": "New Orleans Pelicans", "knicks": "New York Knicks",
    "ny": "New York Knicks", "thunder": "Oklahoma City Thunder", "okc": "Oklahoma City Thunder",
    "magic": "Orlando Magic", "76ers": "Philadelphia 76ers", "sixers": "Philadelphia 76ers",
    "philly": "Philadelphia 76ers", "suns": "Phoenix Suns", "trail blazers": "Portland Trail Blazers",
    "blazers": "Portland Trail Blazers", "kings": "Sacramento Kings", "sactown": "Sacramento Kings",
    "spurs": "San Antonio Spurs", "raptors": "Toronto Raptors", "raps": "Toronto Raptors",
    "jazz": "Utah Jazz", "wizards": "Washington Wizards", "wiz": "Washington Wizards",
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

def update_odds():
    init_db()  # Ensure tables exist
    params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h", "oddsFormat": "decimal", "daysFrom": 7}
    try:
        logging.debug("Fetching odds from The Odds API...")
        response = requests.get(ODDS_API_URL, params=params, timeout=5)
        response.raise_for_status()
        odds_data = response.json()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for game in odds_data[:15]:
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
                c.execute("INSERT OR REPLACE INTO games (date, home, away, odds, status, score) VALUES (?, ?, ?, ?, ?, ?)",
                          (date, home, away, odds, "pending", ""))
        now = datetime.now(timezone.utc) - timedelta(hours=7)
        c.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                  ("last_odds_update", now.strftime("%Y-%m-%d %H:%M:%S PDT")))
        conn.commit()
        conn.close()
        logging.debug("Odds updated in database.")
    except Exception as e:
        logging.error(f"Odds update failed: {str(e)}")


def get_chat_response(query):
    query_lower = query.lower().replace("bset", "best")
    logging.debug(f"Parsed query: {query_lower}")

    teams_mentioned = [full_name for alias, full_name in TEAM_ALIASES.items() if alias in query_lower]
    words = query_lower.split()
    player_mentioned = any(word.isalpha() and word not in TEAM_ALIASES and word not in ["next", "last", "how", "playing", "season", "research", "tell", "about", "game", "is", "the", "in", "this", "who", "best", "record", "games", "won", "many"] for word in words)

    if "next" in query_lower and teams_mentioned:
        team = teams_mentioned[0]
        return f"The {team} have their next game scheduled soon—likely today or tomorrow, April 3 or 4, 2025, based on the current NBA slate. What do you think they’ll bring to the matchup?"
    elif "last" in query_lower and teams_mentioned:
        team = teams_mentioned[0]
        return f"The {team} played their last game recently—probably within the last day or two, around April 1-2, 2025. How do you think they did?"
    elif "how" in query_lower and "playing" in query_lower:
        if teams_mentioned:
            team = teams_mentioned[0]
            if player_mentioned:
                return f"Players on the {team} are putting up solid numbers this season—think points, rebounds, and assists in the 20s and up. Who’s your favorite on their roster to break down further?"
            return f"The {team} have been battling it out this season—mixing wins and losses with strong team play. How do you rate their effort so far?"
        elif player_mentioned:
            return "That player’s been making moves this season—solid stats across the board, though I’d need a team to get precise. What do you think of their performance?"
    elif ("best scorer" in query_lower or "highest scorer" in query_lower) and teams_mentioned:
        team = teams_mentioned[0]
        return f"The {team} have a top scorer lighting it up—likely averaging over 30 points per game this season. Who do you think’s their scoring ace?"
    elif "best shooter" in query_lower and teams_mentioned:
        team = teams_mentioned[0]
        return f"The {team} have some sharpshooters sinking threes—probably a few per game. Who do you see as their top shot-maker?"
    elif "best player" in query_lower and teams_mentioned:
        team = teams_mentioned[0]
        return f"The {team} boast some elite talent—stars shining with big stats. Who’s your pick for their standout player?"
    elif ("winning record" in query_lower or "record" in query_lower or ("games" in query_lower and "won" in query_lower)) and teams_mentioned:
        team = teams_mentioned[0]
        return f"The {team} are around a .500 record this season as of April 2025—splitting wins and losses pretty evenly. What’s your take on their run?"
    else:
        return "Hey, I’ve got the full NBA scoop—games, players, stats, whatever you’re into. What’s on your mind?"

def get_popular_odds(query=""):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT date, home, away, odds FROM games WHERE odds != '' AND date >= ? ORDER BY date LIMIT 15",
                  (datetime.now(timezone.utc).strftime('%Y-%m-%d'),))
        all_bets = [(row[0], row[1], row[2], row[3]) for row in c.fetchall()]
        c.execute("SELECT value FROM metadata WHERE key = 'last_odds_update'")
        odds_time_row = c.fetchone()
        odds_time = odds_time_row[0] if odds_time_row else "Unknown"
        conn.close()

        query_lower = query.lower()
        team_bets = []
        popular_bets = []
        for date, home, away, odds in all_bets:
            bet_str = f"{home} vs {away} on {date} | {odds} | click here to go"
            if any(alias in query_lower for alias in TEAM_ALIASES if TEAM_ALIASES[alias].lower() in (home.lower(), away.lower())):
                team_bets.append(bet_str)
            else:
                popular_bets.append(bet_str)
        
        bets = team_bets[:2] + popular_bets[:5 - len(team_bets[:2])]
        bets_str = "\n".join(bets) if bets else "No odds yet—check back soon!"
        return bets_str, odds_time
    except Exception as e:
        logging.error(f"Get popular odds error: {str(e)}")
        return "No odds available—try again later!", "Unknown"

@app.route('/', methods=['GET', 'POST'])
def index():
    try:
        init_db()
        update_odds()
        bets, odds_time = get_popular_odds("")
        popular_bets_title = f"Popular NBA Bets ({odds_time})"
        popular_bets = bets
        if request.method == 'POST':
            query = request.form.get('query', '')
            response = get_chat_response(query)
            bets, odds_time = get_popular_odds(query)
            return jsonify({'response': response, 'betting': bets, 'betting_title': f"Popular NBA Bets ({odds_time})"})
        return render_template('index.html', popular_bets=popular_bets, popular_bets_title=popular_bets_title)
    except Exception as e:
        logging.error(f"Index error: {str(e)}")
        return render_template('index.html', popular_bets="Error loading data", popular_bets_title="Popular NBA Bets (Error)")

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    app.run(host='0.0.0.0', port=10000)

# degfault to grok3 https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44