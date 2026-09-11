from typing import Dict


def vision_to_context(vision_data: Dict) -> str:
    """
    Converts Vision module's structured output into a plain-text
    paragraph, treated as a single document chunk by the existing
    RAG pipeline. No changes to retrieval/embedding logic needed.

    vision_data is a raw row from the extracted_data table. The real
    product match fields live inside content.primary_match:

    {
        "content": {
            "matches": [ ... ranked list of matches ... ],
            "primary_match": {
                "rank": 1,
                "product_id": 44998,
                "product_display_name": "Maxima Men Black Digital Watch",
                "category": "Accessories",
                "article_type": "Watches",
                "sub_category": "Watches",
                "base_colour": "Black",
                "gender": "Men",
                "usage": "Casual",
                "season": "Winter",
                "similarity_score": 0.6215,
                "image_url": "/catalog-images/44998.jpg",
                ...
            }
        }
    }
    """

    if not vision_data:
        return ""

    content = vision_data.get("content") or {}

    # Real product fields are nested one level deeper, inside "primary_match".
    match = content.get("primary_match") or {}

    parts = []

    product_id = match.get("product_id")
    if product_id:
        parts.append(f"Product {product_id}.")

    # Muneeb's field is "product_display_name", not "product_name".
    product_name = match.get("product_display_name")
    if product_name:
        parts.append(f"Name: {product_name}.")

    category = match.get("category")
    if category:
        parts.append(f"Category: {category}.")

    article_type = match.get("article_type")
    if article_type:
        parts.append(f"Article type: {article_type}.")

    colour = match.get("base_colour")
    if colour:
        parts.append(f"Colour: {colour}.")

    gender = match.get("gender")
    if gender:
        parts.append(f"Gender: {gender}.")

    usage = match.get("usage")
    if usage:
        parts.append(f"Usage: {usage}.")

    season = match.get("season")
    if season:
        parts.append(f"Season: {season}.")

    similarity_score = match.get("similarity_score")
    if similarity_score is not None:
        parts.append(f"Visual match confidence: {similarity_score}.")

    return " ".join(parts)


def build_vision_citation(vision_data: Dict) -> Dict:
    """
    Builds a citation object for a Vision-sourced item, matching
    the 'catalog_item' shape defined in docs/api-contracts.md.
    """

    content = vision_data.get("content") or {}
    match = content.get("primary_match") or {}

    return {
        "source_type": "catalog_item",
        "source": match.get("product_display_name", "Unknown product"),
        "page_number": None,
        "product_id": match.get("product_id"),
        "image_url": match.get("image_url"),
    }