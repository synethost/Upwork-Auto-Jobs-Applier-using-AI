import pickle
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import undetected_chromedriver as uc
from colorama import Fore, Style, init
from .utils import _get_chrome_major_version

init(autoreset=True)

UPWORK_LOGIN_URL = "https://www.upwork.com/ab/account-security/login"
SESSION_FILE = "./files/upwork_session.pkl"


class UpworkSubmitter:
    """Logs in to Upwork and submits proposals using a persistent browser session."""

    def __init__(self, email: str, password: str, hourly_rate: str):
        self.email = email
        self.password = password
        self.hourly_rate = hourly_rate
        self.driver = None
        self.answer_agent = None  # optionally set externally for screening questions

    # ------------------------------------------------------------------
    # Driver / session management
    # ------------------------------------------------------------------

    def _init_driver(self):
        chrome_version = _get_chrome_major_version()
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        kwargs = {"options": options}
        if chrome_version:
            kwargs["version_main"] = chrome_version
        self.driver = uc.Chrome(**kwargs)

    def _save_session(self):
        try:
            with open(SESSION_FILE, "wb") as f:
                pickle.dump(self.driver.get_cookies(), f)
        except Exception:
            pass

    def _restore_session(self) -> bool:
        try:
            with open(SESSION_FILE, "rb") as f:
                cookies = pickle.load(f)
            self.driver.get("https://www.upwork.com")
            time.sleep(3)
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
                    pass
            self.driver.refresh()
            time.sleep(4)
            return self._is_logged_in()
        except Exception:
            return False

    def _is_logged_in(self) -> bool:
        try:
            url = self.driver.current_url
            return "login" not in url and "account-security" not in url
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self) -> bool:
        print(Fore.YELLOW + "\nLogging in to Upwork..." + Style.RESET_ALL)
        self._init_driver()

        if self._restore_session():
            print(Fore.GREEN + "Session restored — skipping login.\n" + Style.RESET_ALL)
            return True

        self.driver.get(UPWORK_LOGIN_URL)
        wait = WebDriverWait(self.driver, 20)

        try:
            # Step 1: email
            email_field = wait.until(EC.presence_of_element_located((By.ID, "login_username")))
            email_field.clear()
            email_field.send_keys(self.email)
            self.driver.find_element(By.ID, "login_password_continue").click()
            time.sleep(3)

            # Step 2: password
            password_field = wait.until(EC.presence_of_element_located((By.ID, "login_password")))
            password_field.clear()
            password_field.send_keys(self.password)
            self.driver.find_element(By.ID, "login_control_continue").click()
            time.sleep(5)

            # Step 3: 2FA (if triggered)
            if "security" in self.driver.current_url or "verification" in self.driver.current_url:
                code = input(Fore.CYAN + "Enter 2FA code from your authenticator: " + Style.RESET_ALL).strip()
                otp_field = self.driver.find_element(
                    By.CSS_SELECTOR, 'input[name="deviceAuthOtp"], input[type="text"]'
                )
                otp_field.send_keys(code)
                self.driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
                time.sleep(5)

            if self._is_logged_in():
                self._save_session()
                print(Fore.GREEN + "Upwork login successful.\n" + Style.RESET_ALL)
                return True

            print(Fore.RED + "Login failed — check UPWORK_EMAIL and UPWORK_PASSWORD in .env\n" + Style.RESET_ALL)
            return False

        except Exception as e:
            print(Fore.RED + f"Login error: {e}\n" + Style.RESET_ALL)
            return False

    # ------------------------------------------------------------------
    # Proposal submission
    # ------------------------------------------------------------------

    def submit_proposal(self, job_url: str, cover_letter: str, job_description: str = "") -> bool:
        if not job_url:
            return False

        print(Fore.YELLOW + f"Submitting proposal to: {job_url[:80]}..." + Style.RESET_ALL)
        wait = WebDriverWait(self.driver, 20)

        try:
            self.driver.get(job_url)
            time.sleep(5)

            # --- Apply button ---
            apply_btn = None
            for selector in [
                '[data-test="apply-button"]',
                'a[href*="/proposals/"]',
                'button[data-qa="btn-apply"]',
                'button[aria-label*="Apply"]',
            ]:
                try:
                    apply_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                    break
                except TimeoutException:
                    continue

            if not apply_btn:
                print(Fore.RED + "Apply button not found — job may be closed or already applied.\n" + Style.RESET_ALL)
                return False

            apply_btn.click()
            time.sleep(5)

            # --- Cover letter field ---
            cover_field = None
            for selector in [
                'textarea[data-test="cover-letter"]',
                'textarea[id*="cover"]',
                'textarea[name*="cover"]',
                'textarea[placeholder*="cover"]',
                'textarea',
            ]:
                try:
                    cover_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    break
                except TimeoutException:
                    continue

            if not cover_field:
                print(Fore.RED + "Cover letter field not found.\n" + Style.RESET_ALL)
                return False

            cover_field.clear()
            cover_field.send_keys(cover_letter)
            time.sleep(1)

            # --- Hourly rate (skip for fixed-price jobs) ---
            try:
                rate_field = self.driver.find_element(
                    By.CSS_SELECTOR,
                    'input[id*="rate"], input[name*="rate"], input[placeholder*="/hr"]',
                )
                rate_field.clear()
                rate_field.send_keys(str(self.hourly_rate))
                time.sleep(1)
            except NoSuchElementException:
                pass

            # --- Screening questions ---
            if self.answer_agent and job_description:
                self._answer_screening_questions(job_description)

            # --- Submit ---
            submit_btn = None
            for selector in [
                'button[data-test="submit-proposal"]',
                'button[data-qa="btn-submit-proposal"]',
                'button[aria-label*="Submit"]',
                'button[type="submit"]',
            ]:
                try:
                    submit_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except NoSuchElementException:
                    continue

            if not submit_btn:
                print(Fore.RED + "Submit button not found.\n" + Style.RESET_ALL)
                return False

            submit_btn.click()
            time.sleep(5)
            self._save_session()
            print(Fore.GREEN + "Proposal submitted!\n" + Style.RESET_ALL)
            return True

        except Exception as e:
            print(Fore.RED + f"Submission error: {e}\n" + Style.RESET_ALL)
            return False

    def _answer_screening_questions(self, job_description: str):
        """Use the answer agent to fill any screening question textareas."""
        try:
            q_fields = self.driver.find_elements(
                By.CSS_SELECTOR,
                'textarea[id*="question"], textarea[data-test*="question"]',
            )
            for field in q_fields:
                label_text = ""
                try:
                    fid = field.get_attribute("id")
                    label_el = self.driver.find_element(By.CSS_SELECTOR, f'label[for="{fid}"]')
                    label_text = label_el.text.strip()
                except Exception:
                    pass
                if not label_text:
                    continue
                prompt = (
                    f"Job description:\n{job_description}\n\n"
                    f"Screening question: {label_text}\n\n"
                    "Write a concise, confident answer (2-3 sentences) as Christopher."
                )
                answer = self.answer_agent.invoke(prompt)
                field.clear()
                field.send_keys(answer)
                time.sleep(1)
        except Exception:
            pass

    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
