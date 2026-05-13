"""Minimal AI Studio smoke test — no Vertex, no billing."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.config import make_client

print("Creating client...")
client = make_client()

print("Calling gemini-2.5-flash (free tier)...")
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Say 'hello from AI Studio free tier' in Telugu, one short sentence only."
)

print("\nResponse:")
print(response.text)
print("\n[OK] AI Studio free tier is working.")