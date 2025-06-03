#!/usr/bin/env python3
"""
Strava Club Events Calendar Scraper
Scrapes upcoming events from Strava clubs and generates an ICS calendar file.
"""

import time
import configparser
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from icalendar import Calendar, Event
import pytz
import re
import os

class StravaEventScraper:
    def __init__(self):
        self.driver = None
        self.config = configparser.ConfigParser()
        self.events = []
        self.pacific_tz = pytz.timezone('America/Los_Angeles')
        
    def load_config(self):
        """Load configuration from config.ini"""
        print("📄 Loading configuration...")
        if not os.path.exists('config.ini'):
            print("❌ config.ini not found. Please create it with your Strava credentials.")
            return False
            
        self.config.read('config.ini')
        
        if 'strava' not in self.config or not self.config['strava'].get('email'):
            print("❌ Missing Strava credentials in config.ini")
            return False
            
        print(f"✅ Config loaded for email: {self.config['strava']['email']}")
        return True
    
    def setup_driver(self):
        """Initialize Chrome WebDriver with session persistence"""
        print("🌐 Setting up Chrome browser...")
        
        chrome_options = Options()
        # Use persistent profile to save cookies
        chrome_options.add_argument("--user-data-dir=./chrome_profile")
        chrome_options.add_argument("--profile-directory=Default")
        # Not headless for better detection avoidance
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        print("✅ Chrome browser ready")
        
    def login_to_strava(self):
        """Open login page and wait for manual login"""
        print("🔐 Opening Strava login page...")
        print("Please log in manually in the browser window.")
        print("After logging in successfully, press Enter in this terminal to continue...")
        
        self.driver.get("https://www.strava.com/login")
        
        # Wait for user to press Enter
        input()
        
        # Verify login was successful
        try:
            WebDriverWait(self.driver, 10).until(
                lambda driver: "dashboard" in driver.current_url or "feed" in driver.current_url
            )
            print("✅ Login verified successfully")
            return True
        except Exception as e:
            print("❌ Login verification failed. Please ensure you're logged in to Strava.")
            print("Press Enter to try again, or Ctrl+C to exit...")
            input()
            return self.login_to_strava()  # Retry login
    
    def load_club_urls(self):
        """Load club URLs from clubs.txt"""
        print("📋 Loading club URLs...")
        
        if not os.path.exists('clubs.txt'):
            print("❌ clubs.txt not found")
            return []
            
        with open('clubs.txt', 'r') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
        print(f"✅ Found {len(urls)} club URLs to scrape")
        for i, url in enumerate(urls, 1):
            print(f"   {i}. {url}")
            
        return urls
    
    def scrape_club_events(self, club_url):
        """Scrape events from a single club"""
        print(f"\n🏃 Scraping club: {club_url}")
        
        try:
            self.driver.get(club_url)
            time.sleep(3)
            
            # Look for "View All" button and click if present
            try:
                view_all_btn = self.driver.find_element(By.CSS_SELECTOR, "button[data-show-all^='View All']")
                view_all_btn.click()
                print("👁️  Clicked 'View All' button")
                time.sleep(2)  # Give time for events to load
            except Exception as e:
                print(f"ℹ️  No 'View All' button found or error clicking it: {str(e)}")
            
            # Find all event rows
            event_rows = self.driver.find_elements(By.CSS_SELECTOR, "li.row")
            print(f"🔍 Found {len(event_rows)} potential event rows")
            
            club_events = []
            for i, row in enumerate(event_rows):
                try:
                    # Look for event title link
                    title_link = row.find_element(By.CSS_SELECTOR, "a.group-event-title")
                    title_text = title_link.text.strip()
                    event_url = title_link.get_attribute('href')
                    
                    # Look for date elements
                    date_elem = row.find_element(By.CSS_SELECTOR, ".date")
                    month_elem = row.find_element(By.CSS_SELECTOR, ".month")
                    
                    date_text = date_elem.text.strip()
                    month_text = month_elem.text.strip()
                    
                    print(f"   📅 Event {i+1}: {title_text}")
                    print(f"      Date: {month_text} {date_text}")
                    print(f"      URL: {event_url}")
                    
                    # Parse the event
                    parsed_event = self.parse_event_details(title_text, date_text, month_text, event_url)
                    if parsed_event:
                        club_events.append(parsed_event)
                        print(f"      ✅ Parsed successfully")
                    else:
                        print(f"      ⚠️  Failed to parse event details")
                        
                except Exception as e:
                    print(f"      ❌ Error parsing event row {i+1}: {str(e)}")
                    continue
            
            print(f"✅ Successfully scraped {len(club_events)} events from club")
            return club_events
            
        except Exception as e:
            print(f"❌ Error scraping club {club_url}: {str(e)}")
            return []
    
    def parse_event_details(self, title_text, date_text, month_text, event_url):
        """Parse event details from scraped text"""
        try:
            # Parse title format: "Tue 6:30 AM / Event Title"
            title_match = re.match(r'(\w+)\s+(\d{1,2}:\d{2})\s+(AM|PM)\s*/\s*(.+)', title_text)
            if not title_match:
                print(f"      ⚠️  Could not parse title format: {title_text}")
                return None
                
            day_name, time_str, am_pm, event_name = title_match.groups()
            
            # Parse date (assume current year, handle year rollover)
            current_year = datetime.now().year
            try:
                # Try current year first
                event_date = datetime.strptime(f"{date_text} {month_text} {current_year}", "%d %b %Y")
                # If date is more than 2 months in the past, assume next year
                if event_date < datetime.now() - timedelta(days=60):
                    event_date = datetime.strptime(f"{date_text} {month_text} {current_year + 1}", "%d %b %Y")
            except ValueError:
                print(f"      ⚠️  Could not parse date: {date_text} {month_text}")
                return None
            
            # Parse time
            try:
                time_obj = datetime.strptime(f"{time_str} {am_pm}", "%I:%M %p").time()
            except ValueError:
                print(f"      ⚠️  Could not parse time: {time_str} {am_pm}")
                return None
            
            # Combine date and time in Pacific timezone
            naive_datetime = datetime.combine(event_date.date(), time_obj)
            event_datetime = self.pacific_tz.localize(naive_datetime)
            
            # Calendar event should be 30 minutes BEFORE ride time
            calendar_datetime = event_datetime - timedelta(minutes=30)
            
            return {
                'name': event_name.strip(),
                'datetime': calendar_datetime,
                'url': event_url,
                'original_time': event_datetime
            }
            
        except Exception as e:
            print(f"      ❌ Error parsing event: {str(e)}")
            return None
    
    def filter_events_by_date_range(self):
        """Filter events to next 4 weeks only"""
        print(f"\n📅 Filtering events to next 4 weeks...")
        
        now = datetime.now(self.pacific_tz)
        four_weeks_later = now + timedelta(weeks=4)
        
        original_count = len(self.events)
        self.events = [event for event in self.events if now <= event['datetime'] <= four_weeks_later]
        
        print(f"✅ Kept {len(self.events)} events (filtered out {original_count - len(self.events)})")
        
        # Show filtered events
        for event in sorted(self.events, key=lambda x: x['datetime']):
            print(f"   📅 {event['datetime'].strftime('%a %m/%d %I:%M %p')} - {event['name']}")
    
    def generate_ics_calendar(self):
        """Generate ICS calendar file and commit to GitHub"""
        print(f"\n📄 Generating calendar.ics...")
        
        cal = Calendar()
        cal.add('prodid', '-//Strava Club Events//mxm.dk//')
        cal.add('version', '2.0')
        cal.add('calscale', 'GREGORIAN')
        cal.add('method', 'PUBLISH')
        cal.add('X-WR-CALNAME', 'Strava Club Events')
        cal.add('X-WR-TIMEZONE', 'America/Los_Angeles')
        
        for event_data in self.events:
            event = Event()
            event.add('summary', event_data['name'])
            event.add('dtstart', event_data['datetime'])
            event.add('dtend', event_data['datetime'] + timedelta(minutes=30))
            event.add('description', f"Strava Event: {event_data['url']}\nRide starts at: {event_data['original_time'].strftime('%I:%M %p')}")
            event.add('url', event_data['url'])
            event.add('uid', f"{event_data['url'].split('/')[-1]}@strava-scraper")
            event.add('dtstamp', datetime.now(pytz.UTC))
            
            cal.add_component(event)
        
        # Ensure docs directory exists
        os.makedirs('docs', exist_ok=True)
        
        # Write to file in docs directory
        calendar_path = os.path.join('docs', 'calendar.ics')
        with open(calendar_path, 'wb') as f:
            f.write(cal.to_ical())
            
        print(f"✅ Generated calendar.ics with {len(self.events)} events")
        print(f"📍 File location: {os.path.abspath(calendar_path)}")
        print(f"🌐 Will be available at: https://defeomike.github.io/strava-club-ride-calendar/calendar.ics")
        
        # Commit and push changes
        try:
            import subprocess
            print("\n📤 Committing and pushing changes to GitHub...")
            
            # Add the calendar file
            subprocess.run(['git', 'add', calendar_path], check=True)
            
            # Get current date for commit message
            date_str = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            # Commit with timestamp
            subprocess.run(['git', 'commit', '-m', f'Update calendar with latest events ({date_str})'], check=True)
            
            # Push to GitHub
            subprocess.run(['git', 'push'], check=True)
            
            print("✅ Successfully updated calendar on GitHub")
            
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Failed to update GitHub: {str(e)}")
            print("💡 You can manually commit and push the changes later")
        except Exception as e:
            print(f"⚠️  Unexpected error updating GitHub: {str(e)}")
            print("💡 You can manually commit and push the changes later")
    
    def run(self):
        """Main execution flow"""
        print("🚀 Starting Strava Club Events Scraper")
        print("=" * 50)
        
        try:
            # Load configuration
            if not self.load_config():
                return False
            
            # Setup browser
            self.setup_driver()
            
            # Login to Strava
            if not self.login_to_strava():
                return False
            
            # Load club URLs
            club_urls = self.load_club_urls()
            if not club_urls:
                return False
            
            # Scrape each club
            for club_url in club_urls:
                club_events = self.scrape_club_events(club_url)
                self.events.extend(club_events)
                time.sleep(2)  # Brief pause between clubs
            
            # Filter events by date range
            self.filter_events_by_date_range()
            
            # Generate calendar
            if self.events:
                self.generate_ics_calendar()
                print("\n🎉 Scraping completed successfully!")
                print(f"📊 Total events: {len(self.events)}")
                print("💡 You can now commit calendar.ics to GitHub")
            else:
                print("\n⚠️  No events found to add to calendar")
            
            return True
            
        except Exception as e:
            print(f"\n❌ Unexpected error: {str(e)}")
            return False
            
        finally:
            if self.driver:
                print("\n🔒 Closing browser...")
                self.driver.quit()

def main():
    scraper = StravaEventScraper()
    success = scraper.run()
    
    if not success:
        print("\n💡 Common issues:")
        print("   - Check config.ini has correct Strava credentials")
        print("   - Ensure clubs.txt exists with valid club URLs")
        print("   - Try running again if login failed")
        exit(1)

if __name__ == "__main__":
    main()