import streamlit as st
import requests
import string
import time
import pandas as pd

# Oxylabs continuous rotation proxy endpoint
PROXY_USER = "customer-kasperpollas_EImZC-cc-us"
PROXY_PASS = "L6mFKak8Uz286dC+"
PROXY_HOST = "pr.oxylabs.io"
PROXY_PORT = "7777"

# Proxy URL (HTTPS)
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
            # Fetch autosuggest keywords
            response = requests.get(url, params=params, proxies=proxies)
            response.raise_for_status()
            return response.json()[1]
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:  # Don't log the error on the last attempt
                time.sleep(1)  # Wait 1 second before retrying
            else:
                st.error(f"Error fetching autosuggest keywords for '{query}': {e}")
    return []  # Return an empty list if all retries fail

# Function to generate expanded keyword variations
def generate_expanded_keywords(seed_keyword):
    expanded_keywords = []
    for letter in string.ascii_lowercase:
        # Append letter to the end of the seed keyword
        expanded_keywords.append(f"{seed_keyword} {letter}")
        # Append letter to the beginning of the seed keyword
        expanded_keywords.append(f"{letter} {seed_keyword}")
    return expanded_keywords

# Streamlit UI
st.title("Google Autosuggest Keyword Fetcher")
query = st.text_input("Enter a seed keyword:")
if query:
    # Initialize variables
    all_keywords = set()
    total_variations = 52  # 26 letters * 2 (beginning and end)
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Fetch initial autosuggest keywords
    with st.spinner("Fetching initial autosuggest keywords..."):
        initial_keywords = get_autosuggest(query)
        if initial_keywords:
            all_keywords.update(initial_keywords)
        progress_bar.progress(1 / total_variations)
        status_text.text(f"Progress: {1}/{total_variations} variations completed")

    # Generate expanded keyword variations
    expanded_keywords = generate_expanded_keywords(query)

    # Fetch autosuggest keywords for each expanded variation
    for i, expanded_query in enumerate(expanded_keywords, start=2):
        with st.spinner(f"Fetching autosuggest keywords for: {expanded_query}..."):
            keywords = get_autosuggest(expanded_query)
            if keywords:  # Only add if keywords are fetched successfully
                all_keywords.update(keywords)
            progress_bar.progress(i / total_variations)
            status_text.text(f"Progress: {i}/{total_variations} variations completed")
        time.sleep(1)  # Add a 1-second delay between requests

    # Display the final list of keywords
    if all_keywords:
        st.success("Keyword fetching completed!")
        st.write(f"Total keywords fetched: {len(all_keywords)}")

        # Convert keywords to a DataFrame
        keywords_df = pd.DataFrame(sorted(all_keywords), columns=["Keyword"])

        # Display the DataFrame
        st.write("Autosuggest Keywords:")
        st.dataframe(keywords_df)

        # Export to CSV
        csv = keywords_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name="autosuggest_keywords.csv",
            mime="text/csv",
        )
    else:
        st.write("No keywords found.")
