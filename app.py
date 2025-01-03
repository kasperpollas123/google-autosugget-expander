import streamlit as st
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import google.generativeai as genai
from google.api_core import retry
import os
import string
from nltk.stem import WordNetLemmatizer
from difflib import SequenceMatcher
from nltk.corpus import stopwords

# Download NLTK data
import nltk
nltk.download('wordnet')
nltk.download('omw-1.4')
nltk.download('stopwords')

# Initialize lemmatizer and stopwords
lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('english'))

# Oxylabs proxy endpoint
PROXY_USER = os.getenv("PROXY_USER", "customer-kasperpollas12345_Lyt6m-cc-us")
PROXY_PASS = os.getenv("PROXY_PASS", "Snaksnak12345+")
PROXY_HOST = os.getenv("PROXY_HOST", "pr.oxylabs.io")
PROXY_PORT = os.getenv("PROXY_PORT", "7777")
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

# Google Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyAlxm5iSAsNVLbLvIVAAlxFkIBjkjE0E1Y")
if not GEMINI_API_KEY:
    st.error("Gemini API key is missing. Please set the GEMINI_API_KEY environment variable.")
    st.stop()

try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    st.write("Gemini model initialized successfully.")
except Exception as e:
    st.error(f"Error initializing Gemini model: {e}")
    st.stop()

# Function to fetch Google autosuggest keywords with retries (uses proxy)
def get_autosuggest(query, max_retries=3):
    url = "https://www.google.com/complete/search"
    params = {
        "q": query,
        "client": "chrome",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    proxies = {
        "http": PROXY_URL,
        "https": PROXY_URL,
    }
    for attempt in range(max_retries):
        try:
            st.write(f"Attempt {attempt + 1} to fetch autosuggest keywords for '{query}'...")
            response = requests.get(url, params=params, headers=headers, proxies=proxies, timeout=10)
            response.raise_for_status()
            st.write(f"Successfully fetched autosuggest keywords for '{query}'.")
            return response.json()[1]
        except requests.exceptions.RequestException as e:
            st.write(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                st.error(f"Error fetching autosuggest keywords for '{query}': {e}")
                return []
    return []

# Function to check if two words are similar (e.g., "monetization" and "monetize")
def is_similar(word1, word2, threshold=0.8):
    return SequenceMatcher(None, word1, word2).ratio() >= threshold

# Comment out the is_relevant function
# def is_relevant(keyword, seed_keyword):
#     try:
#         # Convert to lowercase for case-insensitive comparison
#         keyword_lower = keyword.lower()
#         seed_lower = seed_keyword.lower()

#         # Lemmatize both the keyword and seed keyword, and remove stopwords
#         keyword_words = [lemmatizer.lemmatize(word) for word in keyword_lower.split() if word not in stop_words]
#         seed_words = [lemmatizer.lemmatize(word) for word in seed_lower.split() if word not in stop_words]

#         # Count the number of matching words
#         matching_words = 0
#         for kw_word in keyword_words:
#             for seed_word in seed_words:
#                 if is_similar(kw_word, seed_word):
#                     matching_words += 1
#                     break  # Count each keyword word only once

#         # Check if the keyword contains at least n-1 words from the seed keyword
#         return matching_words >= (len(seed_words) - 1)
#     except Exception as e:
#         st.error(f"Error in relevance check for '{keyword}': {e}")
#         return False

# Function to generate expanded keyword variations with one level of recursion
def generate_expanded_keywords(seed_keyword):
    try:
        all_keywords = set()
        all_keywords.add(seed_keyword)

        # Fetch Level 1 autosuggest keywords
        level1_keywords = get_autosuggest(seed_keyword)
        if level1_keywords:
            all_keywords.update(level1_keywords)

        # Fetch Level 2 autosuggest keywords (one level of recursion)
        for keyword in level1_keywords:
            level2_keywords = get_autosuggest(keyword)
            if level2_keywords:
                # Comment out the relevance filter
                # filtered_level2_keywords = [kw for kw in level2_keywords if is_relevant(kw, seed_keyword)]
                all_keywords.update(level2_keywords)  # Use unfiltered Level 2 keywords

        # Universal modifiers (smaller set for better relevance)
        universal_modifiers = [
            "how to", "why is", "what is", "where to",
            "buy", "hire", "find", "near me",
            "best", "affordable", "top",
            "emergency", "24/7",
            "near me", "local"
        ]

        # Apply universal modifiers to all keywords
        for modifier in universal_modifiers:
            for keyword in list(all_keywords):  # Use list to avoid modifying set during iteration
                all_keywords.add(f"{modifier} {keyword}")
                all_keywords.add(f"{keyword} {modifier}")

        # Append each letter of the alphabet to all keywords
        for letter in string.ascii_lowercase:
            for keyword in list(all_keywords):
                all_keywords.add(f"{keyword} {letter}")
                all_keywords.add(f"{letter} {keyword}")

        return list(all_keywords)
    except Exception as e:
        st.error(f"Error generating expanded keywords: {e}")
        return []

# Function to fetch keywords concurrently using multi-threading
def fetch_keywords_concurrently(queries, progress_bar, status_text):
    all_keywords = set()
    try:
        with ThreadPoolExecutor(max_workers=50) as executor:  # Reduced max_workers to 50
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
    except Exception as e:
        st.error(f"Error in concurrent fetching: {e}")
        return []

# Function to analyze keywords with Gemini (only keywords, no SERP data)
def analyze_keywords_with_gemini(keywords, seed_keyword):
    try:
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
        try:
            initial_keywords = get_autosuggest(query)
            if initial_keywords:
                st.session_state.all_keywords.update(initial_keywords)
            progress_bar.progress(0.2)
            status_text.text("Fetching initial autosuggest keywords...")
        except Exception as e:
            st.error(f"Error fetching initial keywords: {e}")

    # Step 2: Generate expanded keyword variations
    expanded_keywords = generate_expanded_keywords(query)

    # Step 3: Fetch autosuggest keywords concurrently
    with st.spinner("Fetching autosuggest keywords concurrently..."):
        try:
            st.session_state.all_keywords.update(fetch_keywords_concurrently(expanded_keywords, progress_bar, status_text))
            progress_bar.progress(0.5)
            status_text.text("Fetching expanded autosuggest keywords...")
        except Exception as e:
            st.error(f"Error fetching keywords concurrently: {e}")

    # Step 4: Analyze keywords with Gemini
    if st.session_state.all_keywords:
        st.success("Keyword fetching completed!")
        st.write(f"Total keywords fetched: {len(st.session_state.all_keywords)}")

        with st.spinner("Analyzing keywords with Gemini..."):
            try:
                st.session_state.gemini_output = analyze_keywords_with_gemini(st.session_state.all_keywords, query)
                progress_bar.progress(1.0)
                status_text.text("Analysis complete!")
            except Exception as e:
                st.error(f"Error analyzing keywords with Gemini: {e}")

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
