"""Internal HTTP facade for the real Paper#4 pipeline.

FastAPI is an optional dependency, so importing a parsing or registry submodule
must not eagerly import the HTTP application.
"""
