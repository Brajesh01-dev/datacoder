import time
from bs4 import BeautifulSoup
import os
from datetime import datetime, timedelta
from supabase import create_client, Client
import requests

# --- CONFIG ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BLOGGER_API_KEY = os.getenv("BLOGGER_API_KEY")
BLOGGER_BLOG_ID = os.getenv("BLOGGER_BLOG_ID")

# --- Get Blogger Access Token from Refresh Token ---
def get_access_token_from_refresh():
    import requests
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = os.getenv("BLOGGER_REFRESH_TOKEN")
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    r = requests.post(token_url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]

def get_next_html_from_supabase():
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    today = datetime.now().date()
    res = supabase.table("autoblogger") \
        .select("*") \
        .eq("upload_date", str(today)) \
        .execute()
    if res.data and len(res.data) > 0:
        return res.data[0]
    return None

def extract_title_from_body(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    body = soup.body
    if body:
        # Try h1, then h2, then h3, then first <p>
        for tag in ["h1", "h2", "h3", "p"]:
            found = body.find(tag)
            if found and found.get_text(strip=True):
                return found.get_text(strip=True)
    # fallback: try document title
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return "Blog Post"

def post_to_blogger(title, html_content):
    url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/"
    access_token = get_access_token_from_refresh()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    data = {
        "kind": "blogger#post",
        "title": title,
        "content": html_content
    }
    response = requests.post(url, headers=headers, params={"key": BLOGGER_API_KEY}, json=data)
    if response.status_code == 200:
        print("✅ Posted to Blogger")
        return True
    else:
        print("❌ Blogger post failed:", response.text)
        return False

def mark_as_posted(supabase_id):
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    supabase.table("autoblogger").update({"is_posted": True}).eq("id", supabase_id).execute()

def main():
    print("Starting hourly poster. Press Ctrl+C to stop.")
    while True:
        print(f"\n[INFO] Checking for today's post at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        row = get_next_html_from_supabase()
        if not row:
            print("No content to post today.")
        elif not row.get("is_posted"):
            print("Attempting to post today's content...")
            html_content = row["html_content"]
            title = extract_title_from_body(html_content)
            soup = BeautifulSoup(html_content, "html.parser")
            body = soup.body
            if body:
                post_content = body.decode_contents()
            else:
                post_content = html_content
            if post_to_blogger(title, post_content):
                mark_as_posted(row["id"])
        else:
            print("Already posted today. Skipping.")
        # Sleep for 1 hour (3600 seconds)
        time.sleep(3600)

if __name__ == "__main__":
    main()
