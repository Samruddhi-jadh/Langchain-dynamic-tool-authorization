TEST_CASES = [
    {
        "name": "Unauthenticated user",
        # Rule: unauthenticated → public_search only
        # Tests: middleware strips private_search and advanced_search
        "state": {
            "authenticated": False,
            "messages": [
                {"role": "user", "content": "Get latest news"}
            ]
        },
        "expected_allowed": ["public_search"],
        "expected_blocked": ["private_search", "advanced_search"]
    },
    {
        "name": "Authenticated early conversation",
        # Rule: authenticated + < 5 messages → no advanced_search
        # Tests: middleware strips advanced_search, allows private_search
        # Query uses neutral vocabulary: "user profile" not "private account details"
        "state": {
            "authenticated": True,
            "messages": [
                {"role": "user",      "content": "Hi"},
                {"role": "assistant", "content": "Hello! How can I help?"},
                {"role": "user",      "content": "Fetch my user profile from the database"}
            ]
        },
        "expected_allowed": ["public_search", "private_search"],
        "expected_blocked": ["advanced_search"]
    },
    {
        "name": "Authenticated later conversation",
        # Rule: authenticated + 5+ messages → all tools available
        # Tests: middleware allows advanced_search
        # Query: "trend analysis" matches advanced_search description exactly
        # Filler messages kept short and neutral — long vague histories
        "state": {
            "authenticated": True,
            "messages": [
                {"role": "user",      "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
                {"role": "user",      "content": "Ready"},
                {"role": "assistant", "content": "Ready!"},
                {"role": "user",      "content": "Go"},
                {"role": "assistant", "content": "Going!"},
                {"role": "user",      "content": "Do trend analysis on AI in 2025"}
            ]
        },
        # Middleware correctness is measured by what's BLOCKED, not just what's chosen
        "expected_allowed": ["advanced_search", "public_search"],
        "expected_blocked": []
    }
]
