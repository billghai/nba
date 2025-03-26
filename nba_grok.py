from flask import Flask, request, render_template, jsonify
import requests
import os
from dotenv import load_dotenv
import json
from datetime import datetime

env_path = os.path.join(os.path.dirname(__file__), '.env')
print("Looking for .env at:", env_path)
load_dotenv(env_path)
API_KEY = os.getenv("XAI_API_KEY")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
print("Loaded ODDS_API_KEY:", ODDS_API_KEY)
API_URL = "https://api.x.ai/v1/chat/completions"
ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"

app = Flask(__name__)

TEAM_NAME_MAP = {
    "lakers": "Los Angeles Lakers",
    "jazz": "Utah Jazz",
    "celtics": "Boston Celtics",
    "warriors": "Golden State Warriors",
    "nuggets": "Denver Nuggets",
    "bulls": "Chicago Bulls",
    "kings": "Sacramento Kings",
    "bucks": "Milwaukee Bucks",
    "suns": "Phoenix Suns",
    "raptors": "Toronto Raptors",
    "magic": "Orlando Magic",
    "grizzlies": "Memphis Grizzlies",
    "knicks": "New York Knicks",
    "heat": "Miami Heat", "heats": "Miami Heat",
    "clippers": "Los Angeles Clippers",
    "cavaliers": "Cleveland Cavaliers",
    "mavericks": "Dallas Mavericks",
    "rockets": "Houston Rockets",
    "pacers": "Indiana Pacers",
    "nets": "Brooklyn Nets",
    "hawks": "Atlanta Hawks",
    "sixers": "Philadelphia 76ers", "76ers": "Philadelphia 76ers",
    "spurs": "San Antonio Spurs",
    "thunder": "Oklahoma City Thunder",
    "timberwolves": "Minnesota Timberwolves",
    "blazers": "Portland Trail Blazers", "trail blazers": "Portland Trail Blazers",
    "pistons": "Detroit Pistons",
    "hornets": "Charlotte Hornets",
    "wizards": "Washington Wizards",
    "pelicans": "New Orleans Pelicans"
}

SCHEDULE_PATH = os.path.join(os.path.dirname(__file__), 'nba_schedule.json')
with open(SCHEDULE_PATH, 'r') as f:
    NBA_SCHEDULE = json.load(f)

def validate_game(date, team1, team2, score=None):
    games = NBA_SCHEDULE.get(date, [])
    for game in games:
        teams = {game["home"].lower(), game["away"].lower()}
        if team1.lower() in teams and team2.lower() in teams:
            if score and score == game.get("score"):
                return True
            elif not score:
                return True
    return False

def get_last_game(team):
    today = datetime.now().strftime('%Y-%m-%d')
    for date in sorted(NBA_SCHEDULE.keys(), reverse=True):
        if date <= today:
            for game in NBA_SCHEDULE[date]:
                if team.lower() in [game["home"].lower(), game["away"].lower()]:
                    return date, game["home"], game["away"], game.get("score")
    return None, None, None, None

def get_next_game(team):
    today = datetime.now().strftime('%Y-%m-%d')
    for date in sorted(NBA_SCHEDULE.keys()):
        if date >= today:
            for game in NBA_SCHEDULE[date]:
                if team.lower() in [game["home"].lower(), game["away"].lower()]:
                    return date, game["home"], game["away"]
    return None, None, None

def query_grok(prompt):
    current_date = datetime.now().strftime('%Y-%m-%d')
    query_lower = prompt.lower().replace("'", "").replace("’", "")  # Strip apostrophes
    for word in ["last", "game", "research", "the", "what", "was", "score", "in"]:
        query_lower = query_lower.replace(word, "").strip()
    for team in TEAM_NAME_MAP:
        if team in query_lower:
            team_name = TEAM_NAME_MAP[team]
            break
    else:
        return "Sorry, couldn’t identify the team—try again!"

    date, home, away, score = get_last_game(team_name)
    if not date:
        return f"No recent game found for {team_name} in the schedule."

    validated_prompt = f"On {date}, {home} played {away} with a score of {score or 'upcoming'}. Provide top scorer and highest assists for {team_name}."
    
    payload = {
        "model": "grok-2-1212",
        "messages": [
            {"role": "system", "content": (
                f"Today's date is {current_date}. Use the provided game data to provide the top scorer "
                "and highest assists for the requested team in a conversational tone. Do not search externally."
            )},
            {"role": "user", "content": validated_prompt}
        ],
        "max_tokens": 500,
        "temperature": 0.7
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return f"The last game {team_name} played was on {date} against {away if team_name.lower() == home.lower() else home}. The final score was {score or 'still to come'}. {response.json()['choices'][0]['message']['content']}"
    except Exception as e:
        return f"Oops! Something went wrong with the API: {str(e)}"

def get_betting_odds(query=None):
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "h2h",
        "oddsFormat": "decimal",
        "daysFrom": 3
    }
    try:
        response = requests.get(ODDS_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        print("Odds API response length:", len(data))
        print("Raw API games:", [f"{g['home_team']} vs {g['away_team']} ({g['commence_time']})" for g in data])
        validated_data = [game for game in data if validate_game(game["commence_time"].split("T")[0], game["home_team"], game["away_team"])]
        validated_data.sort(key=lambda x: x["commence_time"])
        top_games = validated_data[:5]
        bets = []
        remaining_bets = []

        betting_output = ""

        if query:
            query_lower = query.lower().replace("'", "").replace("’", "")  # Strip apostrophes
            for word in ["last", "next", "game", "research", "the", "what", "was", "score", "in", "hte", "ths"]:
                query_lower = query_lower.replace(word, "").strip()
            for team in TEAM_NAME_MAP:
                if team in query_lower:
                    team_name = team
                    break
                else:
                    team_name = query_lower
                full_team_name = TEAM_NAME_MAP.get(team_name, team_name)
                print("Looking for team:", team_name, "Mapped to:", full_team_name)

            date, home, away = get_next_game(full_team_name)
            if date:
                for game in top_games:
                    home_team = game["home_team"].lower().strip()
                    away_team = game["away_team"].lower().strip()
                    if full_team_name.lower() in [home_team, away_team]:
                        if game.get("bookmakers") and game["bookmakers"][0].get("markets"):
                            bookmakers = game["bookmakers"][0]["markets"][0]["outcomes"]
                            bets.append(f"Next game: Bet on {game['home_team']} vs {game['away_team']}: {bookmakers[0]['name']} to win @ {bookmakers[0]['price']}")
                            print("Found match:", bets[-1], "Time:", game["commence_time"])
                    else:
                        if game.get("bookmakers") and game["bookmakers"][0].get("markets"):
                            bookmakers = game["bookmakers"][0]["market"]

 

# Chat log:https://grok.com/chat/0ccaf3fa-ebee-46fb-a06c-796fe7bede44