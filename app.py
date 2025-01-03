import streamlit as st
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from requests.exceptions import ProxyError
import google.generativeai as genai
from google.api_core import retry
import nltk
from nltk.corpus import wordnet
from difflib import SequenceMatcher
import os

# Download WordNet data (only needed once)
nltk.download('wordnet')

# Oxylabs proxy endpoint
PROXY_USER = os.getenv("PROXY_USER", "customer-kasperpollas12345_Lyt6m-cc-us")
PROXY_PASS = os.getenv("PROXY_PASS", "Snaksnak12345+")
PROXY_HOST = os.getenv("PROXY_HOST", "pr.oxylabs.io")
PROXY_PORT = os.getenv("PROXY_PORT", "7777")
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

# Google Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyAlxm5iSAsNVLbLvIVAAlxFkIBjkjE0E1Y")
genai.configure(api_key=GEMINI_API_KEY)

# Initialize Gemini model (Updated to use Gemini 1.5 Pro)
gemini_model = genai.GenerativeModel('gemini-1.5-pro')

# Function to fetch Google autosuggest keywords with retries (uses proxy)
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

# Function to fetch synonyms using WordNet
def get_synonyms(word):
    synonyms = set()
    for syn in wordnet.synsets(word):
        for lemma in syn.lemmas():
            synonyms.add(lemma.name())
    return list(synonyms)

# Function to calculate relevance score
def calculate_relevance(keyword, seed_keyword):
    seed_words = seed_keyword.lower().split()
    keyword_words = keyword.lower().split()
    return len(set(seed_words).intersection(keyword_words)) / len(seed_words)

# Function to check if two keywords are too similar
def is_similar(keyword1, keyword2, threshold=0.8):
    return SequenceMatcher(None, keyword1, keyword2).ratio() >= threshold

# Function to generate expanded keyword variations
def generate_expanded_keywords(seed_keyword, max_keywords=500):
    # Fetch Level 1 autosuggest keywords
    level1_keywords = get_autosuggest(seed_keyword)

    # Filter autosuggest keywords to include only those containing the seed keyword
    filtered_keywords = [kw for kw in level1_keywords if seed_keyword.lower() in kw.lower()]

    # Fetch synonyms for the seed keyword
    synonyms = get_synonyms(seed_keyword)
    relevant_synonyms = [syn for syn in synonyms if seed_keyword.lower() in syn.lower() or syn.lower() in seed_keyword.lower()]

    # Combine all keywords
    all_keywords = set()
    all_keywords.add(seed_keyword)
    all_keywords.update(filtered_keywords)
    all_keywords.update(relevant_synonyms)

    # Universal modifiers (smaller set for better relevance)
    universal_modifiers = [
        "how to", "why is", "what is", "where to",
        "buy", "hire", "find", "near me",
        "best", "affordable", "top",
        "emergency", "24/7",
        "near me", "local"
    ]

    # Apply universal modifiers to the seed keyword and filtered keywords
    for modifier in universal_modifiers:
        all_keywords.add(f"{modifier} {seed_keyword}")
        all_keywords.add(f"{seed_keyword} {modifier}")
        for keyword in filtered_keywords:
            all_keywords.add(f"{modifier} {keyword}")
            all_keywords.add(f"{keyword} {modifier}")

    # Filter out irrelevant keywords (must contain the seed keyword or its synonyms)
    filtered_keywords = set()
    for keyword in all_keywords:
        if seed_keyword.lower() in keyword.lower():
            filtered_keywords.add(keyword)
        else:
            for synonym in relevant_synonyms:
                if synonym.lower() in keyword.lower():
                    filtered_keywords.add(keyword)
                    break

    # Remove duplicate keywords
    unique_keywords = []
    for kw in filtered_keywords:
        if not any(is_similar(kw, existing_kw) for existing_kw in unique_keywords):
            unique_keywords.append(kw)

    # Limit the number of keywords
    return unique_keywords[:max_keywords]

# Updated Function to fetch and parse Google SERP (only first result, uses proxy)
def fetch_google_serp(query, retries=3):
    url = f"https://www.google.com/search?q={query}"
    proxies = {
        "http": PROXY_URL,
        "https": PROXY_URL,
    }
    for attempt in range(retries):
        try:
            session = requests.Session()
            session.cookies.clear()
            response = session.get(url, proxies=proxies)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                results = []
                for result in soup.find_all('div', class_='Gx5Zad xpd EtOod pkphOe'):
                    if "ads" in result.get("class", []):
                        continue
                    title_element = result.find('h3') or result.find('h2') or result.find('div', class_='BNeawe vvjwJb AP7Wnd')
                    title = title_element.get_text().strip() if title_element else None
                    description_element = result.find('div', class_='BNeawe s3v9rd AP7Wnd') or \
                                         result.find('div', class_='v9i61e') or \
                                         result.find('div', class_='BNeawe UPmit AP7Wnd lRVwie') or \
                                         result.find('div', class_='BNeawe s3v9rd AP7Wnd')
                    description = description_element.get_text().strip() if description_element else None

                    # Only return the first valid result with both title and description
                    if title and description:
                        return [{
                            "title": title,
                            "description": description
                        }]
                # If no valid result is found, return an error message
                return f"No valid SERP result found for '{query}'."
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

