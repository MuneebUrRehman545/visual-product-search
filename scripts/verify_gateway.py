import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from app.db.shared_database import get_shared_connection

try:
    with get_shared_connection() as conn:
        with conn.cursor() as cur:
            # Check if run exists, if not, create it
            run_id = 'e28c6a52-a250-41f1-903c-ec43fb0903d3'
            cur.execute("SELECT 1 FROM pipeline_runs WHERE id = %s", (run_id,))
            exists = bool(cur.fetchone())
            print(f'Exists: {exists}')
            
            if not exists:
                print("Creating the run...")
                cur.execute("INSERT INTO pipeline_runs (id, status) VALUES (%s, %s)", (run_id, 'pending'))
                print("Created.")
except Exception as e:
    print(f"Error: {e}")
