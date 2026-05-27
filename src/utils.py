import re
import subprocess
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By


def read_text_file(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        lines = file.readlines()
        lines = [line.strip() for line in lines if line.strip()]
        return "".join(lines)


def _get_chrome_major_version():
    """Detect installed Chrome major version so ChromeDriver always matches."""
    paths = [
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Chromium.app/Contents/MacOS/Chromium',
    ]
    for path in paths:
        try:
            out = subprocess.check_output(
                [path, '--version'], stderr=subprocess.DEVNULL
            ).decode()
            match = re.search(r'(\d+)\.', out)
            if match:
                return int(match.group(1))
        except Exception:
            continue
    return None


def scrape_upwork_data(search_query, num_jobs, max_pages=3):
    chrome_version = _get_chrome_major_version()
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    kwargs = {'options': options}
    if chrome_version:
        kwargs['version_main'] = chrome_version

    driver = uc.Chrome(**kwargs)
    job_listings = []
    seen_links = set()

    try:
        for page in range(1, max_pages + 1):
            if len(job_listings) >= num_jobs:
                break

            url = (
                f'https://www.upwork.com/nx/search/jobs'
                f'?q={search_query}&sort=recency&page={page}&per_page=10'
            )
            driver.get(url)
            time.sleep(10)

            jobs = driver.find_elements(By.CSS_SELECTOR, 'article[data-test="JobTile"]')
            if not jobs:
                jobs = driver.find_elements(By.CSS_SELECTOR, 'article.job-tile')

            if not jobs:
                print(f'No jobs found on page {page}, stopping.')
                break

            for job in jobs:
                if len(job_listings) >= num_jobs:
                    break
                try:
                    title_element = job.find_element(By.CSS_SELECTOR, 'h2.job-tile-title > a')
                    title = title_element.text.strip()
                    link = title_element.get_attribute('href')

                    if link in seen_links:
                        continue
                    seen_links.add(link)

                    try:
                        description = job.find_element(
                            By.CSS_SELECTOR,
                            'div[data-test="JobTileDetails"] > div > div > p'
                        ).text.strip()
                    except Exception:
                        description = job.find_element(By.CSS_SELECTOR, 'p').text.strip()

                    job_info = job.find_element(By.CSS_SELECTOR, 'ul.job-tile-info-list')

                    try:
                        job_type = job_info.find_element(
                            By.CSS_SELECTOR, 'li[data-test="job-type-label"]'
                        ).text.strip()
                    except Exception:
                        job_type = "N/A"

                    try:
                        experience_level = job_info.find_element(
                            By.CSS_SELECTOR, 'li[data-test="experience-level"]'
                        ).text.strip()
                    except Exception:
                        experience_level = "N/A"

                    try:
                        budget = job_info.find_element(
                            By.CSS_SELECTOR, 'li[data-test="is-fixed-price"]'
                        ).text.strip()
                    except Exception:
                        try:
                            budget = job_info.find_element(
                                By.CSS_SELECTOR, 'li[data-test="duration-label"]'
                            ).text.strip()
                        except Exception:
                            budget = "N/A"

                    job_listings.append({
                        'title': title,
                        'link': link,
                        'description': description,
                        'job_type': job_type,
                        'experience_level': experience_level,
                        'budget': budget,
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