# Function to fetch keywords concurrently using multi-threading
def fetch_keywords_concurrently(queries, progress_bar, status_text, max_keywords=500):
    all_keywords = set()
    with ThreadPoolExecutor(max_workers=500) as executor:
        futures = {executor.submit(get_autosuggest, query): query for query in queries}
        for i, future in enumerate(as_completed(futures), start=1):
            try:
                keywords = future.result()
                if keywords:
                    all_keywords.update(keywords)
                progress_value = i / len(queries)
                progress_bar.progress(min(progress_value, 1.0))
                status_text.text(f"Fetching autosuggest keywords: {i}/{len(queries)} completed")
                if len(all_keywords) >= max_keywords:
                    break  # Stop fetching once the maximum limit is reached
            except Exception as e:
                st.error(f"Error fetching keywords: {e}")
    return list(all_keywords)[:max_keywords]

# Function to fetch SERP results concurrently (uses proxy)
def fetch_serp_results_concurrently(keywords, progress_bar, status_text):
    serp_results = {}
    with ThreadPoolExecutor(max_workers=500) as executor:  # Adjust max_workers as needed
        futures = {executor.submit(fetch_google_serp, keyword): keyword for keyword in keywords}
        for i, future in enumerate(as_completed(futures), start=1):
            keyword = futures[future]
            try:
                result = future.result()
                serp_results[keyword] = result
                progress_value = i / len(keywords)
                progress_bar.progress(min(progress_value, 1.0))
                status_text.text(f"Fetching SERP results: {i}/{len(keywords)} completed")
            except Exception as e:
                st.error(f"Error fetching SERP results for '{keyword}': {e}")
    return serp_results

# Function to format SERP data for logging
def format_serp_data_for_logging(serp_results):
    log_output = ""
    for keyword, results in serp_results.items():
        if isinstance(results, list):  # Only process valid SERP results
            log_output += f"Keyword: {keyword}\n"
            for i, result in enumerate(results, start=1):
                if isinstance(result, dict) and "title" in result and "description" in result:  # Ensure result is valid
                    log_output += f"  Result {i}:\n"
                    log_output += f"    Title: {result['title']}\n"
                    log_output += f"    Description: {result['description']}\n"
            log_output += "\n"
    return log_output

