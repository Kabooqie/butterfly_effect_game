# app.py

import os
import random
import re
import time
import json  # Import the json library
from flask import Flask, render_template, request, jsonify, session
import google.generativeai as genai

# --- SETUP ---
app = Flask(__name__)
app.secret_key = 'a_final_very_secret_key_for_a_perfect_game'

try:
    genai.configure(api_key="AIzaSyBizbSN3GVQU_0FbpLT_ZNwvfCkZnlei8Q")
except Exception as e:
    print(f"CRITICAL ERROR: Could not configure Gemini API. Is GOOGLE_API_KEY set? Error: {e}")

# --- AI System Instructions ---
CHAOS_INSTRUCTIONS = "You are a witty, mischievous, and concise 'Chaos Engine' AI. You follow formatting instructions perfectly, especially when asked for JSON."
CHARACTER_ARCHETYPES = ["a grumpy garden gnome", "a three-eyed alien tourist", "a hyper-intelligent squirrel",
                        "a retired pirate captain", "a nervous, newly self-aware robot", "a cheerful grandmother",
                        "a cynical house cat"]
INITIAL_PROMPT_IDEAS = ["finds a mysterious button", "eats the last cookie", "receives a strange message",
                        "sees a bizarrely-colored bird", "fixes a flickering lightbulb"]
STORY_THEMES = ["darkly humorous", "cosmic horror comedy", "trolling/prank", "bureaucratic absurdity",
                "technological breakdown", "social faux pas escalation"]
GAME_LENGTH = 3

model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=CHAOS_INSTRUCTIONS)


# --- NEW: JSON Extractor Function ---
def extract_json_from_string(text):
    """Finds and extracts the first valid JSON object from a string, ignoring surrounding text."""
    try:
        # Find the first '{' and the last '}'
        start_index = text.find('{')
        end_index = text.rfind('}')

        if start_index != -1 and end_index != -1 and end_index > start_index:
            # Slice the string to get just the JSON part
            json_str = text[start_index:end_index + 1]
            return json_str
        else:
            raise ValueError("No valid JSON object found in the AI's response.")
    except Exception as e:
        # Pass the error up if slicing fails for some reason
        raise ValueError(f"Could not extract JSON: {e}")


@app.route('/')
def home():
    """Starts a new game using a two-step AI call for reliability."""
    session.clear()
    session['score'] = 0
    session['turn'] = 0
    session['user_choices'] = []
    session['story_log'] = []

    try:
        random_character = random.choice(CHARACTER_ARCHETYPES)
        random_situation = random.choice(INITIAL_PROMPT_IDEAS)
        random_theme = random.choice(STORY_THEMES)
        session['current_theme'] = random_theme

        # AI Call #1: The Creative Part
        prompt1_story = f"Theme: '{random_theme}'. Character: {random_character}. Situation: {random_situation}. Write a 1-2 sentence story hook ending at a decision point."
        chat = model.start_chat(history=[])
        story_response = chat.send_message(prompt1_story)
        initial_story = story_response.text.strip()

        # AI Call #2: The Logic Part (Requesting JSON)
        prompt2_choices = (
            f"Here is a story: '{initial_story}'. "
            f"Your task is to generate two distinct choices and pick one as the trigger. "
            f"You MUST reply ONLY with a valid JSON object in this exact format: "
            f'{{"choice1": "Text for button 1", "choice2": "Text for button 2", "secret_trigger_is_choice": 1}}'
        )
        choices_response = chat.send_message(prompt2_choices)

        # Using the new, safe JSON extractor
        clean_json_str = extract_json_from_string(choices_response.text)
        parsed_choices = json.loads(clean_json_str)

        session['secret_trigger_choice'] = parsed_choices['choice1'] if parsed_choices[
                                                                            'secret_trigger_is_choice'] == 1 else \
        parsed_choices['choice2']
        session['story_log'].append({'role': 'model', 'parts': [initial_story]})

        return render_template('index.html', initial_story=initial_story, choice1=parsed_choices['choice1'],
                               choice2=parsed_choices['choice2'], score=session.get('score', 0))

    except Exception as e:
        print(f"Error starting new game: {e}")
        error_message = "The AI is being stubborn! It didn't provide a valid story start. Please refresh the page to try again."
        return render_template('index.html', initial_story=error_message, choice1="Refresh", choice2="to Restart",
                               score=0)


@app.route('/generate', methods=['POST'])
def generate():
    story_log = session.get('story_log', [])
    user_choice_text = request.json['choice']
    story_log.append({'role': 'user', 'parts': [f"The user chose: '{user_choice_text}'"]})
    session['user_choices'].append(user_choice_text)
    session['turn'] += 1

    game_over = session['turn'] >= GAME_LENGTH
    current_theme = session.get('current_theme', 'chaotic')

    if game_over:
        prompt = f"Based on the full history and keeping the '{current_theme}' theme, reveal the final chaotic outcome in a single, punchy paragraph."
        chat = model.start_chat(history=story_log)
        response = chat.send_message(prompt)
        story_log.append({'role': 'model', 'parts': [response.text]})
        session['story_log'] = story_log
        return jsonify({'next_part': response.text, 'game_over': True, 'user_choices': session['user_choices']})
    else:
        try:
            prompt = (
                f"Based on the user's last choice and the story so far, continue the story. Adhere to the '{current_theme}' theme. "
                f"You MUST reply ONLY with a valid JSON object in this exact format: "
                f'{{"story": "New story part (1-2 sentences).", "choice1": "Text for button 1", "choice2": "Text for button 2"}}'
            )
            chat = model.start_chat(history=story_log)
            response = chat.send_message(prompt)
            story_log.append({'role': 'model', 'parts': [response.text]})
            session['story_log'] = story_log

            # Using the new, safe JSON extractor
            clean_json_str = extract_json_from_string(response.text)
            parsed_data = json.loads(clean_json_str)

            return jsonify({'next_part': parsed_data['story'], 'choice1': parsed_data['choice1'],
                            'choice2': parsed_data['choice2'], 'game_over': False})
        except Exception as e:
            print(f"Error parsing mid-game AI response: {e}")
            return jsonify({'next_part': "The story's logic collapsed... an error occurred.", 'game_over': True,
                            'user_choices': session['user_choices']})


@app.route('/guess', methods=['POST'])
def guess():
    user_guess = request.json['guess']
    secret_trigger = session.get('secret_trigger_choice', '')
    correct = user_guess.strip().lower() == secret_trigger.strip().lower()

    if correct:
        session['score'] = session.get('score', 0) + 10
        result_text = f"Correct! The crucial choice was indeed '{secret_trigger}'. Your score is now {session['score']}."
    else:
        result_text = f"Sorry, that wasn't it. The real trigger was '{secret_trigger}'. Your score remains {session.get('score', 0)}."

    return jsonify({'result_text': result_text, 'score': session['score']})


if __name__ == '__main__':
    app.run(debug=True)