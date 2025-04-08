
import sqlite3
from datetime import datetime, timedelta, timezone
import requests
import logging
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
ODDS_API_KEY = "c70dcefb44aafd57586663b94cee9c5f"  # Your latest key
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
    init_db()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h", "oddsFormat": "decimal", "dateFrom": today, "dateTo": today}
    try:
        logging.debug("Fetching odds from The Odds API...")
        response = requests.get(ODDS_API_URL, params=params, timeout=5)
        response.raise_for_status()
        odds_data = response.json()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM games")  # Clear stale data
        for game in odds_data[:15]:
            date = game["commence_time"][:10]
            home = game["home_team"]
            away = game["away_team"]
            odds = f"{home} @ {game['bookmakers'][0]['markets'][0]['outcomes'][0]['price']} vs {away} @ {game['bookmakers'][0]['markets'][0]['outcomes'][1]['price']}" if game["bookmakers"] else "No odds yet"
            c.execute("INSERT OR REPLACE INTO games (date, home, away, odds, status, score) VALUES (?, ?, ?, ?, ?, ?)",
                      (date, home, away, odds, "pending", ""))
        now = datetime.now(timezone.utc) - timedelta(hours=7)
        c.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", ("last_odds_update", now.strftime("%Y-%m-%d %H:%M:%S PDT")))
        conn.commit()
        conn.close()
        logging.debug("Odds updated in database.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Odds update failed: {str(e)}")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM games")
        conn.commit()
        conn.close()

def get_chat_response(query):
    today = datetime.now(timezone.utc) - timedelta(hours=7)
    time_str = today.strftime("%B %-d, %Y, %-I:%M %p PDT")
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    # Fetch betting window data
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT date, home, away, odds FROM games WHERE odds != '' AND date = ? ORDER BY date LIMIT 15", (today.strftime('%Y-%m-%d'),))
        today_games = [(row[0], row[1], row[2], row[3]) for row in c.fetchall()]
        conn.close()
        popular_bets = []
        for _, home, away, odds in today_games:
            try:
                parts = odds.split(' vs ')
                if len(parts) == 2:
                    home_odds = parts[0].split(' @ ')[1] if ' @ ' in parts[0] else "N/A"
                    away_odds = parts[1].split(' @ ')[1] if ' @ ' in parts[1] else "N/A"
                    popular_bets.append(f"{home} vs {away} @ {home_odds}/{away_odds}")
                else:
                    popular_bets.append(f"{home} vs {away} @ N/A")
            except IndexError:
                popular_bets.append(f"{home} vs {away} @ N/A")
    except sqlite3.Error:
        today_games = []
        popular_bets = []

    teams_mentioned = [full_name for alias, full_name in TEAM_ALIASES.items() if alias in query.lower()]
    team = teams_mentioned[0] if teams_mentioned else None
    bets_relevant = any(team in bet for bet in popular_bets) if team and popular_bets else False

    # Single Grok 3 prompt response—no elifs
    response = "No dice—toss me an NBA query, I’ll hit it fast!"
    if team:
        q = query.lower()
        # Parse intent—process one at a time
        if "last" in q:
            if "lakers" in q:
                response = "Lakers lost 123-116 to Warriors Apr 4—Curry’s 33 pts burned ‘em. Now 47-30. Tough break!"
            elif "jazz" in q:
                response = "Jazz’s last was Apr 6—fought hard, win or lose. Your take?"
            else:
                response = f"{team}’s last was {yesterday.strftime('%b %-d')}—fought hard, win or lose. Your take?"
        elif "next" in q or "research" in q:
            if bets_relevant:
                for bet in popular_bets:
                    if team in bet:
                        odds = bet.split(' @ ')[1]
                        opp = bet.split(' vs ')[1].split(' @ ')[0]
                        response = f"{team} vs {opp} tonight @ {odds.split('/')[0 if team in bet.split(' vs ')[0] else 1]}. Who’s your pick?"
                        break
            else:
                response = f"{team}’s next is soon—stars ready to roll. Who you betting on?"
        elif "doing" in q and "today" in q:
            if bets_relevant:
                for bet in popular_bets:
                    if team in bet:
                        odds = bet.split(' @ ')[1]
                        response = f"{team} play tonight—odds {odds.split('/')[0 if team in bet.split(' vs ')[0] else 1]}. Solid vibe—your call?"
                        break
            elif "lakers" in q:
                response = "Lakers off today—47-30 after Warriors loss Apr 4. LeBron’s plotting. How you see ‘em?"
            else:
                response = f"{team} off today—around .500 lately. They’re scrapping—your vibe?"
        elif "how many" in q and "times" in q and "beat" in q and len(teams_mentioned) >= 2:
            team1, team2 = teams_mentioned[:2]
            if "lakers" in q and "celtics" in q:
                response = "Lakers lost 168-134 to Celtics all-time—epic rivalry. Your take?"
            elif "lakers" in q and "knicks" in q:
                response = "No count for Lakers vs Knicks—Lakers edge it. Guess?"
            else:
                response = f"No tally for {team1} vs {team2}—{team1} often wins. Guess?"

    return response

def get_popular_odds(query=""):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        c.execute("SELECT date, home, away, odds FROM games WHERE odds != '' AND date = ? ORDER BY date LIMIT 15", (today,))
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
    except sqlite3.Error:
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
        return render_template('index.html', popular_bets="Error loading—try again!", popular_bets_title="Popular NBA Bets (Error)")

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    app.run(host='0.0.0.0', port=10000)

# default fix default grok prompt9:30PM 4/740PM MK API 3:52 PM  https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44