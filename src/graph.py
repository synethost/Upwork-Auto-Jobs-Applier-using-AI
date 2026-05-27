import json
import os
import time
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict
from typing import List
from colorama import Fore, Style
from .agent import Agent
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


class UpworkAutomationGraph:
    def __init__(self, profile, num_jobs=10):
        self.profile = profile
        self.number_of_jobs = num_jobs
        self.submitter = None
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

        print(
            Fore.GREEN
            + f"----- Scraped {len(job_listings)} jobs -----\n"
            + Style.RESET_ALL
        )
        save_jobs_to_file(job_listings, SCRAPED_JOBS_FILE)
        job_listings_str = "\n".join(map(str, job_listings))
        return {**state, "scraped_jobs_list": job_listings_str}

    def classify_scraped_jobs(self, state):
        print(Fore.YELLOW + "----- Classifying scraped jobs -----\n" + Style.RESET_ALL)
        scraped_jobs = state["scraped_jobs_list"]

        if not scraped_jobs.strip():
            print(Fore.RED + "No jobs scraped — skipping classification.\n" + Style.RESET_ALL)
            return {**state, "matches": []}

        classify_result = self.classify_jobs_agent.invoke(scraped_jobs)

        import re
        classify_result = re.sub(r'```json\s*', '', classify_result)
        classify_result = re.sub(r'```\s*$', '', classify_result)
        classify_result = classify_result.strip()

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
        count = len(state["matches"])
        return {**state, "num_matchs": count}

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

        import re
        cover_letter_result = re.sub(r'```json\s*', '', cover_letter_result)
        cover_letter_result = re.sub(r'```\s*$', '', cover_letter_result)
        cover_letter_result = cover_letter_result.strip()

        cover_letter = json.loads(cover_letter_result, strict=False)["letter"]
        return {
            **state,
            "cover_letter": cover_letter,
            "job_description": match['job'],
        }

    def save_cover_letter(self, state):
        print(Fore.YELLOW + "----- Saving cover letter -----\n" + Style.RESET_ALL)
        match = state["matches"][-1]

        with open(COVER_LETTERS_FILE, "a") as file:
            score = match.get('score', '?')
            file.write(f"Score: {score}/10\n")
            file.write(state["cover_letter"] + f'\n{"-" * 70}\n')

        link = match.get('link', '')
        if link:
            _mark_job_applied(link)
            print(Fore.CYAN + f"Marked as applied: {link}\n" + Style.RESET_ALL)

        # Auto-submit if enabled
        if self.submitter and link:
            success = self.submitter.submit_proposal(
                job_url=link,
                cover_letter=state["cover_letter"],
                job_description=match.get("job", ""),
            )
            if not success:
                print(Fore.YELLOW + "Auto-submit failed — letter saved locally.\n" + Style.RESET_ALL)

        state["matches"].pop()
        return {**state, "matches": state["matches"]}

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

    def run(self, job_title):
        print(
            Fore.BLUE + "----- Running Upwork Jobs Automation -----\n" + Style.RESET_ALL
        )

        # Login before graph runs so the browser session is ready for submissions
        if self.submitter:
            if not self.submitter.login():
                print(Fore.YELLOW + "Disabling auto-submit due to login failure.\n" + Style.RESET_ALL)
                self.submitter = None

        try:
            state = self.graph.invoke({"job_title": job_title})
        finally:
            if self.submitter:
                self.submitter.close()

        return state
