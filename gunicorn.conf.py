import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8050')}"
workers = 1          # single worker to share the in-memory data cache
threads = 4          # multiple threads for concurrent requests
timeout = 120        # give ML inference enough time
keepalive = 5
preload_app = True   # load app once, share across threads
accesslog = "-"
errorlog = "-"
loglevel = "info"
