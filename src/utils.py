import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

def read_text_file(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        lines = file.readlines()
        lines = [line.strip() for line in lines if line.strip()]
        return "".join(lines)

def scrape_upwork_data(search_query, num_jobs):
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = uc.Chrome(options=options, version_main=148)

    job_listings = []

    try:
        url = f'https://www.upwork.com/nx/search/jobs?q={search_query}&sort=recency&page=1&per_page={num_jobs}'
        driver.get(url)

        # Wait longer for Cloudflare challenge to clear
        time.sleep(10)

        # Try current and fallback selectors for job tiles
        jobs = driver.find_elements(By.CSS_SELECTOR, 'article[data-test="JobTile"]')
        if not jobs:
            jobs = driver.find_elements(By.CSS_SELECTOR, 'article.job-tile')

        for job in jobs:
            try:
                title_element = job.find_element(By.CSS_SELECTOR, 'h2.job-tile-title > a')
                title = title_element.text.strip()
                link = title_element.get_attribute('href')

                try:
                    description = job.find_element(By.CSS_SELECTOR, 'div[data-test="JobTileDetails"] > div > div > p').text.strip()
                except Exception:
                    description = job.find_element(By.CSS_SELECTOR, 'p').text.strip()

                job_info = job.find_element(By.CSS_SELECTOR, 'ul.job-tile-info-list')

                try:
                    job_type = job_info.find_element(By.CSS_SELECTOR, 'li[data-test="job-type-label"]').text.strip()
                except Exception:
                    job_type = "N/A"

                try:
                    experience_level = job_info.find_element(By.CSS_SELECTOR, 'li[data-test="experience-level"]').text.strip()
                except Exception:
                    experience_level = "N/A"

                try:
                    budget = job_info.find_element(By.CSS_SELECTOR, 'li[data-test="is-fixed-price"]').text.strip()
                except Exception:
                    try:
                        budget = job_info.find_element(By.CSS_SELECTOR, 'li[data-test="duration-label"]').text.strip()
                    except Exception:
                        budget = "N/A"

                job_listings.append({
                    'title': title,
                    'link': link,
                    'description': description,
                    'job_type': job_type,
                    'experience_level': experience_level,
                    'budget': budget
                })
            except Exception as e:
                print(f'Error parsing job listing: {e}')
                continue

    finally:
        driver.quit()

    return job_listings

def save_jobs_to_file(job_listings, filename):
    with open(filename, 'w', encoding='utf-8') as file:
        for job in job_listings:
            file.write(f"Title: {job['title']}\n")
            file.write(f"Link: {job['link']}\n")
            file.write(f"Description: {job['description']}\n")
            file.write(f"Job Type: {job['job_type']}\n")
            file.write(f"Experience Level: {job['experience_level']}\n")
            file.write(f"Budget: {job['budget']}\n")
            file.write("\n---\n\n")