import json
import os
import re
import time
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict
from typing import List
from colorama import Fore, Style
from .agent import Agent
from .notifier import send_run_summary
from .stats_tracker import record_run
from .submitter import UpworkSubmitter
from .utils import scrape_upwork_data, save_jobs_to_file
from .prompts import classify_jobs_prompt, generate_cover_letter_prompt

SCRAPED_JOBS_FILE = "./files/upwork_job_listings.txt"
COVER_LETTERS_FILE = "./files/cover_letter.txt"
APPLIED_JOBS_FILE = "./files/applied_jobs.json"


class GraphState(TypedDict):
    job_title: str
    scraped_jobs_list: str
    matches: List[dict]
    job_description: str
    cover_letter: str
    num_matches: int


def _load_applied_jobs() -> set:
    try:
        with open(APPLIED_JOBS_FILE, 'r') as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def _mark_job_applied(link: str):
    applied = _load_applied_jobs()
    applied.add(link)
    with open(APPLIED_JOBS_FILE, 'w') as f:
        json.dump(sorted(applied), f, indent=2)


def _extract_title(job_text: str) -> str:
    """Pull the title out of a scraped job string."""
    for line in job_text.split('\n'):
        if 'title' in line.lower():
            return line.split(':', 1)[-1].strip().strip("'\"")[:70]
    return job_text[:70]


