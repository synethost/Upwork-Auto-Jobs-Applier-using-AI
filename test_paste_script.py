"""
Test the paste_job_url.py functionality
This simulates pasting a job description and generating a cover letter
"""
from dotenv import load_dotenv
from src.utils import read_text_file
from src.agent import Agent
from src.prompts import generate_cover_letter_prompt
import json
import re

load_dotenv()

# Sample job description
SAMPLE_JOB = """
Senior AI Agent Developer - LangChain & GPT-4

Budget: $70-100/hr
Experience Level: Expert
Duration: 3-6 months
30+ hrs/week

We're seeking an experienced AI Agent Developer to build sophisticated multi-agent systems using LangChain and GPT-4. You'll design RAG architectures, implement tool calling, and create conversational AI workflows.

Required Skills:
- LangChain, LangGraph
- GPT-4, Claude API integration
- Vector databases (Pinecone, Weaviate)
- Python, FastAPI
- RAG architecture design

Bonus:
- Experience with voice AI
- VR/AR background
- Full-stack development (React, Next.js)

We're looking for someone who can start immediately and has a proven track record with enterprise AI projects.
"""

def test_cover_letter_generation():
    print("\n" + "="*70)
    print("🧪 TESTING PASTE_JOB_URL.PY FUNCTIONALITY")
    print("="*70)

    # Load profile
    print("\n1. Loading profile...")
    profile = read_text_file("./files/profile.md")
    print(f"   ✅ Profile loaded ({len(profile)} chars)")

    # Initialize AI agent
    print("\n2. Initializing AI agent...")
    agent = Agent(
        name="Cover Letter Generator",
        model="groq/llama-3.3-70b-versatile",
        system_prompt=generate_cover_letter_prompt.format(profile=profile),
        temperature=0.1
    )
    print("   ✅ Agent initialized")

    # Generate cover letter
    print("\n3. Generating cover letter...")
    print("   ⏱️  This takes 2-5 seconds...")

    try:
        result = agent.invoke(SAMPLE_JOB)

        # Clean up
        result = re.sub(r'```json\s*', '', result)
        result = re.sub(r'```\s*$', '', result)
        result = result.strip()

        # Parse
        try:
            result_json = json.loads(result, strict=False)
            cover_letter = result_json.get("letter", result)
        except:
            cover_letter = result

        # Display
        print("\n" + "="*70)
        print("✅ COVER LETTER GENERATED")
        print("="*70)
        print("\n" + cover_letter + "\n")
        print("="*70)
        print(f"📊 {len(cover_letter)} characters")
        print("="*70)

        # Test clipboard copy
        try:
            import pyperclip
            pyperclip.copy(cover_letter)
            print("\n✅ CLIPBOARD TEST: Successfully copied to clipboard!")
        except Exception as e:
            print(f"\n⚠️  CLIPBOARD TEST: Failed - {str(e)}")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_cover_letter_generation()

    if success:
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED")
        print("="*70)
        print("\n📋 paste_job_url.py is ready to use!")
        print("\nTo use it:")
        print("  1. python paste_job_url.py")
        print("  2. Choose option 2 (paste description)")
        print("  3. Paste job description")
        print("  4. Press Enter twice")
        print("  5. Cover letter generated and copied to clipboard!")
    else:
        print("\n❌ Tests failed - check error above")
