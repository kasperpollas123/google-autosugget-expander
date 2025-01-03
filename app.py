import streamlit as st
import requests
import string
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from requests.exceptions import ProxyError
import google.generativeai as genai
from google.api_core import retry
import random

# List of Oxylabs proxy endpoints
PROXY_ENDPOINTS = [
    {
        "user": "customer-kasperpollas12345_Lyt6m-cc-us",
        "password": "Snaksnak12345+",
        "host": "pr.oxylabs.io",
        "port": "7777",
    },
    {
        "user": "kasperpollas_EImZC-cc-us",
        "password": "L6mFKak8Uz286dC+",
        "host": "pr.oxylabs.io",
        "port": "7777",
    },
]

# Function to get a random proxy endpoint
def get_random_proxy():
    proxy = random.choice(PROXY_ENDPOINTS)
    proxy_url = f"http://{proxy['user']}:{proxy['password']}@{proxy['host']}:{proxy['port']}"
    print(f"Using proxy: {proxy_url}")  # Log the proxy being used
    return proxy_url

# Google Gemini API key
GEMINI_API_KEY = "AIzaSyAlxm5iSAsNVLbLvIVAAlxFkIBjkjE0E1Y"
genai.configure(api_key=GEMINI_API_KEY)

# Initialize Gemini model (Updated to use Gemini 1.5 Flash)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# Function to fetch Google autosuggest keywords with retries
def get_autosuggest(query, max_retries=3):
    url = "https://www.google.com/complete/search"
    params = {
        "q": query,
        "client": "chrome",
    }
    for attempt in range(max_retries):
        try:
            # Use a random proxy for each request
            proxies = {
                "http": get_random_proxy(),
                "https": get_random_proxy(),
            }
            response = requests.get(url, params=params, proxies=proxies, timeout=30)
            response.raise_for_status()
            return response.json()[1]
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                st.warning(f"Attempt {attempt + 1} failed for '{query}': {e}. Retrying...")
                time.sleep(1)  # Wait before retrying
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
            # Use a random proxy for each request
            proxies = {
                "http": get_random_proxy(),
                "https": get_random_proxy(),
            }
            session = requests.Session()
            session.cookies.clear()
            response = session.get(url, proxies=proxies, timeout=30)
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

# Function to analyze keywords with Gemini
def analyze_keywords_with_gemini(keywords, serp_results):
    # System instructions and chat input (same content)
    prompt = """
    Please analyse the intent for all of the keywords on this list based on the SERP page results for each keyword. Then come up with different themes that keywords can be grouped under. You may use the same keyword more than once in different themes but only once in each theme. The themes should have a catchy and inspiring headline and underneath the headline should simply be the keywords that are grouped together. For each group please remove and omit keywords that are too similar to other keywords and basically mean the same thing and reflect the same intent like for example 'my cat peeing everywhere' and 'cat is peeing everywhere'. You are not allowed to make up keywords that are not on the list i give you. Please limit each group to a maximum of 20 keywords. If there are any keywords that stick out as weird for example asking for the keyword in a specific language or if they just stick out to much compared to the overall intent of most of the keywords, then please remove them.

    The final output should look EXACTLY like this:

    Finding Local Plumbing Professionals
    - r plumbing company
    - j plumbing chicago
    - z plumbers livonia
    - r plumber llc
    - r plumbing
    - j.p. plumbing
    - z plumbing and heating
    - r plumbing llc reviews

    Generating Plumbing Leads
    - plumbing lead generation agency fatrank
    - plumber lead generation
    - how to get plumbing leads
    - plumbing lead generation james dooley
    - plumbing lead generation services
    - plumbing leads near me
    - plumbing leads for plumbers
    - plumbing lead generation services fatrank
    - plumbing lead generation company james dooley
    - plumbing lead generation

    Understanding Lead Pipes in Plumbing
    - lead plumbing pipe
    - plumbing lead
    - plumbing lead joint
    - lead plumbing
    - plumbing lead pipes
    - lead plumbing history
    - led plumbing
    - is lead still used in plumbing
    - how much to replace lead plumbing
    - who is responsible for replacing lead water pipes

    Plumbing Tools and Equipment
    - plumbing lead tools
    - plumbing lead melting pot

    Plumbing Job Information
    - lead plumber salary
    - lead plumber job description

    Do not include any explanations, notes, or additional text. Only provide the grouped keywords in the specified format. The format must be EXACTLY as shown above, with no deviations.
    """

    # Prepare the chat input for Gemini
    chat_input = "Here is the list of keywords and their SERP results:\n"
    for keyword, results in serp_results.items():
        if isinstance(results, list):  # Only process valid SERP results
            chat_input += f"Keyword: {keyword}\n"
            for i, result in enumerate(results, start=1):
                if isinstance(result, dict) and "title" in result and "description" in result:  # Ensure result is valid
                    chat_input += f"  Result {i}:\n"
                    chat_input += f"    Title: {result['title']}\n"
                    chat_input += f"    Description: {result['description']}\n"
            chat_input += "\n"

    # Configure Gemini generation settings
    generation_config = {
        "temperature": 1,  # Higher temperature for more creative outputs
        "max_output_tokens": 10000,  # Increase output token limit to 10,000
    }

    # Retry logic for API calls
    @retry.Retry()
    def call_gemini():
        return gemini_model.generate_content(
            contents=[prompt, prompt + "\n" + chat_input],  # Pass prompt in both places
            generation_config=generation_config,
        )

    try:
        response = call_gemini()
        return response.text
    except Exception as e:
        st.error(f"Error calling Gemini API: {e}")
        return None

# Streamlit UI
st.title("Google Autosuggest Keyword Fetcher with SERP Results and Gemini Analysis")

# Initialize session state to store keywords and SERP results
if "all_keywords" not in st.session_state:
    st.session_state.all_keywords = set()
if "serp_results" not in st.session_state:
    st.session_state.serp_results = {}
if "gemini_output" not in st.session_state:
    st.session_state.gemini_output = None

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

        # Analyze keywords with Gemini
        if st.session_state.serp_results:
            with st.spinner("Analyzing keywords with Gemini..."):
                st.session_state.gemini_output = analyze_keywords_with_gemini(st.session_state.all_keywords, st.session_state.serp_results)

        # Display Gemini output
        if st.session_state.gemini_output:
            st.subheader("Keyword Themes and Groups")
            st.markdown(st.session_state.gemini_output)
    else:
        st.write("No keywords found.")
else:
    st.session_state.all_keywords = set()
    st.session_state.serp_results = {}
    st.session_state.gemini_output = None
