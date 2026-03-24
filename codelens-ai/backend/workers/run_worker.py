import os
import sys

# Ensure the project root is on the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from redis import Redis
from rq import Worker, Queue

from backend.config import REDIS_URL

redis_conn = Redis.from_url(REDIS_URL)
queues = [Queue("codelens", connection=redis_conn)]

if __name__ == "__main__":
    worker = Worker(queues, connection=redis_conn)
    worker.work()
