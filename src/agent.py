import re
import time
from colorama import Fore, init
from litellm import completion
from litellm.exceptions import RateLimitError

# Initialize colorama for colored terminal output
init(autoreset=True)


class Agent:
    def __init__(self, name, model, system_prompt="", temperature=0.1):
        self.name = name
        self.model = model
        self.temperature = temperature
        self.system_prompt = system_prompt

    def invoke(self, message, max_retries=5):
        print(Fore.GREEN + f"\nCalling Agent: {self.name}")
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": message}
        ]
        for attempt in range(max_retries):
            try:
                response = completion(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                )
                return response.choices[0].message.content
            except RateLimitError as e:
                if attempt == max_retries - 1:
                    raise
                # Parse the suggested wait time from the error, default to 60s
                match = re.search(r'try again in (\d+(?:\.\d+)?)s', str(e))
                wait = float(match.group(1)) + 2 if match else 60
                print(Fore.YELLOW + f"Rate limited. Waiting {wait:.0f}s before retry ({attempt + 1}/{max_retries - 1})...")
                time.sleep(wait)
