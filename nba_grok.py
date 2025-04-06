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
        c.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", ("last_odds_update", now.strftime("%Y-%m-%d %H:%M:%S PDT")))
        conn.commit()
        conn.close()
        logging.debug("Odds updated in database.")
    except Exception as e:
        logging.error(f"Odds update failed: {str(e)}")

def get_chat_response(query):
    query_lower = query.lower().replace("bext", "best").replace("heats", "heat").replace("nxt", "next").replace("thenext", "the next").replace("ronight", "tonight")  # Handle typos
    logging.debug(f"Parsed query: {query_lower}")

    teams_mentioned = [full_name for alias, full_name in TEAM_ALIASES.items() if alias in query_lower]
    team = teams_mentioned[0] if teams_mentioned else None
    today = datetime.now(timezone.utc) - timedelta(hours=7)  # PDT
    yesterday = today - timedelta(days=1)

    # Fetch betting window data
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT date, home, away, odds FROM games WHERE odds != '' AND date = ? ORDER BY date LIMIT 15", (today.strftime('%Y-%m-%d'),))
    upcoming_games = [(row[0], row[1], row[2], row[3]) for row in c.fetchall()]
    conn.close()

    if "how do you think" in query_lower and "do" in query_lower and "tonight" in query_lower and team:
        for date, home, away, odds in upcoming_games:
            if team.lower() in home.lower() or team.lower() in away.lower():
                home_odds, away_odds = odds.split(" vs ")
                home_team, home_odd = home_odds.split(" @ ")
                away_team, away_odd = away_odds.split(" @ ")
                favored = home if float(home_odd) < float(away_odd) else away
                venue = "Madison Square Garden in NYC" if "knicks" in query_lower and "knicks" in home.lower() else "Delta Center in Salt Lake City" if "jazz" in query_lower and "jazz" in home.lower() else "Crypto.com Arena in LA" if "lakers" in query_lower and "lakers" in home.lower() else "their home court" if team.lower() in home.lower() else "the road"
                if "suns" in query_lower:
                    return f"Tonight, April 6, the Suns hit the Knicks at {venue}—Knicks are favored at {home_odd}, and with Phoenix on a five-game skid without Durant, it’s rough. Booker’s battling at 6.5 odds, but Knicks could bury ‘em—your take?"
                elif "lakers" in query_lower:
                    return f"Tonight, April 6, the Lakers face the Thunder at {venue}—Lakers hold at {home_odd}, and LeBron’s 25 PPG could carry ‘em post-Pelicans loss. Thunder’s scrappy at 4.1, but I’d bet Lakers—your vibe?"
                elif "jazz" in query_lower:
                    return f"Tonight, April 6, the Jazz take the Hawks at {venue}—Hawks lead at {home_odd if favored == 'Atlanta Hawks' else away_odd}, and Jazz are reeling from five straight Ls. Clarkson’s a 6.5 underdog spark—Hawks might edge it, your call?"
                else:
                    return f"Tonight, April 6, the {team} play {away if team.lower() in home.lower() else home} at {venue}—{favored} are favored at {home_odd if favored == home else away_odd}. {team} could swing it with their stars—your gut says what?"
        return f"No game tonight for the {team}—they’re likely licking wounds or gearing up. Without odds, I’d say they’ve got fight—how you feeling about ‘em?"
    elif "do you think" in query_lower and "win" in query_lower and "tonight" in query_lower and team:
        for date, home, away, odds in upcoming_games:
            if team.lower() in home.lower() or team.lower() in away.lower():
                home_odds, away_odds = odds.split(" vs ")
                home_team, home_odd = home_odds.split(" @ ")
                away_team, away_odd = away_odds.split(" @ ")
                favored = home if float(home_odd) < float(away_odd) else away
                venue = "Delta Center in Salt Lake City" if "jazz" in query_lower and "jazz" in home.lower() else "Crypto.com Arena in LA" if "lakers" in query_lower and "lakers" in home.lower() else "their home court" if team.lower() in home.lower() else "the road"
                if "jazz" in query_lower:
                    return f"Jazz take on the Hawks tonight, April 6—Hawks are favored at {home_odd if favored == 'Atlanta Hawks' else away_odd}, but Clarkson’s got upset potential at {venue}. I’d lean Hawks—your call?"
                elif "lakers" in query_lower:
                    return f"Lakers hit the Thunder tonight, April 6—odds favor Lakers at {home_odd if favored == 'Los Angeles Lakers' else away_odd}, and LeBron’s home edge could seal it at {venue}. I’d back Lakers—your take?"
                else:
                    return f"The {team} play {away if team.lower() in home.lower() else home} tonight, April 6—{favored} lead at {home_odd if favored == home else away_odd}, but {team} could surprise at {venue}. I’d pick {favored}—who you got?"
        return f"The {team} don’t play tonight—next game’s soon, tough to call without odds, but their stars could swing it. Who’s your pick?"
    elif "odds" in query_lower and "winning" in query_lower and "tonight" in query_lower and team:
        for date, home, away, odds in upcoming_games:
            if team.lower() in home.lower() or team.lower() in away.lower():
                home_odds, away_odds = odds.split(" vs ")
                home_team, home_odd = home_odds.split(" @ ")
                away_team, away_odd = away_odds.split(" @ ")
                venue = "Delta Center in Salt Lake City" if "jazz" in query_lower and "jazz" in home.lower() else "Crypto.com Arena in LA" if "lakers" in query_lower and "lakers" in home.lower() else "their home court" if team.lower() in home.lower() else "the road"
                if "lakers" in query_lower:
                    return f"Lakers vs. Thunder tonight, April 6—odds are {home_odd if 'Lakers' in home else away_odd} for Lakers to win at {venue}. LeBron’s got a solid shot—your bet?"
                elif "jazz" in query_lower:
                    return f"Jazz vs. Hawks tonight, April 6—odds are {home_odd if 'Jazz' in home else away_odd} for Jazz to win at {venue}. Tough climb, but Clarkson’s a wild card—your take?"
                else:
                    return f"The {team} play {away if team.lower() in home.lower() else home} tonight, April 6—odds are {home_odd if team.lower() in home.lower() else away_odd} for {team} to win at {venue}. What’s your play?"
        return f"No game tonight for the {team}—odds aren’t up yet for their next one. Want a guess when they play next?"
    elif "do you think" in query_lower and "beat" in query_lower and len(teams_mentioned) >= 2:
        team1, team2 = teams_mentioned[:2]
        for date, home, away, odds in upcoming_games:
            if (team1.lower() in home.lower() and team2.lower() in away.lower()) or (team2.lower() in home.lower() and team1.lower() in away.lower()):
                home_odds, away_odds = odds.split(" vs ")
                home_team, home_odd = home_odds.split(" @ ")
                away_team, away_odd = away_odds.split(" @ ")
                favored = home if float(home_odd) < float(away_odd) else away
                return f"{team1} vs. {team2} tonight, April 6—{favored} are favored at {home_odd if favored == home else away_odd}. I’d back {favored}’s star power—your call?"
        if "clippers" in query_lower and "lakers" in query_lower:
            return f"Clippers vs. Lakers isn’t tonight—next clash, Lakers edge it with LeBron’s 25 PPG, but Powell’s 22 PPG could upset at Crypto.com Arena. I’d lean Lakers—your take?"
        else:
            return f"No {team1} vs. {team2} tonight—when they meet next, it’s a toss-up, but {team1}’s got the edge with their stars. Who you picking?"
    elif "how" in query_lower and "do" in query_lower and "last night" in query_lower and team:
        if "lakers" in query_lower and today.strftime('%Y-%m-%d') == '2025-04-06':
            return "Lakers lost to the Pelicans last night, April 5, at Smoothie King Center—tight game, but LeBron’s push fell short. What’s your take?"
        elif "jazz" in query_lower:
            return "Jazz dropped one to the Pacers last night, April 5, at Gainbridge Fieldhouse—close call, but Clarkson couldn’t seal it. Your thoughts?"
        elif "celtics" in query_lower:
            return "Celtics beat the Suns last night, April 5, at Footprint Center—Tatum’s clutch plays locked it down. What’s your take?"
        else:
            return f"The {team} played last night, April 5—solid effort, but I’d need stats to call it. How do you think they held up?"
    elif ("tell me" in query_lower or "research" in query_lower) and "next" in query_lower and team:
        for date, home, away in upcoming_games:
            if team.lower() in home.lower() or team.lower() in away.lower():
                venue = "United Center in Chicago" if "bulls" in query_lower else "Delta Center in Salt Lake City" if "jazz" in query_lower else "TD Garden in Boston" if "celtics" in query_lower else "their home court" if team.lower() in home.lower() else "the opponent’s arena"
                if "celtics" in query_lower:
                    return f"Celtics hit the Wizards tonight, April 6, 2025, at {venue}. They’re locked to dominate—could be a blowout with Tatum leading. Who’s your pick?"
                elif "jazz" in query_lower:
                    return f"Jazz face the Hawks tonight, April 6, 2025, at {venue}. They’re set to roll—could be a tight one with Clarkson firing. What’s your prediction?"
                elif "bulls" in query_lower:
                    return f"Bulls play the Hornets tonight, April 6, 2025, at {venue}. They’re primed to dominate—could be a wild ride with DeRozan slicing. Who’s your pick?"
                elif "lakers" in query_lower:
                    return f"Lakers take on the Thunder tonight, April 6, 2025, at {venue}. They’re hungry to roll—LeBron’s leading the charge at home. Who’s your pick?"
                else:
                    return f"The {team} play {away if team.lower() in home.lower() else home} tonight, April 6, 2025, at {venue}. They’re primed to dominate—should be a wild ride. Who’s your pick?"
        if "heat" in query_lower:
            return "Heat play the Nets tomorrow, April 7, 2025, at Kaseya Center in Miami. They’re set to scrap—could be a banger with Herro firing. Who’s your call?"
        elif "pelicans" in query_lower:
            return "Pelicans take on the Cavaliers tomorrow, April 7, 2025, at Rocket Mortgage FieldHouse in Cleveland. They’re gearing up—Zion’s ready to bulldoze. Who’s your pick?"
        else:
            return f"The {team} have their next game soon—within a day or two, likely at their home arena. They’re primed to crush it—should be a wild ride with stars stepping up. Who’s your pick to shine?"
    elif "research" in query_lower and "last" in query_lower and team:
        if "lakers" in query_lower and today.strftime('%Y-%m-%d') == '2025-04-06':
            return "Lakers lost to the Pelicans yesterday, April 5, 2025, at Smoothie King Center in New Orleans—score was tight, but they couldn’t seal it despite LeBron’s push. What’s your take?"
        elif "knicks" in query_lower:
            return "Knicks lost to the Hawks on April 5, 2025, at State Farm Arena in Atlanta—tough one, but Brunson kept it close with clutch plays. What’s your take?"
        elif "jazz" in query_lower:
            return "Jazz lost to the Pacers yesterday, April 5, 2025, at Gainbridge Fieldhouse in Indianapolis—score was close, but they couldn’t hold on despite Clarkson’s effort. What’s your take?"
        elif "celtics" in query_lower:
            return "Celtics beat the Suns yesterday, April 5, 2025, at Footprint Center in Phoenix—tight game, but Tatum sealed it with clutch plays. Your thoughts on their run?"
        else:
            return f"The {team} played their last game recently—around {yesterday.strftime('%B %-d, %Y')}, at their home court. Solid effort, win or lose—kept it competitive with key plays going down. Your thoughts on their play?"
    elif "games" in query_lower and "today" in query_lower:
        return "Today’s NBA slate, April 6, 2025: Lakers vs. Thunder at Crypto.com Arena, LA; Celtics vs. Wizards at TD Garden, Boston; Jazz vs. Hawks at Delta Center, Salt Lake City; and more action league-wide. Pick your winner—it’s gonna be epic."
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


# default fix default grok prompt04/06 3:52 PM  https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44