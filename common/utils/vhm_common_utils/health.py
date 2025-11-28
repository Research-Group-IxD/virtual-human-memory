from fastapi import FastAPI
from uvicorn import Config, Server
import threading

app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "ok"}

def run_health_check_server():
    """Runs the health check server in a separate thread."""
    config = Config(app=app, host="0.0.0.0", port=8080, log_level="info")
    server = Server(config)
    
    # Run the server in a daemon thread so it exits when the main thread exits
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
