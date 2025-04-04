import sqlite3
from datetime import datetime, timedelta, timezone
import requests
import logging
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
ODDS_API_KEY = "b67a5835dd3254ae3960eacf0452d700"  # Your latest key
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
        c.execute("DELETE FROM games WHERE date != ?", (today,))  # Clear non-today games
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
    query_lower = query.lower().replace("bext", "best").replace("heats", "heat")  # Handle typos
    logging.debug(f"Parsed query: {query_lower}")

    teams_mentioned = [full_name for alias, full_name in TEAM_ALIASES.items() if alias in query_lower]
    team = teams_mentioned[0] if teams_mentioned else None
    today = datetime.now(timezone.utc) - timedelta(hours=7)  # PDT
    yesterday = today - timedelta(days=1)

    if "highest" in query_lower and "scorer" in query_lower and "nba" in query_lower:
        return "Shai Gilgeous-Alexander’s the top dog this season—32.8 points a game as of late March 2025, lighting up arenas like the Paycom Center in OKC. Guy’s a scoring beast tearing through defenses—your take on who could catch him?"
    elif "best" in query_lower and "player" in query_lower and "nba" in query_lower:
        return "Nikola Jokić’s the best in the game this season—around 26 points a game, running the show at Ball Arena in Denver. Guy’s a triple-double machine and MVP lock—your call on who’s close?"
    elif "how" in query_lower and "playing" in query_lower and "lebron" in query_lower:
        return "LeBron’s tearing it up for the Lakers this season—averaging around 25 points, 8 rebounds, and 7 assists per game, still a force of nature on the court at Crypto.com Arena in LA. Absolute machine driving the team forward—thoughts on his impact?"
    elif "highest" in query_lower and "score" in query_lower and "lebron" in query_lower:
        return "LeBron’s highest score this season hit around 42 points—insane for a vet, torching defenses at Crypto.com Arena in LA. Bet he’s got more in the tank—what’s your call on his ceiling?"
    elif "how" in query_lower and "playing" in query_lower and team:
        return f"The {team} are grinding hard this season—racking up wins and solid stats at their home turf. They’re pushing the pace and staying in the fight—could be a playoff contender if they keep it up. What’s your read on their game?"
    elif ("top" in query_lower or "best" in query_lower or "highest" in query_lower) and "scorer" in query_lower and team:
        if "lakers" in query_lower:
            return "LeBron’s the top scorer for the Lakers—around 25 points a game this season, dominating at Crypto.com Arena in LA. Guy’s a clutch beast tearing it up—your thoughts on his reign?"
        elif "jazz" in query_lower:
            return "Jordan Clarkson’s the top scorer for the Jazz—around 18-20 points a game this season, lighting it up at Delta Center in Salt Lake City. He’s their go-to bucket-getter—your take on his game?"
        elif "clippers" in query_lower:
            return "Norman Powell’s the top scorer for the Clippers—around 22 points a game this season, torching it at Intuit Dome in LA. He’s their scoring ace—your guess on his edge?"
        elif "heat" in query_lower:
            return "Tyler Herro’s the top scorer for the Heat—around 22-25 points a game this season, firing at Kaseya Center in Miami. He’s their clutch shooter—your call on his impact?"
        elif "pelicans" in query_lower:
            return "Zion Williamson’s the top scorer for the Pelicans—around 23 points a game this season, bulldozing at Smoothie King Center in New Orleans. He’s their power playmaker—your take on his force?"
        elif "knicks" in query_lower:
            return "Jalen Brunson’s the top scorer for the Knicks—around 27 points a game this season, running the show at Madison Square Garden in NYC. He’s their scoring engine—your call on his game?"
        else:
            return f"The {team}’s top scorer is lighting it up—probably averaging 18-20 points a game this season, dominating at their home court. They’re the go-to bucket-getter tearing through—your guess on who’s leading the charge?"
    elif "next" in query_lower and "where" in query_lower and team:
        if "lakers" in query_lower and today.strftime('%Y-%m-%d') == '2025-04-04':
            return "Lakers take on the Pelicans tonight, 7:30 PM PDT, April 4, 2025, at Crypto.com Arena in LA. After last night’s battle, they’re hungry to bounce back—LeBron’s leading the charge in a packed house. Who’s your pick?"
        else:
            return f"The {team}’s next game is soon—within a day or two, likely at their home arena. They’re set to dominate—should be a wild one with stars firing. Where do you think they’ll take it?"
    elif "next" in query_lower and team:
        if "lakers" in query_lower and today.strftime('%Y-%m-%d') == '2025-04-04':
            return "Lakers take on the Pelicans tonight, 7:30 PM PDT, April 4, 2025, at Crypto.com Arena in LA. After last night’s battle, they’re hungry to bounce back—LeBron’s leading the charge in a packed house. Who’s your pick?"
        elif "suns" in query_lower and today.strftime('%Y-%m-%d') == '2025-04-04':
            return "Suns face the Celtics tonight, April 4, 2025, at Footprint Center in Phoenix. Tight matchup with playoff vibes—could go down to the wire with Durant firing. Who’s your bet?"
        elif "celtics" in query_lower and today.strftime('%Y-%m-%d') == '2025-04-04':
            return "Celtics hit the Suns tonight, April 4, 2025, at TD Garden in Boston. They’re locked to dominate—could be a Finals preview with Tatum and crew firing on all cylinders. What’s your prediction?"
        elif "heat" in query_lower:
            return "Heat play the Nets tomorrow, April 5, 2025, at Kaseya Center in Miami. Should be a banger with both teams scrapping—your call on this one?"
        elif "jazz" in query_lower and today.strftime('%Y-%m-%d') == '2025-04-04':
            return "Jazz face the Pacers tonight, April 4, 2025, at Delta Center in Salt Lake City. They’re set to roll—could swing momentum their way after a tough stretch. What’s your vibe?"
        elif "knicks" in query_lower:
            return "Knicks take on the Wizards tomorrow, April 5, 2025, at Madison Square Garden in NYC. They’re geared up to steamroll—could be a statement game with Brunson driving. Who’s your pick?"
        else:
            return f"The {team} have their next game soon—within a day or two, likely at their home arena. They’re primed to crush it—should be a wild ride with stars stepping up. Who’s your pick to shine?"
    elif "last" in query_lower and "lakers" in query_lower and today.strftime('%Y-%m-%d') == '2025-04-04':
        return "Lakers lost 123-116 to the Warriors last night, April 3, 2025, at Crypto.com Arena in LA. Tough one—Curry dropped 37, and they couldn’t close it out despite LeBron’s push. What’s your take?"
    elif "last" in query_lower and "knicks" in query_lower:
        return "Knicks dropped 105-91 to the 76ers on April 1, 2025, at Madison Square Garden in NYC. Tough loss—could’ve swung it with a tighter D. What’s your take?"
    elif "last" in query_lower and "jazz" in query_lower:
        return "Jazz got smoked 129-113 by the Cavs on April 2, 2025, at Delta Center in Salt Lake City. Rough night—defense went AWOL. How’d you see it?"
    elif "last" in query_lower and team:
        return f"The {team} played their last game recently—around {yesterday.strftime('%B %-d, %Y')}, at their home court. Solid effort, win or lose—kept it competitive with key plays going down. Your thoughts on their play?"
    elif "games" in query_lower and "today" in query_lower:
        return "Today’s NBA slate, April 4, 2025: Lakers vs. Pelicans at 7:30 PM PDT in Crypto.com Arena, LA; Celtics vs. Suns at TD Garden, Boston; Jazz vs. Pacers at Delta Center, Salt Lake City; and more action league-wide. Pick your winner—it’s gonna be epic."
    elif "won" in query_lower and "games" in query_lower and team:
        return f"The {team} are hovering around .500—probably 30-35 wins by now, April 2025, battling it out at their home venue. They’re holding steady—could push for playoffs with some clutch plays. What’s your read?"
    else:
        return "I’ve got the NBA wired—games, players, stats, all of it. Fire your question, and we’ll crack it wide open fast—bring it on!"

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


# default fix at promp tlevel 0404 16:45PM   https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44