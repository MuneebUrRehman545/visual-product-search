from google import genai
import os
import re
import time
from dotenv import load_dotenv


load_dotenv()


# ==========================================================
# Gemini Configuration
# ==========================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError(
        "GEMINI_API_KEY is missing from .env"
    )

# Model can now be changed from .env
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash"
)

# Number of retries for temporary API errors
GEMINI_MAX_RETRIES = int(
    os.getenv(
        "GEMINI_MAX_RETRIES",
        "2"
    )
)

# Base delay for retry backoff
GEMINI_RETRY_DELAY = float(
    os.getenv(
        "GEMINI_RETRY_DELAY",
        "2"
    )
)


# ==========================================================
# Gemini Client
# ==========================================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# ==========================================================
# Privacy Protection
# ==========================================================

def redact_sensitive_information(text):
    """
    Redacts sensitive personal and financial information
    before sending content to Gemini and after receiving
    the generated response.
    """

    if not text:
        return text

    # ------------------------------------------------------
    # Pakistani CNIC
    # Example: 12345-1234567-1
    # ------------------------------------------------------

    text = re.sub(
        r"\b\d{5}-\d{7}-\d\b",
        "[REDACTED CNIC]",
        text
    )

    # CNIC without hyphens
    text = re.sub(
        r"\b\d{13}\b",
        "[REDACTED CNIC]",
        text
    )

    # ------------------------------------------------------
    # IBAN
    # ------------------------------------------------------

    text = re.sub(
        r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b",
        "[REDACTED BANK ACCOUNT]",
        text,
        flags=re.IGNORECASE
    )

    # ------------------------------------------------------
    # Long bank/account numbers
    # ------------------------------------------------------

    text = re.sub(
        r"\b\d{14,24}\b",
        "[REDACTED BANK ACCOUNT]",
        text
    )

    # ------------------------------------------------------
    # Pakistani phone numbers
    # ------------------------------------------------------

    text = re.sub(
        r"(?<!\d)(?:\+92|0092|92|0)3\d{9}(?!\d)",
        "[REDACTED PHONE]",
        text
    )

    # ------------------------------------------------------
    # Email addresses
    # ------------------------------------------------------

    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[REDACTED EMAIL]",
        text
    )

    return text


# ==========================================================
# Gemini Error Detection
# ==========================================================

def _is_rate_limit_error(error):
    """
    Detect Gemini 429 / quota / rate-limit errors.
    """

    error_text = str(error).lower()

    return (
        "429" in error_text
        or "resource_exhausted" in error_text
        or "quota exceeded" in error_text
        or "rate limit" in error_text
    )


# ==========================================================
# Gemini Request With Retry
# ==========================================================

def _generate_content(
    prompt,
    operation="generation"
):
    """
    Central Gemini request function.

    Handles temporary rate limits and API failures
    without duplicating retry logic throughout the project.
    """

    last_error = None

    for attempt in range(
        GEMINI_MAX_RETRIES + 1
    ):

        try:

            print(
                f"\nGemini {operation} "
                f"(attempt {attempt + 1}/"
                f"{GEMINI_MAX_RETRIES + 1})"
            )

            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )

            return response

        except Exception as error:

            last_error = error

            print(
                f"Gemini {operation} failed:"
            )

            print(
                type(error).__name__
            )

            print(
                str(error)
            )

            # ------------------------------------------------
            # Rate limit / quota
            # ------------------------------------------------

            if _is_rate_limit_error(error):

                # If this is the final attempt, stop.
                if attempt >= GEMINI_MAX_RETRIES:
                    break

                delay = (
                    GEMINI_RETRY_DELAY
                    * (2 ** attempt)
                )

                print(
                    f"Gemini rate limit detected. "
                    f"Retrying in {delay:.1f} seconds..."
                )

                time.sleep(delay)

                continue

            # ------------------------------------------------
            # Other API errors
            # ------------------------------------------------

            break

    # ======================================================
    # Final failure
    # ======================================================

    if last_error:

        if _is_rate_limit_error(last_error):

            raise RuntimeError(
                "Gemini API quota or rate limit has "
                "been exceeded. Please try again later "
                "or use a Gemini API key/model with "
                "available quota."
            ) from last_error

        raise RuntimeError(
            f"Gemini API error during {operation}: "
            f"{str(last_error)}"
        ) from last_error

    raise RuntimeError(
        f"Gemini {operation} failed."
    )


# ==========================================================
# Rewrite Follow-Up Question
# ==========================================================

