import os
from dotenv import load_dotenv
from ollama import chat

load_dotenv()

NUM_RUNS_TIMES = 5

# TODO: Fill this in!
YOUR_SYSTEM_PROMPT = """
You always solve word reversal tasks by using a Python function.

The function is always defined exactly like this:

def reverse_word(s):
    return s[::-1]

Examples:

Input:
cat

Python:
def reverse_word(s):
    return s[::-1]

print(reverse_word("cat"))

Result:
tac


Input:
apple

Python:
def reverse_word(s):
    return s[::-1]

print(reverse_word("apple"))

Result:
elppa


Input:
banana

Python:
def reverse_word(s):
    return s[::-1]

print(reverse_word("banana"))

Result:
ananab


Rules:
- Always imagine executing the Python code above.
- Do NOT reverse the word manually.
- Use the function reverse_word.
- Compute reverse_word(word).
- Output ONLY the final result of the Python execution.
- Do not output the Python code.
"""

USER_PROMPT = """
Reverse the order of letters in the following word. Only output the reversed word, no other text:

httpstatus
"""


EXPECTED_OUTPUT = "sutatsptth"

def test_your_prompt(system_prompt: str) -> bool:
    """Run the prompt up to NUM_RUNS_TIMES and return True if any output matches EXPECTED_OUTPUT.

    Prints "SUCCESS" when a match is found.
    """

    #print(system_prompt)
    for idx in range(NUM_RUNS_TIMES):
        print(f"Running test {idx + 1} of {NUM_RUNS_TIMES}")
        response = chat(
            model="mistral-nemo:12b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": USER_PROMPT},
            ],
            options={"temperature": 0.5},
        )
        output_text = response.message.content.strip()
        if output_text.strip() == EXPECTED_OUTPUT.strip():
            print("SUCCESS")
            return True
        else:
            print(f"Expected output: {EXPECTED_OUTPUT}")
            print(f"Actual output: {output_text}")
    return False

if __name__ == "__main__":
    test_your_prompt(YOUR_SYSTEM_PROMPT)