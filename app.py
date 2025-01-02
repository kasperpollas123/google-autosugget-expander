import streamlit as st
import requests
import string
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from requests.exceptions import ProxyError

# Oxylabs proxy endpoint
PROXY_USER = "customer-kasperpollas12345_Lyt6m-cc-us"
PROXY_PASS = "Snaksnak12345+"
PROXY_HOST = "pr.oxylabs.io"
PROXY_PORT = "7777"
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

# Function to fetch Google autosuggest keywords with retries
def get_autosuggest(query, max_retries=3):
    url = "https://www.google.com/complete/search"
    params = {
        "q": query,
        "client": "chrome",
    }
    proxies = {
        "http": PROXY_URL,
        "https": PROXY_URL,
    }
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, proxies=proxies)
            response.raise_for_status()
            return response.json()[1]
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                st.error(f"Error fetching autosuggest keywords for '{query}': {e}")
    return []

# Function to generate expanded keyword variations
def generate_expanded_keywords(seed_keyword):
    expanded_keywords = []
    for letter in string.ascii_lowercase:
        expanded_keywords.append(f"{seed_keyword} {letter}")
        expanded_keywords.append(f"{letter} {seed_keyword}")
    return expanded_keywords

# Function to fetch keywords concurrently using multi-threading
def fetch_keywords_concurrently(queries):
    all_keywords = set()
    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = {executor.submit(get_autosuggest, query): query for query in queries}
        for i, future in enumerate(as_completed(futures), start=1):
            try:
                keywords = future.result()
                if keywords:
                    all_keywords.update(keywords)
                progress_value = i / len(queries)
                progress_bar.progress(min(progress_value, 1.0))
                status_text.text(f"Progress: {i}/{len(queries)} variations completed")
            except Exception as e:
                st.error(f"Error fetching keywords: {e}")
    return all_keywords

# Function to fetch and parse Google SERP
def fetch_google_serp(query, limit=5, retries=3):
    url = f"https://www.google.com/search?q={query}"
    for attempt in range(retries):
        try:
            proxies = {
                "http": PROXY_URL,
                "https": PROXY_URL,
            }
            session = requests.Session()
            session.cookies.clear()
            response = session.get(url, proxies=proxies)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                results = []
                for result in soup.find_all('div', class_='Gx5Zad xpd EtOod pkphOe')[:limit]:
                    if "ads" in result.get("class", []):
                        continue
                    title_element = result.find('h3') or result.find('h2') or result.find('div', class_='BNeawe vvjwJb AP7Wnd')
                    title = title_element.get_text().strip() if title_element else "No Title Found"
                    description_element = result.find('div', class_='BNeawe s3v9rd AP7Wnd') or \
                                         result.find('div', class_='v9i61e') or \
                                         result.find('div', class_='BNeawe UPmit AP7Wnd lRVwie') or \
                                         result.find('div', class_='BNeawe s3v9rd AP7Wnd')
                    description = description_element.get_text().strip() if description_element else "No Description Found"
                    results.append({
                        "title": title,
                        "description": description
                    })
                return results
            elif response.status_code == 429:
                if attempt < retries - 1:
                    time.sleep(10)
                    continue
                else:
                    return f"Error: Rate limit exceeded for '{query}'."
            else:
                return f"Error: Unable to fetch SERP for '{query}'. Status code: {response.status_code}"
        except ProxyError as e:
            if attempt < retries - 1:
                time.sleep(5)
                continue
            else:
                return f"Proxy error occurred for '{query}': {e}"
        except Exception as e:
            return f"An error occurred for '{query}': {e}"
    return f"Error: Max retries reached for '{query}'."

# Function to fetch SERP results concurrently
def fetch_serp_results_concurrently(keywords):
    serp_results = {}
    with ThreadPoolExecutor(max_workers=20) as executor:  # Adjust max_workers as needed
        futures = {executor.submit(fetch_google_serp, keyword): keyword for keyword in keywords}
        for i, future in enumerate(as_completed(futures), start=1):
            keyword = futures[future]
            try:
                result = future.result()
                serp_results[keyword] = result
                progress_value = i / len(keywords)
                serp_progress_bar.progress(min(progress_value, 1.0))
                serp_status_text.text(f"SERP Progress: {i}/{len(keywords)} keywords completed")
            except Exception as e:
                st.error(f"Error fetching SERP results for '{keyword}': {e}")
    return serp_results

# Streamlit UI
st.title("Google Autosuggest Keyword Fetcher with SERP Results")

# Initialize session state to store keywords and SERP results
if "all_keywords" not in st.session_state:
    st.session_state.all_keywords = set()
if "serp_results" not in st.session_state:
    st.session_state.serp_results = {}

query = st.text_input("Enter a seed keyword:")

if query:
    # Initialize variables
    total_variations = 52  # 26 letters * 2 (beginning and end)
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Fetch initial autosuggest keywords
    with st.spinner("Fetching initial autosuggest keywords..."):
        initial_keywords = get_autosuggest(query)
        if initial_keywords:
            st.session_state.all_keywords.update(initial_keywords)
        progress_value = 1 / total_variations
        progress_bar.progress(min(progress_value, 1.0))
        status_text.text(f"Progress: 1/{total_variations} variations completed")

    # Generate expanded keyword variations
    expanded_keywords = generate_expanded_keywords(query)

    # Fetch autosuggest keywords concurrently
    with st.spinner("Fetching autosuggest keywords concurrently..."):
        st.session_state.all_keywords.update(fetch_keywords_concurrently(expanded_keywords))

    # Fetch SERP results for each keyword concurrently
    if st.session_state.all_keywords:
        st.success("Keyword fetching completed!")
        st.write(f"Total keywords fetched: {len(st.session_state.all_keywords)}")

        # Initialize SERP progress bar and status text
        serp_progress_bar = st.progress(0)
        serp_status_text = st.empty()

        with st.spinner("Fetching SERP results for each keyword concurrently..."):
            st.session_state.serp_results = fetch_serp_results_concurrently(st.session_state.all_keywords)

        # Display SERP results for each keyword
        st.subheader("SERP Results for Each Keyword")
        for keyword, results in st.session_state.serp_results.items():
            if isinstance(results, list):
                st.markdown(f"**Keyword:** {keyword}")
                for i, result in enumerate(results, start=1):
                    st.markdown(f"**Result {i}**")
                    st.markdown(f"**Title:** {result['title']}")
                    st.markdown(f"**Description:** {result['description']}")
                    st.markdown("---")
            else:
                st.error(f"Error for keyword '{keyword}': {results}")
    else:
        st.write("No keywords found.")
else:
    st.session_state.all_keywords = set()
    st.session_state.serp_results = {}
