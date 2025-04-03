import logging
from nba_grok import update_odds

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.debug("Starting Cron update...")
    update_odds()
    logging.debug("Cron update complete.")