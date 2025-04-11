import streamlit as st
import pandas as pd
from search import search_and_save_pages, load_config
import os

def main():
    st.set_page_config(page_title="Influencer Search Tool", layout="wide")
    
    st.title("DCS-Instagram Influencer Search Tool")
    st.write("Find relevant influencers for your brand campaigns")
    
    # Load configuration
    try:
        config = load_config()
    except ValueError as e:
        st.error(f"Configuration Error: {e}")
        return
    
    # Create sidebar for inputs
    with st.sidebar:
        st.header("Search Parameters")
        
        # Niche selection
        st.subheader("Niche Selection")
        niche_input = st.text_input(
            "Enter niche(s)",
            placeholder="e.g., tech, finance, beauty",
            help="For multiple niches, separate with commas"
        )
        
        # Location selection
        st.subheader("Location")
        location = st.text_input(
            "Enter location",
            placeholder="e.g., India, Mumbai, Delhi",
            help="Enter the target location"
        )
        
        # Number of pages
        num_pages = st.slider(
            "Number of pages to search",
            min_value=1,
            max_value=10,
            value=5,
            help="Maximum 10 pages due to API limitations"
        )
        
        # Search button
        search_button = st.button("Search Influencers")
    
    # Main content area
    if search_button and niche_input and location:
        with st.spinner("Searching for influencers..."):
            try:
                # Perform search
                csv_file = search_and_save_pages(
                    search_query=f"{niche_input} {location} '@gmail.com' site:instagram.com",
                    api_key=config['api_key'],
                    search_engine_id=config['search_engine_id'],
                    niche=niche_input,
                    location=location,
                    num_pages=num_pages
                )
                
                # Read and display results
                if os.path.exists(csv_file):
                    df = pd.read_csv(csv_file)
                    
                    # Display statistics
                    st.subheader("Search Results Overview")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Influencers Found", len(df))
                    with col2:
                        avg_followers = df['follower_count_numeric'].mean()
                        st.metric("Average Followers", f"{avg_followers:,.0f}")
                    with col3:
                        has_email = df['email'].notna().sum()
                        st.metric("Influencers with Email", has_email)
                    
                    # Display results table
                    st.subheader("Influencer Details")
                    st.dataframe(
                        df.drop('follower_count_numeric', axis=1),
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    # Download button
                    st.download_button(
                        label="Download Results CSV",
                        data=df.to_csv(index=False).encode('utf-8'),
                        file_name=f"influencers_{niche_input}_{location}.csv",
                        mime="text/csv"
                    )
                else:
                    st.error("No results found.")
            
            except Exception as e:
                st.error(f"An error occurred: {e}")
    
    elif search_button:
        st.warning("Please enter both niche and location to search.")
    
    # Add footer with instructions
    st.markdown("---")
    st.markdown("### How to Use")
    st.markdown("""
    1. Enter the niche(s) you're interested in
    2. Specify the target location
    3. Adjust the number of pages to search
    4. Click 'Search Influencers' to start
    5. Download results as CSV if needed
    """)

if __name__ == "__main__":
    main()
