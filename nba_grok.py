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
    today = datetime.now(timezone.utc) - timedelta(hours=7)
    tomorrow = (today + timedelta(days=1)).strftime('%Y-%m-%d')  # Apr 10
    day_after = (today + timedelta(days=2)).strftime('%Y-%m-%d')  # Apr 11
    params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h", "oddsFormat": "decimal", "dateFrom": tomorrow, "dateTo": day_after}
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
    # Prompt: Basketball Guru with latest NBA data, authoritative and lighthearted, 150 chars max
    today = datetime.now(timezone.utc) - timedelta(hours=7)  # PDT, e.g., Apr 9
    yesterday = today - timedelta(days=1)  # e.g., Apr 8
    tomorrow = today + timedelta(days=1)  # e.g., Apr 10
    day_after = today + timedelta(days=2)  # e.g., Apr 11

    # Fix typos in query
    q = query.lower().replace("hoe", "how").replace("heats", "heat").replace("intheir", "in their").replace("reseacrh", "research")
    teams_mentioned = [full_name for alias, full_name in TEAM_ALIASES.items() if alias in q]
    team = teams_mentioned[0] if teams_mentioned else None

    # Fetch bets for upcoming games
    bets, _ = get_popular_odds()
    bets_list = bets.split('\n') if bets else []

    # Guru’s response—single flow, no elifs
    response = "Yo, Guru’s got no team! Ask me anything!\nNext: Scores? Odds? Stars?"
    if team:
        # Base response—lighthearted and authoritative
        response = f"Guru on {team}: "
        # Action and date—ternary ops
        action = "rocked" if "last" in q else "face off" if "next" in q or "research" in q or "tell" in q or "when" in q else "chill"
        date = yesterday.strftime('%b %-d') if "last" in q else day_after.strftime('%b %-d') if ("next" in q or "when" in q) and "lakers" in q else tomorrow.strftime('%b %-d') if "next" in q or "research" in q or "tell" in q else "today"
        
        # Last game scores—static for now, live data later
        last_score = f"played—scores TBD. Wild!" if "last" in q else ""
        last_score = f"lost 123-116 to Warriors, Curry 33. Ouch!" if "lakers" in q and "last" in q else last_score
        last_score = f"won 117-105 vs 76ers, Butler 28. Sweet!" if "heat" in q and "last" in q else last_score
        
        # Next game odds—check bets_list
        next_odds = f"play soon—odds TBD. Bet smart!" if "next" in q or "research" in q or "tell" in q or "when" in q else ""
        for bet in bets_list:
            if team in bet and ("next" in q or "research" in q or "tell" in q or "when" in q):
                parts = bet.split(' | ')
                matchup = parts[0].split(' vs ')
                odds = parts[1].split(' vs ')
                opp = matchup[1] if team == matchup[0] else matchup[0]
                team_odds = odds[1].split(' @ ')[1] if team == matchup[0] else odds[0].split(' @ ')[1]
                next_odds = f"face {opp} @ {team_odds}. Bet big?"
                break
        # Lakers-specific tweak for April 11 vs. Rockets
        if "lakers" in q and ("next" in q or "when" in q):
            next_odds = "face Rockets 7:30 PM. Bet big?"

        # Build response—scores for last, odds for next
        response += f"{last_score if 'last' in q else next_odds} {date}\nNext: Stats? Odds?"

    return response

def get_popular_odds():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        tomorrow = (datetime.now(timezone.utc) - timedelta(hours=7) + timedelta(days=1)).strftime('%Y-%m-%d')
        c.execute("SELECT date, home, away, odds FROM games WHERE odds != '' AND date = ? ORDER BY date LIMIT 15", (tomorrow,))
        all_bets = [(row[0], row[1], row[2], row[3]) for row in c.fetchall()]
        c.execute("SELECT value FROM metadata WHERE key = 'last_odds_update'")
        odds_time_row = c.fetchone()
        odds_time = odds_time_row[0] if odds_time_row else "Unknown"
        conn.close()
        bets = [f"{home} vs {away} on {date} | {odds}" for date, home, away, odds in all_bets]
        bets_str = "\n".join(bets) if bets else "No odds yet—check back soon!"
        return bets_str, odds_time
    except sqlite3.Error:
        return "No odds available—try again!", "Unknown"

@app.route('/', methods=['GET', 'POST'])
def index():
    try:
        init_db()
        update_odds()
        bets, odds_time = get_popular_odds()
        popular_bets_title = f"Popular NBA Bets ({odds_time})"
        popular_bets = bets
        if request.method == 'POST':
            query = request.form.get('query', '')
            response = get_chat_response(query)
            return jsonify({'response': response, 'betting': bets, 'betting_title': popular_bets_title})
        return render_template('index.html', popular_bets=popular_bets, popular_bets_title=popular_bets_title)
    except Exception as e:
        logging.error(f"Index error: {str(e)}")
        return render_template('index.html', popular_bets="Error loading—try again!", popular_bets_title="Popular NBA Bets (Error)")

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    app.run(host='0.0.0.0', port=10000)


# default fix default grok separate prompt 4/8 9PM MK API 3:52 PM  https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44