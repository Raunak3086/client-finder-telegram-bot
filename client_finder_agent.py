import argparse
import os
import re
import googlemaps
from fpdf import FPDF
from datetime import datetime
from ddgs import DDGS
from dotenv import load_dotenv
import requests

# Load environment variables from .env file
load_dotenv()

# You will need to install these libraries:
# pip install googlemaps fpdf ddgs python-dotenv

def find_email(business_name, city):
    query = f'"{business_name}" {city} email OR @gmail.com OR @yahoo.com'
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=5)
            for r in results:
                snippet = r.get('body', '') + ' ' + r.get('title', '')
                # Basic email regex
                emails = re.findall(r'[a-zA-Z0-9.\-+_]+@[a-zA-Z0-9.\-+_]+\.[a-zA-Z]+', snippet)
                if emails:
                    return emails[0]
    except Exception as e:
        print(f"  [!] Error searching email for {business_name}: {e}")
    return "Not found"

def find_potential_clients(api_key, city, business_type="business", min_reviews=20):
    query = f"{business_type} in {city}"
    print(f"Searching for: {query}")
    
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.websiteUri,places.userRatingCount,places.googleMapsUri,places.nationalPhoneNumber,nextPageToken"
    }
    
    leads = []
    seen_names = set()
    next_page_token = None
    max_pages = 10
    page_count = 0
    
    while page_count < max_pages and len(leads) < 20:
        payload = {
            "textQuery": query,
            "languageCode": "en"
        }
        if next_page_token:
            payload["pageToken"] = next_page_token
            
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            places_data = data.get('places', [])
            next_page_token = data.get('nextPageToken')
        except Exception as e:
            print(f"Error fetching data from Google Places API (New): {e}")
            if 'response' in locals() and response.text:
                print(f"Response: {response.text}")
            break
            
        if not places_data:
            break
        
        for place in places_data:
            if len(leads) >= 20:
                break
                
            # Google Places (New) structure
            name_info = place.get('displayName', {})
            name = name_info.get('text', 'Unknown')
            
            # Deduplicate
            if name in seen_names:
                continue
                
            reviews = place.get('userRatingCount', 0)
            website = place.get('websiteUri')
            phone = place.get('nationalPhoneNumber', 'Not available')
            gmaps_url = place.get('googleMapsUri', '')
            
            # Target criteria: No website, good number of reviews
            if not website and reviews >= min_reviews:
                seen_names.add(name)
                print(f"Found lead: {name} (Reviews: {reviews})")
                print(f"  -> Searching the web for an email address...")
                email = find_email(name, city)
                print(f"  -> Email: {email}")
                
                leads.append({
                    'name': name,
                    'phone': phone,
                    'reviews': reviews,
                    'gmaps_url': gmaps_url,
                    'email': email
                })
                
        if not next_page_token:
            break
            
        page_count += 1
            
    return leads

def sanitize_text(text):
    if not text:
        return ""
    # Strip characters that are not latin-1 compatible
    return text.encode('latin-1', 'ignore').decode('latin-1')

def generate_pdf(leads, city):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    clean_city = sanitize_text(city)
    
    # Title
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt=f"Potential Web Design Clients in {clean_city}", ln=1, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=1, align='C')
    pdf.ln(10)
    
    if not leads:
        pdf.cell(200, 10, txt="No leads found matching the criteria (no website + good reviews).", ln=1)
    else:
        for i, lead in enumerate(leads, 1):
            pdf.set_font("Arial", 'B', 12)
            clean_name = sanitize_text(lead['name'])
            pdf.cell(200, 10, txt=f"{i}. {clean_name}", ln=1)
            
            pdf.set_font("Arial", size=11)
            clean_phone = sanitize_text(lead['phone'])
            clean_email = sanitize_text(lead['email'])
            
            pdf.cell(200, 8, txt=f"Phone: {clean_phone}", ln=1)
            pdf.cell(200, 8, txt=f"Reviews on Google: {lead['reviews']}", ln=1)
            pdf.cell(200, 8, txt=f"Email: {clean_email}", ln=1)
            
            # Make URL clickable if possible, or just text
            pdf.set_text_color(0, 0, 255)
            clean_url = sanitize_text(lead['gmaps_url'])
            pdf.cell(200, 8, txt=f"Google Maps Link: {clean_url}", ln=1, link=clean_url)
            pdf.set_text_color(0, 0, 0)
            
            pdf.ln(5)
            
    output_filename = f"Leads_{clean_city.replace(' ', '_')}.pdf"
    pdf.output(output_filename)
    print(f"\nPDF generated successfully: {output_filename}")
    return output_filename

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find local businesses without websites as web dev clients.")
    parser.add_argument("--city", required=True, help="City to search in")
    parser.add_argument("--type", default="local business", help="Type of business (e.g., 'plumber', 'restaurant')")
    parser.add_argument("--min-reviews", type=int, default=20, help="Minimum number of Google reviews")
    
    args = parser.parse_args()
    
    # Requires a Google Maps API Key exposed as an environment variable
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("Error: Please set the GOOGLE_MAPS_API_KEY environment variable.")
        print("Example: $env:GOOGLE_MAPS_API_KEY='your_api_key_here'")
        exit(1)
        
    print(f"Searching for leads in {args.city}...")
    leads = find_potential_clients(api_key, args.city, args.type, args.min_reviews)
    generate_pdf(leads, args.city)
