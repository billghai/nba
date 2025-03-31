# cron_update.py
import os
import sys
sys.path.append(os.path.dirname(__file__))
from nba_grok import update_schedule_cache

if __name__ == "__main__":
    update_schedule_cache()