class UpworkAutomationGraph:
    def __init__(self, profile, num_jobs=10):
        self.profile = profile
        self.number_of_jobs = num_jobs
        self.submitter = None
        self.review_mode = os.getenv("REVIEW_BEFORE_SUBMIT", "").lower() == "true"

        # Per-run accumulators (reset in run())
        self._run_job_title = ""
        self._run_scraped_count = 0
        self._run_applied: List[dict] = []

        self.init_agents()
        self.graph = self.build_graph()

        if os.getenv("AUTO_SUBMIT", "").lower() == "true":
            self.submitter = UpworkSubmitter(
                email=os.getenv("UPWORK_EMAIL", ""),
                password=os.getenv("UPWORK_PASSWORD", ""),
                hourly_rate=os.getenv("UPWORK_HOURLY_RATE", "85"),
            )
            self.submitter.answer_agent = Agent(
                name="Screening Answerer",
                model="groq/llama-3.3-70b-versatile",
                system_prompt=(
                    "You are Christopher, an expert AI and full-stack developer answering "
                    "screening questions for Upwork proposals. Be concise and professional.\n\n"
                    f"<profile>{self.profile}</profile>"
                ),
                temperature=0.1,
            )

    # ------------------------------------------------------------------
    # Graph nodes
    # ------------------------------------------------------------------

    def scrape_upwork_jobs(self, state):
        job_title = state["job_title"]
        print(
            Fore.YELLOW
            + f"----- Scraping Upwork jobs for: {job_title} -----\n"
            + Style.RESET_ALL
        )

        job_listings = []
        for attempt in range(3):
            job_listings = scrape_upwork_data(job_title, self.number_of_jobs)
            if job_listings:
                break
            if attempt < 2:
                print(
                    Fore.YELLOW
                    + f"No jobs scraped, retrying in 15s... ({attempt + 1}/2)\n"
                    + Style.RESET_ALL
                )
                time.sleep(15)

        self._run_scraped_count = len(job_listings)
        print(
            Fore.GREEN
            + f"----- Scraped {len(job_listings)} jobs -----\n"
            + Style.RESET_ALL
        )
        save_jobs_to_file(job_listings, SCRAPED_JOBS_FILE)
        return {**state, "scraped_jobs_list": "\n".join(map(str, job_listings))}

    def classify_scraped_jobs(self, state):
        print(Fore.YELLOW + "----- Classifying scraped jobs -----\n" + Style.RESET_ALL)
        scraped_jobs = state["scraped_jobs_list"]

        if not scraped_jobs.strip():
            print(Fore.RED + "No jobs scraped — skipping classification.\n" + Style.RESET_ALL)
            return {**state, "matches": []}

        classify_result = self.classify_jobs_agent.invoke(scraped_jobs)
        classify_result = re.sub(r'```json\s*', '', classify_result)
        classify_result = re.sub(r'```\s*$', '', classify_result).strip()

        matches = json.loads(classify_result, strict=False)["matches"]

        # Remove already-applied jobs
        applied_jobs = _load_applied_jobs()
        before = len(matches)
        matches = [m for m in matches if m.get('link', '') not in applied_jobs]
        skipped = before - len(matches)
        if skipped:
            print(Fore.CYAN + f"Skipped {skipped} already-applied job(s).\n" + Style.RESET_ALL)

        # Sort by score descending
        matches.sort(key=lambda m: m.get('score', 0), reverse=True)

        if matches:
            print(Fore.GREEN + "Ranked matches:" + Style.RESET_ALL)
            for i, m in enumerate(matches, 1):
                score = m.get('score', '?')
                title = m.get('job', '')[:60].replace('\n', ' ')
                print(Fore.CYAN + f"  {i}. Score {score}/10 — {title}..." + Style.RESET_ALL)
            print()

        return {**state, "matches": matches}

    def check_for_job_matches(self, state):
        print(
            Fore.YELLOW
            + "----- Checking for remaining job matches -----\n"
            + Style.RESET_ALL
        )
        return {**state, "num_matchs": len(state["matches"])}

    def need_to_process_matches(self, state):
        if len(state["matches"]) == 0:
            print(Fore.RED + "No job matches\n" + Style.RESET_ALL)
            return "No matches"
        print(
            Fore.GREEN
            + f"There are {len(state['matches'])} Job matches to process\n"
            + Style.RESET_ALL
        )
        return "Process jobs"

    def generate_cover_letter(self, state):
        print(Fore.YELLOW + "----- Generating cover letter -----\n" + Style.RESET_ALL)
        match = state["matches"][-1]

        job_input = (
            f"JOB LISTING:\n{match['job']}\n\n"
            f"MATCH SCORE: {match.get('score', 'N/A')}/10\n"
            f"WHY THIS IS A STRONG MATCH: {match.get('reason', '')}"
        )

        cover_letter_result = self.generate_cover_letter_agent.invoke(job_input)
        cover_letter_result = re.sub(r'```json\s*', '', cover_letter_result)
        cover_letter_result = re.sub(r'```\s*$', '', cover_letter_result).strip()

        cover_letter = json.loads(cover_letter_result, strict=False)["letter"]
        return {**state, "cover_letter": cover_letter, "job_description": match['job']}

    def save_cover_letter(self, state):
        print(Fore.YELLOW + "----- Saving cover letter -----\n" + Style.RESET_ALL)
        match = state["matches"][-1]
        link = match.get('link', '')
        score = match.get('score', '?')

        # Save to file
        with open(COVER_LETTERS_FILE, "a") as f:
            f.write(f"Score: {score}/10\n")
            f.write(state["cover_letter"] + f'\n{"-" * 70}\n')

        if link:
            _mark_job_applied(link)
            print(Fore.CYAN + f"Marked as applied: {link}\n" + Style.RESET_ALL)

        # Review/approval mode
        submitted = False
        should_submit = True

        if self.review_mode and self.submitter:
            print(Fore.BLUE + "=" * 60 + Style.RESET_ALL)
            print(Fore.BLUE + "COVER LETTER PREVIEW:" + Style.RESET_ALL)
            print(state["cover_letter"])
            print(Fore.BLUE + "=" * 60 + Style.RESET_ALL)

            answer = input(
                Fore.YELLOW + "Submit this proposal? [y]es / [n]o / [q]uit auto-submit: " + Style.RESET_ALL
            ).strip().lower()

            if answer == 'q':
                print(Fore.YELLOW + "Auto-submit disabled for remaining jobs.\n" + Style.RESET_ALL)
                self.submitter = None
                should_submit = False
            elif answer != 'y':
                print(Fore.YELLOW + "Skipped — letter saved locally.\n" + Style.RESET_ALL)
                should_submit = False

        # Auto-submit
        if self.submitter and link and should_submit:
            submitted = self.submitter.submit_proposal(
                job_url=link,
                cover_letter=state["cover_letter"],
                job_description=match.get("job", ""),
            )
            if not submitted:
                print(Fore.YELLOW + "Auto-submit failed — letter saved locally.\n" + Style.RESET_ALL)

        # Accumulate stats for this run
        self._run_applied.append({
            "title": _extract_title(match.get("job", "")),
            "link": link,
            "score": score,
            "submitted": submitted,
        })

        state["matches"].pop()
        return {**state, "matches": state["matches"]}

    # ------------------------------------------------------------------
    # Agent / graph setup
    # ------------------------------------------------------------------

    def init_agents(self):
        self.classify_jobs_agent = Agent(
            name="Job Classifier Agent",
            model="groq/llama-3.3-70b-versatile",
            system_prompt=classify_jobs_prompt.format(profile=self.profile),
            temperature=0.1,
        )
        self.generate_cover_letter_agent = Agent(
            name="Writer Agent",
            model="groq/llama-3.3-70b-versatile",
            system_prompt=generate_cover_letter_prompt.format(profile=self.profile),
            temperature=0.1,
        )

    def build_graph(self):
        graph = StateGraph(GraphState)

        graph.add_node("scrape_upwork_jobs", self.scrape_upwork_jobs)
        graph.add_node("classify_scraped_jobs", self.classify_scraped_jobs)
        graph.add_node("check_for_job_matches", self.check_for_job_matches)
        graph.add_node("generate_cover_letter", self.generate_cover_letter)
        graph.add_node("save_cover_letter", self.save_cover_letter)

        graph.set_entry_point("scrape_upwork_jobs")
        graph.add_edge("scrape_upwork_jobs", "classify_scraped_jobs")
        graph.add_edge("classify_scraped_jobs", "check_for_job_matches")
        graph.add_conditional_edges(
            "check_for_job_matches",
            self.need_to_process_matches,
            {"Process jobs": "generate_cover_letter", "No matches": END},
        )
        graph.add_edge("generate_cover_letter", "save_cover_letter")
        graph.add_edge("save_cover_letter", "check_for_job_matches")

        return graph.compile()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, job_title):
        print(Fore.BLUE + "----- Running Upwork Jobs Automation -----\n" + Style.RESET_ALL)

        # Reset per-run accumulators
        self._run_job_title = job_title
        self._run_scraped_count = 0
        self._run_applied = []

        if self.submitter:
            if not self.submitter.login():
                print(Fore.YELLOW + "Disabling auto-submit due to login failure.\n" + Style.RESET_ALL)
                self.submitter = None

        try:
            state = self.graph.invoke({"job_title": job_title})
        finally:
            if self.submitter:
                self.submitter.close()

        # Record stats and send notification
        record_run(
            job_title=self._run_job_title,
            scraped=self._run_scraped_count,
            applied_jobs=self._run_applied,
        )
        send_run_summary(
            job_title=self._run_job_title,
            scraped=self._run_scraped_count,
            applied_jobs=self._run_applied,
        )

        # Print run summary to terminal
        if self._run_applied:
            print(Fore.BLUE + f"\n----- Run complete: applied to {len(self._run_applied)} job(s) -----" + Style.RESET_ALL)
            for j in self._run_applied:
                sub = "submitted" if j["submitted"] else "saved locally"
                print(Fore.CYAN + f"  [{j['score']}/10] {j['title'][:55]} ({sub})" + Style.RESET_ALL)
            print()

        return state
