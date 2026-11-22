import os

# Use a throwaway SQLite file for tests, never the real Postgres
os.environ["DATABASE_URL"] = "sqlite:////tmp/agora_test.db"
if os.path.exists("/tmp/agora_test.db"):
    os.remove("/tmp/agora_test.db")