# nba_render/prompt.py
from datetime import datetime, timedelta, timezone

def generate_prompt(q, team, teams_mentioned):
    """
    Generate a Grok.com-style prompt response for NBA queries.
    Args:
        q (str): Pre-processed query (e.g., "how did the heat do in their last game")
        team (str): Detected team (e.g., "Miami Heat")
        teams_mentioned (list): All teams in query (e.g., ["Miami Heat"])
    Returns:
        str: Response, max 150 chars, with 2-3 follow-ups
    """
    today = datetime.now(timezone.utc) - timedelta(hours=7)
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    # Base response—witty, generic, adaptable
    response = "No dice—toss me an NBA query, I’ll zap it fast!\nNext: Stats? Odds? Form?"
    if team:
        # Your custom prompt—edit this as you like
        action = "battled last" if "last" in q else "play next" if "next" in q or "research" in q else "are off"
        date = yesterday.strftime('%b %-d') if "last" in q else tomorrow.strftime('%b %-d') if "next" in q or "research" in q else "today"
        response = f"My NBA scoop on {team}: {action} {date}—stars shone. Your take?\nNext: Stats? Odds? Form?"
        # Example alternative: response = f"Yo, {team} fan! They {action} {date}—wild, huh? Your call?\nNext: Stats? Odds? Form?"

    return response