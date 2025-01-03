import streamlit as st
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import google.generativeai as genai
from google.api_core import retry
from difflib import SequenceMatcher
import os

# Oxylabs proxy endpoint
PROXY_USER = os.getenv("PROXY_USER", "customer-kasperpollas12345_Lyt6m-cc-us")
PROXY_PASS = os.getenv("PROXY_PASS", "Snaksnak12345+")
PROXY_HOST = os.getenv("PROXY_HOST", "pr.oxylabs.io")
PROXY_PORT = os.getenv("PROXY_PORT", "7777")
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

# Google Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyAlxm5iSAsNVLbLvIVAAlxFkIBjkjE0E1Y")
genai.configure(api_key=GEMINI_API_KEY)

# Initialize Gemini model (Switched to Gemini 1.5 Pro)
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

# Function to check if two keywords are too similar
def is_similar(keyword1, keyword2, threshold=0.8):
    return SequenceMatcher(None, keyword1, keyword2).ratio() >= threshold

# Function to generate expanded keyword variations (Level 1)
def generate_expanded_keywords(seed_keyword):
    # Universal modifiers
    universal_modifiers = [
        "how to", "why is", "what is", "where to",
        "buy", "hire", "find", "near me",
        "best", "affordable", "top",
        "emergency", "24/7",
        "near me", "local"
    ]

    # Alphabet modifiers (A-Z)
    alphabet_modifiers = [chr(i) for i in range(ord('a'), ord('z') + 1)]

    # Generate modified seed keywords
    modified_seed_keywords = []
    for modifier in universal_modifiers:
        modified_seed_keywords.append(f"{seed_keyword} {modifier}")
    for letter in alphabet_modifiers:
        modified_seed_keywords.append(f"{seed_keyword} {letter}")

    # Fetch autosuggestions for each modified seed keyword
    all_keywords = set()
    with ThreadPoolExecutor(max_workers=500) as executor:
        futures = {executor.submit(get_autosuggest, query): query for query in modified_seed_keywords}
        for i, future in enumerate(as_completed(futures), start=1):
            try:
                keywords = future.result()
                if keywords:
                    all_keywords.update(keywords)
            except Exception as e:
                st.error(f"Error fetching autosuggest keywords for '{modified_seed_keywords[i-1]}': {e}")

    # Remove duplicate keywords
    unique_keywords = []
    for kw in all_keywords:
        if not any(is_similar(kw, existing_kw) for existing_kw in unique_keywords):
            unique_keywords.append(kw)

    return unique_keywords

# Function to generate Level 2 keywords
def generate_level2_keywords(level1_keywords, progress_bar, status_text):
    all_keywords = set()
    with ThreadPoolExecutor(max_workers=500) as executor:
        futures = {executor.submit(get_autosuggest, query): query for query in level1_keywords}
        for i, future in enumerate(as_completed(futures), start=1):
            try:
                keywords = future.result()
                if keywords:
                    all_keywords.update(keywords)
                    # Log Level 2 keywords
                    with st.expander(f"Level 2 Keywords for '{level1_keywords[i-1]}'"):
                        st.write(keywords)
                progress_value = i / len(level1_keywords)
                progress_bar.progress(min(progress_value, 1.0))
                status_text.text(f"Fetching Level 2 keywords: {i}/{len(level1_keywords)} completed")
            except Exception as e:
                st.error(f"Error fetching Level 2 keywords: {e}")
    return list(all_keywords)

# Function to analyze keywords with Gemini (only keywords, no SERP data)
def analyze_keywords_with_gemini(keywords, seed_keyword):
    # Combine system instructions and chat input into a single prompt
    prompt = f"""
    Please analyze the intent for all of the keywords on this list. Then come up with different themes that keywords can be grouped under. 

    **Rules:**
    1. Include keywords that are related or tangentially relevant to the seed keyword: '{seed_keyword}'.
    2. Remove only keywords that are completely irrelevant, overly generic, or unclear in intent.
    3. Consolidate similar keywords into a single representative keyword only if they are nearly identical.
    4. Limit each group to a maximum of 20 keywords.
    5. Do not include any explanations, notes, or additional text. Only provide the grouped keywords in the specified format.
    6. Ensure all keywords are grouped into relevant themes. If necessary, create an "Other" group for slightly less relevant but still useful keywords.

    The final output should look EXACTLY like this:

    Theme Name
    - keyword 1
    - keyword 2
    - keyword 3

    Here is the list of keywords:
    """
    prompt += "\n".join(keywords)

    # Log the full prompt sent to Gemini
    with st.expander("Full Prompt Sent to Gemini"):
        st.write(prompt)

    # Configure Gemini generation settings
    generation_config = {
        "temperature": 1,  # Higher temperature for more creative outputs
        "max_output_tokens": 8192,  # Set output token limit to 8192
        "top_p": 0.95,  # Set top_p to 0.95
    }

    # Retry logic for API calls with increased timeout
    @retry.Retry()
    def call_gemini():
        return gemini_model.generate_content(
            contents=[prompt],  # Pass the combined prompt as a single input
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
            # Log Level 1 keywords (initial autosuggestions)
            with st.expander("Level 1 Keywords (Initial Autosuggestions)"):
                st.write(initial_keywords)
        progress_bar.progress(0.2)
        status_text.text("Fetching initial autosuggest keywords...")

    # Step 2: Generate expanded keyword variations (Level 1)
    expanded_keywords = generate_expanded_keywords(query)
    # Log Level 1 keywords (with modifiers)
    with st.expander("Level 1 Keywords (With Modifiers)"):
        st.write(expanded_keywords)

    # Step 3: Fetch Level 2 keywords
    with st.spinner("Fetching Level 2 keywords..."):
        level2_keywords = generate_level2_keywords(expanded_keywords, progress_bar, status_text)
        st.session_state.all_keywords.update(level2_keywords)
        progress_bar.progress(0.5)
        status_text.text("Fetching Level 2 keywords...")

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
