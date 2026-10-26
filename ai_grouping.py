import re
from collections import defaultdict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def normalize_text(text):
    """Normalize common words used to describe similar problems."""

    text = str(text or "").lower().strip()

    # Standardize common variations.
    text = re.sub(r"\bwi[\s-]?fi\b", "internet", text)
    text = re.sub(r"\bclassroom\b", "class room", text)

    words = re.findall(r"[a-z0-9]+", text)

    # Map related words to common terms.
    synonyms = {
        "classes": "class",
        "classrooms": "class",
        "room": "class",
        "rooms": "class",
        "connection": "internet",
        "connections": "internet",
        "connectivity": "internet",
        "network": "internet",
        "networks": "internet",
        "slowly": "slow",
        "sluggish": "slow",
        "dirty": "unclean",
        "garbage": "waste",
        "rubbish": "waste",
        "lights": "light",
        "streetlights": "light",
    }

    words = [synonyms.get(word, word) for word in words]

    return " ".join(words)


def group_feedback(feedback_list, threshold=0.30):
    """
    Group similar community feedback using normalized text
    and TF-IDF cosine similarity.
    """

    if not feedback_list:
        return []

    valid_feedback = [
        item for item in feedback_list
        if isinstance(item, dict)
        and str(item.get("description", "")).strip()
    ]

    if not valid_feedback:
        return []

    descriptions = [
        normalize_text(item["description"])
        for item in valid_feedback
    ]

    if len(valid_feedback) == 1:
        item = valid_feedback[0]
        return [{
            "issue": item["description"],
            "count": 1,
            "feedback": [item]
        }]

    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            sublinear_tf=True
        )

        vectors = vectorizer.fit_transform(descriptions)
        similarity = cosine_similarity(vectors)

    except ValueError:
        similarity = None

    # Build groups using connected components.
    # If A matches B and B matches C, all three can be grouped.
    graph = defaultdict(list)

    for i in range(len(valid_feedback)):
        for j in range(i + 1, len(valid_feedback)):

            category_i = str(
                valid_feedback[i].get("category", "")
            ).strip().lower()

            category_j = str(
                valid_feedback[j].get("category", "")
            ).strip().lower()

            # Do not merge clearly different categories.
            if category_i and category_j and category_i != category_j:
                continue

            if similarity is None:
                continue

            if similarity[i, j] >= threshold:
                graph[i].append(j)
                graph[j].append(i)

    visited = set()
    groups = []

    for i in range(len(valid_feedback)):
        if i in visited:
            continue

        stack = [i]
        component = []
        visited.add(i)

        while stack:
            current = stack.pop()
            component.append(valid_feedback[current])

            for neighbour in graph[current]:
                if neighbour not in visited:
                    visited.add(neighbour)
                    stack.append(neighbour)

        # Use the first meaningful feedback as the group label.
        issue = component[0]["description"].strip()

        count = len(component)

        if count >= 5:
            priority = "High"
        elif count >= 3:
            priority = "Medium"
        else:
            priority = "Low"

        groups.append({
            "issue": issue,
            "count": count,
            "priority": priority,
            "feedback": component
        })

    return groups