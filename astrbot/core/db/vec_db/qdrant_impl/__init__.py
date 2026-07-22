def __getattr__(name: str):
    if name == "QdrantVecDB":
        from .vec_db import QdrantVecDB

        return QdrantVecDB
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["QdrantVecDB"]
