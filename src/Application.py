import requests
from bs4 import BeautifulSoup
import urllib3
from urllib.parse import urljoin
import datetime
import os
import re
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Path Configuration ---
# Get the directory of the current script (e.g., /path/to/project/src)
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
# Get the parent directory (the project root, e.g., /path/to/project)
PROJECT_ROOT = os.path.dirname(SRC_DIR)

# Define output directory at the project root level
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
DATA_FILE = os.path.join(OUTPUT_DIR, "menu_data.json")
HTML_FILE = os.path.join(OUTPUT_DIR, "weekly_menu.html")

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_data():
    """Loads existing menu data from JSON file."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_data(data):
    """Saves menu data to JSON file."""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_menu_data(url):
    """
    Fetches menu items and delivery date from the given URL.
    Returns: (delivery_date_string, menu_items_list)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.google.com/',
        'Upgrade-Insecure-Requests': '1',
        'Connection': 'keep-alive'
    }

    session = requests.Session()
    session.headers.update(headers)

    # --- Add Retry Logic for robustness in CI environments ---
    retry_strategy = Retry(
        total=3,  # Total number of retries
        backoff_factor=1,  # Wait 1s, 2s, 4s between retries
        status_forcelist=[429, 500, 502, 503, 504], # Retry on these server errors
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    # --- End Retry Logic ---

    try:
        # Increase timeout from 15 to 30 seconds
        response = session.get(url, verify=False, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. Extract Delivery Date
        # Look for pattern "XX월 XX일에 배송"
        page_text = soup.get_text()
        date_match = re.search(r'(\d{1,2})\s*월\s*(\d{1,2})\s*일.*배송', page_text)

        if date_match:
            delivery_date = f"{date_match.group(1)}월 {date_match.group(2)}일"
        else:
            # Fallback if not found
            today = datetime.date.today()
            delivery_date = f"{today.month}월 {today.day}일 (날짜 미확인)"
            print(f"Warning: Could not find delivery date pattern. Using {delivery_date}")

        # 2. Extract Menu Items
        menu_items = []
        posts = soup.find_all(class_='elementor-post')

        if not posts:
            # Fallback search logic
            text_containers = soup.find_all(class_='elementor-post__text')
            for text_div in text_containers:
                container = text_div.find_parent(class_='elementor-post')
                if container and container not in posts:
                    posts.append(container)

        for post in posts:
            # Extract Name
            name_div = post.find(class_='elementor-post__text')
            if not name_div: continue
            name_link = name_div.find('a')
            if not name_link: continue
            name = name_link.get_text(strip=True)

            # Extract Image
            img_tag = post.find('img')
            if not img_tag: continue

            if 'src' in img_tag.attrs:
                img_url = urljoin(url, img_tag['src'])
            elif 'data-src' in img_tag.attrs:
                img_url = urljoin(url, img_tag['data-src'])
            else:
                continue

            menu_items.append({
                'name': name,
                'image_url': img_url
            })

        return delivery_date, menu_items

    except requests.exceptions.RequestException as e:
        print(f"Error fetching the URL: {e}")
        return None, []


def generate_html_report(all_data):
    """
    Generates an HTML file with a combo box to select dates.
    all_data: Dictionary { "10월 25일": [items...], "11월 1일": [items...] }
    """

    def parse_korean_date(date_str):
        # Extract numbers from "MM월 DD일"
        match = re.search(r'(\d+)\s*월\s*(\d+)\s*일', date_str)
        if match:
            return int(match.group(1)), int(match.group(2))
        return (0, 0)

    # Sort dates chronologically: Newest first
    sorted_dates = sorted(all_data.keys(), key=parse_korean_date, reverse=True)

    if not sorted_dates:
        print("No data to generate report.")
        return

    latest_date = sorted_dates[0]
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Weekly Menu History</title>
        <style>
            body {{ font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; background-color: #f4f4f9; padding: 20px; margin: 0; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            
            h1 {{ 
                text-align: center; 
                color: #333; 
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 15px;
                flex-wrap: wrap; /* 화면이 좁으면 줄바꿈 */
            }}
            
            .home-button {{
                display: inline-block;
                padding: 8px 16px;
                font-size: 16px;
                color: white;
                background-color: #607d8b; /* 밝은 Blue Grey */
                text-decoration: none;
                border-radius: 8px; /* 적당한 라운드 */
                transition: all 0.3s ease;
                box-shadow: 0 2px 5px rgba(0,0,0,0.15);
            }}
            .home-button:hover {{
                background-color: #78909c;
                transform: translateY(-2px);
                box-shadow: 0 4px 8px rgba(0,0,0,0.2);
            }}

            .controls {{ text-align: center; margin-bottom: 30px; }}
            select {{ padding: 10px 20px; font-size: 16px; border-radius: 5px; border: 1px solid #ddd; cursor: pointer; }}
            .menu-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 25px; }}
            .menu-card {{ background: white; border-radius: 15px; box-shadow: 0 10px 20px rgba(0,0,0,0.05); overflow: hidden; transition: transform 0.3s ease; }}
            .menu-card:hover {{ transform: translateY(-5px); box-shadow: 0 15px 30px rgba(0,0,0,0.1); }}
            .image-container {{ width: 100%; height: 250px; overflow: hidden; background-color: #eee; }}
            .menu-card img {{ width: 100%; height: 100%; object-fit: cover; transition: transform 0.5s; }}
            .menu-card:hover img {{ transform: scale(1.05); }}
            .menu-info {{ padding: 20px; text-align: center; }}
            .menu-name {{ font-weight: bold; color: #333; font-size: 1.1em; margin-bottom: 5px; }}
            .hidden {{ display: none; }}
        </style>
        <script>
            function showMenu(date) {{
                // Hide all menu grids
                const grids = document.querySelectorAll('.menu-grid');
                grids.forEach(grid => grid.classList.add('hidden'));

                // Show the selected one
                const selectedGrid = document.getElementById('grid-' + date);
                if (selectedGrid) {{
                    selectedGrid.classList.remove('hidden');
                }}
            }}
        </script>
    </head>
    <body>
        <div class="container">
            <h1>반찬 메뉴 아카이브 <a href="https://thechanonline.com/" target="_blank" class="home-button">The Chan</a></h1>

            <div class="controls">
                <label for="dateSelect">배송 날짜 선택: </label>
                <select id="dateSelect" onchange="showMenu(this.value)">
    """

    # Add options to select box
    for date in sorted_dates:
        selected = "selected" if date == latest_date else ""
        html_content += f'<option value="{date}" {selected}>{date}</option>\n'

    html_content += """
                </select>
            </div>
    """

    # Create a grid for each date
    for date in sorted_dates:
        items = all_data[date]
        # Only the latest date is visible initially
        visibility_class = "" if date == latest_date else "hidden"

        html_content += f'<div id="grid-{date}" class="menu-grid {visibility_class}">'

        for item in items:
            html_content += f"""
                <div class="menu-card">
                    <div class="image-container">
                        <img src="{item['image_url']}" alt="{item['name']}" loading="lazy">
                    </div>
                    <div class="menu-info">
                        <div class="menu-name">{item['name']}</div>
                    </div>
                </div>
            """
        html_content += '</div>'

    html_content += """
        </div>
    </body>
    </html>
    """

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Successfully generated report: {os.path.abspath(HTML_FILE)}")


if __name__ == "__main__":
    target_url = "https://thechanonline.com/"
    print(f"Fetching menu data from {target_url}...")

    # 1. Load existing data
    all_data = load_data()
    print(f"Loaded {len(all_data)} existing records.")

    # 2. Fetch new data
    delivery_date, menu_items = fetch_menu_data(target_url)

    if delivery_date and menu_items:
        print(f"Detected delivery date: {delivery_date}")

        # 3. Update data if new
        if delivery_date in all_data:
            print(f"Data for {delivery_date} already exists. Skipping update.")
            # We still regenerate HTML to ensure it's up to date with the file
        else:
            print(f"New data found for {delivery_date}. Updating records.")
            all_data[delivery_date] = menu_items
            save_data(all_data)

        # 4. Generate HTML
        generate_html_report(all_data)
    else:
        print("Failed to fetch new data.")
