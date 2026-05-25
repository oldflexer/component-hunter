import random
import time

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
    # добавить ещё
]

def random_ua():
    return random.choice(USER_AGENTS)

def random_sleep(min_sec=0.5, max_sec=2.0):
    time.sleep(random.uniform(min_sec, max_sec))