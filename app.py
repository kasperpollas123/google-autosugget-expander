import streamlit as st
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
import os
from openai import OpenAI

# Oxylabs proxy endpoint
PROXY_USER = os.getenv("PROXY_USER", "customer-kasperpollas12345_Lyt6m-cc-us")
PROXY_PASS = os.getenv("PROXY_PASS", "Snaksnak12345+")
PROXY_HOST = os.getenv("PROXY_HOST", "pr.oxylabs.io")
PROXY_PORT = os.getenv("PROXY_PORT", "7777")
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

# OpenAI API key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-svcacct-AmMaPplrcuwyMUy7uuIyS3PnAxgHAYtlUe_6Ox4Cu_M5U9RSKaZvklTwkehkkbUT3BlbkFJUZjZz7Ay7VLN42-C8PPMKf8LIdGMNVNnjT3qSPqwSSsuKcvya_hzlAInRqjQAYwA")
client = OpenAI(api_key=OPENAI_API_KEY)

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
        modified_seed_keywords.append(f"{seed_keyword} {modifier}")  # Append modifier with space
        modified_seed_keywords.append(f"{modifier} {seed_keyword}")  # Prepend modifier with space
    for letter in alphabet_modifiers:
        modified_seed_keywords.append(f"{seed_keyword} {letter}")  # Append letter with space
        modified_seed_keywords.append(f"{letter} {seed_keyword}")  # Prepend letter with space

    # Fetch autosuggestions for each modified seed keyword
    all_keywords = set()
    with ThreadPoolExecutor(max_workers=500) as executor:
        futures = {executor.submit(get_autosuggest, query): query for query in modified_seed_keywords}
        for future in as_completed(futures):
            try:
                keywords = future.result()
                if keywords:
                    all_keywords.update(keywords)
            except Exception as e:
                st.error(f"Error fetching autosuggest keywords: {e}")

    # Remove duplicate keywords
    unique_keywords = []
    for kw in all_keywords:
        if not any(is_similar(kw, existing_kw) for existing_kw in unique_keywords):
            unique_keywords.append(kw)

    return unique_keywords

# Function to generate Level 2 keywords
def generate_level2_keywords(level1_keywords, progress_bar, status_text):
    all_keywords = {}
    with ThreadPoolExecutor(max_workers=500) as executor:
        futures = {executor.submit(get_autosuggest, query): query for query in level1_keywords}
        for i, future in enumerate(as_completed(futures), start=1):
            query = futures[future]  # Get the query associated with this future
            try:
                keywords = future.result()
                if keywords:
                    all_keywords[query] = keywords
                    # Log Level 2 keywords
                    with st.expander(f"Level 2 Keywords for '{query}'"):
                        st.write(keywords)
                progress_value = i / len(level1_keywords)
                progress_bar.progress(min(progress_value, 1.0))
                status_text.text(f"Fetching Level 2 keywords: {i}/{len(level1_keywords)} completed")
            except Exception as e:
                st.error(f"Error fetching Level 2 keywords for '{query}': {e}")
    return all_keywords

