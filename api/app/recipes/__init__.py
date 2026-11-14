"""Recipes (#34, technical-plan.md §5.4, vision §7): the data files, the hybrid search,
scaling to portions and the product links that turn a recipe into order lines.

    uv run python -m app.loaders.recipes            # recipes, links and vectors into Postgres
    uv run python -m app.recipes.embeddings         # regenerate data/recipe-embeddings.json.gz
"""
