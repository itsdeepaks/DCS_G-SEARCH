import requests
import csv
import re
import os
import time
import json
import argparse
from dotenv import load_dotenv
from pathlib import Path
import logging
from contextlib import contextmanager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("influencer_search.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@contextmanager
def safe_open_write(path, mode="w", newline="", encoding="utf-8", max_retries=3, retry_delay=2):
    """Safely open a file for writing with retry mechanism."""
    for attempt in range(max_retries):
        try:
            file = open(path, mode, newline=newline, encoding=encoding)
            try:
                yield file
            finally:
                file.close()
            return  # File operations succeeded, exit the function
        except PermissionError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Permission error when writing to {path}. Retrying in {retry_delay}s... ({attempt+1}/{max_retries})")
                time.sleep(retry_delay)
            else:
                # On last attempt, try with a new filename
                new_path = create_alternative_filename(path)
                logger.warning(f"All retries failed. Trying with alternative filename: {new_path}")
                with open(new_path, mode, newline=newline, encoding=encoding) as alt_file:
                    yield alt_file
        except Exception as e:
            logger.error(f"Error opening file {path}: {e}")
            raise

def create_alternative_filename(filepath):
    """Create an alternative filename if the original is unavailable."""
    path = Path(filepath)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return str(path.with_stem(f"{path.stem}_{timestamp}"))

def validate_email(email):
    """Validate email format and domain."""
    if not email:
        return None
    
    # Basic email validation
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return None
    
    # Check for common dummy emails
    dummy_patterns = ['example.com', 'test.com', 'domain.com']
    for pattern in dummy_patterns:
        if pattern in email.lower():
            return None
            
    return email

def extract_data_to_csv(input_file, output_file):
    """Extract structured data from text file and save to CSV."""
    try:
        # Regular expressions to extract required fields
        name_pattern = r'^\d+\.\s*(.*?)\s*\(@'
        username_pattern = r'\(@([^)]+)\)'
        url_pattern = r'URL: (https://[^\s]+)'
        email_patterns = [
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            r'(?:^|\s)\.{3}\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'(?:^|\s)\.{3}\s*([a-zA-Z0-9._%+-]+)\s*gmail\.com'
        ]
        meta_stats_pattern = r'(\d+\.?\d*[KM]?)\s+Followers,\s*(\d+\.?\d*[KM]?)\s+Following,\s*(\d+\.?\d*[KM]?)\s+Posts'
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # Process the file
        with open(input_file, "r", encoding="utf-8") as infile, safe_open_write(output_file) as outfile:
            writer = csv.DictWriter(outfile, fieldnames=[
                "number", "name", "username", "url", "email", 
                "followers", "following", "posts", "description",
                "follower_count_numeric"  # New field for sorting
            ])
            writer.writeheader()
        
            content = infile.read()
            # Split content into individual results
            results = re.split(r'\n(?=\d+\.)', content)
        
            extracted_items = []
            for result in results:
                if not result.strip():
                    continue
        
                # Initialize data dictionary
                data = {
                    "number": None, "name": None, "username": None, "url": None,
                    "email": None, "followers": None, "following": None, 
                    "posts": None, "description": None, "follower_count_numeric": 0
                }
        
                # Extract number
                number_match = re.match(r'(\d+)\.', result)
                if number_match:
                    data["number"] = int(number_match.group(1))
        
                # Extract name and username
                name_match = re.search(name_pattern, result)
                if name_match:
                    data["name"] = name_match.group(1).strip()
        
                username_match = re.search(username_pattern, result)
                if username_match:
                    data["username"] = username_match.group(1)
        
                # Extract URL
                url_match = re.search(url_pattern, result)
                if url_match:
                    data["url"] = url_match.group(1)
        
                # Extract email (try all patterns)
                for pattern in email_patterns:
                    email_match = re.search(pattern, result)
                    if email_match:
                        email = email_match.group(1) if len(email_match.groups()) > 0 else email_match.group(0)
                        if not email.endswith('gmail.com') and 'gmail.com' in result:
                            email = f"{email}gmail.com"
                        data["email"] = validate_email(email)
                        break
        
                # Extract meta stats
                meta_match = re.search(meta_stats_pattern, result)
                if meta_match:
                    data["followers"] = meta_match.group(1)
                    data["following"] = meta_match.group(2)
                    data["posts"] = meta_match.group(3)
                    
                    # Convert followers to numeric for sorting
                    followers = meta_match.group(1)
                    data["follower_count_numeric"] = convert_to_numeric(followers)
        
                # Extract description (everything between Description: and Meta Description:)
                desc_match = re.search(r'Description: (.*?)(?=Meta Description:|$)', result, re.DOTALL)
                if desc_match:
                    data["description"] = desc_match.group(1).strip()
        
                extracted_items.append(data)
                
            # Sort by follower count (descending)
            extracted_items.sort(key=lambda x: x["follower_count_numeric"], reverse=True)
            
            # Write sorted data
            for data in extracted_items:
                writer.writerow(data)
        
        logger.info(f"Data has been extracted and saved to {output_file}")
        return output_file
    
    except Exception as e:
        logger.error(f"Error extracting data: {e}")
        raise

def convert_to_numeric(follower_string):
    """Convert follower string (like '1.5K' or '2M') to numeric value."""
    if not follower_string:
        return 0
        
    try:
        follower_string = follower_string.strip().upper()
        if 'K' in follower_string:
            return float(follower_string.replace('K', '')) * 1000
        elif 'M' in follower_string:
            return float(follower_string.replace('M', '')) * 1000000
        else:
            return float(follower_string)
    except (ValueError, TypeError):
        return 0

def search_and_save_pages(search_query, api_key, search_engine_id, niche, location, 
                         num_pages=10, results_dir="google_search_results"):
    """Search Google using Custom Search API and save results."""
    try:
        # Create directories if they don't exist
        os.makedirs(results_dir, exist_ok=True)
        os.makedirs(f"{results_dir}/csv_results", exist_ok=True)
        
        # Generate timestamp for unique filenames
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_niche = re.sub(r'[^\w]', '_', niche)
        safe_location = re.sub(r'[^\w]', '_', location)
        base_filename = f"{safe_niche}_{safe_location}_{timestamp}"
        all_results_path = f"{results_dir}/all_results_{base_filename}.txt"
        csv_filename = f"{results_dir}/csv_results/{base_filename}.csv"
        
        # Combined file to save all results
        with safe_open_write(all_results_path) as all_results_file:
            all_results_file.write(f"Google Search Results for '{search_query}'\n")
            all_results_file.write("=" * 80 + "\n\n")
            
            result_count = 0
            
            # Loop through each page
            for page in range(1, num_pages + 1):
                logger.info(f"Processing page {page}...")
                
                # Calculate the start index for pagination
                start_index = (page - 1) * 10 + 1
                
                # Construct the Google Custom Search Engine URL
                cse_url = (
                    f"https://www.googleapis.com/customsearch/v1"
                    f"?key={api_key}"
                    f"&cx={search_engine_id}"
                    f"&q={search_query}"
                    f"&start={start_index}"
                )
                
                # Use the API to get search results with rate limiting
                try:
                    # Add a small delay to prevent hitting rate limits
                    if page > 1:
                        time.sleep(1)
                        
                    response = requests.get(cse_url)
                    response.raise_for_status()
                    search_results = response.json()
                    
                    # Format the search results for saving
                    page_content = f"Page {page} Results:\n"
                    page_content += "=" * 80 + "\n\n"
                    
                    if 'items' in search_results:
                        for i, item in enumerate(search_results['items'], 1):
                            global_item_number = result_count + i
                            page_content += f"{global_item_number}. {item.get('title', 'No Title')}\n"
                            page_content += f"   URL: {item.get('link', 'No URL')}\n"
                            
                            # Include additional information if available
                            if 'snippet' in item:
                                page_content += f"   Description: {item['snippet']}\n"
                            
                            if 'pagemap' in item:
                                # Extract Instagram stats if available
                                instagram_data = extract_instagram_data(item)
                                if instagram_data:
                                    page_content += f"   {instagram_data}\n"
                                
                                # Extract meta description
                                if 'metatags' in item['pagemap'] and len(item['pagemap']['metatags']) > 0:
                                    metatags = item['pagemap']['metatags'][0]
                                    if 'og:description' in metatags:
                                        page_content += f"   Meta Description: {metatags['og:description']}\n"
                            
                            page_content += "\n"
                        
                        result_count += len(search_results['items'])
                    else:
                        page_content += "No results found for this page.\n\n"
                    
                    # Save the formatted results to a page-specific file
                    page_file_path = f"{results_dir}/page_{page}_{base_filename}.txt"
                    with safe_open_write(page_file_path) as page_file:
                        page_file.write(f"Google Search Results for '{search_query}' - Page {page}\n")
                        page_file.write("=" * 80 + "\n\n")
                        page_file.write(page_content)
                    
                    # Also append to the combined results file
                    all_results_file.write(page_content)
                    
                    logger.info(f"Saved search results from page {page}")
                    
                    # Check if we've reached the end of results
                    if 'queries' in search_results and 'nextPage' not in search_results['queries']:
                        logger.info(f"No more results available after page {page}")
                        break
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"API request error for page {page}: {e}")
                    if hasattr(e, 'response') and e.response is not None:
                        logger.error(f"Response status code: {e.response.status_code}")
                        logger.error(f"Response text: {e.response.text}")
                    break
            
            logger.info(f"Completed processing search results. All results saved to {all_results_path}")
            
        # Extract data to CSV
        extract_data_to_csv(all_results_path, csv_filename)
        logger.info(f"Results saved to CSV: {csv_filename}")
        
        return csv_filename
    
    except Exception as e:
        logger.error(f"An error occurred during search: {e}")
        raise

