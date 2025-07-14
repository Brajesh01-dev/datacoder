
import fitz  # PyMuPDF
import re
import google.generativeai as genai
import os
import json

from datetime import datetime, timedelta
from supabase import create_client, Client
# --- Get next upload_date from Supabase ---

def get_next_upload_date(supabase_url=None, supabase_key=None):
    if supabase_url is None:
        supabase_url = SUPABASE_URL
    if supabase_key is None:
        supabase_key = SUPABASE_KEY
    if not (supabase_url and supabase_key):
        print("❌ Supabase credentials not set for date lookup.")
        return datetime.now().date() + timedelta(days=1)
    supabase: Client = create_client(supabase_url, supabase_key)
    try:
        # Get the latest upload_date
        res = supabase.table("autoblogger").select("upload_date").order("upload_date", desc=True).limit(1).execute()
        if res.data and len(res.data) > 0 and res.data[0]["upload_date"]:
            last_date = res.data[0]["upload_date"]
            # Parse date string (YYYY-MM-DD)
            last_date_obj = datetime.strptime(last_date, "%Y-%m-%d").date()
            return last_date_obj + timedelta(days=1)
        else:
            return datetime.now().date() + timedelta(days=1)
    except Exception as e:
        print(f"❌ Could not fetch last upload_date: {e}")
        return datetime.now().date() + timedelta(days=1)
# --- Supabase ---

# CONFIGURATION
PDF_PATH = r"C:/Users/braje/Downloads/M2-Machine_Learning_By_Ethem_Alpaydin.pdf"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
INDEX_PAGE_END = 30  # only first 30 pages checked for TOC

# Supabase config (set your environment variables or hardcode for testing)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# --- Send data to Supabase ---
def send_to_supabase(pdf_name, html_content, upload_date, supabase_url=SUPABASE_URL, supabase_key=SUPABASE_KEY):
    if not (supabase_url and supabase_key):
        print("❌ Supabase credentials not set.")
        return None
    supabase: Client = create_client(supabase_url, supabase_key)
    data = {
        "pdf_name": pdf_name,
        "upload_date": str(upload_date),
        "html_content": html_content
    }
    try:
        response = supabase.table("autoblogger").insert(data).execute()
        print(f"✅ Uploaded to Supabase: {pdf_name} ({upload_date})")
        return response
    except Exception as e:
        print(f"❌ Supabase upload failed: {e}")
        return None
# --- Gemini Init ---
def init_gemini(api_key):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.0-flash")

# --- Extract index pages (first 30) ---
def extract_index_pages(pdf_path, end_page):
    doc = fitz.open(pdf_path)
    return [doc[i].get_text() for i in range(end_page)]

# --- Use Gemini to parse TOC ---
def get_toc_from_gemini(model, index_text):
    prompt = f"""
    You are reading the index or table of contents from a book. Based on the following raw text, extract a dictionary where each key is a topic or chapter title, and the value is a list with [start_page, end_page].

    Example format:
    {{
      "Chapter 1: Introduction": [5, 10],
      "Chapter 2: Deep Learning": [11, 20]
    }}

    Only include items that are real topics with valid page numbers output should json valid format.

    Index text:
    {index_text}
    """

    response = model.generate_content(prompt)
    try:
        clean_json = response.text.strip('` \n')
        if clean_json.startswith('json'):
            clean_json = clean_json[len('json'):].strip()

        # Step 2: Parse JSON
        data = json.loads(clean_json)
        updated_data = {k: [v[0] + 40, v[1] + 40] for k, v in data.items()}
    except json.JSONDecodeError:
        print("⚠️ Could not parse Gemini response as JSON.")
        print(response.text)
        return {}

    return updated_data

# --- Extract topic content ---
def extract_topic_content(pdf_path, topic_dict):
    doc = fitz.open(pdf_path)
    topic_contents = {}
    for title, (start, end) in topic_dict.items():
        pages = [doc[i].get_text() for i in range(start - 1, min(end, len(doc)))]
        topic_contents[title] = "\n".join(pages)
    return topic_contents

# --- Generate blog HTML ---
def generate_blog_html(model, title, content):
    prompt = f"""
    Write an engaging blog article titled "{title}" based on the following book content. 
    Don't mention that you get the content from the book but take the information and make it informative and easy to read. 
    cover all the subjects in the content. all subtopics should be covered in the blog.
    Use a friendly tone and include relevant examples or explanations where necessary.
    Use headings and subheadings to structure the content. 
    Avoid using any code or programming language references.

    Format your response in clean HTML using <h2>, <p>, and <ul>/<li> where needed.

    Content:
    {content}
    """
    response = model.generate_content(prompt)
    return response.text

# --- Save HTML file ---
def save_blog_html(title, html):
    safe_title = re.sub(r"[^\w\-]+", "_", title.strip())[:60]
    filename = f"blog_{safe_title}.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Saved: {filename}")

# --- MAIN ---
def main():
    print("[1] Extracting first 30 pages...")
    index_pages = extract_index_pages(PDF_PATH, INDEX_PAGE_END)
    index_text = "\n".join(index_pages)

    print("[2] Initializing Gemini and extracting index...")
    gemini_model = init_gemini(GEMINI_API_KEY)
    toc_dict = get_toc_from_gemini(gemini_model, index_text)

    if not toc_dict:
        print("❌ Failed to extract TOC. Exiting.")
        return

    for title, (start, end) in toc_dict.items():
        print(f" - {title}: pages {start}–{end}")

    print("[3] Extracting content for each topic...")
    topic_contents = extract_topic_content(PDF_PATH, toc_dict)

    print("[4] Generating blog articles...")
    # Start upload_date from the day after the last date in the table (or tomorrow if none)
    base_date = get_next_upload_date()
    pdf_name = os.path.basename(PDF_PATH)
    for i, (title, content) in enumerate(topic_contents.items()):
        print(f" - Generating blog: {title}")
        html = generate_blog_html(gemini_model, title, content)

        # Save locally
        # save_blog_html(title, html)

        # Clean HTML for Supabase upload
        cleaned_html = html.strip()
        if cleaned_html.startswith('```html'):
            cleaned_html = cleaned_html[len('```html'):].lstrip('\n')
        if cleaned_html.endswith('</html>```'):
            cleaned_html = cleaned_html[:-len('</html>```')].rstrip('\n')
        elif cleaned_html.endswith('```'):
            cleaned_html = cleaned_html[:-3].rstrip('\n')

        # Upload to Supabase with incremented date
        upload_date = base_date + timedelta(days=i)
        send_to_supabase(pdf_name, cleaned_html, upload_date)

    print("\n🎉 All done!")

if __name__ == "__main__":
    main()