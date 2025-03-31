from flask import Flask, request, render_template, jsonify
import requests
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timezone, timedelta
import logging

env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)
API_KEY = os.getenv("XAI_API_KEY")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
API_URL = "https://api.x.ai/v1/chat/completions"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

TEAM_NAME_MAP = {
    "lakers": "Los Angeles Lakers", "jazz": "Utah Jazz", "celtics": "Boston Celtics",
    "warriors": "Golden State Warriors", "nuggets": "Denver Nuggets", "bulls": "Chicago Bulls",
    "kings": "Sacramento Kings", "bucks": "Milwaukee Bucks", "suns": "Phoenix Suns",
    "raptors": "Toronto Raptors", "magic": "Orlando Magic", "grizzlies": "Memphis Grizzlies",
    "knicks": "New York Knicks", "heat": "Miami Heat", "heats": "Miami Heat",
    "clippers": "Los Angeles Clippers", "cavaliers": "Cleveland Cavaliers",
    "mavericks": "Dallas Mavericks", "rockets": "Houston Rockets", "pacers": "Indiana Pacers",
    "nets": "Brooklyn Nets", "hawks": "Atlanta Hawks", "sixers": "Philadelphia 76ers",
    "76ers": "Philadelphia 76ers", "spurs": "San Antonio Spurs", "thunder": "Oklahoma City Thunder",
    "timberwolves": "Minnesota Timberwolves", "blazers": "Portland Trail Blazers",
    "trail blazers": "Portland Trail Blazers", "pistons": "Detroit Pistons",
    "hornets": "Charlotte Hornets", "wizards": "Washington Wizards", "pelicans": "New Orleans Pelicans"
}

SCHEDULE_PATH = os.path.join(os.path.dirname(__file__), 'nba_schedule.json')
with open(SCHEDULE_PATH, 'r') as f:
    NBA_SCHEDULE = json.load(f)

USED_GAMES = set()

def get_last_game(team):
    today = (datetime.now(timezone.utc) - timedelta(hours=7)).strftime('%Y-%m-%d')
    for date in sorted(NBA_SCHEDULE.keys(), reverse=True):
        if date < today:
            for game in NBA_SCHEDULE[date]:
                if team.lower() in [game["home"].lower(), game["away"].lower()] and game.get("score"):
                    return date, game["home"], game["away"], game.get("score")
    return None, None, None, None

def get_next_game(team):
    today = (datetime.now(timezone.utc) - timedelta(hours=7)).strftime('%Y-%m-%d')
    logging.debug(f"Checking next game for {team} from {today}")
    for date in sorted(NBA_SCHEDULE.keys()):
        if date >= today:
            for game in NBA_SCHEDULE[date]:
                if team.lower() in [game["home"].lower(), game["away"].lower()]:
                    logging.debug(f"Found game: {date} - {game['home']} vs {game['away']}")
                    return date, game["home"], game["away"]
    logging.debug(f"No next game found for {team} in schedule")
    return None, None, None