def extract_instagram_data(item):
    """Extract Instagram follower, following, and post counts from search results."""
    if 'person' in item['pagemap'] and len(item['pagemap']['person']) > 0:
        person = item['pagemap']['person'][0]
        followers = person.get('followers', 'N/A')
        following = person.get('following', 'N/A')
        posts = person.get('interactioncount', 'N/A')
        
        return f"{followers} Followers, {following} Following, {posts} Posts"
    
    return None

def load_config():
    """Load configuration from .env file or environment variables."""
    # First try to load from .env file
    load_dotenv()
    
    # Get settings from environment or provide defaults
    config = {
        'api_key': os.getenv('GOOGLE_API_KEY'),
        'search_engine_id': os.getenv('GOOGLE_SEARCH_ENGINE_ID'),
        'results_dir': os.getenv('RESULTS_DIR', 'google_search_results'),
        'max_pages': int(os.getenv('MAX_PAGES', '10'))
    }
    
    # Verify required settings
    missing = [k for k, v in config.items() if v is None and k in ['api_key', 'search_engine_id']]
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
        
    return config

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description='Search for influencers and extract their data.')
    parser.add_argument('--niche', help='Niche or multiple niches separated by comma')
    parser.add_argument('--location', help='Location to search for')
    parser.add_argument('--pages', type=int, help='Number of pages to search (default: from config)')
    parser.add_argument('--output', help='Output directory (default: from config)')
    parser.add_argument('--min-followers', type=int, help='Minimum number of followers')
    parser.add_argument('--max-followers', type=int, help='Maximum number of followers')
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        config = load_config()
        
        # Use command line arguments if provided, otherwise prompt
        niche = args.niche
        location = args.location
        
        if not niche:
            print("\nExample niches: beauty, finance, tech, travel, food, fashion, fitness")
            niche = input("\nEnter niche (or multiple niches separated by comma): ").strip()
        
        if not location:
            print("Example locations: India, Delhi, Mumbai, Noida, Bangalore, Pune")
            location = input("Enter location: ").strip()
        
        # Format the search query
        niches = ' OR '.join(f'{n.strip()}' for n in niche.split(','))
        search_query = f'{niches} {location} "@gmail.com" site:instagram.com'
        
        logger.info(f"Constructed search query: {search_query}")
        
        # Use args values if provided, otherwise use config defaults
        num_pages = args.pages or config['max_pages']
        results_dir = args.output or config['results_dir']
        
        # Perform the search
        csv_file = search_and_save_pages(
            search_query=search_query, 
            api_key=config['api_key'], 
            search_engine_id=config['search_engine_id'],
            niche=niche,
            location=location,
            num_pages=num_pages,
            results_dir=results_dir
        )
        
        logger.info(f"Search completed successfully. Results saved to {csv_file}")
        
    except Exception as e:
        logger.error(f"Error running the script: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())