# Function to analyze keywords with OpenAI GPT-4 (structured input)
def analyze_keywords_with_openai(level1_keywords, level2_keywords_mapping):
    # System message with strict instructions
    system_message = """
    You are a keyword analysis assistant. Your task is to analyze the provided Level 1 keywords and their associated Level 2 keywords, then group them into broader, high-level themes. Follow these rules strictly:

    1. Create broad, meaningful themes that can logically group the Level 1 keywords.
    2. Each theme should include the Level 1 keyword(s) and their associated Level 2 keywords.
    3. Ensure themes are distinct and avoid overlapping.
    4. Do not include any explanations, notes, or additional text. Only provide the grouped keywords in the specified format.
    5. If a Level 1 keyword fits into multiple themes, include it in the most relevant one.

    The final output should look EXACTLY like this:

    Theme Name
    - Level 1 Keyword 1
      - Level 2 Keyword 1
      - Level 2 Keyword 2
    - Level 1 Keyword 2
      - Level 2 Keyword 3
      - Level 2 Keyword 4
    """

    # Prepare structured input for OpenAI
    structured_input = []
    for level1_kw, level2_kws in level2_keywords_mapping.items():
        structured_input.append(f"- {level1_kw}")
        for level2_kw in level2_kws:
            structured_input.append(f"  - {level2_kw}")

    # Chat input (the structured keyword list)
    chat_input = f"""
    Here is the structured list of Level 1 keywords and their associated Level 2 keywords:
    {"\n".join(structured_input)}
    """

    # Log the full prompt sent to OpenAI
    with st.expander("Full Prompt Sent to OpenAI"):
        st.write(system_message + "\n\n" + chat_input)

    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # Use "gpt-4o" if available
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": chat_input},
            ],
            max_tokens=4096,
            temperature=0,  # Lower temperature for deterministic outputs
        )
        # Log the raw response from OpenAI
        with st.expander("Raw Response from OpenAI"):
            st.write(response.choices[0].message.content)
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Error calling OpenAI API: {e}")
        return None

# Streamlit UI
st.title("Google Autosuggest Keyword Fetcher with OpenAI Analysis")

# Initialize session state to store keywords
if "all_keywords" not in st.session_state:
    st.session_state.all_keywords = {}
if "openai_output" not in st.session_state:
    st.session_state.openai_output = None

# Sidebar for user input and settings
with st.sidebar:
    st.header("Settings")
    query = st.text_input("Enter a seed keyword:")
    st.markdown("---")
    st.markdown("**Instructions:**")
    st.markdown("1. Enter a seed keyword (e.g., 'AI').")
    st.markdown("2. The app will fetch autosuggest keywords.")
    st.markdown("3. Keywords will be analyzed and grouped by intent using OpenAI GPT-4.")

# Main content
if query:
    # Initialize progress bar and status text
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Step 1: Fetch initial autosuggest keywords
    with st.spinner("Fetching initial autosuggest keywords..."):
        initial_keywords = get_autosuggest(query)
        if initial_keywords:
            st.session_state.all_keywords[query] = initial_keywords
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
        level2_keywords_mapping = generate_level2_keywords(expanded_keywords, progress_bar, status_text)
        st.session_state.all_keywords.update(level2_keywords_mapping)
        progress_bar.progress(0.5)
        status_text.text("Fetching Level 2 keywords...")

    # Step 4: Analyze keywords with OpenAI GPT-4
    if st.session_state.all_keywords:
        st.success("Keyword fetching completed!")
        st.write(f"Total Level 1 keywords fetched: {len(st.session_state.all_keywords)}")

        with st.spinner("Analyzing keywords with OpenAI GPT-4..."):
            st.session_state.openai_output = analyze_keywords_with_openai(expanded_keywords, level2_keywords_mapping)
            progress_bar.progress(1.0)
            status_text.text("Analysis complete!")

        # Display OpenAI output as collapsible cards with hierarchy
        if st.session_state.openai_output:
            st.subheader("Keyword Themes and Groups")
            
            # Split the OpenAI output into individual themes
            themes = st.session_state.openai_output.strip().split("\n\n")
            
            for theme in themes:
                if theme.strip():  # Ensure the theme is not empty
                    theme_lines = theme.strip().split("\n")
                    theme_name = theme_lines[0]  # The first line is the theme name
                    
                    # Display the theme as a collapsible card
                    with st.expander(theme_name):
                        for line in theme_lines[1:]:
                            if line.startswith("- "):  # Level 1 keyword
                                st.markdown(f"**{line[2:]}**")
                            elif line.startswith("  - "):  # Level 2 keyword
                                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{line[4:]}")
    else:
        st.write("No keywords found.")
else:
    st.session_state.all_keywords = {}
    st.session_state.openai_output = None