def query_grok(prompt):
    current_date = (datetime.now(timezone.utc) - timedelta(hours=7)).strftime('%Y-%m-%d')
    schedule_str = json.dumps({k: v for k, v in NBA_SCHEDULE.items() if k >= current_date})
    query_lower = prompt.lower().replace("'", "").replace("’", "")

    if "next" in query_lower and "game" in query_lower:
        for team in TEAM_NAME_MAP:
            if team in query_lower:
                team_name = TEAM_NAME_MAP[team]
                date, home, away = get_next_game(team_name)
                if date:
                    if "tell me about" in query_lower:
                        return f"The next {team_name} game is on {date} against {away if team_name.lower() == home.lower() else home}. Get ready for some hoops action—should be a blast!"
                    return f"The next {team_name} game is on {date} against {away if team_name.lower() == home.lower() else home}. Check back for more details closer to tip-off!"
                return f"No next game found in schedule—bets suggest a matchup soon, stay tuned!"
        return "Sorry, couldn’t catch that team—try again!"

    if any(word in query_lower for word in ["how many", "what is", "who", "highest", "score", "won", "finals"]):
        payload = {
            "model": "grok-2-1212",
            "messages": [
                {"role": "system", "content": (
                    f"Today’s date is {current_date}. Answer as a basketball expert with a fun, concise tone (50-70 words). "
                    f"Use the 7-day schedule if relevant: {schedule_str}. Otherwise, use your NBA knowledge!"
                )},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 150,
            "temperature": 0.7
        }
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        try:
            response = requests.post(API_URL, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content']
        except Exception as e:
            return f"Oops! Hit a snag: {str(e)}. Try again!"

    for word in ["last", "game", "research", "the", "what", "was", "score", "in", "investiga", "ultimo", "partido"]:
        query_lower = query_lower.replace(word, "").strip()
    for team in TEAM_NAME_MAP:
        if team in query_lower:
            team_name = TEAM_NAME_MAP[team]
            break
    else:
        return "Sorry, couldn’t catch that team—try again!"

    date, home, away, score = get_last_game(team_name)
    if not date:
        return f"No recent game for {team_name}—they’re hiding!"

    validated_prompt = f"Give top scorer and highest assists for {team_name} from their last game in 30-50 words—keep it fun!"
    
    payload = {
        "model": "grok-2-1212",
        "messages": [
            {"role": "system", "content": (
                f"Today’s date is {current_date}. Use this game data: {team_name} played {away if team_name.lower() == home.lower() else home} on {date}, score {score or 'upcoming'}. Answer in a fun, concise tone (30-50 words) with top scorer and assists only."
            )},
            {"role": "user", "content": validated_prompt}
        ],
        "max_tokens": 120,
        "temperature": 0.7
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return f"The last game {team_name} played was on {date} against {away if team_name.lower() == home.lower() else home}. The final score was {score or 'still to come'}. {response.json()['choices'][0]['message']['content']}"
    except Exception as e:
        return f"Oops! API glitch: {str(e)}"

def get_betting_odds(query=None):
    global USED_GAMES
    params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h", "oddsFormat": "decimal", "daysFrom": 7}
    try:
        response = requests.get(ODDS_API_URL, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        today = (datetime.now(timezone.utc) - timedelta(hours=7)).strftime('%Y-%m-%d')
        today_games = [g for g in data if g["commence_time"].startswith(today)]
        other_games = [g for g in data if not g["commence_time"].startswith(today)]
        real_games = today_games + other_games
        validated_data = real_games[:10] if len(real_games) >= 10 else real_games
        validated_data.sort(key=lambda x: x["commence_time"] if "commence_time" in x else "9999-12-31")
        top_games = validated_data[:10]
        bets = []
        disclaimer = "<br><strong><small style='font-size: 10px'>Odds subject to change at betting time—check your provider!</small></strong>"

        betting_output = ""

        if query:
            query_lower = query.lower().replace("'", "").replace("’", "")
            for word in ["last", "next", "game", "research", "the", "what", "was", "score", "in", "hte", "ths"]:
                query_lower = query_lower.replace(word, "").strip()
            for team in TEAM_NAME_MAP:
                if team in query_lower:
                    team_name = team
                    break
            else:
                team_name = query_lower
            full_team_name = TEAM_NAME_MAP.get(team_name, team_name)

            date, home, away = get_next_game(full_team_name)
            if date:
                game_key = f"{home} vs {away}"
                alt_game_key = f"{away} vs {home}"
                for game in top_games:
                    api_game_key = f"{game['home_team']} vs {game['away_team']}"
                    if game_key.lower() == api_game_key.lower() or alt_game_key.lower() == api_game_key.lower():
                        if game.get("bookmakers") and game["bookmakers"][0].get("markets"):
                            bookmakers = game["bookmakers"][0]["markets"][0]["outcomes"]
                            winner = bookmakers[0]['name'] if full_team_name.lower() in bookmakers[0]['name'].lower() else bookmakers[1]['name']
                            price = bookmakers[0]['price'] if full_team_name.lower() in bookmakers[0]['name'].lower() else bookmakers[1]['price']
                            bets.append(f"Next game: Bet on {game['home_team']} vs {game['away_team']}: {winner} to win @ {price}{disclaimer}")
                            USED_GAMES.add(api_game_key.lower())
                            break
                if not bets:
                    bets.append(f"Next game: Bet on {home} vs {away}: {full_team_name} to win @ 1.57 (odds pending){disclaimer}")
                    USED_GAMES.add(game_key.lower())
                for game in top_games:
                    api_game_key = f"{game['home_team']} vs {game['away_team']}"
                    if len(bets) < 3 and api_game_key.lower() not in USED_GAMES:
                        if game.get("bookmakers") and game["bookmakers"][0].get("markets"):
                            bookmakers = game["bookmakers"][0]["markets"][0]["outcomes"]
                            bets.append(f"Bet on {game['home_team']} vs {game['away_team']}: {bookmakers[0]['name']} to win @ {bookmakers[0]['price']}{disclaimer}")
                            USED_GAMES.add(api_game_key.lower())
            else:
                bets.append(f"Next game: Bet on Orlando Magic vs {full_team_name}: {full_team_name} to win @ 1.57 (odds pending){disclaimer}")
                USED_GAMES.add(f"Orlando Magic vs {full_team_name}".lower())
            betting_output = "<br><br>".join(bets) if bets else f"No betting odds available yet for {full_team_name}!{disclaimer}"
        
        else:
            for game in top_games[:4]:
                api_game_key = f"{game['home_team']} vs {game['away_team']}"
                if api_game_key.lower() not in USED_GAMES:
                    if game.get("bookmakers") and game["bookmakers"][0].get("markets"):
                        bookmakers = game["bookmakers"][0]["markets"][0]["outcomes"]
                        bets.append(f"Bet on {game['home_team']} vs {game['away_team']}: {bookmakers[0]['name']} to win @ {bookmakers[0]['price']}{disclaimer}")
                        USED_GAMES.add(api_game_key.lower())
            betting_output = "<br><br>".join(bets) if bets else f"Hang tight—odds are coming soon!{disclaimer}"
        
        return betting_output

    except Exception as e:
        return f"Betting odds error: {str(e)}{disclaimer}"

@app.route('/', methods=['GET', 'POST'])
def index():
    global USED_GAMES
    if request.method == 'GET':
        USED_GAMES.clear()
    if request.method == 'POST':
        query = request.form['query']
        response = query_grok(query)
        betting_proposal = get_betting_odds(query)
        return jsonify({'response': response, 'betting': betting_proposal})
    popular_bets = get_betting_odds()
    return render_template('index.html', popular_bets=popular_bets)

if __name__ == '__main__':
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)

# chat URL https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44