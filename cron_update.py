import logging
from nba_grok import update_schedule, update_odds

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.debug("Starting Cron update...")
    update_schedule()  # Updates database with ESPN schedule
    update_odds()      # Updates database with Odds API data
    logging.debug("Cron update complete.")