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
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')  # Fixed to current date
    params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h", "oddsFormat": "decimal", "dateFrom": today, "dateTo": today}
    try:
        logging.debug("Fetching odds from The Odds API...")
        response = requests.get(ODDS_API_URL, params=params, timeout=5)
        response.raise_for_status()  # Raises exception for 4xx/5xx errors
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
    except requests.exceptions.RequestException as e:
        logging.error(f"Odds update failed: {str(e)}")
        raise  # Re-raise to handle gracefully upstream

def get_chat_response(query):
    query_lower = query.lower().replace("bext", "best").replace("heats", "heat").replace("nxt", "next").replace("thenext", "the next").replace("ronight", "tonight").replace("th enext", "the next")
    logging.debug(f"Parsed query: {query_lower}")

    teams_mentioned = [full_name for alias, full_name in TEAM_ALIASES.items() if alias in query_lower]
    team = teams_mentioned[0] if teams_mentioned else None
    today = datetime.now(timezone.utc) - timedelta(hours=7)  # PDT
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    # Fetch betting window data
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT date, home, away, odds FROM games WHERE odds != '' AND date = ? ORDER BY date LIMIT 15", (today.strftime('%Y-%m-%d'),))
        upcoming_games = [(row[0], row[1], row[2], row[3]) for row in c.fetchall()]
        conn.close()
    except sqlite3.Error as e:
        logging.error(f"Database error: {str(e)}")
        upcoming_games = []

    # Grok.com-style prompt: How do you think [team] will do today/tonight?
    if "how do you think" in query_lower and "do" in query_lower and ("today" in query_lower or "tonight" in query_lower) and team:
        for date, home, away, odds in upcoming_games:
            if team.lower() in home.lower() or team.lower() in away.lower():
                home_odds, away_odds = odds.split(" vs ")
                home_team, home_odd = home_odds.split(" @ ")
                away_team, away_odd = away_odds.split(" @ ")
                favored = home if float(home_odd) < float(away_odd) else away
                team_odds = home_odd if team.lower() in home.lower() else away_odd
                venue = "Madison Square Garden in NYC" if "knicks" in query_lower and "knicks" in home.lower() else "Delta Center in Salt Lake City" if "jazz" in query_lower and "jazz" in home.lower() else "Crypto.com Arena in LA" if "lakers" in query_lower and "lakers" in home.lower() else "their home court" if team.lower() in home.lower() else "the road"
                opponent = away if team.lower() in home.lower() else home
                if "suns" in query_lower:
                    return f"Tonight, April 6, 2025, the Suns take on the Knicks at {venue}. They’re on a brutal five-game skid—last loss was 123-103 to the Celtics on April 4—and sit at 35-42, barely hanging on for a play-in spot. No Durant’s a killer, but Booker’s scrapping at {team_odds} odds. Knicks are favored at {home_odd if favored == 'New York Knicks' else away_odd}—I’d say New York rolls unless Booker goes off. Your take?"
                elif "jazz" in query_lower:
                    return f"Tonight, April 6, 2025, the Jazz face the Hawks at {venue}. They’ve dropped five straight, last to the Pacers, and are hovering around .500. Clarkson’s their spark, but Hawks are crushing it at {home_odd if favored == 'Atlanta Hawks' else away_odd}, Jazz at {team_odds}. Atlanta’s got the mojo—I’d bet they bury Utah unless Clarkson flips it. Your call?"
                elif "lakers" in query_lower:
                    return f"Tonight, April 6, 2025, the Lakers clash with the Thunder at {venue}. They’re 47-30, tops in the Pacific, but fresh off a tight Pelicans loss. LeBron’s 25 PPG keeps ‘em at {team_odds}, favored over Thunder’s {away_odd if team.lower() in home.lower() else home_odd}. I’d say Lakers rebound hard—your vibe?"
                else:
                    return f"Tonight, April 6, 2025, the {team} play {opponent} at {venue}. They’re coming off recent games with mixed vibes—odds put {favored} at {home_odd if favored == home else away_odd}, {team} at {team_odds}. {team} could swing it with their stars—I’d lean {favored}, but it’s tight. Your gut?"
        return f"No game tonight for the {team}—they’re likely prepping their next move. Coming off yesterday, I’d say they’ve got fight left—how you seeing it?"
    elif "do you think" in query_lower and "win" in query_lower and "tonight" in query_lower and team:
        for date, home, away, odds in upcoming_games:
            if team.lower() in home.lower() or team.lower() in away.lower():
                home_odds, away_odds = odds.split(" vs ")
                home_team, home_odd = home_odds.split(" @ ")
                away_team, away_odd = away_odds.split(" @ ")
                favored = home if float(home_odd) < float(away_odd) else away
                team_odds = home_odd if team.lower() in home.lower() else away_odd
                venue = "Delta Center in Salt Lake City" if "jazz" in query_lower and "jazz" in home.lower() else "Crypto.com Arena in LA" if "lakers" in query_lower and "lakers" in home.lower() else "their home court" if team.lower() in home.lower() else "the road"
                opponent = away if team.lower() in home.lower() else home
                if "jazz" in query_lower:
                    return f"Jazz vs. Hawks tonight, April 6—Hawks are favored at {home_odd if favored == 'Atlanta Hawks' else away_odd}, Jazz at {team_odds}. Clarkson’s their shot, but Atlanta’s rolling—I’d say Hawks take it at {venue}. Your pick?"
                elif "lakers" in query_lower:
                    return f"Lakers vs. Thunder tonight, April 6—Lakers lead at {team_odds}, Thunder at {away_odd if team.lower() in home.lower() else home_odd}. LeBron’s clutch at {venue}—I’d bet Lakers win. Your call?"
                else:
                    return f"The {team} play {opponent} tonight, April 6—{favored} are favored at {home_odd if favored == home else away_odd}, {team} at {team_odds}. I’d back {favored} at {venue}—who you got?"
        return f"No game tonight for the {team}—next one’s soon, no odds yet, but their stars give ‘em a shot. Who’s your pick?"
    elif "odds" in query_lower and "winning" in query_lower and "tonight" in query_lower and team:
        for date, home, away, odds in upcoming_games:
            if team.lower() in home.lower() or team.lower() in away.lower():
                home_odds, away_odds = odds.split(" vs ")
                home_team, home_odd = home_odds.split(" @ ")
                away_team, away_odd = away_odds.split(" @ ")
                team_odds = home_odd if team.lower() in home.lower() else away_odd
                venue = "Delta Center in Salt Lake City" if "jazz" in query_lower and "jazz" in home.lower() else "Crypto.com Arena in LA" if "lakers" in query_lower and "lakers" in home.lower() else "their home court" if team.lower() in home.lower() else "the road"
                opponent = away if team.lower() in home.lower() else home
                if "lakers" in query_lower:
                    return f"Lakers vs. Thunder tonight, April 6—odds are {team_odds} for Lakers to win at {venue}. LeBron’s a beast—your bet?"
                elif "jazz" in query_lower:
                    return f"Jazz vs. Hawks tonight, April 6—odds are {team_odds} for Jazz to win at {venue}. Tough sledding—your take?"
                else:
                    return f"The {team} play {opponent} tonight, April 6—odds are {team_odds} for {team} to win at {venue}. What’s your play?"
        return f"No game tonight for the {team}—odds aren’t up yet for their next one. Want a guess when they play?"
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
                opponent = away if team.lower() in home.lower() else home
                if "celtics" in query_lower:
                    return f"Celtics hit the Wizards tonight, April 6, 2025, at {venue}. They’re locked to dominate—could be a blowout with Tatum leading. Who’s your pick?"
                elif "jazz" in query_lower:
                    return f"Jazz face the Hawks tonight, April 6, 2025, at {venue}. They’re set to roll—could be a tight one with Clarkson firing. What’s your prediction?"
                elif "bulls" in query_lower:
                    return f"Bulls play the Hornets tonight, April 6, 2025, at {venue}. They’re primed to dominate—could be a wild ride with DeRozan slicing. Who’s your pick?"
                elif "lakers" in query_lower:
                    return f"Lakers take on the Thunder tonight, April 6, 2025, at {venue}. They’re hungry to roll—LeBron’s leading the charge at home. Who’s your pick?"
                elif "clippers" in query_lower:
                    return f"Clippers don’t play tonight—their next game’s soon, likely at Intuit Dome. Powell’s 22 PPG will be key—could be a banger. Who’s your pick?"
                else:
                    return f"The {team} play {opponent} tonight, April 6, 2025, at {venue}. They’re primed to dominate—should be a wild ride. Who’s your pick?"
        if "lakers" in query_lower and today.strftime('%Y-%m-%d') == '2025-04-06':
            return "Lakers face the Cavaliers tomorrow, April 7, 2025, at Crypto.com Arena in LA. They’re hungry to bounce back—LeBron’s leading the charge. Who’s your pick?"
        elif "heat" in query_lower:
            return "Heat play the Nets tomorrow, April 7, 2025, at Kaseya Center in Miami. They’re set to scrap—could be a banger with Herro firing. Who’s your call?"
        elif "pelicans" in query_lower:
            return "Pelicans take on the Cavaliers tomorrow, April 7, 2025, at Rocket Mortgage FieldHouse in Cleveland. They’re gearing up—Zion’s ready to bulldoze. Who’s your pick?"
        elif "clippers" in query_lower:
            return f"Clippers don’t play tonight—their next game’s soon, likely at Intuit Dome. Powell’s 22 PPG will be key—could be a banger. Who’s your pick?"
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
        return "Today’s NBA slate, April 6, 2025: Knicks vs. Suns at Madison Square Garden, NYC; Jazz vs. Hawks at Delta Center, Salt Lake City; and more action league-wide. Pick your winner—it’s gonna be epic."
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
    except sqlite3.Error as e:
        logging.error(f"Get popular odds error: {str(e)}")
        return "No odds available—try again later!", "Unknown"

@app.route('/', methods=['GET', 'POST'])
def index():
    try:
        init_db()
        update_odds()  # Fetch odds on startup
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
        return render_template('index.html', popular_bets="Error loading data—check back soon!", popular_bets_title="Popular NBA Bets (Error)")

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    app.run(host='0.0.0.0', port=10000)



# default fix default grok prompt07:40PM MK API 3:52 PM  https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44