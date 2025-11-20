# examinor/services/rubric_store.py
# Official PTE-compatible rubric store for testing

RUBRICS = {

    # ------------------------------------------------------------
    # 1. Summarize Written Text (SWT)
    # ------------------------------------------------------------
    "summarize_written_text": {
        "rubric_version": 1,
        "communicative_skills": ["reading", "writing"],
        "criteria": [
            {
                "id": "content",
                "max": 4,
                "desc": "Accuracy, completeness, synthesis of main ideas"
            },
            {
                "id": "form",
                "max": 1,
                "desc": "One sentence, 5–75 words, not all caps"
            },
            {
                "id": "grammar",
                "max": 2,
                "desc": "Correct grammatical structure"
            },
            {
                "id": "vocabulary",
                "max": 2,
                "desc": "Appropriate and precise vocabulary"
            }
        ]
    },

    # ------------------------------------------------------------
    # 2. Write Essay
    # ------------------------------------------------------------
    "write_essay": {
        "rubric_version": 1,
        "communicative_skills": ["writing"],
        "criteria": [
            {
                "id": "content",
                "max": 3,
                "desc": "Relevance, development, and logical organization"
            },
            {
                "id": "development_structure_coherence",
                "max": 3,
                "desc": "Paragraphing, logical flow, linking devices"
            },
            {
                "id": "grammar",
                "max": 2,
                "desc": "Accuracy and complexity of grammar usage"
            },
            {
                "id": "general_linguistic_range",
                "max": 2,
                "desc": "Vocabulary variety and appropriateness"
            },
            {
                "id": "spelling",
                "max": 2,
                "desc": "Correct spelling"
            }
        ]
    },

    # ------------------------------------------------------------
    # 3. Reorder Paragraphs (Reading)
    # ------------------------------------------------------------
    "reorder_paragraphs": {
    "rubric_version": 1,
    "communicative_skills": ["reading"],
    "criteria": [
        {
            "id": "adjacent_pairs",
            "max": 1,
            "desc": "Each correctly ordered adjacent pair = +1 point."
        }
    ],
    "scoring_notes": {
        "explanation": "Score equals number of correct adjacent pairs in candidate response.",
        "example": {
            "correct_order": ["A", "B", "C", "D"],
            "candidate_answer": ["A", "C", "B", "D"],
            "adjacent_pairs": 0
        }
    }
},

    # ------------------------------------------------------------
    # 4. Fill in the Blanks — Reading
    # ------------------------------------------------------------
    "fib_dropdown": {
        "rubric_version": 1,
        "communicative_skills": ["reading"],
        "criteria": [
            {
                "id": "correct_blanks",
                "max": 1,
                "desc": "Each correctly completed blank = +1 point (Dropdown)."
            }
        ],
        "scoring_notes": {
            "rule": "Score 1 for each correct dropdown selection. No penalties.",
            "typical_blanks": "5–6",
            "example": {
                "correct_answers": ["A", "C", "D", "B", "A"],
                "candidate": ["A", "C", "X", "B", "A"],
                "score": 4
            }
        }
    },
    "fib_drag_drop": {
        "rubric_version": 1,
        "communicative_skills": ["reading"],
        "criteria": [
            {
                "id": "correct_blanks",
                "max": 1,
                "desc": "Each correctly placed word = +1 point (Drag & Drop)."
            }
        ],
        "scoring_notes": {
            "rule": "Score 1 for each correctly placed word. No penalties.",
            "typical_blanks": "4–5",
            "example": {
                "correct_answers": ["word1", "word2", "word3", "word4"],
                "candidate": ["word1", "word2", "wrong", "word4"],
                "score": 3
            }
        }
    },


    # ------------------------------------------------------------
    # 5. MCQ — Single Answer (Reading/Listening)
    # ------------------------------------------------------------
        "mc_single": {
        "rubric_version": 1,
        "communicative_skills": ["reading"],
        "criteria": [
            {
                "id": "correct_option",
                "max": 1,
                "desc": "1 point if the selected option is correct, else 0."
            }
        ],
        "scoring_notes": {
            "rule": "Full point only if the chosen option matches the correct answer.",
            "example": {
                "correct_answer": "C",
                "candidate": "A",
                "score": 0
            }
        }
    },


    # ------------------------------------------------------------
    # 6. MCQ — Multiple Answers
    # ------------------------------------------------------------
    "mc_multiple": {
        "rubric_version": 1,
        "communicative_skills": ["reading"],
        "criteria": [
            {
                "id": "multiple_select_scoring",
                "max": 1,
                "desc": "+1 for each correct option selected; -1 for each incorrect option selected; floor at 0."
            }
        ],
        "scoring_notes": {
            "rule": "Score all selected options independently. Sum positive and negative values. Final score cannot be less than 0.",
            "example": {
                "correct_options": ["B", "D"],
                "candidate": ["A", "B", "C"],
                "calculation": "+1 (B) -1 (A) -1 (C) = -1 → final = 0"
            }
        }
    },


    # ------------------------------------------------------------
    # 7. Summarize Spoken Text (SST)
    # ------------------------------------------------------------
     "summarize_spoken_text": {
        "rubric_version": 1,
        "communicative_skills": ["listening", "writing"],
        "criteria": [
            {
                "id": "content",
                "max": 4,
                "desc": "How well the summary captures key ideas, demonstrates comprehension, and synthesizes information without extraneous details."
            },
            {
                "id": "form",
                "max": 2,
                "desc": "50–70 words; written as a single, complete paragraph."
            },
            {
                "id": "grammar",
                "max": 2,
                "desc": "Correct grammatical structures with minimal or no errors."
            },
            {
                "id": "vocabulary",
                "max": 2,
                "desc": "Appropriate word choice with minimal lexical errors."
            },
            {
                "id": "spelling",
                "max": 2,
                "desc": "Correct spelling; 0 for more than one spelling mistake."
            }
        ],
        "scoring_notes": {
            "max_score_total": 12,
            "word_limit": "50–70 words",
            "rule": "Candidate must summarize the audio transcript. Partial credit applies per trait.",
            "official_trait_details": {
                "content": "4 = comprehensive, accurate, synthesized; 0 = no comprehension.",
                "form": "2 = 50–70 words; 1 = 40–49 or 71–100; 0 = <40 or >100 or bullet points/capital letters.",
                "grammar": "2 = correct; 1 = minor errors; 0 = defective structures.",
                "vocabulary": "2 = appropriate; 1 = minor lexical errors; 0 = defective word choice.",
                "spelling": "2 = correct; 1 = one error; 0 = more than one error."
            }
        }
    },
    
    # ------------------------------------------------------------
    # 8. Read Aloud (Speaking)
    # ------------------------------------------------------------
    "read_aloud": {
        "rubric_version": 1,
        "communicative_skills": ["speaking"],
        "criteria": [
            {
                "id": "content",
                "max": 5,
                "desc": "Matching words accurately"
            },
            {
                "id": "pronunciation",
                "max": 5,
                "desc": "Native-like stress, consonants, vowels"
            },
            {
                "id": "fluency",
                "max": 5,
                "desc": "Smooth rhythm, no hesitations"
            }
        ]
    }
}