# Function to analyze keywords with Gemini
def analyze_keywords_with_gemini(keywords, serp_results, seed_keyword):
    # System instructions and chat input
    prompt = f"""
    Please analyze the intent for all of the keywords on this list based on the SERP page results for each keyword. Then come up with different themes that keywords can be grouped under. 

    **Rules:**
    1. Only include keywords that are closely related to the seed keyword: '{seed_keyword}' (artificial intelligence).
    2. Remove keywords that are too generic, irrelevant, or unclear in intent.
    3. Consolidate similar keywords into a single representative keyword.
    4. Limit each group to a maximum of 10 keywords.
    5. Do not include any explanations, notes, or additional text. Only provide the grouped keywords in the specified format.
    6. Ensure all keywords are grouped into relevant themes. Do not create an "Other" group.

    The final output should look EXACTLY like this:

    Theme Name
    - keyword 1
    - keyword 2
    - keyword 3
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

    # Retry logic for API calls with increased timeout
    @retry.Retry()
    def call_gemini():
        return gemini_model.generate_content(
            contents=[prompt, prompt + "\n" + chat_input],  # Pass prompt in both places
            generation_config=generation_config,
            request_options={"timeout": 600},  # 10-minute timeout
        )

    try:
        response = call_gemini()
        return response.text
    except Exception as e:
        st.error(f"Error calling Gemini API: {e}")
        return None

# Streamlit UI
# Remove the main title
# st.title("Google Autosuggest Keyword Fetcher with SERP Results and Gemini Analysis")

# Initialize session state to store keywords and SERP results
if "all_keywords" not in st.session_state:
    st.session_state.all_keywords = set()
if "serp_results" not in st.session_state:
    st.session_state.serp_results = {}
if "gemini_output" not in st.session_state:
    st.session_state.gemini_output = None

# Sidebar for user input and settings
with st.sidebar:
    st.header("Google Autosuggest Keyword Fetcher with SERP Results and Gemini Analysis")  # Replace "Settings" with the new title
    query = st.text_input("Enter a seed keyword:")
    st.markdown("---")
    st.markdown("**Instructions:**")
    st.markdown("1. Enter a seed keyword (e.g., 'AI').")
    st.markdown("2. The app will fetch autosuggest keywords and SERP results.")
    st.markdown("3. Keywords will be analyzed and grouped by intent using Gemini.")

# Main content
if query:
    # Initialize progress bar and status text (hidden from UI)
    progress_bar = st.empty()
    status_text = st.empty()

    # Step 1: Fetch initial autosuggest keywords
    with st.spinner("Fetching initial autosuggest keywords..."):
        initial_keywords = get_autosuggest(query)
        if initial_keywords:
            st.session_state.all_keywords.update(initial_keywords)
        progress_bar.progress(0.2)
        status_text.text("Fetching initial autosuggest keywords...")

    # Step 2: Generate expanded keyword variations
    expanded_keywords = generate_expanded_keywords(query, max_keywords=500)

    # Step 3: Fetch autosuggest keywords concurrently
    with st.spinner("Fetching autosuggest keywords concurrently..."):
        st.session_state.all_keywords.update(fetch_keywords_concurrently(expanded_keywords, progress_bar, status_text, max_keywords=500))
        progress_bar.progress(0.5)
        status_text.text("Fetching expanded autosuggest keywords...")

    # Step 4: Fetch SERP results for each keyword concurrently (uses proxy)
    if st.session_state.all_keywords:
        # Hide "Keyword fetching completed!" and "Total keywords fetched: 18"
        # Hide "Debug: Fetching SERP results for 18 keywords..."
        # Hide "Debug: SERP Results Dictionary" and the JSON output
        # Hide "View Scraped SERP Data (Sample)" and the box around it

        with st.spinner("Fetching SERP results for each keyword concurrently..."):
            st.session_state.serp_results = fetch_serp_results_concurrently(st.session_state.all_keywords, progress_bar, status_text)
            progress_bar.progress(0.8)
            status_text.text("Fetching SERP results...")

        # Step 5: Analyze keywords with Gemini
        if st.session_state.serp_results:
            with st.spinner("Analyzing keywords with Gemini..."):
                st.session_state.gemini_output = analyze_keywords_with_gemini(st.session_state.all_keywords, st.session_state.serp_results, query)
                progress_bar.progress(1.0)
                status_text.text("Analysis complete!")

        # Display Gemini output as collapsible cards in a 3-column grid
        if st.session_state.gemini_output:
            st.subheader("Keyword Themes and Groups")
            
            # Split the Gemini output into individual themes
            themes = st.session_state.gemini_output.strip().split("\n\n")
            
            # Create a container for the grid layout
            grid_container = st.container()
            
            # Initialize a counter to track the number of cards added
            card_counter = 0
            
            # Loop through themes and display them in a 3-column grid
            with grid_container:
                for theme in themes:
                    if theme.strip():  # Ensure the theme is not empty
                        # Split the theme into its name and keywords
                        theme_lines = theme.strip().split("\n")
                        theme_name = theme_lines[0]  # The first line is the theme name
                        theme_keywords = "\n".join(theme_lines[1:])  # The rest are keywords
                        
                        # Create a card-like layout using columns
                        if card_counter % 3 == 0:
                            col1, col2, col3 = st.columns(3)  # Create a new row of 3 columns
                        
                        # Determine which column to use for the current card
                        if card_counter % 3 == 0:
                            current_col = col1
                        elif card_counter % 3 == 1:
                            current_col = col2
                        else:
                            current_col = col3
                        
                        # Display the theme as a collapsible card
                        with current_col:
                            with st.expander(theme_name):
                                st.markdown(
                                    f"""
                                    <div style="
                                        padding: 10px;
                                        border: 1px solid #ddd;
                                        border-radius: 10px;
                                        background-color: #f9f9f9;
                                        height: 250px;  # Fixed height for squared cards
                                        overflow-y: auto;  # Add scroll if content overflows
                                    ">
                                        <pre style="white-space: pre-wrap;">{theme_keywords}</pre>
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                )
                        
                        # Increment the card counter
                        card_counter += 1
    else:
        st.write("No keywords found.")
else:
    st.session_state.all_keywords = set()
    st.session_state.serp_results = {}
    st.session_state.gemini_output = None
