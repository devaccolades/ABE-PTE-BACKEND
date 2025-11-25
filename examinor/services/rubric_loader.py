# examinor/services/rubric_loader.py

from mocktest.models import SubSection

def get_rubric(subsection_name: str) -> dict:
    """
    Fetch the rubric JSON stored in the SubSection model.

    Args:
        subsection_name (str): The internal name of the subsection
                               e.g. "read_aloud", "write_essay", "fib_dropdown"

    Returns:
        dict: The rubric JSON stored in the DB (or empty dict if not found)
    """
    try:
        obj = SubSection.objects.get(name=subsection_name)
        return obj.rubric or {}
    except SubSection.DoesNotExist:
        return {}