def rewrite_question(
    question,
    history=None
):
    """
    Converts a conversational follow-up into a standalone
    retrieval question.

    Example:

        Previous:
            User: Who is Umair?

        Current:
            What information is mentioned about him?

        Result:
            What information is mentioned about Umair?
    """

    question = str(
        question or ""
    ).strip()

    if not question:
        return question

    # ------------------------------------------------------
    # No history
    # ------------------------------------------------------

    if not history:
        return question

    history_parts = []

    for message in history[-8:]:

        role = str(
            message.get(
                "role",
                ""
            )
        ).lower()

        # Support both "text" and "content"
        text = message.get(
            "text"
        )

        if not text:
            text = message.get(
                "content",
                ""
            )

        text = str(
            text or ""
        ).strip()

        if not text:
            continue

        if role == "user":
            label = "User"

        elif role in {
            "bot",
            "assistant"
        }:
            label = "Assistant"

        else:
            continue

        history_parts.append(
            f"{label}: {text}"
        )

    if not history_parts:
        return question

    conversation = "\n".join(
        history_parts
    )

    safe_question = (
        redact_sensitive_information(
            question
        )
    )

    safe_history = (
        redact_sensitive_information(
            conversation
        )
    )

    prompt = f"""
You are the query-rewriting component of a production
Retrieval-Augmented Generation system.

Your ONLY job is to convert the latest user question into
a standalone question suitable for document retrieval.

RULES:

1. Preserve the exact intent of the latest question.

2. Use conversation history only to resolve ambiguous
   references such as:
   he, him, his, she, her, they, them, it, this, that,
   these, those, etc.

3. If the latest question is already standalone,
   return it unchanged.

4. If the latest question refers to a person, document,
   organization, topic, or other entity from the previous
   conversation, explicitly name that entity.

5. Do NOT answer the question.

6. Do NOT add facts that are not present in the conversation.

7. Do NOT change or invent names.

8. Return ONLY the rewritten question.

9. Do NOT include explanations.

10. Do NOT include quotation marks.

================ CONVERSATION HISTORY ================

{safe_history}

================ LATEST USER QUESTION ================

{safe_question}

================ STANDALONE RETRIEVAL QUESTION ================
"""

    try:

        response = _generate_content(
            prompt,
            operation="question rewriting"
        )

        rewritten = (
            response.text or ""
        ).strip()

        if not rewritten:
            return question

        rewritten = rewritten.strip(
            "\"'"
        )

        print(
            "\n"
            + "=" * 70
        )

        print(
            "QUESTION REWRITING"
        )

        print(
            "=" * 70
        )

        print(
            "Original :",
            question
        )

        print(
            "Rewritten:",
            rewritten
        )

        print(
            "=" * 70
        )

        return rewritten

    except Exception as error:

        print(
            "\nQuestion rewriting failed."
        )

        print(
            type(error).__name__,
            str(error)
        )

        # --------------------------------------------------
        # Important:
        # RAG should not completely crash if rewriting fails.
        # --------------------------------------------------

        return question


# ==========================================================
# Generate Answer
# ==========================================================

def generate_answer(
    question,
    context
):
    """
    Generate a grounded answer using ONLY retrieved context.
    """

    # ------------------------------------------------------
    # Protect context BEFORE Gemini sees it
    # ------------------------------------------------------

    safe_context = (
        redact_sensitive_information(
            context
        )
    )

    safe_question = (
        redact_sensitive_information(
            question
        )
    )

    # ------------------------------------------------------
    # Production RAG prompt
    # ------------------------------------------------------

    prompt = f"""
You are a document-based Retrieval-Augmented Generation
assistant.

Your job is to answer the user's question using ONLY the
document context provided below.

==================== STRICT RULES ====================

1. Use ONLY the provided document context.

2. Do NOT use outside knowledge.

3. Do NOT invent, guess, assume, or hallucinate information.

4. If the requested information is not available in the
   provided context, respond exactly:

"I couldn't find that information in the uploaded documents."

5. Do NOT mix information between unrelated people,
   documents, or sources.

6. Only combine information when the user's question
   explicitly asks for a comparison.

==================== PRIVACY RULES ====================

7. NEVER reveal sensitive personal information.

8. NEVER provide:

- CNIC numbers
- Bank account numbers
- IBAN numbers
- Phone numbers
- Email addresses
- Passwords
- Authentication credentials
- Private financial identifiers
- Other unique sensitive identifiers

9. If the context contains sensitive information,
   describe it generally instead.

10. If the user directly asks for a sensitive identifier,
    respond exactly:

"I can't provide sensitive personal or financial information."

11. Names may be provided when relevant and supported
    by the document.

12. General employment information, skills, education,
    and descriptions may be provided when supported.

==================== DOCUMENT ISOLATION ====================

13. Treat every document as a separate source.

14. Never assume information about one person belongs
    to another person.

15. Never mention an unrelated document simply because
    it exists in the knowledge base.

16. Only answer from the supplied context.

==================== DOCUMENT CONTEXT ====================

{safe_context}

==================== USER QUESTION ====================

{safe_question}

==================== ANSWER ====================

Provide a concise, natural answer based ONLY on the
document context.
"""

    print(
        "\n"
        + "=" * 60
    )

    print(
        "Sending privacy-filtered request to Gemini"
    )

    print(
        f"Model: {GEMINI_MODEL}"
    )

    print(
        "=" * 60
    )

    try:

        response = _generate_content(
            prompt,
            operation="answer generation"
        )

        answer = (
            response.text or ""
        ).strip()

    except Exception as error:

        # --------------------------------------------------
        # Don't expose raw Gemini exception to the user.
        # --------------------------------------------------

        print(
            "\nAnswer generation failed:"
        )

        print(
            type(error).__name__,
            str(error)
        )

        return (
            "The AI service is temporarily "
            "unavailable. Please try again later."
        )

    # ------------------------------------------------------
    # Final privacy protection
    # ------------------------------------------------------

    answer = (
        redact_sensitive_information(
            answer
        )
    )

    return answer
