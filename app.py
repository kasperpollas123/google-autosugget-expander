import streamlit as st
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# Initialize Gemini model (Switched to Gemini 1.5 Flash)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

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
def generate_expanded_keywords(seed_keyword):
    # Fetch Level 1 autosuggest keywords
    level1_keywords = get_autosuggest(seed_keyword)

    # Fetch synonyms for the seed keyword
    synonyms = get_synonyms(seed_keyword)

    # Combine all keywords
    all_keywords = set()
    all_keywords.add(seed_keyword)
    all_keywords.update(level1_keywords)
    all_keywords.update(synonyms)

    # Universal modifiers
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
        for keyword in level1_keywords:
            all_keywords.add(f"{modifier} {keyword}")
            all_keywords.add(f"{keyword} {modifier}")

    # Remove duplicate keywords
    unique_keywords = []
    for kw in all_keywords:
        if not any(is_similar(kw, existing_kw) for existing_kw in unique_keywords):
            unique_keywords.append(kw)

    return unique_keywords

# Function to fetch keywords concurrently using multi-threading
def fetch_keywords_concurrently(queries, progress_bar, status_text):
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
            except Exception as e:
                st.error(f"Error fetching keywords: {e}")
    return list(all_keywords)

# Function to analyze keywords with Gemini (only keywords, no SERP data)
def analyze_keywords_with_gemini(keywords, seed_keyword):
    # System instructions and chat input
    prompt = f"""
    Please analyze the intent for all of the keywords on this list. Then come up with different themes that keywords can be grouped under. 

    **Rules:**
    1. Only include keywords that are closely related to the seed keyword: '{seed_keyword}'.
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
    chat_input = "Here is the list of keywords:\n"
    chat_input += "\n".join(keywords)

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
st.title("Google Autosuggest Keyword Fetcher with Gemini Analysis")

# Initialize session state to store keywords
if "all_keywords" not in st.session_state:
    st.session_state.all_keywords = set()
if "gemini_output" not in st.session_state:
    st.session_state.gemini_output = None

# Sidebar for user input and settings
with st.sidebar:
    st.header("Settings")
    query = st.text_input("Enter a seed keyword:")
    st.markdown("---")
    st.markdown("**Instructions:**")
    st.markdown("1. Enter a seed keyword (e.g., 'AI').")
    st.markdown("2. The app will fetch autosuggest keywords.")
    st.markdown("3. Keywords will be analyzed and grouped by intent using Gemini.")

# Main content
if query:
    # Initialize progress bar and status text
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Step 1: Fetch initial autosuggest keywords
    with st.spinner("Fetching initial autosuggest keywords..."):
        initial_keywords = get_autosuggest(query)
        if initial_keywords:
            st.session_state.all_keywords.update(initial_keywords)
        progress_bar.progress(0.2)
        status_text.text("Fetching initial autosuggest keywords...")

    # Step 2: Generate expanded keyword variations
    expanded_keywords = generate_expanded_keywords(query)

    # Step 3: Fetch autosuggest keywords concurrently
    with st.spinner("Fetching autosuggest keywords concurrently..."):
        st.session_state.all_keywords.update(fetch_keywords_concurrently(expanded_keywords, progress_bar, status_text))
        progress_bar.progress(0.5)
        status_text.text("Fetching expanded autosuggest keywords...")

    # Step 4: Analyze keywords with Gemini
    if st.session_state.all_keywords:
        st.success("Keyword fetching completed!")
        st.write(f"Total keywords fetched: {len(st.session_state.all_keywords)}")

        with st.spinner("Analyzing keywords with Gemini..."):
            st.session_state.gemini_output = analyze_keywords_with_gemini(st.session_state.all_keywords, query)
            progress_bar.progress(1.0)
            status_text.text("Analysis complete!")

        # Display Gemini output as collapsible cards
        if st.session_state.gemini_output:
            st.subheader("Keyword Themes and Groups")
            
            # Split the Gemini output into individual themes
            themes = st.session_state.gemini_output.strip().split("\n\n")
            
            for theme in themes:
                if theme.strip():  # Ensure the theme is not empty
                    # Split the theme into its name and keywords
                    theme_lines = theme.strip().split("\n")
                    theme_name = theme_lines[0]  # The first line is the theme name
                    theme_keywords = "\n".join(theme_lines[1:])  # The rest are keywords
                    
                    # Display the theme as a collapsible card
                    with st.expander(theme_name):
                        st.markdown(theme_keywords)
    else:
        st.write("No keywords found.")
else:
    st.session_state.all_keywords = set()
    st.session_state.gemini_output = None
