from django.shortcuts import render
from django.http import JsonResponse

def dummy_pte_data(request):
    # Dummy JSON data (can be any nested structure)
    data = {
        "exam_name": "PTE Mock Test",
        "sections": [
            {
                "id": 1,
                "name": "Speaking & Writing",
                "duration": 77,
                "questions": [
                    {"id": 1, "type": "Read Aloud", "text": "Technology is reshaping education."},
                    {"id": 2, "type": "Repeat Sentence", "text": "Education empowers the future."}
                ]
            },
            {
                "id": 2,
                "name": "Reading",
                "duration": 32,
                "questions": [
                    {"id": 1, "type": "Fill in the blanks", "count": 5},
                    {"id": 2, "type": "Reorder paragraphs", "count": 3}
                ]
            }
        ],
        "total_duration": 109
    }

    return JsonResponse(data)
